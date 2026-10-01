"""Backend SDK v1. Reviewed Python plugins are TRUSTED code, not a Python sandbox."""
from dataclasses import dataclass, field
from copy import deepcopy
import json
from fastapi import HTTPException
from ..db import connection
from ..contracts.resources import CORE_CAPABILITIES

@dataclass
class Result:
    data: dict | None = None
    message: str = ''
    output: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)

class Context:
    def __init__(self, manager, plugin_id, room, state, user=None, con=None, services=None):
        self.manager, self.plugin_id = manager, plugin_id
        self.room, self.state = dict(room), deepcopy(state)
        self.user, self.con, self.services = user, con, services or {}
        self.room_id = room['id'];self.reads={}
    @property
    def is_owner(self):
        return bool(self.user and self.room['owner_id'] == self.user['id'])
    def require_owner(self):
        if not self.is_owner: raise HTTPException(403,'此插件操作仅允许房主执行')
    def query(self, sql, params=()):
        if self.con is not None: return self.con.execute(sql,params).fetchall()
        with connection() as c: return c.execute(sql,params).fetchall()
    def characters(self):
        assigned={r['character_id']:r['user_id'] for r in self.query('SELECT * FROM assignments WHERE room_id=?',(self.room_id,))}
        return [dict(c,assigned_to=assigned.get(c['id'])) for c in self.state['characters']]
    def control(self, character_id):
        char=next((c for c in self.characters() if c['id']==character_id),None)
        if not char: raise HTTPException(404,'当前时间线中没有这个角色')
        if not self.user or (not self.is_owner and char['assigned_to']!=self.user['id']):
            raise HTTPException(403,'你只能移动分配给自己的角色')
        return char
    def resource(self, name):
        manifest=self.manager.items[self.plugin_id]['manifest']
        if name not in manifest.get('uses',[]): raise HTTPException(403,'插件未声明此资源读取能力')
        grants=CORE_CAPABILITIES
        if name.startswith('core.') and name not in grants:raise HTTPException(404,'未知宿主资源契约')
        if name in grants and grants[name] not in manifest.get('capabilities',[]):raise HTTPException(403,'未声明宿主资源能力')
        resource=self.manager.resource(self.room,self.state,name,self.user,self.con)
        if resource:self.reads[resource['owner']]=resource['revision']
        return resource
    def events(self, limit=30):
        return [dict(r) for r in self.query("SELECT id,seq,type,text,payload_json,actor_name FROM events WHERE room_id=? AND active=1 ORDER BY seq DESC LIMIT ?",(self.room_id,limit))][::-1]
    def save_asset(self,content,mime):
        from ..config import settings
        from ..db import uid
        if 'asset:write' not in self.manager.items[self.plugin_id]['manifest'].get('capabilities',[]):
            raise HTTPException(403,'插件未声明素材写入能力')
        allowed={'audio/mpeg','audio/wav','image/png','image/jpeg','image/webp'}
        if mime not in allowed or not content or len(content)>5*1024*1024:raise HTTPException(422,'素材类型或大小不符合限制')
        asset_id=uid();folder=settings.data_dir/'assets'/self.room_id/self.plugin_id
        folder.mkdir(parents=True,exist_ok=True);temporary=folder/(asset_id+'.tmp');temporary.write_bytes(content);temporary.replace(folder/(asset_id+'.bin'))
        return {'id':asset_id,'mime':mime,'bytes':len(content)}
    def own_data(self):
        return deepcopy(self.manager.namespace(self.state,self.plugin_id)['data'])

class Plugin:
    schema_version=1
    def initial(self,ctx): return {}
    def on_event(self,ctx,event,data): return None
    def resources(self,ctx,data): return {}
    def public_data(self,ctx,data):
        # API v1 namespaces are shared by default. Override to redact private fields.
        return deepcopy(data)
    async def action(self,ctx,name,payload,data): raise HTTPException(404,'插件操作不存在')
    def signal(self,ctx,name,payload,data): raise HTTPException(404,'插件信号不存在')
    def migrate(self,data,old_version):
        if old_version!=self.schema_version: raise ValueError('state schema migration required')
        return data
