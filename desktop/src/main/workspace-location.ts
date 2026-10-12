import {lstat,readdir,readFile,mkdir,open,rename,unlink,statfs} from 'node:fs/promises';
import {resolve,dirname,join,isAbsolute,relative,sep} from 'node:path';
import {randomBytes,createHash} from 'node:crypto';

export const WORKSPACE_MIN_DESKTOP='0.2.0-beta.4';
export interface WorkspaceLocation {root:string;defaultRoot:string;custom:boolean;minimumDesktop:string}
export interface WorkspaceInspection {root:string;existing:boolean;availableBytes:number|null}
function contains(parent:string,child:string){const part=relative(parent,child);return !part||(!part.startsWith('..'+sep)&&part!=='..'&&!isAbsolute(part));}
function sameRoot(a:string,b:string){return relative(resolve(a),resolve(b))==='';}
async function regularDirectory(path:string){
 let cursor=resolve(path);
 for(;;){const info=await lstat(cursor);if(!info.isDirectory()||info.isSymbolicLink())throw new Error('工作区目录及其父目录不能是链接或特殊文件');const parent=dirname(cursor);if(parent===cursor)break;cursor=parent;}
}
async function boundedFile(path:string,max:number){const info=await lstat(path);if(!info.isFile()||info.isSymbolicLink()||info.size>max)throw new Error('工作区管理文件需要检查，原文件保留');return readFile(path,'utf8');}
export class WorkspaceLocationStore {
 private stamp:string|null=null;
 constructor(readonly settingsRoot:string,readonly defaultRoot:string){}
 private get file(){return join(this.settingsRoot,'desktop-workspace.json');}
 private async encoded(){try{return await boundedFile(this.file,32768);}catch(e:any){if(e.code==='ENOENT')return null;throw e;}}
 private fingerprint(value:string|null){return value===null?null:createHash('sha256').update(value).digest('hex');}
 async load():Promise<string>{
  const encoded=await this.encoded();this.stamp=this.fingerprint(encoded);if(encoded===null){await mkdir(this.defaultRoot,{recursive:true});await regularDirectory(this.defaultRoot);return resolve(this.defaultRoot);}
  let data:any;try{data=JSON.parse(encoded);}catch{throw new Error('工作区位置记录损坏，请保留 desktop-workspace.json 后检查；不会改用空目录');}
  if(data?.format!=='ember.desktop-workspace/v1'||typeof data.root!=='string'||!isAbsolute(data.root)||data.root.length>4096||data.root.startsWith('\\\\'))throw new Error('工作区位置记录不受支持；原数据保留，不会改用默认目录');
  // A missing selected disk must fail visibly rather than create a new workspace.
  await regularDirectory(data.root);return resolve(data.root);
 }
 snapshot(root:string):WorkspaceLocation{return {root,defaultRoot:resolve(this.defaultRoot),custom:!sameRoot(root,this.defaultRoot),minimumDesktop:WORKSPACE_MIN_DESKTOP};}
 async mark(root:string){
  const path=join(root,'.ember-workspace.json');
  let handle;try{handle=await open(path,'wx',0o600);}catch(e:any){if(e.code!=='EEXIST')throw e;const value=JSON.parse(await boundedFile(path,1024));if(value?.format!=='ember.workspace/v1')throw new Error('工作区标记格式不受支持；原文件保留');return;}
  try{await handle.writeFile(JSON.stringify({format:'ember.workspace/v1'})+'\n');await handle.sync();}catch(error){await handle.close();await unlink(path);throw error;}finally{await handle.close().catch(()=>{});}
 }
 async inspect(path:string,activeRoot:string):Promise<WorkspaceInspection>{
  if(typeof path!=='string'||!isAbsolute(path)||path.length>4096||path.startsWith('\\\\'))throw new Error('请选择本机磁盘上的绝对目录；网络共享不适合 SQLite 工作区');
  const root=sameRoot(path,activeRoot)?resolve(activeRoot):resolve(path);await regularDirectory(root);
  if(!sameRoot(root,activeRoot)&&(contains(root,resolve(activeRoot))||contains(resolve(activeRoot),root)))throw new Error('新旧工作区不能互相包含，请选择独立目录');
  if(!sameRoot(root,this.defaultRoot)&&(contains(root,resolve(this.settingsRoot))||contains(resolve(this.settingsRoot),root)))throw new Error('工作区不能包含桌面配置目录，也不能放在其中');
  const names=await readdir(root);let existing=false;
  if(names.length){
   if(!names.includes('launcher.json')){
    if(!names.includes('.ember-workspace.json'))throw new Error('此目录有其他文件，请选择空目录或已有余烬工作区；不会覆盖或接管未知文件');
    const marker=JSON.parse(await boundedFile(join(root,'.ember-workspace.json'),1024));if(marker?.format!=='ember.workspace/v1')throw new Error('工作区标记不受支持，原文件保留');existing=true;
   }else{
   let index:any;try{index=JSON.parse(await boundedFile(join(root,'launcher.json'),8<<20));}catch{throw new Error('已有工作区索引无法读取，原数据保留，请先检查 launcher.json');}
   if(!index||![0,1,undefined].includes(index.schema)||!Array.isArray(index.instances))throw new Error('已有工作区来自不支持的格式，不能接管；原文件保留');existing=true;
   }
  }
  const probe=join(root,'.ember-write-check-'+randomBytes(16).toString('hex'));const handle=await open(probe,'wx',0o600);
  try{await handle.writeFile('workspace write check');await handle.sync();}finally{await handle.close();await unlink(probe);}
  let availableBytes:number|null=null;try{const stats=await statfs(root,{bigint:true}),value=stats.bavail*stats.bsize;availableBytes=value<=BigInt(Number.MAX_SAFE_INTEGER)?Number(value):null;}catch{}
  return {root,existing,availableBytes};
 }
 async save(root:string){
  await regularDirectory(root);await mkdir(this.settingsRoot,{recursive:true});await regularDirectory(this.settingsRoot);
  if(this.fingerprint(await this.encoded())!==this.stamp)throw new Error('工作区位置记录已被其他程序修改，请重新打开桌面后选择');
  const temporary=this.file+'.'+randomBytes(16).toString('hex')+'.tmp';const handle=await open(temporary,'wx',0o600);
  try{const encoded=JSON.stringify({format:'ember.desktop-workspace/v1',root:resolve(root)},null,2)+'\n';await handle.writeFile(encoded);await handle.sync();await handle.close();
   if(this.fingerprint(await this.encoded())!==this.stamp)throw new Error('工作区位置记录已改变，未覆盖');await rename(temporary,this.file);this.stamp=this.fingerprint(encoded);
  }finally{await handle.close().catch(()=>{});await unlink(temporary).catch(()=>{});}
 }
}
