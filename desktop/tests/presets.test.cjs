const test=require('node:test');const assert=require('node:assert/strict');
const {HostController,packageHash}=require('../.vite/core.cjs');const {presetPayload}=require('../.vite/preset-file.cjs');
const instanceId='a'.repeat(32),hash='b'.repeat(64);

test('preset identities are hashes, not filesystem paths or arbitrary operation names',()=>{
 assert.equal(packageHash(hash),hash);for(const value of ['../file','a'.repeat(32),'g'.repeat(64),null])assert.throws(()=>packageHash(value));
});
test('preset creation preserves one caller intent, explicitly demo, no supplied model credentials',async()=>{
 const controller=new HostController({options:{root:'/unused'}},{});const calls=[];controller.game=async(...args)=>{calls.push(args);return {id:'c'.repeat(32)}};
 const args={instanceId,packageHash:hash,title:'我们的完整预设',hostPlays:false,requestKey:'one-intent-123',ai_mode:'live',api_key:'must-not-forward'};
 await controller.invoke('createPresetRoom',args);await controller.invoke('createPresetRoom',args);
 assert.deepEqual(calls[0],[instanceId,'/rooms/from-preset','POST',{title:'我们的完整预设',package_hash:hash,ai_mode:'demo',host_plays:false,request_key:'one-intent-123'}]);assert.deepEqual(calls[0],calls[1]);
 await assert.rejects(controller.invoke('createPresetRoom',{...args,packageHash:'../room'}));await assert.rejects(controller.invoke('createPresetRoom',{...args,requestKey:'x'}));await assert.rejects(controller.invoke('createPresetRoom',{...args,title:'x'.repeat(61)}));
});
test('native file decoder only accepts bounded ZIP or native JSON transport, never scripts',()=>{
 const encode=value=>new TextEncoder().encode(value);
 assert.deepEqual(presetPayload(encode('zip-fixture'),'data.zip'),{archive_base64:Buffer.from('zip-fixture').toString('base64')});
 assert.deepEqual(presetPayload(encode('{"format":"ember.preset-bundle/v1","files":{}}'),'data.json'),{document:{format:'ember.preset-bundle/v1',files:{}}});
 assert.throws(()=>presetPayload(new Uint8Array(1024*1024+1),'large.zip'));assert.throws(()=>presetPayload(new Uint8Array(2*1024*1024+1),'large.json'));
 assert.throws(()=>presetPayload(encode('alert(1)'),'data.js'));assert.throws(()=>presetPayload(encode('{"format":"ember.preset/v9"}'),'data.json'));assert.throws(()=>presetPayload(new Uint8Array([0xff]),'data.json'));
});
test('renderer cannot supply a path to import via the ordinary controller',async()=>{
 const controller=new HostController({options:{root:'/unused'}},{});await assert.rejects(controller.invoke('importPreset',{instanceId,path:'/private/file.json',approve:true}),/未知/);
});
