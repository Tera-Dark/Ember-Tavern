import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import hashlib
import json
import logging
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import settings, ROOT
from .db import connection, init_db, uid, now, dump, append_event, event_dict
from .auth import current_user, create_user, issue_session, user_public, user_from_token, verify_password, password_hash
from .schemas import (Register, Login, RoomCreate, JoinRoom, Revision, Action, Chat, FreeDice,
                      Rollback, Assign, CharacterInput, WorldUpdate, SettingsUpdate, GMNote)
from .domain import initial_state, character, resolve_check, free_roll, ATTR_NAMES
from .retrieval import retrieve
from .ai import run_gm, AIError, model_status
from .plugin_runtime.manager import manager
from .plugin_runtime.sdk import Context
from .plugin_runtime.routes import router as extension_router, relay_signal

logger = logging.getLogger('ember')
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

    def online(self, room_id):
        return {user_id for user_id in self.rooms[room_id].values()}

    async def signal(self,room_id,message):
        for socket in list(self.rooms[room_id]):
            try: await socket.send_json(message)
            except Exception: self.rooms[room_id].pop(socket,None)

    async def broadcast(self, room_id):
        for websocket, user_id in list(self.rooms[room_id].items()):
            try:
                with connection() as con:
                    user = con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
                if user:
                    await websocket.send_json({'type':'state','data':pack_room(room_id, dict(user))})
            except (RuntimeError,WebSocketDisconnect,HTTPException):
                self.rooms[room_id].pop(websocket, None)
            except Exception:
                self.rooms[room_id].pop(websocket, None)

hub = Hub()


def pack_room(room_id, user):
    with connection() as con:
        room = get_room_member(con,room_id,user)
        state = json.loads(room['state_json'])
        assignments = {r['character_id']:r['user_id'] for r in con.execute('SELECT * FROM assignments WHERE room_id=?',(room_id,))}
        for char in state['characters']:
            char['assigned_to'] = assignments.get(char['id'])
        online = hub.online(room_id)
        members = [{'id':r['id'],'display_name':r['display_name'],'role':'host' if r['id']==room['owner_id'] else 'player',
                    'online':r['id'] in online, 'guest':bool(r['guest'])}
                   for r in con.execute('SELECT u.* FROM users u JOIN members m ON u.id=m.user_id WHERE m.room_id=? ORDER BY m.joined_at',(room_id,))]
        events = [event_dict(r) for r in con.execute('SELECT * FROM events WHERE room_id=? AND active=1 ORDER BY seq DESC LIMIT 200',(room_id,))][::-1]
        archived_count = con.execute('SELECT COUNT(*) FROM events WHERE room_id=? AND active=0',(room_id,)).fetchone()[0]
        total = con.execute('SELECT COUNT(*) FROM events WHERE room_id=? AND active=1',(room_id,)).fetchone()[0]
    return {'id':room['id'],'title':room['title'],'code':room['code'],'owner_id':room['owner_id'],
            'is_owner':room['owner_id']==user['id'],'revision':room['revision'],'branch':room['branch'],
            'ai_mode':room['ai_mode'],'state':state,'members':members,'events':events,
            'archived_count':archived_count,'event_count':total,'busy':locks[room_id].locked(),
            'models':model_status(),'plugins':manager.catalog(room,state),'plugin_api_version':1,'updated_at':room['updated_at']}


