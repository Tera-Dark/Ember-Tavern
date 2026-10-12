#!/usr/bin/env python3
"""M4 submission / release evidence tooling. No installs or submitted-code execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from urllib.parse import urlsplit
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.config import ROOT
from server.contracts.community import CommunityRelease, RegistrySubmission, RegistryReview,release_url
from server.contracts.registry import RegistryIndex,PluginRegistryEntry,PresetRegistryEntry
from server.contracts.plugin import validate_manifest
from server.presets.codec import parse_archive
from scripts.creator import release_check
from scripts.registry import validate_registry,_strict_json,_safe_file

MAX_ARCHIVE=8*1024*1024
MAX_JSON=2*1024*1024
MAX_EXPANDED=32*1024*1024


def digest(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def linked(path):return path.is_symlink() or getattr(path,'is_junction',lambda:False)()


def read(path,limit=MAX_JSON):
    path=Path(path)
    if linked(path) or not path.is_file() or path.stat().st_size>limit:raise ValueError('输入必须是有界普通文件')
    return path.read_bytes()


def write_new(path,raw):
    path=Path(path)
    if path.exists() or linked(path):raise ValueError('输出已存在；不会覆盖')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as file:file.write(raw)


def member_path(value):
    parts=value.split('/')
    if (not value or len(value)>180 or '\\' in value or any(p in ('','.','..') or p.startswith('.')
            or ':' in p or p.endswith((' ','.')) or p.split('.')[0].upper() in
            {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for p in parts)):
        raise ValueError('归档包含不安全 / 不可移植路径')
    return value


def inspect_archive(raw,kind):
    if not raw or len(raw)>MAX_ARCHIVE:raise ValueError('作品归档超过 8 MiB 或为空')
    if kind=='preset':
        package=parse_archive(raw)
        return {'manifest':package.manifest,'files':{name:value.encode('utf-8') for name,value in package.files.items()},'package_hash':package.package_hash}
    if kind!='plugin':raise ValueError('仅支持插件或预设发行')
    files={};total=0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos=archive.infolist()
        if not infos or len(infos)>128:raise ValueError('插件归档文件数量无效')
        names=[member_path(info.filename) for info in infos]
        if len(set(name.casefold() for name in names))!=len(names):raise ValueError('插件归档含重复 / 大小写冲突路径')
        for info,name in zip(infos,names):
            mode=(info.external_attr>>16)&0o170000
            if info.is_dir() or mode not in (0,stat.S_IFREG) or info.flag_bits&1 or info.file_size>MAX_ARCHIVE:
                raise ValueError('插件归档只能含有界未加密普通文件')
            data=archive.read(info);total+=len(data)
            if len(data)!=info.file_size or total>MAX_EXPANDED:raise ValueError('插件解压大小无效')
            files[name]=data
    manifests=[name for name in files if name=='plugin.json' or name.endswith('/plugin.json')]
    if len(manifests)!=1:raise ValueError('插件归档必须只有一个 plugin.json')
    prefix=manifests[0][:-len('plugin.json')]
    if any(not name.startswith(prefix) for name in files):raise ValueError('插件归档包含模块根目录之外的文件')
    files={member_path(name[len(prefix):]):raw for name,raw in files.items()}
    if len(files['plugin.json'])>64*1024:raise ValueError('插件清单超过上限')
    manifest=validate_manifest(_strict_json(files['plugin.json']))
    for name in (manifest.get('backend'),manifest.get('frontend')):
        if name and name not in files:raise ValueError('插件归档缺少声明入口')
    h=hashlib.sha256()
    for name,data in sorted(files.items()):h.update(name.encode()+b'\0'+data+b'\0')
    return {'manifest':manifest,'files':files,'package_hash':h.hexdigest()}


def check_rights(checked,kind):
    # Native typed contracts already checked shape / bounds.
    m=checked['manifest'];documents=[m] if kind=='plugin' else [_strict_json(raw) for name,raw in checked['files'].items() if name.endswith('.json')]
    for doc in documents:
        metadata=doc if kind=='plugin' else doc.get('metadata',{})
        if not metadata.get('authors') or str(metadata.get('license','')).strip().upper() in ('','UNLICENSED','UNSPECIFIED','NONE'):
            raise ValueError('发行及所有组件必须声明作者和明确许可')


def provenance(source,archive,repository,source_commit,sdk_commit,tag):
    result=release_check(source,tag=tag)
    raw=read(archive,MAX_ARCHIVE);checked=inspect_archive(raw,result['kind']);check_rights(checked,result['kind'])
    source_hash=result['package_hash'] if result['kind']=='preset' else None
    if result['kind']=='plugin':
        # Compare the published file footprint byte-for-byte. Runtime trust
        # digests retain their existing algorithm; this canonical archive
        # fingerprint is not an installation / capability grant.
        folder=Path(source) if Path(source).is_dir() else Path(source).parent
        source_files={}
        for path in folder.rglob('*'):
            parts=path.relative_to(folder).parts
            if any(part.startswith('.') or part in ('__pycache__','node_modules') for part in parts) or path.suffix=='.pyc':continue
            if linked(path):raise ValueError('源码包含链接')
            if path.is_file():source_files[member_path(path.relative_to(folder).as_posix())]=read(path,MAX_ARCHIVE)
        if source_files!=checked['files']:raise ValueError('归档文件与已检查源码不一致')
        source_hash=checked['package_hash']
    if source_hash!=checked['package_hash']:raise ValueError('归档内容与已检查源码不一致；请从同一份源码重新打包')
    proof=CommunityRelease(kind=result['kind'],id=result['id'],version=result['version'],repository=repository,
                           source_commit=source_commit,sdk_commit=sdk_commit,tag=result['expected_tag'],
                           archive_name=Path(archive).name,archive_sha256=digest(raw),archive_bytes=len(raw),package_hash=checked['package_hash'])
    return proof.model_dump(mode='json')


def entry_from(proof,checked,issue_url=None):
    common={'id':proof.id,'version':proof.version,'source_url':f'{proof.repository}/tree/{proof.source_commit}',
            'download_url':release_url(proof.repository,proof.tag,proof.archive_name),'maintenance_status':'active','issue_url':issue_url,'evidence':[]}
    m=checked['manifest']
    if proof.kind=='plugin':
        names=('name','description','category','minimum_host','api_version','capabilities','requires','uses','provides','license','authors')
        result={**common,**{name:m[name] for name in names},'backend':bool(m.get('backend')),'review_status':'community-submitted',
                'package':f'{proof.id}-{proof.version}.zip','sha256':proof.archive_sha256,'template_path':f'templates/community/{proof.id}/{proof.version}'}
        return PluginRegistryEntry.model_validate(result)
    metadata=m['metadata'];names=('rule_system','rule_version','minimum_host','plugin_api','language','play_mode','min_players','max_players','duration_minutes','difficulty','content_warnings','plugins')
    result={**common,**{name:metadata[name] for name in ('name','description','tags','license','authors')},**{name:m[name] for name in names},
            'package_hash':proof.package_hash,'archive_sha256':proof.archive_sha256,'status':'community-submitted','source_path':f'presets/community/{proof.id}/{proof.version}'}
    return PresetRegistryEntry.model_validate(result)


def prepare(source,archive,output,repository,source_commit,sdk_commit,tag,issue_url=None):
    output=Path(output)
    if output.exists() or linked(output):raise ValueError('投稿输出目录必须不存在')
    proof=CommunityRelease.model_validate(provenance(source,archive,repository,source_commit,sdk_commit,tag))
    raw=read(archive,MAX_ARCHIVE);checked=inspect_archive(raw,proof.kind)
    submission=RegistrySubmission(kind=proof.kind,entry=entry_from(proof,checked,issue_url),release=proof,
                                   provenance_url=release_url(proof.repository,proof.tag,'release-provenance.json'))
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.community-',dir=output.parent) as temp:
        stage=Path(temp)/'submission';stage.mkdir()
        write_new(stage/'submission.json',encoded(submission.model_dump(mode='json')))
        write_new(stage/'release-provenance.json',encoded(proof.model_dump(mode='json')))
        write_new(stage/proof.archive_name,raw)
        text=f"# 目录投稿：{proof.id}@{proof.version}\n\n类型：{proof.kind}\n\n源码：{submission.entry.source_url}\n\n下载：{submission.entry.download_url}\n\n归档 SHA256：{proof.archive_sha256}\n\n本地检查不代表线上核验、版权认证或试玩通过。维护者先运行 verify-release，再审阅投稿和独立测试范围。\n"
        write_new(stage/'SUBMISSION.md',text.encode('utf-8'));stage.rename(output)
    return {'created':str(output),'submission_sha256':digest(read(output/'submission.json')),'status':'community-submitted','code_executed':False,'network_access':False}


def load_submission(folder):
    folder=Path(folder)
    if linked(folder):raise ValueError('投稿目录不能是链接')
    raw=read(folder/'submission.json');submission=RegistrySubmission.model_validate(_strict_json(raw))
    archive=read(folder/submission.release.archive_name,MAX_ARCHIVE)
    checked=inspect_archive(archive,submission.kind);check_rights(checked,submission.kind)
    p=submission.release
    if digest(archive)!=p.archive_sha256 or len(archive)!=p.archive_bytes or checked['package_hash']!=p.package_hash:raise ValueError('本地投稿归档与锁定发行不符')
    expected=entry_from(p,checked,submission.entry.issue_url)
    if expected.model_dump()!=submission.entry.model_dump():raise ValueError('投稿摘要与实际归档不符')
    proof=CommunityRelease.model_validate(_strict_json(read(folder/'release-provenance.json')))
    if proof!=p:raise ValueError('本地来源声明与投稿不一致')
    return submission,checked,digest(raw)


def public_url(value):
    u=urlsplit(value)
    if u.scheme!='https' or u.username or u.password or u.port or u.hostname not in ('api.github.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'):
        raise ValueError('发行核验只访问 GitHub 及其 HTTPS 资产域名')
    return value


class PublicFetcher:
    def __call__(self,url,limit):
        import httpx
        # No env proxy, Authorization, provider keys, cookies, or host sessions.
        with httpx.Client(timeout=30,follow_redirects=False,trust_env=False,headers={'User-Agent':'Ember-Community-Verifier','Accept':'application/vnd.github+json'}) as client:
            for hop in range(6):
                public_url(url)
                with client.stream('GET',url) as response:
                    if response.status_code in (301,302,303,307,308):
                        from urllib.parse import urljoin
                        location=response.headers.get('location')
                        if not location or hop==5:raise ValueError('发行下载重定向无效')
                        url=public_url(urljoin(url,location));continue
                    if response.status_code!=200:raise ValueError(f'GitHub 发行请求失败（HTTP {response.status_code}）；保留原目录，可稍后重试')
                    if int(response.headers.get('content-length','0'))>limit:raise ValueError('远程发行内容超过大小上限')
                    raw=bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw)>limit:raise ValueError('远程发行内容超过大小上限')
                    return bytes(raw)
        raise ValueError('发行下载未完成')


def verify_release(folder,fetcher=None):
    submission,local,submission_hash=load_submission(folder);p=submission.release
    fetcher=fetcher or PublicFetcher()
    def fetch(url,limit):
        public_url(url);raw=fetcher(url,limit)
        if not isinstance(raw,bytes) or len(raw)>limit:raise ValueError('远程响应无效或过大')
        return raw
    repository=p.repository.removeprefix('https://github.com/')
    api=f'https://api.github.com/repos/{repository}'
    release=_strict_json(fetch(f'{api}/releases/tags/{p.tag}',MAX_JSON))
    commit=_strict_json(fetch(f'{api}/commits/{p.tag}',MAX_JSON))
    if release.get('draft') or release.get('tag_name')!=p.tag or commit.get('sha')!=p.source_commit:raise ValueError('GitHub 发行 tag / 提交与投稿不一致')
    if type(release.get('id')) is not int or release['id']<=0:raise ValueError('GitHub 发行身份无效')
    sdk=_strict_json(fetch(f'https://api.github.com/repos/Tera-Dark/Ember-Tavern/commits/{p.sdk_commit}',MAX_JSON))
    if sdk.get('sha')!=p.sdk_commit:raise ValueError('来源声明引用的 SDK 提交不存在或不符')
    assets=release.get('assets',[])
    if not isinstance(assets,list):raise ValueError('GitHub 资产列表无效')
    def asset(name,url,size=None):
        matches=[a for a in assets if isinstance(a,dict) and a.get('name')==name]
        if len(matches)!=1 or matches[0].get('browser_download_url')!=url:raise ValueError('GitHub 发行缺少对应唯一资产或地址不符')
        item=matches[0]
        if type(item.get('id')) is not int or item['id']<=0:raise ValueError('GitHub 资产身份无效')
        if size is not None and item.get('size')!=size:raise ValueError('GitHub 归档大小声明不符')
        return item
    binary=asset(p.archive_name,submission.entry.download_url,p.archive_bytes)
    asset('release-provenance.json',submission.provenance_url)
    remote=fetch(submission.entry.download_url,MAX_ARCHIVE)
    checked=inspect_archive(remote,p.kind);check_rights(checked,p.kind)
    if digest(remote)!=p.archive_sha256 or len(remote)!=p.archive_bytes or checked['package_hash']!=p.package_hash:raise ValueError('远程归档散列 / 内容锁不符')
    remote_proof=CommunityRelease.model_validate(_strict_json(fetch(submission.provenance_url,MAX_JSON)))
    if remote_proof!=p:raise ValueError('远程来源声明与投稿不符')
    advertised=binary.get('digest')
    if advertised is not None and advertised!='sha256:'+p.archive_sha256:raise ValueError('GitHub 资产摘要与实际归档不符')
    return {'format':'ember.release-verification/v1','kind':p.kind,'id':p.id,'version':p.version,'verified_at':now(),
            'submission_sha256':submission_hash,'archive_sha256':p.archive_sha256,'package_hash':p.package_hash,
            'repository':p.repository,'source_commit':p.source_commit,'sdk_commit':p.sdk_commit,'tag':p.tag,
            'release_id':release.get('id'),'asset_id':binary['id'],'online_verified':True,'code_executed':False,
            'scope':'metadata-and-release-only','notice':'核验公开发行记录、归档字节和来源声明；不认证权属、作者身份、代码安全或实际试玩。'}


def review(folder,verification,index,reviewer,reason,decision='approve-catalog-entry'):
    if decision not in ('approve-catalog-entry','reject','needs-changes'):raise ValueError('投稿审核不能自动授予试玩 / 官方推荐等级')
    if decision!='approve-catalog-entry':
        raw=read(Path(folder)/'submission.json');submitted=_strict_json(raw);p=submitted.get('release',{})
        # Rejection can be recorded even when the archive / online checks fail.
        return RegistryReview(kind=submitted.get('kind'),id=p.get('id'),version=p.get('version'),decision=decision,
                              reviewer=reviewer,reason=reason,reviewed_at=now(),input_sha256=digest(raw),
                              verification_sha256=None if verification=='-' else digest(read(verification)),
                              expected_index_sha256=digest(read(index))).model_dump(mode='json')
    submission,checked,submission_hash=load_submission(folder)
    report_raw=read(verification);report=_strict_json(report_raw);p=submission.release
    if (report.get('format')!='ember.release-verification/v1' or report.get('online_verified') is not True
            or report.get('code_executed') is not False or report.get('scope')!='metadata-and-release-only'
            or report.get('submission_sha256')!=submission_hash or report.get('archive_sha256')!=p.archive_sha256
            or report.get('source_commit')!=p.source_commit or report.get('package_hash')!=p.package_hash
            or report.get('sdk_commit')!=p.sdk_commit or report.get('repository')!=p.repository or report.get('tag')!=p.tag
            or type(report.get('asset_id')) is not int or report['asset_id']<=0
            or type(report.get('release_id')) is not int or report['release_id']<=0
            or (report.get('kind'),report.get('id'),report.get('version'))!=(p.kind,p.id,p.version)):
        raise ValueError('审核需要绑定这份投稿的独立线上核验记录')
    return RegistryReview(kind=p.kind,id=p.id,version=p.version,decision=decision,reviewer=reviewer,reason=reason,
                          reviewed_at=now(),input_sha256=submission_hash,verification_sha256=digest(report_raw),
                          expected_index_sha256=digest(read(index))).model_dump(mode='json')


def copy_checked_tree(source,target):
    total=0
    for path in sorted(source.rglob('*')):
        if linked(path):raise ValueError('目录参考源码包含链接')
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        if path.is_file():
            raw=read(path,MAX_ARCHIVE);total+=len(raw)
            if total>MAX_EXPANDED:raise ValueError('目录参考源码超过大小限制')
            write_new(target/path.relative_to(source),raw)


def stage_submission(folder,verification,review_path,index,output,root=ROOT):
    root=Path(root).resolve();index=Path(index);output=Path(output)
    if output.exists() or linked(output):raise ValueError('暂存输出目录必须不存在；不会写当前索引')
    submission,checked,submission_hash=load_submission(folder);p=submission.release
    record=RegistryReview.model_validate(_strict_json(read(review_path)))
    # Re-evaluate the report binding instead of trusting a submitted review blob.
    expected=review(folder,verification,index,record.reviewer,record.reason,record.decision)
    for key in ('kind','id','version','decision','input_sha256','verification_sha256','expected_index_sha256'):
        if record.model_dump()[key]!=expected[key]:raise ValueError('审核记录已过期或与当前索引 / 投稿不符')
    if record.decision!='approve-catalog-entry':raise ValueError('仅明确通过的目录投稿可生成暂存补丁')
    validate_registry(index,root=root)
    raw=read(index);catalog=_strict_json(raw);section='plugins' if p.kind=='plugin' else 'preset_library'
    if any((e['id'],e['version'])==(p.id,p.version) for e in catalog[section]):raise ValueError('目录身份 / 版本已存在；不能覆盖既有作品锁')
    catalog[section].append(submission.entry.model_dump(mode='json'));RegistryIndex.model_validate(catalog)
    target=submission.entry.template_path if p.kind=='plugin' else submission.entry.source_path
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.registry-stage-',dir=output.parent) as temp:
        temp=Path(temp);check_root=temp/'check';patch=temp/'patch';check_root.mkdir();patch.mkdir()
        original=RegistryIndex.model_validate(_strict_json(raw))
        for entry in original.plugins:
            copy_checked_tree(_safe_file(root,entry.template_path,directory=True),check_root/entry.template_path)
            if entry.package:
                relative='plugin-packages/'+entry.package
                if not (check_root/relative).exists():write_new(check_root/relative,read(_safe_file(root,relative),MAX_ARCHIVE))
        for entry in original.preset_library:copy_checked_tree(_safe_file(root,entry.source_path,directory=True),check_root/entry.source_path)
        for entry in [*original.content_templates,*original.gameplay_templates,*original.core_schemas]:
            for key in ('schema_path','template_path'):
                relative=getattr(entry,key,None)
                if relative and not (check_root/relative).exists():write_new(check_root/relative,read(_safe_file(root,relative)))
        for name,body in checked['files'].items():
            member_path(name)
            write_new(check_root/target/name,body);write_new(patch/target/name,body)
        if p.kind=='plugin':
            relative='plugin-packages/'+submission.entry.package
            archive=read(Path(folder)/p.archive_name,MAX_ARCHIVE)
            write_new(check_root/relative,archive);write_new(patch/relative,archive)
        new_index=encoded(catalog)
        write_new(check_root/'registry/index.json',new_index);validate_registry(check_root/'registry/index.json',root=check_root)
        record.resulting_index_sha256=digest(new_index)
        write_new(patch/'registry/index.json',new_index)
        write_new(patch/'registry/reviews'/f'{p.kind}-{p.id}-{p.version}.json',encoded(record.model_dump(mode='json')))
        write_new(patch/'registry/reviews'/f'{p.kind}-{p.id}-{p.version}.verification.json',read(verification))
        # Retain exact reviewed inputs for auditing after public assets disappear.
        write_new(patch/'registry/reviews'/f'{p.kind}-{p.id}-{p.version}.submission.json',read(Path(folder)/'submission.json'))
        write_new(patch/'registry/reviews'/f'{p.kind}-{p.id}-{p.version}.provenance.json',read(Path(folder)/'release-provenance.json'))
        patch.rename(output)
    return {'staged':str(output),'expected_index_sha256':digest(raw),'resulting_index_sha256':digest(new_index),'original_index_changed':False,'code_executed':False,'network_access':False}


def maintenance(index,output,kind,identity,version,expected_hash,reviewer,reason,decision,root=ROOT):
    if decision not in ('archive','maintenance-needed','incompatible'):raise ValueError('维护操作只允许归档、标记维护或不兼容')
    validate_registry(index,root=root);raw=read(index)
    if digest(raw)!=expected_hash:raise ValueError('目录已变化，拒绝过期维护操作')
    catalog=_strict_json(raw);section='plugins' if kind=='plugin' else 'preset_library' if kind=='preset' else None
    if not section:raise ValueError('作品类型无效')
    matches=[e for e in catalog[section] if (e['id'],e['version'])==(identity,version)]
    if len(matches)!=1:raise ValueError('目录中不存在对应的唯一版本')
    entry=matches[0];before=digest(encoded(entry));status_key='review_status' if kind=='plugin' else 'status'
    if decision in ('archive','incompatible'):
        entry[status_key]='archived' if decision=='archive' else 'incompatible'
        entry['maintenance_status']='archived' if decision=='archive' else 'maintenance-needed'
        # Preserve immutable local identities / hashes, remove public install link.
        entry['download_url']=None
        if kind=='preset':entry['archive_sha256']=None
    else:entry['maintenance_status']='maintenance-needed'
    RegistryIndex.model_validate(catalog);new_index=encoded(catalog)
    record=RegistryReview(kind=kind,id=identity,version=version,decision=decision,reviewer=reviewer,reason=reason,reviewed_at=now(),
                          input_sha256=before,expected_index_sha256=expected_hash,resulting_index_sha256=digest(new_index))
    output=Path(output)
    if output.exists() or linked(output):raise ValueError('维护草稿输出目录必须不存在')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.registry-maintenance-',dir=output.parent) as temp:
        stage=Path(temp)/'patch';stage.mkdir()
        write_new(stage/'registry/index.json',new_index)
        write_new(stage/'registry/reviews'/f'{kind}-{identity}-{version}.maintenance.json',encoded(record.model_dump(mode='json')))
        stage.rename(output)
    return {'staged':str(output),'original_index_changed':False,'versions_deleted':False,'code_executed':False,'network_access':False}


def main():
    parser=argparse.ArgumentParser(description='目录投稿 / 公开 GitHub 发行核验 / 审核暂存；不安装或运行作品')
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('provenance','prepare'):
        p=commands.add_parser(name);p.add_argument('source');p.add_argument('archive');p.add_argument('output')
        p.add_argument('--repository',required=True);p.add_argument('--source-commit',required=True);p.add_argument('--sdk-commit',required=True);p.add_argument('--tag',required=True)
        if name=='prepare':p.add_argument('--issue-url')
    p=commands.add_parser('verify-release');p.add_argument('submission');p.add_argument('output')
    p=commands.add_parser('review');p.add_argument('submission');p.add_argument('verification');p.add_argument('output');p.add_argument('--index',default=str(ROOT/'registry/index.json'));p.add_argument('--reviewer',required=True);p.add_argument('--reason',required=True);p.add_argument('--decision',choices=['approve-catalog-entry','reject','needs-changes'],default='approve-catalog-entry')
    p=commands.add_parser('stage');p.add_argument('submission');p.add_argument('verification');p.add_argument('review');p.add_argument('output');p.add_argument('--root',default=str(ROOT));p.add_argument('--index')
    p=commands.add_parser('maintenance');p.add_argument('output');p.add_argument('--root',default=str(ROOT));p.add_argument('--index');p.add_argument('--kind',choices=['plugin','preset'],required=True);p.add_argument('--id',required=True);p.add_argument('--version',required=True);p.add_argument('--expected-index-sha256',required=True);p.add_argument('--reviewer',required=True);p.add_argument('--reason',required=True);p.add_argument('--decision',choices=['archive','maintenance-needed','incompatible'],required=True)
    args=parser.parse_args()
    try:
        if args.command in ('provenance','prepare'):
            kwargs={k:getattr(args,k) for k in ('repository','source_commit','sdk_commit','tag')}
            if args.command=='prepare':result=prepare(args.source,args.archive,args.output,**kwargs,issue_url=args.issue_url)
            else:result=provenance(args.source,args.archive,**kwargs);write_new(args.output,encoded(result))
        elif args.command=='verify-release':result=verify_release(args.submission);write_new(args.output,encoded(result))
        elif args.command=='review':result=review(args.submission,args.verification,args.index,args.reviewer,args.reason,args.decision);write_new(args.output,encoded(result))
        elif args.command=='stage':result=stage_submission(args.submission,args.verification,args.review,args.index or Path(args.root)/'registry/index.json',args.output,root=args.root)
        else:result=maintenance(args.index or Path(args.root)/'registry/index.json',args.output,args.kind,args.id,args.version,args.expected_index_sha256,args.reviewer,args.reason,args.decision,root=args.root)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as exc:
        # Network failures may include signed URLs in transport exception text.
        message=str(exc) if isinstance(exc,(ValueError,OSError)) else '核验处理失败，请检查公开发行、格式或网络后重试'
        print(json.dumps({'valid':False,'message':message,'code_executed':False},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)


if __name__=='__main__':main()
