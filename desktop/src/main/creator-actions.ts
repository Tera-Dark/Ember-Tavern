import {dialog,shell,type BrowserWindow} from 'electron';
import {join,dirname} from 'node:path';
import {lstat} from 'node:fs/promises';
import {id,type HostController} from './core';
import {CreatorProjects,creatorDirectory,creatorOutside} from './creator-projects';
const templates=['worldbook','character','theme','scenario','preset','plugin-ui','plugin-backend','plugin-dice','plugin-campaign'];
const operations=['inspect','metadata','validate','lock','package','publication'];
async function run(controller:HostController,instanceId:string,request:Record<string,unknown>){
 const task=await controller.engine.request('/api/instances/'+id(instanceId)+'/creator','POST',request),deadline=Date.now()+65000;
 while(Date.now()<deadline){const reply=await controller.engine.request('/api/creator-results/'+id(task.id));if(reply.done){if(reply.error)throw new Error(reply.error);return reply.result;}await new Promise(r=>setTimeout(r,250));}
 throw new Error('创作任务仍在处理，请在任务中心确认后刷新作品；原稿保留');
}
export async function creatorAction(window:BrowserWindow,controller:HostController,projects:CreatorProjects,method:string,args:Record<string,any>,protectedRoots:string[]=[]){
 if(method==='creatorProjects')return projects.snapshot();
 if(projects.error)throw new Error(projects.error);
 if(method==='creatorForget'){const p=projects.get(args.projectId);const choice=await dialog.showMessageBox(window,{type:'question',message:'从列表移除“'+p.name+'”？',detail:'只移除本机目录记录，草稿、素材与发行包全部保留。',buttons:['取消','移除记录'],defaultId:0,cancelId:0});return choice.response===1?projects.forget(p.id):{cancelled:true};}
 const instanceId=id(args.instanceId);await controller.instance(instanceId);
 const excluded=[controller.engine.options.root,controller.engine.options.host,...protectedRoots];
 if(method==='creatorOpen'){
  const choice=await dialog.showOpenDialog(window,{title:'打开已有创作目录',properties:['openDirectory']});if(choice.canceled||!choice.filePaths[0])return {cancelled:true};
  const directory=await creatorDirectory(choice.filePaths[0]);creatorOutside(directory,excluded);
  const result=await run(controller,instanceId,{operation:'inspect',directory});if(result.ok){await projects.register(directory,result.kind,result.metadata.name);return {result,project:projects.snapshot().projects.find(p=>p.directory===directory)};}return {result};
 }
 if(method==='creatorCreate'){
  if(!templates.includes(args.kind)||typeof args.identity!=='string'||! /^[a-z][a-z0-9-]{2,47}$/.test(args.identity)||typeof args.name!=='string'||!args.name.trim()||args.name.length>80)throw new Error('请选择模板，填写 3–48 位小写 ID 与作品名称');
  const choice=await dialog.showOpenDialog(window,{title:'选择独立创作目录的父文件夹',properties:['openDirectory','createDirectory']});if(choice.canceled||!choice.filePaths[0])return {cancelled:true};
  const parent=await creatorDirectory(choice.filePaths[0]),directory=join(parent,args.identity);creatorOutside(directory,excluded);
  const result=await run(controller,instanceId,{operation:'create',directory,kind:args.kind,identity:args.identity,name:args.name.trim()});if(result.ok){await projects.register(directory,result.kind,result.metadata.name);return {result,project:projects.snapshot().projects.find(p=>p.directory===directory)};}return {result};
 }
 const project=projects.get(args.projectId),directory=await creatorDirectory(project.directory);creatorOutside(directory,excluded);
 if(method==='creatorFolder'){const error=await shell.openPath(directory);if(error)throw new Error('未能打开作品文件夹，请在本机检查');return {opened:true};}
 if(method!=='creatorOperate'||!operations.includes(args.operation))throw new Error('不支持的创作操作');
 const request:Record<string,unknown>={operation:args.operation,directory,revision:args.revision};
 if(args.operation==='metadata'){if(!args.metadata||typeof args.metadata!=='object'||Array.isArray(args.metadata)||Object.keys(args.metadata).some(k=>!['name','version','description','authors','license','tags'].includes(k)))throw new Error('作品信息字段不受支持');request.metadata=args.metadata;}
 if(args.operation==='lock'&&args.refreshPlugins===true){const approval=await dialog.showMessageBox(window,{type:'warning',message:'明确更新此草稿的内容锁与模块版本？',detail:'将刷新草稿中已声明模块的本机精确版本和散列。运行中的房间与旧作品包均保留，不安装或执行模块。',buttons:['取消','更新草稿内容锁'],defaultId:0,cancelId:0});if(approval.response!==1)return {cancelled:true};request.refresh_plugins=true;}
 if(args.operation==='package'){
  const suffix=project.kind==='preset'||project.kind==='plugin'?'zip':'json';const choice=await dialog.showSaveDialog(window,{title:'保存新的作品版本包（不会上传）',defaultPath:project.name+'.'+suffix,filters:[{name:'作品版本包',extensions:[suffix]}]});if(choice.canceled||!choice.filePath)return {cancelled:true};
  const output=choice.filePath;await creatorDirectory(dirname(output));creatorOutside(output,[...excluded,directory]);try{await lstat(output);throw new Error('请选择新的文件名，已有作品包不会覆盖');}catch(e:any){if(e.code!=='ENOENT')throw e;}request.output=output;
 }
 const result=await run(controller,instanceId,request);if(result.ok&&result.metadata)await projects.register(directory,result.kind,result.metadata.name);return {result};
}
