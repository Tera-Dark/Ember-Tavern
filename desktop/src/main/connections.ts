import {randomBytes,createHash} from 'node:crypto';
import {lstat,readFile,open,mkdir,rename,unlink} from 'node:fs/promises';
import {join} from 'node:path';
import type {SecretStorage} from './core';
import type {ConnectionKind,ConnectionProfile,ConnectionSnapshot,ConnectionTest} from '../types';

interface PrivateProfile {id:string;revision:number;name:string;kind:ConnectionKind;baseURL:string;model:string;voice:string;jsonMode:boolean;key:string}
interface Binding {profileId:string;revision:number;values:Record<string,string>}
interface Vault {format:'ember.connections/v1';profiles:PrivateProfile[];bindings:Record<string,Partial<Record<ConnectionKind,Binding>>>}
const empty=():Vault=>({format:'ember.connections/v1',profiles:[],bindings:{}});
const kinds=['decision','tts','knowledge'] as const;
export const KNOWLEDGE_URL='https://generativelanguage.googleapis.com/v1beta';
const identity=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v);
function field(v:unknown,max:number,label:string,blank=false):string {
 if(typeof v!=='string'||v.length>max||/[\x00-\x1f\x7f]/.test(v)||!blank&&!v.trim())throw new Error(label+'无效');
 return v.trim();
}
export function connectionURL(value:unknown):string {
 const raw=field(value,512,'接口地址');let u:URL;
 try{u=new URL(raw);}catch{throw new Error('接口地址无效');}
 if(u.username||u.password||u.search||u.hash||!u.hostname||u.protocol!=='https:'&&!(u.protocol==='http:'&&['localhost','127.0.0.1'].includes(u.hostname)))throw new Error('接口需要 HTTPS，本机可用 HTTP；凭据不要放进 URL');
 return u.href.replace(/\/$/,'');
}
function validateProfile(v:any):PrivateProfile {
 if(!v||!identity(v.id)||!Number.isInteger(v.revision)||v.revision<1||v.revision>1000000||!kinds.includes(v.kind)||typeof v.jsonMode!=='boolean')throw new Error('连接档案格式无效');
 const result={id:v.id,revision:v.revision,name:field(v.name,60,'档案名称'),kind:v.kind as ConnectionKind,baseURL:connectionURL(v.baseURL),model:field(v.model,160,'模型名称'),voice:field(v.voice,160,'声音 ID',true),jsonMode:v.jsonMode,key:field(v.key,2048,'密钥',true)};
 if(result.kind==='knowledge'&&(result.baseURL!==KNOWLEDGE_URL||!/^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/.test(result.model)||result.jsonMode))throw new Error('知识顾问使用 Gemini 官方接口和模型 ID；不支持自定义地址或 JSON 模式');
 if(result.key&&[result.name,result.baseURL,result.model,result.voice].some(s=>s.includes(result.key)))throw new Error('密钥只能填写在密钥栏');
 return result;
}
function runtime(profile:PrivateProfile):Record<string,string> {
 if(profile.kind==='knowledge')return {GEMINI_API_KEY:profile.key,GEMINI_MODEL:profile.model};
 return profile.kind==='decision'?{DECISION_API_KEY:profile.key,DECISION_BASE_URL:profile.baseURL,DECISION_MODEL:profile.model,DECISION_JSON_MODE:String(profile.jsonMode)}:{TTS_API_KEY:profile.key,TTS_BASE_URL:profile.baseURL,TTS_MODEL:profile.model,TTS_VOICE:profile.voice||'alloy'};
}
function parseVault(v:any):Vault {
 if(!v||v.format!=='ember.connections/v1'||!Array.isArray(v.profiles)||v.profiles.length>64||!v.bindings||typeof v.bindings!=='object'||Array.isArray(v.bindings)||Object.keys(v.bindings).length>128)throw new Error('档案文件格式无效');
 const profiles=v.profiles.map(validateProfile);if(new Set(profiles.map((p:PrivateProfile)=>p.id)).size!==profiles.length)throw new Error('档案 ID 重复');
 const bindings:Vault['bindings']={};
 for(const [instanceId,entry] of Object.entries(v.bindings)){
  if(!identity(instanceId)||!entry||typeof entry!=='object'||Array.isArray(entry))throw new Error('档案关联无效');
  const next:Partial<Record<ConnectionKind,Binding>>={};
  for(const [kind,binding] of Object.entries(entry)){
   const b=binding as Binding;
   if(!kinds.includes(kind as ConnectionKind)||!b||!identity(b.profileId)||!profiles.some((p:PrivateProfile)=>p.id===b.profileId&&p.kind===kind)||!Number.isInteger(b.revision)||b.revision<1||b.revision>1000000||!b.values||typeof b.values!=='object'||Array.isArray(b.values))throw new Error('档案关联无效');
   const prefix=kind==='decision'?'DECISION_':kind==='knowledge'?'GEMINI_':'TTS_';const expected=kind==='decision'?['API_KEY','BASE_URL','MODEL','JSON_MODE']:kind==='knowledge'?['API_KEY','MODEL']:['API_KEY','BASE_URL','MODEL','VOICE'];
   if(Object.keys(b.values).length!==expected.length||expected.some(key=>!Object.hasOwn(b.values,prefix+key)))throw new Error('运行配置格式无效');
   if(b.revision>profiles.find((p:PrivateProfile)=>p.id===b.profileId)!.revision||kind==='decision'&&!['true','false'].includes(b.values.DECISION_JSON_MODE))throw new Error('运行配置修订或 JSON 模式无效');
   const p=validateProfile({id:b.profileId,revision:b.revision,name:'应用快照',kind,baseURL:kind==='knowledge'?KNOWLEDGE_URL:b.values[prefix+'BASE_URL'],model:b.values[prefix+'MODEL'],key:b.values[prefix+'API_KEY'],voice:kind==='tts'?b.values.TTS_VOICE:'',jsonMode:kind==='decision'?b.values.DECISION_JSON_MODE==='true':false});
   next[kind as ConnectionKind]={profileId:b.profileId,revision:b.revision,values:runtime(p)};
  }
  bindings[instanceId]=next;
 }
 return {format:'ember.connections/v1',profiles,bindings};
}

