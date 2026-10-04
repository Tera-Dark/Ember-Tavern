"""M3: bounded experimental rules, deterministic goldens, and atomic API writes."""
from copy import deepcopy
import json

from fastapi import HTTPException
import pytest

from server.db import connection, dump
from server.rules import ENGINES, contract_hash, engine_for
from server.rules.cooperative import CooperativeSettlementRules
from server.rules.dnd5e import Dnd5eRules
from server.schemas import Decision
from server.state import load_state, migrate_state
from test_game import account, act, key, revise

DND='dnd5e-srd-5.2.1/v1'
COOP='ember-coop-settlement/v1'


def preset_room(client, headers, identity, *, host_plays=True):
    catalog=client.get('/api/presets',headers=headers)
    assert catalog.status_code==200,catalog.text
    item=next(entry for entry in catalog.json()['entries'] if entry['id']==identity)
    assert item['compatibility']['can_create'],item['compatibility']
    response=client.post('/api/rooms/from-preset',headers=headers,json={
        'title':item['name'],'package_hash':item['package_hash'],'ai_mode':'demo',
        'host_plays':host_plays,'request_key':key()})
    assert response.status_code==201,response.text
    return response.json()


def rule_body(current, **fields):
    return {**revise(current),'branch':current['branch'],**fields}


def plan(client,current,headers,**order):
    return client.post(f"/api/rooms/{current['id']}/rules/strategy/orders",headers=headers,
                       json=rule_body(current,**order))


def settle(client,current,headers):
    return client.post(f"/api/rooms/{current['id']}/rules/strategy/settle",headers=headers,
                       json=rule_body(current))


def advance(client,current,headers,scene_id,transition_id):
    return client.post(f"/api/rooms/{current['id']}/campaign/advance",headers=headers,
                       json={**revise(current),'scene_id':scene_id,'transition_id':transition_id})


def raw_state(room_id):
    with connection() as con:
        encoded=con.execute('SELECT state_json FROM rooms WHERE id=?',(room_id,)).fetchone()[0]
    return load_state(encoded)


def test_m3_rule_contracts_are_versioned_experimental_subsets():
    catalog=__import__('server.rules',fromlist=['adapter_catalog']).adapter_catalog()
    adapters={item['id']:item for item in catalog['adapters']}
    assert adapters[DND]['status']=='experimental'
    assert adapters[COOP]['status']=='experimental'
    assert adapters[DND]['implementation_version']=='0.1.0'
    assert adapters[COOP]['implementation_version']=='0.1.0'
    assert len(adapters[DND]['implementation_sha256'])==64
    assert adapters[DND]['contract_sha256']==contract_hash(ENGINES[DND])
    assert '法术' in adapters[DND]['not_supported']
    assert '休息时长和中断条件' in adapters[DND]['not_supported']
    assert 'PvP' in adapters[COOP]['not_supported']
    assert not any('完整' in value for value in (adapters[DND]['name'],adapters[COOP]['name']))


def test_m3_migration_initializes_only_locked_rule_state_and_projection_hides_internals(client):
    _,headers,_=account(client,'m3migration')
    current=preset_room(client,headers,'echo-well-srd521')
    assert current['state']['schema_version']==4
    assert current['state']['world']['rule_system']==DND
    assert current['state']['game_rules']['adapter_id']==DND
    assert '_rule_state' not in current['state']
    raw=raw_state(current['id'])
    assert raw['schema_version']==4 and raw['_rule_state']['adapter_id']==DND

    old=deepcopy(raw)
    old['schema_version']=3
    old.pop('_rule_state',None)
    migrated=migrate_state(old)
    assert migrated['schema_version']==4
    assert migrated['_rule_state']['adapter_id']==DND
    light=deepcopy(old)
    light['world']['rule_system']='ember-light/v1'
    light.pop('_preset_lock',None)
    light.pop('_scenario',None)
    light['schema_version']=3
    migrated_light=migrate_state(light)
    assert migrated_light['schema_version']==4 and migrated_light['_rule_state'] is None


