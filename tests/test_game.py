import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest
import httpx
import server.app as game_app
from server.app import app
from server.config import settings
from server.db import connection
from server.ai import AIError
from server.schemas import Decision
from server.retrieval import model_context


def key():return uuid.uuid4().hex

def account(client,username='playerone'):
    r=client.post('/api/auth/register',json={'username':username,'display_name':username,'password':'testpassword123'})
    assert r.status_code==201,r.text
    data=r.json()
    return data['user'],{'Authorization':'Bearer '+data['token']},data['token']

def room(client,headers):
    r=client.post('/api/rooms',json={'title':'test-room','preset':'harbor'},headers=headers)
    assert r.status_code==201,r.text
    return r.json()

def read(client,r,h):return client.get('/api/rooms/'+r['id'],headers=h).json()

def revise(r):return {'expected_revision':r['revision'],'request_key':key()}

def act(client,r,h,text='我推开生锈的门',character_id=None,request_key=None):
    return client.post('/api/rooms/'+r['id']+'/actions',headers=h,json={**revise(r),'request_key':request_key or key(),'text':text,'character_id':character_id or r['state']['characters'][0]['id']})

def roll(client,r,h,request_key=None):
    return client.post('/api/rooms/'+r['id']+'/checks/'+r['state']['pending_check']['id']+'/roll',headers=h,json={**revise(r),'request_key':request_key or key()})


def test_auth_and_password_storage(client):
    user,h,token=account(client)
    assert client.get('/api/auth/me',headers=h).json()['id']==user['id']
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',json={'username':'playerone','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'PLAYERONE','password':'testpassword123'}).status_code==200
    with connection() as c:
        raw=c.execute('SELECT password_hash FROM users').fetchone()[0]
        stored=c.execute('SELECT token_hash FROM sessions').fetchone()[0]
    assert raw!='testpassword123' and len(raw)==64
    assert stored!=token
    client.post('/api/auth/logout',headers=h)
    assert client.get('/api/auth/me',headers=h).status_code==401


def test_room_access_and_role_permissions(client):
    owner,oh,_=account(client,'host');player,ph,_=account(client,'guestplayer')
    r=room(client,oh)
    assert client.get('/api/rooms/'+r['id'],headers=ph).status_code==403
    joined=client.post('/api/rooms/join',json={'code':r['code'].lower()},headers=ph)
    assert joined.status_code==200
    r=joined.json();char=r['state']['characters'][1]['id']
    assert act(client,r,ph,character_id=char).status_code==403
    path='/api/rooms/'+r['id']+'/characters/'+char+'/assign'
    assert client.post(path,headers=ph,json={**revise(r),'user_id':player['id']}).status_code==403
    r=client.post(path,headers=oh,json={**revise(r),'user_id':player['id']}).json()
    assert act(client,r,ph,character_id=char).status_code==200


def test_action_roll_and_authoritative_consequence(client,monkeypatch):
    _,h,_=account(client);r=room(client,h)
    hp=r['state']['characters'][0]['hp']
    r=act(client,r,h).json()
    assert r['state']['pending_check']['risk']=='harm'
    assert r['state']['turn']==1
    assert r['events'][-1]['payload']['mode']=='demo'
    monkeypatch.setattr('server.domain.secrets.randbelow',lambda n:0)
    result=roll(client,r,h)
    assert result.status_code==200,result.text
    r=result.json()
    assert r['state']['pending_check'] is None
    assert r['state']['characters'][0]['hp']==hp-1
    dice=next(e for e in r['events'] if e['type']=='dice')
    assert dice['payload']['rolls']==[1] and dice['payload']['outcome']=='大失败'
    assert not r['state']['awaiting_gm']


def test_pending_check_blocks_new_action_and_edit(client):
    _,h,_=account(client);r=room(client,h);r=act(client,r,h).json()
    assert act(client,r,h).status_code==409
    c=r['state']['characters'][0]
    body={k:v for k,v in c.items() if k not in ('id','assigned_to')}
    assert client.put('/api/rooms/'+r['id']+'/characters/'+c['id'],headers=h,json={**revise(r),**body}).status_code==409


