import hashlib
import uuid
import pytest
from fastapi.websockets import WebSocketDisconnect
from server.db import connection


def host(client):
    data=client.post('/api/auth/register',json={'username':'host_'+uuid.uuid4().hex[:8],'display_name':'房主','password':'qa-guest-password'}).json()
    headers={'X-Ember-Session':data['token']}
    room=client.post('/api/rooms',headers=headers,json={'title':'局域网桌'}).json()
    return headers,room


def issue(client,headers,room,name='小王'):
    return client.post(f"/api/rooms/{room['id']}/guest-access",headers=headers,json={'identity':name,'expected_revision':room['revision'],'request_key':uuid.uuid4().hex})


def login(client,key,name='小王'):
    return client.post('/api/auth/guest-join',json={'identity':name,'verification_key':key})


def test_named_guest_reuses_identity_no_registration_or_ownership(client):
    h,r=host(client); minted=issue(client,h,r).json();key=minted['invite']['verification_key']
    first=login(client,key).json();second=login(client,key).json()
    assert first['user']['guest'] and first['user']['id']==second['user']['id']
    gh={'X-Ember-Session':first['token']}
    view=client.get(f"/api/rooms/{r['id']}",headers=gh).json()
    assert not view['is_owner'] and len(view['members'])==2
    assert client.get(f"/api/rooms/{r['id']}/guest-access",headers=gh).status_code==403
    assert client.post(f"/api/rooms/{r['id']}/guest-access",headers=gh,json={'identity':'another','expected_revision':view['revision'],'request_key':uuid.uuid4().hex}).status_code==403
    listed=client.get(f"/api/rooms/{r['id']}/guest-access",headers=h).json()
    assert key not in str(listed) and key not in str(view)
    with connection() as con:
        row=con.execute('SELECT * FROM guest_invites').fetchone()
        assert row['key_hash']==hashlib.sha256(key.encode()).hexdigest()
        assert key not in str(dict(row))


def test_guest_wrong_name_key_rotation_and_idempotent_no_secret_replay(client):
    h,r=host(client);body={'identity':'小王','expected_revision':r['revision'],'request_key':uuid.uuid4().hex};url=f"/api/rooms/{r['id']}/guest-access"
    minted=client.post(url,headers=h,json=body).json();key=minted['invite']['verification_key']
    assert login(client,key,'冒充名字').status_code==401
    assert login(client,'ET-'+'x'*32).status_code==401
    repeated=client.post(url,headers=h,json=body).json();assert repeated['invite'] is None and key not in str(repeated)
    rotated=issue(client,h,minted['room']).json();assert login(client,key).status_code==401
    assert login(client,rotated['invite']['verification_key']).status_code==200


def test_guest_pause_new_seats_but_allow_existing_reconnect(client):
    h,r=host(client);a=issue(client,h,r).json();key=a['invite']['verification_key']
    first=login(client,key).json();b=issue(client,h,a['room'],'小李').json()
    paused=client.post(f"/api/rooms/{r['id']}/invitation",headers=h,json={'expected_revision':b['room']['revision'],'request_key':uuid.uuid4().hex,'accepting_players':False}).json()
    assert login(client,b['invite']['verification_key'],'小李').status_code==403
    assert login(client,key).json()['user']['id']==first['user']['id']


def test_guest_revocation_disconnect_and_cannot_return(client):
    h,r=host(client);a=issue(client,h,r).json();key=a['invite']['verification_key'];g=login(client,key).json()
    with client.websocket_connect(f"/ws/rooms/{r['id']}") as socket:
        socket.send_json({'type':'auth','token':g['token']});socket.receive_json()
        view=client.get(f"/api/rooms/{r['id']}",headers=h).json()
        result=client.post(f"/api/rooms/{r['id']}/guest-access/{a['invite']['id']}/revoke",headers=h,json={'expected_revision':view['revision'],'request_key':uuid.uuid4().hex})
        assert result.status_code==200
        with pytest.raises(WebSocketDisconnect) as exc:socket.receive_json()
        assert exc.value.code==4403
    assert login(client,key).status_code==401


def test_remove_guest_also_revokes_key(client):
    h,r=host(client);a=issue(client,h,r).json();key=a['invite']['verification_key'];g=login(client,key).json()
    view=client.get(f"/api/rooms/{r['id']}",headers=h).json()
    assert client.post(f"/api/rooms/{r['id']}/members/{g['user']['id']}/remove",headers=h,json={'expected_revision':view['revision'],'request_key':uuid.uuid4().hex}).status_code==200
    assert login(client,key).status_code==401


def test_guest_input_bounds_stale_revision_and_control_characters(client):
    h,r=host(client)
    assert issue(client,h,r,'房主').status_code==422
    assert issue(client,h,r,'bad\nname').status_code==422
    a=issue(client,h,r).json()
    assert issue(client,h,r,'stale').status_code==409
    assert client.post('/api/auth/guest-join',json={'identity':'小王','verification_key':a['invite']['verification_key'],'owner':True}).status_code==422
