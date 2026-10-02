import {spawn,type ChildProcess} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {readFile,writeFile,mkdir,rename} from 'node:fs/promises';
import {join} from 'node:path';
import {localDiagnostics} from './diagnostics';
import type {RPCMethod,State,Instance,Room,BuildInfo} from '../types';

export function packageHash(value:unknown):string{if(typeof value!=='string'||!/^[a-f0-9]{64}$/.test(value))throw new Error('无效预设包散列');return value;}
export function id(value:unknown):string {if(typeof value!=='string'||!/^[a-f0-9]{32}$/.test(value))throw new Error('无效实例／房间 ID');return value;}
export function allowedExternal(value:string):boolean {try{const u=new URL(value);return u.protocol==='https:'&&u.hostname==='github.com'&&!u.username&&!u.password;}catch{return false;}}
export function trustedFrame(sender:number,expected:number,frameURL:string,expectedURL:string,isMain:boolean):boolean {return sender===expected&&isMain&&frameURL===expectedURL;}
export function engineHandshake(data:any):{port:number;token:string}{
  if(data?.ready===false&&data?.code==='startup_state')throw new Error('部署引擎无法载入管理数据，可能是索引损坏／来自新版本，或目录被旧启动器占用。请保留 launcher.json、index-backups 与所有实例，查看本机 launcher.log；不要删库重装。');
  if(data?.ready!==true||!Number.isInteger(data.port)||data.port<1||data.port>65535||typeof data.token!=='string'||!/^[a-f0-9]{48}$/.test(data.token))throw new Error('部署引擎握手格式错误');
  return {port:data.port,token:data.token};
}
export interface SecretStorage {encode(value:string):string;decode(value:string):string}
export interface EngineOptions {exe:string;root:string;host:string;commit:string;testPython?:string;testSkip?:boolean;build?:BuildInfo}

