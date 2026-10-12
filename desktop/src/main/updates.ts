import {createHash,randomBytes} from 'node:crypto';
import {mkdir,readFile,writeFile,rename,open,unlink,lstat} from 'node:fs/promises';
import {dirname,join,resolve} from 'node:path';
import {spawn} from 'node:child_process';
import type {DesktopRelease,DesktopUpdateState} from '../types';

const REPOSITORY='Tera-Dark/Ember-Tavern';
const API='https://api.github.com/repos/'+REPOSITORY;
const VERSION=/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;
function versionParts(value:string){
  const match=VERSION.exec(value);
  if(!match||match[4]?.split('.').some(x=>/^\d+$/.test(x)&&x.length>1&&x[0]==='0'))throw new Error('无效版本号');
  return {core:match.slice(1,4).map(BigInt),pre:match[4]?.split('.')||[]};
}
export function compareVersions(a:string,b:string):number{
  const x=versionParts(a),y=versionParts(b);
  for(let i=0;i<3;i++)if(x.core[i]!==y.core[i])return x.core[i]>y.core[i]?1:-1;
  if(!x.pre.length||!y.pre.length)return x.pre.length===y.pre.length?0:!x.pre.length?1:-1;
  for(let i=0;i<Math.min(x.pre.length,y.pre.length);i++){
    const p=x.pre[i],q=y.pre[i];if(p===q)continue;
    const pn=/^\d+$/.test(p),qn=/^\d+$/.test(q);
    if(pn&&qn)return BigInt(p)>BigInt(q)?1:-1;
    if(pn!==qn)return pn?-1:1;
    return p>q?1:-1;
  }
  return Math.sign(x.pre.length-y.pre.length);
}
export function releaseAssetURL(value:string):string{
  const u=new URL(value);
  if(u.protocol!=='https:'||u.hostname!=='github.com'||u.port||u.username||u.password||u.search||u.hash||!u.pathname.startsWith('/'+REPOSITORY+'/releases/download/'))throw new Error('发行下载地址不可信');
  return u.href;
}
function downloadDestination(value:string){
  const u=new URL(value);
  if(u.protocol!=='https:'||u.username||u.password||u.port||!['github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'].includes(u.hostname))throw new Error('下载重定向不可信');
  return u.href;
}
async function request(url:string,max:number,fetcher:typeof fetch,redirects=0):Promise<Response>{
  const response=await fetcher(url,{headers:{'User-Agent':'Ember-Desktop','Accept':'application/vnd.github+json'},signal:AbortSignal.timeout(60000),redirect:'manual'});
  if([301,302,303,307,308].includes(response.status)){
    await response.body?.cancel();
    const location=response.headers.get('location');if(!location||redirects>=5)throw new Error('下载重定向过多');
    return request(downloadDestination(new URL(location,url).href),max,fetcher,redirects+1);
  }
  if(!response.ok)throw new Error(response.status===403||response.status===429?'GitHub 请求受限，请稍后重试':'GitHub 请求失败（HTTP '+response.status+'）');
  if(Number(response.headers.get('content-length'))>max){await response.body?.cancel();throw new Error('下载文件超过大小限制');}
  return response;
}
async function boundedText(response:Response,max:number):Promise<string>{
  if(!response.body)throw new Error('GitHub 返回空内容');
  const chunks:Uint8Array[]=[];let size=0;
  for await(const chunk of response.body as any){size+=chunk.length;if(size>max){await response.body.cancel().catch(()=>{});throw new Error('GitHub 内容超过大小限制');}chunks.push(chunk);}
  return Buffer.concat(chunks).toString('utf8');
}
type Preferences={lastVersion?:string;ignoredThrough?:string;resume?:string[];pending?:{from:string;to:string;ignore?:string;resume?:string[]}};
export interface UpdateOptions{root:string;version:string;executable:string;portable?:string;packaged:boolean;platform?:string;fetcher?:typeof fetch}

