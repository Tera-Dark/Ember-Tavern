import json
import uuid
import httpx
import pytest
from server.config import settings
from test_game import account, room, revise, act


def decision_only(monkeypatch):
    monkeypatch.setattr(settings,'decision_api_key','qa-decision-secret')
    monkeypatch.setattr(settings,'decision_model','qa-model')
    monkeypatch.setattr(settings,'gemini_api_key','')
    monkeypatch.setattr(settings,'gemini_model','')


def test_single_readiness_and_mode_switch_need_no_gemini_or_provider_calls(client,monkeypatch):
    decision_only(monkeypatch)
    models=client.get('/api/models').json()
    assert models['single_ready'] and not models['live_ready']
    assert 'qa-decision-secret' not in json.dumps(models)
    _,headers,_=account(client);initial=room(client,headers)
    switched=client.put('/api/rooms/'+initial['id']+'/settings',headers=headers,json={**revise(initial),'ai_mode':'single'})
    assert switched.status_code==200,switched.text
    result=switched.json()
    assert result['ai_mode']=='single' and result['state']==initial['state']
    assert '真实单模型' in result['events'][-1]['text']
    assert result['events'][-1]['type']=='system'


@pytest.mark.parametrize('knowledge_configured',[False,True])
def test_single_calls_only_decision_and_keeps_server_validation(client,monkeypatch,knowledge_configured):
    import server.ai as ai
    decision_only(monkeypatch)
    if knowledge_configured:
        monkeypatch.setattr(settings,'gemini_api_key','unused-knowledge-secret')
        monkeypatch.setattr(settings,'gemini_model','unused-knowledge-model')
    calls=[]
    def mock(request):
        calls.append(request)
        assert 'generativelanguage' not in request.url.host
        assert request.headers['Authorization']=='Bearer qa-decision-secret'
        prompt=json.loads(request.content)['messages'][-1]['content']
        assert json.loads(prompt)['knowledge_advice']==''
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'narration':'单模型 HTTP 桩返回，数值由服务器验证。','facts':[],'check':{'attribute':'insight','dc':12,'reason':'检查证据','risk':'none'}})}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(ai.httpx,'AsyncClient',lambda *args,**kwargs:original(transport=httpx.MockTransport(mock),**kwargs))
    _,headers,_=account(client)
    response=client.post('/api/rooms',headers=headers,json={'title':'单模型契约测试','preset':'harbor','ai_mode':'single'})
    assert response.status_code==201
    result=act(client,response.json(),headers).json()
    assert len(calls)==1 and result['ai_mode']=='single'
    trace=result['events'][-1]['payload']
    assert trace['mode']=='single' and 'knowledge' not in trace
    assert result['state']['pending_check']['dc']==12
    assert 'qa-decision-secret' not in json.dumps(result) and 'unused-knowledge-secret' not in json.dumps(result)


def test_single_failure_does_not_fall_back_to_demo(client,monkeypatch):
    import server.ai as ai
    decision_only(monkeypatch)
    original=httpx.AsyncClient
    monkeypatch.setattr(ai.httpx,'AsyncClient',lambda *args,**kwargs:original(transport=httpx.MockTransport(lambda request:httpx.Response(401,json={})),**kwargs))
    _,headers,_=account(client)
    initial=client.post('/api/rooms',headers=headers,json={'title':'单模型失败保留','ai_mode':'single'}).json()
    result=act(client,initial,headers).json()
    assert result['events'][-1]['type']=='error'
    assert result['state']['gm_error'] and '401' in result['state']['gm_error']
    assert result['state']['turn']==1 and result['state']['awaiting_gm']
    assert not any(event['type']=='gm' for event in result['events'])


def test_single_missing_config_and_nonowner_cannot_enable(client,monkeypatch):
    _,headers,_=account(client);initial=room(client,headers)
    response=client.put('/api/rooms/'+initial['id']+'/settings',headers=headers,json={**revise(initial),'ai_mode':'single'})
    assert response.status_code==422
    decision_only(monkeypatch)
    _,other,_=account(client,'nonowner')
    client.post('/api/rooms/join',headers=other,json={'code':initial['code']})
    response=client.put('/api/rooms/'+initial['id']+'/settings',headers=other,json={**revise(initial),'ai_mode':'single'})
    assert response.status_code==403
