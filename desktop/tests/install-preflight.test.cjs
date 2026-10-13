const test=require('node:test'),assert=require('node:assert/strict');
const {installPreflight}=require('../.vite/install-preflight.cjs');
const engine={options:{root:'/fixture'},request:async()=>({port:8183,python_url:'https://www.python.org/fixture.zip',python_version:'fixture',dependency_url:'https://pypi.org/simple/fastapi/'})};
const locations={inspect:async()=>({availableBytes:1000000})};
test('installation preflight checks only fixed official sources without credentials or a provider',async()=>{
 const calls=[];const result=await installPreflight(engine,locations,0,async(url,options)=>{calls.push({url,options});return new Response(null,{status:200,headers:{'content-length':'5000'}})});
 assert.equal(result.port,8183);assert.equal(result.pythonBytes,5000);assert.equal(result.availableBytes,1000000);assert.equal(calls.length,2);assert(calls.every(c=>c.options.method==='HEAD'&&c.options.redirect==='error'&&c.options.headers===undefined));
 assert.deepEqual(calls.map(c=>new URL(c.url).hostname).sort(),['pypi.org','www.python.org']);assert(result.checks.every(c=>c.status==='passed'));
});
test('offline connectivity remains a warning while invalid ports, disk space and untrusted sources block',async()=>{
 const offline=await installPreflight(engine,locations,8183,async()=>{throw new Error('offline')});assert.equal(offline.pythonBytes,null);assert.equal(offline.checks.filter(c=>c.status==='warning').length,2);
 await assert.rejects(installPreflight(engine,locations,NaN),/端口/);await assert.rejects(installPreflight(engine,{inspect:async()=>({availableBytes:3})},0,async()=>new Response(null,{headers:{'content-length':'5000'}})),/剩余空间/);
 const wrong={...engine,request:async()=>({python_url:'https://provider.invalid/v1',dependency_url:'https://pypi.org/simple/fastapi/'})};let calls=0;await assert.rejects(installPreflight(wrong,locations,0,async()=>{calls++;return new Response(null)}),/来源/);
 assert(calls<=1); // The independent public PyPI HEAD may already have started.
});