def test_idempotent_action_and_roll(client):
    _,h,_=account(client);before=room(client,h);k=key()
    r=act(client,before,h,request_key=k).json()
    assert act(client,before,h,request_key=k).json()['revision']==r['revision']
    roll_key=key();after=roll(client,r,h,request_key=roll_key).json()
    duplicate=roll(client,r,h,request_key=roll_key).json()
    assert duplicate['revision']==after['revision']
    assert len([e for e in after['events'] if e['type']=='action'])==1
    assert len([e for e in after['events'] if e['type']=='dice'])==1


def test_rollback_restores_game_not_membership_and_filters_memory(client,monkeypatch):
    owner,h,_=account(client,'host');player,ph,_=account(client,'friend')
    original=room(client,h);r=original
    target=r['events'][0]['id']
    client.post('/api/rooms/join',headers=ph,json={'code':r['code']})
    char=r['state']['characters'][1]['id']
    r=client.post('/api/rooms/'+r['id']+'/characters/'+char+'/assign',headers=h,json={**revise(r),'user_id':player['id']}).json()
    r=act(client,r,h,text='我推开门并写下 VOIDFUTURE12345').json()
    monkeypatch.setattr('server.domain.secrets.randbelow',lambda n:0)
    r=roll(client,r,h).json()
    world={**r['state']['world'],'title':'Future World'}
    r=client.put('/api/rooms/'+r['id']+'/world',headers=h,json={**revise(r),**world}).json()
    rewound=client.post('/api/rooms/'+r['id']+'/rollback',headers=h,json={**revise(r),'target_event_id':target,'reason':'测试'}).json()
    assert rewound['state']['world']==original['state']['world']
    assert rewound['state']['characters'][0]['hp']==original['state']['characters'][0]['hp']
    assert rewound['state']['turn']==0 and rewound['state']['pending_check'] is None
    assert rewound['branch']==2 and rewound['archived_count']>0
    assert len(rewound['members'])==2
    assert rewound['state']['characters'][1]['assigned_to']==player['id']
    search=client.get('/api/rooms/'+r['id']+'/context?q=VOIDFUTURE12345',headers=h).json()
    assert search['results']==[]
    with connection() as c:state=json.loads(c.execute('SELECT state_json FROM rooms WHERE id=?',(r['id'],)).fetchone()[0])
    context=model_context(r['id'],state,'VOIDFUTURE12345')
    assert 'VOIDFUTURE12345' not in json.dumps(context,ensure_ascii=False)
    assert client.get('/api/rooms/'+r['id']+'/events?archived=true',headers=ph).status_code==403


def test_rollback_to_action_allows_retry(client):
    _,h,_=account(client);r=room(client,h);r=act(client,r,h).json()
    target=next(e for e in r['events'] if e['type']=='action')
    r=client.post('/api/rooms/'+r['id']+'/rollback',headers=h,json={**revise(r),'target_event_id':target['id'],'reason':'retry'}).json()
    assert r['state']['awaiting_gm'] and r['state']['pending_check'] is None
    r=client.post('/api/rooms/'+r['id']+'/gm/retry',headers=h,json=revise(r)).json()
    assert r['state']['pending_check'] and not r['state']['awaiting_gm']
    assert len([e for e in r['events'] if e['type']=='action'])==1


def test_revision_conflict_does_not_commit(client):
    _,h,_=account(client);r=room(client,h);revision=r['revision']
    response=client.post('/api/rooms/'+r['id']+'/dice',headers=h,json={**revise(r),'expected_revision':revision-1,'expression':'1d20'})
    assert response.status_code==409
    assert read(client,r,h)['revision']==revision


def test_concurrent_actions_are_serialized(client):
    _,h,_=account(client);r=room(client,h)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:act(client,r,h),range(2)))
    assert sorted(x.status_code for x in results)==[200,409]
    current=read(client,r,h)
    assert len([e for e in current['events'] if e['type']=='action'])==1


def test_gm_failure_not_fake_success_and_host_note_recovers(client,monkeypatch):
    async def failed(*args):raise AIError('知识模型请求失败（HTTP 429）')
    monkeypatch.setattr(game_app,'run_gm',failed)
    _,h,_=account(client);r=room(client,h);r=act(client,r,h).json()
    assert r['state']['awaiting_gm'] and '429' in r['state']['gm_error']
    assert r['events'][-1]['type']=='error'
    assert not any(e['type']=='gm' for e in r['events'])
    r=client.post('/api/rooms/'+r['id']+'/gm/note',headers=h,json={**revise(r),'text':'门开了，但里面空无一人。'}).json()
    assert not r['state']['awaiting_gm'] and r['state']['gm_error'] is None
    assert r['events'][-1]['type']=='gm_note'


