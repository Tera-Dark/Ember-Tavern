import base64
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import stat
import zipfile

import pytest
from fastapi import HTTPException
from server.config import ROOT
from server.db import connection
from server.contracts.presets import Scenario
from server.plugin_runtime.manager import manager
from server.presets.codec import (load_folder,parse_envelope,parse_archive,archive_bytes,decode_input,canonical,digest,MAX_ARCHIVE,PresetError)
from server.presets.library import compatibility
from server.rules import engine_for
from server.schemas import Decision
from server.retrieval import model_context
from test_game import account,revise,key,act


@pytest.fixture
def host(client):
    return account(client,'preset_host')[1]


def package(identity='harbor-last-ferry'):
    return load_folder(ROOT/'presets'/identity)


def envelope(identity='community-episode',version='1.0.0'):
    value=deepcopy(package().envelope())
    manifest=json.loads(value['files']['preset.json']);manifest['metadata']['id']=identity;manifest['metadata']['version']=version
    value['files']['preset.json']=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    return value


def imported(client,headers,value):
    preview=client.post('/api/presets/preview',headers=headers,json={'document':value});assert preview.status_code==200,preview.text
    result=client.post('/api/presets/import',headers=headers,json={'document':value,'expected_hash':preview.json()['package_hash'],'confirm_data_only':True});assert result.status_code==200,result.text
    return result.json()


def new_room(client,headers,identity='harbor-last-ferry',request=None,host_plays=True):
    data={'title':'预设验收','package_hash':package(identity).package_hash,'request_key':request or key(),'host_plays':host_plays}
    response=client.post('/api/rooms/from-preset',headers=headers,json=data);assert response.status_code==201,response.text
    return response.json(),data


def reveal(client,headers,room,clue):
    response=client.post('/api/rooms/'+room['id']+'/campaign/reveal',headers=headers,json={**revise(room),'scene_id':room['state']['campaign']['current_scene'],'clue_id':clue})
    assert response.status_code==200,response.text
    return response.json()


def advance(client,headers,room,edge):
    response=client.post('/api/rooms/'+room['id']+'/campaign/advance',headers=headers,json={**revise(room),'scene_id':room['state']['campaign']['current_scene'],'transition_id':edge})
    assert response.status_code==200,response.text
    return response.json()


def test_catalog_is_public_metadata_not_future_scenes_or_gm_secrets(client,host):
    assert client.get('/api/presets').status_code==401
    result=client.get('/api/presets',headers=host).json()
    assert len(result['entries'])==5
    assert {item['rule_system'] for item in result['entries']} >= {'dnd5e-srd-5.2.1/v1','ember-coop-settlement/v1'}
    assert 'hbr-secret-m1' not in json.dumps(result)
    for entry in result['entries']:
        assert entry['compatibility']['can_create'] and entry['default_ai_mode']=='demo' and entry['data_only']
        assert entry['character_count']==4 and entry['ending_count']>=2
        assert any('再分发' in warning for warning in entry['warnings'])


@pytest.mark.parametrize('identity',['harbor-last-ferry','frontier-lost-caravan','town-one-week'])
def test_pack_roundtrip_pins_components_exactly(identity):
    original=package(identity);restored=parse_archive(archive_bytes(original))
    assert restored.package_hash==original.package_hash
    assert decode_input(document=original.envelope()).package_hash==original.package_hash
    assert len(restored.characters)==4


@pytest.mark.parametrize('path',['../escape.json','/absolute.json','a\\b.json','a//b.json','con.json','lpt1.txt','x.py','x.js','x.html','.env','UPPER.json','c:/secret.json'])
def test_unsafe_zip_paths_and_code_rejected(path):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:archive.writestr(path,'{}')
    with pytest.raises(PresetError):parse_archive(output.getvalue())


