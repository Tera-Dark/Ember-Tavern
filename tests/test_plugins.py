import asyncio,hashlib,json,zipfile,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
import pytest
from fastapi import HTTPException
from server.config import settings
from server.db import connection
from server.plugin_runtime.manager import manager,package_hash
from server.plugin_runtime.routes import plugin_locks
from server.schemas import Decision
from test_game import account,room,revise,key,read,act


def toggle(client,r,h,pid,enabled=True):
    response=client.post(f"/api/rooms/{r['id']}/extensions/{pid}/toggle",headers=h,json={**revise(r),'enabled':enabled})
    assert response.status_code==200,response.text
    return response.json()

def action(client,r,h,pid,name,payload,via=None,request_key=None):
    return client.post(f"/api/rooms/{r['id']}/extensions/{pid}/actions/{name}",headers=h,json={
        'expected_plugin_revision':r['state'].get('_plugins',{}).get(pid,{}).get('revision',0),
        'expected_branch':r['branch'],'request_key':request_key or key(),'payload':payload,'via':via})

def setup_map(client,h):
    r=room(client,h);r=toggle(client,r,h,'map-generator');r=toggle(client,r,h,'map-tokens')
    response=action(client,r,h,'map-generator','generate',{'seed':42,'theme':'harbor'})
    assert response.status_code==200,response.text
    return response.json()['room']


def test_plugin_default_and_dependency_switches(client):
    _,h,_=account(client);r=room(client,h)
    assert [p['id'] for p in r['plugins'] if p['enabled']]==['ai-host']
    r=toggle(client,r,h,'voice-tts')
    assert all(next(p for p in r['plugins'] if p['id']==pid)['enabled'] for pid in ['narrator-script','voice-tts'])
    old=r['state']['_plugins']['narrator-script']
    r=toggle(client,r,h,'narrator-script',False)
    assert not any(p['enabled'] for p in r['plugins'] if p['id'] in ['voice-tts','narrator-script'])
    assert r['state']['_plugins']['narrator-script']==old
    r=toggle(client,r,h,'narrator-script')
    assert r['state']['_plugins']['narrator-script']==old


def test_map_generation_namespaced_and_disable_cascade(client):
    _,h,_=account(client);r=setup_map(client,h)
    layout=r['state']['_plugins']['scene-map']['data']['map']
    assert len(layout['grid'])==16 and len(layout['grid'][0])==24
    assert layout['source']=='procedural' and r['state']['turn']==0
    positions=r['state']['_plugins']['map-tokens']['data']['positions']
    assert len(positions)==len(r['state']['characters'])
    r=toggle(client,r,h,'scene-map',False)
    assert not any(p['enabled'] for p in r['plugins'] if p['id'] in ['scene-map','map-generator','map-tokens'])
    assert r['state']['_plugins']['scene-map']['data']['map']==layout
    assert r['state']['_plugins']['map-tokens']['data']['positions']==positions
    assert action(client,r,h,'map-tokens','move',{}).status_code==403


def test_token_permissions_bounds_obstacles_and_cross_capability(client):
    owner,h,_=account(client,'host');friend,fh,_=account(client,'friend');r=setup_map(client,h)
    client.post('/api/rooms/join',headers=fh,json={'code':r['code']})
    layout=r['state']['_plugins']['scene-map']['data']['map'];char=r['state']['characters'][0]['id']
    payload={'character_id':char,'map_id':layout['id'],'x':5,'y':8}
    assert action(client,r,fh,'map-tokens','move',payload).status_code==403
    assert action(client,r,h,'map-tokens','move',dict(payload,x=100)).status_code==422
    assert action(client,r,h,'map-tokens','move',dict(payload,x=0,y=0)).status_code==422
    assert action(client,r,h,'map-tokens','move',payload,via='map-generator').status_code==403
    result=action(client,r,h,'map-tokens','move',payload,via='scene-map')
    assert result.status_code==200,result.text
    r=result.json()['room'];assert r['state']['_plugins']['map-tokens']['data']['positions'][char]=={'x':5,'y':8}


