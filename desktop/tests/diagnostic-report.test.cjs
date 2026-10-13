const {test}=require('node:test');const assert=require('node:assert/strict');
const {diagnosticReport}=require('../.vite/diagnostic-report.cjs');
test('diagnostic export whitelists metadata and cannot copy secrets through labels, errors, paths or future fields',()=>{
 const secret='synthetic-private-context',id='a'.repeat(32),instance={id,name:secret,status:'running',version:'2.4.0-beta.1',lan:true,lan_urls:['https://'+secret+'.invalid'],data_path:secret,error:secret};
 const task={id:'b'.repeat(32),instance_id:id,kind:secret,status:'failed',stage:secret,phase:secret,error:secret,error_code:secret,logs:[secret]};
 const state={root:secret,platform:secret,launcher_version:'0.2.0-beta.4',instances:[instance],tasks:[task],build:{desktop_version:'0.2.0-beta.4',commit:'f'.repeat(40),source_dirty:false,extra:secret}};
 const report=diagnosticReport(state,instance,[{id:'health',status:'passed',label:secret,detail:secret},{id:secret,status:'passed'}],{DECISION_API_KEY:secret,DECISION_MODEL:secret,DECISION_API_KEY_configured:true,DECISION_BASE_URL:secret,unknown:secret});
 assert(!JSON.stringify(report).includes(secret));assert.equal(report.configuration.decisionKey,true);assert.deepEqual(report.checks,[{id:'health',status:'passed'}]);assert.equal(report.tasks[0].kind,'unknown');assert.equal(report.tasks[0].errorCode,'unknown');assert.equal(report.service.detectedAddresses,1);
});