async def finish(room_id, user):
    await hub.broadcast(room_id)
    return pack_room(room_id,user)


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
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        code = ''.join(secrets.choice(alphabet) for _ in range(6))
        while con.execute('SELECT 1 FROM rooms WHERE code=?',(code,)).fetchone():
            code = ''.join(secrets.choice(alphabet) for _ in range(6))
        con.execute('INSERT INTO rooms VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (room_id,code,user['id'],data.title,data.ai_mode,dump(state),0,1,timestamp,timestamp))
        con.execute('INSERT INTO members VALUES (?,?,?)',(room_id,user['id'],timestamp))
        con.execute('INSERT INTO assignments VALUES (?,?,?)',(room_id,state['characters'][0]['id'],user['id']))
        append_event(con,room_id,'prologue',state['scene']['text'],state,payload={'label':'预设开场 · 非模型生成','mode':'preset'})
    return room_id


async def complete_gm(room_id):
    with connection() as con:
        room = con.execute('SELECT * FROM rooms WHERE id=?',(room_id,)).fetchone()
        state = json.loads(room['state_json'])
    try:
        provider=manager.gm_provider(room_id)
        if not provider:
            with connection() as con:
                append_event(con,room_id,'system','AI 主持模块已关闭，本轮等待房主人工补述。',state)
            return
        provider_id,provider_item=provider
        ctx=Context(manager,provider_id,room,state,services={'gm':run_gm})
        decision, trace = await provider_item['backend'].gm(ctx,state,room['ai_mode'])
        state['awaiting_gm'] = False
        state['gm_error'] = None
        state['scene']['text'] = decision.narration
        if decision.scene_title:
            state['scene']['title'] = decision.scene_title
        for fact in decision.facts:
            if fact not in state['facts']:
                state['facts'].append(fact)
        state['facts'] = state['facts'][-100:]
        if decision.check:
            check = decision.check.model_dump()
            char = character(state,state['continuation']['character_id'])
            state['pending_check'] = dict(check,id=uid(),character_id=char['id'],character_name=char['name'],
                                          modifier=char['attributes'][check['attribute']])
        with connection() as con:
            append_event(con,room_id,'gm',decision.narration,state,payload=trace)
    except AIError as exc:
        state['gm_error'] = str(exc)
        with connection() as con:
            append_event(con,room_id,'error',str(exc),state,payload={'label':'模型请求失败 · 未降级为模拟回复'})
    except Exception:
        logger.exception('GM pipeline error in room %s', room_id)
        state['gm_error'] = '主持处理遇到内部错误。已提交数据保留，房主可重试或补述。'
        with connection() as con:
            append_event(con,room_id,'error',state['gm_error'],state,payload={'label':'服务器错误'})


@asynccontextmanager
async def lifespan(app):
    init_db()
    manager.refresh()
    with connection() as con:
        for room in con.execute('SELECT * FROM rooms').fetchall():
            state = json.loads(room['state_json'])
            if state.get('awaiting_gm') and not state.get('gm_error') and manager.gm_provider(room['id'],con):
                state['gm_error'] = '服务曾重启，未完成的主持可由房主重试；已提交行动和骰子结果保留。'
                append_event(con,room['id'],'error',state['gm_error'],state)
    yield

app = FastAPI(title='余烬酒馆 API',version='2.1.0-beta.1',lifespan=lifespan)
app.include_router(extension_router)


@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if 'Content-Security-Policy' not in response.headers:
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self' ws: wss:; object-src 'none'; frame-src 'self'; base-uri 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/health')
def health():
    return {'ok':True,'product':'余烬酒馆','version':'2.1.0-beta.1'}


@app.get('/api/models')
def models():
    return model_status()


@app.post('/api/auth/register',status_code=201)
def register(data:Register,request:Request):
    throttle(('register',request.client.host),10,300)
    try:
        user = create_user(data.username,data.display_name,data.password)
    except sqlite3.IntegrityError:
        raise HTTPException(409,'用户名已被使用')
    return {'token':issue_session(user),'user':user_public(user)}


@app.post('/api/auth/login')
def login(data:Login,request:Request):
    throttle(('login',request.client.host),20,300)
    with connection() as con:
        row = con.execute('SELECT * FROM users WHERE username=? AND guest=0',(data.username.lower(),)).fetchone()
    user = dict(row) if row else None
    if user is None:
        password_hash(data.password,'0'*32)
    if user is None or not verify_password(user,data.password):
        raise HTTPException(401,'用户名或密码错误')
    return {'token':issue_session(user),'user':user_public(user)}


