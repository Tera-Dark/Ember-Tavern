"""Authoritative light-rules adapter. Randomness never comes from the AI or browser."""
import re
import secrets
from fastapi import HTTPException
from ..schemas import Decision

RULE_ID = 'ember-light/v1'
RULE_TEXT = '轻规则 v1：d20 + 属性修正 ≥ 难度。天然20大成功、天然1大失败。难度8–20。失败时，仅明确标注生命风险扣1生命，压力风险加1压力。生命0无法继续行动；压力上限6。自由掷骰不改变角色状态。'

def parse_dice(expression):
    match = re.fullmatch(r'(\d{1,2})d(\d{1,3})([+-]\d{1,3})?', expression.lower().replace(' ', ''))
    if not match:
        raise HTTPException(422, '骰子格式应为 1d20、2d6 或 1d20+2')
    count, sides, modifier = int(match[1]), int(match[2]), int(match[3] or 0)
    if not 1 <= count <= 20 or not 2 <= sides <= 100 or abs(modifier) > 100:
        raise HTTPException(422, '仅支持1–20颗、2–100面骰，修正值±100以内')
    return count, sides, modifier


def free_roll(expression):
    count, sides, modifier = parse_dice(expression)
    rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
    return {'expression':f'{count}d{sides}' + (f'{modifier:+d}' if modifier else ''), 'rolls':rolls, 'modifier':modifier, 'total':sum(rolls)+modifier, 'kind':'free'}


def resolve_check(state):
    check = state['pending_check']
    char = next((item for item in state['characters'] if item['id'] == check['character_id']), None)
    if char is None:
        raise HTTPException(404, '角色不存在于当前时间线')
    raw = secrets.randbelow(20) + 1
    modifier = check['modifier']
    total = raw + modifier
    success = raw == 20 or (raw != 1 and total >= check['dc'])
    outcome = '大成功' if raw == 20 else '大失败' if raw == 1 else '成功' if success else '失败'
    consequence = '无属性变化'
    if not success and check['risk'] == 'harm':
        char['hp'] = max(0, char['hp'] - 1)
        consequence = f"{char['name']} 生命 −1"
    elif not success and check['risk'] == 'stress':
        char['stress'] = min(6, char['stress'] + 1)
        consequence = f"{char['name']} 压力 +1"
    result = dict(check, rolls=[raw], total=total, success=success, outcome=outcome,
                  consequence=consequence, expression=f'1d20{modifier:+d}', kind='check', character_name=char['name'])
    state['pending_check'] = None
    return result


class LightRules:
    id = RULE_ID
    description = RULE_TEXT

    def roll(self, expression):
        return free_roll(expression)

    def resolve(self, state):
        return resolve_check(state)

    def validate_decision(self, state, value):
        decision = Decision.model_validate(value.model_dump() if isinstance(value, Decision) else value)
        if (state.get('continuation') or {}).get('phase') == 'roll' and decision.check is not None:
            raise ValueError('已完成检定，主持提供者不能再次提出检定')
        return decision

    def contract(self):
        return {'id': self.id, 'name': '余烬通用轻规则', 'description': self.description,
                'dice': {'max_count': 20, 'min_sides': 2, 'max_sides': 100, 'max_modifier': 100},
                'check_schema': Decision.model_json_schema()}
