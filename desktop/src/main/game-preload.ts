import {contextBridge,ipcRenderer} from 'electron';
if(process.isMainFrame)contextBridge.exposeInMainWorld('emberGame',{session:()=>ipcRenderer.invoke('ember:game-session')});