export class EngineClient {
  child?:ChildProcess;port=0;private token='';
  constructor(readonly options:EngineOptions){}
  async start():Promise<void>{
    const args=['--headless','--desktop-control','--data-dir',this.options.root,'--bundled-source',this.options.host,'--bundled-commit',this.options.commit];
    if(this.options.testPython){args.push('--dev-python',this.options.testPython);if(this.options.testSkip!==false)args.push('--dev-system-packages','--dev-skip-deps');}
    this.child=spawn(this.options.exe,args,{windowsHide:true,stdio:['ignore','pipe','pipe']});
    await new Promise<void>((resolve,reject)=>{let buffer='';let ready=false;const timer=setTimeout(()=>reject(new Error('部署引擎启动超时，请查看 launcher.log')),15000);
      this.child!.once('error',error=>{clearTimeout(timer);reject(error)});
      this.child!.once('exit',()=>{clearTimeout(timer);if(!ready)reject(new Error('部署引擎退出；请确认没有旧启动器同时管理同一目录'))});
      this.child!.stdout!.on('data',chunk=>{buffer+=chunk.toString();if(buffer.length>8192){clearTimeout(timer);reject(new Error('部署引擎握手异常'));return;}if(!buffer.includes('\n')||ready)return;try{const data=engineHandshake(JSON.parse(buffer.split('\n')[0]));this.port=data.port;this.token=data.token;ready=true;clearTimeout(timer);resolve();}catch(error){clearTimeout(timer);reject(error)}});
      this.child!.stderr!.resume(); // Private handshake/token is never logged or returned to renderer.
    });
  }
  async request(path:string,method='GET',body?:unknown):Promise<any>{
    if(!this.port)throw new Error('部署引擎未就绪');
    const origin=`http://127.0.0.1:${this.port}`;
    const response=await fetch(origin+path,{method,headers:{Cookie:'ember-launcher='+this.token,Origin:origin,'X-Ember-Launcher':'1','Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(60000),redirect:'error'});
    const value=await response.json().catch(()=>({error:'部署引擎响应异常'}));if(!response.ok)throw new Error(value.error||'部署请求失败');return value;
  }
  async stop(){if(!this.child||this.child.exitCode!==null)return;try{await this.request('/api/shutdown','POST',{});}catch{}if(this.child.exitCode!==null)return;await new Promise<void>(resolve=>{const timer=setTimeout(()=>{this.child?.kill();resolve()},10000);this.child!.once('exit',()=>{clearTimeout(timer);resolve()});});}
}

export class HostController {
  private tokens=new Map<string,string>();private accounts:Record<string,{username:string;password:string}>={};private loaded=false;private pending=new Map<string,Promise<string>>();private credentialsQueue:Promise<void>=Promise.resolve();
  constructor(readonly engine:EngineClient,readonly storage:SecretStorage){}
  async state():Promise<State>{const state=await this.engine.request('/api/state');return {...state,...(this.engine.options.build?{build:this.engine.options.build}:{})};}
  async instance(instanceId:string):Promise<Instance>{const value=(await this.state()).instances.find(item=>item.id===id(instanceId));if(!value)throw new Error('实例不存在');return value;}
  async hostSession(instanceId:string):Promise<string>{
    const current=this.pending.get(instanceId);if(current)return current;
    const next=this.createHostSession(instanceId).finally(()=>this.pending.delete(instanceId));this.pending.set(instanceId,next);return next;
  }
  private async createHostSession(instanceId:string):Promise<string>{
    if(this.tokens.has(instanceId))return this.tokens.get(instanceId)!;
    const instance=await this.instance(instanceId);if(instance.status!=='running')throw new Error('请先安装并启动实例');
    const account=await this.accountFor(instanceId,instance.recovered_from_id);
    let response=await fetch(`http://127.0.0.1:${instance.port}/api/auth/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(account),signal:AbortSignal.timeout(15000),redirect:'error'});
    if(response.status===401&&!instance.recovered_from_id)response=await fetch(`http://127.0.0.1:${instance.port}/api/auth/register`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...account,display_name:'房主'}),signal:AbortSignal.timeout(15000),redirect:'error'});
    const data=await response.json();if(!response.ok)throw new Error('本机房主登录失败；不会重置已有账号或覆盖数据');this.tokens.set(instanceId,data.token);return data.token;
  }
  private accountFor(instanceId:string,recoveredFrom?:string):Promise<{username:string;password:string}>{
    const task=this.credentialsQueue.then(async()=>{
      if(!this.loaded){try{const raw=await readFile(join(this.engine.options.root,'desktop-credentials.json'),'utf8');const accounts=JSON.parse(this.storage.decode(JSON.parse(raw).encrypted));if(!accounts||typeof accounts!=='object'||Array.isArray(accounts)||Object.values(accounts).some((item:any)=>!item||typeof item.username!=='string'||typeof item.password!=='string'||!item.username||item.username.length>24||!item.password||item.password.length>128))throw new Error('invalid protected credentials');this.accounts=accounts;}catch(error:any){if(error.code!=='ENOENT')throw new Error('房主凭据无法解密，请保留数据并使用原 Windows 用户打开');}this.loaded=true;}
      if(Object.hasOwn(this.accounts,instanceId))return this.accounts[instanceId];
      let account:{username:string;password:string};
      if(recoveredFrom){
        if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(recoveredFrom)||!Object.hasOwn(this.accounts,recoveredFrom))throw new Error('数据已恢复，但缺少原房主凭据。请保留 desktop-credentials.json 并使用原 Windows 用户，或在浏览器以原账号登录；不会重置账号。');
        // Preserve the original owner, and persist the new-ID association using
        // the same protected atomic write. Never discard the original key.
        account=this.accounts[recoveredFrom];
      }else account={username:'desktop_'+instanceId.slice(0,16),password:randomBytes(32).toString('base64url')};
      const updated={...this.accounts,[instanceId]:account};const encrypted=this.storage.encode(JSON.stringify(updated));
      await mkdir(this.engine.options.root,{recursive:true});const file=join(this.engine.options.root,'desktop-credentials.json');await writeFile(file+'.tmp',JSON.stringify({encrypted}),{mode:0o600});await rename(file+'.tmp',file);
      this.accounts=updated;return account;
    });
    this.credentialsQueue=task.then(()=>{},()=>{});return task;
  }
  async game(instanceId:string,path:string,method='GET',body?:unknown,retry=true):Promise<any>{
    const instance=await this.instance(instanceId);const token=await this.hostSession(instanceId);
    const response=await fetch(`http://127.0.0.1:${instance.port}/api${path}`,{method,headers:{'X-Ember-Session':token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(45000),redirect:'error'});
    if(response.status===401&&retry){this.tokens.delete(instanceId);return this.game(instanceId,path,method,body,false);}
    const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:data.detail?.message?(data.detail.message+(data.detail.blockers?.length?'：'+data.detail.blockers.join('；'):'')):'房间请求失败，请刷新状态');return data;
  }
  async diagnostics(instanceId:string){const instance=await this.instance(instanceId);const settings=await this.engine.request('/api/instances/'+instanceId+'/settings');return localDiagnostics(instance,settings);}
  async invoke(method:RPCMethod,args:Record<string,any>={}):Promise<any>{
    if(method==='state')return this.state();
    if(method==='recoverIndex')return this.engine.request('/api/index-recovery/'+id(args.entryId),'POST',{confirm_stopped:args.confirmStopped===true});
    if(method==='createInstance'){if(typeof args.name!=='string'||args.name.length>48)throw new Error('请填写实例名称');return this.engine.request('/api/instances','POST',{name:args.name,channel:'bundled',port:Number(args.port)||0,lan:args.lan!==false,start:true});}
    const instanceId=id(args.instanceId);const prefix='/api/instances/'+instanceId;
    switch(method){
      case 'instanceAction':{if(!['install','start','stop','update','check','folder'].includes(args.action))throw new Error('不支持的操作');if(args.action==='stop')this.tokens.delete(instanceId);return this.engine.request(prefix+'/'+args.action,'POST',{});}
      case 'configureInstance':return this.engine.request(prefix,'PUT',{name:args.name,channel:args.channel,port:Number(args.port),lan:!!args.lan});
      case 'diagnostics':return this.diagnostics(instanceId);
      case 'presetCatalog':return this.game(instanceId,'/presets');
      case 'createPresetRoom':{if(typeof args.title!=='string'||!args.title.trim()||[...args.title].length>60)throw new Error('房间名称需要 1–60 个字符');if(typeof args.requestKey!=='string'||!/^[a-zA-Z0-9_-]{8,80}$/.test(args.requestKey))throw new Error('开桌需要稳定请求标识');return this.game(instanceId,'/rooms/from-preset','POST',{title:args.title.trim(),package_hash:packageHash(args.packageHash),ai_mode:'demo',host_plays:args.hostPlays!==false,request_key:args.requestKey});}
      case 'starterWorlds':return this.game(instanceId,'/starters');
      case 'assignCharacter':{const room=await this.game(instanceId,'/rooms/'+id(args.roomId));return this.game(instanceId,'/rooms/'+args.roomId+'/characters/'+id(args.characterId)+'/assign','POST',{user_id:args.userId===null?null:id(args.userId),expected_revision:room.revision,request_key:randomBytes(16).toString('hex')});}
      case 'settings':return this.engine.request(prefix+'/settings');
      case 'saveSettings':return this.engine.request(prefix+'/settings','PUT',args.values);
      case 'rooms':return this.game(instanceId,'/rooms');
      case 'createRoom':{const preset=args.preset||'harbor';if(!['harbor','frontier'].includes(preset))throw new Error('请选择一个内置入门世界');if(typeof args.title!=='string'||!args.title.trim()||[...args.title].length>60)throw new Error('房间名称需要 1–60 个字符');return this.game(instanceId,'/rooms','POST',{title:args.title.trim(),preset,ai_mode:'demo'});}
      case 'room':return this.game(instanceId,'/rooms/'+id(args.roomId));
      case 'guestInvites':return this.game(instanceId,'/rooms/'+id(args.roomId)+'/guest-access');
      case 'issueGuest':{const room=await this.game(instanceId,'/rooms/'+id(args.roomId));return this.game(instanceId,'/rooms/'+args.roomId+'/guest-access','POST',{identity:args.identity,expected_revision:room.revision,request_key:randomBytes(16).toString('hex')});}
      case 'revokeGuest':{const room=await this.game(instanceId,'/rooms/'+id(args.roomId));return this.game(instanceId,'/rooms/'+args.roomId+'/guest-access/'+id(args.inviteId)+'/revoke','POST',{expected_revision:room.revision,request_key:randomBytes(16).toString('hex')});}
      case 'roomAction':{const room:Room=await this.game(instanceId,'/rooms/'+id(args.roomId));let path='';let data:any={};if(args.action==='invitation'){path='/invitation';data={accepting_players:!!args.accepting};}else if(args.action==='plugin'){if(!/^[a-z][a-z0-9-]{2,47}$/.test(args.pluginId))throw new Error('插件 ID 无效');path='/extensions/'+args.pluginId+'/toggle';data={enabled:!!args.enabled};}else throw new Error('不支持的房间操作');return this.game(instanceId,'/rooms/'+args.roomId+path,'POST',{...data,expected_revision:room.revision,request_key:randomBytes(16).toString('hex')});}
      default:throw new Error('未知桌面操作');
    }
  }
}