@app.post('/api/auth/demo')
def demo(request:Request):
    if not settings.enable_demo:
        raise HTTPException(403,'此部署未开启游客试玩')
    throttle(('demo',request.client.host),10,300)
    suffix = secrets.token_hex(3)
    user = create_user('guest_'+suffix,'旅人·'+suffix[:4].upper(),secrets.token_urlsafe(24),guest=True)
    room_id = create_room(user,RoomCreate(title='雾港的第一夜'))
    return {'token':issue_session(user),'user':user_public(user),'room_id':room_id}


@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    return user_public(user)


@app.post('/api/auth/logout')
def logout(request:Request,user=Depends(current_user)):
    raw = request.headers['authorization'][7:]
    with connection() as con:
        con.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(raw.encode()).hexdigest(),))
    return {'ok':True}


@app.get('/api/rooms')
def list_rooms(user=Depends(current_user)):
    with connection() as con:
        rooms = con.execute('''SELECT r.*,u.display_name owner_name FROM rooms r
            JOIN members m ON r.id=m.room_id JOIN users u ON r.owner_id=u.id
            WHERE m.user_id=? ORDER BY r.updated_at DESC''',(user['id'],)).fetchall()
        result = []
        for r in rooms:
            state = json.loads(r['state_json'])
            count = con.execute('SELECT COUNT(*) FROM members WHERE room_id=?',(r['id'],)).fetchone()[0]
            result.append({'id':r['id'],'title':r['title'],'code':r['code'],'is_owner':r['owner_id']==user['id'],
                           'owner_name':r['owner_name'],'world_title':state['world']['title'],'turn':state['turn'],
                           'members':count,'characters':len(state['characters']),'ai_mode':r['ai_mode'],'updated_at':r['updated_at']})
    return result


@app.post('/api/rooms',status_code=201)
def new_room(data:RoomCreate,user=Depends(current_user)):
    throttle(('create',user['id']),10,3600)
    return pack_room(create_room(user,data),user)


@app.post('/api/rooms/join')
async def join_room(data:JoinRoom,user=Depends(current_user)):
    throttle(('join',user['id']),15,300)
    with connection() as con:
        room = con.execute('SELECT * FROM rooms WHERE code=?',(data.code.upper(),)).fetchone()
        if not room:
            raise HTTPException(404,'邀请码无效')
        existing = con.execute('SELECT 1 FROM members WHERE room_id=? AND user_id=?',(room['id'],user['id'])).fetchone()
        if not existing:
            if con.execute('SELECT COUNT(*) FROM members WHERE room_id=?',(room['id'],)).fetchone()[0] >= 12:
                raise HTTPException(422,'首版每房间最多12位成员')
            con.execute('INSERT INTO members VALUES (?,?,?)',(room['id'],user['id'],now()))
    return await finish(room['id'],user)


@app.get('/api/rooms/{room_id}')
def read_room(room_id:str,user=Depends(current_user)):
    return pack_room(room_id,user)


@app.post('/api/rooms/{room_id}/actions')
async def action(room_id:str,data:Action,user=Depends(current_user)):
    throttle(('action',user['id']),12,60)
    async with game_lock(room_id):
        duplicate = False
        with connection() as con:
            room = get_room_member(con,room_id,user)
            duplicate = receipt(con,room_id,user,data.request_key)
            if not duplicate:
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                char = authorize_character(con,room,user,state,data.character_id)
                if state['pending_check']:
                    raise HTTPException(409,'请先完成待处理检定，或由房主取消检定')
                if state['awaiting_gm']:
                    raise HTTPException(409,'上一轮主持未完成，请由房主重试或补述')
                if char['hp'] <= 0:
                    raise HTTPException(422,'该角色生命为0，请先由房主处理恢复或救援')
                state['turn'] += 1
                state['awaiting_gm'] = True
                state['gm_error'] = None
                state['continuation'] = {'phase':'action','text':data.text,'character_id':char['id']}
                append_event(con,room_id,'action',data.text,state,user,char['id'],{'character_name':char['name']})
                save_receipt(con,room_id,user,data.request_key)
        if not duplicate:
            await hub.broadcast(room_id)
            await complete_gm(room_id)
    return await finish(room_id,user)