def test_generic_dossier_edits_cannot_overwrite_dnd_sheet_state(client):
    _, headers, _ = account(client, 'm3dossierlock')
    current = preset_room(client, headers, 'echo-well-srd521')
    character = next(char for char in current['state']['characters'] if char['name'] == '旧路探寻者')
    path = f"/api/rooms/{current['id']}/characters/{character['id']}"
    card = {key: value for key, value in character.items() if key not in ('id', 'assigned_to')}
    original_state = deepcopy(current['state'])
    original_raw_state = raw_state(current['id'])
    original_events = len(current['events'])
    extension = deepcopy(card['extensions'])
    extension['dnd5e.srd-5.2.1/v1']['level'] = 2
    illegal_edits = [
        {**card, 'hp': character['hp'] - 1},
        {**card, 'max_hp': character['max_hp'] + 1},
        {**card, 'extensions': extension},
    ]
    for edit in illegal_edits:
        response = client.put(path, headers=headers, json={**revise(current), **edit})
        assert response.status_code == 409, response.text
        unchanged = client.get(f"/api/rooms/{current['id']}", headers=headers).json()
        assert unchanged['revision'] == current['revision']
        assert len(unchanged['events']) == original_events
        assert unchanged['state'] == original_state
        assert raw_state(current['id']) == original_raw_state

    narrative = {**card, 'description': '只更新叙事档案，不触碰 5e 规则属性。'}
    response = client.put(path, headers=headers, json={**revise(current), **narrative})
    assert response.status_code == 200, response.text
    updated = response.json()
    updated_character = next(char for char in updated['state']['characters']
                             if char['id'] == character['id'])
    assert updated_character['description'] == narrative['description']
    assert updated_character['hp'] == character['hp']
    assert updated_character['max_hp'] == character['max_hp']
    assert updated['state']['game_rules']['sheets'][character['id']] == \
        current['state']['game_rules']['sheets'][character['id']]


def test_dnd_character_import_initializes_sheet_and_invalid_profile_is_atomic(client):
    _, headers, _ = account(client, 'm3characterimport')
    current = preset_room(client, headers, 'echo-well-srd521')
    document = client.get('/api/creators/templates/character').json()
    document['rule_system'] = DND
    document['character'].update({
        'name': '导入的守井人', 'hp': 8, 'max_hp': 10,
        'extensions': {'dnd5e.srd-5.2.1/v1': {
            'level': 2,
            'ability_scores': {'strength': 14, 'dexterity': 12, 'constitution': 13,
                               'intelligence': 10, 'wisdom': 10, 'charisma': 10},
            'armor_class': 14, 'weapon_die': 8, 'weapon_ability': 'strength',
            'hit_die': 10, 'max_hit_points': 14,
        }},
    })
    imported = client.post(f"/api/rooms/{current['id']}/content/import", headers=headers,
                           json={**revise(current), 'kind': 'character', 'document': document,
                                 'mode': 'merge'})
    assert imported.status_code == 200, imported.text
    current = imported.json()
    character = next(char for char in current['state']['characters'] if char['name'] == '导入的守井人')
    assert character['assigned_to'] is None
    assert character['hp'] == 8 and character['max_hp'] == 14
    sheet = current['state']['game_rules']['sheets'][character['id']]
    assert sheet['level'] == 2 and sheet['hit_points'] == 8 and sheet['max_hit_points'] == 14

    invalid = deepcopy(document)
    invalid['character']['extensions']['dnd5e.srd-5.2.1/v1']['level'] = 9
    before_state = raw_state(current['id'])
    rejected = client.post(f"/api/rooms/{current['id']}/content/import", headers=headers,
                           json={**revise(current), 'kind': 'character', 'document': invalid,
                                 'mode': 'merge'})
    assert rejected.status_code == 422, rejected.text
    unchanged = client.get(f"/api/rooms/{current['id']}", headers=headers).json()
    assert unchanged['revision'] == current['revision']
    assert len(unchanged['state']['characters']) == len(current['state']['characters'])
    assert raw_state(current['id']) == before_state


