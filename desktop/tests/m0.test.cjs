const test=require('node:test');const assert=require('node:assert/strict');
const {mkdtemp,writeFile,readFile,rm}=require('node:fs/promises');const {tmpdir}=require('node:os');const {join}=require('node:path');
const {HostController}=require('../.vite/core.cjs');
const storage={encode:value=>Buffer.from(value).toString('base64'),decode:value=>Buffer.from(value,'base64').toString()};
const instanceId='a'.repeat(32),roomId='b'.repeat(32),characterId='c'.repeat(32),userId='d'.repeat(32);

test('recovered instances reuse protected original credentials without re-registering',async()=>{
 const root=await mkdtemp(join(tmpdir(),'ember-recovered-owner-'));const originalFetch=global.fetch;let registrations=0;
 try{
  await writeFile(join(root,'desktop-credentials.json'),JSON.stringify({encrypted:storage.encode(JSON.stringify({'legacy-room':{username:'original_owner',password:'fixture-only-not-real'}}))}));
  const controller=new HostController({options:{root},request:async()=>({instances:[{id:instanceId,port:18180,status:'running',recovered_from_id:'legacy-room'}]})},storage);
  global.fetch=async(url,options)=>{if(url.endsWith('/register'))registrations++;assert(url.endsWith('/login'));assert.equal(JSON.parse(options.body).username,'original_owner');return Response.json({token:'fixture-session'});};
  assert.equal(await controller.hostSession(instanceId),'fixture-session');assert.equal(registrations,0);
 }finally{global.fetch=originalFetch;await rm(root,{recursive:true,force:true});}
});
test('missing or corrupted recovery credentials never create a replacement owner',async()=>{
 const root=await mkdtemp(join(tmpdir(),'ember-recovery-no-owner-'));const originalFetch=global.fetch;let calls=0;
 try{
  global.fetch=async()=>{calls++;throw new Error('must not contact login or register')};
  const engine={options:{root},request:async()=>({instances:[{id:instanceId,port:18180,status:'running',recovered_from_id:'legacy-room'}]})};
  await assert.rejects(new HostController(engine,storage).hostSession(instanceId),/原房主凭据/);
  await assert.rejects(readFile(join(root,'desktop-credentials.json')),{code:'ENOENT'});
  const broken=JSON.stringify({encrypted:storage.encode('null')});await writeFile(join(root,'desktop-credentials.json'),broken);
  await assert.rejects(new HostController(engine,storage).hostSession(instanceId),/凭据无法解密/);
  assert.equal(await readFile(join(root,'desktop-credentials.json'),'utf8'),broken);assert.equal(calls,0);
 }finally{global.fetch=originalFetch;await rm(root,{recursive:true,force:true});}
});
test('recovery RPC allows only fingerprint IDs and an explicit stopped confirmation',async()=>{
 const requests=[];const controller=new HostController({options:{root:'/unused'},request:async(...args)=>{requests.push(args);return {restored:true}}},storage);
 await assert.rejects(controller.invoke('recoverIndex',{entryId:'../outside',confirmStopped:true}));assert.equal(requests.length,0);
 await controller.invoke('recoverIndex',{entryId:instanceId,confirmStopped:'true'});
 assert.deepEqual(requests[0],['/api/index-recovery/'+instanceId,'POST',{confirm_stopped:false}]);
});
test('local diagnostics probe only host health, never a provider, login or TTS',async()=>{
 const originalFetch=global.fetch,urls=[];
 try{
  const instance={id:instanceId,port:18180,channel:'bundled',version:'2.3.0-beta.2',commit:'e'.repeat(40),status:'running',lan:true,lan_urls:['http://192.168.1.20:18180']};
  const engine={options:{root:'/unused'},request:async(path)=>path==='/api/state'?{instances:[instance]}:{DECISION_API_KEY_configured:true,DECISION_MODEL:'fixture',GEMINI_API_KEY_configured:true,GEMINI_MODEL:'fixture'}};
  global.fetch=async(url)=>{urls.push(url);return Response.json({ok:true,product:'余烬酒馆',version:'2.3.0-beta.2'})};
  const result=await new HostController(engine,storage).invoke('diagnostics',{instanceId});
  assert.deepEqual(urls,['http://127.0.0.1:18180/api/health']);assert.equal(result.find(item=>item.id==='health').status,'passed');
  assert.equal(result.find(item=>item.id==='models').status,'unknown');assert(JSON.stringify(result).includes('均未验证'));assert(!JSON.stringify(result).includes('fixture'));
 }finally{global.fetch=originalFetch;}
});
test('starter creation is explicitly demo and character assignment uses authoritative revision',async()=>{
 const controller=new HostController({options:{root:'/unused'}},storage),calls=[];
 controller.game=async(...args)=>{calls.push(args);return {revision:8}};
 await controller.invoke('createRoom',{instanceId,title:'我们的第一夜',preset:'frontier'});
 assert.deepEqual(calls[0],[instanceId,'/rooms','POST',{title:'我们的第一夜',preset:'frontier',ai_mode:'demo'}]);
 await assert.rejects(controller.invoke('createRoom',{instanceId,title:'wrong',preset:'not-installed-preset'}));
 await assert.rejects(controller.invoke('createRoom',{instanceId,title:'x'.repeat(61)}));
 await controller.invoke('assignCharacter',{instanceId,roomId,characterId,userId});
 const mutation=calls.at(-1);assert.equal(mutation[1],'/rooms/'+roomId+'/characters/'+characterId+'/assign');assert.equal(mutation[3].expected_revision,8);assert.equal(mutation[3].user_id,userId);assert.match(mutation[3].request_key,/^[a-f0-9]{32}$/);
});

test('known engine startup failures explain preservation, without echoing raw errors or tokens',()=>{
 const {engineHandshake}=require('../.vite/core.cjs');
 assert.throws(()=>engineHandshake({ready:false,code:'startup_state',error:'private-detail',token:'do-not-echo'}),error=>/保留 launcher.json/.test(error.message)&&!error.message.includes('private-detail')&&!error.message.includes('do-not-echo'));
 assert.throws(()=>engineHandshake({ready:true,port:0,token:'a'.repeat(48)}));
 assert.equal(engineHandshake({ready:true,port:8180,token:'a'.repeat(48)}).port,8180);
});
test('a recovered database with rejected original login must not trigger registration',async()=>{
 const root=await mkdtemp(join(tmpdir(),'ember-recovery-wrong-login-'));const originalFetch=global.fetch;const calls=[];
 try{
  await writeFile(join(root,'desktop-credentials.json'),JSON.stringify({encrypted:storage.encode(JSON.stringify({'legacy-room':{username:'original_owner',password:'fixture-only-not-real'}}))}));
  const engine={options:{root},request:async()=>({instances:[{id:instanceId,port:18180,status:'running',recovered_from_id:'legacy-room'}]})};
  global.fetch=async(url)=>{calls.push(url);return Response.json({detail:'wrong credentials'},{status:401})};
  await assert.rejects(new HostController(engine,storage).hostSession(instanceId),/不会重置/);
  assert.deepEqual(calls,['http://127.0.0.1:18180/api/auth/login']);
  const raw=JSON.parse(await readFile(join(root,'desktop-credentials.json'),'utf8'));const saved=JSON.parse(storage.decode(raw.encrypted));assert.deepEqual(saved[instanceId],saved['legacy-room']);
 }finally{global.fetch=originalFetch;await rm(root,{recursive:true,force:true});}
});
