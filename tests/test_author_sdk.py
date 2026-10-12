"""M4 author tools: detached archive usage and publication declarations.

These are synthetic authors / packages, not independent community acceptance.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest

from scripts.author_sdk import build,verify,ROOT,EXPLICIT
from scripts.creator import release_check,scaffold,lock_preset


@pytest.fixture
def sdk_archive(tmp_path):
    path=tmp_path/'sdk.zip';result=build(path)
    assert type(result['source_dirty']) is bool
    return path,result


def rewrite_archive(path,transform):
    with zipfile.ZipFile(path) as archive:
        files={info.filename:(copy.copy(info),archive.read(info)) for info in archive.infolist()}
    transform(files)
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for info,raw in files.values():archive.writestr(info,raw)
    path.write_bytes(buffer.getvalue())


def test_sdk_reproducible_with_hashes_and_no_private_or_host_binaries(tmp_path):
    a,b=tmp_path/'first.zip',tmp_path/'second.zip'
    first=build(a);second=build(b)
    assert a.read_bytes()==b.read_bytes()
    assert first['sha256']==second['sha256']==hashlib.sha256(a.read_bytes()).hexdigest()
    assert Path(str(a)+'.sha256').read_text().strip()==first['sha256']+'  '+a.name
    result=verify(a,first['sha256']);assert result['valid'] and not result['code_executed']
    with zipfile.ZipFile(a) as archive:
        paths=[name.split('/',1)[1] for name in archive.namelist()]
    assert 'README.md' in paths and 'ember-creator.py' in paths
    assert not any(part.startswith('.') for name in paths for part in name.split('/'))
    assert not any(name.startswith(('desktop/','web/','static/','launcher/','data/')) for name in paths)
    assert not any(name.endswith(('.env','.exe','.sqlite3','.private.json')) for name in paths)


def test_sdk_refuses_overwrite_and_public_mode_without_clean_rights(sdk_archive,tmp_path):
    archive,_=sdk_archive
    before=archive.read_bytes()
    with pytest.raises(ValueError,match='不会覆盖'):build(archive)
    assert archive.read_bytes()==before
    with pytest.raises(ValueError,match='干净提交|LICENSE'):build(tmp_path/'public.zip',release=True)
    assert not (tmp_path/'public.zip').exists()


@pytest.mark.parametrize('corruption',['changed-file','extra-file','symlink','traversal','manifest-version','false-publication'])
def test_sdk_verifier_rejects_corruption_without_extraction(sdk_archive,corruption):
    path,_=sdk_archive
    def corrupt(files):
        prefix=next(iter(files)).split('/')[0]
        if corruption=='changed-file':
            info,raw=files[prefix+'/scripts/creator.py'];files[info.filename]=(info,raw+b'\n# tamper')
        elif corruption=='extra-file':
            info=zipfile.ZipInfo(prefix+'/unexpected.py');files[info.filename]=(info,b"raise RuntimeError('must never execute')")
        elif corruption=='symlink':
            info,raw=files[prefix+'/README.md'];info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        elif corruption=='traversal':
            info=zipfile.ZipInfo(prefix+'/../escape');files[info.filename]=(info,b'bad')
        else:
            info,raw=files[prefix+'/sdk-manifest.json'];metadata=json.loads(raw)
            if corruption=='manifest-version':metadata['version']='9.0.0'
            else:metadata['publication_ready']=True
            files[info.filename]=(info,json.dumps(metadata).encode())
    rewrite_archive(path,corrupt)
    with pytest.raises(ValueError):verify(path)


def test_sdk_hash_mismatch_and_duplicate_archive_paths(sdk_archive):
    path,_=sdk_archive
    with pytest.raises(ValueError,match='SHA256'):verify(path,'0'*64)
    with zipfile.ZipFile(path,'a') as archive:
        name=archive.namelist()[0];archive.writestr(name.upper(),b'duplicate casefold')
    with pytest.raises(ValueError,match='重复'):verify(path)


def test_sdk_runs_detached_from_checkout_and_never_executes_plugin_code(sdk_archive,tmp_path):
    archive,result=sdk_archive;verify(archive,result['sha256'])
    detached=tmp_path/'detached';detached.mkdir()
    with zipfile.ZipFile(archive) as bundle:bundle.extractall(detached)
    sdk=next(detached.iterdir());cwd=tmp_path/'author-repository';cwd.mkdir()
    env={**os.environ,'PYTHONPATH':'','PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','DATA_DIR':str(tmp_path/'isolated-data')}
    def cli(entry,*args):
        result=subprocess.run([sys.executable,str(sdk/entry),*map(str,args)],cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
        assert result.returncode==0,result.stderr
        return result.stdout
    cli('ember-creator.py','schemas','--check')
    preset=cwd/'my-game';cli('ember-creator.py','init','preset',preset,'--id','fixture-game')
    cli('ember-creator.py','validate',preset)
    plugin=cwd/'my-notes';cli('ember-creator.py','init','plugin-backend',plugin,'--id','fixture-notes')
    sentinel=cwd/'backend-executed'
    (plugin/'backend.py').write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('unexpected')\nraise RuntimeError('must not execute')\n",encoding='utf-8')
    cli('ember-creator.py','validate',plugin)
    cli('ember-plugins.py','package',plugin,cwd/'plugin.zip')
    cli('ember-creator.py','package-preset',preset,cwd/'preset.zip')
    manifest=plugin/'plugin.json';data=json.loads(manifest.read_text(encoding='utf-8'))
    data.update(authors=['Synthetic automation fixture'],license='MIT');manifest.write_text(json.dumps(data),encoding='utf-8')
    cli('ember-plugins.py','package',plugin,cwd/'submission-plugin.zip')
    result=json.loads(cli('ember-community.py','prepare',plugin,cwd/'submission-plugin.zip',cwd/'submission',
                          '--repository','https://github.com/synthetic-author/synthetic-work',
                          '--source-commit','a'*40,'--sdk-commit','b'*40,'--tag','plugin-fixture-notes-v1.0.0'))
    assert result['network_access'] is False
    assert (cwd/'submission/submission.json').is_file()
    assert not sentinel.exists() and not (tmp_path/'isolated-data').exists()


def test_preset_publication_requires_each_component_and_exact_tag(tmp_path):
    folder=tmp_path/'preset';scaffold('preset',folder,'fixture-game')
    with pytest.raises(ValueError,match='署名|许可'):release_check(folder)
    for file in folder.rglob('*.json'):
        document=json.loads(file.read_text(encoding='utf-8'))
        if 'metadata' in document:
            document['metadata']['authors']=['Automated fixture; not a community author']
            document['metadata']['license']='MIT'
            file.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
    lock_preset(folder)
    assert release_check(folder,tag='preset-fixture-game-v1.0.0')['publication_ready']
    with pytest.raises(ValueError,match='标签'):release_check(folder,tag='preset-fixture-game-v2.0.0')
    character=next((folder/'characters').glob('*.json'));document=json.loads(character.read_text(encoding='utf-8'))
    document['metadata']['license']='UNLICENSED';character.write_text(json.dumps(document),encoding='utf-8');lock_preset(folder)
    with pytest.raises(ValueError,match='角色'):release_check(folder)


def test_plugin_publication_is_data_only_and_does_not_import_runtime(tmp_path):
    folder=tmp_path/'plugin';scaffold('plugin-backend',folder,'fixture-notes')
    manifest=json.loads((folder/'plugin.json').read_text(encoding='utf-8'));manifest.update(authors=['Automated fixture'],license='MIT')
    (folder/'plugin.json').write_text(json.dumps(manifest),encoding='utf-8')
    (folder/'backend.py').write_text("raise RuntimeError('submitted code executed')",encoding='utf-8')
    result=release_check(folder,tag='plugin-fixture-notes-v1.0.0')
    assert result['publication_ready'] and result['code_executed'] is False
    process=subprocess.run([sys.executable,'-c',"import scripts.plugins,sys; assert 'server.plugin_runtime.manager' not in sys.modules"],cwd=ROOT,capture_output=True,text=True)
    assert process.returncode==0,process.stderr


def source_fixture(tmp_path):
    root=tmp_path/'source';root.mkdir()
    for name in (*EXPLICIT,'server/version.py'):
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    def git(*args):
        result=subprocess.run(['git','-C',str(root),'-c','user.name=Automated fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false',*args],capture_output=True)
        assert result.returncode==0,result.stderr
    git('init');git('add','.');git('commit','-m','Synthetic SDK source fixture')
    return root,git


def test_sdk_ignores_untracked_credentials_even_inside_source_subtrees(tmp_path):
    root,_=source_fixture(tmp_path)
    for name in ('.env','api-test-profiles.private.json','server/untracked.py'):
        (root/name).write_text('synthetic-private-sentinel; no real credentials',encoding='utf-8')
    path=tmp_path/'private-excluded.zip';build(path,root=root)
    with zipfile.ZipFile(path) as archive:
        assert not any('untracked' in name or '.private.json' in name or name.endswith('/.env') for name in archive.namelist())
        assert not any(b'synthetic-private-sentinel' in archive.read(info) for info in archive.infolist())


def test_sdk_release_requires_clean_commit_and_explicit_nonempty_rights(tmp_path):
    root,git=source_fixture(tmp_path)
    with pytest.raises(ValueError,match='LICENSE'):build(tmp_path/'missing-rights.zip',root=root,release=True)
    (root/'LICENSE').write_text('Synthetic fixture license, not project authorization',encoding='utf-8')
    (root/'AUTHOR_SDK_LICENSE.md').write_text('Synthetic fixture scope for tests only',encoding='utf-8')
    git('add','.');git('commit','-m','Synthetic rights declarations for test only')
    result=build(tmp_path/'fixture-public.zip',root=root,release=True)
    assert not result['source_dirty'] and result['publication_ready']
    assert verify(tmp_path/'fixture-public.zip',result['sha256'])['publication_ready']
    (root/'AUTHOR_SDK_LICENSE.md').write_text('',encoding='utf-8');git('add','.');git('commit','-m','Empty fixture rights')
    with pytest.raises(ValueError,match='LICENSE'):build(tmp_path/'empty-rights.zip',root=root,release=True)
