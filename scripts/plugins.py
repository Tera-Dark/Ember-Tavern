#!/usr/bin/env python3
"""Operator-only installer. Nothing fetched from GitHub is silently trusted or executed."""
import argparse,hashlib,json,shutil,sys,tempfile,zipfile
from pathlib import Path,PurePosixPath
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from server.config import ROOT,settings
from server.plugin_runtime.manager import package_hash,ID_PATTERN

def install(source,expected=None,trust_backend=False,grant_capabilities=False):
    if source.startswith('https://'):
        if not expected:raise ValueError('Remote installs require an independently verified --sha256')
        with urlopen(source,timeout=30) as response:data=response.read(10*1024*1024+1)
    else:data=Path(source).read_bytes()
    if len(data)>10*1024*1024:raise ValueError('Package exceeds 10 MiB')
    archive_hash=hashlib.sha256(data).hexdigest()
    if expected and archive_hash!=expected.lower():raise ValueError('Archive SHA256 mismatch')
    with tempfile.TemporaryDirectory() as temporary:
        temporary=Path(temporary);bundle=temporary/'bundle.zip';bundle.write_bytes(data)
        target=temporary/'unpacked';target.mkdir()
        with zipfile.ZipFile(bundle) as archive:
            if sum(i.file_size for i in archive.infolist())>20*1024*1024:raise ValueError('Unpacked package exceeds20 MiB')
            for entry in archive.infolist():
                path=PurePosixPath(entry.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or ((entry.external_attr>>16)&0o170000)==0o120000:raise ValueError('Unsafe archive path / symlink')
            archive.extractall(target)
        manifests=list(target.rglob('plugin.json'))
        if len(manifests)!=1:raise ValueError('Exactly one plugin.json required')
        folder=manifests[0].parent;m=json.loads(manifests[0].read_text());pid=m['id']
        if not ID_PATTERN.fullmatch(pid) or m.get('api_version')!=1:raise ValueError('Invalid ID or incompatible API version')
        if (ROOT/'plugins'/pid).exists():raise ValueError('Cannot replace bundled plugins using community installer')
        if m.get('backend') and not trust_backend:raise ValueError('Python backend is trusted server code. Review first and explicitly pass --trust-backend')
        if any(not c.startswith('read:') for c in m.get('capabilities',[])) and not (trust_backend or grant_capabilities):raise ValueError('High-risk UI capability requires review and explicit --grant-capabilities')
        destination=settings.data_dir/'plugins'/pid
        if destination.exists():raise ValueError('Already installed. Remove/backup this plugin with the server stopped before upgrading.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        staging=destination.parent/('.install-'+__import__('uuid').uuid4().hex)
        try:shutil.copytree(folder,staging);staging.rename(destination)
        finally:
            if staging.exists():shutil.rmtree(staging)
        trust=settings.data_dir/'plugin-trust.json';trusted=json.loads(trust.read_text()) if trust.exists() else {}
        if trust_backend or grant_capabilities:trusted[pid]=package_hash(destination);temporary_trust=trust.with_suffix('.json.tmp');temporary_trust.write_text(json.dumps(trusted,indent=2));temporary_trust.replace(trust)
        return {'installed':pid,'archive_sha256':archive_hash,'package_hash':package_hash(destination),'backend_trusted':bool(m.get('backend') and trust_backend),'capabilities_granted':bool(trust_backend or grant_capabilities)}

def package(source,output):
    source=Path(source);output=Path(output)
    if not (source/'plugin.json').is_file():raise ValueError('plugin.json required')
    if output.resolve().is_relative_to(source.resolve()):raise ValueError('Write package outside source folder')
    output.parent.mkdir(parents=True,exist_ok=True);files=[]
    for path in sorted(source.rglob('*')):
        parts=path.relative_to(source).parts
        if any(p.startswith('.') or p in ('__pycache__','node_modules') for p in parts) or path.suffix=='.pyc':continue
        if path.is_symlink():raise ValueError('Symlinks cannot be packaged')
        if path.is_file():files.append(path)
    if sum(p.stat().st_size for p in files)>20*1024*1024:raise ValueError('Package expands beyond 20 MiB')
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for path in files:z.write(path,source.name+'/'+path.relative_to(source).as_posix())
    if output.stat().st_size>10*1024*1024:output.unlink();raise ValueError('Package exceeds10 MiB')
    print(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+str(output))

if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    i=sub.add_parser('install');i.add_argument('source');i.add_argument('--sha256');i.add_argument('--trust-backend',action='store_true');i.add_argument('--grant-capabilities',action='store_true')
    b=sub.add_parser('package');b.add_argument('folder');b.add_argument('output')
    sub.add_parser('lock-builtins')
    args=p.parse_args()
    if args.command=='lock-builtins':
        lock={d.name:package_hash(d) for d in (ROOT/'plugins').iterdir() if d.is_dir() and (d/'plugin.json').exists()}
        lock_path=ROOT/'plugins/catalog.lock.json';temporary_lock=lock_path.with_suffix('.json.tmp');temporary_lock.write_text(json.dumps(lock,indent=2));temporary_lock.replace(lock_path);print('Reviewed bundled plugin lock updated')
    elif args.command=='package':package(args.folder,args.output)
    else:
        try:print(json.dumps(install(args.source,args.sha256,args.trust_backend,args.grant_capabilities),ensure_ascii=False,indent=2))
        except Exception as exc:raise SystemExit(str(exc))
