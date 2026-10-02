"""Atomic room creation, shared by legacy starters and data-only compositions."""
import hashlib
import json
import secrets
from fastapi import HTTPException
from .db import connection, uid, now, dump, append_event
from .domain import initial_state
from .hosting_modes import validate_hosting_mode


def invitation_code(con):
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(6))
        if not con.execute('SELECT 1 FROM rooms WHERE code=?', (code,)).fetchone():
            return code


def creation_hash(kind,data):
    value={'kind':kind,'request':data.model_dump(mode='json',exclude={'request_key'})}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def create_transaction(user,title,mode,request_key,payload_hash,build,host_plays=True):
    """A retry returns its original room; changing an intent with the same key
    is a conflict. All SQL rows, module flags, locks and prologue commit together.
    No claim is made about side effects of already trusted Python hook code.
    """
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        if request_key:
            prior=con.execute('SELECT * FROM room_creation_receipts WHERE user_id=? AND request_key=?',(user['id'],request_key)).fetchone()
            if prior:
                if prior['payload_hash']!=payload_hash:
                    raise HTTPException(409,'开桌请求标识已用于不同配置；请刷新，不会另建或覆盖房间')
                return prior['room_id']
        validate_hosting_mode(user,mode)
        from .runtime import throttle
        throttle(('room-create',user['id']),10,3600)
        state,flags,package_hash=build(con)
        room_id,timestamp=uid(),now()
        code=invitation_code(con)
        con.execute('INSERT INTO rooms VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (room_id,code,user['id'],title,mode,dump(state),0,1,timestamp,timestamp))
        con.execute('INSERT INTO members VALUES (?,?,?)',(room_id,user['id'],timestamp))
        if host_plays:
            con.execute('INSERT INTO assignments VALUES (?,?,?)',(room_id,state['characters'][0]['id'],user['id']))
        if flags is not None:
            con.execute('INSERT INTO room_plugins VALUES (?,?)',(room_id,dump(flags)))
        if package_hash:
            con.execute('INSERT INTO room_preset_locks VALUES (?,?)',(room_id,package_hash))
        append_event(con,room_id,'prologue',state['scene']['text'],state,
                     payload={'label':'玩法预设开场 · 非模型生成' if package_hash else '预设开场 · 非模型生成','mode':'preset'})
        if request_key:
            con.execute('INSERT INTO room_creation_receipts VALUES (?,?,?,?,?)',(user['id'],request_key,payload_hash,room_id,timestamp))
        return room_id


def create_room(user,data):
    return create_transaction(user,data.title,data.ai_mode,data.request_key,creation_hash('starter',data),
                              lambda con:(initial_state(data.preset,data.premise),None,None))


def create_preset_room(user,data):
    from .presets.library import get_package,authorize_package
    from .presets.composer import compose
    from .plugin_runtime.manager import manager
    def build(con):
        authorize_package(con,data.package_hash,user)
        package=get_package(con,data.package_hash)
        state,flags=compose(package,manager)
        return state,flags,package.package_hash
    return create_transaction(user,data.title,data.ai_mode,data.request_key,creation_hash('preset',data),build,data.host_plays)