export class DesktopUpdates{
  private prefs:Preferences={};private initialized=false;private checking?:Promise<DesktopUpdateState>;private applying=false;
  private initializing?:Promise<void>;
  private releases:DesktopRelease[]=[];
  private state:DesktopUpdateState;
  constructor(readonly options:UpdateOptions){
    versionParts(options.version);
    this.state={current:options.version,phase:'idle',available:false,suppressed:false,percent:0,releases:[],can_install:options.packaged&&(options.platform||process.platform)==='win32'};
  }
  snapshot():DesktopUpdateState{return structuredClone(this.state);}
  private get preferencePath(){return join(this.options.root,'desktop-updates.json');}
  private async save(){
    await mkdir(this.options.root,{recursive:true});
    await writeFile(this.preferencePath+'.tmp',JSON.stringify(this.prefs,null,2)+'\n',{mode:0o600});
    await rename(this.preferencePath+'.tmp',this.preferencePath);
  }
  private async initialize(){
    if(this.initialized)return;
    if(!this.initializing)this.initializing=this.loadPreferences().finally(()=>{this.initializing=undefined;});
    return this.initializing;
  }
  private async loadPreferences(){
    try{
      const info=await lstat(this.preferencePath);if(!info.isFile()||info.isSymbolicLink()||info.size>16384)throw new Error('更新偏好文件无效');
      const data=JSON.parse(await readFile(this.preferencePath,'utf8'));
      if(!data||typeof data!=='object'||Array.isArray(data))throw new Error('更新偏好文件无效');
      for(const key of ['lastVersion','ignoredThrough'])if(data[key]!==undefined)versionParts(data[key]);
      if(data.pending){versionParts(data.pending.from);versionParts(data.pending.to);if(data.pending.ignore)versionParts(data.pending.ignore);}
      for(const ids of [data.resume,data.pending?.resume])if(ids!==undefined&&(!Array.isArray(ids)||ids.length>24||ids.some((x:any)=>typeof x!=='string'||!/^[a-f0-9]{32}$/.test(x))))throw new Error('实例恢复列表无效');
      this.prefs=data;
    }catch(error:any){if(error.code!=='ENOENT')throw new Error('无法读取更新偏好，请保留 desktop-updates.json 后重试');}
    if(this.prefs.pending&&(this.prefs.pending.to===this.options.version||this.prefs.pending.from===this.options.version))this.prefs.resume=this.prefs.pending.resume;
    if(this.prefs.pending?.to===this.options.version){this.prefs.ignoredThrough=this.prefs.pending.ignore;delete this.prefs.pending;}
    else if(this.prefs.lastVersion&&compareVersions(this.options.version,this.prefs.lastVersion)<0){
      // Also recognize an intentional downgrade performed with a downloaded installer.
      if(!this.prefs.ignoredThrough||compareVersions(this.prefs.lastVersion,this.prefs.ignoredThrough)>0)this.prefs.ignoredThrough=this.prefs.lastVersion;
      delete this.prefs.pending;
    }else if(this.prefs.pending){delete this.prefs.pending;}
    this.prefs.lastVersion=this.options.version;await this.save();this.initialized=true;
  }
  async resumeInstances():Promise<string[]>{await this.initialize();const ids=this.prefs.resume||[];delete this.prefs.resume;await this.save();return ids;}
  private availability(){
    const latest=this.releases[0];this.state.latest=latest;
    this.state.suppressed=!!latest&&!!this.prefs.ignoredThrough&&compareVersions(latest.version,this.prefs.ignoredThrough)<=0&&compareVersions(latest.version,this.options.version)>0;
    this.state.available=!!latest&&compareVersions(latest.version,this.options.version)>0&&!this.state.suppressed;
  }
  async check():Promise<DesktopUpdateState>{
    if(this.checking)return this.checking;
    if(this.applying)return this.snapshot();
    this.checking=this.refresh().finally(()=>{this.checking=undefined;});return this.checking;
  }
  private async refresh():Promise<DesktopUpdateState>{
    this.state.phase='checking';this.state.error=undefined;
    try{
      await this.initialize();const fetcher=this.options.fetcher||fetch;const releases:DesktopRelease[]=[];
      let complete=false;
      for(let page=1;page<=20;page++){
        const response=await request(API+'/releases?per_page=100&page='+page,4<<20,fetcher);
        const rows=JSON.parse(await boundedText(response,4<<20));if(!Array.isArray(rows))throw new Error('GitHub 版本目录无效');
        for(const row of rows){
          if(row.draft||typeof row.tag_name!=='string'||!row.tag_name.startsWith('desktop-v'))continue;
          const version=row.tag_name.slice(9);try{versionParts(version);}catch{continue;}
          const role=this.options.portable?'portable':'setup';const name='ember-desktop-'+version+'-x64-'+role+'.exe';
          const assets=Array.isArray(row.assets)?row.assets:[];
          const binary=assets.find((a:any)=>a.name===name),checksum=assets.find((a:any)=>a.name===name+'.sha256');
          const release:DesktopRelease={tag:row.tag_name,version,name:typeof row.name==='string'?row.name:row.tag_name,notes:typeof row.body==='string'?row.body.slice(0,12000):'',published_at:row.published_at||'',prerelease:!!row.prerelease,installable:false};
          if(binary&&checksum&&Number.isSafeInteger(binary.size)&&binary.size>0&&binary.size<=512*1024*1024){
            try{release.asset_url=releaseAssetURL(binary.browser_download_url);release.checksum_url=releaseAssetURL(checksum.browser_download_url);release.asset_name=name;release.bytes=binary.size;release.installable=true;}catch{}
          }
          if(!release.installable)release.reason='此版本没有匹配的 Windows 安装文件和 SHA256 校验文件';
          releases.push(release);
        }
        if(rows.length<100){complete=true;break;}
      }
      if(!complete)throw new Error('版本目录超过查询上限');
      releases.sort((a,b)=>compareVersions(b.version,a.version)||b.published_at.localeCompare(a.published_at));
      this.releases=releases;this.state.releases=structuredClone(releases);this.state.checked_at=new Date().toISOString();this.availability();this.state.phase='idle';
    }catch(error:any){this.state.phase='error';this.state.error=error.message||'检查更新失败';}
    return this.snapshot();
  }
  async download(tag:string):Promise<{path:string;release:DesktopRelease}>{
    if(typeof tag!=='string'||!tag.startsWith('desktop-v')||tag.length>80)throw new Error('请选择有效版本');
    if(!this.state.can_install)throw new Error('版本安装需要 Windows 正式桌面包');
    if(this.applying)throw new Error('已有版本切换任务');
    this.applying=true;
    try{
      if(this.checking)await this.checking;
      const checked=await this.refresh();if(checked.error)throw new Error(checked.error);
      const release=this.releases.find(x=>x.tag===tag);if(!release?.installable)throw new Error(release?.reason||'所选版本已被撤回或不存在');
      if(compareVersions(release.version,this.options.version)===0)throw new Error('当前已经是此版本');
      this.state.phase='downloading';this.state.target=release.version;this.state.percent=0;
      const fetcher=this.options.fetcher||fetch;
      const sum=await boundedText(await request(release.checksum_url!,4096,fetcher),4096);
      const match=/^([a-f0-9]{64})[ \t]+\*?([^\r\n]+)\s*$/i.exec(sum.trim());
      if(!match||match[2]!==release.asset_name)throw new Error('发行校验文件无效');
      const folder=join(this.options.root,'updates',randomBytes(16).toString('hex'));await mkdir(folder,{recursive:true});
      const path=join(folder,release.asset_name!),part=path+'.part';
      const file=await open(part,'wx',0o600);const hash=createHash('sha256');let size=0;
      try{
        const response=await request(release.asset_url!,512<<20,fetcher);
        if(!response.body)throw new Error('安装包为空');
        for await(const chunk of response.body as any){
          size+=chunk.length;if(size>release.bytes!||size>512*1024*1024)throw new Error('下载超过声明大小');
          await file.writeFile(chunk);hash.update(chunk);this.state.percent=Math.min(99,Math.floor(size*100/release.bytes!));
        }
        if(size!==release.bytes||hash.digest('hex')!==match[1].toLowerCase())throw new Error('安装包 SHA256 或大小校验失败，未执行');
        await file.sync();
      }catch(error){await file.close();await unlink(part).catch(()=>{});throw error;}
      await file.close();await rename(part,path);this.state.phase='ready';this.state.percent=100;
      return {path,release};
    }catch(error:any){this.state.phase='error';this.state.error=error.message;this.applying=false;throw error;}
  }
  async markApplying(release:DesktopRelease,resume:string[]=[]){
    await this.initialize();
    if(resume.length>24||resume.some(x=>!/^[a-f0-9]{32}$/.test(x)))throw new Error('实例恢复列表无效');
    const downgrade=compareVersions(release.version,this.options.version)<0;
    this.prefs.pending={from:this.options.version,to:release.version,ignore:downgrade?(this.releases[0]?.version||this.options.version):undefined,resume};
    await this.save();this.state.phase='installing';
  }
  failed(message:string){this.applying=false;this.state.phase='error';this.state.error=message;}
}

