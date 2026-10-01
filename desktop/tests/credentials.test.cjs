const test=require('node:test');const assert=require('node:assert/strict');const {mkdtemp,readFile,rm}=require('node:fs/promises');const {tmpdir}=require('node:os');const {join}=require('node:path');const {HostController}=require('../.vite/core.cjs');
test('simultaneous instances cannot lose credentials; host session creation is single-flight',async()=>{
 const root=await mkdtemp(join(tmpdir(),'ember-credentials-'));const ids=['a'.repeat(32),'b'.repeat(32)];const fetch=global.fetch;let registrations=0;
 global.fetch=async(_url,options)=>{if(_url.endsWith('/login'))return new Response('{}',{status:401});registrations++;await new Promise(r=>setTimeout(r,5));return Response.json({token:JSON.parse(options.body).username});};
 try{const engine={options:{root},request:async()=>({instances:ids.map((id,i)=>({id,port:18080+i,status:'running'}))})};const store={encode:s=>Buffer.from(s).toString('base64'),decode:s=>Buffer.from(s,'base64').toString()};const c=new HostController(engine,store);const [a,b,again]=await Promise.all([c.hostSession(ids[0]),c.hostSession(ids[1]),c.hostSession(ids[0])]);assert.equal(a,again);assert.equal(registrations,2);const raw=JSON.parse(await readFile(join(root,'desktop-credentials.json'),'utf8'));const saved=JSON.parse(store.decode(raw.encrypted));assert.equal(Object.keys(saved).length,2);assert.equal(saved[ids[1]].username,b);assert(!JSON.stringify(raw).includes(saved[ids[0]].password));}
 finally{global.fetch=fetch;await rm(root,{recursive:true,force:true});}
});
test('failed encryption does not cache or write an unprotected account',async()=>{
 const root=await mkdtemp(join(tmpdir(),'ember-no-key-'));const instanceId='a'.repeat(32);let attempts=0;const c=new HostController({options:{root},request:async()=>({instances:[{id:instanceId,port:18080,status:'running'}]})},{encode:()=>{attempts++;throw new Error('secure storage unavailable');},decode:s=>s});
 try{await assert.rejects(c.hostSession(instanceId),/secure storage/);await assert.rejects(c.hostSession(instanceId),/secure storage/);assert.equal(attempts,2);await assert.rejects(readFile(join(root,'desktop-credentials.json')), {code:'ENOENT'});}
 finally{await rm(root,{recursive:true,force:true});}
});
