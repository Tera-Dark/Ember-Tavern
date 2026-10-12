const test=require('node:test'),assert=require('node:assert/strict');
const {mkdtemp,mkdir,writeFile,readFile,readdir,rm,symlink}=require('node:fs/promises');
const {tmpdir}=require('node:os'),{join}=require('node:path');
const {WorkspaceLocationStore,WORKSPACE_MIN_DESKTOP}=require('../.vite/workspace-location.cjs');
async function fixture(run){const parent=await mkdtemp(join(tmpdir(),'ember-workspace-location-'));try{const settings=join(parent,'profile'),original=join(parent,'original'),target=join(parent,'target');await mkdir(settings);await mkdir(target);await run({parent,settings,original,target,store:new WorkspaceLocationStore(settings,original)});}finally{await rm(parent,{recursive:true,force:true});}}
test('unified workspace selection survives restart and leaves original data untouched',()=>fixture(async({store,settings,original,target})=>{
 assert.equal(await store.load(),original);await writeFile(join(original,'launcher.json'),JSON.stringify({schema:1,instances:[]}));await writeFile(join(original,'private-state'),'preserve');
 const inspected=await store.inspect(target,original);assert.equal(inspected.existing,false);assert(inspected.availableBytes===null||inspected.availableBytes>0);assert.deepEqual(await readdir(target),[]);await store.mark(target);assert.equal((await store.inspect(target,original)).existing,true);await store.mark(target);
 await store.save(target);assert.equal(await new WorkspaceLocationStore(settings,original).load(),target);assert.equal(await readFile(join(original,'private-state'),'utf8'),'preserve');
 assert.equal((await store.inspect(original,target)).existing,true);assert.equal(store.snapshot(target).minimumDesktop,WORKSPACE_MIN_DESKTOP);await store.save(original);assert.equal(await store.load(),original);
}));
test('unknown directories, nested roots, future indexes and links cannot be adopted',()=>fixture(async({store,original,target,parent})=>{
 await store.load();await writeFile(join(target,'unrelated.txt'),'preserve');await assert.rejects(store.inspect(target,original),/其他文件/);assert.equal(await readFile(join(target,'unrelated.txt'),'utf8'),'preserve');
 const nested=join(original,'nested');await mkdir(nested);await assert.rejects(store.inspect(nested,original),/互相包含/);
 await writeFile(join(target,'launcher.json'),JSON.stringify({schema:999,instances:[]}));await assert.rejects(store.inspect(target,original),/不支持/);
 const link=join(parent,'linked');try{await symlink(target,link,process.platform==='win32'?'junction':'dir');}catch(e){if(e.code==='EPERM')return;throw e;}await assert.rejects(store.inspect(link,original),/链接/);
}));
test('missing selected disk and damaged or externally modified preferences never fall back or overwrite',()=>fixture(async({store,settings,original,target})=>{
 await store.load();await store.save(target);await rm(target,{recursive:true});await assert.rejects(new WorkspaceLocationStore(settings,original).load(),{code:'ENOENT'});
 const file=join(settings,'desktop-workspace.json');await writeFile(file,'future-private-file');await assert.rejects(new WorkspaceLocationStore(settings,original).load(),/损坏/);assert.equal(await readFile(file,'utf8'),'future-private-file');
 await assert.rejects(store.save(original),/其他程序修改/);assert.equal(await readFile(file,'utf8'),'future-private-file');
}));