def test_symlink_duplicate_and_bomb_archive_rejected():
    for mode in ['link','duplicate','bomb']:
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            info=zipfile.ZipInfo('preset.json')
            if mode=='link':info.external_attr=(stat.S_IFLNK|0o777)<<16
            archive.writestr(info,'{}')
            if mode=='duplicate':archive.writestr('preset.json','{}')
            if mode=='bomb':archive.writestr('world.json','x'*(513*1024))
        with pytest.raises(PresetError):parse_archive(output.getvalue())
    with pytest.raises(PresetError):parse_archive(b'x'*(MAX_ARCHIVE+1))


def test_checksums_unknown_formats_ids_and_unknown_fields_rejected():
    original=package().envelope()
    mutations=[]
    changed=deepcopy(original);changed['files']['world/worldbook.json']+=' ';mutations.append(changed)
    changed=deepcopy(original);manifest=json.loads(changed['files']['preset.json']);manifest['format']='ember.preset/v2';changed['files']['preset.json']=json.dumps(manifest);mutations.append(changed)
    changed=deepcopy(original);manifest=json.loads(changed['files']['preset.json']);manifest['api_key']='must-not-be-supported';changed['files']['preset.json']=json.dumps(manifest);mutations.append(changed)
    changed=deepcopy(original);changed['files']['script.js']='alert(1)';mutations.append(changed)
    changed=deepcopy(original);manifest=json.loads(changed['files']['preset.json']);manifest['scenario']['id']='wrong-id';changed['files']['preset.json']=json.dumps(manifest);mutations.append(changed)
    for changed in mutations:
        with pytest.raises(PresetError):parse_envelope(changed)


def test_scenario_graph_rejects_unreachable_and_clue_deadlocks():
    story=deepcopy(package().scenario)
    story['scenes'][0]['transitions'][0]['target']='missing'
    with pytest.raises(ValueError):Scenario.model_validate(story)
    story=deepcopy(package('town-one-week').scenario)
    story['scenes'][0]['transitions'][0]['requires_clues']=['recipe'] # obtained only in next scene
    story['scenes'][0]['transitions']=story['scenes'][0]['transitions'][:1]
    with pytest.raises(ValueError):Scenario.model_validate(story)


def test_preview_no_writes_import_requires_confirmed_hash_and_formal_host(client,host):
    value=envelope();before=client.get('/api/presets',headers=host).json()
    preview=client.post('/api/presets/preview',headers=host,json={'document':value}).json()
    assert preview['writes'] is False and preview['code_executed'] is False
    assert before==client.get('/api/presets',headers=host).json()
    response=client.post('/api/presets/import',headers=host,json={'document':value,'expected_hash':'0'*64,'confirm_data_only':True})
    assert response.status_code==409
    result=imported(client,host,value)
    assert result['added'] and result['code_executed'] is False
    assert imported(client,host,value)['added'] is False
    guest=client.post('/api/auth/demo').json()
    assert client.post('/api/presets/import',headers={'X-Ember-Session':guest['token']},json={'document':value,'expected_hash':result['package_hash'],'confirm_data_only':True}).status_code==403


def test_conflicting_same_version_cannot_replace_older_room_source(client,host):
    first=envelope('community-version');first_result=imported(client,host,first)
    data={'title':'固定旧版本','package_hash':first_result['package_hash'],'request_key':key()}
    original=client.post('/api/rooms/from-preset',headers=host,json=data).json()
    conflict=deepcopy(first);manifest=json.loads(conflict['files']['preset.json']);manifest['metadata']['description']='不同内容，同版本';conflict['files']['preset.json']=json.dumps(manifest)
    preview=client.post('/api/presets/preview',headers=host,json={'document':conflict}).json()
    response=client.post('/api/presets/import',headers=host,json={'document':conflict,'expected_hash':preview['package_hash'],'confirm_data_only':True})
    assert response.status_code==409
    newer=deepcopy(conflict);manifest['metadata']['version']='2.0.0';newer['files']['preset.json']=json.dumps(manifest)
    assert imported(client,host,newer)['added']
    existing=client.get('/api/rooms/'+original['id'],headers=host).json()
    assert existing['state']['_preset_lock']['package_hash']==first_result['package_hash']
    assert existing['state']['_preset_lock']['preset']['version']=='1.0.0'


