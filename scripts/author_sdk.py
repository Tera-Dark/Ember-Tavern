#!/usr/bin/env python3
"""Build / verify a portable author SDK. Standard library only; no server startup.

Build from tracked source plus explicitly named SDK additions. No arbitrary data,
credentials, binaries, third-party submission code execution, or network access.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FORMAT='ember.author-sdk/v1'
MAX_ARCHIVE=8*1024*1024
MAX_EXPANDED=24*1024*1024
MAX_FILE=1024*1024
MAX_FILES=1000
EXPLICIT=('author-sdk.json','scripts/author_sdk.py','scripts/creator.py','scripts/plugins.py',
          'docs/AUTHOR_SDK.md','author-sdk/README.md','requirements-lock.txt','server/package_integrity.py',
          'server/contracts/community.py','scripts/community.py','scripts/registry.py','docs/COMMUNITY_REVIEW.md',
          'registry/community-release.schema.json','registry/registry-submission.schema.json','registry/registry-review.schema.json')
AUTHOR_DOCS={'CREATOR_GUIDE.md','PRESET_AUTHORING.md','PRESET_FORMAT_RFC.md','PLUGIN_SDK.md','AUTHOR_SDK.md','COMMUNITY_REVIEW.md'}


def digest(raw):return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise ValueError('JSON 包含重复字段')
            result[key]=value
        return result
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)


def git(root,*args):
    result=subprocess.run(['git','-C',str(root),*args],capture_output=True,check=False)
    if result.returncode:raise ValueError('SDK 构建需要有效的源码 Git 工作区')
    return result.stdout


def allowed(relative):
    path=PurePosixPath(relative)
    if any(part.startswith('.') or part in ('__pycache__','node_modules','data') for part in path.parts):return False
    if path.parts[0]=='server':return path.suffix=='.py' or relative=='server/plugin_runtime/bridge.js'
    if path.parts[0]=='templates':return path.suffix in ('.json','.md','.txt','.py','.js')
    if path.parts[0]=='plugins':return path.suffix in ('.json','.py','.js')
    if path.parts[0]=='registry':return path.name.endswith('.schema.json')
    if path.parts[0]=='docs':return len(path.parts)==2 and path.name in AUTHOR_DOCS
    return False


def safe_path(value):
    if not isinstance(value,str) or not value or len(value)>200 or '\\' in value or ':' in value:
        raise ValueError('SDK 路径无效')
    parts=value.split('/')
    if any(part in ('','.','..') or part.startswith('.') for part in parts):raise ValueError('SDK 路径不安全')
    return value


def read_source(root,relative):
    safe_path(relative)
    current=root
    for part in relative.split('/'):
        current=current/part
        if current.is_symlink():raise ValueError('SDK 源码不能包含符号链接：'+relative)
    if not current.is_file() or current.stat().st_size>MAX_FILE:raise ValueError('SDK 文件缺失或超过大小限制：'+relative)
    return current.read_bytes()


def build(output,*,root=ROOT,release=False):
    root=Path(root).resolve();output=Path(output)
    # Read the version as data; building never imports runtime or plugin Python.
    metadata=strict_json(read_source(root,'author-sdk.json'))
    version=metadata.get('version','')
    if metadata.get('format')!='ember.author-sdk-source/v1' or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version):raise ValueError('SDK 版本清单无效')
    if metadata.get('plugin_api')!=1 or metadata.get('python_minimum')!='3.11':raise ValueError('未知 SDK / Python 契约')
    commit=git(root,'rev-parse','HEAD').decode().strip()
    if not re.fullmatch(r'[a-f0-9]{40}',commit):raise ValueError('SDK 来源必须是完整提交')
    dirty=bool(git(root,'status','--porcelain','--untracked-files=normal').strip())
    tracked=git(root,'ls-files','-z').decode('utf-8').split('\0')
    files={name:read_source(root,name) for name in tracked if name and allowed(name)}
    for name in EXPLICIT:files[name]=read_source(root,name)
    license_ready=(root/'LICENSE').is_file() and (root/'AUTHOR_SDK_LICENSE.md').is_file()
    if license_ready:
        license_ready=all(read_source(root,name).strip() for name in ('LICENSE','AUTHOR_SDK_LICENSE.md'))
    if release and dirty:raise ValueError('正式 SDK 包只能来自干净提交；开发包不会冒充发行包')
    if release and not license_ready:raise ValueError('公开 SDK 发行需要正式 LICENSE 和覆盖代码 / 模板 / 文档的 AUTHOR_SDK_LICENSE.md')
    if license_ready:
        for name in ('LICENSE','AUTHOR_SDK_LICENSE.md'):files[name]=read_source(root,name)
    # Only the SDK landing page becomes README. No host download instructions.
    files['README.md']=files.pop('author-sdk/README.md')
    for name,script in [('ember-creator.py','creator.py'),('ember-plugins.py','plugins.py'),('ember-community.py','community.py')]:
        files[name]=(f"from pathlib import Path\nimport runpy\nrunpy.run_path(str(Path(__file__).resolve().parent/'scripts'/'{script}'),run_name='__main__')\n").encode()
    host=read_source(root,'server/version.py').decode('utf-8')
    match=re.search(r"HOST_VERSION = '([^']+)'",host)
    if not match:raise ValueError('宿主版本来源缺失')
    manifest={'format':FORMAT,'version':version,'host_version':match[1],'plugin_api':1,'python_minimum':'3.11',
              'repository':'Tera-Dark/Ember-Tavern','source_commit':commit,'source_dirty':dirty,
              'publication_ready':not dirty and license_ready,
              'notice':'声明不是版权或代码安全认证；本工具不安装依赖、不调用模型、不运行作品代码。',
              'files':[{'path':name,'bytes':len(raw),'sha256':digest(raw)} for name,raw in sorted(files.items())]}
    files['sdk-manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    if len(files)>MAX_FILES or sum(map(len,files.values()))>MAX_EXPANDED:raise ValueError('SDK 包超过限制')
    if output.suffix!='.zip':raise ValueError('SDK 输出必须为 ZIP')
    sidecar=Path(str(output)+'.sha256')
    if output.exists() or output.is_symlink() or sidecar.exists() or sidecar.is_symlink():raise ValueError('SDK 输出已存在；不会覆盖')
    prefix='ember-author-sdk-'+version+'/'
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,raw in sorted(files.items()):
            info=zipfile.ZipInfo(prefix+name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3;info.external_attr=(stat.S_IFREG|0o644)<<16
            archive.writestr(info,raw)
    raw=buffer.getvalue()
    if len(raw)>MAX_ARCHIVE:raise ValueError('SDK ZIP 超过大小限制')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as file:file.write(raw)
    try:
        with sidecar.open('x',encoding='ascii',newline='\n') as file:file.write(digest(raw)+'  '+output.name+'\n')
    except Exception:
        output.unlink();raise
    return {'archive':str(output),'sha256':digest(raw),'version':version,'source_commit':commit,
            'source_dirty':dirty,'publication_ready':manifest['publication_ready'],'files':len(files),'code_executed':False}


def verify(path,expected=None):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_ARCHIVE:raise ValueError('SDK 归档入口无效或过大')
    raw=path.read_bytes()
    if expected is not None and (not re.fullmatch(r'[a-fA-F0-9]{64}',expected) or digest(raw)!=expected.lower()):raise ValueError('SDK 归档 SHA256 不匹配')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos=archive.infolist();names=[safe_path(info.filename) for info in infos]
        if not infos or len(infos)>MAX_FILES or len(names)!=len(set(name.casefold() for name in names)):raise ValueError('SDK 路径重复或文件数量无效')
        prefixes={name.split('/')[0] for name in names}
        if len(prefixes)!=1:raise ValueError('SDK 必须只有一个版本根目录')
        prefix=next(iter(prefixes));manifest_name=prefix+'/sdk-manifest.json'
        total=0;payload={}
        for info,name in zip(infos,names):
            mode=(info.external_attr>>16)&0o170000
            if info.is_dir() or mode not in (0,stat.S_IFREG) or info.flag_bits&1:raise ValueError('SDK 只能包含未加密普通文件')
            if info.file_size>MAX_FILE:raise ValueError('SDK 单文件超过大小限制')
            data=archive.read(info);total+=len(data)
            if len(data)!=info.file_size or total>MAX_EXPANDED:raise ValueError('SDK 解压大小无效')
            payload[name]=data
        if manifest_name not in payload:raise ValueError('SDK 缺少文件清单')
        manifest=strict_json(payload.pop(manifest_name))
        version=manifest.get('version','')
        if manifest.get('format')!=FORMAT or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version) or prefix!='ember-author-sdk-'+version:raise ValueError('SDK 清单 / 目录版本不一致')
        if not re.fullmatch(r'[a-f0-9]{40}',manifest.get('source_commit','')) or type(manifest.get('source_dirty')) is not bool:raise ValueError('SDK 构建来源无效')
        if manifest.get('plugin_api')!=1 or manifest.get('python_minimum')!='3.11':raise ValueError('SDK 契约版本不兼容')
        indexed=set()
        entries=manifest.get('files')
        if not isinstance(entries,list) or len(entries)>MAX_FILES:raise ValueError('SDK 文件清单无效')
        for entry in entries:
            if not isinstance(entry,dict) or set(entry)!= {'path','bytes','sha256'}:raise ValueError('SDK 文件声明无效')
            name=prefix+'/'+safe_path(entry['path']);data=payload.get(name)
            if name in indexed or data is None or type(entry['bytes']) is not int or entry['bytes']!=len(data) or entry['sha256']!=digest(data):raise ValueError('SDK 文件缺失、重复或散列不匹配')
            indexed.add(name)
        if indexed!=set(payload):raise ValueError('SDK 含未声明文件')
        expected_ready=not manifest['source_dirty'] and all(bool(payload.get(prefix+'/'+name,b'').strip()) for name in ('LICENSE','AUTHOR_SDK_LICENSE.md'))
        if type(manifest.get('publication_ready')) is not bool or manifest['publication_ready']!=expected_ready:raise ValueError('SDK 发布状态与来源 / 许可文件不一致')
        source_metadata=strict_json(payload[prefix+'/author-sdk.json']) if prefix+'/author-sdk.json' in payload else {}
        if source_metadata.get('version')!=version or source_metadata.get('format')!='ember.author-sdk-source/v1':raise ValueError('SDK 源码版本清单与归档不一致')
        for required in ('README.md','ember-creator.py','scripts/creator.py','scripts/plugins.py','requirements-lock.txt','author-sdk.json'):
            if prefix+'/'+required not in indexed:raise ValueError('SDK 缺少必要入口：'+required)
    return {'valid':True,'format':FORMAT,'version':version,'sha256':digest(raw),'source_commit':manifest['source_commit'],
            'source_dirty':manifest['source_dirty'],'publication_ready':manifest.get('publication_ready',False),
            'files':len(infos),'code_executed':False,'notice':'散列是完整性校验，不是签名、版权认证或第三方代码审查。'}


def main():
    parser=argparse.ArgumentParser(description='版本化作者 SDK：构建 / 只读验证，无外网与作品代码执行')
    commands=parser.add_subparsers(dest='command',required=True)
    pack=commands.add_parser('build');pack.add_argument('output');pack.add_argument('--release',action='store_true')
    check=commands.add_parser('verify');check.add_argument('archive');check.add_argument('--sha256')
    args=parser.parse_args()
    try:
        result=build(args.output,release=args.release) if args.command=='build' else verify(args.archive,args.sha256)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError,zipfile.BadZipFile) as exc:
        print(json.dumps({'valid':False,'message':str(exc)},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)


if __name__=='__main__':main()
