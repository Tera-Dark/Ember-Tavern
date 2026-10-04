"""Narrow, experimental d20 combat adapter for SRD 5.2.1 compatibility.

This adapter intentionally ships no copied SRD prose, named creatures, spells,
class features, or monster stat blocks. Randomness is supplied by the server.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException
from ..contracts.rules_m3 import (Dnd5eSheet, DndEncounterSetup, DndTurnAction,
                                  DndRest)
from ..schemas import Decision
from .light import free_roll

RULE_ID = 'dnd5e-srd-5.2.1/v1'
EXTENSION_ID = 'dnd5e.srd-5.2.1/v1'
IMPLEMENTATION_VERSION = '0.1.0'
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
RULE_TEXT = (
    '实验规则：SRD 5.2.1（5.5e 核心机制）的有限 d20 战斗切片；支持等级 1–4 的通用能力值、先攻、'
    '单次武器攻击、AC、生命、闪避与简化休息。生命上限、AC、武器骰由房主手动指定；敌方在遭遇设置中输入，'
    '每个敌方回合攻击当前生命最低的角色（平手按角色 ID 排序）。当前不追踪休息时长与中断条件，也没有职业特性、法术、技能熟练、'
    '死亡豁免、反应、专注、状态效果、多重攻击或怪物目录。未支持的规则由房主另行裁决；'
    'AI 不会以余烬轻规则检定替代本规则。'
)


def modifier(score):
    return (int(score) - 10) // 2


def _roll(sides, randbelow):
    value = randbelow(sides)
    if type(value) is not int or not 0 <= value < sides:
        raise ValueError('规则随机源必须返回范围内的整数')
    return value + 1


def _sheet_profile(character):
    extensions = character.get('extensions') or {}
    raw = extensions.get(EXTENSION_ID, {})
    try:
        return Dnd5eSheet.model_validate(raw).model_dump(mode='json')
    except Exception as exc:
        raise ValueError(f"角色「{character.get('name', '')}」的 5e 规则扩展无效") from exc


def _build_sheet(character, profile):
    profile = deepcopy(profile)
    maximum = profile.pop('max_hit_points', None) or character['max_hp']
    sheet = {
        **profile,
        'hit_points': min(character['hp'], maximum),
        'max_hit_points': maximum,
        'hit_dice_remaining': profile['level'],
        'proficiency_bonus': 2 + (profile['level'] - 1) // 4,
        'dodging': False,
    }
    character['max_hp'] = maximum
    character['hp'] = sheet['hit_points']
    character.setdefault('extensions', {})[EXTENSION_ID] = {
        **profile, 'max_hit_points': maximum,
    }
    return sheet


def _public_sheet(sheet):
    return {key: sheet[key] for key in (
        'level', 'ability_scores', 'armor_class', 'weapon_die', 'weapon_ability',
        'hit_die', 'hit_points', 'max_hit_points', 'hit_dice_remaining',
        'dodging', 'proficiency_bonus')}


def _actor_name(state, character_id):
    character = next((item for item in state['characters'] if item['id'] == character_id), None)
    return character['name'] if character else '未知角色'


def _sync_hp(state, character_id, sheet):
    character = next((item for item in state['characters'] if item['id'] == character_id), None)
    if character is not None:
        character['hp'] = sheet['hit_points']
        character['max_hp'] = sheet['max_hit_points']


def _active(state):
    rules = state.get('_rule_state')
    if not isinstance(rules, dict) or rules.get('adapter_id') != RULE_ID:
        raise HTTPException(409, '此房间的 5e 规则状态尚未初始化；请从对应玩法预设新建房间')
    return rules


def _living_characters(rules):
    return [identity for identity, sheet in rules['sheets'].items() if sheet['hit_points'] > 0]


def _finish_if_terminal(rules):
    encounter = rules.get('encounter')
    if not encounter or encounter['status'] != 'active':
        return
    if encounter['foe']['hit_points'] <= 0:
        encounter['status'] = 'victory'
    elif not _living_characters(rules):
        encounter['status'] = 'defeat'


def _record(encounter, text, payload):
    record = {'round': encounter['round'], 'text': text, **payload}
    encounter['log'].append(record)
    encounter['log'] = encounter['log'][-40:]


def _enemy_turn(state, rules, randbelow):
    encounter = rules['encounter']
    foe = encounter['foe']
    candidates = [(sheet['hit_points'], identity) for identity, sheet in rules['sheets'].items()
                  if sheet['hit_points'] > 0]
    if not candidates:
        encounter['status'] = 'defeat'
        return '队伍已无人能够继续行动。', {'kind': 'defeat'}
    _, target_id = min(candidates, key=lambda pair: (pair[0], pair[1]))
    target = rules['sheets'][target_id]
    first = _roll(20, randbelow)
    disadvantage = bool(target.get('dodging'))
    rolls = [first, _roll(20, randbelow)] if disadvantage else [first]
    chosen = min(rolls) if disadvantage else first
    total = chosen + foe['attack_bonus']
    hit = chosen == 20 or (chosen != 1 and total >= target['armor_class'])
    critical = chosen == 20
    damage_rolls = [_roll(foe['damage_die'], randbelow) for _ in range(2 if critical else 1)] if hit else []
    damage = max(0, sum(damage_rolls) + foe['damage_bonus']) if hit else 0
    target['hit_points'] = max(0, target['hit_points'] - damage)
    _sync_hp(state, target_id, target)
    _finish_if_terminal(rules)
    if hit:
        text = (f"{foe['name']} 攻击 {_actor_name(state, target_id)}：d20 {rolls}，"
                f"攻击值 {total} 对 AC {target['armor_class']} 命中，伤害 {damage}；"
                f"生命 {target['hit_points']}/{target['max_hit_points']}。")
    else:
        text = (f"{foe['name']} 攻击 {_actor_name(state, target_id)}：d20 {rolls}，"
                f"攻击值 {total} 未命中 AC {target['armor_class']}。")
    payload = {'kind': 'enemy_attack', 'target_id': target_id, 'd20': rolls,
               'chosen': chosen, 'attack_total': total, 'armor_class': target['armor_class'],
               'hit': hit, 'critical': critical, 'damage_rolls': damage_rolls,
               'damage': damage, 'remaining_hp': target['hit_points'],
               'disadvantage': disadvantage}
    _record(encounter, text, payload)
    return text, payload


def _advance_to_player(state, rules, randbelow):
    encounter = rules['encounter']
    notes = []
    limit = max(4, len(encounter['order']) * 3)
    for _ in range(limit):
        _finish_if_terminal(rules)
        if encounter['status'] != 'active':
            break
        if encounter['current_index'] < 0:
            encounter['current_index'] = 0
        else:
            encounter['current_index'] = (encounter['current_index'] + 1) % len(encounter['order'])
            if encounter['current_index'] == 0:
                encounter['round'] += 1
        seat = encounter['order'][encounter['current_index']]
        if seat['kind'] == 'foe':
            text, payload = _enemy_turn(state, rules, randbelow)
            notes.append({'text': text, **payload})
            continue
        sheet = rules['sheets'].get(seat['character_id'])
        if not sheet or sheet['hit_points'] <= 0:
            continue
        # A Dodge remains active until the start of this character's next turn.
        sheet['dodging'] = False
        return notes
    _finish_if_terminal(rules)
    if encounter['status'] == 'active' and not encounter['order']:
        encounter['status'] = 'defeat'
    return notes


class Dnd5eRules:
    id = RULE_ID
    extension_id = EXTENSION_ID
    description = RULE_TEXT
    status = 'experimental'

    def roll(self, expression):
        return free_roll(expression)

    def resolve(self, state):
        raise HTTPException(422, '5e 实验规则没有余烬轻规则的待检定流程；请用规则工作台支持的命令')

    def validate_decision(self, state, value):
        decision = Decision.model_validate(value.model_dump() if isinstance(value, Decision) else value)
        if decision.check is not None:
            raise ValueError('5e 子集未支持 AI 轻规则检定提议；本轮不会提交，请用已支持的规则命令或由房主裁决')
        return decision

    def initial_rule_state(self, state):
        sheets = {}
        for character in state.get('characters', []):
            sheets[character['id']] = _build_sheet(character, _sheet_profile(character))
        return {'adapter_id': self.id, 'sheets': sheets, 'encounter': None}

    def add_character(self, state, character):
        rules = _active(state)
        if rules.get('encounter') and rules['encounter']['status'] == 'active':
            raise HTTPException(409, '遭遇进行中不能加入新角色')
        try:
            sheet = _build_sheet(character, _sheet_profile(character))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        rules['sheets'][character['id']] = sheet

    def update_character_card(self, state, character):
        rules = _active(state)
        if rules.get('encounter') and rules['encounter']['status'] == 'active':
            raise HTTPException(409, '遭遇进行中不能修改角色卡；请先结束遭遇')
        prior = rules['sheets'].get(character['id'])
        if prior is None:
            self.add_character(state, character)
            return
        profile = _sheet_profile(character)
        requested_maximum = profile.pop('max_hit_points', None)
        maximum = requested_maximum or character['max_hp']
        profile['max_hit_points'] = maximum
        sheet = _build_sheet(character, profile)
        sheet['hit_points'] = min(character['hp'], sheet['max_hit_points'])
        character['hp'] = sheet['hit_points']
        # Generic card edits may update narrative metadata, but never reset
        # hit dice or alter an active encounter behind the typed rule API.
        sheet['hit_dice_remaining'] = min(prior['hit_dice_remaining'], sheet['level'])
        rules['sheets'][character['id']] = sheet

    def remove_character(self, state, character_id):
        rules = _active(state)
        if rules.get('encounter') and rules['encounter']['status'] == 'active':
            raise HTTPException(409, '遭遇进行中不能移除角色')
        rules['sheets'].pop(character_id, None)

    def project_state(self, state):
        rules = _active(state)
        encounter = deepcopy(rules.get('encounter'))
        if encounter and encounter['status'] == 'active' and 0 <= encounter['current_index'] < len(encounter['order']):
            encounter['current_actor'] = encounter['order'][encounter['current_index']]['name']
        return {
            'adapter_id': self.id,
            'implementation_version': IMPLEMENTATION_VERSION,
            'implementation_sha256': IMPLEMENTATION_SHA256,
            'status': self.status,
            'sheets': {identity: _public_sheet(sheet) for identity, sheet in rules['sheets'].items()},
            'encounter': encounter,
            'supported': ['initiative', 'attack', 'damage', 'AC', 'HP', 'dodge', 'short-rest', 'long-rest'],
            'not_supported': ['职业特性', '法术', '技能与豁免', '死亡豁免', '反应', '专注', '多重攻击', '怪物目录', '移动与距离', '休息时长和中断条件'],
        }

    def update_sheet(self, state, character_id, value):
        rules = _active(state)
        if rules.get('encounter') and rules['encounter']['status'] == 'active':
            raise HTTPException(409, '遭遇进行中不能重写角色卡')
        character = next((item for item in state['characters'] if item['id'] == character_id), None)
        if character is None:
            raise HTTPException(404, '角色不存在于当前时间线')
        profile = Dnd5eSheet.model_validate(value).model_dump(mode='json')
        maximum = profile.pop('max_hit_points', None) or character['max_hp']
        sheet = {**profile, 'hit_points': min(character['hp'], maximum),
                 'max_hit_points': maximum, 'hit_dice_remaining': profile['level'],
                 'proficiency_bonus': 2 + (profile['level'] - 1) // 4,
                 'dodging': False}
        rules['sheets'][character_id] = sheet
        character['max_hp'] = maximum
        character.setdefault('extensions', {})[EXTENSION_ID] = {
            **profile, 'max_hit_points': maximum,
        }
        _sync_hp(state, character_id, sheet)
        return {'text': f"房主更新了「{character['name']}」的 5e 实验角色卡。",
                'payload': {'kind': 'sheet_update', 'character_id': character_id,
                            'level': profile['level']}}

    def start_encounter(self, state, value, randbelow):
        rules = _active(state)
        if rules.get('encounter') and rules['encounter']['status'] == 'active':
            raise HTTPException(409, '当前已有进行中的遭遇')
        setup = DndEncounterSetup.model_validate(value).model_dump(mode='json')
        participants = []
        for character in state['characters']:
            sheet = rules['sheets'].get(character['id'])
            if not sheet:
                raise HTTPException(422, f"角色「{character['name']}」缺少 5e 角色卡")
            if sheet['hit_points'] > 0:
                initiative_roll = _roll(20, randbelow)
                dex_mod = modifier(sheet['ability_scores']['dexterity'])
                participants.append({'kind': 'character', 'character_id': character['id'],
                                     'name': character['name'], 'initiative_roll': initiative_roll,
                                     'initiative_bonus': dex_mod, 'initiative': initiative_roll + dex_mod})
        if not participants:
            raise HTTPException(422, '队伍没有生命值大于 0 的角色，不能开始遭遇')
        foe_roll = _roll(20, randbelow)
        participants.append({'kind': 'foe', 'name': setup['name'], 'initiative_roll': foe_roll,
                             'initiative_bonus': setup['initiative_bonus'],
                             'initiative': foe_roll + setup['initiative_bonus']})
        participants.sort(key=lambda item: (-item['initiative'], 0 if item['kind'] == 'foe' else 1,
                                            item.get('character_id', '')))
        order = [{key: value for key, value in item.items() if key != 'initiative_roll'}
                 for item in participants]
        rules['encounter'] = {
            'status': 'active', 'round': 1, 'current_index': -1, 'order': order,
            'foe': {'name': setup['name'], 'hit_points': setup['hit_points'],
                    'max_hit_points': setup['hit_points'], 'armor_class': setup['armor_class'],
                    'attack_bonus': setup['attack_bonus'], 'damage_die': setup['damage_die'],
                    'damage_bonus': setup['damage_bonus']},
            'log': [],
        }
        opening = [{'text': '先攻顺序：' + ' → '.join(
            (item['name'] + f" ({item['initiative']})") for item in participants),
            'kind': 'initiative', 'order': deepcopy(participants)}]
        opening.extend(_advance_to_player(state, rules, randbelow))
        return {'text': f"实验遭遇开始；先攻顺序已由服务器掷骰。{opening[0]['text']}",
                'payload': {'kind': 'encounter_start', 'order': opening[0]['order'],
                            'automatic_actions': opening[1:], 'round': rules['encounter']['round'],
                            'status': rules['encounter']['status']}}

    def take_turn(self, state, value, randbelow):
        rules = _active(state)
        action = DndTurnAction.model_validate(value)
        encounter = rules.get('encounter')
        if not encounter or encounter['status'] != 'active':
            raise HTTPException(409, '没有进行中的 5e 遭遇')
        sheet = rules['sheets'].get(action.character_id)
        if not sheet:
            raise HTTPException(404, '角色没有对应的 5e 角色卡')
        if sheet['hit_points'] <= 0:
            raise HTTPException(422, '生命值为 0 的角色不能行动')
        seat = encounter['order'][encounter['current_index']]
        if seat['kind'] != 'character' or seat['character_id'] != action.character_id:
            active_name = seat['name']
            raise HTTPException(409, f'尚未轮到该角色；当前行动者是「{active_name}」')
        records = []
        actor_name = _actor_name(state, action.character_id)
        if action.action == 'attack':
            ability = sheet['weapon_ability']
            ability_mod = modifier(sheet['ability_scores'][ability])
            first = _roll(20, randbelow)
            total = first + ability_mod + sheet['proficiency_bonus']
            foe = encounter['foe']
            hit = first == 20 or (first != 1 and total >= foe['armor_class'])
            critical = first == 20
            damage_rolls = [_roll(sheet['weapon_die'], randbelow) for _ in range(2 if critical else 1)] if hit else []
            damage = max(0, sum(damage_rolls) + ability_mod) if hit else 0
            foe['hit_points'] = max(0, foe['hit_points'] - damage)
            text = (f"{actor_name} 攻击 {foe['name']}：d20 {first} + {ability_mod:+d} + "
                    f"熟练 +{sheet['proficiency_bonus']} = {total}，AC {foe['armor_class']}，"
                    f"{'命中' if hit else '未命中'}。")
            if hit:
                text += f"伤害骰 {damage_rolls}，共 {damage}；目标生命 {foe['hit_points']}/{foe['max_hit_points']}。"
            result = {'kind': 'attack', 'character_id': action.character_id, 'foe': foe['name'],
                      'd20': first, 'ability': ability, 'ability_modifier': ability_mod,
                      'proficiency_bonus': sheet['proficiency_bonus'], 'attack_total': total,
                      'armor_class': foe['armor_class'], 'hit': hit, 'critical': critical,
                      'damage_rolls': damage_rolls, 'damage': damage,
                      'target_hit_points': foe['hit_points']}
            _record(encounter, text, result)
            records.append({'text': text, **result})
        else:
            sheet['dodging'] = True
            text = f'{actor_name} 采取防御性闪避；直到其下回合开始，下一次针对该角色的敌方攻击采用劣势。'
            result = {'kind': 'dodge', 'character_id': action.character_id,
                      'round': encounter['round'], 'effect': 'disadvantage-until-next-turn'}
            _record(encounter, text, result)
            records.append({'text': text, **result})
        _finish_if_terminal(rules)
        records.extend(_advance_to_player(state, rules, randbelow))
        return {'text': ' '.join(item['text'] for item in records),
                'payload': {'kind': 'turn', 'character_id': action.character_id,
                            'action': action.action, 'results': records,
                            'round': encounter['round'], 'status': encounter['status'],
                            'current_actor': (encounter['order'][encounter['current_index']]['name']
                                              if encounter['status'] == 'active' else None)}}

    def end_encounter(self, state):
        rules = _active(state)
        encounter = rules.get('encounter')
        if not encounter or encounter['status'] != 'active':
            raise HTTPException(409, '没有进行中的遭遇')
        encounter['status'] = 'retreated'
        text = '房主结束了当前实验遭遇；已结算的生命变化保留。'
        _record(encounter, text, {'kind': 'encounter_end'})
        return {'text': text, 'payload': {'kind': 'encounter_end', 'status': 'retreated'}}

    def rest(self, state, value, randbelow):
        rules = _active(state)
        rest = DndRest.model_validate(value)
        encounter = rules.get('encounter')
        if encounter and encounter['status'] == 'active':
            raise HTTPException(409, '进行中的遭遇不能休息')
        sheet = rules['sheets'].get(rest.character_id)
        if not sheet:
            raise HTTPException(404, '角色没有对应的 5e 角色卡')
        actor_name = _actor_name(state, rest.character_id)
        before = sheet['hit_points']
        if rest.kind == 'short':
            if sheet['hit_dice_remaining'] <= 0:
                raise HTTPException(422, '没有可用于短休的生命骰')
            die = _roll(sheet['hit_die'], randbelow)
            constitution = modifier(sheet['ability_scores']['constitution'])
            healed = min(sheet['max_hit_points'] - before, max(0, die + constitution))
            sheet['hit_points'] += healed
            sheet['hit_dice_remaining'] -= 1
            text = f'{actor_name} 短休并消耗 1 枚生命骰（{die}{constitution:+d}），恢复 {healed} 点生命。'
            payload = {'kind': 'short_rest', 'die': die, 'constitution_modifier': constitution,
                       'healed': healed, 'remaining_hit_dice': sheet['hit_dice_remaining']}
        else:
            sheet['hit_points'] = sheet['max_hit_points']
            recovered = min(sheet['level'], max(1, sheet['level'] // 2))
            old_dice = sheet['hit_dice_remaining']
            sheet['hit_dice_remaining'] = min(sheet['level'], old_dice + recovered)
            healed = sheet['hit_points'] - before
            text = f'{actor_name} 长休，恢复 {healed} 点生命并恢复 {sheet["hit_dice_remaining"] - old_dice} 枚生命骰。'
            payload = {'kind': 'long_rest', 'healed': healed,
                       'recovered_hit_dice': sheet['hit_dice_remaining'] - old_dice,
                       'remaining_hit_dice': sheet['hit_dice_remaining']}
        _sync_hp(state, rest.character_id, sheet)
        payload['character_id'] = rest.character_id
        payload['remaining_hp'] = sheet['hit_points']
        return {'text': text, 'payload': payload}

    def contract(self):
        return {
            'id': self.id, 'implementation_version': IMPLEMENTATION_VERSION,
            'implementation_sha256': IMPLEMENTATION_SHA256, 'name': 'SRD 5.2.1 有限战斗实验',
            'description': self.description, 'status': self.status,
            'scope': ['等级 1–4 通用角色卡', '先攻', '单次武器攻击与伤害', '闪避', '简化短休 / 长休', '房主输入的简化敌方单次攻击'],
            'not_supported': ['职业与子职业特性', '法术', '技能与豁免', '死亡豁免', '反应', '专注', '多重攻击', '怪物目录', '移动与距离', '休息时长和中断条件'],
            'dice': {'max_count': 20, 'min_sides': 2, 'max_sides': 100, 'max_modifier': 100},
            'character_schema': Dnd5eSheet.model_json_schema(),
            'encounter_schema': DndEncounterSetup.model_json_schema(),
            'action_schema': DndTurnAction.model_json_schema(),
            'check_schema': Decision.model_json_schema(),
        }
