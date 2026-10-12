import {app,BrowserWindow,ipcMain,dialog,shell,clipboard,safeStorage,Menu,Tray,screen} from 'electron';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {mkdirSync} from 'node:fs';
import {EngineClient,HostController,allowedExternal,trustedFrame,id} from './core';
import {importPreset} from './preset-import';
import {exportPreset} from './preset-export';
import {DesktopUpdates,launchInstall} from './updates';
import {PreferencesStore,fitWindow} from './preferences';
import {ConnectionVault} from './connections';
import type {RPCMethod,BuildInfo} from '../types';

let window:BrowserWindow;let engine:EngineClient;let controller:HostController;let rendererURL='';let closing=false;
let updates:DesktopUpdates;
let updateTimer:ReturnType<typeof setInterval>;
let desktopInstalling=false;
const games=new Map<number,{instanceId:string;origin:string}>();
const gameRooms=new Map<number,string>();
let preferences:PreferencesStore;let tray:Tray|undefined;let closePending=false;let boundsTimer:ReturnType<typeof setTimeout>;
let connections:ConnectionVault;let connectionRestoreError='';let runtimeTail:Promise<void>=Promise.resolve();
function serializedRuntime<T>(action:()=>Promise<T>):Promise<T>{const task=runtimeTail.then(action);runtimeTail=task.then(()=>{},()=>{});return task;}
async function waitEngineTask(taskId:string){const deadline=Date.now()+45000;while(Date.now()<deadline){const current=await controller.state(),task=current.tasks.find(t=>t.id===taskId);if(task?.status==='failed')throw new Error(task.error||'停止服务失败');if(task?.status==='success')return;await new Promise(resolve=>setTimeout(resolve,300));}throw new Error('停止服务尚未完成，请在任务中心确认后重试');}
if(process.env.EMBER_DESKTOP_TEST_MODE==='1'&&process.env.EMBER_DESKTOP_TEST_ROOT){const profile=join(process.env.EMBER_DESKTOP_TEST_ROOT,'electron-profile');mkdirSync(profile,{recursive:true});app.setPath('userData',profile);}
if(!app.requestSingleInstanceLock())app.quit();
app.on('second-instance',()=>{window?.show();window?.focus()});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{if(closing)return;event.preventDefault();closing=true;clearInterval(updateTimer);clearTimeout(boundsTimer);Promise.resolve(window&&!window.isDestroyed()?preferences?.update({bounds:window.getNormalBounds(),maximized:window.isMaximized()}).catch(()=>{}):undefined).then(()=>engine?.stop()).finally(()=>{tray?.destroy();for(const item of BrowserWindow.getAllWindows())item.destroy();app.quit();});});

