import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings, ROOT
from .db import connection, init_db, uid, dump, append_event
from .auth import current_user, user_from_token
from .schemas import Revision, Action, Chat, FreeDice, SettingsUpdate, GMNote
from .domain import character, resolve_check, ATTR_NAMES
from .ai import run_gm, AIError, model_status
from .plugin_runtime.manager import manager
from .plugin_runtime.sdk import Context
from .plugin_runtime.routes import router as extension_router, relay_signal
from .content.routes import router as content_router
from .routes.auth import router as auth_router
from .routes.rooms import router as rooms_router
from .routes.dossiers import router as dossiers_router
from .routes.history import router as history_router
from .routes.membership import router as membership_router
from .routes.guests import router as guests_router
from .network import websocket_origin_allowed
from .state import load_state
from .rules import engine_for
from .contracts.hosting import GMTrace
from .http_limits import RequestBodyLimit
from .version import HOST_VERSION

logger = logging.getLogger('ember')
from .runtime import (locks, rate_windows, hub, throttle, get_room_member, check_revision,
                      receipt, save_receipt, authorize_character, game_lock, pack_room, finish)


async def complete_gm(room_id):
    with connection() as con:
        room = con.execute('SELECT * FROM rooms WHERE id=?',(room_id,)).fetchone()
        state = load_state(room['state_json'])
    try:
        provider=manager.gm_provider(room_id)
        if not provider:
            with connection() as con:
                append_event(con,room_id,'system','AI 主持模块已关闭，本轮等待房主人工补述。',state)
            return
        provider_id,provider_item=provider
        ctx=Context(manager,provider_id,room,state,services={'gm':run_gm})
        proposed, trace = await provider_item['backend'].gm(ctx,state,room['ai_mode'])
        decision = engine_for(state).validate_decision(state, proposed)
        trace = GMTrace.model_validate(trace).model_dump(mode='json', exclude_none=True)
        trace['label'] = trace['label'] or provider_item['manifest']['name']
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
            state = load_state(room['state_json'])
            if dump(state) != room['state_json']:
                con.execute('UPDATE rooms SET state_json=? WHERE id=?', (dump(state), room['id']))
            if state.get('awaiting_gm') and not state.get('gm_error') and manager.gm_provider(room['id'],con):
                state['gm_error'] = '服务曾重启，未完成的主持可由房主重试；已提交行动和骰子结果保留。'
                append_event(con,room['id'],'error',state['gm_error'],state)
    yield

app = FastAPI(title='余烬酒馆 API',version=HOST_VERSION,lifespan=lifespan)
app.add_middleware(RequestBodyLimit)
for router in (auth_router, rooms_router, dossiers_router, history_router, extension_router, content_router, membership_router, guests_router):
    app.include_router(router)


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
    return {'ok':True,'product':'余烬酒馆','version':HOST_VERSION}


@app.get('/api/models')
def models():
    return model_status()


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
                state = load_state(room['state_json'])
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
                state = load_state(room['state_json'])
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
                if data.source_plugin:
                    plugin = manager.need(room_id, data.source_plugin, con)['manifest']
                    if 'dice:roll' not in plugin.get('capabilities', []) or 'core.dice/v1' not in plugin.get('uses', []):
                        raise HTTPException(403, '插件未声明宿主骰子能力')
                result = engine_for(load_state(room['state_json'])).roll(data.expression)
                result['request_key'] = data.request_key
                if data.source_plugin:
                    result['source_plugin'] = data.source_plugin
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
                state = load_state(room['state_json'])
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
                state = load_state(room['state_json'])
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
                state = load_state(room['state_json'])
                if not state['pending_check']:
                    raise HTTPException(422,'没有待处理检定')
                state['pending_check'] = None
                append_event(con,room_id,'system','房主取消了本次待处理检定。',state,user)
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


@app.websocket('/ws/rooms/{room_id}')
async def websocket_room(websocket:WebSocket,room_id:str):
    if not websocket_origin_allowed(websocket.headers):
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
        hub.tokens[websocket] = token
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
    except (asyncio.TimeoutError,ValueError,TypeError,AttributeError,RuntimeError):
        try:
            await websocket.close(code=4400)
        except RuntimeError:
            pass
    finally:
        hub.remove(room_id, websocket)
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
