import {contextBridge,ipcRenderer} from 'electron';
import type {RPCMethod} from '../types';
contextBridge.exposeInMainWorld('emberDesktop',{kind:'native',invoke:(method:RPCMethod,args:Record<string,unknown>={})=>ipcRenderer.invoke('ember:desktop',method,args)});