def test_map_and_script_rollback_and_operational_flags(client):
    _,h,_=account(client);r=setup_map(client,h);r=toggle(client,r,h,'narrator-script')
    target=r['events'][-1]['id'];before=json.loads(json.dumps(r['state']['_plugins']))
    layout=before['scene-map']['data']['map'];char=r['state']['characters'][0]['id']
    r=action(client,r,h,'map-tokens','move',{'character_id':char,'map_id':layout['id'],'x':6,'y':8}).json()['room']
    line=r['state']['_plugins']['narrator-script']['data']['lines'][0]
    r=action(client,r,h,'narrator-script','edit',{'line_id':line['id'],'text':'撤销的未来台本','speaker':'旁白'}).json()['room']
    r=toggle(client,r,h,'map-tokens',False)
    response=client.post('/api/rooms/'+r['id']+'/rollback',headers=h,json={**revise(r),'target_event_id':target,'reason':'test'})
    assert response.status_code==200,response.text
    restored=response.json()
    assert restored['state']['_plugins']['map-tokens']['data']==before['map-tokens']['data']
    assert restored['state']['_plugins']['narrator-script']['data']==before['narrator-script']['data']
    assert not next(p for p in restored['plugins'] if p['id']=='map-tokens')['enabled']


def test_plugin_idempotency_and_branch_prevents_aba(client):
    _,h,_=account(client);r=setup_map(client,h);before=r;layout=r['state']['_plugins']['scene-map']['data']['map'];char=r['state']['characters'][0]['id'];k=key()
    payload={'character_id':char,'map_id':layout['id'],'x':5,'y':8}
    after=action(client,r,h,'map-tokens','move',payload,request_key=k).json()['room']
    assert action(client,before,h,'map-tokens','move',payload,request_key=k).json()['room']['revision']==after['revision']
    target=before['events'][-1]['id']
    restored=client.post('/api/rooms/'+r['id']+'/rollback',headers=h,json={**revise(after),'target_event_id':target,'reason':'ABA'}).json()
    assert action(client,before,h,'map-tokens','move',payload).status_code==409
    assert restored['branch']==2


def test_frame_sandbox_policy_and_no_secret_context(client,monkeypatch):
    _,h,_=account(client);r=setup_map(client,h)
    monkeypatch.setattr(settings,'tts_api_key','PRIVATEKEY123')
    response=client.get('/plugin-frame/scene-map?bridge='+'a'*32)
    assert response.status_code==200
    assert "connect-src 'none'" in response.headers['content-security-policy']
    assert "frame-src 'none'" in response.headers['content-security-policy']
    assert 'PRIVATEKEY123' not in response.text
    context=client.get('/api/rooms/'+r['id']+'/extensions/scene-map/context',headers=h).json()
    assert 'PRIVATEKEY123' not in json.dumps(context)
    assert 'Authorization' not in json.dumps(context)
    assert context['resources']['scene.tokens/v1']['data']['tokens']


def test_ai_disabled_human_hosting(client):
    _,h,_=account(client);r=room(client,h);r=toggle(client,r,h,'ai-host',False)
    after=act(client,r,h,'我观察周围').json()
    assert after['state']['awaiting_gm'] and after['state']['gm_error'] is None
    assert not any(e['type']=='gm' for e in after['events'])
    assert '人工补述' in after['events'][-1]['text']


