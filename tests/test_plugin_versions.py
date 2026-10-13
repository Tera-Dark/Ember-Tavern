from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile
import subprocess
import sys
import pytest
from scripts.plugin_versions import preview, upgrade, rollback, recover, history, ModuleError
from server.package_integrity import package_hash


def module(folder, version='1.0.0', schema=1, fail=False, marker=None):
    folder.mkdir(parents=True)
    manifest={'id':'qa-upgrade','name':'Synthetic upgrade','version':version,'api_version':1,'state_version':schema,'description':'Synthetic transaction fixture','backend':'backend.py','capabilities':[]}
    (folder/'plugin.json').write_text(json.dumps(manifest),encoding='utf-8')
    code='from server.plugin_runtime.sdk import Plugin\n'
    if marker:
        code+='from pathlib import Path\nPath('+repr(str(marker))+').write_text("trusted execution")\n'
    code+='class Extension(Plugin):\n    schema_version='+str(schema)+'\n    def migrate(self,data,old_version):\n'
    code+= '        raise ValueError("private migration body must not be emitted")\n' if fail else '        return {**data,"migrated":True}\n'
    (folder/'backend.py').write_text(code,encoding='utf-8')
    return manifest


def fixture(tmp_path, fail=False, marker=None):
    data=tmp_path/'数据 # data';data.mkdir()
    old=data/'plugins/qa-upgrade';module(old)
    trust={'qa-upgrade':package_hash(old)};(data/'plugin-trust.json').write_text(json.dumps(trust),encoding='utf-8')
    database=data/'tavern.sqlite3'
    with closing(sqlite3.connect(database)) as con, con:
        con.executescript('CREATE TABLE rooms(id TEXT PRIMARY KEY,state_json TEXT,revision INTEGER);CREATE TABLE members(id TEXT);CREATE TABLE sessions(id TEXT);CREATE TABLE guest_invites(enabled INTEGER);')
        state={'plot':'present timeline','_rule_state':{'unchanged':True},'_plugins':{'qa-upgrade':{'schema_version':1,'revision':3,'data':{'counter':2}}}}
        con.execute('INSERT INTO rooms VALUES (?,?,?)',('room',json.dumps(state),7))
        con.execute('INSERT INTO members VALUES (?)',('current-player',));con.execute('INSERT INTO sessions VALUES (?)',('current-session',));con.execute('INSERT INTO guest_invites VALUES (0)')
    source=tmp_path/'new-code';module(source,'2.0.0',2,fail,marker)
    archive=tmp_path/'new.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for path in source.iterdir():z.write(path,'qa-upgrade/'+path.name)
    return data,archive,hashlib.sha256(archive.read_bytes()).hexdigest()


def state(data):
    with closing(sqlite3.connect(data/'tavern.sqlite3')) as con, con:
        return json.loads(con.execute('SELECT state_json FROM rooms WHERE id="room"').fetchone()[0])


def test_preview_never_executes_candidate_and_upgrade_needs_explicit_trust(tmp_path):
    marker=tmp_path/'executed';data,archive,sha=fixture(tmp_path,marker=marker)
    result=preview(data,archive,sha)
    assert result['can_upgrade'] and result['backend'] and result['code_executed'] is False
    assert not marker.exists()
    before=(data/'tavern.sqlite3').read_bytes()
    with pytest.raises(ModuleError,match='python_trust_required'):upgrade(data,archive,sha,'a'*32)
    assert (data/'tavern.sqlite3').read_bytes()==before
    assert not marker.exists()