@pytest.mark.parametrize('expression',['0d20','21d6','1d1','1d101','1d20+101','evil'])
def test_invalid_free_dice(client,expression):
    _,h,_=account(client);r=room(client,h)
    assert client.post('/api/rooms/'+r['id']+'/dice',headers=h,json={**revise(r),'expression':expression}).status_code==422


def test_valid_free_dice_never_changes_attributes(client):
    _,h,_=account(client);r=room(client,h);chars=r['state']['characters']
    result=client.post('/api/rooms/'+r['id']+'/dice',headers=h,json={**revise(r),'expression':'2d6+2'}).json()
    assert 4<=result['events'][-1]['payload']['total']<=14
    assert result['state']['characters']==chars


def test_context_is_room_scoped_and_ooc_excluded(client):
    _,h,_=account(client);a=room(client,h);b=room(client,h)
    a=client.post('/api/rooms/'+a['id']+'/gm/note',headers=h,json={**revise(a),'text':'ONLYROOMTOKEN888'}).json()
    assert client.get('/api/rooms/'+b['id']+'/context?q=ONLYROOMTOKEN888',headers=h).json()['results']==[]
    a=client.post('/api/rooms/'+a['id']+'/chat',headers=h,json={'request_key':key(),'text':'OUTSIDECHAT111'}).json()
    assert client.get('/api/rooms/'+a['id']+'/context?q=OUTSIDECHAT111',headers=h).json()['results']==[]


def test_export_contains_snapshots_not_credentials(client):
    _,h,_=account(client);r=room(client,h)
    response=client.get('/api/rooms/'+r['id']+'/export',headers=h)
    data=response.json()
    assert data['format']=='ember-tavern/v1' and 'snapshot' in data['all_events'][0]
    assert 'password_hash' not in response.text and 'token_hash' not in response.text
    assert 'testpassword123' not in response.text


def test_live_mode_requires_both_credentials(client):
    _,h,_=account(client);r=room(client,h)
    response=client.put('/api/rooms/'+r['id']+'/settings',headers=h,json={**revise(r),'ai_mode':'live'})
    assert response.status_code==422
    assert not client.get('/api/models').json()['live_ready']


def test_live_dual_adapter_contract_with_mock_services(client,monkeypatch):
    import server.ai as ai
    monkeypatch.setattr(settings,'gemini_api_key','knowledge-secret')
    monkeypatch.setattr(settings,'gemini_model','test-knowledge')
    monkeypatch.setattr(settings,'decision_api_key','decision-secret')
    monkeypatch.setattr(settings,'decision_model','test-decision')
    calls=[]
    def mock(request):
        calls.append(request)
        if 'generativelanguage' in request.url.host:
            assert request.headers['x-goog-api-key']=='knowledge-secret'
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'尊重黄铜钥匙与旧海关的联系。'}]}}]})
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'narration':'潮湿的钥匙柄刻着海鸥。','facts':[],'check':{'attribute':'insight','dc':12,'reason':'辨认印记','risk':'none'}})}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(ai.httpx,'AsyncClient',lambda *args,**kwargs:original(transport=httpx.MockTransport(mock),**kwargs))
    _,h,_=account(client);r=room(client,h)
    r=client.put('/api/rooms/'+r['id']+'/settings',headers=h,json={**revise(r),'ai_mode':'live'}).json()
    r=act(client,r,h).json()
    assert len(calls)==2
    assert r['events'][-1]['payload']['mode']=='live'
    assert r['state']['pending_check']['dc']==12
    assert 'knowledge-secret' not in json.dumps(r) and 'decision-secret' not in json.dumps(r)


def test_decision_schema_rejects_unauthorized_mutation():
    with pytest.raises(ValueError):Decision.model_validate({'narration':'hello','hp_delta':-100})
    with pytest.raises(ValueError):Decision.model_validate({'narration':'hello','check':{'attribute':'admin','dc':12,'reason':'hack','risk':'none'}})
    with pytest.raises(ValueError):Decision.model_validate({'narration':'hello','check':{'attribute':'insight','dc':100,'reason':'hack','risk':'none'}})


