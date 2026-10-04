"""M2 structured state, round coordination, memory provenance and rule registry tests."""
from copy import deepcopy
import json

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from server.config import settings
import server.app as game_app
from server.contracts.campaign_state import CampaignState
from server.schemas import Decision
from server.db import connection, dump
from server.plugin_runtime.manager import manager
from server.rules import ENGINES, adapter_catalog, contract_hash, engine_for, validate_registry
from server.state import load_state, migrate_state
from test_game import account, key, revise, room


def action(client, current, headers, character_id, text, *, request_key=None, branch=None):
    return client.post(f"/api/rooms/{current['id']}/actions", headers=headers, json={
        **revise(current), 'request_key': request_key or key(), 'character_id': character_id,
        'text': text, 'branch': current['branch'] if branch is None else branch})


def set_action_mode(client, current, headers, mode='round', *, request_key=None):
    return client.put(f"/api/rooms/{current['id']}/action-mode", headers=headers, json={
        **revise(current), 'request_key': request_key or key(), 'branch': current['branch'], 'mode': mode})


def settle(client, current, headers, *, request_key=None):
    return client.post(f"/api/rooms/{current['id']}/action-round/settle", headers=headers, json={
        **revise(current), 'request_key': request_key or key(), 'branch': current['branch']})


def join_player(client, owner_headers, player_headers, current, player):
    response = client.post('/api/rooms/join', headers=player_headers, json={'code': current['code']})
    assert response.status_code == 200, response.text
    current = response.json()
    character = current['state']['characters'][1]
    response = client.post(f"/api/rooms/{current['id']}/characters/{character['id']}/assign",
                           headers=owner_headers, json={**revise(current), 'user_id': player['id']})
    assert response.status_code == 200, response.text
    return response.json(), character['id']


def raw_state(room_id):
    with connection() as con:
        return load_state(con.execute('SELECT state_json FROM rooms WHERE id=?', (room_id,)).fetchone()[0])


def test_campaign_state_contract_has_bounded_unique_records():
    valid = CampaignState.model_validate({'quests':[{'id':'quest-one','title':'Find the key'}]})
    assert valid.format == 'ember.campaign-state/v1'
    assert valid.quests[0].visibility == 'public'

    with pytest.raises(ValidationError, match='ID 不能重复'):
        CampaignState.model_validate({'quests':[
            {'id':'quest-one','title':'One'}, {'id':'quest-one','title':'Two'}]})
    with pytest.raises(ValidationError, match='资源当前值'):
        CampaignState.model_validate({'resources':[{'id':'resource-one','name':'Food','value':3,'minimum':0,'maximum':2}]})
    with pytest.raises(ValidationError, match='下限'):
        CampaignState.model_validate({'resources':[{'id':'resource-one','name':'Food','value':3,'minimum':4,'maximum':2}]})
    with pytest.raises(ValidationError, match='120 条'):
        CampaignState.model_validate({
            'quests':[{'id':f'quest-{i:02d}','title':'Quest'} for i in range(40)],
            'npcs':[{'id':f'npc-{i:02d}','name':'NPC'} for i in range(40)],
            'resources':[{'id':f'resource-{i:02d}','name':'Resource','value':0} for i in range(41)],
        })


