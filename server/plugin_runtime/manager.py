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
from .sdk import Context, Plugin

API_VERSION=1
logger=logging.getLogger('ember.plugins')
ID_PATTERN=re.compile(r'^[a-z][a-z0-9-]{2,47}$')

def reviewed_records(path):
    if not path.exists():return {}
    try:
        value=json.loads(path.read_text())
        if not isinstance(value,dict) or any(not isinstance(k,str) or not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v) for k,v in value.items()):raise ValueError('invalid review record')
        return value
    except (ValueError,OSError):logger.warning('Invalid plugin review record; privileged plugins remain blocked: %s',path.name);return {}

def package_hash(folder):
    digest=hashlib.sha256()
    for path in sorted(folder.rglob('*')):
        if '__pycache__' in path.parts or path.name.endswith('.pyc'):continue
        if path.is_symlink():raise ValueError('package symlinks are not allowed')
        if path.is_file():digest.update(path.relative_to(folder).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()

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
                    m=json.loads(raw);pid=m['id']
                    if not ID_PATTERN.fullmatch(pid) or folder.name!=pid:raise ValueError('invalid plugin id')
                    if pid in discovered:continue # external packages cannot override bundled packages
                    if any((folder/name).is_symlink() for name in ('plugin.json','backend.py','ui.js')):raise ValueError('symlink entry point')
                    for resource in m.get('uses',[])+m.get('provides',[]):
                        if not re.fullmatch(r'[a-z][a-z0-9.-]{1,70}/v[1-9][0-9]*',resource):raise ValueError('invalid resource contract')
                    for field in ('name','version','description','api_version'): 
                        if field not in m:raise ValueError('missing '+field)
                    for field,limit in [('name',80),('description',1000),('category',64),('icon',64)]:
                        if field in m and (not isinstance(m[field],str) or len(m[field])>limit):raise ValueError('invalid '+field)
                    if type(m.get('default_enabled',False))is not bool:raise ValueError('invalid default enabled')
                    for field in ('requires','uses','provides','capabilities','actions','signals','hooks'):
                        values=m.get(field,[])
                        if not isinstance(values,list) or len(values)>40 or any(not isinstance(v,str) or len(v)>120 for v in values):raise ValueError('invalid '+field)
                    if type(m['api_version'])is not int or type(m.get('state_version',1))is not int or m.get('state_version',1)<1:raise ValueError('invalid API/state version')
                    if any(h!='gm' for h in m.get('hooks',[])) or ((m.get('provides') or m.get('hooks')) and not m.get('backend')):raise ValueError('invalid backend provider declaration')
                    if not re.fullmatch(r'\d+\.\d+\.\d+',m['version']):raise ValueError('invalid semantic version')
                    if m.get('backend') not in (None,'backend.py') or m.get('frontend') not in (None,'ui.js'):raise ValueError('entry point must be backend.py / ui.js')
                    if any(not ID_PATTERN.fullmatch(x) for x in m.get('requires',[])):raise ValueError('invalid dependency')
                    if m.get('frontend') and m.get('ui'):
                        ui=m['ui']
                        if not isinstance(ui,dict) or ui.get('slot') not in ('toolbar','main') or not isinstance(ui.get('group'),str) or len(ui['group'])>48:raise ValueError('invalid UI slot/group')
                        if 'label' in ui and (not isinstance(ui['label'],str) or len(ui['label'])>80):raise ValueError('invalid UI label')
                        if type(ui.get('height',500))is not int or not 120<=ui.get('height',500)<=1200:raise ValueError('invalid UI height')
                    digest=package_hash(folder);reason=''
                    if m['api_version']!=API_VERSION:reason='插件 API 版本不兼容'
                    elif (m.get('backend') or any(not c.startswith('read:') for c in m.get('capabilities',[]))) and trusted.get(pid)!=digest:reason='后端或高风险界面能力未获部署者信任，或文件已变化'
                    backend=None
                    if not reason and m.get('backend'):
                        cache_key=(pid,digest)
                        if cache_key not in self.cache:
                            module_name='ember_plugin_'+pid.replace('-','_')+'_'+digest[:8]
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
        return {pid:bool(flags.get(pid,item['manifest'].get('default_enabled',False))) for pid,item in self.items.items()}
    def enabled(self,room_id,pid,con=None):
        item=self.items.get(pid)
        if not item or item['blocked']:return False
        flags=self.flags(room_id,con)
        return bool(flags.get(pid) and all(flags.get(dep) and dep in self.items and not self.items[dep]['blocked'] for dep in item['manifest'].get('requires',[])))
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
    def resource(self,room,state,name,user=None,con=None):
        for pid,item in self.items.items():
            if name not in item['manifest'].get('provides',[]) or not self.enabled(room['id'],pid,con):continue
            if not item['backend']:return None
            ctx=Context(self,pid,room,state,user,con)
            try:
                res=item['backend'].resources(ctx,self.namespace(state,pid)['data']).get(name)
                return {'owner':pid,'revision':self.namespace(state,pid)['revision'],'data':res} if res is not None else None
            except Exception:
                logger.warning('Resource provider failed: %s/%s',pid,name);return None
        return None
    def catalog(self,room,state,con=None):
        flags=self.flags(room['id'],con)
        return [dict(item['manifest'],enabled=self.enabled(room['id'],pid,con),requested_enabled=flags.get(pid,False),
                     blocked=item['blocked'],builtin=item['builtin'],hash=item['hash'],state_revision=self.namespace(state,pid)['revision'],
                     fault=state.get('_plugin_faults',{}).get(pid)) for pid,item in self.items.items()]
    def public_context(self,room,state,user,pid,con=None):
        item=self.need(room['id'],pid,con);m=item['manifest'];ctx=Context(self,pid,room,state,user,con)
        data={'api_version':1,'plugin_id':pid,'room_id':room['id'],'branch':room['branch'],
              'plugin_revision':self.namespace(state,pid)['revision'],'is_owner':ctx.is_owner,
              'user':{'id':user['id'],'display_name':user['display_name'],'guest':bool(user['guest'])},
              'own_state':self.namespace(state,pid)['data'],'resources':{}}
        if 'read:room' in m.get('capabilities',[]):
            data['room']={'title':room['title'],'scene':deepcopy(state['scene']),'world':deepcopy(state['world']),
                         'characters':ctx.characters(),'turn':state['turn'],'facts':state['facts']}
        if 'read:events' in m.get('capabilities',[]):
            data['events']=[{'id':r['id'],'seq':r['seq'],'type':r['type'],'text':r['text'],'actor_name':r['actor_name']} for r in ctx.events(30)]
        for resource in m.get('uses',[])+m.get('provides',[]):
            data['resources'][resource]=self.resource(room,state,resource,user,con)
        data['integrations']={x:self.enabled(room['id'],x,con) for x in self.items}
        return data
    def toggle_plan(self,room_id,pid,enabled,con):
        if pid not in self.items:raise HTTPException(404,'插件未安装')
        if self.items[pid]['blocked']:raise HTTPException(422,self.items[pid]['blocked'])
        flags=self.flags(room_id,con);changed=[]
        def enable(current,trail):
            if current in trail:raise HTTPException(422,'插件依赖存在环')
            if current not in self.items or self.items[current]['blocked']:raise HTTPException(422,'依赖不可用：'+current)
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