def test_upgrade_migrates_copy_and_rollback_preserves_current_plot_and_security(tmp_path):
    data,archive,sha=fixture(tmp_path)
    old_hash=package_hash(data/'plugins/qa-upgrade')
    result=upgrade(data,archive,sha,'a'*32,True)
    assert state(data)['_plugins']['qa-upgrade']['schema_version']==2
    assert state(data)['_plugins']['qa-upgrade']['data']=={'counter':2,'migrated':True}
    with closing(sqlite3.connect(data/'tavern.sqlite3')) as con, con:
        current=state(data);current['plot']='newer plot must stay';current['_plugins']['qa-upgrade']['data']['counter']=99
        con.execute('UPDATE rooms SET state_json=?',(json.dumps(current),))
        con.execute('DELETE FROM sessions');con.execute('INSERT INTO sessions VALUES (?)',('new-session',))
    reverted=rollback(data,'a'*32,'b'*32,True)
    assert reverted['version']=='1.0.0' and package_hash(data/'plugins/qa-upgrade')==old_hash
    assert state(data)['plot']=='newer plot must stay'
    assert state(data)['_rule_state']=={'unchanged':True}
    assert state(data)['_plugins']['qa-upgrade']['data']=={'counter':2}
    with closing(sqlite3.connect(data/'tavern.sqlite3')) as con, con:
        assert con.execute('SELECT id FROM sessions').fetchall()==[('new-session',)]
        assert con.execute('SELECT id FROM members').fetchall()==[('current-player',)]
        assert con.execute('SELECT enabled FROM guest_invites').fetchone()[0]==0
    with closing(sqlite3.connect(data.parent/'module-upgrades'/('b'*32)/'before.sqlite3')) as con, con:
        saved=json.loads(con.execute('SELECT state_json FROM rooms').fetchone()[0]);assert saved['_plugins']['qa-upgrade']['data']['counter']==99
    assert len(history(data)['records'])==2


def test_failed_migration_keeps_original_code_database_trust_and_remains_recoverable(tmp_path):
    data,archive,sha=fixture(tmp_path,fail=True)
    database=(data/'tavern.sqlite3').read_bytes();trust=(data/'plugin-trust.json').read_bytes();old=package_hash(data/'plugins/qa-upgrade')
    with pytest.raises(ValueError):upgrade(data,archive,sha,'a'*32,True)
    assert (data/'tavern.sqlite3').read_bytes()==database
    assert (data/'plugin-trust.json').read_bytes()==trust
    assert package_hash(data/'plugins/qa-upgrade')==old
    recover(data)
    assert history(data)['records'][0]['state']=='recovered'
    assert (data/'plugin-trust.json').read_bytes()==trust


def test_preset_pins_block_mismatched_versions_without_modifying_locks(tmp_path):
    data,archive,sha=fixture(tmp_path)
    with closing(sqlite3.connect(data/'tavern.sqlite3')) as con, con:
        current=state(data);current['_preset_lock']={'plugins':[{'id':'qa-upgrade','version':'1.0.0','sha256':package_hash(data/'plugins/qa-upgrade')}]}
        con.execute('UPDATE rooms SET state_json=?',(json.dumps(current),))
    original=state(data)
    assert preview(data,archive,sha)['pinned_rooms']==1
    with pytest.raises(ModuleError,match='pinned_rooms_require_original'):upgrade(data,archive,sha,'a'*32,True)
    assert state(data)==original


def test_commit_interruption_recovers_all_managed_changes(tmp_path,monkeypatch):
    from scripts import plugin_versions as tool
    data,archive,sha=fixture(tmp_path)
    original=state(data);old=package_hash(data/'plugins/qa-upgrade');trust=(data/'plugin-trust.json').read_bytes()
    real=tool.write_json
    def fail_final(path,value):
        if path.name=='transaction.json' and value.get('state')=='committed':raise OSError('synthetic interrupted commit')
        return real(path,value)
    monkeypatch.setattr(tool,'write_json',fail_final)
    with pytest.raises(OSError):upgrade(data,archive,sha,'a'*32,True)
    assert state(data)==original
    assert package_hash(data/'plugins/qa-upgrade')==old
    assert json.loads((data/'plugin-trust.json').read_text())==json.loads(trust)
    assert history(data)['records'][0]['state']=='recovered'


def test_archive_and_checkpoint_identity_are_scoped_and_hash_bound(tmp_path):
    data,archive,sha=fixture(tmp_path)
    with pytest.raises(ModuleError,match='archive_changed'):preview(data,archive,'0'*64)
    with pytest.raises(ModuleError,match='invalid_checkpoint'):upgrade(data,archive,sha,'../outside',True)
    with pytest.raises(ModuleError,match='invalid_checkpoint'):rollback(data,'../outside','a'*32,True)


