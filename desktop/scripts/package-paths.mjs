export const hostRoots=['server','plugins','presets','static','scripts','registry','templates','docs','plugin-packages','requirements-lock.txt','launcher-manifest.json'];
const excludedFolders=new Set(['data','backups','creations','__pycache__','.venv','.git','node_modules','artifacts','.cache','.pytest_cache','.test-data']);
/** Build from reviewed/indexed public source, never arbitrary local files. */
export function publicHostFile(name,tracked){
 const parts=name.split('/'),file=parts.at(-1)||'';
 return tracked.has(name)&&hostRoots.includes(parts[0])&&!parts.some(p=>excludedFolders.has(p))&&
  !(file.startsWith('.env')&&file!=='.env.example')&&!file.endsWith('.private.json')&&!/\.(?:sqlite3|db|log|pyc|exe)(?:$|[.-])/.test(file);
}
export function packageIndex(files){const tracked=new Set(files),allowed=new Set([...tracked].filter(name=>publicHostFile(name,tracked)));const directories=new Set();for(const file of allowed){const parts=file.split('/');for(let i=1;i<parts.length;i++)directories.add(parts.slice(0,i).join('/'));}return {allowed,directories};}
