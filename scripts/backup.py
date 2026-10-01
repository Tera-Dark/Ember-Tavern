#!/usr/bin/env python3
"""SQLite online backup; --bundle also includes immutable assets and installed plugins.
A DB snapshot is taken before copying immutable files: extra orphan files are harmless.
Do not upgrade/remove plugins or garbage-collect assets while backing up.
"""
from pathlib import Path
import argparse,hashlib,json,sqlite3,sys,tempfile,zipfile
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from server.config import settings

def database_backup(output):
    source=sqlite3.connect(f'file:{settings.db_path}?mode=ro',uri=True);target=sqlite3.connect(output)
    try:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed')
    finally:target.close();source.close()

def backup(output,bundle=False):
    output=Path(output)
    if not settings.db_path.exists():raise ValueError(f'Database does not exist: {settings.db_path}')
    if output.resolve()==settings.db_path.resolve() or output.exists():raise ValueError('Backup output must be new and not overwrite live DB')
    if output.resolve().is_relative_to(settings.data_dir.resolve()):raise ValueError('Keep backups outside the live data directory')
    output.parent.mkdir(parents=True,exist_ok=True)
    if not bundle:database_backup(output);return {'path':str(output),'integrity_check':'ok','format':'sqlite-only'}
    with tempfile.TemporaryDirectory(prefix='.backup-',dir=output.parent) as folder:
        database=Path(folder)/'tavern.sqlite3';database_backup(database);files=[('tavern.sqlite3',database)]
        for name in ['assets','audio','plugins','plugin-trust.json']:
            base=settings.data_dir/name
            candidates=base.rglob('*') if base.is_dir() else [base]
            for path in candidates:
                if path.is_symlink():raise ValueError('Backup refuses symlinks')
                if path.is_file() and '__pycache__' not in path.parts and not path.name.endswith('.tmp'):
                    files.append((path.relative_to(settings.data_dir).as_posix(),path))
        manifest={'format':'ember-tavern-backup/v2','created_at':datetime.now(timezone.utc).isoformat(),'files':[]}
        staged=Path(folder)/'bundle.zip'
        with zipfile.ZipFile(staged,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,path in files:
                data=path.read_bytes();manifest['files'].append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()});archive.writestr(name,data)
            archive.writestr('backup-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        staged.replace(output)
    return {'path':str(output),'integrity_check':'ok','format':'ember-tavern-backup/v2','files':len(files),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--bundle',action='store_true');args=parser.parse_args()
    output=args.output or Path('backups')/('tavern-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+('.zip' if args.bundle else '.sqlite3'))
    try:print(json.dumps(backup(output,args.bundle),ensure_ascii=False,indent=2))
    except Exception as error:raise SystemExit(str(error))
