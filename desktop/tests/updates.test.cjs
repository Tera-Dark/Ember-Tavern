const test=require('node:test');const assert=require('node:assert/strict');
const {mkdtemp,writeFile,readFile,rm}=require('node:fs/promises');const {join}=require('node:path');const {tmpdir}=require('node:os');const {createHash}=require('node:crypto');
const {DesktopUpdates,compareVersions,releaseAssetURL,installScript}=require('../.vite/updates.cjs');
const repo='https://github.com/Tera-Dark/Ember-Tavern/releases/download/';
const binary=Buffer.from('fixture executable bytes - never executed');
function release(version,role='setup'){
 const tag='desktop-v'+version,name='ember-desktop-'+version+'-x64-'+role+'.exe';
 return {tag_name:tag,name:tag,published_at:'2026-10-12T00:00:00Z',prerelease:version.includes('-'),draft:false,assets:[{name,size:binary.length,browser_download_url:repo+tag+'/'+name},{name:name+'.sha256',browser_download_url:repo+tag+'/'+name+'.sha256'}]};
}
function feed(rows,options={}){
 const calls=[];
 const fetcher=async(url)=>{
  calls.push(url);
  if(url.includes('/releases?'))return Response.json(rows);
  if(url.endsWith('.sha256'))return new Response((options.badHash?'0'.repeat(64):createHash('sha256').update(binary).digest('hex'))+'  '+decodeURIComponent(url.split('/').at(-1)).slice(0,-7)+'\n');
  if(url.endsWith('.exe'))return new Response(options.chunked?new ReadableStream({start(c){c.enqueue(binary.subarray(0,9));c.enqueue(binary.subarray(9));c.close();}}):options.truncated?binary.subarray(1):binary);
  throw new Error('unexpected fixture URL '+url);
 };return {fetcher,calls};
}
async function fixture(fn){const root=await mkdtemp(join(tmpdir(),'ember-update-'));try{await fn(root);}finally{await rm(root,{recursive:true,force:true});}}
function updater(root,version,fetcher,extra={}){return new DesktopUpdates({root,version,fetcher,executable:'C:\\Program Files\\余烬桌面\\余烬桌面.exe',packaged:true,platform:'win32',...extra});}

