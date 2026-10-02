import {readFile,writeFile,lstat} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {fileDigest,releaseVersions} from './build-info.mjs';

export function checkSmoke(report,versions,commit){
  if(report.status!=='passed'||report.graceful_shutdown!==true)throw new Error('Installed Windows smoke did not pass / exit gracefully.');
  if(report.source_commit!==commit||report.source_dirty!==false)throw new Error('Smoke source does not match the clean release commit.');
  for(const field of ['desktop_version','launcher_version','app_version'])if(report[field]!==versions[field])throw new Error('Smoke version mismatch: '+field);
}
function namesFor(versions){return [
  ['ember-desktop-'+versions.desktop_version+'-x64-setup.exe','installer'],
  ['ember-desktop-'+versions.desktop_version+'-x64-portable.exe','portable'],
];}
export async function createProvenance(dist,smokePath,versions,commit,builtAt=new Date().toISOString()){
  if(!/^[a-f0-9]{40}$/.test(commit))throw new Error('An exact commit is required.');
  const smoke=JSON.parse(await readFile(smokePath,'utf8'));checkSmoke(smoke,versions,commit);
  const artifacts=[];
  for(const [name,role] of namesFor(versions)){
    const path=join(dist,name);const info=await lstat(path);if(!info.isFile()||info.isSymbolicLink()||info.size===0)throw new Error('Release binary is missing or not a regular nonempty file.');
    const digest=await fileDigest(path);artifacts.push({name,role,...digest});
    const sumName=name+'.sha256',sum=await readFile(join(dist,sumName),'utf8');
    if(sum.replace(/\r/g,'').trim()!==digest.sha256+'  '+name)throw new Error('Checksum file does not match binary: '+name);
    artifacts.push({name:sumName,role:'checksum',...await fileDigest(join(dist,sumName))});
  }
  artifacts.push({name:'desktop-smoke.json',role:'installed-windows-smoke',...await fileDigest(smokePath)});
  return {format:'ember.desktop-release/v1',repository:'Tera-Dark/Ember-Tavern',commit,...versions,built_at:builtAt,code_signed:false,artifacts};
}
export async function verifyProvenance(dist,smokePath,path,versions,commit){
  const actual=JSON.parse(await readFile(path,'utf8'));
  const expected=await createProvenance(dist,smokePath,versions,commit,actual.built_at);
  if(JSON.stringify(actual)!==JSON.stringify(expected))throw new Error('Provenance / binary / smoke mismatch; publication refused.');
  return actual;
}
async function main(){
  const [command='versions',folder,requestedCommit]=process.argv.slice(2);
  const repo=resolve(import.meta.dirname,'../..'),versions=await releaseVersions(repo);
  if(command==='versions'){console.log(JSON.stringify(versions));return;}
  const commit=requestedCommit||execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim();
  if(command==='create'){
    const dist=join(repo,'desktop/dist'),smoke=join(repo,'desktop-smoke.json');
    const proof=await createProvenance(dist,smoke,versions,commit);
    await writeFile(join(repo,'desktop-provenance.json'),JSON.stringify(proof,null,2)+'\n');console.log('Verified release provenance:',proof.tag,commit);return;
  }
  if(command==='verify'&&folder){
    const base=resolve(folder);await verifyProvenance(join(base,'desktop/dist'),join(base,'desktop-smoke.json'),join(base,'desktop-provenance.json'),versions,commit);console.log('Release artifact provenance verified:',versions.tag,commit);return;
  }
  throw new Error('Usage: release-metadata.mjs versions | create [unused] [commit] | verify <artifact-directory> <commit>');
}
if(process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url)main().catch(error=>{console.error(error.message);process.exitCode=1;});
