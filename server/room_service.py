"""Room creation and invitation codes, independent of HTTP route registration."""
import secrets
from fastapi import HTTPException
from .config import settings
from .db import connection, uid, now, dump, append_event
from .domain import initial_state
from .hosting_modes import validate_hosting_mode


def invitation_code(con):
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(6))
        if not con.execute('SELECT 1 FROM rooms WHERE code=?', (code,)).fetchone():
            return code


def create_room(user, data):
    validate_hosting_mode(user,data.ai_mode)
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