async function openGame(instanceId:string,roomId:string){
  const instance=await controller.instance(id(instanceId));await controller.hostSession(instanceId);
  for(const [contentsId,value] of games){if(value.instanceId===instanceId&&gameRooms.get(contentsId)===roomId){const existing=BrowserWindow.getAllWindows().find(w=>w.webContents.id===contentsId);if(existing&&!existing.isDestroyed()){if(existing.isMinimized())existing.restore();existing.show();existing.focus();return;}}}
  const origin=`http://127.0.0.1:${instance.port}`;
  const game=new BrowserWindow({width:1440,height:940,minWidth:880,title:'余烬酒馆 · 冒险桌',backgroundColor:'#111812',webPreferences:{preload:join(__dirname,'game-preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
  const gameContentsId=game.webContents.id;
  games.set(gameContentsId,{instanceId,origin});gameRooms.set(gameContentsId,roomId);game.on('closed',()=>{games.delete(gameContentsId);gameRooms.delete(gameContentsId);});
  game.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  game.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin!==origin)event.preventDefault()});
  game.webContents.session.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
  await game.loadURL(origin+'/room/'+id(roomId));
}

app.whenReady().then(async()=>{
  Menu.setApplicationMenu(null);
  const resources=app.isPackaged?process.resourcesPath:join(app.getAppPath(),'resources');
  const root=process.env.EMBER_DESKTOP_TEST_ROOT||(process.platform==='win32'?join(process.env.LOCALAPPDATA||app.getPath('userData'),'EmberTavern'):join(app.getPath('userData'),'instances'));
  preferences=new PreferencesStore(root);await preferences.load();
  const build:BuildInfo=JSON.parse(await readFile(join(resources,'host','desktop-bundle.json'),'utf8'));
  if(build.format!=='ember.desktop-build/v1'||!/^([a-f0-9]{40})$/.test(build.commit)||build.desktop_version!==app.getVersion()||typeof build.source_dirty!=='boolean')throw new Error('打包来源清单缺失或与桌面版本不符；请保留实例数据并使用完整安装包。');
  const commit=build.commit;
  engine=new EngineClient({exe:join(resources,'bin',process.platform==='win32'?'ember-engine.exe':'ember-engine'),root,host:join(resources,'host'),commit,build,testPython:process.env.EMBER_DESKTOP_TEST_MODE==='1'?process.env.EMBER_DESKTOP_TEST_PYTHON:undefined});
  try{await engine.start();}catch(error){if(process.env.EMBER_DESKTOP_TEST_MODE==='1')console.error('ENGINE_START_FAILED',String(error));else dialog.showErrorBox('余烬桌面无法启动',String(error));app.quit();return;}
  const secretStorage={encode:(value:string)=>{if(!safeStorage.isEncryptionAvailable()||(process.platform==='linux'&&safeStorage.getSelectedStorageBackend()==='basic_text'))throw new Error('系统凭据加密不可用；不会明文保存凭据');return safeStorage.encryptString(value).toString('base64');},decode:(value:string)=>safeStorage.decryptString(Buffer.from(value,'base64'))};
  controller=new HostController(engine,secretStorage);
  connections=new ConnectionVault(root,secretStorage);await connections.load();
  const restoreConnections=()=>connections.restore((instanceId,values)=>engine.request('/api/instances/'+id(instanceId)+'/runtime-settings','PUT',values));
  try{await restoreConnections();}catch{connectionRestoreError='连接档案未能安全载入，自动启动已暂停。请在应用设置检查档案；原配置与数据保留。';}
  updates=new DesktopUpdates({root,version:app.getVersion(),executable:process.execPath,portable:process.env.PORTABLE_EXECUTABLE_FILE,packaged:app.isPackaged});
  const bounds=fitWindow(preferences.value.bounds,screen.getAllDisplays().map(display=>display.workArea));
  window=new BrowserWindow({...bounds,minWidth:Math.min(760,bounds.width),minHeight:Math.min(520,bounds.height),frame:false,title:'余烬桌面',backgroundColor:'#19161f',autoHideMenuBar:true,webPreferences:{preload:join(__dirname,'preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false,webSecurity:true}});
  if(preferences.value.maximized)window.maximize();
  const rememberBounds=()=>{clearTimeout(boundsTimer);boundsTimer=setTimeout(()=>{if(!window.isDestroyed()&&!window.isMinimized())void preferences.update({bounds:window.getNormalBounds(),maximized:window.isMaximized()}).catch(()=>{});},400);};
  window.on('resize',rememberBounds);window.on('move',rememberBounds);
  const show=()=>{if(window.isMinimized())window.restore();window.show();window.focus();};
  try{tray=new Tray(join(resources,'assets','ember.ico'));tray.setToolTip('余烬桌面 · 房主工作台');tray.on('double-click',show);tray.setContextMenu(Menu.buildFromTemplate([{label:'打开余烬桌面',click:show},{type:'separator'},{label:'退出并停止服务',click:()=>void requestClose(true)}]));}catch(error){if(process.env.EMBER_DESKTOP_TEST_MODE==='1')console.error('TRAY_UNAVAILABLE',String(error));}
  async function requestClose(forceQuit=false){
   if(closePending||closing)return;closePending=true;
   try{
    const current=await controller.state();const tasks=current.tasks.some(t=>t.status==='running');
    if(tasks&&!forceQuit&&tray){window.hide();return;}
    if(tasks){await dialog.showMessageBox(window,{type:'info',title:'酒馆任务仍在进行',message:'环境准备或版本切换尚未完成',detail:'请等待任务结束，或关闭窗口让任务在托盘中继续。原数据和恢复资料会保留。',buttons:['继续等待']});return;}
    const choice=forceQuit?'quit':preferences.value.closeBehavior;
    if(choice==='tray'&&tray){window.hide();return;}
    if(choice==='ask'||choice==='tray'&&!tray){const reply=await dialog.showMessageBox(window,{type:'question',title:'关闭余烬桌面',message:current.instances.some(i=>i.status==='running')?'酒馆仍在运行，同伴可能正在冒险':'选择关闭后的行为',detail:'后台运行会保留服务；退出会停止实例，同伴暂时无法继续。存档不会删除。',buttons:tray?['后台运行','退出并停止服务','取消']:['退出并停止服务','取消'],defaultId:0,cancelId:tray?2:1,checkboxLabel:'记住此选择',checkboxChecked:false});
     if(reply.response===(tray?2:1))return;
     const selected=tray&&reply.response===0?'tray':'quit';if(reply.checkboxChecked)await preferences.update({closeBehavior:selected});if(selected==='tray'){window.hide();return;}
    }
    app.quit();
   }catch{await dialog.showMessageBox(window,{type:'warning',message:'暂时无法确认实例状态',detail:'为保留任务与数据，桌面继续运行。请查看诊断后重试。',buttons:['返回桌面']});}finally{closePending=false;}
  }
  window.on('close',event=>{if(closing)return;event.preventDefault();if(process.env.EMBER_DESKTOP_TEST_MODE==='1'){app.quit();return;}void requestClose();});
  rendererURL=pathToFileURL(join(__dirname,'renderer','index.html')).href;
  window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  window.webContents.on('will-navigate',event=>event.preventDefault());
  window.webContents.session.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
  ipcMain.handle('ember:game-session',async event=>{const game=games.get(event.sender.id);if(!game||event.senderFrame!==event.sender.mainFrame||new URL(event.senderFrame!.url).origin!==game.origin)throw new Error('会话请求被拒绝');return {token:await controller.hostSession(game.instanceId)};});
  ipcMain.handle('ember:desktop',async(event,method:RPCMethod,args:Record<string,any>={})=>{
    if(!trustedFrame(event.sender.id,window.webContents.id,event.senderFrame?.url||'',rendererURL,event.senderFrame===event.sender.mainFrame))throw new Error('桌面请求被拒绝');
    if(!args||typeof args!=='object'||Array.isArray(args)||JSON.stringify(args).length>40000)throw new Error('请求格式错误');
    try{
      if(method==='state')return {...await controller.state(),desktop_updates:updates.snapshot(),connection_error:connections.error||connectionRestoreError||undefined};
      if(method==='desktopPreferences')return preferences.snapshot();
      if(method==='saveDesktopPreferences'){if(!['ask','tray','quit'].includes(args.closeBehavior)||!['dashboard','last'].includes(args.openBehavior))throw new Error('桌面偏好无效');await preferences.update({closeBehavior:args.closeBehavior,openBehavior:args.openBehavior});return preferences.snapshot();}
      if(desktopInstalling&&method!=='window')throw new Error('正在切换桌面版本，请等待重新启动');
      if(method==='connections')return connections.snapshot();
      if(method==='saveConnectionProfile')return connections.save(args);
      if(method==='removeConnectionProfile')return connections.remove(args.profileId);
      if(method==='testConnectionProfile')return connections.test(args.profileId,args.mode,args.paidConfirmed===true);
      if(method==='bindConnectionProfile')return serializedRuntime(async()=>{
        const instanceId=id(args.instanceId),instance=await controller.instance(instanceId);let stopped=false;
        if(instance.status==='busy')throw new Error('请等待实例任务完成');
        if(instance.status==='running'&&args.restart===true){
          const reply=await dialog.showMessageBox(window,{type:'warning',title:'应用连接并重启酒馆',message:'“'+instance.name+'”的所有房间会暂时断线',detail:'先停止服务，再应用连接档案并重新启动。房间进度、身份与内容锁保留；房间模型模式不会修改。请先告知同伴。',buttons:['取消','应用并重启'],defaultId:0,cancelId:0});
          if(reply.response!==1)return {cancelled:true};
          const task=await controller.invoke('instanceAction',{instanceId,action:'stop'});await waitEngineTask(task.id);stopped=true;
        }
        try{
          const result=await connections.bind(instanceId,args.kind,args.profileId,values=>engine.request('/api/instances/'+instanceId+'/runtime-settings','PUT',values));
          if(connectionRestoreError&&!connections.error){try{await restoreConnections();connectionRestoreError='';}catch{/* Other protected bindings still require attention. */}}
          if(stopped)await controller.invoke('instanceAction',{instanceId,action:'start'});
          return result;
        }catch(error){if(stopped&&!connectionRestoreError&&!connections.error)await controller.invoke('instanceAction',{instanceId,action:'start'}).catch(()=>{});throw error;}
      });
      if((connectionRestoreError||connections.error)&&(method==='retryTask'||method==='createInstance'||method==='switchInstanceVersion'||method==='instanceAction'&&['start','install','update'].includes(args.action)))throw new Error(connectionRestoreError||connections.error);
      if(method==='desktopUpdateCheck')return updates.check();
      if(method==='desktopUpdateInstall'){
        if(typeof args.tag!=='string')throw new Error('请选择发行版本');
        if(['downloading','ready','installing'].includes(updates.snapshot().phase))throw new Error('已有版本切换任务');
        const current=await controller.state();if(current.tasks.some(item=>item.status==='running'))throw new Error('请等待实例安装／更新任务完成，再切换桌面版本');
        void (async()=>{
          let stopped=false;
          try{
            const downloaded=await updates.download(args.tag);
            desktopInstalling=true;
            const latest=await controller.state();if(latest.tasks.some(item=>item.status==='running'))throw new Error('实例正在执行任务，安装包已保留，请完成任务后重试');
            await engine.stop();
            stopped=true;
            await updates.markApplying(downloaded.release,latest.instances.filter(item=>item.status==='running').map(item=>item.id));
            await launchInstall({path:downloaded.path,executable:process.execPath,portable:process.env.PORTABLE_EXECUTABLE_FILE,root});
            app.quit();
          }catch(error:any){
            if(stopped)try{await engine.start();await restoreConnections();}catch{connectionRestoreError='引擎或连接档案未恢复；请检查任务与连接设置后重新打开桌面。';}
            desktopInstalling=false;updates.failed(error.message||'桌面版本切换失败');
          }
        })();
        return {started:true};
      }
      if(method==='openGame'){await openGame(args.instanceId,args.roomId);return {opened:true};}
      if(method==='window'){if(args.action==='minimize')window.minimize();else if(args.action==='maximize'){if(window.isMaximized())window.unmaximize();else window.maximize();}else if(args.action==='close')window.close();else throw new Error('不支持的窗口操作');return {};}
      if(method==='clipboard'){if(typeof args.text!=='string'||args.text.length>5000)throw new Error('文字过长');clipboard.writeText(args.text);return {copied:true};}
      if(method==='external'){if(!allowedExternal(args.url))throw new Error('只打开可信 GitHub 文档');await shell.openExternal(args.url);return {};}
      if(method==='exportPreset')return exportPreset(window,controller,id(args.instanceId),args.packageHash);
      if(method==='importPreset')return await importPreset(window,controller,id(args.instanceId));
      if(method==='installPlugin'){
        const instance=await controller.instance(id(args.instanceId));if(instance.status==='running'||instance.status==='busy')throw new Error('请先停止实例再安装插件');
        const selected=await dialog.showOpenDialog(window,{title:'选择已审阅的插件 ZIP',filters:[{name:'插件包',extensions:['zip']}],properties:['openFile']});if(selected.canceled)return {cancelled:true};
        const file=selected.filePaths[0];const bytes=await readFile(file);if(bytes.length>10*1024*1024)throw new Error('插件包超过 10 MiB');const sha=createHash('sha256').update(bytes).digest('hex');
        const approval=await dialog.showMessageBox(window,{type:'warning',title:'审阅与安装插件',message:'插件不是官方自动审核内容',detail:'请先确认来源、SHA256、清单和代码。选择 Python 信任等同允许完整服务器代码执行。\nSHA256: '+sha,buttons:['取消','公共只读 UI','批准 UI 能力（含骰子／声音／GM）','明确信任 Python 后台'],defaultId:0,cancelId:0});
        if(approval.response===0)return {cancelled:true};return engine.request('/api/instances/'+instance.id+'/plugin-install','POST',{path:file,sha256:sha,trust_backend:approval.response===3,grant_capabilities:approval.response>=2});
      }
      if(method==='retryTask'||method==='instanceAction'||method==='switchInstanceVersion'||method==='createInstance')return await serializedRuntime(()=>controller.invoke(method,args));
      return await controller.invoke(method,args);
    }catch(error){throw new Error(error instanceof Error?error.message:'操作失败');}
  });
  await window.loadURL(rendererURL);
  void updates.resumeInstances().then(async ids=>{
    if(connectionRestoreError||connections.error)return;for(const instanceId of ids)await serializedRuntime(()=>engine.request('/api/instances/'+id(instanceId)+'/start','POST',{})).catch(()=>{});
  }).catch(()=>{});
  if(process.env.EMBER_DESKTOP_TEST_MODE!=='1'){
    const checkAll=async()=>{
      await updates.check();
      const state=await controller.state();
      for(const instance of state.instances)if(instance.commit)await engine.request('/api/instances/'+instance.id+'/check','POST',{}).catch(()=>{});
    };
    void checkAll().catch(()=>{});
    updateTimer=setInterval(()=>void checkAll().catch(()=>{}),6*60*60*1000);updateTimer.unref();
  }
  if(process.env.EMBER_DESKTOP_TEST_MODE==='1')await window.webContents.executeJavaScript('window.__desktopSmoke = true');
}).catch(error=>{if(!closing){if(process.env.EMBER_DESKTOP_TEST_MODE==='1')console.error('DESKTOP_START_FAILED',String(error));else dialog.showErrorBox('余烬桌面',String(error));}app.quit()});
