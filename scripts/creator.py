#!/usr/bin/env python3
"""Creator CLI: scaffold, validate, and check schemas without executing extensions."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.config import ROOT
from server.contracts.catalog import CONTENT_FORMATS, schema_for
from server.contracts.common import Metadata
from server.contracts.plugin import validate_manifest
from server.content.imports import ContentError, MAX_CONTENT_BYTES, normalize

PLUGIN_TEMPLATES = {'plugin-ui': 'session-insights', 'plugin-backend': 'scene-notes', 'plugin-dice': 'dice-tray'}
KINDS = tuple(CONTENT_FORMATS) + tuple(PLUGIN_TEMPLATES)


def scaffold(kind, destination, identity, name=None):
    # Validate the user-provided identity before touching the filesystem.
    if kind not in KINDS:
        raise ValueError('未知模板类型')
    info = Metadata(id=identity, name=name or identity).model_dump(mode='json')
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError('输出目录不能是符号链接')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('输出目录必须不存在或为空；不会覆盖已有作品')
    destination.mkdir(parents=True, exist_ok=True)
    if kind in PLUGIN_TEMPLATES:
        source = ROOT / 'templates' / PLUGIN_TEMPLATES[kind]
        for path in source.iterdir():
            if path.is_file():
                shutil.copy2(path, destination / path.name)
        manifest_path = destination / 'plugin.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest.update(id=identity, name=info['name'], version='1.0.0', default_enabled=False, authors=[], license='',
                        minimum_host='2.2.0' if kind=='plugin-dice' else '2.1.0')
        if manifest.get('ui'):
            manifest['ui'].update(group=identity, label=info['name'])
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        validate_manifest(manifest, destination)
    else:
        source = ROOT / 'templates' / kind / f'{kind}.json'
        document = json.loads(source.read_text(encoding='utf-8'))
        document['metadata'].update(id=identity, name=info['name'], authors=[], license='')
        normalize(kind, document)
        (destination / f'{kind}.json').write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        readme = ROOT / 'templates' / kind / 'README.md'
        if readme.exists():
            shutil.copy2(readme, destination / 'README.md')
    return {'created': str(destination), 'kind': kind, 'id': identity, 'next': '修改内容、填写署名与许可，再运行 validate'}


def validate(path, kind=None):
    path = Path(path)
    if path.is_dir() or path.name == 'plugin.json':
        folder = path if path.is_dir() else path.parent
        manifest = validate_manifest(json.loads((folder / 'plugin.json').read_text(encoding='utf-8')), folder)
        if manifest['api_version'] != 1:
            raise ValueError('当前宿主只支持 Plugin API 1')
        return {'valid': True, 'kind': 'plugin', 'id': manifest['id'], 'code_executed': False,
                'notice': '只校验清单与入口文件；不代表代码审计或安全授权。'}
    if path.stat().st_size > MAX_CONTENT_BYTES:
        raise ContentError('创作文件不能超过 512 KiB')
    document = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(document, dict):
        raise ValueError('创作文件的顶层必须是 JSON 对象')
    if kind is None:
        kind = next((name for name, fmt in CONTENT_FORMATS.items() if document.get('format') == fmt), None)
    if kind is None:
        raise ValueError('兼容格式请指定 --kind worldbook 或 --kind character')
    result = normalize(kind, document)
    return {'valid': True, **{key: value for key, value in result.items() if key != 'document'}}


def schemas(check=False):
    changed = []
    for kind in (*CONTENT_FORMATS, 'plugin'):
        path = ROOT / 'registry' / f'{kind}.schema.json'
        value = json.dumps(schema_for(kind), ensure_ascii=False, indent=2) + '\n'
        if not path.exists() or path.read_text(encoding='utf-8') != value:
            changed.append(path.relative_to(ROOT).as_posix())
            if not check:
                path.write_text(value, encoding='utf-8')
    if check and changed:
        raise ValueError('契约 Schema 发生漂移，请审阅后重新生成：' + ', '.join(changed))
    return {'schema_drift': changed if check else [], 'generated': changed if not check else []}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='余烬酒馆创作工具（不执行插件代码）')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('kind', choices=KINDS)
    init.add_argument('output')
    init.add_argument('--id', required=True)
    init.add_argument('--name')
    check = commands.add_parser('validate')
    check.add_argument('path')
    check.add_argument('--kind', choices=tuple(CONTENT_FORMATS))
    export = commands.add_parser('schemas')
    export.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            result = scaffold(args.kind, args.output, args.id, args.name)
        elif args.command == 'validate':
            result = validate(args.path, args.kind)
        else:
            result = schemas(args.check)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RecursionError) as exc:
        print(json.dumps({'valid': False, 'message': str(exc), 'errors': getattr(exc, 'errors', [])}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
