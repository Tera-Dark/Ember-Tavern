"""Stopped-instance module transactions. Submitted Python requires explicit trust.

Snapshots are private operator data. No room content/rule/plugin pin is rewritten;
rollback restores only this module's namespace, never membership or sessions.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.config import ROOT
from server.contracts.plugin import validate_manifest, needs_capability_grant
from server.package_integrity import package_hash
from server.plugin_runtime.sdk import Plugin
from server.version import HOST_VERSION
from scripts.creator import write_json

PID = re.compile(r'^[a-z][a-z0-9-]{2,47}$')
HEX = re.compile(r'^[a-f0-9]{64}$')
TID = re.compile(r'^[a-f0-9]{32}$')


class ModuleError(ValueError):
    def __init__(self, code):
        self.code = code


def ordinary(path, missing=False):
    path = Path(path)
    if not path.is_absolute():
        raise ModuleError('unsafe_path')
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ModuleError('unsafe_path')
    if not missing and not (path.is_file() or path.is_dir()):
        raise ModuleError('missing_file')
    return path


def small_json(path, limit=128*1024):
    path = ordinary(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ModuleError('invalid_metadata')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def tree(folder):
    count = total = 0
    for path in folder.rglob('*'):
        ordinary(path)
        if not path.is_file() and not path.is_dir():
            raise ModuleError('unsafe_path')
        if path.is_file():
            count += 1
            total += path.stat().st_size
            if count > 1000 or total > 20*1024*1024:
                raise ModuleError('package_too_large')


def current(data, pid):
    if not PID.fullmatch(pid):
        raise ModuleError('invalid_plugin_id')
    if (ROOT/'plugins'/pid).exists():
        raise ModuleError('builtin_managed_by_host')
    folder = ordinary(data/'plugins'/pid)
    tree(folder)
    manifest = validate_manifest(small_json(folder/'plugin.json',32768), folder)
    if manifest['id'] != pid:
        raise ModuleError('invalid_metadata')
    return folder, manifest, package_hash(folder)


def trust_record(data):
    path = data/'plugin-trust.json'
    if not path.exists():
        return {}
    records = small_json(path)
    if not isinstance(records,dict) or len(records)>1000 or any(not PID.fullmatch(k) or not isinstance(v,str) or not HEX.fullmatch(v) for k,v in records.items()):
        raise ModuleError('invalid_trust_record')
    return records


def clone_database(source, target):
    source = ordinary(source)
    src = sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ModuleError('database_invalid')
    finally:
        dst.close();src.close()


def source_revision(data):
    """Guard stopped data against another writer; shared-memory is not content."""
    result = []
    for name in ('tavern.sqlite3', 'tavern.sqlite3-wal', 'plugin-trust.json'):
        path = ordinary(data/name, missing=True)
        if path.exists():
            if not path.is_file():
                raise ModuleError('unsafe_path')
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b''):
                    digest.update(chunk)
            result.append((name, digest.hexdigest()))
        else:
            result.append((name, None))
    return result


def file_digest(path):
    digest=hashlib.sha256()
    with ordinary(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def compatible(manifest, host_version):
    if not isinstance(host_version, str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', host_version):
        raise ModuleError('host_incompatible')
    if manifest['api_version'] != 1 or tuple(map(int, manifest['minimum_host'].split('.'))) > tuple(map(int, host_version.split('-')[0].split('.'))):
        raise ModuleError('host_incompatible')


def dependency_issues(data, candidate, host_version):
    """Inspect required manifests as data, without importing any module code."""
    issues=set();visited=set()
    installed_app=ordinary(data.parent/'app',missing=True)
    bundled=installed_app/'plugins' if installed_app.exists() else ROOT/'plugins'
    def visit(manifest, trail):
        pid=manifest['id']
        if pid in trail:
            issues.add(pid);return
        if pid in visited:return
        if len(trail)>100 or len(visited)>1000:
            raise ModuleError('dependencies_unavailable')
        for required in manifest.get('requires', []):
            if required==candidate['id']:
                visit(candidate, trail|{pid});continue
            folder=bundled/required
            if not folder.exists():folder=data/'plugins'/required
            try:
                tree(ordinary(folder))
                dependency=validate_manifest(small_json(folder/'plugin.json',32768),folder)
                if dependency['id']!=required:raise ModuleError('invalid_metadata')
                compatible(dependency, host_version)
            except (ModuleError, ValueError, OSError):
                issues.add(required);continue
            visit(dependency, trail|{pid})
        visited.add(pid)
    visit(candidate,set())
    return sorted(issues)


def rows(database):
    con = sqlite3.connect(ordinary(database).as_uri()+'?mode=ro',uri=True)
    try:
        result = con.execute('SELECT id,state_json FROM rooms').fetchall()
        if len(result)>10000:
            raise ModuleError('too_many_rooms')
        return [(rid,json.loads(raw)) for rid,raw in result]
    finally:
        con.close()


def check_pins(database, pid, target_hash, target_version):
    conflicts = 0
    for _, state in rows(database):
        lock = state.get('_preset_lock')
        if lock:
            pin = next((p for p in lock['plugins'] if p['id']==pid),None)
            if pin and (pin['sha256']!=target_hash or pin['version']!=target_version):
                conflicts += 1
    return conflicts


@contextlib.contextmanager
def archive_folder(path, expected, host_version=HOST_VERSION):
    path = ordinary(path)
    if not path.is_file() or path.stat().st_size>10*1024*1024:
        raise ModuleError('package_too_large')
    raw = path.read_bytes()
    if not isinstance(expected,str) or not HEX.fullmatch(expected) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ModuleError('archive_changed')
    with tempfile.TemporaryDirectory(prefix='ember-module-inspect-') as temporary:
        folder = Path(temporary)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries)>1000 or len({p.filename.casefold() for p in entries})!=len(entries) or sum(p.file_size for p in entries)>20*1024*1024:
                raise ModuleError('package_too_large')
            for entry in entries:
                name = PurePosixPath(entry.filename)
                mode = stat.S_IFMT(entry.external_attr>>16)
                segments=entry.filename.rstrip('/').split('/')
                reserved={'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}
                if name.is_absolute() or not name.parts or any(p in ('','.','..') or ':' in p or p.rstrip(' .')!=p or p.split('.')[0].upper() in reserved for p in segments) or '\\' in entry.filename or mode not in (0,stat.S_IFREG,stat.S_IFDIR):
                    raise ModuleError('unsafe_archive')
            archive.extractall(folder)
        manifests = list(folder.rglob('plugin.json'))
        if len(manifests)!=1:
            raise ModuleError('invalid_metadata')
        source = manifests[0].parent
        tree(source)
        manifest = validate_manifest(small_json(manifests[0],32768),source)
        compatible(manifest, host_version)
        yield source, manifest, package_hash(source)


def preview(data, archive, sha, host_version=HOST_VERSION):
    data = ordinary(data)
    with archive_folder(archive,sha,host_version) as (_, candidate, digest):
        pid = candidate['id']
        _, old, old_hash = current(data,pid)
        blocked = check_pins(data/'tavern.sqlite3',pid,digest,candidate['version'])
        newer = tuple(map(int,candidate['version'].split('.')))>tuple(map(int,old['version'].split('.')))
        issues=dependency_issues(data,candidate,host_version)
        return {'plugin_id':pid,'name':candidate['name'],'authors':candidate['authors'],'license':candidate['license'],'requires':candidate['requires'],'capabilities':candidate['capabilities'],'dependency_issues':issues,'old_version':old['version'],'new_version':candidate['version'],'old_hash':old_hash,'new_hash':digest,'archive_sha256':sha,'minimum_host':candidate['minimum_host'],'backend':bool(candidate.get('backend')),'capability_grant':needs_capability_grant(candidate),'pinned_rooms':blocked,'can_upgrade':blocked==0 and newer and not issues,'code_executed':False}


def transaction_dir(data, identity):
    if not TID.fullmatch(identity):
        raise ModuleError('invalid_checkpoint')
    base = ordinary(data).parent/'module-upgrades'
    ordinary(base,missing=True)
    return ordinary(base/identity,missing=True)


def read_journal(data, identity):
    directory = transaction_dir(data,identity)
    journal = small_json(directory/'transaction.json')
    if journal.get('format')!='ember.plugin-transaction/v1' or journal.get('id')!=identity or not PID.fullmatch(journal.get('plugin_id','')) or not HEX.fullmatch(journal.get('old_hash','')) or not HEX.fullmatch(journal.get('new_hash','')) or not HEX.fullmatch(journal.get('staged_db_sha256','')) or type(journal.get('trust_existed')) is not bool or journal.get('state') not in ('preflight','prepared','code-swapped','data-swapped','committed','recovered') or journal.get('action') not in ('upgrade','rollback'):
        raise ModuleError('invalid_checkpoint')
    files=journal.get('source_files')
    if not isinstance(files,dict) or set(files)!={'tavern.sqlite3','tavern.sqlite3-wal','plugin-trust.json'} or not isinstance(files['tavern.sqlite3'],str) or any(value is not None and (not isinstance(value,str) or not HEX.fullmatch(value)) for value in files.values()):
        raise ModuleError('invalid_checkpoint')
    return directory,journal


def recover_one(data, identity):
    directory,journal = read_journal(data,identity)
    if journal['state'] in ('committed','recovered'):
        return
    target = data/'plugins'/journal['plugin_id']
    displaced = directory/'displaced-code'
    original = directory/'displaced.sqlite3'
    database = data/'tavern.sqlite3'
    if journal['state']=='preflight':
        if package_hash(ordinary(target))!=journal['old_hash']:
            raise ModuleError('recovery_blocked')
        journal['state']='recovered';write_json(directory/'transaction.json',journal)
        return
    # Check the private recovery record before moving any managed live file.
    old_trust = small_json(directory/'trust-before.json')
    if not isinstance(old_trust, dict) or any(not PID.fullmatch(k) or not isinstance(v, str) or not HEX.fullmatch(v) for k,v in old_trust.items()):
        raise ModuleError('invalid_trust_record')
    expected_database=journal['source_files']['tavern.sqlite3']
    if original.exists():
        if file_digest(original)!=expected_database or database.exists() and file_digest(database)!=journal['staged_db_sha256']:
            raise ModuleError('recovery_blocked')
    elif not database.exists() or file_digest(database)!=expected_database:
        raise ModuleError('recovery_blocked')
    sidecars=[]
    for suffix in ('-wal','-shm'):
        prior=ordinary(directory/('displaced.sqlite3'+suffix),missing=True)
        live=ordinary(data/('tavern.sqlite3'+suffix),missing=True)
        if prior.exists():
            if live.exists():raise ModuleError('recovery_blocked')
            if suffix=='-wal' and file_digest(prior)!=journal['source_files']['tavern.sqlite3-wal']:
                raise ModuleError('recovery_blocked')
            sidecars.append((prior,live))
    if displaced.exists():
        if package_hash(ordinary(displaced))!=journal['old_hash']:
            raise ModuleError('recovery_blocked')
        if target.exists():
            if package_hash(ordinary(target))!=journal['new_hash']:
                raise ModuleError('recovery_blocked')
            # Exact scoped module target checked, then moved; no recursive delete.
            target.rename(directory/'interrupted-code')
        displaced.rename(target)
    elif not target.exists() or package_hash(ordinary(target))!=journal['old_hash']:
        raise ModuleError('recovery_blocked')
    restoring_database = original.exists()
    if restoring_database:
        if database.exists():
            if hashlib.sha256(database.read_bytes()).hexdigest()!=journal['staged_db_sha256']:
                raise ModuleError('recovery_blocked')
            database.rename(directory/'interrupted.sqlite3')
        original.rename(database)
    # Resume even if recovery itself stopped after restoring the main database.
    for prior,live in sidecars:
        prior.rename(live)
    if restoring_database or sidecars or journal['state']=='data-swapped':
        if journal['trust_existed']:
            write_json(data/'plugin-trust.json',old_trust)
        else:
            (data/'plugin-trust.json').unlink(missing_ok=True)
    journal['state']='recovered';write_json(directory/'transaction.json',journal)


def recover(data):
    data=ordinary(data);base=data.parent/'module-upgrades'
    barrier=data.parent/'update-journal.json'
    if not base.exists():
        if barrier.exists():
            raise ModuleError('recovery_blocked')
        return {'recovered':True}
    ordinary(base)
    if barrier.exists():
        marker=small_json(barrier)
        if marker.get('format')!='ember.module-barrier/v1' or not TID.fullmatch(marker.get('transaction_id','')):
            raise ModuleError('host_update_in_progress')
        read_journal(data,marker['transaction_id'])
    for child in sorted(base.iterdir()):
        if TID.fullmatch(child.name):
            recover_one(data,child.name)
    if barrier.exists():
        barrier.unlink()
    return {'recovered':True}


def backend(folder, manifest, approved):
    if not manifest.get('backend'):
        return None
    if not approved:
        raise ModuleError('python_trust_required')
    digest=package_hash(folder)
    spec=importlib.util.spec_from_file_location('ember_migration_'+digest,folder/'backend.py',submodule_search_locations=[str(folder)])
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    extension=module.Extension()
    if not isinstance(extension,Plugin) or extension.schema_version!=manifest.get('state_version',1):
        raise ModuleError('state_version_invalid')
    if 'gm' in manifest.get('hooks',[]) and not callable(getattr(extension,'gm',None)):
        raise ModuleError('gm_implementation_missing')
    return extension


def migrate(database, pid, extension, previous=None):
    before = {rid:state.get('_plugins',{}).get(pid) for rid,state in rows(previous)} if previous else None
    con=sqlite3.connect(database)
    try:
        with con:
            for rid, state in rows(database):
                namespace=state.get('_plugins',{}).get(pid)
                if before is not None:
                    old=before.get(rid)
                    if old is None:
                        state.get('_plugins',{}).pop(pid,None)
                    else:
                        state.setdefault('_plugins',{})[pid]={**old,'revision':max((namespace or {}).get('revision',0),old.get('revision',0))+1}
                elif namespace and extension:
                    output=extension.migrate(namespace['data'],namespace['schema_version'])
                    if not isinstance(output,dict) or len(json.dumps(output,allow_nan=False).encode())>262144:
                        raise ModuleError('migration_invalid')
                    state['_plugins'][pid]={'schema_version':extension.schema_version,'revision':namespace['revision']+1,'data':output}
                else:
                    continue
                # No other plot/security/lock field changes, no security table writes.
                con.execute('UPDATE rooms SET state_json=?,revision=revision+1 WHERE id=?',(json.dumps(state,ensure_ascii=False,separators=(',',':')),rid))
        con.execute('PRAGMA journal_mode=DELETE')
        if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ModuleError('database_invalid')
    finally:
        con.close()


def commit(data, source, manifest, digest, identity, approved, grant, previous=None, host_version=HOST_VERSION):
    recover(data)
    old_folder,old,old_hash=current(data,manifest['id']);pid=manifest['id']
    if dependency_issues(data,manifest,host_version):
        raise ModuleError('dependencies_unavailable')
    if check_pins(data/'tavern.sqlite3',pid,digest,manifest['version']):
        raise ModuleError('pinned_rooms_require_original')
    if manifest.get('backend') and not approved:
        raise ModuleError('python_trust_required')
    if needs_capability_grant(manifest) and not (approved or grant):
        raise ModuleError('capability_grant_required')
    directory=transaction_dir(data,identity)
    if directory.exists():
        raise ModuleError('checkpoint_exists')
    directory.mkdir(parents=True)
    trust=trust_record(data);existed=(data/'plugin-trust.json').exists();write_json(directory/'trust-before.json',trust)
    original_revision = source_revision(data)
    journal={'format':'ember.plugin-transaction/v1','id':identity,'plugin_id':pid,'old_version':old['version'],'new_version':manifest['version'],'old_hash':old_hash,'new_hash':digest,'source_files':dict(original_revision),'staged_db_sha256':'0'*64,'state':'preflight','action':'rollback' if previous else 'upgrade','trust_existed':existed,'created_at':datetime.now(timezone.utc).isoformat()}
    write_json(directory/'transaction.json',journal)
    tree(old_folder);shutil.copytree(old_folder,directory/'old-code')
    shutil.copytree(source,directory/'candidate-code')
    clone_database(data/'tavern.sqlite3',directory/'before.sqlite3')
    clone_database(data/'tavern.sqlite3',directory/'staged.sqlite3')
    # Candidate code is imported only after explicit trust; preflight mutates a copy.
    extension=backend(directory/'candidate-code',manifest,approved)
    migrate(directory/'staged.sqlite3',pid,extension,previous)
    if source_revision(data) != original_revision:
        raise ModuleError('source_changed')
    staged_hash=hashlib.sha256((directory/'staged.sqlite3').read_bytes()).hexdigest()
    journal.update(staged_db_sha256=staged_hash,state='prepared')
    write_json(directory/'transaction.json',journal)
    write_json(data.parent/'update-journal.json',{'format':'ember.module-barrier/v1','transaction_id':identity})
    try:
        if source_revision(data) != original_revision or package_hash(old_folder)!=old_hash or package_hash(directory/'candidate-code')!=digest:
            raise ModuleError('source_changed')
        old_folder.rename(directory/'displaced-code')
        (directory/'candidate-code').rename(old_folder)
        journal['state']='code-swapped';write_json(directory/'transaction.json',journal)
        for suffix in ('','-wal','-shm'):
            path=data/('tavern.sqlite3'+suffix)
            if path.exists():
                ordinary(path).rename(directory/('displaced.sqlite3'+suffix))
        (directory/'staged.sqlite3').rename(data/'tavern.sqlite3')
        journal['state']='data-swapped';write_json(directory/'transaction.json',journal)
        if approved or grant:
            trust[pid]=digest
        else:
            trust.pop(pid,None)
        write_json(data/'plugin-trust.json',trust)
        journal['state']='committed';write_json(directory/'transaction.json',journal)
    except BaseException:
        recover_one(data,identity)
        raise
    return {'committed':True,'checkpoint_id':identity,'plugin_id':pid,'version':manifest['version'],'package_hash':digest}


def upgrade(data, archive, sha, identity, approved=False, grant=False, expected_old=None, host_version=HOST_VERSION):
    data=ordinary(data)
    with archive_folder(archive,sha,host_version) as (folder,manifest,digest):
        _,old,actual_old=current(data,manifest['id'])
        if expected_old is not None and actual_old!=expected_old:
            raise ModuleError('source_changed')
        if tuple(map(int,manifest['version'].split('.')))<=tuple(map(int,old['version'].split('.'))):
            raise ModuleError('version_not_newer')
        return commit(data,folder,manifest,digest,identity,approved,grant,host_version=host_version)


def rollback(data, checkpoint, identity, approved=False, grant=False, host_version=HOST_VERSION):
    data=ordinary(data);directory,journal=read_journal(data,checkpoint)
    if journal['state']!='committed':
        raise ModuleError('checkpoint_unavailable')
    _,_,actual=current(data,journal['plugin_id'])
    if actual!=journal['new_hash']:
        raise ModuleError('source_changed')
    source=ordinary(directory/'old-code');tree(source)
    if package_hash(source)!=journal['old_hash']:
        raise ModuleError('checkpoint_changed')
    manifest=validate_manifest(small_json(source/'plugin.json',32768),source)
    compatible(manifest, host_version)
    return commit(data,source,manifest,journal['old_hash'],identity,approved,grant,directory/'before.sqlite3',host_version)


def history(data, host_version=HOST_VERSION):
    data=ordinary(data);base=data.parent/'module-upgrades';records=[]
    if not base.exists():
        return {'records':records}
    ordinary(base)
    for child in sorted(base.iterdir()):
        if not TID.fullmatch(child.name):
            continue
        directory,journal=read_journal(data,child.name)
        record={k:journal[k] for k in ('id','plugin_id','old_version','new_version','old_hash','new_hash','state','action')}
        record['created_at']=journal.get('created_at','')
        record.update(can_rollback=False,backend=False,capability_grant=False,pinned_rooms=0)
        if journal['state']=='committed':
            source=ordinary(directory/'old-code');tree(source)
            if package_hash(source)!=journal['old_hash']:
                raise ModuleError('checkpoint_changed')
            manifest=validate_manifest(small_json(source/'plugin.json',32768),source)
            supported = True
            try:
                compatible(manifest, host_version)
                supported = not dependency_issues(data,manifest,host_version)
            except ModuleError:
                supported = False
            _,_,actual=current(data,journal['plugin_id'])
            pinned=check_pins(data/'tavern.sqlite3',journal['plugin_id'],journal['old_hash'],journal['old_version'])
            record.update(can_rollback=supported and actual==journal['new_hash'] and pinned==0,backend=bool(manifest.get('backend')),capability_grant=needs_capability_grant(manifest),pinned_rooms=pinned)
        records.append(record)
    return {'records':sorted(records,key=lambda r:r['created_at'],reverse=True)[:100]}


if __name__=='__main__':
    try:
        request=json.loads(sys.stdin.buffer.read(48*1024+1));data=Path(request['data_dir']);operation=request['operation']
        host_version=request.get('host_version', HOST_VERSION)
        with open(os.devnull, 'w', encoding='utf-8') as discarded, contextlib.redirect_stdout(discarded),contextlib.redirect_stderr(discarded):
            if operation=='preview':result=preview(data,Path(request['archive']),request['sha256'],host_version)
            elif operation=='upgrade':result=upgrade(data,Path(request['archive']),request['sha256'],request['transaction_id'],request.get('trust_backend') is True,request.get('grant_capabilities') is True,request.get('old_hash'),host_version)
            elif operation=='rollback':result=rollback(data,request['checkpoint_id'],request['transaction_id'],request.get('trust_backend') is True,request.get('grant_capabilities') is True,host_version)
            elif operation=='recover':result=recover(data)
            elif operation=='history':result=history(data,host_version)
            else:raise ModuleError('unsupported_operation')
        response={'ok':True,**result}
    except Exception as error:
        response={'ok':False,'code':error.code if isinstance(error,ModuleError) else 'module_operation_failed'}
    print(json.dumps(response,ensure_ascii=False,separators=(',',':')))
