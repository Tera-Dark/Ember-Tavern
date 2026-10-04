"""Creator contracts, room import transactions and privacy regression tests."""
from copy import deepcopy
import json
from pathlib import Path

import jsonschema
import pytest

from server.config import settings
from server.content.imports import ContentError, normalize
from server.contracts.catalog import schema_for
from server.db import connection, dump
from server.retrieval import encoded_chars, model_context, select_lore
from server.state import load_state, migrate_state
from test_game import account, act, key, read, revise, room, roll
from test_plugins import toggle

ROOT = Path(__file__).resolve().parent.parent


def template(kind):
    return json.loads((ROOT / 'templates' / kind / f'{kind}.json').read_text(encoding='utf-8'))


def imported(client, r, headers, document=None, *, kind='worldbook', mode='merge', request_key=None):
    return client.post(f"/api/rooms/{r['id']}/content/import", headers=headers, json={
        **revise(r), 'request_key': request_key or key(), 'kind': kind,
        'document': document if document is not None else template(kind), 'mode': mode})


def current_state(r):
    with connection() as con:
        return load_state(con.execute('SELECT state_json FROM rooms WHERE id=?', (r['id'],)).fetchone()[0])


@pytest.mark.parametrize('kind', ['worldbook', 'character', 'theme'])
def test_templates_match_generated_schema_and_runtime(client, kind):
    schema = schema_for(kind)
    jsonschema.Draft202012Validator.check_schema(schema)
    document = template(kind)
    jsonschema.validate(document, schema)
    parsed = normalize(kind, document)
    jsonschema.validate(parsed['document'], schema)
    assert client.get('/api/contracts/' + kind).json() == schema
    assert client.get('/api/creators/templates/' + kind).json() == document
    assert json.loads((ROOT / 'registry' / f'{kind}.schema.json').read_text(encoding='utf-8')) == schema
    assert parsed['warnings'] # The starter deliberately leaves licensing for its author.


def test_native_preview_has_no_state_or_model_side_effects(client, monkeypatch):
    async def forbidden(*args):
        raise AssertionError('Preview must not invoke a model')
    monkeypatch.setattr('server.app.run_gm', forbidden)
    _, h, _ = account(client)
    r = room(client, h)
    response = client.post(f"/api/rooms/{r['id']}/content/preview", headers=h,
                           json={'kind': 'worldbook', 'document': template('worldbook'), 'mode': 'merge'})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview['revision'] == r['revision'] and preview['branch'] == r['branch']
    assert preview['summary']['entries'] == 3 and preview['summary']['gm_only'] == 1
    assert preview['summary']['rules'] == 1 and preview['effects']['keeps_world_settings']
    assert read(client, r, h) == r


def test_merge_keeps_world_settings_and_updates_stable_ids(client):
    _, h, _ = account(client)
    before = room(client, h)
    r = imported(client, before, h).json()
    assert r['state']['world']['title'] == before['state']['world']['title']
    assert r['state']['world']['premise'] == before['state']['world']['premise']
    assert len(r['state']['world']['lore']) == len(before['state']['world']['lore']) + 3
    book = template('worldbook')
    book['world']['lore'][1]['content'] = '新版渡船条目，不增加第二个同 ID 条目。'
    r2 = imported(client, r, h, book).json()
    assert len(r2['state']['world']['lore']) == len(r['state']['world']['lore'])
    assert next(entry for entry in r2['state']['world']['lore'] if entry['id'] == 'harbor-ferry')['content'].startswith('新版')
    assert r2['state']['_content']['sources'][-1]['metadata']['id'] == 'mist-harbor'


def test_replace_and_rollback_restore_whole_worldbook(client):
    _, h, _ = account(client)
    before = room(client, h)
    target = before['events'][-1]['id']
    book = template('worldbook')
    book['world']['title'] = '另一个世界'
    r = imported(client, before, h, book, mode='replace').json()
    assert r['state']['world']['title'] == '另一个世界'
    assert len(r['state']['world']['lore']) == 3
    restored = client.post(f"/api/rooms/{r['id']}/rollback", headers=h,
                          json={**revise(r), 'target_event_id': target}).json()
    assert restored['state']['world'] == before['state']['world']
    assert '_content' not in restored['state']


def test_import_revision_and_idempotency_prevent_duplicate_characters(client):
    _, h, _ = account(client)
    before = room(client, h)
    request_key = key()
    response = imported(client, before, h, kind='character', request_key=request_key)
    assert response.status_code == 200, response.text
    r = response.json()
    duplicate = imported(client, before, h, kind='character', request_key=request_key).json()
    assert duplicate['revision'] == r['revision'] and len(duplicate['state']['characters']) == 3
    assert imported(client, before, h, kind='character').status_code == 409
    char = r['state']['characters'][-1]
    assert char['assigned_to'] is None and char['id'] != template('character')['metadata']['id']
    assert char['gm_notes'] and char['attributes']['dexterity'] == 2