def test_dnd5e_api_golden_critical_hit_assignment_receipt_and_rule_lock(client,monkeypatch):
    host,host_headers,_=account(client,'m3dndhost')
    player,player_headers,_=account(client,'m3dndplayer')
    current=preset_room(client,host_headers,'echo-well-srd521')
    player_join=client.post('/api/rooms/join',headers=player_headers,json={'code':current['code']})
    assert player_join.status_code==200,player_join.text
    current=player_join.json()
    pathfinder=next(char for char in current['state']['characters'] if char['name']=='旧路探寻者')
    assigned=client.post(f"/api/rooms/{current['id']}/characters/{pathfinder['id']}/assign",
                         headers=host_headers,json={**revise(current),'user_id':player['id']})
    assert assigned.status_code==200,assigned.text
    current=assigned.json()

    sheet_path=f"/api/rooms/{current['id']}/rules/dnd5e/sheets/{pathfinder['id']}"
    profile={
        'level':1,
        'ability_scores':{'strength':10,'dexterity':18,'constitution':14,'intelligence':12,'wisdom':14,'charisma':10},
        'armor_class':13,'weapon_die':6,'weapon_ability':'dexterity','hit_die':8,'max_hit_points':18,
    }
    denied=client.put(sheet_path,headers=player_headers,json=rule_body(current,**profile))
    assert denied.status_code==403
    sheet=client.put(sheet_path,headers=host_headers,json=rule_body(current,**profile))
    assert sheet.status_code==200,sheet.text
    current=sheet.json()
    public_sheet=current['state']['game_rules']['sheets'][pathfinder['id']]
    assert public_sheet['ability_scores']['dexterity']==18
    assert public_sheet['max_hit_points']==18
    assert current['state']['characters'][1]['max_hp']==18

    sequence=[0,0,0,0,0,19,3,4]
    def deterministic_randbelow(sides):
        assert sequence,'golden random sequence exhausted'
        value=sequence.pop(0)
        assert 0<=value<sides,(value,sides)
        return value
    monkeypatch.setattr('server.routes.rules.secrets.randbelow',deterministic_randbelow)
    encounter_path=f"/api/rooms/{current['id']}/rules/dnd5e/encounters"
    enemy={'name':'灰岩守卫（主持简化数据）','hit_points':8,'armor_class':13,
           'initiative_bonus':0,'attack_bonus':2,'damage_die':6,'damage_bonus':1}
    player_start=client.post(encounter_path,headers=player_headers,json=rule_body(current,**enemy))
    assert player_start.status_code==403
    started=client.post(encounter_path,headers=host_headers,json=rule_body(current,**enemy))
    assert started.status_code==200,started.text
    current=started.json()
    encounter=current['state']['game_rules']['encounter']
    assert encounter['status']=='active'
    assert encounter['order'][0]['character_id']==pathfinder['id']
    assert encounter['order'][0]['initiative']==5
    assert encounter['current_actor']=='旧路探寻者'

    wrong_turn=client.post(f"/api/rooms/{current['id']}/rules/dnd5e/actions",headers=host_headers,
                           json=rule_body(current,character_id=current['state']['characters'][0]['id'],action='attack'))
    assert wrong_turn.status_code==409
    latest=client.get(f"/api/rooms/{current['id']}",headers=host_headers).json()
    assert latest['revision']==current['revision']

    attack_key='m3-critical-golden-0001'
    attack_body=rule_body(current,character_id=pathfinder['id'],action='attack')
    attack_body['request_key']=attack_key
    attacked=client.post(f"/api/rooms/{current['id']}/rules/dnd5e/actions",headers=player_headers,json=attack_body)
    assert attacked.status_code==200,attacked.text
    after=attacked.json()
    result=after['events'][-1]['payload']['results'][0]
    assert result=={
        'text':'旧路探寻者 攻击 灰岩守卫（主持简化数据）：d20 20 + +4 + 熟练 +2 = 26，AC 13，命中。伤害骰 [4, 5]，共 13；目标生命 0/8。',
        'kind':'attack','character_id':pathfinder['id'],'foe':'灰岩守卫（主持简化数据）',
        'd20':20,'ability':'dexterity','ability_modifier':4,'proficiency_bonus':2,
        'attack_total':26,'armor_class':13,'hit':True,'critical':True,
        'damage_rolls':[4,5],'damage':13,'target_hit_points':0,
    }
    assert after['state']['game_rules']['encounter']['status']=='victory'
    assert after['state']['characters'][1]['hp']==11
    duplicate=client.post(f"/api/rooms/{current['id']}/rules/dnd5e/actions",headers=player_headers,json=attack_body)
    assert duplicate.status_code==200 and duplicate.json()['revision']==after['revision']
    assert sequence==[]
    assert '_rule_state' not in json.dumps(after['state'])

    switched={**after['state']['world'],'rule_system':'ember-coop-settlement/v1'}
    change=client.put(f"/api/rooms/{current['id']}/world",headers=host_headers,
                      json={**revise(after),**switched})
    assert change.status_code==409


