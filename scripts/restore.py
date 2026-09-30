#!/usr/bin/env python3
"""Restore a trusted V2 bundle into a NEW empty data directory. Never overwrite live data.
--stopped is operator confirmation, not automatic process shutdown/PID verification.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,shutil,sqlite3,tempfile,zipfile

def restore(source,target,expected=None):
    source=Path(source);target=Path(target)
    if expected and hashlib.sha256(source.read_bytes()).hexdigest()!=expected.lower():raise ValueError('Backup SHA256 mismatch')
    if target.exists() and (not target.is_dir() or any(target.iterdir())):raise ValueError('Restore target must be new or empty')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.restore-',dir=target.parent) as folder:
        with zipfile.ZipFile(source) as archive:
            infos=archive.infolist()
            if len(infos)>10000 or sum(i.file_size for i in infos)>2*1024**3:raise ValueError('Backup exceeds restore limits')
            for i in infos:
                p=PurePosixPath(i.filename)
                if p.is_absolute() or '..' in p.parts or '\\' in i.filename or ((i.external_attr>>16)&0o170000)==0o120000:raise ValueError('Unsafe backup path / symlink')
            if len({i.filename for i in infos})!=len(infos):raise ValueError('Duplicate archive entries')
            manifest=json.loads(archive.read('backup-manifest.json'))
            if manifest.get('format')!='ember-tavern-backup/v2':raise ValueError('Unsupported backup format')
            declared={item['path'] for item in manifest['files']}
            if declared!={i.filename for i in infos if i.filename!='backup-manifest.json'}:raise ValueError('Backup manifest mismatch')
            for item in manifest['files']:
                data=archive.read(item['path'])
                if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Backup file checksum mismatch')
            archive.extractall(folder)
        con=sqlite3.connect(Path(folder)/'tavern.sqlite3')
        try:
            if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Restored DB failed integrity check')
        finally:con.close()
        Path(folder,'backup-manifest.json').unlink()
        if target.exists():target.rmdir()
        shutil.copytree(folder,target)
    return {'restored_to':str(target),'files':len(declared),'integrity_check':'ok','warning':'Review restored plugin code and trust records before starting; .env is NOT backed up.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--target',required=True);p.add_argument('--sha256');p.add_argument('--stopped',action='store_true');args=p.parse_args()
    if not args.stopped:raise SystemExit('Stop the service first, then confirm --stopped; this script does not stop it for you.')
    try:print(json.dumps(restore(args.source,args.target,args.sha256),ensure_ascii=False,indent=2))
    except Exception as error:raise SystemExit(str(error))
