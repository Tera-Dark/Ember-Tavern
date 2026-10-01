"""Room creation and invitation codes, independent of HTTP route registration."""
import secrets
from fastapi import HTTPException
from .config import settings
from .db import connection, uid, now, dump, append_event
from .domain import initial_state


def invitation_code(con):
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(6))
        if not con.execute('SELECT 1 FROM rooms WHERE code=?', (code,)).fetchone():
            return code


def create_room(user, data):
    if data.ai_mode == 'live' and user['guest']:
        raise HTTPException(403, '体验账号不能启用付费模型，请使用正式账号')
    if data.ai_mode == 'live' and not settings.live_ready:
        raise HTTPException(422, '请先在服务端 .env 配置两个模型，再开启真实双模型模式')
    if data.ai_mode == 'demo' and not settings.enable_demo:
        raise HTTPException(403, '此部署未开启演示模式')
    room_id, timestamp = uid(), now()
    state = initial_state(data.preset,data.premise)
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        code = invitation_code(con)
        con.execute('INSERT INTO rooms VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (room_id,code,user['id'],data.title,data.ai_mode,dump(state),0,1,timestamp,timestamp))
        con.execute('INSERT INTO members VALUES (?,?,?)',(room_id,user['id'],timestamp))
        con.execute('INSERT INTO assignments VALUES (?,?,?)',(room_id,state['characters'][0]['id'],user['id']))
        append_event(con,room_id,'prologue',state['scene']['text'],state,payload={'label':'预设开场 · 非模型生成','mode':'preset'})
    return room_id
