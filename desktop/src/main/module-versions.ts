import {dialog,type BrowserWindow} from 'electron';
import {randomBytes,createHash} from 'node:crypto';
import {lstat,readFile} from 'node:fs/promises';
import {id,type HostController} from './core';
import type {ModulePreview,ModuleRecord} from '../types';
type Ticket={instanceId:string;path:string;sha:string;oldHash:string;expires:number};
export class ModuleVersions {
 private tickets=new Map<string,Ticket>();
 constructor(readonly controller:HostController,readonly submit:<T>(action:()=>Promise<T>)=>Promise<T>=action=>action(),readonly dialogs:typeof dialog=dialog){}
 private async run(instanceId:string,request:Record<string,any>,wait=true){const call=()=>this.controller.engine.request('/api/instances/'+id(instanceId)+'/module-versions','POST',request);const task=wait?await call():await this.submit(async()=>{const instance=await this.controller.instance(instanceId);if(instance.status==='running'||instance.status==='busy')throw new Error('此酒馆已开始运行或其他任务，请停止后重新检查');return call();});if(!wait)return {task};const deadline=Date.now()+65000;while(Date.now()<deadline){const reply=await this.controller.engine.request('/api/creator-results/'+id(task.id));if(reply.done){if(reply.error)throw new Error(reply.error);return {result:reply.result};}await new Promise(r=>setTimeout(r,250));}throw new Error('模块检查仍在处理，请在任务中心确认后重试');}
 async invoke(window:BrowserWindow,method:string,args:Record<string,any>){
  const instanceId=id(args.instanceId),instance=await this.controller.instance(instanceId);
  if(method==='moduleHistory')return this.run(instanceId,{operation:'history'});
  if(method==='modulePreview'){
   for(const [key,value] of this.tickets)if(value.expires<Date.now())this.tickets.delete(key);if(this.tickets.size>=20)throw new Error('请关闭旧预览后重新选择');
   const choice=await this.dialogs.showOpenDialog(window,{title:'选择已审阅的新模块 ZIP',properties:['openFile'],filters:[{name:'模块版本包',extensions:['zip']}]});if(choice.canceled||!choice.filePaths[0])return {cancelled:true};const path=choice.filePaths[0],info=await lstat(path);if(!info.isFile()||info.isSymbolicLink()||info.size>10<<20)throw new Error('模块包必须是普通 ZIP 且不超过 10 MiB');const sha=createHash('sha256').update(await readFile(path)).digest('hex');
   const value=await this.run(instanceId,{operation:'preview',archive:path,sha256:sha}),result=value.result as ModulePreview;if(!result.ok)return value;const ticket=randomBytes(16).toString('hex');this.tickets.set(ticket,{instanceId,path,sha,oldHash:result.old_hash,expires:Date.now()+5*60*1000});return {result,ticket};
  }
  if(instance.status==='running'||instance.status==='busy')throw new Error('先停止酒馆并等待任务结束，再变更模块');
  if(method==='moduleUpgrade'){
   const key=id(args.ticket),ticket=this.tickets.get(key);if(!ticket||ticket.instanceId!==instanceId||ticket.expires<Date.now())throw new Error('预览已过期，请重新选择版本包');
   const checked=await this.run(instanceId,{operation:'preview',archive:ticket.path,sha256:ticket.sha}),preview=checked.result as ModulePreview;if(!preview.ok||!preview.can_upgrade||preview.old_hash!==ticket.oldHash)throw new Error('模块或版本锁已改变 / 不兼容，请重新预览');
   if(preview.backend&&args.trustBackend!==true||preview.capability_grant&&!preview.backend&&args.grantCapabilities!==true)throw new Error('请先明确审阅并授信所需代码 / 能力');
   const reply=await this.dialogs.showMessageBox(window,{type:'warning',title:'备份后升级模块',message:preview.plugin_id+' · '+preview.old_version+' → '+preview.new_version,detail:'旧代码与模块数据保留，先创建完整备份，再在数据库副本迁移与预检。失败恢复原版，完成保持停止等待复核。\nSHA256：'+preview.archive_sha256+'\n'+(preview.backend?'你已选择信任完整 Python 服务器代码并执行迁移，拥有文件 / 网络等权限；备份不能撤销外部副作用。':'界面能力仅按你的选择批准。')+'\n不修改旧房间的内容、规则或模块 pins。',buttons:['取消','备份并升级'],defaultId:0,cancelId:0});if(reply.response!==1)return {cancelled:true};
   const result=await this.run(instanceId,{operation:'upgrade',archive:ticket.path,sha256:ticket.sha,old_hash:ticket.oldHash,trust_backend:args.trustBackend===true,grant_capabilities:args.grantCapabilities===true},false);this.tickets.delete(key);return result;
  }
  if(method==='moduleRollback'){
   const checkpointId=id(args.checkpointId),history=await this.run(instanceId,{operation:'history'});if(!history.result?.ok)throw new Error('模块记录需要检查，原文件保留');const record:ModuleRecord=history.result.records.find((r:ModuleRecord)=>r.id===checkpointId);if(!record?.can_rollback)throw new Error('此快照不匹配当前模块或有精确版本锁，请刷新后检查');
   if(record.backend&&args.trustBackend!==true||record.capability_grant&&!record.backend&&args.grantCapabilities!==true)throw new Error('回退代码 / 能力也需明确重新审阅');
   const reply=await this.dialogs.showMessageBox(window,{type:'warning',title:'回退模块与模块数据',message:record.plugin_id+' · '+record.new_version+' → '+record.old_version,detail:'先备份当前全部进度。仅此模块的数据恢复到切换前；其余当前剧情、规则、内容锁、成员、会话、角色分配与邀请权限保持。新建房间没有旧模块数据的会重新初始化此模块。\n较新的模块数据保存在新的完整备份与快照，操作完成保持停止。\n旧代码 SHA256：'+record.old_hash+'\n'+(record.backend?'将执行你明确授信的旧 Python 代码；外部副作用不能通过备份撤销。':'原界面能力只按你的选择批准。'),buttons:['取消','备份并回退此模块'],defaultId:0,cancelId:0});if(reply.response!==1)return {cancelled:true};return this.run(instanceId,{operation:'rollback',checkpoint_id:checkpointId,trust_backend:args.trustBackend===true,grant_capabilities:args.grantCapabilities===true},false);
  }
  throw new Error('不支持的模块版本操作');
 }
}