def test_content_commands_and_sensitive_exports_require_owner(client):
    _, h, _ = account(client, 'host')
    _, ph, _ = account(client, 'friend')
    r = room(client, h)
    client.post('/api/rooms/join', headers=ph, json={'code': r['code']})
    assert imported(client, r, ph).status_code == 403
    assert client.post(f"/api/rooms/{r['id']}/content/preview", headers=ph,
                       json={'kind': 'worldbook', 'document': template('worldbook')}).status_code == 403
    assert client.get(f"/api/rooms/{r['id']}/content/worldbook/export", headers=ph).status_code == 403
    cid = r['state']['characters'][0]['id']
    assert client.get(f"/api/rooms/{r['id']}/content/characters/{cid}/export", headers=ph).status_code == 403
    assert client.get(f"/api/rooms/{r['id']}/gm/context-preview", headers=ph).status_code == 403
    # A player's theme preference does not require world-editing permissions.
    assert client.post('/api/content/validate', headers=ph, json={'kind': 'theme', 'document': template('theme')}).status_code == 200


def test_worldbook_and_character_exports_roundtrip_without_account_identity(client):
    _, h, _ = account(client)
    r = room(client, h)
    r = imported(client, r, h, kind='character').json()
    world = client.get(f"/api/rooms/{r['id']}/content/worldbook/export", headers=h).json()
    assert normalize('worldbook', world)['document']['world'] == r['state']['world']
    char = r['state']['characters'][-1]
    card = client.get(f"/api/rooms/{r['id']}/content/characters/{char['id']}/export", headers=h).json()
    assert normalize('character', card)['document']['character']['gm_notes'] == char['gm_notes']
    assert 'assigned_to' not in card['character'] and 'id' not in card['character']
    assert 'owner_id' not in json.dumps(card) and 'password_hash' not in json.dumps(card)


def test_secrets_filtered_from_rest_search_websocket_events_and_plugin_context(client):
    _, h, token = account(client, 'host')
    _, ph, player_token = account(client, 'friend')
    r = room(client, h)
    client.post('/api/rooms/join', headers=ph, json={'code': r['code']})
    book = template('worldbook')
    book['world']['lore'][2].update(content='GMSECRETPAYLOAD999 仅主持知道的地窖事实。', keys=['GMSECRETPAYLOAD999'])
    r = imported(client, r, h, book).json()
    card = template('character')
    card['character']['gm_notes'] = 'PRIVATECHARACTERNOTE999'
    r = imported(client, r, h, card, kind='character').json()
    r = toggle(client, r, h, 'scene-map')
    r = act(client, r, h, '我观察 GMSECRETPAYLOAD999').json()
    assert 'context_selection' in r['events'][-1]['payload']
    assert any(entry['visibility'] == 'gm' for entry in r['events'][-1]['payload']['context_selection']['entries'])
    # Public action text may contain the query; private content and private evidence must not leak.
    player = read(client, r, ph)
    assert not any(entry.get('visibility') == 'gm' for entry in player['state']['world']['lore'])
    assert '仅主持知道的地窖事实' not in json.dumps(player, ensure_ascii=False)
    assert 'PRIVATECHARACTERNOTE999' not in json.dumps(player)
    assert '_content' not in player['state'] and 'context_ids' not in player['events'][-1]['payload']
    search = client.get(f"/api/rooms/{r['id']}/context?q=GMSECRETPAYLOAD999", headers=ph).json()
    assert all(item['source'] != 'lore' for item in search['results'])
    owner_search = client.get(f"/api/rooms/{r['id']}/context?q=GMSECRETPAYLOAD999", headers=h).json()
    assert any(item['source'] == 'lore' for item in owner_search['results'])
    public_events = client.get(f"/api/rooms/{r['id']}/events", headers=ph).json()
    assert not any('context_selection' in event['payload'] for event in public_events)
    for headers in (h, ph):
        ctx = client.get(f"/api/rooms/{r['id']}/extensions/scene-map/context", headers=headers).json()
        assert not any(entry.get('visibility') == 'gm' for entry in ctx['room']['world']['lore'])
        assert 'PRIVATECHARACTERNOTE999' not in json.dumps(ctx)
    with client.websocket_connect(f"/ws/rooms/{r['id']}") as socket:
        socket.send_json({'type': 'auth', 'token': player_token})
        data = socket.receive_json()['data']
        assert '仅主持知道的地窖事实' not in json.dumps(data, ensure_ascii=False)
        assert 'PRIVATECHARACTERNOTE999' not in json.dumps(data)


