"""Synthetic publication fixtures; never claim external authors or real releases."""
import copy
import io
import json
from pathlib import Path
import zipfile

import httpx
import pytest

from scripts.creator import scaffold,lock_preset,package_preset
from scripts.plugins import package
from scripts.community import (prepare,load_submission,verify_release,review,stage_submission,maintenance,
                               encoded,digest,inspect_archive,PublicFetcher,public_url,ROOT)
from server.contracts.community import RegistrySubmission
from scripts.registry import validate_registry


@pytest.fixture(params=['plugin','preset'])
def submission(tmp_path,request):
    kind=request.param;source=tmp_path/'source';identity='synthetic-'+kind
    scaffold('plugin-backend' if kind=='plugin' else 'preset',source,identity)
    for path in source.rglob('*.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        metadata=data if kind=='plugin' and path.name=='plugin.json' else data.get('metadata')
        if metadata is not None:metadata.update(authors=['Synthetic automation fixture; not a community author'],license='MIT')
        path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    marker=tmp_path/'must-not-execute'
    if kind=='plugin':
        (source/'backend.py').write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('submitted code executed')\n",encoding='utf-8')
    else:lock_preset(source)
    archive=tmp_path/(kind+'.zip')
    if kind=='plugin':package(source,archive)
    else:package_preset(source,archive)
    folder=tmp_path/'submission'
    result=prepare(source,archive,folder,'https://github.com/synthetic-author/synthetic-work','a'*40,'b'*40,f'{kind}-{identity}-v1.0.0')
    assert result['network_access'] is False and not marker.exists()
    return folder,source,marker


def remote_feed(folder,mutate=None):
    s,checked,_=load_submission(folder);p=s.release
    urls={
        f'https://api.github.com/repos/synthetic-author/synthetic-work/releases/tags/{p.tag}':encoded({'id':100,'draft':False,'tag_name':p.tag,'assets':[
            {'id':201,'name':p.archive_name,'size':p.archive_bytes,'browser_download_url':s.entry.download_url,'digest':'sha256:'+p.archive_sha256},
            {'id':202,'name':'release-provenance.json','browser_download_url':s.provenance_url}]}),
        f'https://api.github.com/repos/synthetic-author/synthetic-work/commits/{p.tag}':encoded({'sha':p.source_commit}),
        f'https://api.github.com/repos/Tera-Dark/Ember-Tavern/commits/{p.sdk_commit}':encoded({'sha':p.sdk_commit}),
        s.entry.download_url:(folder/p.archive_name).read_bytes(),
        s.provenance_url:(folder/'release-provenance.json').read_bytes(),
    }
    if mutate:mutate(urls,s)
    calls=[]
    def fetch(url,limit):calls.append(url);return urls[url]
    return fetch,calls


def check_report(folder,path,mutate=None):
    fetch,calls=remote_feed(folder,mutate);report=verify_release(folder,fetch)
    path.write_bytes(encoded(report));return report


def test_prepare_and_online_verification_are_pinned_data_only(submission,tmp_path):
    folder,source,marker=submission;s,checked,_=load_submission(folder)
    fetch,calls=remote_feed(folder);report=verify_release(folder,fetch)
    assert report['online_verified'] and report['code_executed'] is False
    assert len(calls)==5 and not marker.exists()
    assert report['source_commit']=='a'*40 and report['sdk_commit']=='b'*40
    text=(folder/'SUBMISSION.md').read_text(encoding='utf-8')
    assert str(tmp_path) not in text
    entry=s.entry.model_dump()
    assert entry.get('status',entry.get('review_status'))=='community-submitted'


@pytest.mark.parametrize('fault',['tag','commit','sdk','archive','provenance','asset','size','digest','draft','missing-asset','duplicate-asset'])
def test_online_verification_rejects_mismatched_release_evidence(submission,fault):
    folder,_,marker=submission
    def corrupt(urls,s):
        if fault in ('tag','asset','size','digest','draft','missing-asset','duplicate-asset'):
            key=next(u for u in urls if '/releases/tags/' in u);data=json.loads(urls[key])
            if fault=='tag':data['tag_name']='plugin-unrelated-v9.0.0'
            if fault=='asset':data['assets'][0]['browser_download_url']='https://evil.example/archive.zip'
            if fault=='size':data['assets'][0]['size']+=1
            if fault=='digest':data['assets'][0]['digest']='sha256:'+'0'*64
            if fault=='draft':data['draft']=True
            if fault=='missing-asset':data['assets'].pop()
            if fault=='duplicate-asset':data['assets'].append(copy.deepcopy(data['assets'][0]))
            urls[key]=encoded(data)
        elif fault in ('commit','sdk'):
            key=next(u for u in urls if '/commits/' in u and ('Ember-Tavern' in u)==(fault=='sdk'));urls[key]=encoded({'sha':'c'*40})
        elif fault=='archive':urls[s.entry.download_url]+=b'changed'
        else:
            data=json.loads(urls[s.provenance_url]);data['source_commit']='c'*40;urls[s.provenance_url]=encoded(data)
    fetch,_=remote_feed(folder,corrupt)
    with pytest.raises(ValueError):verify_release(folder,fetch)
    assert not marker.exists()


def test_submission_cannot_self_promote_or_change_source_url(submission):
    folder,_,_=submission;data=json.loads((folder/'submission.json').read_text(encoding='utf-8'))
    status='review_status' if data['kind']=='plugin' else 'status'
    data['entry'][status]='official-recommended';data['entry']['evidence']=['https://github.com/synthetic-author/synthetic-work/issues/1']
    with pytest.raises(ValueError,match='只能申请'):RegistrySubmission.model_validate(data)
    data['entry'][status]='community-submitted';data['entry']['source_url']='https://github.com/synthetic-author/synthetic-work/tree/main'
    with pytest.raises(ValueError,match='精确提交'):RegistrySubmission.model_validate(data)


def test_approval_stages_valid_patch_and_preserves_original_catalog(submission,tmp_path):
    folder,_,marker=submission;index=ROOT/'registry/index.json';before=index.read_bytes()
    report=tmp_path/'verification.json';check_report(folder,report)
    record=review(folder,report,index,'Synthetic maintainer','Automated metadata test, not real community review')
    review_path=tmp_path/'review.json';review_path.write_bytes(encoded(record))
    output=tmp_path/'patch';result=stage_submission(folder,report,review_path,index,output)
    assert result['original_index_changed'] is False and index.read_bytes()==before
    staged=json.loads((output/'registry/index.json').read_text(encoding='utf-8'));original=json.loads(before)
    section='plugins' if record['kind']=='plugin' else 'preset_library'
    assert staged[section][:-1]==original[section]
    assert len(staged[section])==len(original[section])+1 and not marker.exists()
    assert (output/'registry/reviews'/f"{record['kind']}-{record['id']}-{record['version']}.json").exists()
    base=f"{record['kind']}-{record['id']}-{record['version']}"
    assert (output/'registry/reviews'/f'{base}.submission.json').read_bytes()==(folder/'submission.json').read_bytes()
    assert (output/'registry/reviews'/f'{base}.provenance.json').read_bytes()==(folder/'release-provenance.json').read_bytes()


def test_staging_refuses_stale_review_and_changed_archive(submission,tmp_path):
    folder,_,_=submission;index=ROOT/'registry/index.json';report=tmp_path/'report.json';check_report(folder,report)
    record=review(folder,report,index,'Synthetic maintainer','Synthetic decision')
    record['expected_index_sha256']='0'*64;path=tmp_path/'review.json';path.write_bytes(encoded(record))
    with pytest.raises(ValueError,match='过期'):stage_submission(folder,report,path,index,tmp_path/'stale')
    assert not (tmp_path/'stale').exists()
    s,_,_=load_submission(folder);(folder/s.release.archive_name).write_bytes(b'not a package')
    rejected=review(folder,'-',index,'Synthetic maintainer','Archive failed verification','needs-changes')
    assert rejected['decision']=='needs-changes' and rejected['verification_sha256'] is None


def test_maintenance_is_version_scoped_preserves_hashes_and_rejects_stale_index(tmp_path):
    index=ROOT/'registry/index.json';raw=index.read_bytes();original=json.loads(raw)
    item=original['plugins'][0];output=tmp_path/'maintenance'
    maintenance(index,output,'plugin',item['id'],item['version'],digest(raw),'Synthetic maintainer','Synthetic archive test','archive')
    changed=json.loads((output/'registry/index.json').read_text())
    assert changed['plugins'][0]['review_status']=='archived' and changed['plugins'][0]['download_url'] is None
    for key in ('id','version','package','sha256','template_path'):assert changed['plugins'][0][key]==item[key]
    assert changed['preset_library']==original['preset_library'] and index.read_bytes()==raw
    with pytest.raises(ValueError,match='过期'):maintenance(index,tmp_path/'bad','plugin',item['id'],item['version'],'0'*64,'Synthetic','Stale','archive')


@pytest.mark.parametrize('url',['http://github.com/owner/repo','https://localhost/data','https://127.0.0.1/data','https://github.com.evil.test/data','https://token@github.com/data','https://github.com:443/data'])
def test_network_verifier_rejects_private_foreign_or_credential_urls(url):
    with pytest.raises(ValueError):public_url(url)


def test_public_fetcher_checks_redirects_bounds_and_sends_no_credentials(monkeypatch):
    real_client=httpx.Client;calls=[]
    def handler(request):
        calls.append(request)
        assert 'authorization' not in request.headers and 'x-ember-session' not in request.headers
        return httpx.Response(302,headers={'location':'https://localhost/private'})
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return real_client(transport=httpx.MockTransport(handler),**kwargs)
    monkeypatch.setattr(httpx,'Client',client)
    with pytest.raises(ValueError,match='GitHub'):PublicFetcher()('https://github.com/synthetic/repo/releases/download/v/test.zip',100)
    assert len(calls)==1


def test_plugin_archive_rejects_traversal_without_extracting(tmp_path):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('../outside','bad')
    with pytest.raises(ValueError,match='不安全'):inspect_archive(buffer.getvalue(),'plugin')
    assert not (tmp_path/'outside').exists()


@pytest.mark.parametrize('advertised',['1000',None])
def test_public_fetcher_enforces_advertised_and_streamed_size_limits(monkeypatch,advertised):
    real_client=httpx.Client
    def handler(request):
        response=httpx.Response(200,content=b'x'*1000)
        if advertised is None:response.headers.pop('content-length',None)
        else:response.headers['content-length']=advertised
        return response
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    with pytest.raises(ValueError,match='大小上限'):PublicFetcher()('https://github.com/synthetic/repo/releases/download/v/test.zip',100)


def test_review_refuses_report_for_a_different_submission(submission,tmp_path):
    folder,_,_=submission;report=tmp_path/'report.json';data=check_report(folder,report)
    data['source_commit']='c'*40;report.write_bytes(encoded(data))
    with pytest.raises(ValueError,match='绑定'):review(folder,report,ROOT/'registry/index.json','Synthetic maintainer','Synthetic decision')
