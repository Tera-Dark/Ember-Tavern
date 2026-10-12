// Runs the real Windows helper with a synthetic executable, never a user install.
const {mkdtemp,writeFile,readFile,copyFile}=require('node:fs/promises');
const {tmpdir}=require('node:os');const {join}=require('node:path');const {spawn,execFile}=require('node:child_process');const {promisify}=require('node:util');const assert=require('node:assert/strict');
const run=promisify(execFile);const {installScript}=require('../.vite/updates.cjs');
(async()=>{
 if(process.platform!=='win32')throw new Error('Windows only');
 const root=await mkdtemp(join(tmpdir(),"ember helper's 中文 空格-"));
 const source=join(root,'fixture.go'),binary=join(root,'fixture installer.exe');
 await writeFile(source,`package main
import("os";"path/filepath";"strings")
func main(){
 if len(os.Args)>1&&os.Args[1]=="/S" { folder:=strings.TrimPrefix(strings.Join(os.Args[2:]," "),"/D=");if e:=os.WriteFile(filepath.Join(folder,"installer-ran.txt"),[]byte("installed"),0600);e!=nil{os.Exit(2)};return }
 path,_:=os.Executable();_ = os.WriteFile(path+".launched",[]byte("launched"),0600)
}
`);
 await run('go',['build','-o',binary,source],{windowsHide:true,timeout:90000});
 const report={status:'running',root,executable:'synthetic fixture only'};
 for(const role of ['installer','portable']){
  const target=join(root,role+' 余烬.exe');
  if(role==='installer')await copyFile(binary,target);else await writeFile(target,'original portable fixture');
  const sleeper=spawn(process.execPath,['-e','setTimeout(()=>{},1500)'],{windowsHide:true,stdio:'ignore'});
  const script=join(root,role+'.ps1'),log=join(root,role+'-error.log');
  await writeFile(script,'\ufeff'+installScript({pid:sleeper.pid,path:binary,executable:target,portable:role==='portable'?target:undefined,log}));
  await run('powershell.exe',['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',script],{windowsHide:true,timeout:30000});
  // Start-Process is asynchronous; wait only for our fixture's output marker.
  let content;for(let i=0;i<50;i++){try{content=await readFile(target+'.launched','utf8');break;}catch{await new Promise(r=>setTimeout(r,100));}}
  assert.equal(content,'launched');
  if(role==='installer')assert.equal(await readFile(join(root,'installer-ran.txt'),'utf8'),'installed');
  else assert.equal(await readFile(target+'.previous.exe','utf8'),'original portable fixture');
  report[role]='passed';
 }
 report.status='passed';await writeFile(join(root,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(error=>{console.error(error);process.exitCode=1;});