export class ConnectionVault {
 private value=empty();private stamp:string|null=null;private tail:Promise<void>=Promise.resolve();private tests=new Map<string,ConnectionTest>();error='';
 constructor(readonly root:string,readonly storage:SecretStorage){}
 async load(){try{const path=join(this.root,'connections.private.json'),info=await lstat(path);if(!info.isFile()||info.isSymbolicLink()||info.size>2*1024*1024)throw new Error('invalid file');const raw=await readFile(path),outer=JSON.parse(raw.toString('utf8'));if(outer.format!=='ember.connections-encrypted/v1'||typeof outer.encrypted!=='string')throw new Error('unknown file');this.value=parseVault(JSON.parse(this.storage.decode(outer.encrypted)));this.stamp=createHash('sha256').update(raw).digest('hex');}catch(e:any){if(e.code!=='ENOENT')this.error='连接档案无法解密或格式不受支持。原文件保留；请使用原系统用户恢复，不能覆盖此文件。';}return this.snapshot();}
 snapshot():ConnectionSnapshot {return {readOnly:!!this.error,error:this.error||undefined,profiles:this.value.profiles.map(p=>({id:p.id,revision:p.revision,name:p.name,kind:p.kind,baseURL:p.baseURL,model:p.model,voice:p.voice,jsonMode:p.jsonMode,keyConfigured:!!p.key,test:this.tests.get(p.id)})),bindings:Object.fromEntries(Object.entries(this.value.bindings).map(([instanceId,entry])=>[instanceId,Object.fromEntries(Object.entries(entry).map(([kind,b])=>[kind,{profileId:b!.profileId,revision:b!.revision}]))]))};}
 private enqueue<T>(action:()=>Promise<T>):Promise<T>{const task=this.tail.then(action);this.tail=task.then(()=>{},()=>{});return task;}
 private async assertUnchanged(){if(this.error)throw new Error(this.error);let stamp:string|null=null;try{const path=join(this.root,'connections.private.json'),info=await lstat(path);if(!info.isFile()||info.isSymbolicLink()||info.size>2*1024*1024)throw new Error('invalid file');stamp=createHash('sha256').update(await readFile(path)).digest('hex');}catch(e:any){if(e.code!=='ENOENT'){this.error='连接档案文件发生变化或无法读取。原文件保留，请关闭桌面后检查；本次不会覆盖。';throw new Error(this.error);}}if(stamp!==this.stamp){this.error='连接档案在桌面打开后被其他操作修改。原文件保留，请关闭并重新打开桌面再检查。';throw new Error(this.error);}}
 private async persist(next:Vault){await this.assertUnchanged();parseVault(next);const encrypted=this.storage.encode(JSON.stringify(next)),raw=JSON.stringify({format:'ember.connections-encrypted/v1',encrypted})+'\n';const path=join(this.root,'connections.private.json'),temp=path+'.tmp-'+randomBytes(8).toString('hex');await mkdir(this.root,{recursive:true});const handle=await open(temp,'wx',0o600);try{await handle.writeFile(raw);await handle.close();await this.assertUnchanged();await rename(temp,path);}finally{await handle.close().catch(()=>{});await unlink(temp).catch(()=>{});}this.value=next;this.stamp=createHash('sha256').update(raw).digest('hex');}
 save(input:any){return this.enqueue(async()=>{
  if(!input||typeof input!=='object'||!['keep','replace','clear'].includes(input.keyAction))throw new Error('请选择保留、替换或清除密钥');
  const old=input.id?this.profile(input.id):undefined;
  if(old&&input.revision!==old.revision)throw new Error('档案已更新，请重新打开后编辑');
  if(old&&input.kind!==old.kind)throw new Error('档案用途不能修改，请新建档案');
  if(!old&&this.value.profiles.length>=64)throw new Error('连接档案已达上限');
  const key=input.keyAction==='keep'?old?.key||'':input.keyAction==='clear'?'':field(input.key,2048,'新密钥');
  const profile=validateProfile({...input,id:old?.id||randomBytes(16).toString('hex'),revision:(old?.revision||0)+1,key});
  await this.persist({...this.value,profiles:[...this.value.profiles.filter(p=>p.id!==profile.id),profile]});this.tests.delete(profile.id);return this.snapshot();
 });}
 remove(profileId:string){return this.enqueue(async()=>{this.profile(profileId);if(Object.values(this.value.bindings).some(entry=>Object.values(entry).some(b=>b?.profileId===profileId)))throw new Error('先在各酒馆解除此档案，再删除');await this.persist({...this.value,profiles:this.value.profiles.filter(p=>p.id!==profileId)});this.tests.delete(profileId);return this.snapshot();});}
 private profile(profileId:string){const p=this.value.profiles.find(p=>p.id===profileId);if(!identity(profileId)||!p)throw new Error('连接档案不存在');return p;}
 private effective(instanceId:string,bindings=this.value.bindings):Record<string,string>{return Object.assign({},...Object.values(bindings[instanceId]||{}).map(b=>b?.values||{}));}
 async restore(apply:(instanceId:string,values:Record<string,string>)=>Promise<unknown>){if(this.error)throw new Error(this.error);for(const instanceId of Object.keys(this.value.bindings))await apply(instanceId,this.effective(instanceId));}
 bind(instanceId:string,kind:ConnectionKind,profileId:string|null,apply:(values:Record<string,string>)=>Promise<unknown>){return this.enqueue(async()=>{
  if(this.error)throw new Error(this.error);if(!identity(instanceId)||!kinds.includes(kind))throw new Error('档案目标无效');
  const p=profileId===null?undefined:this.profile(profileId);if(p&&p.kind!==kind)throw new Error('档案用途不匹配');
  const bindings=structuredClone(this.value.bindings),entry={...bindings[instanceId]};
  if(p)entry[kind]={profileId:p.id,revision:p.revision,values:runtime(p)};else delete entry[kind];
  if(Object.keys(entry).length)bindings[instanceId]=entry;else delete bindings[instanceId];
  const previous=this.effective(instanceId);await apply(this.effective(instanceId,bindings));
  try{await this.persist({...this.value,bindings});}catch{try{await apply(previous);}catch{throw new Error('档案保存失败且运行配置未能恢复；请保留文件并停止实例后重新打开桌面。');}throw new Error('档案保存失败，原关联与运行配置已恢复。');}
  return this.snapshot();
 });}
 async test(profileId:string,mode:'models'|'generate',paidConfirmed:boolean,transport:typeof fetch=fetch):Promise<ConnectionTest>{
  await this.assertUnchanged();if(mode!=='models'&&mode!=='generate')throw new Error('检测方式无效');if(mode==='generate'&&!paidConfirmed)throw new Error('生成测试可能收费，请明确确认后发送');
  const profile=structuredClone(this.profile(profileId));if(!profile.key)throw new Error('请先保存密钥');
  const result:ConnectionTest={mode,status:'failed',checkedAt:new Date().toISOString(),detail:''};
  try{
   const route=mode==='models'?'/models':profile.kind==='knowledge'?'/models/'+encodeURIComponent(profile.model)+':generateContent':profile.kind==='decision'?'/chat/completions':'/audio/speech';
   const body=mode==='models'?undefined:profile.kind==='knowledge'?{contents:[{role:'user',parts:[{text:'只回复 OK，不生成故事。'}]}],generationConfig:{maxOutputTokens:16}}:profile.kind==='decision'?{model:profile.model,messages:[{role:'user',content:'只回复 OK，不生成故事。'}],max_tokens:16}:{model:profile.model,input:'你好。',voice:profile.voice||'alloy',response_format:'mp3'};
   const response=await transport(profile.baseURL+route,{method:body?'POST':'GET',headers:profile.kind==='knowledge'?{'x-goog-api-key':profile.key,'Content-Type':'application/json'}:{Authorization:'Bearer '+profile.key,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(25000),redirect:'error'});
   if(!response.ok){await response.body?.cancel();result.detail=response.status===404||response.status===405?'接口不支持此检测；可手填模型，不代表生成不可用。':'接口拒绝检测（HTTP '+response.status+'）；请检查地址、权限和余额。';}
   else{
    const bytes=await boundedBody(response,mode==='generate'&&profile.kind==='tts'?1024*1024:128*1024);
    if(mode==='models'){
     const value=JSON.parse(Buffer.from(bytes).toString('utf8'));const rows=profile.kind==='knowledge'?value.models:value.data;if(!Array.isArray(rows))throw new Error('invalid list');
     const models=rows.slice(0,200).filter((v:any)=>profile.kind!=='knowledge'||Array.isArray(v?.supportedGenerationMethods)&&v.supportedGenerationMethods.includes('generateContent')).map((v:any)=>profile.kind==='knowledge'?v?.name?.replace(/^models\//,''):v?.id).filter((v:any)=>typeof v==='string'&&v.length>0&&v.length<=160&&!/[\x00-\x1f\x7f]/.test(v)&&!v.includes(profile.key));
     result.models=[...new Set(models)] as string[];result.detail='模型列表已获取；尚未证明实际生成可用。';result.status='passed';
    }else if(profile.kind==='knowledge'){
     const value=JSON.parse(Buffer.from(bytes).toString('utf8'));const parts=value.candidates?.[0]?.content?.parts;if(!Array.isArray(parts)||!parts.some((p:any)=>!p.thought&&typeof p.text==='string'&&p.text.trim()))throw new Error('no knowledge output');
     result.detail='一次知识顾问文本测试成功；未读取任何房间，也未改变房间模型模式。';result.status='passed';
    }else if(profile.kind==='decision'){
     const value=JSON.parse(Buffer.from(bytes).toString('utf8'));if(typeof value.choices?.[0]?.message?.content!=='string'||!value.choices[0].message.content.trim())throw new Error('no output');
     result.detail='一次文本生成测试成功；不代表房间规则与结构化输出均已验证。';result.status='passed';
    }else{if(!response.headers.get('content-type')?.toLowerCase().startsWith('audio/mpeg')||bytes.length<4||!(bytes[0]===0x49&&bytes[1]===0x44&&bytes[2]===0x33||bytes[0]===0xff&&(bytes[1]&0xe0)===0xe0))throw new Error('invalid audio');result.detail='一次声音请求返回 MP3 数据；未进行听感与完整解码验收。';result.status='passed';}
   }
  }catch{result.detail='检测未完成：连接、超时或响应格式异常。密钥与供应商响应正文未记录。';}
  if(this.value.profiles.find(p=>p.id===profileId)?.revision===profile.revision)this.tests.set(profileId,result);
  return result;
 }
}
async function boundedBody(response:Response,limit:number):Promise<Uint8Array>{
 const reader=response.body?.getReader();if(!reader)throw new Error('empty response');const chunks:Uint8Array[]=[];let size=0;
 try{while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>limit)throw new Error('response too large');chunks.push(value);}}
 catch(e){await reader.cancel().catch(()=>{});throw e;}finally{reader.releaseLock();}
 const result=new Uint8Array(size);let offset=0;for(const chunk of chunks){result.set(chunk,offset);offset+=chunk.length;}return result;
}