@app.post('/api/rooms/{room_id}/checks/{check_id}/roll')
async def roll_check(room_id:str,check_id:str,data:Revision,user=Depends(current_user)):
    async with game_lock(room_id):
        duplicate = False
        with connection() as con:
            room = get_room_member(con,room_id,user)
            duplicate = receipt(con,room_id,user,data.request_key)
            if not duplicate:
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                if not state['pending_check'] or state['pending_check']['id'] != check_id:
                    raise HTTPException(409,'检定不存在或已完成')
                char = authorize_character(con,room,user,state,state['pending_check']['character_id'])
                result = resolve_check(state)
                state['awaiting_gm'] = True
                state['gm_error'] = None
                state['continuation'] = dict(state['continuation'],phase='roll',roll=result)
                text = f"{char['name']} 的{ATTR_NAMES[result['attribute']]}检定：{result['rolls'][0]} {result['modifier']:+d} = {result['total']}，难度 {result['dc']}，{result['outcome']}。{result['consequence']}。"
                append_event(con,room_id,'dice',text,state,user,char['id'],result)
                save_receipt(con,room_id,user,data.request_key)
        if not duplicate:
            await hub.broadcast(room_id)
            await complete_gm(room_id)
    return await finish(room_id,user)


@app.post('/api/rooms/{room_id}/dice')
async def dice(room_id:str,data:FreeDice,user=Depends(current_user)):
    throttle(('dice',user['id']),30,60)
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                result = free_roll(data.expression)
                append_event(con,room_id,'dice',f"{user['display_name']} 掷出 {result['expression']} = {result['total']}",actor=user,payload=result)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.post('/api/rooms/{room_id}/chat')
