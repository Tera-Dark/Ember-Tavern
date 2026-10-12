const test=require('node:test'),assert=require('node:assert/strict');
const {mkdtemp,mkdir,readFile,writeFile,rm,symlink}=require('node:fs/promises');const {join}=require('node:path'),{tmpdir}=require('node:os');
const {CreatorProjects,creatorDirectory,creatorOutside}=require('../.vite/creator-projects.cjs');
async function isolated(action){const root=await mkdtemp(join(tmpdir(),'ember-creator-projects-'));try{await action(root);}finally{await rm(root,{recursive:true,force:true});}}
test('project records serialize changes and reopen stable opaque IDs without copying draft bodies',()=>isolated(async root=>{
 const projects=new CreatorProjects(root);await projects.load();await Promise.all([projects.register(join(root,'one'),'worldbook','One'),projects.register(join(root,'two'),'plugin','Two')]);assert.equal(projects.snapshot().projects.length,2);const first=projects.snapshot().projects[0];await projects.register(first.directory,'worldbook','Renamed');assert.equal(projects.snapshot().projects.find(p=>p.name==='Renamed').id,first.id);
 const reopened=new CreatorProjects(root);assert.equal((await reopened.load()).projects.length,2);await assert.rejects(Promise.resolve().then(()=>reopened.get('../path')));await reopened.forget(first.id);assert.equal(reopened.snapshot().projects.length,1);
}));
test('future and externally changed project files are preserved rather than overwritten',()=>isolated(async root=>{
 const store=new CreatorProjects(root);await store.load();await store.register(join(root,'one'),'worldbook','One');const file=join(root,'creator-projects.private.json'),future='{"format":"future/v9","private":"preserve"}';await writeFile(file,future);await assert.rejects(store.register(join(root,'two'),'theme','Two'));assert.equal(await readFile(file,'utf8'),future);assert((await new CreatorProjects(root).load()).readOnly);
}));
test('native directory guards reject linked ancestors and managed or bundled output paths',()=>isolated(async root=>{
 const source=join(root,'source');await mkdir(source);assert.equal(await creatorDirectory(source),source);assert.throws(()=>creatorOutside(join(source,'draft'),[source]));assert.throws(()=>creatorOutside(source,[source]));creatorOutside(join(root,'other'),[source]);
 const link=join(root,'link');try{await symlink(source,link,process.platform==='win32'?'junction':'dir');}catch(e){if(e.code==='EPERM')return;throw e;}await assert.rejects(creatorDirectory(link));
}));
