import {lstat,readFile,mkdir,open,rename,unlink} from 'node:fs/promises';
import {isAbsolute,join,dirname,relative,resolve,sep} from 'node:path';
import {randomBytes,createHash} from 'node:crypto';
import type {CreatorProject} from '../types';
const kinds=['worldbook','character','theme','scenario','preset','plugin'];
export async function creatorDirectory(value:string){
 if(typeof value!=='string'||!isAbsolute(value)||value.length>4096||value.startsWith('\\\\'))throw new Error('请选择本机作品目录');
 let path=resolve(value);for(;;){const info=await lstat(path);if(!info.isDirectory()||info.isSymbolicLink())throw new Error('作品目录及父目录不能是链接或特殊文件');const parent=dirname(path);if(parent===path)break;path=parent;}return resolve(value);
}
export function creatorOutside(path:string,bases:string[]){for(const base of bases){const part=relative(resolve(base),resolve(path));if(!part||part!=='..'&&!part.startsWith('..'+sep)&&!isAbsolute(part))throw new Error('草稿与发行输出请放在酒馆、运行环境和桌面资源之外的独立目录');}}
export class CreatorProjects {
 private projects:CreatorProject[]=[];private stamp:string|null=null;private tail:Promise<void>=Promise.resolve();error='';
 constructor(readonly root:string){}
 private get path(){return join(this.root,'creator-projects.private.json');}
 private async raw(){try{const info=await lstat(this.path);if(!info.isFile()||info.isSymbolicLink()||info.size>128<<10)throw new Error('invalid projects file');return await readFile(this.path);}catch(e:any){if(e.code==='ENOENT')return null;throw e;}}
 private hash(raw:Buffer|null){return raw===null?null:createHash('sha256').update(raw).digest('hex');}
 async load(){try{const raw=await this.raw();this.stamp=this.hash(raw);if(raw){const value=JSON.parse(raw.toString('utf8'));if(value?.format!=='ember.creator-projects/v1'||!Array.isArray(value.projects)||value.projects.length>64)throw new Error('invalid projects format');const ids=new Set<string>();for(const p of value.projects){if(!p||! /^[a-f0-9]{32}$/.test(p.id)||ids.has(p.id)||!kinds.includes(p.kind)||typeof p.name!=='string'||p.name.length>80||typeof p.directory!=='string'||!isAbsolute(p.directory)||p.directory.length>4096)throw new Error('invalid project record');ids.add(p.id);}this.projects=value.projects.map((p:CreatorProject)=>({id:p.id,kind:p.kind,name:p.name,directory:p.directory}));}}catch{this.error='作品目录记录无法读取或来自未知格式。原文件保留，本次不能更改记录；草稿文件不会删除。';}return this.snapshot();}
 snapshot(){return {projects:structuredClone(this.projects),readOnly:!!this.error,error:this.error||undefined};}
 get(projectId:unknown){if(typeof projectId!=='string'||! /^[a-f0-9]{32}$/.test(projectId))throw new Error('请选择已登记的作品');const project=this.projects.find(p=>p.id===projectId);if(!project)throw new Error('作品未登记，请用原生选择器打开目录');return structuredClone(project);}
 private mutate(action:()=>CreatorProject[]){const task=this.tail.then(async()=>{if(this.error)throw new Error(this.error);const next=action();if(next.length>64)throw new Error('最多登记 64 个作品目录');if(this.hash(await this.raw())!==this.stamp)throw new Error('作品记录已被其他操作更改，请重新打开桌面');await mkdir(this.root,{recursive:true});const temp=this.path+'.'+randomBytes(16).toString('hex')+'.tmp',handle=await open(temp,'wx',0o600);const raw=Buffer.from(JSON.stringify({format:'ember.creator-projects/v1',projects:next})+'\n');try{await handle.writeFile(raw);await handle.sync();await handle.close();if(this.hash(await this.raw())!==this.stamp)throw new Error('作品记录已改变，本次未覆盖');await rename(temp,this.path);}finally{await handle.close().catch(()=>{});await unlink(temp).catch(()=>{});}this.projects=next;this.stamp=this.hash(raw);return this.snapshot();});this.tail=task.then(()=>{},()=>{});return task;}
 register(directory:string,kind:string,name:string){if(!kinds.includes(kind)||typeof name!=='string'||name.length>80||!isAbsolute(directory))throw new Error('作品摘要格式不受支持');return this.mutate(()=>{const existing=this.projects.find(p=>relative(p.directory,directory)==='');return [...this.projects.filter(p=>p.id!==existing?.id),{id:existing?.id||randomBytes(16).toString('hex'),directory:resolve(directory),kind,name}];});}
 forget(projectId:unknown){const project=this.get(projectId);return this.mutate(()=>this.projects.filter(p=>p.id!==project.id));}
}