def test_campaign_state_api_projects_private_records_and_receipts(client):
    host, host_headers, _ = account(client, 'ledgerhost')
    player, player_headers, _ = account(client, 'ledgerplayer')
    current = room(client, host_headers)
    current, _ = join_player(client, host_headers, player_headers, current, player)
    ledger = {
        'format':'ember.campaign-state/v1',
        'quests':[
            {'id':'quest-public','title':'Find the brass key','status':'active','visibility':'public'},
            {'id':'quest-secret','title':'A hidden promise','summary':'LEDGER_PRIVATE_MARKER','visibility':'gm'},
        ],
        'npcs':[
            {'id':'npc-public','name':'Aro','summary':'Ferry captain','visibility':'public'},
            {'id':'npc-secret','name':'The patron','summary':'NPC_PRIVATE_MARKER','visibility':'gm'},
        ],
        'resources':[
            {'id':'resource-public','name':'Rations','value':4,'minimum':0,'maximum':8,'unit':'days'},
            {'id':'resource-secret','name':'Debt','value':9,'minimum':0,'maximum':20,'visibility':'gm'},
        ],
    }
    request_key = key()
    body = {**revise(current), 'request_key':request_key, 'branch':current['branch'], 'ledger':ledger}
    response = client.put(f"/api/rooms/{current['id']}/campaign-state", headers=host_headers, json=body)
    assert response.status_code == 200, response.text
    updated = response.json()
    duplicate = client.put(f"/api/rooms/{current['id']}/campaign-state", headers=host_headers, json=body)
    assert duplicate.status_code == 200 and duplicate.json()['revision'] == updated['revision']

    host_ledger = client.get(f"/api/rooms/{current['id']}/campaign-state", headers=host_headers).json()['ledger']
    public_ledger = client.get(f"/api/rooms/{current['id']}/campaign-state", headers=player_headers).json()['ledger']
    assert len(host_ledger['quests']) == 2 and len(host_ledger['npcs']) == 2 and len(host_ledger['resources']) == 2
    assert [item['id'] for item in public_ledger['quests']] == ['quest-public']
    assert [item['id'] for item in public_ledger['npcs']] == ['npc-public']
    assert [item['id'] for item in public_ledger['resources']] == ['resource-public']
    player_view = client.get(f"/api/rooms/{current['id']}", headers=player_headers).json()
    assert public_ledger == player_view['state']['campaign_state']
    assert '_campaign_state' not in updated['state']
    assert client.get(f"/api/rooms/{current['id']}/campaign-state", headers=player_headers).status_code == 200
    assert 'LEDGER_PRIVATE_MARKER' not in json.dumps(player_view, ensure_ascii=False)
    assert 'NPC_PRIVATE_MARKER' not in json.dumps(player_view, ensure_ascii=False)
    safe_event = next(event for event in player_view['events'] if event['type'] == 'campaign_state')
    assert safe_event['text'] == '房主更新了战役状态记录。'
    assert 'changed_ids' not in safe_event['payload']
    assert len([event for event in updated['events'] if event['type'] == 'campaign_state']) == 1

    denied = client.put(f"/api/rooms/{current['id']}/campaign-state", headers=player_headers,
                        json={**revise(updated), 'branch':updated['branch'], 'ledger':ledger})
    assert denied.status_code == 403
    invalid = deepcopy(ledger)
    invalid['resources'][0]['value'] = 99
    rejected = client.put(f"/api/rooms/{current['id']}/campaign-state", headers=host_headers,
                          json={**revise(updated), 'branch':updated['branch'], 'ledger':invalid})
    assert rejected.status_code == 422


def test_rule_catalog_pins_light_adapter_and_unknown_rules_are_rejected(client):
    validate_registry()
    catalog = client.get('/api/rules')
    assert catalog.status_code == 200
    data = catalog.json()
    assert data['registration'] == 'reviewed-host-code-only'
    assert [item['id'] for item in data['adapters']] == [
        'dnd5e-srd-5.2.1/v1','ember-coop-settlement/v1','ember-light/v1']
    adapter = next(item for item in data['adapters'] if item['id']=='ember-light/v1')
    assert adapter['implementation_version']
    assert len(adapter['implementation_sha256']) == 64
    assert adapter['contract_sha256'] == contract_hash(ENGINES['ember-light/v1'])
    assert ENGINES['ember-light/v1'].contract()['check_schema']['title'] == 'Decision'

    with pytest.raises(HTTPException) as error:
        engine_for({'world':{'rule_system':'unreviewed/homebrew/v1'}})
    assert error.value.status_code == 422

    _, headers, _ = account(client, 'rulehost')
    current = room(client, headers)
    state = raw_state(current['id'])
    state['world']['rule_system'] = 'unreviewed/homebrew/v1'
    with connection() as con:
        con.execute('UPDATE rooms SET state_json=? WHERE id=?', (dump(state), current['id']))
    result = client.post(f"/api/rooms/{current['id']}/dice", headers=headers,
                         json={**revise(current), 'expression':'1d20'})
    assert result.status_code == 422


