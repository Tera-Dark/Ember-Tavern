const test=require('node:test');const assert=require('node:assert/strict');const {mkdtemp,writeFile,readFile,rm}=require('node:fs/promises');const {tmpdir}=require('node:os');const {join}=require('node:path');

test('release versions are coordinated and not hard-coded to a historical tag',async()=>{
 const {releaseVersions}=await import('../scripts/build-info.mjs');const versions=await releaseVersions(join(__dirname,'../..'));
 assert.equal(versions.desktop_version,require('../package.json').version);assert.equal(versions.tag,'desktop-v'+versions.desktop_version);assert.equal(versions.launcher_version,versions.desktop_version);
});
test('release provenance rejects wrong source, failed smoke and replaced binaries',async()=>{
 const {fileDigest}=await import('../scripts/build-info.mjs');const {createProvenance,verifyProvenance,checkSmoke}=await import('../scripts/release-metadata.mjs');
 const root=await mkdtemp(join(tmpdir(),'ember-provenance-'));const commit='a'.repeat(40);const versions={desktop_version:'0.2.0-beta.2',launcher_version:'0.2.0-beta.2',app_version:'2.3.0-beta.2',tag:'desktop-v0.2.0-beta.2'};
 const report={status:'passed',graceful_shutdown:true,source_commit:commit,source_dirty:false,...versions};
 try{
  const smoke=join(root,'desktop-smoke.json'),proofPath=join(root,'desktop-provenance.json');await writeFile(smoke,JSON.stringify(report));
  for(const suffix of ['setup','portable']){const name='ember-desktop-'+versions.desktop_version+'-x64-'+suffix+'.exe';const path=join(root,name);await writeFile(path,'fixture binary, not a real installer');await writeFile(path+'.sha256',(await fileDigest(path)).sha256+'  '+name+'\n');}
  const proof=await createProvenance(root,smoke,versions,commit);await writeFile(proofPath,JSON.stringify(proof));await verifyProvenance(root,smoke,proofPath,versions,commit);
  assert.throws(()=>checkSmoke({...report,source_commit:'b'.repeat(40)},versions,commit),/source/);assert.throws(()=>checkSmoke({...report,source_dirty:true},versions,commit),/source/);assert.throws(()=>checkSmoke({...report,status:'failed'},versions,commit),/smoke/);
  const changed=join(root,'ember-desktop-'+versions.desktop_version+'-x64-setup.exe');await writeFile(changed,'replacement');
  await assert.rejects(verifyProvenance(root,smoke,proofPath,versions,commit),/Checksum/);
  // Replacing both EXE and checksum is still rejected by the immutable proof.
  await writeFile(changed+'.sha256',(await fileDigest(changed)).sha256+'  '+changed.split(require('node:path').sep).at(-1)+'\n');
  await assert.rejects(verifyProvenance(root,smoke,proofPath,versions,commit),/mismatch/);
 }finally{await rm(root,{recursive:true,force:true});}
});