async def chat(room_id:str,data:Chat,user=Depends(current_user)):
    throttle(('chat',user['id']),30,60)
    async with game_lock(room_id):
        with connection() as con:
            get_room_member(con,room_id,user)
            if not receipt(con,room_id,user,data.request_key):
                append_event(con,room_id,'chat',data.text,actor=user,payload={'label':'场外聊天 · 不进入主持上下文'})
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.post('/api/rooms/{room_id}/gm/retry')
async def retry_gm(room_id:str,data:Revision,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            duplicate = receipt(con,room_id,user,data.request_key)
            if not duplicate:
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                if not state['awaiting_gm'] or not state['continuation']:
                    raise HTTPException(422,'没有需要重试的主持请求')
                save_receipt(con,room_id,user,data.request_key)
        if not duplicate:
            await hub.broadcast(room_id)
            await complete_gm(room_id)
    return await finish(room_id,user)


@app.post('/api/rooms/{room_id}/gm/note')
async def gm_note(room_id:str,data:GMNote,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                state['scene']['text'] = data.text
                if data.scene_title:
                    state['scene']['title'] = data.scene_title
                state['awaiting_gm'] = False
                state['gm_error'] = None
                append_event(con,room_id,'gm_note',data.text,state,user,payload={'label':'房主补述 · 人工裁定'})
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.post('/api/rooms/{room_id}/checks/cancel')
async def cancel_check(room_id:str,data:Revision,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                if not state['pending_check']:
                    raise HTTPException(422,'没有待处理检定')
                state['pending_check'] = None
                append_event(con,room_id,'system','房主取消了本次待处理检定。',state,user)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.post('/api/rooms/{room_id}/characters')
async def add_character(room_id:str,data:CharacterInput,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                if len(state['characters']) >= 12:
                    raise HTTPException(422,'首版每房间最多12个角色')
                char = data.model_dump(exclude={'expected_revision','request_key'}) | {'id':uid()}
                state['characters'].append(char)
                append_event(con,room_id,'character',f"房主创建了角色「{char['name']}」。",state,user,char['id'])
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.put('/api/rooms/{room_id}/characters/{character_id}')
async def update_character(room_id:str,character_id:str,data:CharacterInput,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                char = character(state,character_id)
                if state['pending_check'] and state['pending_check']['character_id'] == character_id:
                    raise HTTPException(409,'该角色正在等待检定，先完成或取消检定再修改属性')
                char.update(data.model_dump(exclude={'expected_revision','request_key'}))
                append_event(con,room_id,'character',f"房主更新了「{char['name']}」的角色记录。",state,user,character_id)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.delete('/api/rooms/{room_id}/characters/{character_id}')
async def delete_character(room_id:str,character_id:str,data:Revision,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                char = character(state,character_id)
                if len(state['characters']) <= 1:
                    raise HTTPException(422,'请至少保留一个角色')
                if (state['pending_check'] and state['pending_check']['character_id']==character_id) or (state['awaiting_gm'] and state['continuation'] and state['continuation']['character_id']==character_id):
                    raise HTTPException(409,'请先完成该角色的主持或检定，再移除角色')
                state['characters'] = [c for c in state['characters'] if c['id']!=character_id]
                con.execute('DELETE FROM assignments WHERE room_id=? AND character_id=?',(room_id,character_id))
                append_event(con,room_id,'character',f"房主移除了角色「{char['name']}」。",state,user,character_id)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.post('/api/rooms/{room_id}/characters/{character_id}/assign')
async def assign_character(room_id:str,character_id:str,data:Assign,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                char = character(state,character_id)
                name = '未分配'
                if data.user_id:
                    row = con.execute('SELECT u.display_name FROM users u JOIN members m ON u.id=m.user_id WHERE m.room_id=? AND u.id=?',(room_id,data.user_id)).fetchone()
                    if not row:
                        raise HTTPException(422,'只能分配给当前房间成员')
                    name = row['display_name']
                    con.execute('DELETE FROM assignments WHERE room_id=? AND user_id=?',(room_id,data.user_id))
                con.execute('DELETE FROM assignments WHERE room_id=? AND character_id=?',(room_id,character_id))
                if data.user_id:
                    con.execute('INSERT INTO assignments VALUES (?,?,?)',(room_id,character_id,data.user_id))
                append_event(con,room_id,'system',f"「{char['name']}」的操控者已设为：{name}。",state,user)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.put('/api/rooms/{room_id}/world')
async def update_world(room_id:str,data:WorldUpdate,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = json.loads(room['state_json'])
                lore = [item.model_dump() | {'id':item.id or uid()} for item in data.lore]
                if len({x['id'] for x in lore}) != len(lore):
                    raise HTTPException(422,'世界书条目ID不能重复')
                state['world'] = {'title':data.title,'premise':data.premise,'tone':data.tone,'lore':lore}
                append_event(con,room_id,'world','房主更新了世界设定与世界书。',state,user)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.put('/api/rooms/{room_id}/settings')
async def update_settings(room_id:str,data:SettingsUpdate,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                if data.ai_mode=='live' and user['guest']:
                    raise HTTPException(403,'体验账号不能启用付费模型，请使用正式账号')
                if data.ai_mode=='live' and not settings.live_ready:
                    raise HTTPException(422,'双模型尚未配置完整，请先设置服务端 .env')
                if data.ai_mode=='demo' and not settings.enable_demo:
                    raise HTTPException(403,'此部署未开启演示模式')
                con.execute('UPDATE rooms SET ai_mode=? WHERE id=?',(data.ai_mode,room_id))
                append_event(con,room_id,'system',f"主持模式切换为{'真实双模型' if data.ai_mode=='live' else '演示规则脚本'}。",actor=user)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.post('/api/rooms/{room_id}/rollback')
async def rollback(room_id:str,data:Rollback,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                target = con.execute('SELECT * FROM events WHERE room_id=? AND id=? AND active=1',(room_id,data.target_event_id)).fetchone()
                if not target:
                    raise HTTPException(422,'只能回到当前时间线中的历史节点')
                archived = con.execute('SELECT COUNT(*) FROM events WHERE room_id=? AND active=1 AND seq>?',(room_id,target['seq'])).fetchone()[0]
                if archived == 0:
                    raise HTTPException(422,'该节点已经是最新记录，无需回档')
                state = json.loads(target['snapshot_json'])
                con.execute('UPDATE events SET active=0 WHERE room_id=? AND active=1 AND seq>?',(room_id,target['seq']))
                con.execute('UPDATE rooms SET branch=branch+1 WHERE id=?',(room_id,))
                append_event(con,room_id,'rewind',f"回到事件 #{target['seq']} 之后的状态。{archived} 条后续记录已封存。原因：{data.reason}",
                             state,user,payload={'target_event_id':target['id'],'target_seq':target['seq'],'archived':archived,'reason':data.reason})
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@app.get('/api/rooms/{room_id}/context')
def context_search(room_id:str,q:str=Query(default='',max_length=200),user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con,room_id,user)
        state = json.loads(room['state_json'])
    return {'query':q,'method':'中文双字词 / 英文词项匹配（非向量检索）','results':retrieve(room_id,state,q,20)}


@app.get('/api/rooms/{room_id}/events')
def events(room_id:str,archived:bool=False,before_seq:int|None=None,user=Depends(current_user)):
    with connection() as con:
        get_room_member(con,room_id,user,archived)
        rows = con.execute('SELECT * FROM events WHERE room_id=? AND active=? AND seq<? ORDER BY seq DESC LIMIT 200',
                           (room_id,0 if archived else 1,before_seq or 2**62)).fetchall()
    return [event_dict(row) for row in rows]


@app.get('/api/rooms/{room_id}/export')
def export(room_id:str,user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con,room_id,user,True)
        rows = con.execute('SELECT * FROM events WHERE room_id=? ORDER BY seq',(room_id,)).fetchall()
        all_events = [event_dict(r) | {'snapshot':json.loads(r['snapshot_json'])} for r in rows]
    data = {'format':'ember-tavern/v1','exported_at':now(),'room':pack_room(room_id,user),'all_events':all_events}
    return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="ember-session-{room_id[:8]}.json"'})


@app.websocket('/ws/rooms/{room_id}')
async def websocket_room(websocket:WebSocket,room_id:str):
    origin = websocket.headers.get('origin','')
    if origin:
        host = urlparse(origin).netloc
        accepted_hosts = {websocket.headers.get('host',''),websocket.headers.get('x-forwarded-host','')}
        if host not in accepted_hosts and not host.endswith('.e2b.app'):
            await websocket.close(code=4403)
            return
    await websocket.accept()
    try:
        auth = await asyncio.wait_for(websocket.receive_json(),timeout=8)
        token = auth.get('token','') if auth.get('type')=='auth' else ''
        user = user_from_token(token)
        if not user:
            await websocket.close(code=4401)
            return
        with connection() as con:
            get_room_member(con,room_id,user)
        hub.rooms[room_id][websocket] = user['id']
        await hub.broadcast(room_id)
        while True:
            message = await websocket.receive_json()
            if not user_from_token(token):
                await websocket.close(code=4401)
                break
            if message.get('type')=='plugin_signal':
                try: await relay_signal(room_id,user,message)
                except HTTPException as exc: await websocket.send_json({'type':'plugin_error','message':exc.detail})
                continue
            if message.get('type')=='ping':
                await websocket.send_json({'type':'pong'})
    except WebSocketDisconnect:
        pass
    except HTTPException:
        try:
            await websocket.close(code=4403)
        except RuntimeError:
            pass
    except (asyncio.TimeoutError,ValueError,TypeError,AttributeError):
        try:
            await websocket.close(code=4400)
        except RuntimeError:
            pass
    finally:
        hub.rooms[room_id].pop(websocket,None)
        await hub.broadcast(room_id)


STATIC = ROOT / 'static'
if STATIC.exists() and (STATIC / 'assets').exists():
    app.mount('/assets',StaticFiles(directory=STATIC / 'assets'),name='assets')

@app.get('/{path:path}',include_in_schema=False)
def frontend(path:str):
    if path.startswith(('api/','ws/')):
        raise HTTPException(404,'接口不存在')
    candidate = (STATIC / path).resolve()
    if candidate.is_relative_to(STATIC.resolve()) and candidate.is_file():
        return FileResponse(candidate)
    index = STATIC / 'index.html'
    if not index.exists():
        return JSONResponse({'message':'前端尚未构建，请在 web 目录执行 npm install && npm run build'},status_code=503)
    return FileResponse(index)