def test_hard_process_interruption_requires_compatible_recovery_before_start(tmp_path):
    data,archive,sha=fixture(tmp_path)
    original=state(data);old=package_hash(data/'plugins/qa-upgrade')
    script='''
import os,sys
from pathlib import Path
from scripts import plugin_versions as tool
real=tool.write_json
def interrupted(path,value):
    if path.name=='transaction.json' and value.get('state')=='code-swapped':os._exit(93)
    return real(path,value)
tool.write_json=interrupted
tool.upgrade(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],'a'*32,True)
'''
    process=subprocess.run([sys.executable,'-c',script,str(data),str(archive),sha],capture_output=True)
    assert process.returncode==93
    marker=json.loads((data.parent/'update-journal.json').read_text())
    assert marker['format']=='ember.module-barrier/v1'
    assert 'prior' not in marker  # Legacy recovery rejects before touching files.
    assert package_hash(data/'plugins/qa-upgrade')!=old
    recover(data)
    assert not (data.parent/'update-journal.json').exists()
    assert package_hash(data/'plugins/qa-upgrade')==old
    assert state(data)==original


def test_backup_supports_unicode_and_hash_directory_without_reading_another_database(tmp_path,monkeypatch):
    from scripts import backup as tool
    data,_,_=fixture(tmp_path)
    monkeypatch.setattr(tool.settings,'data_dir',data)
    output=tmp_path/'完整备份.zip'
    result=tool.backup(output,True)
    assert result['integrity_check']=='ok'
    with zipfile.ZipFile(output) as archive:
        assert 'tavern.sqlite3' in archive.namelist()


def test_installed_host_version_blocks_candidate_before_execution(tmp_path):
    marker=tmp_path/'executed';data,archive,sha=fixture(tmp_path,marker=marker)
    with pytest.raises(ModuleError,match='host_incompatible'):
        preview(data,archive,sha,host_version='0.0.1')
    with pytest.raises(ModuleError,match='host_incompatible'):
        upgrade(data,archive,sha,'a'*32,True,host_version='0.0.1')
    assert not marker.exists()
    assert not (data.parent/'module-upgrades').exists()


def test_external_write_during_migration_is_preserved_instead_of_overwritten(tmp_path,monkeypatch):
    from scripts import plugin_versions as tool
    data,archive,sha=fixture(tmp_path)
    old=package_hash(data/'plugins/qa-upgrade');real=tool.migrate
    def concurrent_write(*args,**kwargs):
        real(*args,**kwargs)
        with closing(sqlite3.connect(data/'tavern.sqlite3')) as con, con:
            changed=state(data);changed['plot']='external newer progress'
            con.execute('UPDATE rooms SET state_json=?',(json.dumps(changed),))
    monkeypatch.setattr(tool,'migrate',concurrent_write)
    with pytest.raises(ModuleError,match='source_changed'):
        upgrade(data,archive,sha,'a'*32,True)
    recover(data)
    assert state(data)['plot']=='external newer progress'
    assert state(data)['_plugins']['qa-upgrade']['schema_version']==1
    assert package_hash(data/'plugins/qa-upgrade')==old


@pytest.mark.parametrize('cycle',[False,True])
def test_missing_or_cyclic_dependencies_block_upgrade_without_execution(tmp_path,cycle):
    data,archive,_=fixture(tmp_path)
    source=tmp_path/'new-code';manifest=json.loads((source/'plugin.json').read_text())
    manifest['requires']=['qa-dependency'];(source/'plugin.json').write_text(json.dumps(manifest),encoding='utf-8')
    if cycle:
        dependency=data/'plugins/qa-dependency';dep=module(dependency)
        dep.update(id='qa-dependency',requires=['qa-upgrade']);(dependency/'plugin.json').write_text(json.dumps(dep),encoding='utf-8')
    with zipfile.ZipFile(archive,'w') as z:
        for path in source.iterdir():z.write(path,'qa-upgrade/'+path.name)
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    result=preview(data,archive,sha)
    assert not result['can_upgrade'] and result['dependency_issues']
    with pytest.raises(ModuleError,match='dependencies_unavailable'):
        upgrade(data,archive,sha,'a'*32,True)
    assert state(data)['_plugins']['qa-upgrade']['schema_version']==1


