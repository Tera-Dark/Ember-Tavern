import {plainRPCArgs} from '../ipc-payload';
import type {RPCMethod} from '../types';
export async function invoke<T=any>(method:RPCMethod,args:Record<string,any>={}):Promise<T>{
  if(window.emberDesktop)return window.emberDesktop.invoke<T>(method,plainRPCArgs(args));
  if(import.meta.env.DEV){const response=await fetch('/desktop-api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,args})});const value=await response.json();if(!response.ok)throw new Error(value.error||'预览服务未连接');return value;}
  throw new Error('请从余烬桌面 EXE 打开；此页面不是独立的管理接口');
}
