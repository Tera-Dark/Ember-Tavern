const {test}=require('node:test');const assert=require('node:assert/strict');
const {ConnectionVault,connectionURL}=require('../.vite/connections.cjs');
const {mkdtemp,readFile,writeFile,rm}=require('node:fs/promises');const {tmpdir}=require('node:os');const {join,resolve,sep,basename}=require('node:path');
const {randomBytes,createCipheriv,createDecipheriv}=require('node:crypto');
const key=randomBytes(32),storage={encode:value=>{const nonce=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,nonce);return Buffer.concat([nonce,cipher.update(value,'utf8'),cipher.final(),cipher.getAuthTag()]).toString('base64');},decode:value=>{const b=Buffer.from(value,'base64'),cipher=createDecipheriv('aes-256-gcm',key,b.subarray(0,12));cipher.setAuthTag(b.subarray(-16));return Buffer.concat([cipher.update(b.subarray(12,-16)),cipher.final()]).toString('utf8');}};
const profile={name:'Synthetic decision',kind:'decision',baseURL:'http://127.0.0.1:9999/v1',model:'qa-model',voice:'',jsonMode:false,keyAction:'replace',key:'qa-connection-secret'};
const instance='a'.repeat(32);
async function isolated(action){const root=await mkdtemp(join(tmpdir(),'ember-connections-'));try{await action(root);}finally{assert(resolve(root).startsWith(resolve(tmpdir())+sep)&&basename(root).startsWith('ember-connections-'));await rm(root,{recursive:true,force:true});}}
test('connection addresses reject credential URLs, nonlocal HTTP and unsafe schemes',()=>{
 assert.equal(connectionURL('https://example.com/v1/'),'https://example.com/v1');
 for(const value of ['http://example.com/v1','https://u:p@example.com/v1','https://example.com/v1?key=secret','file:///tmp/provider','https://example.com/v1#token','https://example.com/\n'])assert.throws(()=>connectionURL(value));
});
test('profiles keep keys encrypted and bind an explicit revision without changing existing instances on edit',()=>isolated(async root=>{
 const vault=new ConnectionVault(root,storage);await vault.load();let snapshot=await vault.save(profile);const p=snapshot.profiles[0];
 assert.equal(p.keyConfigured,true);assert(!JSON.stringify(snapshot).includes(profile.key));assert(!(await readFile(join(root,'connections.private.json'),'utf8')).includes(profile.key));
 const calls=[];await vault.bind(instance,'decision',p.id,async values=>calls.push(values));assert.equal(calls[0].DECISION_MODEL,'qa-model');
 snapshot=await vault.save({...p,keyAction:'keep',model:'new-model'});assert.equal(snapshot.profiles[0].revision,2);assert.equal(snapshot.bindings[instance].decision.revision,1);
 const restored=new ConnectionVault(root,storage);await restored.load();await restored.restore(async(id,values)=>{assert.equal(id,instance);assert.equal(values.DECISION_MODEL,'qa-model');assert.equal(values.DECISION_API_KEY,profile.key);});
 await assert.rejects(vault.remove(p.id),/解除/);await vault.bind(instance,'decision',null,async values=>assert.deepEqual(values,{}));await vault.remove(p.id);assert.equal(vault.snapshot().profiles.length,0);
}));
test('explicit key keep/replace/clear and stale edits are distinct',()=>isolated(async root=>{
 const vault=new ConnectionVault(root,storage);const a=(await vault.save(profile)).profiles[0];
 const b=(await vault.save({...a,keyAction:'clear'})).profiles[0];assert.equal(b.keyConfigured,false);
 await assert.rejects(vault.save({...a,keyAction:'keep'}),/重新打开/);
 const c=(await vault.save({...b,keyAction:'replace',key:'new-qa-secret'})).profiles[0];assert.equal(c.keyConfigured,true);assert.equal(c.revision,3);
 await assert.rejects(vault.save({...c,keyAction:'keep',baseURL:'https://example.com/?key=new-qa-secret'}));
}));
test('externally changed vaults cannot be overwritten or tested with a stale cached credential',()=>isolated(async root=>{
 const vault=new ConnectionVault(root,storage),p=(await vault.save(profile)).profiles[0],path=join(root,'connections.private.json');
 const future=JSON.stringify({format:'future/v2',encrypted:'new-owner-content'});await writeFile(path,future);
 await assert.rejects(vault.save({...p,keyAction:'keep'}));assert(vault.snapshot().readOnly);assert.equal(await readFile(path,'utf8'),future);
 let called=false;await assert.rejects(vault.test(p.id,'generate',true,async()=>{called=true;return new Response('{}');}));assert.equal(called,false);
}));
test('unknown pinned runtime modes and revisions fail closed instead of silently becoming a different configuration',()=>isolated(async root=>{
 const vault=new ConnectionVault(root,storage),p=(await vault.save(profile)).profiles[0];await vault.bind(instance,'decision',p.id,async()=>{});const path=join(root,'connections.private.json'),outer=JSON.parse(await readFile(path,'utf8')),original=JSON.parse(storage.decode(outer.encrypted));
 for(const change of [value=>value.bindings[instance].decision.values.DECISION_JSON_MODE='future-mode',value=>value.bindings[instance].decision.revision=999]){const value=structuredClone(original);change(value);const raw=JSON.stringify({...outer,encrypted:storage.encode(JSON.stringify(value))});await writeFile(path,raw);const bad=new ConnectionVault(root,storage);assert((await bad.load()).readOnly);await assert.rejects(bad.restore(async()=>{}));assert.equal(await readFile(path,'utf8'),raw);}
}));
test('corrupt, future, or un-decryptable vaults retain their original files and fail closed',()=>isolated(async root=>{
 const path=join(root,'connections.private.json'),original=JSON.stringify({format:'future/v2',encrypted:'unknown'});await writeFile(path,original);
 const vault=new ConnectionVault(root,storage);assert((await vault.load()).readOnly);await assert.rejects(vault.save(profile));await assert.rejects(vault.restore(async()=>{}));assert.equal(await readFile(path,'utf8'),original);
}));
test('binding failures leave the previous encrypted association intact and undo unpersisted runtime changes',()=>isolated(async root=>{
 let fail=false;const guarded={...storage,encode:v=>{if(fail)throw new Error('encryption unavailable');return storage.encode(v);}};
 const vault=new ConnectionVault(root,guarded);const p=(await vault.save(profile)).profiles[0];const before=await readFile(join(root,'connections.private.json'),'utf8');
 await assert.rejects(vault.bind(instance,'decision',p.id,async()=>{throw new Error('busy');}));assert.deepEqual(vault.snapshot().bindings,{});
 const calls=[];fail=true;await assert.rejects(vault.bind(instance,'decision',p.id,async v=>calls.push(v)),/已恢复/);assert.equal(calls.length,2);assert.deepEqual(calls[1],{});assert.equal(await readFile(join(root,'connections.private.json'),'utf8'),before);
}));
test('model-list detection never sends a generation request; paid tests require explicit confirmation and never echo provider text',()=>isolated(async root=>{
 const vault=new ConnectionVault(root,storage),p=(await vault.save(profile)).profiles[0];const calls=[];
 const transport=async(url,options)=>{calls.push({url,options});return new Response(JSON.stringify(url.endsWith('/models')?{data:[{id:'qa-model'},{id:profile.key},{id:'bad\nmodel'}]}:{choices:[{message:{content:profile.key}}]}),{headers:{'Content-Type':'application/json'}});};
 const list=await vault.test(p.id,'models',false,transport);assert.deepEqual(list.models,['qa-model']);assert.equal(calls.length,1);assert(calls[0].url.endsWith('/models'));assert.equal(calls[0].options.redirect,'error');
 await assert.rejects(vault.test(p.id,'generate',false,transport));assert.equal(calls.length,1);
 const generate=await vault.test(p.id,'generate',true,transport);assert.equal(generate.status,'passed');assert(!JSON.stringify(generate).includes(profile.key));assert.equal(calls.length,2);
 const failed=await vault.test(p.id,'models',false,async()=>new Response(profile.key,{status:401}));assert(!JSON.stringify(failed).includes(profile.key));assert.equal(failed.status,'failed');
 const excessive=await vault.test(p.id,'models',false,async()=>new Response('x'.repeat(140000)));assert.equal(excessive.status,'failed');
}));
test('TTS verification rejects a successful JSON response masquerading as audio',()=>isolated(async root=>{
 const vault=new ConnectionVault(root,storage),p=(await vault.save({...profile,kind:'tts',voice:'alloy'})).profiles[0];
 assert.equal((await vault.test(p.id,'generate',true,async()=>new Response('{}',{headers:{'content-type':'application/json'}}))).status,'failed');
 const result=await vault.test(p.id,'generate',true,async()=>new Response(new Uint8Array([73,68,51,4]),{headers:{'content-type':'audio/mpeg'}}));assert.equal(result.status,'passed');
}));