def test_previous_and_current_state_snapshots_migrate_to_m2_schema(client):
    _, headers, _ = account(client, 'migrationhost')
    current = room(client, headers)
    base = raw_state(current['id'])
    for key_name in ('_campaign_state', '_action_mode', '_action_round', '_memory_summary'):
        base.pop(key_name, None)
    base['schema_version'] = 2
    migrated_previous = migrate_state(base)
    assert migrated_previous['schema_version'] == 4
    assert migrated_previous['_campaign_state']['format'] == 'ember.campaign-state/v1'
    assert migrated_previous['_action_mode'] == 'free'
    assert migrated_previous['_action_round'] is None and migrated_previous['_memory_summary'] is None
    assert migrate_state(migrated_previous) == migrated_previous

    current_state = raw_state(current['id'])
    assert current_state['schema_version'] == 4
    assert migrate_state(current_state) == current_state
    with pytest.raises(ValueError, match='版本'):
        migrate_state(dict(current_state, schema_version=5))


def test_action_round_collects_once_per_character_and_settlement_is_idempotent(client):
    host, host_headers, _ = account(client, 'roundhost')
    player, player_headers, _ = account(client, 'roundplayer')
    current = room(client, host_headers)
    current, player_character = join_player(client, host_headers, player_headers, current, player)
    host_character = current['state']['characters'][0]['id']

    # A player cannot enable collection or settle a team round.
    assert set_action_mode(client, current, player_headers).status_code == 403
    current = set_action_mode(client, current, host_headers).json()
    assert current['state']['action_mode'] == 'round'
    assert current['state']['action_round']['required_count'] == 2

    # Replaying the same request receipt cannot duplicate a submission.
    receipt_key = 'round-player-receipt-0001'
    submitted = action(client, current, player_headers, player_character, '我等待潮声退去', request_key=receipt_key)
    assert submitted.status_code == 200, submitted.text
    after_player = submitted.json()
    assert after_player['state']['action_round']['submitted_count'] == 1
    assert after_player['state']['action_round']['status'] == 'collecting'
    assert not any(event['type'] == 'gm' for event in after_player['events'])
    replay = action(client, current, player_headers, player_character, '我等待潮声退去', request_key=receipt_key)
    assert replay.status_code == 200
    after_receipt = replay.json()
    assert replay.status_code == 200 and replay.json()['revision'] == after_player['revision']
    duplicate_character = action(client, after_receipt, player_headers, player_character, '再提交一次', request_key='round-player-receipt-0002')
    assert duplicate_character.status_code == 409
    assert len([event for event in after_receipt['events'] if event['type'] == 'action_intent']) == 1

    # A different branch number is rejected before changing the round.
    stale_branch = action(client, after_receipt, player_headers, player_character, '旧时间线行动',
                          request_key='round-player-receipt-0003', branch=after_receipt['branch'] + 1)
    assert stale_branch.status_code == 409

    owner_submission = action(client, after_receipt, host_headers, host_character, '我和同伴商量下一步')
    assert owner_submission.status_code == 200, owner_submission.text
    collected = owner_submission.json()
    round_view = collected['state']['action_round']
    assert round_view['submitted_count'] == round_view['required_count'] == 2
    assert round_view['ready'] and round_view['status'] == 'collecting'
    assert not any(event['type'] == 'gm' for event in collected['events'])

    assert settle(client, collected, player_headers).status_code == 403
    settle_key = 'round-settle-receipt-0001'
    resolved = settle(client, collected, host_headers, request_key=settle_key)
    assert resolved.status_code == 200, resolved.text
    finished = resolved.json()
    assert finished['state']['action_round']['status'] == 'completed'
    assert finished['state']['turn'] == 1 and finished['state']['pending_check'] is None
    assert len([event for event in finished['events'] if event['type'] == 'gm']) == 1

    duplicate_settle = settle(client, collected, host_headers, request_key=settle_key)
    assert duplicate_settle.status_code == 200
    assert duplicate_settle.json()['revision'] == finished['revision']
    assert len([event for event in duplicate_settle.json()['events'] if event['type'] == 'gm']) == 1

    next_round = action(client, finished, player_headers, player_character, '我等待第二轮开始')
    assert next_round.status_code == 200, next_round.text
    next_round_view = next_round.json()['state']['action_round']
    assert next_round_view['number'] == 2 and next_round_view['status'] == 'collecting'


