import {readFile,readdir} from 'node:fs/promises';
import {join,relative} from 'node:path';
import {createHash} from 'node:crypto';

const versionPattern=/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(?:alpha|beta|rc)\.[1-9]\d*)?$/;
export async function releaseVersions(repo){
  const desktop=JSON.parse(await readFile(join(repo,'desktop/package.json'),'utf8')).version;
  const web=JSON.parse(await readFile(join(repo,'web/package.json'),'utf8')).version;
  const manifest=JSON.parse(await readFile(join(repo,'launcher-manifest.json'),'utf8'));
  const launcher=(await readFile(join(repo,'launcher/internal/engine/types.go'),'utf8')).match(/const LauncherVersion = "([^"]+)"/)?.[1];
  const host=(await readFile(join(repo,'server/version.py'),'utf8')).match(/HOST_VERSION = '([^']+)'/)?.[1];
  if(![desktop,web,launcher,host].every(value=>typeof value==='string'&&versionPattern.test(value)))throw new Error('Version fields must be explicit release versions.');
  if(desktop!==launcher||manifest.minimum_launcher!==launcher||web!==host||manifest.app_version!==host)throw new Error('Desktop/engine and host/web/manifest versions are inconsistent.');
  return {desktop_version:desktop,launcher_version:launcher,app_version:host,tag:'desktop-v'+desktop};
}
export async function fileDigest(path){
  const bytes=await readFile(path);return {sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length};
}
export async function hostDigests(folder){
  const result=[];
  async function walk(path){
    for(const entry of (await readdir(path,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))){
      const file=join(path,entry.name),name=relative(folder,file).split('\\').join('/');
      if(entry.isSymbolicLink())throw new Error('Bundled host must not contain symlinks.');
      if(entry.isDirectory())await walk(file);
      else if(entry.isFile()&&name!=='desktop-bundle.json')result.push({path:name,...await fileDigest(file)});
      else if(!entry.isFile())throw new Error('Bundled host contains a special file.');
    }
  }
  await walk(folder);return result;
}
