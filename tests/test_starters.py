from server.starters import starter_worlds


def registered(client, name='m0_host'):
    response=client.post('/api/auth/register',json={'username':name,'password':'demo-test-password','display_name':'开桌房主'})
    assert response.status_code==201,response.text
    return {'X-Ember-Session':response.json()['token']}


def test_starter_metadata_requires_session_and_contains_no_world_secrets(client):
    assert client.get('/api/starters').status_code==401
    headers=registered(client)
    response=client.get('/api/starters',headers=headers)
    assert response.status_code==200
    worlds=response.json()
    assert {entry['id'] for entry in worlds}=={'harbor','frontier'}
    for world in worlds:
        assert world['ai_mode']=='demo' and world['external_calls'] is False
        assert world['rule_system']=='ember-light/v1'
        assert 'lore' not in world and 'gm_notes' not in world and 'api_key' not in world
        assert '非完整玩法包' in world['label']


def test_each_starter_creates_independent_demo_room_with_ready_characters(client):
    headers=registered(client)
    rooms=[]
    for starter in starter_worlds():
        response=client.post('/api/rooms',headers=headers,json={'title':starter['name'],'preset':starter['id'],'ai_mode':'demo'})
        assert response.status_code==201,response.text
        room=response.json();rooms.append(room)
        assert room['state']['world']['title']==starter['world_title']
        assert room['ai_mode']=='demo' and room['state']['turn']==0
        assert len(room['state']['characters'])==2
        assert room['state']['characters'][0]['assigned_to']==room['owner_id']
    assert rooms[0]['id']!=rooms[1]['id']
    assert rooms[0]['state']['characters'][0]['id']!=rooms[1]['state']['characters'][0]['id']
    assert len(client.get('/api/rooms',headers=headers).json())==2