def test_websocket_auth_presence_and_broadcast(client):
    owner,h,t=account(client,'host');friend,fh,ft=account(client,'friend');r=room(client,h)
    client.post('/api/rooms/join',headers=fh,json={'code':r['code']})
    path='/ws/rooms/'+r['id']
    with client.websocket_connect(path) as a:
        a.send_json({'type':'auth','token':t})
        first=a.receive_json()
        assert first['type']=='state'
        with client.websocket_connect(path) as b:
            b.send_json({'type':'auth','token':ft})
            state=b.receive_json()['data']
            assert sum(m['online'] for m in state['members'])==2
            client.post('/api/rooms/'+r['id']+'/chat',headers=h,json={'text':'同步消息','request_key':key()})
            updated=b.receive_json()['data']
            assert updated['events'][-1]['text']=='同步消息'
    with client.websocket_connect(path) as denied:
        denied.send_json({'type':'auth','token':'invalid'})
        with pytest.raises(WebSocketDisconnect) as exc:denied.receive_json()
        assert exc.value.code==4401


def test_websocket_nonmember_denied(client):
    _,h,_=account(client,'host');_,_,t=account(client,'outsider');r=room(client,h)
    with client.websocket_connect('/ws/rooms/'+r['id']) as ws:
        ws.send_json({'type':'auth','token':t})
        with pytest.raises(WebSocketDisconnect) as exc:ws.receive_json()
        assert exc.value.code==4403


def test_data_and_sessions_survive_restart(client):
    user,h,_=account(client);r=room(client,h)
    with TestClient(app) as fresh:
        assert fresh.get('/api/rooms/'+r['id'],headers=h).json()['state']==r['state']
        assert fresh.get('/api/auth/me',headers=h).json()['id']==user['id']


def test_natural_twenty_succeeds_against_high_difficulty(client,monkeypatch):
    from server.domain import resolve_check,initial_state
    state=initial_state();c=state['characters'][0]
    state['pending_check']={'id':key(),'attribute':'strength','dc':20,'reason':'test','risk':'harm',
                            'character_id':c['id'],'modifier':-3}
    monkeypatch.setattr('server.domain.secrets.randbelow',lambda n:19)
    result=resolve_check(state)
    assert result['total']==17 and result['success'] and result['outcome']=='大成功'


def test_guest_cannot_enable_paid_models(client,monkeypatch):
    guest=client.post('/api/auth/demo').json()
    h={'Authorization':'Bearer '+guest['token']}
    r=client.get('/api/rooms/'+guest['room_id'],headers=h).json()
    monkeypatch.setattr(settings,'gemini_api_key','k')
    monkeypatch.setattr(settings,'gemini_model','m')
    monkeypatch.setattr(settings,'decision_api_key','k')
    monkeypatch.setattr(settings,'decision_model','m')
    assert client.put('/api/rooms/'+r['id']+'/settings',headers=h,json={**revise(r),'ai_mode':'live'}).status_code==403


def test_invalid_decision_json_is_explicit_error(client,monkeypatch):
    import server.ai as ai
    monkeypatch.setattr(settings,'gemini_api_key','k')
    monkeypatch.setattr(settings,'gemini_model','m')
    monkeypatch.setattr(settings,'decision_api_key','k')
    monkeypatch.setattr(settings,'decision_model','m')
    def mock(request):
        if 'generativelanguage' in request.url.host:
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'knowledge'}]}}]})
        return httpx.Response(200,json={'choices':[{'message':{'content':'not JSON'}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(ai.httpx,'AsyncClient',lambda *args,**kwargs:original(transport=httpx.MockTransport(mock),**kwargs))
    _,h,_=account(client);r=room(client,h)
    r=client.put('/api/rooms/'+r['id']+'/settings',headers=h,json={**revise(r),'ai_mode':'live'}).json()
    after=act(client,r,h).json()
    assert after['state']['awaiting_gm']
    assert after['events'][-1]['type']=='error'
    assert after['state']['characters']==r['state']['characters']


def test_cannot_delete_character_with_unfinished_hosting(client,monkeypatch):
    async def failed(*args):raise AIError('temporarily failed')
    monkeypatch.setattr(game_app,'run_gm',failed)
    _,h,_=account(client);r=room(client,h);r=act(client,r,h).json()
    c=r['state']['characters'][0]
    response=client.request('DELETE','/api/rooms/'+r['id']+'/characters/'+c['id'],headers=h,json=revise(r))
    assert response.status_code==409