test('semantic ordering includes beta.10, stable, build metadata and invalid prereleases',()=>{
 assert(compareVersions('0.2.0-beta.10','0.2.0-beta.9')>0);assert(compareVersions('0.2.0','0.2.0-rc.1')>0);assert.equal(compareVersions('1.0.0+a','1.0.0+b'),0);assert.throws(()=>compareVersions('0.2.0-beta.01','0.2.0'));assert.throws(()=>compareVersions('0.02.0','0.2.0'));
});
test('old installer finds newest prerelease by version, filters unrelated releases, and fetches all pages',async()=>fixture(async root=>{
 const calls=[];const first=Array.from({length:100},(_,i)=>({tag_name:'plugin-example-'+i}));first.push();
 const fetcher=async url=>{calls.push(url);return Response.json(url.endsWith('page=1')?first:[release('0.2.0-beta.10'),release('0.2.0-beta.9'),{...release('9.0.0'),draft:true}]);};
 const updates=updater(root,'0.2.0-beta.1',fetcher);const state=await updates.check();
 assert.equal(calls.length,2);assert.equal(state.latest.version,'0.2.0-beta.10');assert(state.available);assert.equal(state.releases.length,2);assert(!state.error);
}));
test('successful downgrade dismisses the same latest across restarts, a newer release alerts again',async()=>fixture(async root=>{
 const oldFeed=feed([release('0.2.0-beta.4'),release('0.2.0-beta.5')]);
 const latest=updater(root,'0.2.0-beta.5',oldFeed.fetcher);await latest.check();
 const target=await latest.download('desktop-v0.2.0-beta.4');assert.deepEqual(await readFile(target.path),binary);await latest.markApplying(target.release);
 const old=updater(root,'0.2.0-beta.4',oldFeed.fetcher);let state=await old.check();assert.equal(state.available,false);assert.equal(state.suppressed,true);
 state=await updater(root,'0.2.0-beta.4',oldFeed.fetcher).check();assert(state.suppressed);
 state=await updater(root,'0.2.0-beta.4',feed([release('0.2.0-beta.6'),release('0.2.0-beta.5')]).fetcher).check();assert(state.available);assert(!state.suppressed);
}));
test('failed downgrade does not suppress a release; manual reinstall downgrade is remembered',async()=>fixture(async root=>{
 const f=feed([release('0.2.0-beta.6'),release('0.2.0-beta.4')]);const current=updater(root,'0.2.0-beta.5',f.fetcher);await current.check();
 const target=await current.download('desktop-v0.2.0-beta.4');await current.markApplying(target.release);
 const restarted=await updater(root,'0.2.0-beta.5',f.fetcher).check();assert(restarted.available);assert(!restarted.suppressed);
 const old=await updater(root,'0.2.0-beta.4',f.fetcher).check();assert(old.available,'a newer unseen release remains available');
 const prefs=JSON.parse(await readFile(join(root,'desktop-updates.json'),'utf8'));assert.equal(prefs.ignoredThrough,'0.2.0-beta.5');
}));
test('checksum mismatch and truncated binary never become an executable download',async()=>{
 for(const options of [{badHash:true},{truncated:true}])await fixture(async root=>{
  const updates=updater(root,'0.2.0-beta.4',feed([release('0.2.0-beta.5')],options).fetcher);
  await assert.rejects(updates.download('desktop-v0.2.0-beta.5'),/SHA256|大小/);assert.equal(updates.snapshot().phase,'error');
  const {readdir}=require('node:fs/promises');for(const dir of await readdir(join(root,'updates')))assert.deepEqual(await readdir(join(root,'updates',dir)),[]);
 });
});
test('streamed download appends every chunk before verifying the complete digest',async()=>fixture(async root=>{
 const updates=updater(root,'0.2.0-beta.4',feed([release('0.2.0-beta.5')],{chunked:true}).fetcher);const result=await updates.download('desktop-v0.2.0-beta.5');assert.deepEqual(await readFile(result.path),binary);assert.equal(updates.snapshot().percent,100);
}));
test('missing assets stay visible but cannot install; portable uses its own checksums',async()=>fixture(async root=>{
 const missing={...release('0.3.0'),assets:[]};const portable=release('0.2.0-beta.5','portable');const f=feed([missing,portable]);
 const updates=updater(root,'0.2.0-beta.4',f.fetcher,{portable:'D:\\便携 目录\\余烬.exe'});const state=await updates.check();assert(state.available);assert(!state.latest.installable);
 await assert.rejects(updates.download('desktop-v0.3.0'),/没有匹配/);
 const result=await updates.download(portable.tag_name);assert(result.path.endsWith('-portable.exe'));assert.deepEqual(await readFile(result.path),binary);
}));
test('network failure is distinct from up to date, and concurrent checks are coalesced',async()=>fixture(async root=>{
 let calls=0;const updates=updater(root,'0.2.0-beta.4',async()=>{calls++;throw new Error('offline fixture');});const states=await Promise.all([updates.check(),updates.check()]);assert.equal(calls,1);assert.equal(states[0].phase,'error');assert.match(states[0].error,/offline/);assert(!states[0].checked_at);
}));
test('redirects, foreign URLs and renderer-selected download URLs are rejected',async()=>fixture(async root=>{
 for(const url of ['http://github.com/Tera-Dark/Ember-Tavern/releases/download/v/a.exe','https://github.com/evil/repo/releases/download/v/a.exe','https://user:pass@github.com/Tera-Dark/Ember-Tavern/releases/download/v/a.exe','https://github.com.evil.test/x'])assert.throws(()=>releaseAssetURL(url));
 const row=release('0.2.0-beta.5');let contacts=[];const updates=updater(root,'0.2.0-beta.4',async url=>{contacts.push(url);if(url.includes('/releases?'))return Response.json([row]);return new Response(null,{status:302,headers:{location:'https://evil.example/payload'}});});
 await assert.rejects(updates.download(row.tag_name),/重定向不可信/);assert(!contacts.some(x=>x.includes('evil.example')));
 await assert.rejects(updates.download('../evil'),/有效版本/);
}));
test('corrupt preferences are preserved and never silently reset',async()=>fixture(async root=>{
 await writeFile(join(root,'desktop-updates.json'),'bad original');const state=await updater(root,'0.2.0-beta.4',feed([]).fetcher).check();assert.match(state.error,/保留/);assert.equal(await readFile(join(root,'desktop-updates.json'),'utf8'),'bad original');
}));
test('desktop restart resumes only the instances that were running, once',async()=>fixture(async root=>{
 const f=feed([release('0.2.0-beta.5'),release('0.2.0-beta.4')]);const current=updater(root,'0.2.0-beta.4',f.fetcher);await current.check();
 const target=await current.download('desktop-v0.2.0-beta.5');await current.markApplying(target.release,['a'.repeat(32)]);
 const restarted=updater(root,'0.2.0-beta.5',f.fetcher);assert.deepEqual(await restarted.resumeInstances(),['a'.repeat(32)]);assert.deepEqual(await restarted.resumeInstances(),[]);
 assert.deepEqual(await updater(root,'0.2.0-beta.5',f.fetcher).resumeInstances(),[]);
}));
test('Windows helper waits for exit, quotes paths literally, preserves portable backup and retries locks',()=>{
 const input={pid:123,path:"C:\\下载\\installer's file.exe",executable:'C:\\应用 目录\\余烬.exe',log:'C:\\日志\\error.log'};
 const installed=installScript(input);assert(installed.includes('Wait-Process -Id 123'));assert(installed.includes("installer''s file.exe"));assert(installed.includes('/S /D='));assert(installed.includes('-WindowStyle Hidden'));
 const portable=installScript({...input,portable:'D:\\便携\\余烬.exe'});assert(portable.includes('.previous.exe'));assert(portable.includes('-LiteralPath'));assert(portable.includes('updateAttempt -lt 120'));assert(!portable.includes('cmd /c'));assert.throws(()=>installScript({...input,pid:0}));
});
