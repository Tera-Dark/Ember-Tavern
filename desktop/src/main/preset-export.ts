import {dialog,type BrowserWindow} from 'electron';
import {writeFile} from 'node:fs/promises';
import {packageHash,type HostController} from './core';
/** Only an owner-authorized, exact installed data package; no renderer path. */
export async function exportPreset(window:BrowserWindow,controller:HostController,instanceId:string,hash:string){
 packageHash(hash);const instance=await controller.instance(instanceId);if(instance.status!=='running')throw new Error('请先启动酒馆再导出作品');
 const token=await controller.hostSession(instanceId);
 const response=await fetch(`http://127.0.0.1:${instance.port}/api/presets/${hash}/export`,{headers:{'X-Ember-Session':token},signal:AbortSignal.timeout(15000),redirect:'error'});
 if(!response.ok){await response.body?.cancel();throw new Error('预设导出失败；只能导出自己可读取的完整数据作品');}
 const reader=response.body?.getReader();if(!reader)throw new Error('预设导出响应为空');const chunks:Uint8Array[]=[];let size=0;
 try{while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>2*1024*1024)throw new Error('预设导出超过大小限制');chunks.push(value);}}catch(e){await reader.cancel().catch(()=>{});throw e;}finally{reader.releaseLock();}
 const bytes=Buffer.concat(chunks);if(bytes.length<4||bytes[0]!==0x50||bytes[1]!==0x4b)throw new Error('预设导出格式无效');
 const choice=await dialog.showSaveDialog(window,{title:'保存完整作品（可能包含主持秘密，分享前检查许可与内容）',defaultPath:'ember-preset-'+hash.slice(0,12)+'.zip',filters:[{name:'玩法预设',extensions:['zip']}]});
 if(choice.canceled||!choice.filePath)return {cancelled:true};
 try{await writeFile(choice.filePath,bytes,{flag:'wx',mode:0o600});}catch(e:any){if(e.code==='EEXIST')throw new Error('请选择新文件名；导出不会覆盖既有作品');throw new Error('作品未能完整保存，请检查所选位置的空间与权限');}
 return {exported:true};
}