def test_missing_required_dependency_leaves_no_partial_room(client,host):
    value=envelope('dependency-test');manifest=json.loads(value['files']['preset.json']);manifest['plugins'][0]['id']='not-installed';value['files']['preset.json']=json.dumps(manifest)
    result=imported(client,host,value)
    assert not result['compatibility']['can_create']
    response=client.post('/api/rooms/from-preset',headers=host,json={'title':'不可创建','package_hash':result['package_hash'],'request_key':key()})
    assert response.status_code==422
    with connection() as con:
        for table in ('rooms','members','events','assignments','room_plugins','room_preset_locks','room_creation_receipts'):
            assert con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0


def test_missing_optional_dependency_warns_and_does_not_auto_install():
    value=envelope('optional-module');manifest=json.loads(value['files']['preset.json']);manifest['plugins'].append({'id':'optional-hud','version':'1.0.0','sha256':'0'*64,'required':False,'enabled':True});value['files']['preset.json']=json.dumps(manifest)
    ready=compatibility(parse_envelope(value),manager)
    assert ready['can_create'] and ready['warnings'] and all(pin['id']!='optional-hud' for pin in ready['plugins'])


def test_room_creation_retry_and_changed_request_conflict(client,host):
    room,data=new_room(client,host,host_plays=False)
    assert all(not char['assigned_to'] for char in room['state']['characters'])
    for _ in range(12):assert client.post('/api/rooms/from-preset',headers=host,json=data).json()['id']==room['id']
    assert client.post('/api/rooms/from-preset',headers=host,json=data|{'title':'不同意图'}).status_code==409
    assert len(client.get('/api/rooms',headers=host).json())==1
    _,other,_=account(client,'other_host')
    assert client.post('/api/rooms/from-preset',headers=other,json=data).json()['id']!=room['id']


def test_concurrent_room_retries_create_one_atomic_room(client,host):
    data={'title':'并发开桌','package_hash':package().package_hash,'request_key':key()}
    def create(_):
        response=client.post('/api/rooms/from-preset',headers=host,json=data)
        assert response.status_code==201,response.text
        return response.json()['id']
    with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(create,range(4)))
    assert len(set(ids))==1
    with connection() as con:
        assert con.execute('SELECT COUNT(*) FROM room_creation_receipts').fetchone()[0]==1


def test_failure_after_room_insert_rolls_back_all_rows(client,host,monkeypatch):
    import server.room_service as factory
    def fail(*args,**kwargs):raise RuntimeError('injected prologue failure')
    monkeypatch.setattr(factory,'append_event',fail)
    with pytest.raises(RuntimeError):new_room(client,host)
    with connection() as con:
        for table in ('rooms','members','assignments','room_plugins','room_preset_locks','room_creation_receipts','events'):
            assert con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0


def test_player_cannot_see_or_advance_hidden_story(client,host):
    room,_=new_room(client,host)
    _,player,_=account(client,'story_player');client.post('/api/rooms/join',headers=player,json={'code':room['code']})
    public=client.get('/api/rooms/'+room['id'],headers=player).json()
    assert 'hbr-secret-m1' not in json.dumps(public)
    for field in ('_scenario','_preset_lock','_preset_theme'):assert field not in public['state']
    assert not {'gm_notes','transitions','clues','lock'}&set(public['state']['campaign'])
    data={**revise(room),'scene_id':'dock','clue_id':'letter'}
    assert client.post('/api/rooms/'+room['id']+'/campaign/reveal',headers=player,json=data).status_code==403
    assert client.get('/api/presets/'+package().package_hash+'/export',headers=player).status_code==200 # public catalog package export, not private campaign state
    assert client.get('/api/rooms/'+room['id']+'/export',headers=player).status_code==403


