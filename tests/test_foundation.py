"""Room lifecycle, shared plugin contracts, creator CLI and SDK foundation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import threading
import zipfile

from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect
import pytest

from scripts.creator import scaffold, schemas, validate
from scripts.plugins import install, package
from server.config import settings
from server.contracts.catalog import schema_for
from server.contracts.plugin import validate_manifest
from server.db import connection, dump
from server.network import websocket_origin_allowed
from server.plugin_runtime.manager import manager
from server.plugin_runtime.sdk import Result
from test_game import account, key, read, revise, room
from test_plugins import action, install_notes, toggle


def access(client, r, h, **values):
    response = client.post(f"/api/rooms/{r['id']}/invitation", headers=h,
                           json={**revise(r), 'accepting_players': True, **values})
    assert response.status_code == 200, response.text
    return response.json()


def test_invite_rotation_pause_and_rollback_are_operational(client):
    owner, h, _ = account(client, 'host')
    _, ph, _ = account(client, 'friend')
    _, other_h, _ = account(client, 'otherfriend')
    before = room(client, h)
    r = client.post('/api/rooms/join', headers=ph, json={'code': before['code']}).json()
    target = r['events'][0]['id']
    assert client.post(f"/api/rooms/{r['id']}/invitation", headers=ph,
                       json={**revise(r), 'accepting_players': False}).status_code == 403
    r = access(client, r, h, rotate_code=True, accepting_players=False)
    assert r['code'] != before['code'] and not r['access']['accepting_players']
    assert client.post('/api/rooms/join', headers=other_h, json={'code': before['code']}).status_code == 404
    assert client.post('/api/rooms/join', headers=other_h, json={'code': r['code']}).status_code == 403
    assert client.post('/api/rooms/join', headers=ph, json={'code': r['code']}).status_code == 200
    restored = client.post(f"/api/rooms/{r['id']}/rollback", headers=h,
                          json={**revise(r), 'target_event_id': target}).json()
    assert restored['code'] == r['code'] and restored['access'] == r['access']
    assert len(restored['members']) == 2
    assert r['code'] not in json.dumps(r['events'])


def test_removed_member_disconnected_and_cannot_read_or_act(client):
    _, h, _ = account(client, 'host')
    player, ph, pt = account(client, 'friend')
    r = room(client, h)
    r = client.post('/api/rooms/join', headers=ph, json={'code': r['code']}).json()
    cid = r['state']['characters'][1]['id']
    r = client.post(f"/api/rooms/{r['id']}/characters/{cid}/assign", headers=h,
                    json={**revise(r), 'user_id': player['id']}).json()
    with client.websocket_connect(f"/ws/rooms/{r['id']}") as socket:
        socket.send_json({'type': 'auth', 'token': pt})
        assert socket.receive_json()['type'] == 'state'
        response = client.post(f"/api/rooms/{r['id']}/members/{player['id']}/remove", headers=h, json=revise(r))
        assert response.status_code == 200, response.text
        after = response.json()
        assert after['state']['characters'][1]['assigned_to'] is None
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
        assert exc.value.code == 4403
    assert client.get('/api/rooms/' + r['id'], headers=ph).status_code == 403
    assert client.post('/api/rooms/' + r['id'] + '/dice', headers=ph,
                       json={**revise(after), 'expression': '1d20'}).status_code == 403


def test_leave_clears_assignment_is_idempotent_and_owner_cannot_leave(client):
    _, h, _ = account(client, 'host')
    player, ph, _ = account(client, 'friend')
    r = room(client, h)
    assert client.post(f"/api/rooms/{r['id']}/leave", headers=h, json=revise(r)).status_code == 422
    client.post('/api/rooms/join', headers=ph, json={'code': r['code']})
    cid = r['state']['characters'][1]['id']
    r = client.post(f"/api/rooms/{r['id']}/characters/{cid}/assign", headers=h,
                    json={**revise(r), 'user_id': player['id']}).json()
    body = revise(r)
    path = f"/api/rooms/{r['id']}/leave"
    assert client.post(path, headers=ph, json=body).status_code == 200
    assert client.post(path, headers=ph, json=body).json()['left']
    after = read(client, r, h)
    assert len(after['members']) == 1 and after['state']['characters'][1]['assigned_to'] is None


def test_logout_revokes_open_websocket_immediately(client):
    _, h, token = account(client)
    r = room(client, h)
    with client.websocket_connect(f"/ws/rooms/{r['id']}") as socket:
        socket.send_json({'type': 'auth', 'token': token})
        socket.receive_json()
        assert client.post('/api/auth/logout', headers=h).status_code == 200
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
        assert exc.value.code == 4401


def test_origin_validation_does_not_trust_unrelated_preview_hosts(monkeypatch):
    monkeypatch.setattr(settings, 'allowed_origins', '')
    assert websocket_origin_allowed({'host': '8000-this.e2b.app', 'origin': 'https://8000-this.e2b.app'})
    assert not websocket_origin_allowed({'host': '8000-this.e2b.app', 'origin': 'https://8000-other.e2b.app'})
    assert not websocket_origin_allowed({'host': 'localhost:8000', 'origin': 'null'})
    assert not websocket_origin_allowed({'host': 'localhost:8000', 'origin': 'http://localhost:8000/evil'})
    assert websocket_origin_allowed({'host': 'internal:8000', 'x-forwarded-host': 'tavern.example', 'origin': 'https://tavern.example'})
    monkeypatch.setattr(settings, 'allowed_origins', 'https://my-tavern.example')
    assert websocket_origin_allowed({'host': 'internal:8000', 'origin': 'https://my-tavern.example'})


def test_creator_scaffolds_all_template_types_and_never_overwrites(tmp_path):
    for index, kind in enumerate(('worldbook', 'character', 'theme', 'plugin-ui', 'plugin-backend', 'plugin-dice')):
        destination = tmp_path / kind
        result = scaffold(kind, destination, f'example-{index}', '我的创作')
        assert result['id'] == f'example-{index}'
        path = destination if kind.startswith('plugin-') else destination / f'{kind}.json'
        assert validate(path)['valid']
        with pytest.raises(ValueError, match='覆盖'):
            scaffold(kind, destination, 'example-again')
    assert schemas(check=True)['schema_drift'] == []
    with pytest.raises(ValueError):
        scaffold('worldbook', tmp_path / 'invalid', '../escape')
    assert not (tmp_path / 'invalid').exists()


def test_single_plugin_schema_used_by_tools_and_runtime(client, tmp_path):
    import jsonschema
    manifest = json.loads(Path('templates/dice-tray/plugin.json').read_text())
    jsonschema.validate(manifest, schema_for('plugin'))
    assert client.get('/api/contracts/plugin').json() == schema_for('plugin')
    assert json.loads(Path('registry/plugin.schema.json').read_text()) == schema_for('plugin')
    invalid = dict(manifest, default_enabled='yes')
    with pytest.raises(ValueError):
        validate_manifest(invalid)
    invalid = dict(manifest, provides=['core.world/v1'], backend='backend.py')
    with pytest.raises(ValueError, match='保留'):
        validate_manifest(invalid)
    folder = tmp_path / 'invalid-plugin'
    folder.mkdir()
    (folder / 'plugin.json').write_text(json.dumps(invalid))
    (folder / 'backend.py').write_text('raise AssertionError("must not execute")')
    (folder / 'ui.js').write_text('void 0;')
    with pytest.raises(ValueError):
        package(folder, tmp_path / 'invalid.zip')


def test_dice_template_uses_core_resources_and_authoritative_command(client, tmp_path, monkeypatch):
    destination = tmp_path / 'dice-tray.zip'
    package(Path('templates/dice-tray'), destination)
    install(str(destination), grant_capabilities=True)
    _, h, _ = account(client)
    r = room(client, h)
    r = toggle(client, r, h, 'dice-tray')
    ctx = client.get(f"/api/rooms/{r['id']}/extensions/dice-tray/context", headers=h).json()
    assert ctx['resources']['core.dice/v1']['owner'] == '@core'
    assert ctx['resources']['core.rules/v1']['data']['id'] == 'ember-light/v1'
    monkeypatch.setattr('server.domain.secrets.randbelow', lambda _: 2)
    response = client.post(f"/api/rooms/{r['id']}/dice", headers=h,
                           json={**revise(r), 'expression': '2d6+1', 'source_plugin': 'dice-tray'})
    assert response.status_code == 200, response.text
    after = response.json()
    assert after['events'][-1]['payload']['rolls'] == [3, 3]
    assert after['events'][-1]['payload']['total'] == 7
    assert after['events'][-1]['payload']['source_plugin'] == 'dice-tray'
    assert after['state']['characters'] == r['state']['characters']
    assert 'coreDice' in client.get('/plugin-frame/dice-tray').text
    r = toggle(client, after, h, 'scene-map')
    assert client.post(f"/api/rooms/{r['id']}/dice", headers=h,
                       json={**revise(r), 'expression': '1d20', 'source_plugin': 'scene-map'}).status_code == 403


def test_private_plugin_projection_redacts_and_fails_closed(client, tmp_path, monkeypatch):
    install_notes(tmp_path)
    _, h, _ = account(client, 'host')
    _, ph, _ = account(client, 'friend')
    r = room(client, h)
    client.post('/api/rooms/join', headers=ph, json={'code': r['code']})
    r = toggle(client, r, h, 'scene-notes')
    with connection() as con:
        state = json.loads(con.execute('SELECT state_json FROM rooms WHERE id=?', (r['id'],)).fetchone()[0])
        state['_plugins']['scene-notes']['data']['private'] = 'PRIVATENAMESPACE999'
        con.execute('UPDATE rooms SET state_json=? WHERE id=?', (dump(state), r['id']))
    extension = manager.items['scene-notes']['backend']
    monkeypatch.setattr(extension, 'public_data', lambda ctx, data: data if ctx.is_owner else {'notes': data['notes']})
    assert 'PRIVATENAMESPACE999' not in json.dumps(read(client, r, ph))
    assert 'PRIVATENAMESPACE999' in json.dumps(read(client, r, h))
    ctx = client.get(f"/api/rooms/{r['id']}/extensions/scene-notes/context", headers=ph).json()
    assert 'private' not in ctx['own_state']
    def failed(*args):
        raise RuntimeError('projection failed')
    monkeypatch.setattr(extension, 'public_data', failed)
    assert read(client, r, ph)['state']['_plugins']['scene-notes']['data'] == {}


def test_transitive_dependency_health_checked_and_community_never_auto_enabled(client, tmp_path):
    for pid, requires in (('base-addon', []), ('middle-addon', ['base-addon']), ('top-addon', ['middle-addon'])):
        folder = settings.data_dir / 'plugins' / pid
        folder.mkdir(parents=True)
        (folder / 'plugin.json').write_text(json.dumps({'id': pid, 'name': pid, 'version': '1.0.0', 'api_version': 1,
            'description': 'read-only test', 'requires': requires, 'default_enabled': True}))
    manager.refresh()
    _, h, _ = account(client)
    r = room(client, h)
    assert not any(p['enabled'] for p in r['plugins'] if p['id'].endswith('addon'))
    r = toggle(client, r, h, 'top-addon')
    assert all(p['enabled'] for p in r['plugins'] if p['id'].endswith('addon'))
    manager.items['base-addon']['blocked'] = 'review revoked'
    assert not manager.enabled(r['id'], 'top-addon')


def test_backend_core_resource_reads_participate_in_optimistic_conflicts(client, tmp_path, monkeypatch):
    install_notes(tmp_path)
    _, h, _ = account(client)
    r = room(client, h)
    r = toggle(client, r, h, 'scene-notes')
    extension = manager.items['scene-notes']['backend']
    monkeypatch.setitem(manager.items['scene-notes']['manifest'], 'uses', ['core.world/v1'])
    started = threading.Event()
    async def slow(ctx, name, payload, data):
        ctx.resource('core.world/v1')
        started.set()
        await asyncio.sleep(.3)
        return Result(data={'notes': ['cannot overwrite newer core']})
    monkeypatch.setattr(extension, 'action', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(action, client, r, h, 'scene-notes', 'append', {})
        assert started.wait(3)
        world = dict(r['state']['world'], title='Changed while reading')
        response = client.put(f"/api/rooms/{r['id']}/world", headers=h, json={**revise(r), **world})
        assert response.status_code == 200, response.text
        result = future.result()
        assert result.status_code == 409, result.text
    assert read(client, r, h)['state']['_plugins']['scene-notes']['data']['notes'] == []


def test_concurrent_joins_cannot_exceed_twelve_members(client):
    _, h, _ = account(client, 'host')
    r = room(client, h)
    # Create users through the same service without repeatedly exercising the IP signup limiter.
    from server.auth import create_user, issue_session
    headers = []
    for index in range(12):
        user = create_user(f'friend{index}', f'同伴 {index}', 'testpassword123')
        headers.append({'Authorization': 'Bearer ' + issue_session(user)})
    for header in headers[:10]:
        assert client.post('/api/rooms/join', headers=header, json={'code': r['code']}).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda header: client.post('/api/rooms/join', headers=header,
                               json={'code': r['code']}), headers[10:]))
    assert sorted(response.status_code for response in results) == [200, 422]
    assert len(read(client, r, h)['members']) == 12


def test_private_read_requires_explicit_grant_and_is_owner_gated(client, tmp_path):
    folder = tmp_path / 'private-inspector'
    folder.mkdir()
    manifest = {'id':'private-inspector','name':'秘密检查器','version':'1.0.0','api_version':1,
                'description':'Test explicit private-read consent','frontend':'ui.js',
                'capabilities':['read:room','read:gm'],'uses':['core.world/v1']}
    (folder / 'plugin.json').write_text(json.dumps(manifest))
    (folder / 'ui.js').write_text('void 0;')
    bundle = tmp_path / 'private.zip'
    package(folder, bundle)
    with pytest.raises(ValueError, match='grant-capabilities'):
        install(str(bundle))
    install(str(bundle), grant_capabilities=True)
    _, h, _ = account(client, 'host')
    _, ph, _ = account(client, 'friend')
    r = room(client, h)
    client.post('/api/rooms/join', headers=ph, json={'code':r['code']})
    world = r['state']['world']
    world['lore'][0].update(visibility='gm',content='APPROVEDPRIVATEENTRY777')
    response = client.put(f"/api/rooms/{r['id']}/world", headers=h, json={**revise(r),**world})
    assert response.status_code == 200, response.text
    r = toggle(client, response.json(), h, 'private-inspector')
    url = f"/api/rooms/{r['id']}/extensions/private-inspector/context"
    host_context = client.get(url,headers=h).json()
    assert 'APPROVEDPRIVATEENTRY777' in json.dumps(host_context['room'])
    assert 'APPROVEDPRIVATEENTRY777' not in json.dumps(host_context['resources']['core.world/v1'])
    assert 'APPROVEDPRIVATEENTRY777' not in json.dumps(client.get(url,headers=ph).json())
    (settings.data_dir / 'plugins/private-inspector/ui.js').write_text('void 1;')
    manager.refresh()
    assert manager.items['private-inspector']['blocked']
    assert client.get(url,headers=h).status_code == 403


def test_future_host_requirement_blocks_loading_even_trusted_backend(client, tmp_path):
    folder = tmp_path / 'future-addon'
    folder.mkdir()
    (folder / 'plugin.json').write_text(json.dumps({'id':'future-addon','name':'未来插件','version':'1.0.0',
        'api_version':1,'description':'Do not execute incompatible code','backend':'backend.py',
        'minimum_host':'99.0.0','authors':['Example author'],'license':'LicenseRef-Test',
        'homepage':'https://example.test/future'}))
    (folder / 'backend.py').write_text('raise AssertionError("incompatible code must not execute")')
    bundle = tmp_path / 'future.zip'
    package(folder,bundle)
    install(str(bundle),trust_backend=True)
    manager.refresh()
    item = manager.items['future-addon']
    assert item['backend'] is None and '99.0.0' in item['blocked']
    assert item['manifest']['authors'] == ['Example author']
    assert item['manifest']['license'] == 'LicenseRef-Test'
    with pytest.raises(ValueError):
        validate_manifest(dict(item['manifest'], homepage='javascript:alert(1)'))


def test_creator_guide_and_local_catalog_match_actual_templates(client):
    guide = client.get('/api/creators/guide')
    assert guide.status_code == 200
    assert 'ember.worldbook/v1' in guide.json()['text'] and '正在整理' not in guide.json()['text']
    catalog = json.loads(Path('registry/index.json').read_text(encoding='utf-8'))
    assert set(catalog['scaffold_kinds']) == {'worldbook','character','theme','plugin-ui','plugin-backend','plugin-dice'}
    for item in catalog['content_templates']:
        document = json.loads(Path(item['template_path']).read_text(encoding='utf-8'))
        assert document['format'] == item['format']
        assert json.loads(Path(item['schema_path']).read_text()) == schema_for(item['kind'])
    for item in catalog['plugins']:
        assert (Path(item['template_path']) / 'plugin.json').is_file()
        if item.get('package'):
            assert hashlib.sha256((Path('plugin-packages') / item['package']).read_bytes()).hexdigest() == item['sha256']
        else:
            assert item['download_url'] is None and item['sha256'] is None


def test_creator_cli_reports_nonobject_and_recursive_json_cleanly(tmp_path):
    import subprocess, sys
    for name, content in [('array.json','[]'), ('deep.json','{"value":'*2000+'1'+'}'*2000)]:
        path = tmp_path / name
        path.write_text(content)
        result = subprocess.run([sys.executable,'scripts/creator.py','validate',str(path)],capture_output=True,text=True)
        assert result.returncode == 1
        assert json.loads(result.stderr)['valid'] is False
        assert 'Traceback' not in result.stderr


def test_application_session_header_survives_proxy_and_logout_revokes_ws(client):
    owner, h, token = account(client)
    app_header = {'X-Ember-Session':token}
    assert client.get('/api/auth/me',headers=app_header).json()['id'] == owner['id']
    assert client.get('/api/auth/me',headers={**app_header,'Authorization':'Bearer proxy-owned-value'}).status_code == 200
    assert client.get('/api/auth/me',headers={**h,'X-Ember-Session':'invalid-value'}).status_code == 401
    r = room(client,app_header)
    with client.websocket_connect(f"/ws/rooms/{r['id']}") as socket:
        socket.send_json({'type':'auth','token':token})
        socket.receive_json()
        assert client.post('/api/auth/logout',headers=app_header).status_code == 200
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
        assert exc.value.code == 4401
    assert client.get('/api/auth/me',headers=h).status_code == 401


def test_plugin_download_checks_https_at_every_redirect_hop():
    from scripts.plugins import HTTPSOnlyRedirect
    from urllib.request import Request
    policy = HTTPSOnlyRedirect()
    request = Request('https://example.test/bundle.zip')
    redirected = policy.redirect_request(request,None,302,'redirect',{},'https://assets.example.test/bundle.zip')
    assert redirected.full_url.startswith('https://')
    with pytest.raises(ValueError,match='HTTPS'):
        policy.redirect_request(request,None,302,'redirect',{},'http://example.test/temporary-hop')
