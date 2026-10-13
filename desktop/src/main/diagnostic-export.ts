import {dialog,type BrowserWindow} from 'electron';
import {writeFile} from 'node:fs/promises';
import type {HostController} from './core';
import {diagnosticReport} from './diagnostic-report';
export async function exportDiagnostics(window:BrowserWindow,controller:HostController,instanceId:string){
 const instance=await controller.instance(instanceId),state=await controller.state();
 const [checks,settings]=await Promise.all([controller.diagnostics(instanceId),controller.engine.request('/api/instances/'+instanceId+'/settings')]);
 const report=diagnosticReport(state,instance,checks,settings);
 const choice=await dialog.showSaveDialog(window,{title:'保存诊断摘要（不包含密钥、地址、房间和日志正文）',defaultPath:'ember-diagnostics-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json',filters:[{name:'诊断摘要',extensions:['json']}]});
 if(choice.canceled||!choice.filePath)return {cancelled:true};
 try{await writeFile(choice.filePath,JSON.stringify(report,null,2)+'\n',{mode:0o600,flag:'wx'});}catch(e:any){if(e.code==='EEXIST')throw new Error('请选择新的诊断文件名，原文件保留');throw new Error('诊断摘要保存失败，请检查所选位置的空间与权限');}
 return {exported:true};
}