function ps(value:string){return "'"+value.replace(/'/g,"''")+"'";}
export function installScript(input:{pid:number;path:string;executable:string;portable?:string;log:string}):string{
  if(!Number.isSafeInteger(input.pid)||input.pid<=0)throw new Error('无效进程');
  const target=resolve(input.portable||input.executable),asset=resolve(input.path);
  if(asset===target||!target.toLowerCase().endsWith('.exe')||!asset.toLowerCase().endsWith('.exe'))throw new Error('安装目标无效');
  const header=`$ErrorActionPreference = 'Stop'\n$updateLog = ${ps(resolve(input.log))}\ntry {\n  Wait-Process -Id ${input.pid} -ErrorAction SilentlyContinue -Timeout 120\n  if (Get-Process -Id ${input.pid} -ErrorAction SilentlyContinue) { throw '桌面未能退出，未应用更新' }\n`;
  const body=input.portable?`
  $updateTarget = ${ps(target)}
  $updateBackup = $updateTarget + '.previous.exe'
  $updateNext = $updateTarget + '.next.exe'
  if (Test-Path -LiteralPath $updateNext) { throw '便携更新暂存文件已存在，请保留后检查' }
  Copy-Item -LiteralPath ${ps(asset)} -Destination $updateNext
  $updateMoved = $false
  for ($updateAttempt = 0; $updateAttempt -lt 120; $updateAttempt++) {
    try {
      if (Test-Path -LiteralPath $updateBackup) { Remove-Item -LiteralPath $updateBackup }
      Move-Item -LiteralPath $updateTarget -Destination $updateBackup
      $updateMoved = $true
      break
    } catch { Start-Sleep -Milliseconds 1000 }
  }
  if (-not $updateMoved) { throw '便携文件仍被占用，旧版本保留' }
  try {
    Move-Item -LiteralPath $updateNext -Destination $updateTarget
    Start-Process -FilePath $updateTarget -WindowStyle Hidden
  } catch {
    if (Test-Path -LiteralPath $updateTarget) { Remove-Item -LiteralPath $updateTarget }
    Move-Item -LiteralPath $updateBackup -Destination $updateTarget
    Start-Process -FilePath $updateTarget -WindowStyle Hidden
    throw
  }
`:`
  $updateInstaller = Start-Process -FilePath ${ps(asset)} -ArgumentList ${ps('/S /D='+dirname(target))} -WindowStyle Hidden -Wait -PassThru
  if ($updateInstaller.ExitCode -ne 0) { throw ('安装器失败：' + $updateInstaller.ExitCode) }
  Start-Process -FilePath ${ps(target)} -WindowStyle Hidden
`;
  return header+body+`\n} catch { $_.Exception.Message | Out-File -LiteralPath $updateLog -Encoding utf8; exit 1 }\n`;
}
export async function launchInstall(input:{path:string;executable:string;portable?:string;root:string}):Promise<void>{
  const helper=join(dirname(input.path),'apply-update.ps1');
  await writeFile(helper,'\ufeff'+installScript({...input,pid:process.pid,log:join(input.root,'desktop-update-error.log')}),{mode:0o600});
  const child=spawn(join(process.env.SystemRoot||'C:\\Windows','System32','WindowsPowerShell','v1.0','powershell.exe'),['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',helper],{detached:true,windowsHide:true,stdio:'ignore'});
  await new Promise<void>((resolve,reject)=>{child.once('spawn',resolve);child.once('error',reject);});child.unref();
}
