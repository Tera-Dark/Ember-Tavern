const {test}=require('node:test');const assert=require('node:assert/strict');
const {ModuleVersions}=require('../.vite/module-versions.cjs');
const instance='a'.repeat(32),checkpoint='b'.repeat(32);
const record={id:checkpoint,plugin_id:'qa-upgrade',old_version:'1.0.0',new_version:'2.0.0',old_hash:'1'.repeat(64),can_rollback:true,backend:true,capability_grant:false};
function fixture(){
 const calls=[];let running=false;
 const controller={instance:async()=>({id:instance,status:running?'running':'ready'}),engine:{request:async(path,method,body)=>{calls.push({path,body});if(path.startsWith('/api/creator-results/'))return {done:true,result:{ok:true,records:[record]}};return {id:'c'.repeat(32)};}}};
 return {controller,calls,start:()=>{running=true;}};
}
test('module inspection bypasses the global mutation queue',async()=>{
 const f=fixture();let queued=0;
 const modules=new ModuleVersions(f.controller,async action=>{queued++;return action();});
 const result=await modules.invoke({},'moduleHistory',{instanceId:instance});
 assert.equal(result.result.records[0].id,checkpoint);assert.equal(queued,0);
});
test('native cancellation or missing code trust never submits a rollback',async()=>{
 const f=fixture();let approvals=0;
 const modules=new ModuleVersions(f.controller,async action=>action(),{showMessageBox:async()=>{approvals++;return {response:0};}});
 await assert.rejects(modules.invoke({},'moduleRollback',{instanceId:instance,checkpointId:checkpoint}),/重新审阅/);
 assert.equal(approvals,0);
 assert.equal((await modules.invoke({},'moduleRollback',{instanceId:instance,checkpointId:checkpoint,trustBackend:true})).cancelled,true);
 assert(!f.calls.some(c=>c.body?.operation==='rollback'));
});
test('queued mutation rechecks running state after native approval',async()=>{
 const f=fixture();let queued=0;
 const modules=new ModuleVersions(f.controller,async action=>{queued++;f.start();return action();},{showMessageBox:async()=>({response:1})});
 await assert.rejects(modules.invoke({},'moduleRollback',{instanceId:instance,checkpointId:checkpoint,trustBackend:true}),/已开始运行/);
 assert.equal(queued,1);assert(!f.calls.some(c=>c.body?.operation==='rollback'));
});
