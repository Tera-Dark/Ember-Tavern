const {test}=require('node:test');const assert=require('node:assert/strict');
test('host bundles exclude ignored/unreviewed files and private data even if accidentally indexed',async()=>{
 const {packageIndex}=await import('../scripts/package-paths.mjs');
 const files=['server/app.py','plugins/scene-map/plugin.json','plugin-packages/map.zip','docs/ARCHITECTURE.md','requirements-lock.txt','server/.env','server/secret.private.json','server/data/tavern.sqlite3','scripts/private.sqlite3-wal','docs/backups/report.json','scripts/installer.exe','plugins/__pycache__/backend.pyc'];
 const index=packageIndex(files);
 assert.deepEqual([...index.allowed],files.slice(0,5));assert(index.directories.has('plugins/scene-map'));assert(!index.allowed.has('server/untracked-secrets.json'));assert(!index.directories.has('server/data'));
});