def test_dnd_dodge_disadvantage_and_rest_goldens():
    engine=Dnd5eRules()
    character={'id':'hero-one','name':'守望者','hp':5,'max_hp':10,'extensions':{
        'dnd5e.srd-5.2.1/v1':{
            'level':1,'ability_scores':{'strength':10,'dexterity':14,'constitution':14,'intelligence':10,'wisdom':10,'charisma':10},
            'armor_class':13,'weapon_die':6,'weapon_ability':'strength','hit_die':6,'max_hit_points':10,
        }}}
    state={'characters':[character]}
    state['_rule_state']=engine.initial_rule_state(state)
    start_rolls=[10,0]
    result=engine.start_encounter(state,{'name':'简化训练靶','hit_points':30,'armor_class':18,
                                        'initiative_bonus':0,'attack_bonus':0,'damage_die':6,'damage_bonus':1},
                                 lambda sides:start_rolls.pop(0))
    assert result['payload']['status']=='active'
    assert state['_rule_state']['encounter']['order'][0]['character_id']=='hero-one'
    actions=[16,3]
    dodged=engine.take_turn(state,{'character_id':'hero-one','action':'dodge'},lambda sides:actions.pop(0))
    enemy=next(item for item in dodged['payload']['results'] if item['kind']=='enemy_attack')
    assert enemy=={'text':'简化训练靶 攻击 守望者：d20 [17, 4]，攻击值 4 未命中 AC 13。',
                   'kind':'enemy_attack','target_id':'hero-one','d20':[17,4],'chosen':4,
                   'attack_total':4,'armor_class':13,'hit':False,'critical':False,
                   'damage_rolls':[],'damage':0,'remaining_hp':5,'disadvantage':True}
    assert state['_rule_state']['sheets']['hero-one']['dodging'] is False

    state['_rule_state']['encounter']['status']='retreated'
    character['hp']=5
    state['_rule_state']['sheets']['hero-one']['hit_points']=5
    short=engine.rest(state,{'character_id':'hero-one','kind':'short'},lambda sides:1)
    assert short['payload']=={'kind':'short_rest','die':2,'constitution_modifier':2,'healed':4,
                              'remaining_hit_dice':0,'character_id':'hero-one','remaining_hp':9}
    assert character['hp']==9 and character['max_hp']==10
    long=engine.rest(state,{'character_id':'hero-one','kind':'long'},lambda sides:0)
    assert long['payload']=={'kind':'long_rest','healed':1,'recovered_hit_dice':1,
                             'remaining_hit_dice':1,'character_id':'hero-one','remaining_hp':10}
    assert character['hp']==10