def test_action_round_host_can_early_settle_and_rejects_empty_settlement(client):
    host, host_headers, _ = account(client, 'earlyhost')
    player, player_headers, _ = account(client, 'earlyplayer')
    current = room(client, host_headers)
    current, player_character = join_player(client, host_headers, player_headers, current, player)
    current = set_action_mode(client, current, host_headers).json()

    empty_settle = settle(client, current, host_headers)
    assert empty_settle.status_code == 422
    submitted = action(client, current, player_headers, player_character, '我等待一会儿')
    assert submitted.status_code == 200
    current = submitted.json()
    round_view = current['state']['action_round']
    assert round_view['submitted_count'] == 1 and round_view['required_count'] == 2
    assert round_view['missing_character_ids']

    resolved = settle(client, current, host_headers)
    assert resolved.status_code == 200, resolved.text
    final = resolved.json()
    settle_event = next(event for event in final['events'] if event['type'] == 'action_round' and '已汇总' in event['text'])
    assert settle_event['payload']['missing_count'] == 1
    assert '提前结算' in settle_event['text']
    assert final['state']['action_round']['status'] == 'completed'


def test_memory_summary_requires_active_sources_and_is_hidden_from_players(client, monkeypatch):
    host, host_headers, _ = account(client, 'memoryhost')
    player, player_headers, _ = account(client, 'memoryplayer')
    current = room(client, host_headers)
    joined = client.post('/api/rooms/join', headers=player_headers, json={'code':current['code']})
    assert joined.status_code == 200, joined.text
    current = joined.json()
    response = client.post(f"/api/rooms/{current['id']}/gm/note", headers=host_headers,
                           json={**revise(current), 'text':'The brass key was found in the tide cellar.'})
    assert response.status_code == 200, response.text
    current = response.json()
    source = current['events'][-1]
    summary = 'The party found the brass key; ownership is still uncertain.'

    no_source = client.put(f"/api/rooms/{current['id']}/memory/summary", headers=host_headers,
                           json={**revise(current), 'branch':current['branch'], 'text':summary, 'source_event_ids':[]})
    assert no_source.status_code == 422

    summary_response = client.put(f"/api/rooms/{current['id']}/memory/summary", headers=host_headers,
                                  json={**revise(current), 'branch':current['branch'], 'text':summary,
                                        'source_event_ids':[source['id']]})
    assert summary_response.status_code == 200, summary_response.text
    saved = summary_response.json()
    memory_api = client.get(f"/api/rooms/{current['id']}/memory", headers=host_headers)
    assert memory_api.status_code == 200
    assert memory_api.json()['summary']['text'] == summary
    assert source['id'] in {event['id'] for event in memory_api.json()['sources']}
    assert client.get(f"/api/rooms/{current['id']}/memory", headers=player_headers).status_code == 403

    player_view = client.get(f"/api/rooms/{current['id']}", headers=player_headers).json()
    assert 'memory_summary' not in player_view['state']
    assert summary not in json.dumps(player_view, ensure_ascii=False)
    hidden_event = next(event for event in player_view['events'] if event['type'] == 'memory_summary')
    assert summary not in hidden_event['text']
    assert 'source_event_ids' not in hidden_event['payload']
    with connection() as con:
        room_row = con.execute('SELECT * FROM rooms WHERE id=?', (current['id'],)).fetchone()
        plugin_resource = manager.resource(room_row, raw_state(current['id']), 'core.campaign-state/v1', host, con)
    assert plugin_resource and summary not in json.dumps(plugin_resource, ensure_ascii=False)

    monkeypatch.setattr(settings, 'memory_summary_context_chars', 24)
    context = manager_context(current['id'])
    assert context['memory_summary']['text'] == summary[:24]
    assert context['_selection']['memory_summary']['included']
    assert context['_selection']['memory_summary']['truncated']
    assert context['_selection']['memory_summary']['source_event_ids'] == [source['id']]

    # Neither sources from another room nor archived future events may be bound.
    other_room = room(client, host_headers)
    cross_room = client.put(f"/api/rooms/{other_room['id']}/memory/summary", headers=host_headers,
                            json={**revise(other_room), 'branch':other_room['branch'], 'text':'Cross-room',
                                  'source_event_ids':[source['id']]})
    assert cross_room.status_code == 409

    current = client.post(f"/api/rooms/{current['id']}/gm/note", headers=host_headers,
                          json={**revise(saved), 'text':'Later event that will be archived.'}).json()
    target = current['events'][0]['id']
    rewound = client.post(f"/api/rooms/{current['id']}/rollback", headers=host_headers,
                          json={**revise(current), 'target_event_id':target, 'reason':'M2 source validation'}).json()
    assert rewound['branch'] == current['branch'] + 1
    stale_source = client.put(f"/api/rooms/{current['id']}/memory/summary", headers=host_headers,
                              json={**revise(rewound), 'branch':rewound['branch'], 'text':'Archived source',
                                    'source_event_ids':[source['id']]})
    assert stale_source.status_code == 409
    assert client.get(f"/api/rooms/{current['id']}/memory", headers=host_headers).json()['summary'] is None
    assert 'memory_summary' not in manager_context(current['id'])


