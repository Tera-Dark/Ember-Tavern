#!/usr/bin/env python3
"""Creator scaffolding, validation, immutable packaging. Never imports plugin code."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import os
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from server.config import ROOT,settings
from server.contracts.catalog import CONTENT_FORMATS,AUTHOR_MODELS,CORE_MODELS,schema_for
from server.contracts.common import Metadata
from server.contracts.presets import Scenario
from server.contracts.plugin import validate_manifest
from server.content.imports import ContentError,MAX_CONTENT_BYTES,normalize
from server.presets.codec import (load_folder,parse_archive,parse_envelope,archive_bytes,digest,validate_model,safe_path,PresetError,MAX_ARCHIVE)
from server.plugin_runtime.integrity import package_hash

PLUGIN_TEMPLATES={'plugin-ui':'session-insights','plugin-backend':'scene-notes','plugin-dice':'dice-tray','plugin-campaign':'campaign-compass'}
KINDS=tuple(AUTHOR_MODELS)+tuple(PLUGIN_TEMPLATES)


def write_json(path,value):
    path=Path(path)
    if path.is_symlink():raise ValueError('输出不能是链接')
    handle,temporary=tempfile.mkstemp(prefix='.creator-',dir=path.parent)
    try:
        with os.fdopen(handle,'w',encoding='utf-8',newline='\n') as file:
            file.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n');file.flush();os.fsync(file.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def plugin_pins(identity=None):
    results=[];seen=set()
    for base in (ROOT/'plugins',settings.data_dir/'plugins'):
        if not base.exists():continue
        for folder in sorted(base.iterdir()):
            if folder.is_symlink() or not folder.is_dir() or not (folder/'plugin.json').is_file():continue
            if (folder/'plugin.json').is_symlink():raise ValueError('插件清单不能是链接')
            manifest=validate_manifest(json.loads((folder/'plugin.json').read_text(encoding='utf-8')),folder)
            if manifest['id'] in seen:continue
            seen.add(manifest['id'])
            if identity and manifest['id']!=identity:continue
            results.append({'id':manifest['id'],'version':manifest['version'],'sha256':package_hash(folder)})
    if identity and not results:raise ValueError('模块未在本机安装；不会下载或执行代码')
    return results


def lock_preset(folder,refresh_plugins=False):
    folder=Path(folder);path=folder/'preset.json'
    if path.is_symlink():raise ValueError('清单不能是链接')
    manifest=json.loads(path.read_text(encoding='utf-8-sig'))
    refs=[manifest['worldbook'],manifest['scenario'],*manifest['characters'],*([manifest['theme']] if manifest.get('theme') else [])]
    for ref in refs:
        source=folder/safe_path(ref['path'])
        if source.is_symlink() or not source.is_file() or source.stat().st_size>MAX_CONTENT_BYTES:raise ValueError('组件文件不是普通小型文件')
        raw=source.read_bytes();metadata=json.loads(raw.decode('utf-8-sig'))['metadata']
        ref.update(id=metadata['id'],version=metadata['version'],sha256=digest(raw))
    for ref in manifest.get('documents',[]):
        source=folder/safe_path(ref['path'])
        if source.is_symlink() or not source.is_file() or source.stat().st_size>MAX_CONTENT_BYTES:raise ValueError('说明文件无效')
        ref['sha256']=digest(source.read_bytes())
    if refresh_plugins:
        for ref in manifest.get('plugins',[]):ref.update(plugin_pins(ref['id'])[0])
    # Check all files and graph before changing the existing manifest.
    files={}
    for source in folder.rglob('*'):
        if source.is_symlink():raise ValueError('作品目录含链接')
        if source.is_file():files[source.relative_to(folder).as_posix()]=source.read_text(encoding='utf-8')
    files['preset.json']=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    from server.presets.codec import parse_files
    package=parse_files(files)
    write_json(path,manifest)
    return {'locked':str(folder),'package_hash':package.package_hash,'warnings':list(package.warnings),'code_executed':False}


def scaffold(kind,destination,identity,name=None):
    if kind not in KINDS:raise ValueError('未知模板类型')
    info=Metadata(id=identity,name=name or identity).model_dump(mode='json')
    destination=Path(destination)
    if destination.is_symlink():raise ValueError('输出目录不能是符号链接')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):raise ValueError('输出目录必须不存在或为空；不会覆盖已有作品')
    destination.mkdir(parents=True,exist_ok=True)
    if kind in PLUGIN_TEMPLATES:
        source=ROOT/'templates'/PLUGIN_TEMPLATES[kind]
        for path in source.iterdir():
            if path.is_file():shutil.copy2(path,destination/path.name)
        manifest_path=destination/'plugin.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.update(id=identity,name=info['name'],version='1.0.0',default_enabled=False,authors=[],license='',minimum_host='2.4.0' if kind=='plugin-campaign' else '2.2.0' if kind=='plugin-dice' else '2.1.0')
        if manifest.get('ui'):manifest['ui'].update(group=identity,label=info['name'])
        write_json(manifest_path,manifest);validate_manifest(manifest,destination)
    elif kind=='preset':
        shutil.copytree(ROOT/'templates/preset',destination,dirs_exist_ok=True)
        manifest=json.loads((destination/'preset.json').read_text(encoding='utf-8'));manifest['metadata'].update(id=identity,name=info['name'],authors=[],license='')
        write_json(destination/'preset.json',manifest)
        lock_preset(destination,refresh_plugins=True)
    else:
        source=ROOT/'templates'/kind/f'{kind}.json';document=json.loads(source.read_text(encoding='utf-8'))
        document['metadata'].update(id=identity,name=info['name'],authors=[],license='')
        if kind=='scenario':validate_model(Scenario,json.dumps(document,ensure_ascii=False).encode())
        else:normalize(kind,document)
        write_json(destination/f'{kind}.json',document)
        readme=ROOT/'templates'/kind/'README.md'
        if readme.exists():shutil.copy2(readme,destination/'README.md')
    return {'created':str(destination),'kind':kind,'id':identity,'next':'修改内容、填写署名与许可，再运行 validate；预设改组件后先 lock-preset'}


def validate(path,kind=None):
    path=Path(path)
    if path.is_symlink():raise ValueError('创作入口不能是链接')
    if (path.is_dir() and (path/'preset.json').is_file()) or path.name=='preset.json':
        package=load_folder(path if path.is_dir() else path.parent)
        return {'valid':True,'kind':'preset','package_hash':package.package_hash,'summary':package.summary(),'code_executed':False}
    if path.suffix=='.zip':
        if path.stat().st_size>MAX_ARCHIVE:raise ValueError('预设 ZIP 最多 1 MiB')
        package=parse_archive(path.read_bytes())
        return {'valid':True,'kind':'preset','package_hash':package.package_hash,'summary':package.summary(),'code_executed':False}
    if path.is_dir() or path.name=='plugin.json':
        folder=path if path.is_dir() else path.parent;manifest=validate_manifest(json.loads((folder/'plugin.json').read_text(encoding='utf-8')),folder)
        if manifest['api_version']!=1:raise ValueError('当前宿主只支持 Plugin API 1')
        return {'valid':True,'kind':'plugin','id':manifest['id'],'code_executed':False,'notice':'只校验清单与入口文件；不代表代码审计或安全授权。'}
    if path.stat().st_size>2*MAX_CONTENT_BYTES and kind!='preset':raise ContentError('创作文件过大')
    raw=path.read_bytes();document=json.loads(raw.decode('utf-8-sig'))
    if not isinstance(document,dict):raise ValueError('创作文件的顶层必须是 JSON 对象')
    if document.get('format')=='ember.preset-bundle/v1':
        package=parse_envelope(document)
        return {'valid':True,'kind':'preset','package_hash':package.package_hash,'summary':package.summary(),'code_executed':False}
    if kind=='scenario' or document.get('format')=='ember.scenario/v1':
        if len(raw)>MAX_CONTENT_BYTES:raise ValueError('剧本文件过大')
        value=validate_model(Scenario,raw)
        return {'valid':True,'kind':'scenario','id':value['metadata']['id'],'scenes':len(value['scenes']),'code_executed':False}
    if len(raw)>MAX_CONTENT_BYTES:raise ContentError('创作文件不能超过 512 KiB')
    if kind is None:kind=next((name for name,fmt in CONTENT_FORMATS.items() if document.get('format')==fmt),None)
    if kind is None:raise ValueError('兼容格式请指定 --kind worldbook 或 --kind character')
    result=normalize(kind,document)
    return {'valid':True,**{key:value for key,value in result.items() if key!='document'}}


def package_preset(folder,output):
    package=load_folder(folder);output=Path(output)
    if output.suffix not in ('.zip','.json'):raise ValueError('预设输出只支持 .zip 或 .json')
    if output.exists() or output.is_symlink():raise ValueError('输出已存在；不会覆盖')
    output.parent.mkdir(parents=True,exist_ok=True)
    raw=archive_bytes(package) if output.suffix=='.zip' else json.dumps(package.envelope(),ensure_ascii=False,indent=2).encode()
    with output.open('xb') as file:file.write(raw)
    return {'created':str(output),'archive_sha256':digest(raw),'package_hash':package.package_hash,'code_executed':False}


def schemas(check=False):
    changed=[]
    for kind in (*AUTHOR_MODELS, *CORE_MODELS, 'plugin'):
        path=ROOT/'registry'/f'{kind}.schema.json';value=json.dumps(schema_for(kind),ensure_ascii=False,indent=2)+'\n'
        if not path.exists() or path.read_text(encoding='utf-8')!=value:
            changed.append(path.relative_to(ROOT).as_posix())
            if not check:path.write_text(value,encoding='utf-8',newline='\n')
    if check and changed:raise ValueError('契约 Schema 发生漂移，请审阅后重新生成：'+', '.join(changed))
    return {'schema_drift':changed if check else [],'generated':changed if not check else []}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='余烬创作工具（不执行插件代码）');commands=parser.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init');init.add_argument('kind',choices=KINDS);init.add_argument('output');init.add_argument('--id',required=True);init.add_argument('--name')
    check=commands.add_parser('validate');check.add_argument('path');check.add_argument('--kind',choices=tuple(AUTHOR_MODELS))
    export=commands.add_parser('schemas');export.add_argument('--check',action='store_true')
    lock=commands.add_parser('lock-preset');lock.add_argument('path');lock.add_argument('--refresh-plugins',action='store_true')
    pack=commands.add_parser('package-preset');pack.add_argument('path');pack.add_argument('output')
    pins=commands.add_parser('plugin-pins');pins.add_argument('--id')
    args=parser.parse_args()
    try:
        if args.command=='init':result=scaffold(args.kind,args.output,args.id,args.name)
        elif args.command=='validate':result=validate(args.path,args.kind)
        elif args.command=='schemas':result=schemas(args.check)
        elif args.command=='lock-preset':result=lock_preset(args.path,args.refresh_plugins)
        elif args.command=='package-preset':result=package_preset(args.path,args.output)
        else:result={'pins':plugin_pins(args.id),'code_executed':False,'notice':'散列不是授权；安装代码和能力仍需独立审阅。'}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,OSError,RecursionError,KeyError) as exc:
        print(json.dumps({'valid':False,'message':str(exc),'errors':getattr(exc,'errors',[])},ensure_ascii=False),file=sys.stderr);raise SystemExit(1)
