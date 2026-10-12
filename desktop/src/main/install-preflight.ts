import type {EngineClient} from './core';
import {WorkspaceLocationStore} from './workspace-location';

export interface InstallPreflight {root:string;port:number;availableBytes:number|null;pythonVersion:string;pythonBytes:number|null;checks:{id:string;status:'passed'|'warning';detail:string}[]}
async function checkURL(value:string,python:boolean,fetcher:typeof fetch){
 const url=new URL(value);
 if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||url.port||url.hostname!==(python?'www.python.org':'pypi.org'))throw new Error('安装下载来源不受支持');
 try{const response=await fetcher(url.href,{method:'HEAD',redirect:'error',signal:AbortSignal.timeout(10000)});await response.body?.cancel();
  const size=Number(response.headers.get('content-length'));return {passed:response.ok,bytes:response.ok&&Number.isSafeInteger(size)&&size>0?size:null};
 }catch{return {passed:false,bytes:null};}
}
export async function installPreflight(engine:EngineClient,locations:WorkspaceLocationStore,port:unknown,fetcher:typeof fetch=fetch):Promise<InstallPreflight>{
 if(typeof port!=='number'||!Number.isInteger(port)||port!==0&&(port<1024||port>65535))throw new Error('端口需在 1024–65535，或留空自动选择');
 const [plan,directory]=await Promise.all([engine.request('/api/install-plan?port='+port),locations.inspect(engine.options.root,engine.options.root)]);
 const [python,dependencies]=await Promise.all([checkURL(plan.python_url,true,fetcher),checkURL(plan.dependency_url,false,fetcher)]);
 const space=directory.availableBytes!==null&&python.bytes!==null&&directory.availableBytes<python.bytes;
 if(space)throw new Error('剩余空间连 Python 下载包都无法容纳，请选择其他工作区或先释放空间');
 return {root:engine.options.root,port:plan.port,availableBytes:directory.availableBytes,pythonVersion:plan.python_version,pythonBytes:python.bytes,checks:[
 {id:'directory',status:'passed',detail:'工作区可写；原数据与环境不覆盖'},
 {id:'port',status:'passed',detail:'当前端口 '+plan.port+' 可用；创建与启动时会再次检查'},
 {id:'python',status:python.passed?'passed':'warning',detail:python.passed?'Python 官方下载地址可访问':'尚未确认 Python 下载可用，可能离线、代理受限或不支持 HEAD；安装会再次尝试'},
 {id:'dependencies',status:dependencies.passed?'passed':'warning',detail:dependencies.passed?'PyPI 索引可访问；具体锁定依赖仍需安装时校验':'尚未确认 PyPI 可访问；已有缓存是否足够以安装结果为准'}]};
}
