import {app,BrowserWindow,ipcMain,dialog,shell,clipboard,safeStorage,Menu} from 'electron';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {EngineClient,HostController,allowedExternal,trustedFrame,id} from './core';
import {importPreset} from './preset-import';
import type {RPCMethod,BuildInfo} from '../types';

let window:BrowserWindow;let engine:EngineClient;let controller:HostController;let rendererURL='';let closing=false;
const games=new Map<number,{instanceId:string;origin:string}>();
if(!app.requestSingleInstanceLock())app.quit();
app.on('second-instance',()=>{window?.show();window?.focus()});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{if(closing)return;event.preventDefault();closing=true;Promise.resolve(engine?.stop()).finally(()=>{for(const item of BrowserWindow.getAllWindows())item.destroy();app.quit();});});

async function openGame(instanceId:string,roomId:string){
  const instance=await controller.instance(id(instanceId));await controller.hostSession(instanceId);
  const origin=`http://127.0.0.1:${instance.port}`;
  const game=new BrowserWindow({width:1440,height:940,minWidth:880,title:'余烬酒馆 · 冒险桌',backgroundColor:'#111812',webPreferences:{preload:join(__dirname,'game-preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
  const gameContentsId=game.webContents.id;
  games.set(gameContentsId,{instanceId,origin});game.on('closed',()=>games.delete(gameContentsId));
  game.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  game.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin!==origin)event.preventDefault()});
  game.webContents.session.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
  await game.loadURL(origin+'/room/'+id(roomId));
}

app.whenReady().then(async()=>{
  Menu.setApplicationMenu(null);
  const resources=app.isPackaged?process.resourcesPath:join(app.getAppPath(),'resources');
  const root=process.env.EMBER_DESKTOP_TEST_ROOT||(process.platform==='win32'?join(process.env.LOCALAPPDATA||app.getPath('userData'),'EmberTavern'):join(app.getPath('userData'),'instances'));
  const build:BuildInfo=JSON.parse(await readFile(join(resources,'host','desktop-bundle.json'),'utf8'));
  if(build.format!=='ember.desktop-build/v1'||!/^([a-f0-9]{40})$/.test(build.commit)||build.desktop_version!==app.getVersion()||typeof build.source_dirty!=='boolean')throw new Error('打包来源清单缺失或与桌面版本不符；请保留实例数据并使用完整安装包。');
  const commit=build.commit;
  engine=new EngineClient({exe:join(resources,'bin',process.platform==='win32'?'ember-engine.exe':'ember-engine'),root,host:join(resources,'host'),commit,build,testPython:process.env.EMBER_DESKTOP_TEST_MODE==='1'?process.env.EMBER_DESKTOP_TEST_PYTHON:undefined});
  try{await engine.start();}catch(error){if(process.env.EMBER_DESKTOP_TEST_MODE==='1')console.error('ENGINE_START_FAILED',String(error));else dialog.showErrorBox('余烬桌面无法启动',String(error));app.quit();return;}
  controller=new HostController(engine,{encode:value=>{if(!safeStorage.isEncryptionAvailable()||(process.platform==='linux'&&safeStorage.getSelectedStorageBackend()==='basic_text'))throw new Error('系统凭据加密不可用；不会明文保存房主密码');return safeStorage.encryptString(value).toString('base64');},decode:value=>safeStorage.decryptString(Buffer.from(value,'base64'))});
  window=new BrowserWindow({width:1380,height:920,minWidth:1020,minHeight:720,title:'余烬桌面',backgroundColor:'#131713',autoHideMenuBar:true,webPreferences:{preload:join(__dirname,'preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false,webSecurity:true}});
  rendererURL=pathToFileURL(join(__dirname,'renderer','index.html')).href;
  window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  window.webContents.on('will-navigate',event=>event.preventDefault());
  window.webContents.session.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
  ipcMain.handle('ember:game-session',async event=>{const game=games.get(event.sender.id);if(!game||event.senderFrame!==event.sender.mainFrame||new URL(event.senderFrame!.url).origin!==game.origin)throw new Error('会话请求被拒绝');return {token:await controller.hostSession(game.instanceId)};});
  ipcMain.handle('ember:desktop',async(event,method:RPCMethod,args:Record<string,any>={})=>{
    if(!trustedFrame(event.sender.id,window.webContents.id,event.senderFrame?.url||'',rendererURL,event.senderFrame===event.sender.mainFrame))throw new Error('桌面请求被拒绝');
    if(!args||typeof args!=='object'||Array.isArray(args)||JSON.stringify(args).length>40000)throw new Error('请求格式错误');
    try{
      if(method==='openGame'){await openGame(args.instanceId,args.roomId);return {opened:true};}
      if(method==='window'){if(args.action==='minimize')window.minimize();else if(args.action==='close')window.close();return {};}
      if(method==='clipboard'){if(typeof args.text!=='string'||args.text.length>5000)throw new Error('文字过长');clipboard.writeText(args.text);return {copied:true};}
      if(method==='external'){if(!allowedExternal(args.url))throw new Error('只打开可信 GitHub 文档');await shell.openExternal(args.url);return {};}
      if(method==='importPreset')return await importPreset(window,controller,id(args.instanceId));
      if(method==='installPlugin'){
        const instance=await controller.instance(id(args.instanceId));if(instance.status==='running'||instance.status==='busy')throw new Error('请先停止实例再安装插件');
        const selected=await dialog.showOpenDialog(window,{title:'选择已审阅的插件 ZIP',filters:[{name:'插件包',extensions:['zip']}],properties:['openFile']});if(selected.canceled)return {cancelled:true};
        const file=selected.filePaths[0];const bytes=await readFile(file);if(bytes.length>10*1024*1024)throw new Error('插件包超过 10 MiB');const sha=createHash('sha256').update(bytes).digest('hex');
        const approval=await dialog.showMessageBox(window,{type:'warning',title:'审阅与安装插件',message:'插件不是官方自动审核内容',detail:'请先确认来源、SHA256、清单和代码。选择 Python 信任等同允许完整服务器代码执行。\nSHA256: '+sha,buttons:['取消','公共只读 UI','批准 UI 能力（含骰子／声音／GM）','明确信任 Python 后台'],defaultId:0,cancelId:0});
        if(approval.response===0)return {cancelled:true};return engine.request('/api/instances/'+instance.id+'/plugin-install','POST',{path:file,sha256:sha,trust_backend:approval.response===3,grant_capabilities:approval.response>=2});
      }
      return await controller.invoke(method,args);
    }catch(error){throw new Error(error instanceof Error?error.message:'操作失败');}
  });
  await window.loadURL(rendererURL);
  if(process.env.EMBER_DESKTOP_TEST_MODE==='1')await window.webContents.executeJavaScript('window.__desktopSmoke = true');
}).catch(error=>{if(!closing){if(process.env.EMBER_DESKTOP_TEST_MODE==='1')console.error('DESKTOP_START_FAILED',String(error));else dialog.showErrorBox('余烬桌面',String(error));}app.quit()});