def test_map_move_during_slow_gm_is_preserved(client,monkeypatch):
    import server.app as app
    started=threading.Event()
    async def slow(*args):started.set();await asyncio.sleep(.4);return Decision(narration='主持处理完成。'),{'mode':'demo','duration_ms':400,'retrieval_count':0}
    monkeypatch.setattr(app,'run_gm',slow)
    _,h,_=account(client);r=setup_map(client,h)
    layout=r['state']['_plugins']['scene-map']['data']['map'];char=r['state']['characters'][0]['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(act,client,r,h,'我等待主持处理')
        assert started.wait(3)
        busy=read(client,r,h);assert busy['busy']
        moved=action(client,busy,h,'map-tokens','move',{'character_id':char,'map_id':layout['id'],'x':7,'y':8})
        assert moved.status_code==200,moved.text
        after=future.result().json()
    assert after['state']['_plugins']['map-tokens']['data']['positions'][char]=={'x':7,'y':8}
    assert after['state']['scene']['text']=='主持处理完成。'


def test_hook_failure_isolates_extension(client,monkeypatch):
    _,h,_=account(client);r=setup_map(client,h)
    def broken(*args):raise RuntimeError('plugin failed')
    monkeypatch.setattr(manager.items['map-tokens']['backend'],'on_event',broken)
    after=act(client,r,h,'我商量下一步')
    assert after.status_code==200
    assert after.json()['state']['scene']['text']
    assert 'map-tokens' in after.json()['state']['_plugin_faults']


def test_script_event_hook_and_edit_does_not_rewrite_story(client):
    _,h,_=account(client);r=room(client,h);r=toggle(client,r,h,'narrator-script')
    before=r['state']['scene']['text'];line=r['state']['_plugins']['narrator-script']['data']['lines'][0]
    r=action(client,r,h,'narrator-script','edit',{'line_id':line['id'],'text':'演员的改写台本','speaker':'酒保'}).json()['room']
    assert r['state']['scene']['text']==before
    r=act(client,r,h,'我等待片刻').json()
    assert r['state']['_plugins']['narrator-script']['data']['lines'][-1]['source_event_id']==r['events'][-1]['id']


def test_tts_adapter_asset_access_and_rollback(client,monkeypatch):
    import server.plugin_runtime.services as services
    monkeypatch.setattr(settings,'tts_api_key','tts-private')
    monkeypatch.setattr(settings,'tts_model','test-tts')
    calls=[]
    def mock(request):
        calls.append(request);assert request.headers['authorization']=='Bearer tts-private'
        assert json.loads(request.content)['response_format']=='mp3'
        return httpx.Response(200,headers={'content-type':'audio/mpeg'},content=b'ID3-test-contract-audio')
    original=httpx.AsyncClient
    monkeypatch.setattr(services.httpx,'AsyncClient',lambda *a,**kw:original(transport=httpx.MockTransport(mock),**kw))
    _,h,_=account(client);r=room(client,h);r=toggle(client,r,h,'voice-tts');target=r['events'][-1]['id']
    line=r['state']['_plugins']['narrator-script']['data']['lines'][0]
    response=action(client,r,h,'voice-tts','synthesize',{'line_id':line['id']})
    assert response.status_code==200,response.text
    assert len(calls)==1
    clip=response.json()['output']['clip'];r=response.json()['room']
    path='/api/rooms/'+r['id']+'/assets/voice-tts/'+clip['id']
    assert client.get(path,headers=h).content==b'ID3-test-contract-audio'
    assert 'tts-private' not in response.text
    r=client.post('/api/rooms/'+r['id']+'/rollback',headers=h,json={**revise(r),'target_event_id':target,'reason':'audio rewind'}).json()
    assert client.get(path,headers=h).status_code==404


def test_untrusted_python_plugin_not_executed(client,tmp_path):
    folder=settings.data_dir/'plugins'/'unsafe-addon';folder.mkdir(parents=True)
    manifest={'id':'unsafe-addon','name':'Unsafe','version':'1.0.0','description':'test','api_version':1,'backend':'backend.py','default_enabled':False}
    (folder/'plugin.json').write_text(json.dumps(manifest))
    marker=tmp_path/'executed';(folder/'backend.py').write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n")
    _,h,_=account(client);data=client.get('/api/plugins',headers=h).json()
    plugin=next(p for p in data['plugins'] if p['id']=='unsafe-addon')
    assert plugin['blocked'] and not marker.exists()


def test_hot_discovery_ui_plugin_and_installer_security(client,tmp_path):
    from scripts.plugins import install
    bundle=tmp_path/'addon.zip';m={'id':'test-panel','name':'Test','version':'1.0.0','description':'test','api_version':1,'backend':None,'frontend':'ui.js','ui':{'group':'test','slot':'main'},'capabilities':['read:room']}
    with zipfile.ZipFile(bundle,'w') as z:z.writestr('test-panel/plugin.json',json.dumps(m));z.writestr('test-panel/ui.js',"document.getElementById('plugin-root').textContent='test';")
    digest=hashlib.sha256(bundle.read_bytes()).hexdigest();install(str(bundle),digest)
    _,h,_=account(client);r=room(client,h);client.get('/api/plugins',headers=h)
    r=toggle(client,r,h,'test-panel')
    assert next(p for p in r['plugins'] if p['id']=='test-panel')['enabled']
    assert client.get('/plugin-frame/test-panel').status_code==200
    assert 'test-panel' not in Path('web/src/App.jsx').read_text()
    malicious=tmp_path/'malicious.zip'
    with zipfile.ZipFile(malicious,'w') as z:z.writestr('../outside','bad')
    with pytest.raises(ValueError,match='Unsafe archive'):install(str(malicious))
    with pytest.raises(ValueError,match='SHA256'):install(str(bundle),'a'*64)


def test_seed_zero_is_reproducible(client):
    _,h,_=account(client);r=room(client,h);r=toggle(client,r,h,'map-generator')
    r=action(client,r,h,'map-generator','generate',{'seed':0,'theme':'forest'}).json()['room'];a=r['state']['_plugins']['scene-map']['data']['map']
    r=action(client,r,h,'map-generator','generate',{'seed':0,'theme':'forest'}).json()['room'];b=r['state']['_plugins']['scene-map']['data']['map']
    assert a['seed']==b['seed']==0 and a['grid']==b['grid']


def test_recursive_calls_bounded_without_commit(client,monkeypatch):
    from server.plugin_runtime.sdk import Result
    _,h,_=account(client);r=setup_map(client,h);extension=manager.items['map-tokens']['backend']
    async def loop(ctx,name,payload,data):return Result(data=data,calls=[{'plugin':'map-tokens','action':'move','payload':{}}])
    monkeypatch.setattr(extension,'action',loop)
    response=action(client,r,h,'map-tokens','move',{})
    assert response.status_code==422 and '循环' in response.text
    assert read(client,r,h)['revision']==r['revision']


def test_high_risk_ui_needs_grant_and_hash_changes_revoke(client,tmp_path):
    from scripts.plugins import install
    bundle=tmp_path/'speech-ui.zip';manifest={'id':'speech-addon','name':'Speech','version':'1.0.0','description':'test','api_version':1,'frontend':'ui.js','capabilities':['local:speech']}
    with zipfile.ZipFile(bundle,'w') as z:z.writestr('speech-addon/plugin.json',json.dumps(manifest));z.writestr('speech-addon/ui.js','void 0;')
    with pytest.raises(ValueError,match='grant-capabilities'):install(str(bundle))
    install(str(bundle),grant_capabilities=True)
    _,h,_=account(client);response=client.get('/api/plugins',headers=h).json()
    assert not next(p for p in response['plugins'] if p['id']=='speech-addon')['blocked']
    (settings.data_dir/'plugins/speech-addon/ui.js').write_text('void 1;')
    response=client.get('/api/plugins',headers=h).json()
    assert next(p for p in response['plugins'] if p['id']=='speech-addon')['blocked']


def install_notes(tmp_path):
    from scripts.plugins import install,package
    target=tmp_path/'notes.zip';package(Path('templates/scene-notes'),target);install(str(target),trust_backend=True)


def test_trusted_backend_template_and_rollback(client,tmp_path):
    install_notes(tmp_path)
    _,h,_=account(client);r=room(client,h);r=toggle(client,r,h,'scene-notes');target=r['events'][-1]['id']
    response=action(client,r,h,'scene-notes','append',{'text':'真正独立的便签插件'})
    assert response.status_code==200,response.text
    r=response.json()['room'];assert r['state']['_plugins']['scene-notes']['data']['notes']==['真正独立的便签插件']
    r=client.post('/api/rooms/'+r['id']+'/rollback',headers=h,json={**revise(r),'target_event_id':target,'reason':'notes'}).json()
    assert r['state']['_plugins']['scene-notes']['data']['notes']==[]


def test_state_migration_on_reenable(client,tmp_path):
    install_notes(tmp_path)
    _,h,_=account(client);r=room(client,h);r=toggle(client,r,h,'scene-notes');r=toggle(client,r,h,'scene-notes',False)
    folder=settings.data_dir/'plugins/scene-notes';m=json.loads((folder/'plugin.json').read_text());m.update(state_version=2,version='1.1.0');(folder/'plugin.json').write_text(json.dumps(m))
    code=(folder/'backend.py').read_text().replace('schema_version=1','schema_version=2\n    def migrate(self,data,old_version):return dict(data,migrated_from=old_version)')
    (folder/'backend.py').write_text(code)
    trust=settings.data_dir/'plugin-trust.json';values=json.loads(trust.read_text());values['scene-notes']=package_hash(folder);trust.write_text(json.dumps(values))
    manager.refresh();r=toggle(client,r,h,'scene-notes')
    assert r['state']['_plugins']['scene-notes']['schema_version']==2
    assert r['state']['_plugins']['scene-notes']['data']['migrated_from']==1


def test_resource_provider_collision_is_rejected(client,tmp_path):
    from scripts.plugins import install
    bundle=tmp_path/'tokens.zip';m={'id':'alt-tokens','name':'Alt','version':'1.0.0','description':'test','api_version':1,'backend':'backend.py','requires':['scene-map'],'provides':['scene.tokens/v1'],'actions':[],'capabilities':['read:room']}
    with zipfile.ZipFile(bundle,'w') as z:
        z.writestr('alt-tokens/plugin.json',json.dumps(m));z.writestr('alt-tokens/backend.py','from server.plugin_runtime.sdk import Plugin\nclass Extension(Plugin):pass\n')
    install(str(bundle),trust_backend=True)
    _,h,_=account(client);r=setup_map(client,h)
    response=client.post(f"/api/rooms/{r['id']}/extensions/alt-tokens/toggle",headers=h,json={**revise(r),'enabled':True})
    assert response.status_code==409 and '已有启用提供者' in response.text
    r=toggle(client,r,h,'map-tokens',False);r=toggle(client,r,h,'alt-tokens')
    assert next(p for p in r['plugins'] if p['id']=='alt-tokens')['enabled']


def test_tts_result_after_rollback_rejected_and_asset_not_visible(client,monkeypatch):
    import server.plugin_runtime.services as services
    started=threading.Event();monkeypatch.setattr(settings,'tts_api_key','fake-private');monkeypatch.setattr(settings,'tts_model','test')
    async def mock(request):started.set();await asyncio.sleep(.3);return httpx.Response(200,headers={'content-type':'audio/mpeg'},content=b'ID3-contract')
    original=httpx.AsyncClient;monkeypatch.setattr(services.httpx,'AsyncClient',lambda *a,**kw:original(transport=httpx.MockTransport(mock),**kw))
    _,h,_=account(client);r=room(client,h);r=toggle(client,r,h,'voice-tts');target=r['events'][0]['id'];line=r['state']['_plugins']['narrator-script']['data']['lines'][0]['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(action,client,r,h,'voice-tts','synthesize',{'line_id':line});assert started.wait(3)
        restored=client.post('/api/rooms/'+r['id']+'/rollback',headers=h,json={**revise(r),'target_event_id':target,'reason':'during external call'});assert restored.status_code==200
        response=future.result();assert response.status_code==409,response.text
    asset=next((settings.data_dir/'assets'/r['id']/'voice-tts').glob('*.bin'))
    assert client.get('/api/rooms/'+r['id']+'/assets/voice-tts/'+asset.stem,headers=h).status_code==404


def test_full_backup_restores_db_assets_plugins_and_trust(client,tmp_path):
    from scripts.backup import backup
    from scripts.restore import restore
    _,h,_=account(client);r=room(client,h);install_notes(tmp_path)
    folder=settings.data_dir/'assets'/r['id']/'voice-tts';folder.mkdir(parents=True);(folder/(key()+'.bin')).write_bytes(b'backup-contract-asset')
    output=tmp_path.parent/(tmp_path.name+'-full-backup.zip');result=backup(output,True)
    destination=tmp_path.parent/(tmp_path.name+'-restored');restored=restore(output,destination,result['sha256'])
    assert restored['integrity_check']=='ok' and (destination/'tavern.sqlite3').exists()
    assert next((destination/'assets'/r['id']/'voice-tts').glob('*.bin')).read_bytes()==b'backup-contract-asset'
    assert (destination/'plugins/scene-notes/backend.py').exists() and (destination/'plugin-trust.json').exists()
    with pytest.raises(ValueError,match='empty'):restore(output,destination)


def test_malformed_metadata_and_trust_file_do_not_break_core(client):
    folder=settings.data_dir/'plugins'/'broken-title';folder.mkdir(parents=True)
    (folder/'plugin.json').write_text(json.dumps({'id':'broken-title','name':{'invalid':'object'},'version':'1.0.0','description':'bad title','api_version':1}))
    (settings.data_dir/'plugin-trust.json').write_text('{broken-json')
    _,h,_=account(client);r=room(client,h);catalog=client.get('/api/plugins',headers=h)
    assert catalog.status_code==200
    assert not any(p['id']=='broken-title' for p in catalog.json()['plugins'])
    assert client.get('/api/rooms/'+r['id'],headers=h).status_code==200
    assert next(p for p in r['plugins'] if p['id']=='ai-host')['enabled']