def test_strategy_invalid_orders_are_non_mutating_and_reservations_are_projected(client):
    host,host_headers,_=account(client,'m3coopillegal')
    current=preset_room(client,host_headers,'ashen-canal-coop')
    baseline_revision=current['revision']
    baseline_events=len(current['events'])
    invalid=plan(client,current,host_headers,action='repair')
    assert invalid.status_code==422
    unchanged=client.get(f"/api/rooms/{current['id']}",headers=host_headers).json()
    assert unchanged['revision']==baseline_revision
    assert len(unchanged['events'])==baseline_events
    assert unchanged['state']['game_rules']['orders']==[]

    request_key='m3-order-receipt-0001'
    body=rule_body(current,action='build',building='quarry')
    body['request_key']=request_key
    submitted=client.post(f"/api/rooms/{current['id']}/rules/strategy/orders",headers=host_headers,json=body)
    assert submitted.status_code==200,submitted.text
    after=submitted.json()
    board=after['state']['game_rules']
    assert board['my_order_submitted'] is True
    assert board['resources']=={'food':10,'timber':6,'stone':3,'coin':4}
    assert board['available_resources']=={'food':8,'timber':3,'stone':3,'coin':4}
    public_order=board['orders'][0]
    assert public_order['actor_name']==host['display_name']
    assert 'actor_id' not in public_order and 'reserved_cost' not in public_order
    stored=raw_state(current['id'])['_rule_state']['orders'][0]
    assert stored['actor_id']==host['id'] and stored['reserved_cost']['timber']==3

    replay=client.post(f"/api/rooms/{current['id']}/rules/strategy/orders",headers=host_headers,json=body)
    assert replay.status_code==200 and replay.json()['revision']==after['revision']
    assert len(replay.json()['state']['game_rules']['orders'])==1


def test_cooperative_economic_golden_goal_ends_and_gates_story_ending(client,monkeypatch):
    _,headers,_=account(client,'m3coopgold')
    current=preset_room(client,headers,'ashen-canal-coop')
    entered=advance(client,current,headers,'council','go-worksite')
    assert entered.status_code==200,entered.text
    current=entered.json()
    assert current['state']['campaign']['current_scene']=='worksite'
    early=advance(client,current,headers,'worksite','spring')
    assert early.status_code==409
    current=client.get(f"/api/rooms/{current['id']}",headers=headers).json()
    assert current['revision']==entered.json()['revision']
    assert not next(edge for edge in current['state']['campaign']['transitions'] if edge['id']=='spring')['ready']

    first=plan(client,current,headers,action='build',building='quarry')
    assert first.status_code==200,first.text
    current=first.json()
    monkeypatch.setattr('server.routes.rules.secrets.randbelow',lambda sides:3)
    first_result=settle(client,current,headers)
    assert first_result.status_code==200,first_result.text
    current=first_result.json()
    golden=current['state']['game_rules']['settlements'][-1]
    assert golden=={
        'turn_resolved':1,'orders':[{'id':golden['orders'][0]['id'],'actor_name':'m3coopgold','action':'build','detail':"建造 quarry，消耗 {'food': 2, 'timber': 3, 'stone': 0, 'coin': 0}"}],
        'production':{'food':2,'timber':2,'stone':2,'coin':0},
        'random_event':{'roll':4,'name':'平安无事','changes':{}},
        'resources_before':{'food':10,'timber':6,'stone':3,'coin':4},
        'resources_after':{'food':10,'timber':5,'stone':5,'coin':4},
        'bridge_repairs':0,'status':'active','next_turn':2,
    }
    assert current['state']['game_rules']['my_order_submitted'] is False

    monkeypatch.setattr('server.routes.rules.secrets.randbelow',lambda sides:5)
    schedule=[('build',{'building':'sawmill'}),('repair',{}),('repair',{}),
              ('trade',{'source':'food','destination':'stone','amount':2}),('repair',{})]
    for action_name,details in schedule:
        response=plan(client,current,headers,action=action_name,**details)
        assert response.status_code==200,response.text
        current=response.json()
        settled=settle(client,current,headers)
        assert settled.status_code==200,settled.text
        current=settled.json()

    board=current['state']['game_rules']
    assert board['status']=='completed' and board['phase']=='completed'
    assert board['bridge_repairs']==3 and board['turn']==6
    assert board['orders']==[] and board['my_order_submitted'] is False
    assert len(board['settlements'])==6
    final=board['settlements'][-1]
    assert final['turn_resolved']==6 and final['status']=='completed'
    assert final['random_event'] is None
    assert final['production']=={'food':0,'timber':0,'stone':0,'coin':0}
    assert final['resources_after']=={'food':8,'timber':5,'stone':2,'coin':4}
    spring=next(edge for edge in current['state']['campaign']['transitions'] if edge['id']=='spring')
    winter=next(edge for edge in current['state']['campaign']['transitions'] if edge['id']=='winter')
    assert spring['ready'] is True and winter['ready'] is False
    finished=advance(client,current,headers,'worksite','spring')
    assert finished.status_code==200,finished.text
    assert finished.json()['state']['campaign']['completed'] is True
    assert finished.json()['state']['campaign']['current_scene']=='ending-spring'

    terminal=plan(client,finished.json(),headers,action='repair')
    assert terminal.status_code==409


