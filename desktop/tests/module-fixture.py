"""Synthetic stopped-instance native QA fixture. No provider or real credentials."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zipfile


def digest(folder):
    sha=hashlib.sha256()
    for path in sorted(folder.rglob('*')):
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        if path.is_file():sha.update(path.relative_to(folder).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    return sha.hexdigest()


def code(folder,version,schema):
    folder.mkdir(parents=True)
    manifest={'id':'qa-upgrade','name':'Synthetic native module','version':version,'api_version':1,'state_version':schema,'description':'Isolated native module fixture','backend':'backend.py','capabilities':[],'default_enabled':False}
    (folder/'plugin.json').write_text(json.dumps(manifest),encoding='utf-8')
    (folder/'backend.py').write_text('from server.plugin_runtime.sdk import Plugin\nclass Extension(Plugin):\n    schema_version='+str(schema)+'\n    def migrate(self,data,old_version):\n        return {**data,"migrated":True}\n',encoding='utf-8')


if __name__=='__main__':
    root,archive,room=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
    data=root/'data';old=data/'plugins/qa-upgrade';code(old,'1.0.0',1)
    trust=data/'plugin-trust.json';records=json.loads(trust.read_text(encoding='utf-8')) if trust.exists() else {};records['qa-upgrade']=digest(old);trust.write_text(json.dumps(records),encoding='utf-8')
    con=sqlite3.connect(data/'tavern.sqlite3')
    try:
        with con:
            state=json.loads(con.execute('SELECT state_json FROM rooms WHERE id=?',(room,)).fetchone()[0]);state.setdefault('_plugins',{})['qa-upgrade']={'schema_version':1,'revision':0,'data':{'counter':7}}
            con.execute('UPDATE rooms SET state_json=?,revision=revision+1 WHERE id=?',(json.dumps(state),room))
    finally:con.close()
    candidate=archive.parent/'new-module';code(candidate,'2.0.0',2)
    with zipfile.ZipFile(archive,'w') as bundle:
        for path in sorted(candidate.iterdir()):bundle.write(path,'qa-upgrade/'+path.name)
