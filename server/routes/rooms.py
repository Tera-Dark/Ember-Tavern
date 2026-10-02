import json
from fastapi import APIRouter, Depends, HTTPException
from ..auth import current_user, named_guest
from ..db import connection, now
from ..schemas import RoomCreate, JoinRoom
from ..state import load_state
from ..runtime import throttle, pack_room, finish
from ..room_service import create_room
from ..starters import starter_worlds

router = APIRouter()


@router.get('/api/starters')
def list_starters(user=Depends(current_user)):
    return starter_worlds()


@router.get('/api/rooms')
def list_rooms(user=Depends(current_user)):
    with connection() as con:
        rooms = con.execute('''SELECT r.*,u.display_name owner_name FROM rooms r
            JOIN members m ON r.id=m.room_id JOIN users u ON r.owner_id=u.id
            WHERE m.user_id=? ORDER BY r.updated_at DESC''',(user['id'],)).fetchall()
        result = []
        for r in rooms:
            state = load_state(r['state_json'])
            count = con.execute('SELECT COUNT(*) FROM members WHERE room_id=?',(r['id'],)).fetchone()[0]
            result.append({'id':r['id'],'title':r['title'],'code':r['code'],'is_owner':r['owner_id']==user['id'],
                           'owner_name':r['owner_name'],'world_title':state['world']['title'],'turn':state['turn'],
                           'members':count,'characters':len(state['characters']),'ai_mode':r['ai_mode'],'updated_at':r['updated_at']})
    return result


@router.post('/api/rooms',status_code=201)
def new_room(data:RoomCreate,user=Depends(current_user)):
    if named_guest(user):
        raise HTTPException(403, '受邀同伴不能创建房间，请联系房主')
    return pack_room(create_room(user,data),user)


@router.post('/api/rooms/join')
async def join_room(data:JoinRoom,user=Depends(current_user)):
    if named_guest(user):
        raise HTTPException(403, '受邀同伴请使用身份与专属验证密钥入座，不能通过通用邀请码绕过撤销')
    throttle(('join',user['id']),15,300)
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        room = con.execute('SELECT * FROM rooms WHERE code=?',(data.code.upper(),)).fetchone()
        if not room:
            raise HTTPException(404,'邀请码无效')
        existing = con.execute('SELECT 1 FROM members WHERE room_id=? AND user_id=?',(room['id'],user['id'])).fetchone()
        if not existing:
            access = con.execute('SELECT accepting_players FROM room_access WHERE room_id=?', (room['id'],)).fetchone()
            if access and not access[0]:
                raise HTTPException(403, '房主已暂停新成员加入')
            if con.execute('SELECT COUNT(*) FROM members WHERE room_id=?',(room['id'],)).fetchone()[0] >= 12:
                raise HTTPException(422,'首版每房间最多12位成员')
            con.execute('INSERT INTO members VALUES (?,?,?)',(room['id'],user['id'],now()))
    return await finish(room['id'],user)


@router.get('/api/rooms/{room_id}')
def read_room(room_id:str,user=Depends(current_user)):
    return pack_room(room_id,user)
