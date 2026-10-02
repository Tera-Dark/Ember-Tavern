import hashlib
import importlib.util
import json
import logging
import re
import sys
from copy import deepcopy
from pathlib import Path
from fastapi import HTTPException
from ..config import ROOT, settings
from ..db import connection
from ..contracts.plugin import validate_manifest, needs_capability_grant
from ..contracts.resources import CORE_CAPABILITIES
from ..version import HOST_VERSION
from ..projection import project_state, project_event
from ..rules import engine_for
from .sdk import Context, Plugin
from .integrity import package_hash
from ..state import load_state

API_VERSION=1
logger=logging.getLogger('ember.plugins')
ID_PATTERN=re.compile(r'^[a-z][a-z0-9-]{2,47}$')

def reviewed_records(path):
    if not path.exists():return {}
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,dict) or any(not isinstance(k,str) or not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v) for k,v in value.items()):raise ValueError('invalid review record')
        return value
    except (ValueError,OSError):logger.warning('Invalid plugin review record; privileged plugins remain blocked: %s',path.name);return {}


class Manager:
    def __init__(self): self.items={};self.cache={}
    def refresh(self):
        bundled=ROOT/'plugins';extra=settings.data_dir/'plugins'
        lock_path=bundled/'catalog.lock.json'
        locks=reviewed_records(lock_path)
        trust=settings.data_dir/'plugin-trust.json'
        extra_trust=reviewed_records(trust)
        discovered={}
        for base,trusted in ((bundled,locks),(extra,extra_trust)):
            if not base.exists():continue
            for folder in sorted(base.iterdir()):
                if folder.name.startswith('.') or not folder.is_dir() or folder.is_symlink() or not (folder/'plugin.json').exists():continue
                try:
                    raw=(folder/'plugin.json').read_bytes()
                    if len(raw)>32768:raise ValueError('manifest too large')
                    m=validate_manifest(json.loads(raw),folder);pid=m['id']
                    if folder.name!=pid:raise ValueError('folder name must match plugin id')
                    if pid in discovered:continue # external packages cannot override bundled packages
                    if (folder/'plugin.json').is_symlink():raise ValueError('symlink manifest')
                    digest=package_hash(folder);reason=''
                    if m['api_version']!=API_VERSION:reason='插件 API 版本不兼容'
                    elif tuple(map(int,m['minimum_host'].split('.'))) > tuple(map(int,HOST_VERSION.split('-')[0].split('.'))):reason='插件要求更高版本宿主：'+m['minimum_host']
                    elif (m.get('backend') or needs_capability_grant(m)) and trusted.get(pid)!=digest:reason='后端或高风险界面能力未获部署者信任，或文件已变化'
                    backend=None
                    if not reason and m.get('backend'):
                        cache_key=(pid,digest)
                        if cache_key not in self.cache:
                            module_name='ember_plugin_'+pid.replace('-','_')+'_'+digest
                            spec=importlib.util.spec_from_file_location(module_name,folder/'backend.py',submodule_search_locations=[str(folder)])
                            module=importlib.util.module_from_spec(spec);sys.modules[module_name]=module
                            try:spec.loader.exec_module(module)
                            except Exception:sys.modules.pop(module_name,None);raise
                            instance=module.Extension()
                            if not isinstance(instance,Plugin):raise ValueError('backend must extend Plugin')
                            if 'gm' in m.get('hooks',[]) and not callable(getattr(instance,'gm',None)):raise ValueError('missing GM implementation')
                            if instance.schema_version!=m.get('state_version',1):raise ValueError('manifest/backend state version mismatch')
                            self.cache[cache_key]=instance
                        backend=self.cache[cache_key]
                    discovered[pid]={'manifest':m,'folder':folder,'hash':digest,'backend':backend,'blocked':reason,'builtin':base==bundled}
                except Exception as exc:
                    logger.warning('Plugin discovery rejected %s: %s',folder.name,type(exc).__name__)
        self.items=discovered
    def gm_provider(self,room_id,con=None):
        return next(((pid,item) for pid,item in self.items.items() if 'gm' in item['manifest'].get('hooks',[]) and self.enabled(room_id,pid,con)),None)

    def flags(self,room_id,con=None):
        if con is None:
            with connection() as c:return self.flags(room_id,c)
        row=con.execute('SELECT flags_json FROM room_plugins WHERE room_id=?',(room_id,)).fetchone()
        flags=json.loads(row[0]) if row else {}
        return {pid:bool(flags.get(pid,item['manifest'].get('default_enabled',False) if item['builtin'] else False)) for pid,item in self.items.items()}
    def pin_reason(self,room_id,pid,con=None):
        if con is None:
            with connection() as c: return self.pin_reason(room_id,pid,c)
        row=con.execute('SELECT state_json FROM rooms WHERE id=?',(room_id,)).fetchone()
        lock=load_state(row['state_json']).get('_preset_lock') if row else None
        if not lock: return ''
        pin=next((pin for pin in lock['plugins'] if pin['id']==pid),None)
        if not pin: return '本预设未锁定此模块；添加新模块需要显式升级，不自动改变旧房间'
        item=self.items.get(pid)
        if not item or item['manifest']['version']!=pin['version'] or item['hash']!=pin['sha256']:
            return '原模块版本 / SHA256 已变化；保留状态并恢复匹配版本，不自动替换'
        return ''
    def enabled(self,room_id,pid,con=None):
        flags=self.flags(room_id,con)
        def ready(current,trail):
            item=self.items.get(current)
            if current in trail or not item or item['blocked'] or not flags.get(current) or self.pin_reason(room_id,current,con):return False
            return all(ready(dep,trail|{current}) for dep in item['manifest'].get('requires',[]))
        return ready(pid,set())
    def need(self,room_id,pid,con=None):
        if pid not in self.items:raise HTTPException(404,'插件未安装')
        if not self.enabled(room_id,pid,con):raise HTTPException(403,'插件未开启、依赖关闭或未获信任')
        return self.items[pid]
    def namespace(self,state,pid):
        return deepcopy(state.get('_plugins',{}).get(pid,{'schema_version':1,'revision':0,'data':{}}))
    def write(self,state,pid,data):
        encoded=json.dumps(data,ensure_ascii=False,allow_nan=False)
        if not isinstance(data,dict) or len(encoded.encode())>262144:raise ValueError('plugin state must be an object <= 256 KiB')
        old=self.namespace(state,pid);backend=self.items[pid]['backend']
        state.setdefault('_plugins',{})[pid]={'schema_version':backend.schema_version if backend else 1,'revision':old['revision']+1,'data':json.loads(encoded)}
    def initialize(self,room,state,pid,user=None,con=None):
        item=self.need(room['id'],pid,con)
        if pid in state.get('_plugins',{}):
            ns=self.namespace(state,pid);backend=item['backend']
            if backend and ns['schema_version']!=backend.schema_version:
                self.write(state,pid,backend.migrate(ns['data'],ns['schema_version']))
            return
        ctx=Context(self,pid,room,state,user,con)
        self.write(state,pid,item['backend'].initial(ctx) if item['backend'] else {})
    def on_event(self,con,room,state,event):
        for pid,item in list(self.items.items()):
            if not self.enabled(room['id'],pid,con) or not item['backend']:continue
            try:
                self.initialize(room,state,pid,con=con)
                ctx=Context(self,pid,room,state,con=con)
                updated=item['backend'].on_event(ctx,event,self.namespace(state,pid)['data'])
                if updated is not None:self.write(state,pid,updated)
            except Exception:
                logger.exception('Plugin hook failed: %s',pid)
                # Isolate a faulty hook. Never cancel the host's game transaction.
                state.setdefault('_plugin_faults',{})[pid]='事件钩子异常；内核继续运行，需检查插件'
    def viewer_state(self,state,user,manifest):
        # The caller supplies a room-specific viewer; read:gm is an explicit, reviewed capability.
        include_gm=bool(user and user.get('_is_owner') and 'read:gm' in manifest.get('capabilities',[]))
        return project_state(state,include_gm=include_gm)
    def public_data(self,room,state,pid,user,con=None):
        item=self.items.get(pid)
        if not item or item['blocked']:return {}
        viewer=dict(user,_is_owner=room['owner_id']==user['id'])
        safe=self.viewer_state(state,viewer,item['manifest'])
        ctx=Context(self,pid,room,safe,user,con)
        data=self.namespace(state,pid)['data']
        try:
            projected=item['backend'].public_data(ctx,deepcopy(data)) if item['backend'] else deepcopy(data)
            if not isinstance(projected,dict) or len(json.dumps(projected,ensure_ascii=False,allow_nan=False).encode())>262144:raise ValueError('invalid public projection')
            return projected
        except Exception:
            logger.exception('Plugin public projection failed: %s',pid)
            return {} # Never fall back to potentially private raw data.
    def core_resource(self,room,state,name,user=None,con=None):
        ctx=Context(self,'@core',room,state,user,con)
        data=None
        if name=='core.campaign/v1':
            from ..presets.scenario import view as campaign_view
            data={'campaign':campaign_view(state,False) if state.get('_scenario') else deepcopy(state.get('campaign'))}
        elif name=='core.world/v1':data=deepcopy(state['world'])
        elif name=='core.characters/v1':data={'characters':ctx.characters()}
        elif name=='core.rules/v1':data=engine_for(state).contract()
        elif name=='core.dice/v1':data={'rule_system':engine_for(state).id,'limits':engine_for(state).contract()['dice']}
        elif name=='core.events/v1':
            data={'events':[project_event({'id':r['id'],'seq':r['seq'],'type':r['type'],'text':r['text'],
                         'actor_name':r['actor_name'],'payload':json.loads(r['payload_json'])},include_gm=False) for r in ctx.events(30)]}
        return {'owner':'@core','revision':room['revision'],'data':data} if data is not None else None
    def resource(self,room,state,name,user=None,con=None):
        if name.startswith('core.'):
            if name not in CORE_CAPABILITIES:return None
            safe=project_state(state,include_gm=False) if user else state
            return self.core_resource(room,safe,name,user,con)
        for pid,item in self.items.items():
            if name not in item['manifest'].get('provides',[]) or not self.enabled(room['id'],pid,con):continue
            if not item['backend']:return None
            viewer=dict(user,_is_owner=room['owner_id']==user['id']) if user else None
            safe=self.viewer_state(state,viewer,item['manifest']) if user else state
            ctx=Context(self,pid,room,safe,user,con)
            data=self.public_data(room,safe,pid,user,con) if user else self.namespace(state,pid)['data']
            try:
                res=item['backend'].resources(ctx,data).get(name)
                return {'owner':pid,'revision':self.namespace(state,pid)['revision'],'data':res} if res is not None else None
            except Exception:
                logger.warning('Resource provider failed: %s/%s',pid,name);return None
        return None
    def catalog(self,room,state,con=None):
        flags=self.flags(room['id'],con)
        return [dict(item['manifest'],enabled=self.enabled(room['id'],pid,con),requested_enabled=flags.get(pid,False),
                     blocked=item['blocked'] or self.pin_reason(room['id'],pid,con),builtin=item['builtin'],hash=item['hash'],state_revision=self.namespace(state,pid)['revision'],
                     fault=state.get('_plugin_faults',{}).get(pid)) for pid,item in self.items.items()]
    def public_context(self,room,state,user,pid,con=None):
        item=self.need(room['id'],pid,con);m=item['manifest']
        viewer=dict(user,_is_owner=room['owner_id']==user['id'])
        safe=self.viewer_state(state,viewer,m)
        ctx=Context(self,pid,room,safe,user,con)
        data={'api_version':1,'plugin_id':pid,'room_id':room['id'],'branch':room['branch'],
              'plugin_revision':self.namespace(state,pid)['revision'],'is_owner':ctx.is_owner,
              'user':{'id':user['id'],'display_name':user['display_name'],'guest':bool(user['guest'])},
              'own_state':self.public_data(room,safe,pid,user,con),'resources':{}}
        if 'read:room' in m.get('capabilities',[]):
            data['room']={'title':room['title'],'scene':deepcopy(safe['scene']),'world':deepcopy(safe['world']),
                         'characters':ctx.characters(),'turn':safe['turn'],'facts':safe['facts'],'rules':engine_for(state).description}
        if 'read:events' in m.get('capabilities',[]):
            data['events']=[{'id':r['id'],'seq':r['seq'],'type':r['type'],'text':r['text'],'actor_name':r['actor_name']} for r in ctx.events(30)]
        grants=CORE_CAPABILITIES
        for resource in m.get('uses',[])+m.get('provides',[]):
            if resource in grants and grants[resource] not in m.get('capabilities',[]):continue
            data['resources'][resource]=self.resource(room,safe,resource,user,con)
        data['integrations']={x:self.enabled(room['id'],x,con) for x in self.items}
        return data
    def toggle_plan(self,room_id,pid,enabled,con):
        if pid not in self.items:raise HTTPException(404,'插件未安装')
        if self.items[pid]['blocked']:raise HTTPException(422,self.items[pid]['blocked'])
        flags=self.flags(room_id,con);changed=[]
        def enable(current,trail):
            if current in trail:raise HTTPException(422,'插件依赖存在环')
            if current not in self.items or self.items[current]['blocked']:raise HTTPException(422,'依赖不可用：'+current)
            pinned=self.pin_reason(room_id,current,con)
            if pinned:raise HTTPException(422,pinned)
            for dep in self.items[current]['manifest'].get('requires',[]):enable(dep,trail+[current])
            if not flags.get(current):changed.append(current)
            flags[current]=True
        def disable(current):
            if flags.get(current):changed.append(current)
            flags[current]=False
            for other,item in self.items.items():
                if flags.get(other) and current in item['manifest'].get('requires',[]):disable(other)
        enable(pid,[]) if enabled else disable(pid)
        resources={};gm=[]
        for current,item in self.items.items():
            if not flags.get(current) or item['blocked']:continue
            if 'gm' in item['manifest'].get('hooks',[]):gm.append(current)
            for name in item['manifest'].get('provides',[]):
                if name in resources:raise HTTPException(409,'资源 '+name+' 已有启用提供者，请先关闭旧插件')
                resources[name]=current
        if len(gm)>1:raise HTTPException(409,'一次只能启用一个主持提供者，请先关闭旧主持')
        return flags,changed

manager=Manager()
