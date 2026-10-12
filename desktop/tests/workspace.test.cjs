const {test}=require('node:test');const assert=require('node:assert/strict');
const {parsePreferences,orderInstances,chooseContinuation}=require('../.vite/workspace-state.cjs');
const {parseDesktopPreferences,fitWindow,PreferencesStore}=require('../.vite/preferences.cjs');
const {mkdtemp,writeFile,readFile,rm}=require('node:fs/promises');const {tmpdir}=require('node:os');const {join,resolve,sep,basename}=require('node:path');
const a='a'.repeat(32),b='b'.repeat(32),c='c'.repeat(32);
test('guest QR encodes only the browser entry and rejects secrets, loopback or unsafe schemes',()=>{
 const {guestEntryURL,guestEntryQR}=require('../.vite/guest-entry.cjs');
 assert.equal(guestEntryURL('http://192.168.1.10:8180'),'http://192.168.1.10:8180/?guest=1');
 assert.equal(guestEntryQR('http://192.168.1.10:8180').url,'http://192.168.1.10:8180/?guest=1');
 assert(guestEntryQR('http://192.168.1.10:8180').image.startsWith('data:image/gif;base64,'));
 for(const value of ['http://127.0.0.1:8180','http://localhost:8180','http://0.0.0.0:8180','http://u:p@192.168.1.10:8180','http://192.168.1.10:8180/?verification_key=secret','javascript:alert(1)'])assert.throws(()=>guestEntryURL(value));
});
test('continuation follows an explicit saved room and never silently substitutes another owner or room',()=>{
 const rooms=[{id:a,is_owner:false},{id:b,is_owner:true},{id:c,is_owner:true}];
 assert.equal(chooseContinuation(rooms,b).room.id,b);
 assert.deepEqual(chooseContinuation(rooms,a),{room:undefined,needsSelection:true,missing:true});
 assert.equal(chooseContinuation(rooms).room,undefined);
 assert.equal(chooseContinuation([rooms[0],rooms[1]]).room.id,b);
});
test('UI preferences bound identity and text, ignore corruption, and sort without mutating service state',()=>{
 assert.deepEqual(parsePreferences('{invalid').instances,{});
 const prefs=parsePreferences(JSON.stringify({version:1,instances:{[a]:{favorite:true,lastUsed:1,roomId:'../bad',roomTitle:'x'.repeat(1000)},[b]:{lastUsed:2},'../data':{favorite:true}}}));
 assert.equal(Object.keys(prefs.instances).length,2);assert.equal(prefs.instances[a].roomId,undefined);assert.equal(prefs.instances[a].roomTitle.length,80);
 const instances=[{id:b,name:'B',status:'running'},{id:a,name:'A',status:'ready'}];assert.equal(orderInstances(instances,prefs)[0].id,a);assert.equal(instances[0].id,b);
});
test('window restoration remains on a live monitor and fits logical DPI work areas',()=>{
 const restored=fitWindow({x:5000,y:-5000,width:1800,height:1000},[{x:0,y:0,width:911,height:480}]);
 assert.deepEqual(restored,{x:0,y:0,width:911,height:480});
 const negative=fitWindow({x:-1900,y:20,width:1000,height:700},[{x:0,y:0,width:1365,height:768},{x:-1920,y:0,width:1920,height:1080}]);assert(negative.x<0);
 const centered=fitWindow(undefined,[{x:0,y:0,width:1921,height:1081}]);assert(Number.isInteger(centered.x)&&Number.isInteger(centered.y));
 assert.throws(()=>parseDesktopPreferences({format:'future/v2'}));
});
test('native preferences serialize concurrent changes and preserve corrupted originals',async()=>{
 const root=await mkdtemp(join(tmpdir(),'ember-preferences-'));try{
  const store=new PreferencesStore(root);await store.load();await Promise.all([store.update({closeBehavior:'tray'}),store.update({openBehavior:'last'})]);
  const saved=JSON.parse(await readFile(join(root,'desktop-preferences.json'),'utf8'));assert.equal(saved.closeBehavior,'tray');assert.equal(saved.openBehavior,'last');
  const path=join(root,'desktop-preferences.json');await writeFile(path,'{broken');const corrupt=new PreferencesStore(root);const report=await corrupt.load();assert(report.readOnly);await assert.rejects(corrupt.update({closeBehavior:'quit'}));assert.equal(await readFile(path,'utf8'),'{broken');
 }finally{assert(resolve(root).startsWith(resolve(tmpdir())+sep)&&basename(root).startsWith('ember-preferences-'));await rm(root,{recursive:true,force:true});}
});
test('a delayed response from an old instance cannot replace a newly selected workspace',async()=>{
 const {createDesktop}=require('../.vite/workspace.cjs');let resolveOld;
 global.localStorage={getItem:()=>null,setItem:()=>{}};global.window={emberDesktop:{kind:'native',invoke:async(method,args)=>{
  if(method==='rooms'&&args.instanceId===a)return await new Promise(resolve=>resolveOld=resolve);
  if(method==='rooms')return [];
  if(method==='state')return {instances:[],tasks:[]};return {};
 }}};
 const store=createDesktop();const original=store.enter({id:a,name:'old',status:'running',port:8180,lan:true,channel:'bundled'});
 await Promise.resolve();await store.enter({id:b,name:'new',status:'running',port:8181,lan:true,channel:'bundled'});
 resolveOld([{id:c,title:'Old private room',is_owner:true}]);await original;
 assert.equal(store.selected.value,b);assert.deepEqual(store.rooms.value,[]);store.stop();
});
test('a room refresh started before a plugin action cannot overwrite its confirmed result',async()=>{
 const {createDesktop}=require('../.vite/workspace.cjs');let finishList;
 const original={id:b,title:'Room',is_owner:true,plugins:[{id:'scene-map',enabled:false}]};
 global.localStorage={getItem:()=>null,setItem:()=>{}};global.window={emberDesktop:{kind:'native',invoke:async(method)=>{
  if(method==='rooms')return await new Promise(resolve=>finishList=resolve);
  if(method==='roomAction')return {...original,plugins:[{id:'scene-map',enabled:true}]};
  if(method==='state')return {instances:[{id:a,status:'running'}],tasks:[]};
  if(method==='room')return original;if(method==='guestInvites')return [];return {};
 }}};
 const store=createDesktop();store.selected.value=a;store.room.value=original;
 const refresh=store.loadRooms();await Promise.resolve();await store.toggle(original.plugins[0]);
 finishList([original]);await refresh;assert.equal(store.room.value.plugins[0].enabled,true);store.stop();
});