@pytest.mark.parametrize('stage',['data-swapped','committed'])
def test_hard_database_and_trust_interruption_recovers_and_is_idempotent(tmp_path,stage):
    data,archive,sha=fixture(tmp_path)
    original=state(data);old=package_hash(data/'plugins/qa-upgrade')
    trust=json.loads((data/'plugin-trust.json').read_text())
    script='''
import os,sys
from pathlib import Path
from scripts import plugin_versions as tool
real=tool.write_json
def interrupted(path,value):
    if path.name=='transaction.json' and value.get('state')==sys.argv[4]:os._exit(93)
    return real(path,value)
tool.write_json=interrupted
tool.upgrade(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],'a'*32,True)
'''
    process=subprocess.run([sys.executable,'-c',script,str(data),str(archive),sha,stage],capture_output=True)
    assert process.returncode==93
    recover(data);recover(data)
    assert state(data)==original
    assert package_hash(data/'plugins/qa-upgrade')==old
    assert json.loads((data/'plugin-trust.json').read_text())==trust
    assert not (data.parent/'update-journal.json').exists()


def test_recovery_resumes_sidecars_after_main_database_was_already_restored(tmp_path,monkeypatch):
    from scripts import plugin_versions as tool
    data,archive,sha=fixture(tmp_path);original=state(data);real=tool.write_json
    def interrupted(path,value):
        if path.name=='transaction.json' and value.get('state')=='committed':
            directory=path.parent
            # Simulate recovery already restoring main/code, before pending SHM.
            current=data/'plugins/qa-upgrade';current.rename(directory/'interrupted-code')
            (directory/'displaced-code').rename(current)
            (data/'tavern.sqlite3').rename(directory/'interrupted.sqlite3')
            (directory/'displaced.sqlite3').rename(data/'tavern.sqlite3')
            (directory/'displaced.sqlite3-shm').write_bytes(b'synthetic pending shared-memory')
            raise OSError('synthetic recovery interruption')
        return real(path,value)
    monkeypatch.setattr(tool,'write_json',interrupted)
    with pytest.raises(OSError):upgrade(data,archive,sha,'a'*32,True)
    assert (data/'tavern.sqlite3-shm').read_bytes()==b'synthetic pending shared-memory'
    assert not (data.parent/'module-upgrades'/('a'*32)/'displaced.sqlite3-shm').exists()
    assert state(data)==original
    recover(data)


def test_changed_recovery_database_blocks_before_moving_any_live_code(tmp_path,monkeypatch):
    from scripts import plugin_versions as tool
    data,archive,sha=fixture(tmp_path);real=tool.write_json
    def corrupt_backup(path,value):
        if path.name=='transaction.json' and value.get('state')=='data-swapped':
            (path.parent/'displaced.sqlite3').write_bytes(b'corrupt recovery database')
            raise OSError('synthetic interruption')
        return real(path,value)
    monkeypatch.setattr(tool,'write_json',corrupt_backup)
    with pytest.raises(ModuleError,match='recovery_blocked'):
        upgrade(data,archive,sha,'a'*32,True)
    changed_code=package_hash(data/'plugins/qa-upgrade')
    database=(data/'tavern.sqlite3').read_bytes()
    with pytest.raises(ModuleError,match='recovery_blocked'):recover(data)
    assert package_hash(data/'plugins/qa-upgrade')==changed_code
    assert (data/'tavern.sqlite3').read_bytes()==database
    assert (data.parent/'update-journal.json').exists()


def test_dependency_preview_uses_installed_app_instead_of_newer_desktop_builtins(tmp_path,monkeypatch):
    from scripts import plugin_versions as tool
    data,archive,_=fixture(tmp_path)
    desktop=tmp_path/'newer-desktop';dependency=desktop/'plugins/qa-dependency'
    manifest=module(dependency);manifest['id']='qa-dependency'
    (dependency/'plugin.json').write_text(json.dumps(manifest),encoding='utf-8')
    monkeypatch.setattr(tool,'ROOT',desktop)
    (data.parent/'app/plugins').mkdir(parents=True)
    source=tmp_path/'new-code';candidate=json.loads((source/'plugin.json').read_text());candidate['requires']=['qa-dependency']
    (source/'plugin.json').write_text(json.dumps(candidate),encoding='utf-8')
    with zipfile.ZipFile(archive,'w') as z:
        for path in source.iterdir():z.write(path,'qa-upgrade/'+path.name)
    result=preview(data,archive,hashlib.sha256(archive.read_bytes()).hexdigest())
    assert result['dependency_issues']==['qa-dependency'] and not result['can_upgrade']