def test_cooperative_expiry_unlocks_the_loss_ending(client, monkeypatch):
    _, headers, _ = account(client, 'm3coopexpiry')
    current = preset_room(client, headers, 'ashen-canal-coop')
    entered = advance(client, current, headers, 'council', 'go-worksite')
    assert entered.status_code == 200, entered.text
    current = entered.json()
    monkeypatch.setattr('server.routes.rules.secrets.randbelow', lambda sides: 3)

    for _ in range(8):
        submitted = plan(client, current, headers, action='trade', source='food',
                         destination='stone', amount=2)
        assert submitted.status_code == 200, submitted.text
        current = submitted.json()
        settled = settle(client, current, headers)
        assert settled.status_code == 200, settled.text
        current = settled.json()

    board = current['state']['game_rules']
    assert board['status'] == 'expired' and board['turn'] == 9
    assert board['bridge_repairs'] == 0
    winter = next(edge for edge in current['state']['campaign']['transitions'] if edge['id'] == 'winter')
    spring = next(edge for edge in current['state']['campaign']['transitions'] if edge['id'] == 'spring')
    assert winter['ready'] is True and spring['ready'] is False
    finished = advance(client, current, headers, 'worksite', 'winter')
    assert finished.status_code == 200, finished.text
    assert finished.json()['state']['campaign']['completed'] is True
    assert finished.json()['state']['campaign']['current_scene'] == 'ending-winter'
    assert plan(client, finished.json(), headers, action='repair').status_code == 409