def test_context_rules_activation_budget_and_disabled_entries(client, monkeypatch):
    _, h, _ = account(client)
    r = room(client, h)
    book = template('worldbook')
    book['world']['lore'][1].update(enabled=False, content='DISABLEDLORETOKEN999')
    book['world']['lore'][2].update(content='PRIVATELORETOKEN999', keys=['地窖'])
    for index in range(16):
        book['world']['lore'].append({'id': f'long-{index}', 'title': f'常驻设定 {index}', 'content': '港口的潮汐。' * 300,
                                     'activation': 'always', 'priority': -index})
    r = imported(client, r, h, book, mode='replace').json()
    monkeypatch.setattr(settings, 'context_max_chars', 8000)
    monkeypatch.setattr(settings, 'lore_context_chars', 1600)
    state = current_state(r)
    state['continuation'] = {'phase': 'action', 'text': '我调查地窖', 'character_id': state['characters'][0]['id']}
    context = model_context(r['id'], state, '我调查地窖')
    selection = context.pop('_selection')
    assert encoded_chars(context) <= 8000 and selection['used_chars'] <= 1600
    assert context['retrieved'][0]['id'] == 'table-boundaries'
    assert selection['omitted_ids'] and any(entry['truncated'] for entry in selection['entries'])
    assert 'DISABLEDLORETOKEN999' not in json.dumps(context)
    preview = client.get(f"/api/rooms/{r['id']}/gm/context-preview?q=不匹配的行动", headers=h)
    assert preview.status_code == 200 and preview.json()['context']['retrieved'][0]['kind'] == 'rule'
    a = select_lore(state, '地窖', 6000)
    b = select_lore(state, '地窖', 6000)
    assert a == b # Stable ordering; no regex, randomness or probabilistic injection.


def test_gm_context_excludes_vendor_extensions_and_plugin_state(client):
    _, h, _ = account(client)
    r = room(client, h)
    state = current_state(r)
    state['world']['extensions'] = {'example.extra/v1': {'text': 'VENDOREXTENSION999'}}
    state['_plugins']['ai-host']['data']['huge'] = 'PLUGINCONTEXT999' * 1000
    state['continuation'] = {'phase': 'action', 'text': '我等待', 'character_id': state['characters'][0]['id']}
    context = model_context(r['id'], state, '我等待')
    assert 'VENDOREXTENSION999' not in json.dumps(context)
    assert 'PLUGINCONTEXT999' not in json.dumps(context)


def test_compatibility_conversion_is_explicit_and_keeps_disabled_items():
    document = {'name': '社区世界书', 'entries': {
        '4': {'uid': 4, 'comment': '灯塔', 'content': '一座灯塔', 'key': ['灯塔'], 'constant': True, 'position': 0},
        '5': {'uid': 5, 'comment': '正则', 'content': '不能执行的正则', 'key': ['(a+)+'], 'useRegex': True},
        '6': {'uid': 6, 'comment': '停用', 'content': '暂不读取', 'key': ['停用'], 'disable': True},
    }}
    parsed = normalize('worldbook', document)
    entries = parsed['document']['world']['lore']
    assert parsed['source_format'] == 'sillytavern-entries'
    assert entries[0]['activation'] == 'always' and entries[0]['id'] == 'st-4'
    assert not entries[1]['enabled'] and not entries[2]['enabled']
    assert all(entry['visibility'] == 'public' for entry in entries)
    assert any('正则' in warning for warning in parsed['warnings'])
    assert any('注入位置' in warning for warning in parsed['warnings'])


def test_legacy_missing_ids_are_deterministic():
    document = {'title': '旧版世界书', 'premise': '旅人相遇。', 'lore': [{'title': '酒馆', 'content': '一盏灯。'}]}
    first = normalize('worldbook', document)
    second = normalize('worldbook', document)
    assert first['document'] == second['document']
    assert first['document']['world']['lore'][0]['id'].startswith('entry-')


@pytest.mark.parametrize('mutate', [
    lambda doc: doc.update(format='ember.worldbook/v99'),
    lambda doc: doc['world'].update(rule_system='dnd-5e/v1'),
    lambda doc: doc['world'].update(python='print("execute")'),
    lambda doc: doc['world']['lore'].append(deepcopy(doc['world']['lore'][0])),
    lambda doc: doc['world']['lore'][0].update(visibility='admin'),
    lambda doc: doc['world']['lore'][0].update(content='x' * 3001),
    lambda doc: doc['world']['lore'][0].update(enabled='false'),
])
def test_bad_worldbook_contracts_rejected(mutate):
    document = template('worldbook')
    mutate(document)
    with pytest.raises(ContentError):
        normalize('worldbook', document)


