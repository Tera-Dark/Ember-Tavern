import {dialog,type BrowserWindow} from 'electron';
import {readFile,lstat} from 'node:fs/promises';
import {basename} from 'node:path';
import type {HostController} from './core';
import {presetPayload} from '../preset-file';

/** Native file selection only; renderer cannot supply paths or code grants. */
export async function importPreset(window:BrowserWindow,controller:HostController,instanceId:string){
  const instance=await controller.instance(instanceId);
  if(instance.status!=='running')throw new Error('先启动支持玩法预设的宿主，再导入数据包');
  const choice=await dialog.showOpenDialog(window,{title:'选择玩法预设数据包',filters:[{name:'数据包',extensions:['zip','json']}],properties:['openFile']});
  if(choice.canceled)return {cancelled:true};
  const path=choice.filePaths[0],info=await lstat(path);
  if(!info.isFile()||info.isSymbolicLink()||info.size>2*1024*1024)throw new Error('预设文件需为普通小型 ZIP / JSON；不会执行代码');
  const payload=presetPayload(await readFile(path),basename(path));
  const preview=await controller.game(instanceId,'/presets/preview','POST',payload);
  const summary=preview.summary;
  const details=[`作品：${summary.name} @ ${summary.version}`,`数据散列：${preview.package_hash}`,
    `许可：${summary.license||'未声明'}。分享前确认各组件授权。`,
    `${summary.character_count} 张角色卡 / ${summary.scene_count} 个场景 / ${summary.ending_count} 个结局`,
    ...summary.warnings,...preview.compatibility.blockers,...preview.compatibility.warnings,
    '只写入你自己的本机数据作品库；不创建房间，不下载依赖，不授予 JS / Python / 高风险能力。'].join('\n').slice(0,6000);
  const approval=await dialog.showMessageBox(window,{type:'warning',title:'确认数据预设导入',message:'预览不会执行包内代码。请检查来源、内容提醒和许可。',detail:details,buttons:['取消','确认只导入数据'],defaultId:0,cancelId:0});
  if(approval.response!==1)return {cancelled:true};
  return controller.game(instanceId,'/presets/import','POST',{...payload,expected_hash:preview.package_hash,confirm_data_only:true});
}