def test_clue_gates_stale_scene_and_rewind_are_authoritative(client,host):
    room,_=new_room(client,host);opening=room['events'][0]['id']
    stale=deepcopy(room)
    response=client.post('/api/rooms/'+room['id']+'/campaign/reveal',headers=host,json={**revise(room),'scene_id':'dock','clue_id':'ledger'})
    assert response.status_code==422
    room=reveal(client,host,room,'letter');room=advance(client,host,room,'warehouse');room=reveal(client,host,room,'ledger');room=advance(client,host,room,'board')
    room=advance(client,host,room,'evidence');assert room['state']['campaign']['completed']
    response=client.post('/api/rooms/'+room['id']+'/campaign/advance',headers=host,json={**revise(stale),'scene_id':'dock','transition_id':'leave'})
    assert response.status_code==409
    restored=client.post('/api/rooms/'+room['id']+'/rollback',headers=host,json={**revise(room),'target_event_id':opening,'reason':'验收回档'}).json()
    assert restored['state']['campaign']['current_scene']=='dock' and not restored['state']['campaign']['revealed_clues']
    assert restored['state']['_preset_lock']['package_hash']==package().package_hash
    assert not any('货单的空行' in fact for fact in restored['state']['facts'])


ROUTES={
 'harbor-last-ferry':[[':letter','warehouse',':ledger','board','evidence'],['leave']],
 'frontier-lost-caravan':[['camp','gate',':tunnel','rescue'],['camp',':agreement','trade'],['withdraw']],
 'town-one-week':[[':promise','workshop','feast','together'],['quiet']],
}
@pytest.mark.parametrize('identity',list(ROUTES))
def test_each_original_example_has_playable_ending_paths(client,host,identity):
    endings=set()
    for steps in ROUTES[identity]:
        room,_=new_room(client,host,identity)
        for step in steps:room=reveal(client,host,room,step[1:]) if step.startswith(':') else advance(client,host,room,step)
        assert room['state']['campaign']['completed'];endings.add(room['state']['campaign']['current_scene'])
    assert len(endings)>=2


def test_narrative_profile_is_enforced_not_only_a_prompt(client,host):
    room,_=new_room(client,host,'town-one-week')
    room=act(client,room,host).json()
    assert room['state']['pending_check'] is None and '叙事模式' in room['events'][-1]['text']
    state=deepcopy(room['state'])
    bad=Decision(narration='不允许绕过模式',check={'attribute':'insight','dc':12,'reason':'强迫检定','risk':'none'})
    with pytest.raises(ValueError):engine_for(state).validate_decision(state,bad)
    context=model_context(room['id'],state,'询问')
    assert 'scenes' not in context['campaign'] and context['campaign']['profile']['checks']=='narrative'


def test_rule_and_plugin_changes_do_not_silently_upgrade_campaign(client,host,monkeypatch):
    room,_=new_room(client,host)
    state=deepcopy(room['state']);state['_preset_lock']['rule']['contract_sha256']='0'*64
    with pytest.raises(HTTPException) as exc:engine_for(state)
    assert exc.value.status_code==409
    original=manager.items['ai-host']['hash'];monkeypatch.setitem(manager.items['ai-host'],'hash','0'*64)
    assert not manager.enabled(room['id'],'ai-host')
    assert 'SHA256' in manager.pin_reason(room['id'],'ai-host')
    response=client.post('/api/rooms/'+room['id']+'/extensions/scene-map/toggle',headers=host,json={**revise(room),'enabled':True})
    assert response.status_code==422


def test_owner_archive_includes_frozen_data_but_no_account_secrets(client,host):
    room,_=new_room(client,host)
    exported=client.get('/api/rooms/'+room['id']+'/export',headers=host)
    assert exported.status_code==200
    value=exported.json();assert value['preset_bundle']['format']=='ember.preset-bundle/v1'
    assert parse_envelope(value['preset_bundle']).package_hash==package().package_hash
    assert 'password_hash' not in exported.text and 'token_hash' not in exported.text