@pytest.mark.parametrize('mutate', [
    lambda doc: doc['character'].update(assigned_to='stolen-user'),
    lambda doc: doc['character'].update(hp=100, max_hp=12),
    lambda doc: doc['character']['attributes'].update(strength=999),
])
def test_character_cards_cannot_import_permissions_or_invalid_stats(mutate):
    document = template('character')
    mutate(document)
    with pytest.raises(ContentError):
        normalize('character', document)


@pytest.mark.parametrize('mutate', [
    lambda doc: doc['modes']['dark'].update({'--bg': 'url(https://example.com/tracker)'}),
    lambda doc: doc['modes']['dark'].update({'--evil': '#ffffff'}),
    lambda doc: doc.update(script='alert(1)'),
    lambda doc: doc.update(modes={'dark': None, 'light': None}),
])
def test_theme_cannot_inject_css_network_or_scripts(mutate):
    document = template('theme')
    mutate(document)
    with pytest.raises(ContentError):
        normalize('theme', document)


def test_oversized_and_deep_documents_are_rejected():
    with pytest.raises(ContentError, match='512'):
        normalize('worldbook', {'untrusted': 'x' * (512 * 1024 + 1)})
    document = {}
    current = document
    for _ in range(20):
        current['nested'] = {}
        current = current['nested']
    with pytest.raises(ContentError, match='嵌套'):
        normalize('worldbook', document)


def test_old_core_state_and_snapshots_migrate_without_inferring_secrets(client):
    _, h, _ = account(client)
    r = room(client, h)
    state = current_state(r)
    state.pop('schema_version')
    for key in ('_campaign_state', '_action_mode', '_action_round', '_memory_summary'):
        state.pop(key, None)
    state['world'].pop('rule_system')
    for entry in state['world']['lore']:
        for field in ('kind', 'visibility', 'activation', 'keys', 'enabled', 'priority'):
            entry.pop(field)
    for char in state['characters']:
        char.pop('gm_notes')
    with connection() as con:
        con.execute('UPDATE rooms SET state_json=? WHERE id=?', (dump(state), r['id']))
    migrated = read(client, r, h)['state']
    assert migrated['schema_version'] == 4 and migrated['world']['rule_system'] == 'ember-light/v1'
    assert migrated['action_mode'] == 'free' and migrated['action_round'] is None
    assert migrated['campaign_state'] == {'format':'ember.campaign-state/v1','quests':[],'npcs':[],'resources':[]}
    assert all(entry['visibility'] == 'public' for entry in migrated['world']['lore'])
    with connection() as con:
        raw = json.loads(con.execute('SELECT state_json FROM rooms WHERE id=?', (r['id'],)).fetchone()[0])
    normalized = migrate_state(raw)
    assert normalized['schema_version'] == 4
    assert normalized['_campaign_state']['format'] == 'ember.campaign-state/v1'
    assert normalized['_action_mode'] == 'free' and normalized['_action_round'] is None
    assert normalized['_memory_summary'] is None
    assert migrate_state(normalized) == normalized
    with pytest.raises(ValueError, match='版本'):
        migrate_state(dict(normalized, schema_version=99))


def test_all_gm_providers_validated_by_authoritative_rule_adapter(client, monkeypatch):
    # A third-party GM cannot bypass validation by skipping the built-in AI adapter.
    from server.plugin_runtime.manager import manager
    _, h, _ = account(client)
    r = room(client, h)
    async def malicious(*args):
        return {'narration': '非法主持输出', 'hp_delta': -999}, {'mode': 'demo'}
    monkeypatch.setattr(manager.items['ai-host']['backend'], 'gm', malicious)
    after = act(client, r, h).json()
    assert after['state']['gm_error'] and after['state']['awaiting_gm']
    assert after['state']['characters'] == r['state']['characters']
    assert not any(event['type'] == 'gm' for event in after['events'])


