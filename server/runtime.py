"""Room authority, permissions and realtime transport. No route imports or feature UI."""
import asyncio
import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import HTTPException, WebSocketDisconnect
from .db import connection, now, event_dict
from .auth import user_from_token
from .domain import character
from .ai import model_status
from .plugin_runtime.manager import manager
from .projection import project_state, project_event
from .state import load_state

locks = defaultdict(asyncio.Lock)
rate_windows = defaultdict(deque)


def throttle(key, maximum=60, seconds=60):
    window = rate_windows[key]
    current = time.monotonic()
    while window and window[0] <= current - seconds:
        window.popleft()
    if len(window) >= maximum:
        raise HTTPException(429, '操作过于频繁，请稍后重试')
    window.append(current)


def get_room_member(con, room_id, user, owner_only=False):
    room = con.execute('SELECT * FROM rooms WHERE id=?', (room_id,)).fetchone()
    if not room:
        raise HTTPException(404, '房间不存在')
    member = con.execute('SELECT 1 FROM members WHERE room_id=? AND user_id=?', (room_id, user['id'])).fetchone()
    if not member:
        raise HTTPException(403, '你不是该房间成员')
    if owner_only and room['owner_id'] != user['id']:
        raise HTTPException(403, '只有房主可以执行此操作')
    return room


def check_revision(room, expected):
    if room['revision'] != expected:
        raise HTTPException(409, '房间状态已更新，请同步后重试；本次操作未提交')


def receipt(con, room_id, user, key):
    return bool(con.execute('SELECT 1 FROM receipts WHERE room_id=? AND user_id=? AND request_key=?', (room_id,user['id'],key)).fetchone())


def save_receipt(con, room_id, user, key):
    con.execute('INSERT INTO receipts VALUES (?,?,?,?)', (room_id,user['id'],key,now()))


def authorize_character(con, room, user, state, character_id):
    char = character(state, character_id)
    if room['owner_id'] != user['id']:
        assigned = con.execute('SELECT 1 FROM assignments WHERE room_id=? AND character_id=? AND user_id=?',
                               (room['id'],character_id,user['id'])).fetchone()
        if not assigned:
            raise HTTPException(403, '你只能操控房主分配给你的角色')
    return char


@asynccontextmanager
async def game_lock(room_id):
    lock = locks[room_id]
    if lock.locked():
        raise HTTPException(409, '主持正在处理上一轮，请等它完成后再操作')
    async with lock:
        yield


class Hub:
    def __init__(self):
        self.rooms = defaultdict(dict)
        self.tokens = {}

    def remove(self, room_id, socket):
        self.rooms[room_id].pop(socket, None)
        self.tokens.pop(socket, None)

    def online(self, room_id):
        return set(self.rooms[room_id].values())

    async def close(self, room_id, socket, code=4403):
        self.remove(room_id, socket)
        try:
            await socket.close(code=code)
        except (RuntimeError, WebSocketDisconnect):
            pass

    async def disconnect_user(self, room_id, user_id):
        for socket, member in list(self.rooms[room_id].items()):
            if member == user_id:
                await self.close(room_id, socket)

    async def disconnect_session(self, token):
        affected = []
        for room_id, sockets in list(self.rooms.items()):
            for socket in list(sockets):
                if self.tokens.get(socket) == token:
                    await self.close(room_id, socket, 4401)
                    affected.append(room_id)
        for room_id in set(affected):
            await self.broadcast(room_id)

    def authorized_user(self, room_id, socket):
        user = user_from_token(self.tokens.get(socket))
        if not user:
            raise HTTPException(401, '登录已失效')
        with connection() as con:
            get_room_member(con, room_id, user)
        return user

    async def signal(self, room_id, message):
        for socket in list(self.rooms[room_id]):
            try:
                self.authorized_user(room_id, socket)
                await socket.send_json(message)
            except HTTPException as exc:
                await self.close(room_id, socket, 4401 if exc.status_code == 401 else 4403)
            except Exception:
                self.remove(room_id, socket)

    async def broadcast(self, room_id):
        for socket in list(self.rooms[room_id]):
            try:
                user = self.authorized_user(room_id, socket)
                await socket.send_json({'type': 'state', 'data': pack_room(room_id, user)})
            except HTTPException as exc:
                await self.close(room_id, socket, 4401 if exc.status_code == 401 else 4403)
            except Exception:
                self.remove(room_id, socket)

hub = Hub()


def pack_room(room_id, user):
    with connection() as con:
        room = get_room_member(con,room_id,user)
        state = load_state(room['state_json'])
        assignments = {r['character_id']:r['user_id'] for r in con.execute('SELECT * FROM assignments WHERE room_id=?',(room_id,))}
        for char in state['characters']:
            char['assigned_to'] = assignments.get(char['id'])
        online = hub.online(room_id)
        members = [{'id':r['id'],'display_name':r['display_name'],'role':'host' if r['id']==room['owner_id'] else 'player',
                    'online':r['id'] in online, 'guest':bool(r['guest'])}
                   for r in con.execute('SELECT u.* FROM users u JOIN members m ON u.id=m.user_id WHERE m.room_id=? ORDER BY m.joined_at',(room_id,))]
        include_gm = room['owner_id'] == user['id']
        events = [project_event(event_dict(r), include_gm) for r in con.execute('SELECT * FROM events WHERE room_id=? AND active=1 ORDER BY seq DESC LIMIT 200',(room_id,))][::-1]
        archived_count = con.execute('SELECT COUNT(*) FROM events WHERE room_id=? AND active=0',(room_id,)).fetchone()[0]
        total = con.execute('SELECT COUNT(*) FROM events WHERE room_id=? AND active=1',(room_id,)).fetchone()[0]
        catalog = manager.catalog(room, state, con)
        view = project_state(state, include_gm)
        if not include_gm:
            for pid, namespace in view.get('_plugins', {}).items():
                namespace['data'] = manager.public_data(room, state, pid, user, con)
        access_row = con.execute('SELECT accepting_players FROM room_access WHERE room_id=?', (room_id,)).fetchone()
        access = {'accepting_players': bool(access_row[0]) if access_row else True, 'member_limit': 12}
    return {'id':room['id'],'title':room['title'],'code':room['code'],'owner_id':room['owner_id'],
            'is_owner':room['owner_id']==user['id'],'revision':room['revision'],'branch':room['branch'],
            'ai_mode':room['ai_mode'],'state':view,'access':access,'members':members,'events':events,
            'archived_count':archived_count,'event_count':total,'busy':locks[room_id].locked(),
            'models':model_status(),'plugins':catalog,'plugin_api_version':1,'updated_at':room['updated_at']}


async def finish(room_id, user):
    await hub.broadcast(room_id)
    return pack_room(room_id,user)