def test_creator_preset_scaffold_lock_package_and_schema(tmp_path):
    from scripts.creator import scaffold,validate,lock_preset,package_preset,schemas
    folder=tmp_path/'example';scaffold('preset',folder,'author-example','作者样例')
    assert validate(folder)['code_executed'] is False
    manifest=json.loads((folder/'preset.json').read_text());ref=manifest['worldbook']
    world=json.loads((folder/ref['path']).read_text());world['world']['premise']='我自己的新设定';(folder/ref['path']).write_text(json.dumps(world,ensure_ascii=False))
    with pytest.raises(ValueError):validate(folder)
    lock_preset(folder);target=tmp_path/'package.zip';package_preset(folder,target)
    assert validate(target)['package_hash']==validate(folder)['package_hash']
    with pytest.raises(ValueError):package_preset(folder,target)
    assert not schemas(check=True)['schema_drift']


def test_private_import_is_not_a_hash_capability_for_other_accounts(client,host):
    own=imported(client,host,envelope('private-personal-story'))
    _,other,_=account(client,'private_other')
    catalog=client.get('/api/presets',headers=other).json()
    assert all(entry['id']!='private-personal-story' for entry in catalog['entries'])
    assert client.get('/api/presets/'+own['package_hash']+'/export',headers=other).status_code==404
    response=client.post('/api/rooms/from-preset',headers=other,json={'title':'不可读取','package_hash':own['package_hash'],'request_key':key()})
    assert response.status_code==404
    # Possession of the actual data file permits a separate personal library grant.
    assert imported(client,other,envelope('private-personal-story'))['added'] is False
    assert client.get('/api/presets/'+own['package_hash']+'/export',headers=other).status_code==200


def test_ai_fact_text_cannot_satisfy_structured_clue_gate(client,host):
    room,_=new_room(client,host)
    state=deepcopy(room['state']);state['facts'].append('ledger 已知道，货单证明了真相')
    from server.presets import scenario
    scenario.advance(state,'dock','boat')
    with pytest.raises(HTTPException) as error:scenario.advance(state,'boat','evidence')
    assert error.value.status_code==422 and state['_scenario']['current_scene']=='boat'


def test_declared_matching_disabled_optional_module_can_be_enabled_without_upgrading(client,host):
    value=envelope('optional-map-story');manifest=json.loads(value['files']['preset.json']);item=manager.items['scene-map']
    manifest['plugins'].append({'id':'scene-map','version':item['manifest']['version'],'sha256':item['hash'],'required':False,'enabled':False})
    value['files']['preset.json']=json.dumps(manifest)
    result=imported(client,host,value)
    room=client.post('/api/rooms/from-preset',headers=host,json={'title':'可选地图','package_hash':result['package_hash'],'request_key':key()}).json()
    assert any(pin['id']=='scene-map' and not pin['enabled'] for pin in room['state']['_preset_lock']['plugins'])
    assert not manager.enabled(room['id'],'scene-map')
    response=client.post('/api/rooms/'+room['id']+'/extensions/scene-map/toggle',headers=host,json={**revise(room),'enabled':True})
    assert response.status_code==200,response.text
    assert manager.enabled(room['id'],'scene-map')


def test_public_campaign_resource_hides_gm_even_for_owner(client,host):
    room,_=new_room(client,host)
    user={'id':room['owner_id'],'display_name':'房主','guest':False}
    resource=manager.resource(room,room['state'],'core.campaign/v1',user)
    public=resource['data']['campaign']
    assert resource['owner']=='@core' and not {'gm_notes','clues','transitions','lock'}&set(public)
    assert 'hbr-secret-m1' not in json.dumps(resource)
    assert public['current_scene']=='dock'
