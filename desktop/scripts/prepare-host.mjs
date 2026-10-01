import {cp,mkdir,rm,writeFile,readFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
const repo=resolve(import.meta.dirname,'../..'),target=join(repo,'desktop/resources/host');
await rm(target,{recursive:true,force:true});await mkdir(target,{recursive:true});
for(const name of ['server','plugins','static','scripts','registry','templates','docs','plugin-packages','requirements-lock.txt','launcher-manifest.json'])await cp(join(repo,name),join(target,name),{recursive:true,filter:path=>!path.includes('__pycache__')&&!path.endsWith('.pyc')});
await writeFile(join(target,'desktop-bundle.json'),JSON.stringify({commit:execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim(),source:'Tera-Dark/Ember-Tavern',app_version:JSON.parse(await readFile(join(repo,'launcher-manifest.json'),'utf8')).app_version},null,2));
console.log('Bundled only host source/static/contracts; no .env, database or user content.');
