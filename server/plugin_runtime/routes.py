import asyncio
import hashlib
import json
from collections import defaultdict
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import FileResponse,HTMLResponse
from pydantic import Field
from ..auth import current_user
from ..config import ROOT,settings
from ..db import connection,dump,append_event
from ..schemas import Revision,StrictModel
from .manager import manager
from .sdk import Context,Result

router=APIRouter()
plugin_locks=defaultdict(asyncio.Lock)

class Toggle(Revision):
    enabled:bool
class Invoke(StrictModel):
    expected_plugin_revision:int=Field(ge=0)
    expected_branch:int=Field(ge=1)
    request_key:str=Field(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
    payload:dict=Field(default_factory=dict)
    via:str|None=None

from .. import runtime
from ..state import load_state

def authorized_via(room_id,via,target,operation,signal=False,con=None):
    item=manager.need(room_id,target,con)
    origin=manager.need(room_id,via,con)
    declared=item['manifest'].get('signals' if signal else 'actions',[])
    if operation not in declared:raise HTTPException(404,'插件未声明此操作')
    kind='signal' if signal else 'invoke'
    caps=origin['manifest'].get('capabilities',[])
    resource_grant=any(f'{kind}-resource:{res}.{operation}' in caps and res in origin['manifest'].get('uses',[]) for res in item['manifest'].get('provides',[]))
    if via!=target and f'{kind}:{target}.{operation}' not in caps and not resource_grant:
        raise HTTPException(403,'调用者插件没有这项跨插件能力')
    return item

@router.get('/api/plugins')
def installed(user=Depends(current_user)):
    manager.refresh()
    return {'api_version':1,'plugins':[dict(x['manifest'],blocked=x['blocked'],builtin=x['builtin'],hash=x['hash']) for x in manager.items.values()],
            'community_url':settings.plugin_community_url or None}

@router.get('/api/plugins/guide')
def guide(user=Depends(current_user)):
    path=ROOT/'docs/PLUGIN_SDK.md'
    return {'text':path.read_text() if path.exists() else '插件 SDK 文档正在整理。','community_url':settings.plugin_community_url or None}

@router.get('/api/plugins/{plugin_id}/ui')
def ui(plugin_id:str,user=Depends(current_user)):
    manager.refresh();item=manager.items.get(plugin_id)
    if not item or item['blocked'] or not item['manifest'].get('frontend'):raise HTTPException(404,'界面插件不可用')
    source=(item['folder']/'ui.js').read_text()
    if len(source.encode())>524288:raise HTTPException(422,'前端插件包超过512 KiB')
    return {'source':source,'manifest':item['manifest'],'hash':item['hash']}

@router.get('/plugin-frame/{plugin_id}')
def frame(plugin_id:str,bridge:str=''):
    # Public code shell ONLY. Authentication/state/keys are never placed in the document.
    import secrets,re
    manager.refresh();item=manager.items.get(plugin_id)
    if not item or item['blocked'] or not item['manifest'].get('frontend'):raise HTTPException(404,'插件界面不可用')
    channel=bridge if re.fullmatch(r'[a-f0-9]{32}',bridge) else secrets.token_hex(16)
    nonce=secrets.token_urlsafe(24)
    sdk=(ROOT/'server/plugin_runtime/bridge.js').read_text()
    source=(item['folder']/'ui.js').read_text()
    if len(source.encode())>524288:raise HTTPException(422,'前端插件包过大')
    source=re.sub(r'</script',lambda m:'<'+chr(92)+m[0][1:],source,flags=re.I)
    css="*{box-sizing:border-box}body{margin:0;padding:14px;background:var(--bg,#141a17);color:var(--text,#e7e9df);font:13px -apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif}button,input,select,textarea{font:inherit;color:inherit}button{cursor:pointer}button:disabled{opacity:.4;cursor:not-allowed}input,select,textarea{background:var(--surface,#1a211d);border:1px solid var(--border,#303a32);border-radius:6px;padding:9px;outline:none}button{border:1px solid var(--border,#303a32);border-radius:6px;background:var(--surface,#1a211d);padding:9px 12px}button:hover:not(:disabled){border-color:var(--gold,#d5b37b)}button.primary{background:var(--gold,#d5b37b);color:#20271e;border-color:var(--gold,#d5b37b)}small,.muted{color:var(--muted,#96a093)}h2,h3,p{margin:0}.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.row>label{display:flex;align-items:center;gap:6px;font-size:11px;max-width:100%}.row>label>select,.row>label>input{min-width:0}.badge{font-size:10px;color:var(--gold,#d5b37b);border:1px solid var(--border,#303a32);border-radius:4px;padding:4px 7px}.card{background:var(--surface,#1a211d);border:1px solid var(--border,#303a32);border-radius:8px;padding:15px}.note{font-size:11px;line-height:1.8;color:var(--muted,#96a093);margin-top:10px}::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-thumb{background:var(--border,#303a32);border-radius:4px}button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}"
    markup=f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{css}</style></head><body><div id="plugin-root"></div><script nonce="{nonce}">window.__EMBER_CHANNEL={json.dumps(channel)};</script><script nonce="{nonce}">{sdk}</script><script nonce="{nonce}">{source}</script></body></html>'
    return HTMLResponse(markup,headers={'Content-Security-Policy':f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; img-src data:; media-src data: blob:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'",'Cache-Control':'no-store'})

@router.get('/api/rooms/{room_id}/extensions/{plugin_id}/context')
def context(room_id:str,plugin_id:str,user=Depends(current_user)):
    with connection() as con:
        room=runtime.get_room_member(con,room_id,user);state=load_state(room['state_json'])
        return manager.public_context(room,state,user,plugin_id,con)

@router.post('/api/rooms/{room_id}/extensions/{plugin_id}/toggle')
async def toggle(room_id:str,plugin_id:str,data:Toggle,user=Depends(current_user)):
    manager.refresh()
    async with runtime.game_lock(room_id):
        with connection() as con:
            room=runtime.get_room_member(con,room_id,user,True)
            if not runtime.receipt(con,room_id,user,data.request_key):
                runtime.check_revision(room,data.expected_revision)
                flags,changed=manager.toggle_plan(room_id,plugin_id,data.enabled,con)
                con.execute('INSERT INTO room_plugins(room_id,flags_json) VALUES (?,?) ON CONFLICT(room_id) DO UPDATE SET flags_json=excluded.flags_json',(room_id,dump(flags)))
                state=load_state(room['state_json'])
                if data.enabled:
                    for pid in changed:manager.initialize(room,state,pid,user,con)
                names='、'.join(manager.items[x]['manifest']['name'] for x in changed) or manager.items[plugin_id]['manifest']['name']
                append_event(con,room_id,'extension',('开启' if data.enabled else '关闭')+'模块：'+names+'。已有数据保留。',state,user,
                             payload={'plugin_id':plugin_id,'action':'toggle','changed':changed,'enabled':data.enabled})
                runtime.save_receipt(con,room_id,user,data.request_key)
    return await runtime.finish(room_id,user)

@router.post('/api/rooms/{room_id}/extensions/{plugin_id}/actions/{action}')
async def invoke(room_id:str,plugin_id:str,action:str,data:Invoke,user=Depends(current_user)):
    runtime.throttle(('plugin-action',user['id']),60,60)
    if len(dump(data.payload).encode())>32768:raise HTTPException(422,'插件请求超过32 KiB')
    lock=plugin_locks[(room_id,plugin_id)]
    if lock.locked():raise HTTPException(409,'这个插件正在处理请求，其他模块仍可使用')
    async with lock:
        with connection() as con:
            room=runtime.get_room_member(con,room_id,user)
            if runtime.receipt(con,room_id,user,data.request_key):
                return {'room':runtime.pack_room(room_id,user),'output':{},'duplicate':True}
            item=authorized_via(room_id,data.via or plugin_id,plugin_id,action,con=con)
            base=load_state(room['state_json'])
            if room['branch']!=data.expected_branch or manager.namespace(base,plugin_id)['revision']!=data.expected_plugin_revision:
                raise HTTPException(409,'插件状态或时间线已更新，请同步后重试')
        simulated=json.loads(dump(base));patches={};versions={};root_output={};message='插件状态已更新。'
        pending=[(plugin_id,action,data.payload,data.via or plugin_id)];steps=0;core_revision=None
        while pending:
            steps+=1
            if steps>16:raise HTTPException(422,'跨插件调用链过长或形成循环')
            pid,name,payload,via=pending.pop(0)
            if len(patches)>8:raise HTTPException(422,'跨插件调用超过限制')
            extension=authorized_via(room_id,via,pid,name)['backend']
            if not extension:raise HTTPException(404,'此界面插件没有后端操作')
            versions.setdefault(pid,manager.namespace(base,pid)['revision'])
            for dep in manager.items[pid]['manifest'].get('requires',[]):versions.setdefault(dep,manager.namespace(base,dep)['revision'])
            ctx=Context(manager,pid,room,simulated,user)
            try: result=await extension.action(ctx,name,payload,manager.namespace(simulated,pid)['data'])
            except (ValueError,KeyError,TypeError): raise HTTPException(422,'插件请求格式不符合规范')
            if not isinstance(result,Result):raise HTTPException(500,'插件未返回 SDK Result')
            if pid==plugin_id:root_output=result.output;message=result.message or message
            for provider in ctx.reads:
                if provider=='@core':core_revision=room['revision']
                else:versions.setdefault(provider,manager.namespace(base,provider)['revision'])
            if result.data is not None:
                if pid not in patches and len(patches)>=8:raise HTTPException(422,'一次最多写入8个插件namespace')
                manager.write(simulated,pid,result.data);patches[pid]=result.data
            for call in result.calls:
                authorized_via(room_id,pid,call['plugin'],call['action'])
                pending.append((call['plugin'],call['action'],call.get('payload',{}),pid))
        with connection() as con:
            latest=runtime.get_room_member(con,room_id,user);state=load_state(latest['state_json'])
            manager.need(room_id,plugin_id,con)
            if (core_revision is not None and latest['revision']!=core_revision) or latest['branch']!=data.expected_branch or any(manager.namespace(state,pid)['revision']!=v for pid,v in versions.items()):
                raise HTTPException(409,'生成期间依赖或时间线发生变化；结果未应用，请重试')
            for dependency in versions:manager.need(room_id,dependency,con)
            for pid,patch in patches.items():manager.need(room_id,pid,con);manager.write(state,pid,patch)
            append_event(con,room_id,'extension',message[:500],state,user,payload={'plugin_id':plugin_id,'action':action})
            runtime.save_receipt(con,room_id,user,data.request_key)
    return {'room':await runtime.finish(room_id,user),'output':root_output}

@router.get('/api/rooms/{room_id}/assets/{plugin_id}/{asset_id}')
def asset(room_id:str,plugin_id:str,asset_id:str,user=Depends(current_user)):
    if not __import__('re').fullmatch(r'[a-f0-9]{32}',asset_id):raise HTTPException(404,'素材不存在')
    with connection() as con:
        room=runtime.get_room_member(con,room_id,user);manager.need(room_id,plugin_id,con)
        state=load_state(room['state_json']);assets=manager.namespace(state,plugin_id)['data'].get('_assets',[])
        metadata=next((x for x in assets if x['id']==asset_id),None)
        if not metadata:raise HTTPException(404,'素材不属于当前有效时间线')
    path=settings.data_dir/'assets'/room_id/plugin_id/(asset_id+'.bin')
    if not path.exists():raise HTTPException(404,'素材文件不存在，请检查持久数据卷')
    extensions={'audio/mpeg':'mp3','audio/wav':'wav','image/png':'png','image/jpeg':'jpg','image/webp':'webp'}
    mime=metadata['mime']
    if mime not in extensions:raise HTTPException(422,'不支持的素材类型')
    return FileResponse(path,media_type=mime,filename=asset_id+'.'+extensions[mime])

async def relay_signal(room_id,user,message):
    runtime.throttle(('plugin-signal',user['id']),30,1)
    pid=message.get('plugin_id','');name=message.get('name','');payload=message.get('payload',{})
    if len(dump(payload).encode())>4096:raise HTTPException(422,'信号过大')
    with connection() as con:
        room=runtime.get_room_member(con,room_id,user)
        if room['branch']!=message.get('branch'):raise HTTPException(409,'时间线已变化')
        item=authorized_via(room_id,message.get('via') or pid,pid,name,True,con)
        state=load_state(room['state_json']);ctx=Context(manager,pid,room,state,user,con)
        output=item['backend'].signal(ctx,name,payload,manager.namespace(state,pid)['data'])
    await runtime.hub.signal(room_id,{'type':'plugin_signal','plugin_id':pid,'name':name,'payload':output,'branch':room['branch'],'actor_id':user['id']})