def test_coop_member_order_permissions_and_atomic_settlement_failure(client):
    host,host_headers,_=account(client,'m3coophost')
    player,player_headers,_=account(client,'m3coopplayer')
    current=preset_room(client,host_headers,'ashen-canal-coop')
    joined=client.post('/api/rooms/join',headers=player_headers,json={'code':current['code']})
    assert joined.status_code==200,joined.text
    current=joined.json()
    denied=settle(client,current,player_headers)
    assert denied.status_code==403

    submission=plan(client,current,player_headers,action='build',building='market')
    assert submission.status_code==200,submission.text
    current=submission.json()
    assert current['state']['game_rules']['my_order_submitted'] is True
    player_view=client.get(f"/api/rooms/{current['id']}",headers=player_headers).json()
    rules_view=player_view['state']['game_rules']
    assert rules_view['my_order_submitted'] is True
    assert all('actor_id' not in item and 'reserved_cost' not in item for item in rules_view['orders'])
    assert '_rule_state' not in player_view['state']
    assert host['id'] not in json.dumps(rules_view)

    duplicate_actor=plan(client,current,player_headers,action='trade',source='food',destination='stone',amount=2)
    assert duplicate_actor.status_code==409
    current=client.get(f"/api/rooms/{current['id']}",headers=host_headers).json()
    assert len(current['state']['game_rules']['orders'])==1
    assert settle(client,current,player_headers).status_code==403
    assert settle(client,current,host_headers).status_code==200

    engine=CooperativeSettlementRules()
    state={'characters':[]}
    state['_rule_state']=engine.initial_rule_state(state)
    user={'id':'unit-user','display_name':'测试玩家'}
    engine.plan_order(state,{'action':'build','building':'quarry'},user,1)
    state['_rule_state']['resources']['timber']=2
    before=deepcopy(state)
    with pytest.raises(HTTPException) as error:
        engine.settle_turn(state,lambda sides:5)
    assert error.value.status_code==409
    assert state==before


def test_coop_deadline_has_a_deterministic_terminal_failure():
    engine=CooperativeSettlementRules()
    state={'characters':[]}
    state['_rule_state']=engine.initial_rule_state(state)
    state['_rule_state']['turn']=8
    user={'id':'late-user','display_name':'期限测试'}
    engine.plan_order(state,{'action':'build','building':'market'},user,1)
    result=engine.settle_turn(state,lambda sides:5)
    assert result['payload']['random_event']=={'roll':6,'name':'平安无事','changes':{}}
    assert result['payload']['status']=='expired'
    assert result['payload']['next_turn'] is None
    assert state['_rule_state']['turn']==9
    assert state['_rule_state']['phase']=='completed'


def test_m3_invalid_ai_check_does_not_partially_apply_rules_or_narration(client, monkeypatch):
    from server.plugin_runtime.manager import manager

    _, headers, _ = account(client, 'm3invalidai')
    current = preset_room(client, headers, 'echo-well-srd521')
    before_state = deepcopy(current['state'])
    before_rules = raw_state(current['id'])['_rule_state']

    async def invalid_proposal(*args):
        return Decision(narration='非法提议中的部分叙事不得提交。',
                       check={'attribute': 'strength', 'dc': 12, 'reason': '未支持的 5e 检定',
                              'risk': 'harm'}), {'mode': 'demo'}

    monkeypatch.setattr(manager.items['ai-host']['backend'], 'gm', invalid_proposal)
    after = act(client, current, headers, text='测试一个未经支持的规则检定')
    assert after.status_code == 200, after.text
    result = after.json()
    assert result['state']['awaiting_gm'] is True
    assert result['state']['pending_check'] is None
    assert result['state']['scene'] == before_state['scene']
    assert result['state']['facts'] == before_state['facts']
    assert raw_state(current['id'])['_rule_state'] == before_rules
    assert not any(event['type'] == 'gm' and '非法提议中的部分叙事' in event['text']
                   for event in result['events'])


def test_m3_ai_light_check_proposals_are_rejected_and_narration_does_not_change_rules():
    state={'world':{'rule_system':DND},'characters':[],'_rule_state':None}
    engine=Dnd5eRules()
    with pytest.raises(ValueError,match='轻规则检定'):
        engine.validate_decision(state,Decision(narration='攻击成功',check={'attribute':'strength','dc':12,'reason':'攻击','risk':'harm'}))
    coop=CooperativeSettlementRules()
    state={'world':{'rule_system':COOP},'characters':[],'_rule_state':coop.initial_rule_state({'characters':[]})}
    before=deepcopy(state['_rule_state'])
    with pytest.raises(ValueError,match='轻规则检定'):
        coop.validate_decision(state,Decision(narration='建造完成',check={'attribute':'strength','dc':12,'reason':'建造','risk':'none'}))
    assert state['_rule_state']==before