def manager_context(room_id):
    from server.retrieval import model_context
    return model_context(room_id, raw_state(room_id), 'continue the story')


def test_memory_summary_rejects_duplicate_and_recursive_sources(client):
    _, headers, _ = account(client, 'memoryvalid')
    current = room(client, headers)
    note_response = client.post(f"/api/rooms/{current['id']}/gm/note", headers=headers,
                                json={**revise(current), 'text':'A current source.'})
    assert note_response.status_code == 200
    note = note_response.json()
    source = note['events'][-1]['id']
    payload = {**revise(note), 'branch':note['branch'], 'text':'A summary.', 'source_event_ids':[source, source]}
    duplicate = client.put(f"/api/rooms/{current['id']}/memory/summary", headers=headers, json=payload)
    assert duplicate.status_code == 422

    saved_response = client.put(f"/api/rooms/{current['id']}/memory/summary", headers=headers,
                                json={**revise(note), 'branch':note['branch'], 'text':'A summary.',
                                      'source_event_ids':[source]})
    assert saved_response.status_code == 200
    saved = saved_response.json()
    summary_event_id = saved['events'][-1]['id']
    recursive = client.put(f"/api/rooms/{current['id']}/memory/summary", headers=headers,
                           json={**revise(saved), 'branch':saved['branch'], 'text':'A revised summary.',
                                 'source_event_ids':[summary_event_id]})
    assert recursive.status_code == 409


def test_three_sessions_preserve_structured_facts_across_sixty_actions(client, monkeypatch):
    async def deterministic_gm(*args):
        return Decision(narration='动作已记录，当前事实没有变化。'), {
            'mode':'demo', 'label':'M2 deterministic test host', 'retrieval_count':0,
            'duration_ms':0, 'context_ids':[]}

    monkeypatch.setattr(game_app, 'run_gm', deterministic_gm)
    # This is a state-integrity test, not a rate-limit test; exercise more than
    # the production 12-action/minute throttle without waiting several minutes.
    monkeypatch.setattr(game_app, 'throttle', lambda *args, **kwargs: None)
    _, headers, _ = account(client, 'sixtysessionhost')
    facts = {
        'format':'ember.campaign-state/v1',
        'quests':[{'id':'quest-key-fact','title':'Keep the lighthouse supplied',
                   'summary':'The brass key is held by the ferry captain.',
                   'status':'active','visibility':'public'}],
        'npcs':[{'id':'npc-ferry-captain','name':'Ferry captain','role':'Keeper',
                 'summary':'Trusts the party; the key remains in her custody.',
                 'status':'ally','relationship':3,'visibility':'public'}],
        'resources':[{'id':'resource-oil','name':'Lamp oil','value':12,
                      'minimum':0,'maximum':20,'unit':'flasks','visibility':'public'}],
    }
    total_actions = 0
    for session_number in range(1, 4):
        current = room(client, headers)
        update = client.put(f"/api/rooms/{current['id']}/campaign-state", headers=headers,
                            json={**revise(current), 'branch':current['branch'], 'ledger':facts})
        assert update.status_code == 200, update.text
        current = update.json()
        character_id = current['state']['characters'][0]['id']
        for action_number in range(1, 21):
            response = action(client, current, headers, character_id,
                              f'我等待并整理记录（冒险 {session_number}，行动 {action_number}）')
            assert response.status_code == 200, response.text
            current = response.json()
            total_actions += 1
            state = current['state']
            assert state['turn'] == action_number
            assert state['campaign_state']['quests'][0]['summary'] == facts['quests'][0]['summary']
            assert state['campaign_state']['npcs'][0]['relationship'] == 3
            assert state['campaign_state']['npcs'][0]['status'] == 'ally'
            assert state['campaign_state']['resources'][0]['value'] == 12
    assert total_actions == 60