def test_api_body_limits_bound_streamed_inputs_before_parsing(client):
    _, h, _ = account(client)
    response = client.post('/api/content/validate', headers=h,
                           content=b'x' * (2 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.headers['cache-control'] == 'no-store'
    response = client.post('/api/content/validate', headers=h,
                           content=(b'x' * 65536 for _ in range(34)))
    assert response.status_code == 413


def test_invalid_trace_cannot_publish_arbitrary_private_prompt_dumps(client, monkeypatch):
    from server.plugin_runtime.manager import manager
    from server.schemas import Decision
    _, h, _ = account(client)
    r = room(client, h)
    async def invalid(*args):
        return Decision(narration='不应被部分应用的回复'), {'mode': 'demo', 'raw_prompt': 'PRIVATEPROMPT999'}
    monkeypatch.setattr(manager.items['ai-host']['backend'], 'gm', invalid)
    after = act(client, r, h).json()
    assert after['state']['scene'] == r['state']['scene']
    assert 'PRIVATEPROMPT999' not in json.dumps(after)
    assert after['state']['awaiting_gm']


def test_deep_raw_json_body_is_rejected_without_internal_error(client):
    content='{"kind":"worldbook","document":'+'{"nested":'*2000+'{}'+'}'*2000+'}'
    _, headers, _ = account(client)
    # CPython 3.13 can parse deeper JSON; our bounded validator still rejects it.
    assert client.post('/api/content/validate',content=content,headers={**headers,'content-type':'application/json'}).status_code in (400,422)


def test_world_data_total_limit_and_oversized_merge_never_write(client):
    from server.contracts.content import WorldData
    from pydantic import ValidationError
    world = template('worldbook')['world']
    world['lore'] = [{'id': f'large-{n}', 'title': '大条目', 'content': '文' * 2900} for n in range(52)]
    with pytest.raises(ValidationError, match='384 KiB'):
        WorldData.model_validate(world)
    # Each half is legal; a merge must revalidate the combined data, not just count IDs.
    world['lore'] = world['lore'][:26]
    _, h, _ = account(client)
    before = room(client, h)
    book = template('worldbook')
    book['world'] = world
    r = imported(client, before, h, book, mode='replace').json()
    book['world']['lore'] = [dict(entry, id='second-'+entry['id']) for entry in world['lore']]
    preview = client.post(f"/api/rooms/{r['id']}/content/preview", headers=h,
                          json={'kind':'worldbook','mode':'merge','document':book})
    assert preview.status_code == 422 and '384 KiB' in preview.text
    assert imported(client, r, h, book).status_code == 422
    assert read(client, r, h)['revision'] == r['revision']
    export = client.get(f"/api/rooms/{r['id']}/content/worldbook/export", headers=h)
    assert len(export.content) < 512 * 1024
    assert normalize('worldbook', export.json())['document']['world'] == r['state']['world']


def test_creator_catalog_advertises_capability_bound_core_resources(client):
    catalog = client.get('/api/creators').json()
    from server.version import HOST_VERSION
    assert catalog['host_version'] == HOST_VERSION
    assert {r['name']:r['capability'] for r in catalog['core_resources']}['core.dice/v1'] == 'dice:roll'


def test_extensions_depth_is_bounded_even_for_direct_dossier_updates(client):
    _, h, _ = account(client)
    r = room(client, h)
    nested = {'value':1}
    for _ in range(20):
        nested = {'nested':nested}
    world = dict(r['state']['world'], extensions={'example.data/v1':nested})
    response = client.put(f"/api/rooms/{r['id']}/world",headers=h,json={**revise(r),**world})
    assert response.status_code == 422 and '12' in response.text
    char = {k:v for k,v in r['state']['characters'][0].items() if k not in ('id','assigned_to')}
    char['extensions'] = {'example.data/v1':nested}
    response = client.put(f"/api/rooms/{r['id']}/characters/{r['state']['characters'][0]['id']}",
                          headers=h,json={**revise(r),**char})
    assert response.status_code == 422 and read(client,r,h)['revision'] == r['revision']


def test_id_generation_revalidates_world_byte_limit(client):
    from server.contracts.content import WorldData, MAX_WORLD_BYTES
    world = template('worldbook')['world']
    world['lore'] = [{'id':'','title':'x','content':'a'*2800} for _ in range(128)]
    value = WorldData.model_validate(world).model_dump(mode='json')
    remaining = MAX_WORLD_BYTES - 30 - len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
    assert remaining > 0
    for entry in value['lore']:
        delta = min(remaining, 3000-len(entry['content']))
        entry['content'] += 'a'*delta
        remaining -= delta
    assert remaining == 0
    WorldData.model_validate(value)  # Legal until IDs are added.
    book = template('worldbook')
    book['world'] = value
    with pytest.raises(ContentError, match='补全条目 ID'):
        normalize('worldbook',book)
    _, h, _ = account(client)
    r = room(client,h)
    response = client.put(f"/api/rooms/{r['id']}/world",headers=h,json={**revise(r),**value})
    assert response.status_code == 422 and '384 KiB' in response.text
    assert read(client,r,h)['revision'] == r['revision']
