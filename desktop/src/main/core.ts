import {spawn,type ChildProcess} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {readFile,writeFile,mkdir,rename} from 'node:fs/promises';
import {join} from 'node:path';
import type {RPCMethod,State,Instance,Room} from '../types';

export function id(value:unknown):string {if(typeof value!=='string'||!/^[a-f0-9]{32}$/.test(value))throw new Error('无效实例／房间 ID');return value;}
export function allowedExternal(value:string):boolean {try{const u=new URL(value);return u.protocol==='https:'&&u.hostname==='github.com'&&!u.username&&!u.password;}catch{return false;}}
export function trustedFrame(sender:number,expected:number,frameURL:string,expectedURL:string,isMain:boolean):boolean {return sender===expected&&isMain&&frameURL===expectedURL;}
export interface SecretStorage {encode(value:string):string;decode(value:string):string}
export interface EngineOptions {exe:string;root:string;host:string;commit:string;testPython?:string;testSkip?:boolean}

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
      this.child!.stdout!.on('data',chunk=>{buffer+=chunk.toString();if(buffer.length>8192){clearTimeout(timer);reject(new Error('部署引擎握手异常'));return;}if(!buffer.includes('\n')||ready)return;try{const data=JSON.parse(buffer.split('\n')[0]);if(!data.ready||!Number.isInteger(data.port)||data.port<1||data.port>65535||!/^[a-f0-9]{48}$/.test(data.token))throw new Error('握手格式错误');this.port=data.port;this.token=data.token;ready=true;clearTimeout(timer);resolve();}catch(error){clearTimeout(timer);reject(error)}});
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
  async state():Promise<State>{return this.engine.request('/api/state');}
  async instance(instanceId:string):Promise<Instance>{const value=(await this.state()).instances.find(item=>item.id===id(instanceId));if(!value)throw new Error('实例不存在');return value;}
  async hostSession(instanceId:string):Promise<string>{
    const current=this.pending.get(instanceId);if(current)return current;
    const next=this.createHostSession(instanceId).finally(()=>this.pending.delete(instanceId));this.pending.set(instanceId,next);return next;
  }
  private async createHostSession(instanceId:string):Promise<string>{
    if(this.tokens.has(instanceId))return this.tokens.get(instanceId)!;
    const instance=await this.instance(instanceId);if(instance.status!=='running')throw new Error('请先安装并启动实例');
    const account=await this.accountFor(instanceId);
    let response=await fetch(`http://127.0.0.1:${instance.port}/api/auth/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(account),signal:AbortSignal.timeout(15000),redirect:'error'});
    if(response.status===401)response=await fetch(`http://127.0.0.1:${instance.port}/api/auth/register`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...account,display_name:'房主'}),signal:AbortSignal.timeout(15000),redirect:'error'});
    const data=await response.json();if(!response.ok)throw new Error('本机房主登录失败；不会重置已有账号或覆盖数据');this.tokens.set(instanceId,data.token);return data.token;
  }
  private accountFor(instanceId:string):Promise<{username:string;password:string}>{
    const task=this.credentialsQueue.then(async()=>{
      if(!this.loaded){try{const raw=await readFile(join(this.engine.options.root,'desktop-credentials.json'),'utf8');this.accounts=JSON.parse(this.storage.decode(JSON.parse(raw).encrypted));}catch(error:any){if(error.code!=='ENOENT')throw new Error('房主凭据无法解密，请保留数据并使用原 Windows 用户打开');}this.loaded=true;}
      if(this.accounts[instanceId])return this.accounts[instanceId];
      const account={username:'desktop_'+instanceId.slice(0,16),password:randomBytes(32).toString('base64url')};
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
    const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'房间请求失败，请刷新状态');return data;
  }
  async invoke(method:RPCMethod,args:Record<string,any>={}):Promise<any>{
    if(method==='state')return this.state();
    if(method==='createInstance'){if(typeof args.name!=='string'||args.name.length>48)throw new Error('请填写实例名称');return this.engine.request('/api/instances','POST',{name:args.name,channel:'bundled',port:Number(args.port)||0,lan:args.lan!==false,start:true});}
    const instanceId=id(args.instanceId);const prefix='/api/instances/'+instanceId;
    switch(method){
      case 'instanceAction':{if(!['install','start','stop','update','check','folder'].includes(args.action))throw new Error('不支持的操作');if(args.action==='stop')this.tokens.delete(instanceId);return this.engine.request(prefix+'/'+args.action,'POST',{});}
      case 'configureInstance':return this.engine.request(prefix,'PUT',{name:args.name,channel:args.channel,port:Number(args.port),lan:!!args.lan});
      case 'settings':return this.engine.request(prefix+'/settings');
      case 'saveSettings':return this.engine.request(prefix+'/settings','PUT',args.values);
      case 'rooms':return this.game(instanceId,'/rooms');
      case 'createRoom':return this.game(instanceId,'/rooms','POST',{title:String(args.title).slice(0,80),preset:args.preset||'harbor',ai_mode:'demo'});
      case 'room':return this.game(instanceId,'/rooms/'+id(args.roomId));
      case 'guestInvites':return this.game(instanceId,'/rooms/'+id(args.roomId)+'/guest-access');
      case 'issueGuest':{const room=await this.game(instanceId,'/rooms/'+id(args.roomId));return this.game(instanceId,'/rooms/'+args.roomId+'/guest-access','POST',{identity:args.identity,expected_revision:room.revision,request_key:randomBytes(16).toString('hex')});}
      case 'revokeGuest':{const room=await this.game(instanceId,'/rooms/'+id(args.roomId));return this.game(instanceId,'/rooms/'+args.roomId+'/guest-access/'+id(args.inviteId)+'/revoke','POST',{expected_revision:room.revision,request_key:randomBytes(16).toString('hex')});}
      case 'roomAction':{const room:Room=await this.game(instanceId,'/rooms/'+id(args.roomId));let path='';let data:any={};if(args.action==='invitation'){path='/invitation';data={accepting_players:!!args.accepting};}else if(args.action==='plugin'){if(!/^[a-z][a-z0-9-]{2,47}$/.test(args.pluginId))throw new Error('插件 ID 无效');path='/extensions/'+args.pluginId+'/toggle';data={enabled:!!args.enabled};}else throw new Error('不支持的房间操作');return this.game(instanceId,'/rooms/'+args.roomId+path,'POST',{...data,expected_revision:room.revision,request_key:randomBytes(16).toString('hex')});}
      default:throw new Error('未知桌面操作');
    }
  }
}
