#!/usr/bin/env python3
"""Validate the repository-local community index without network or code execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from io import BytesIO

MAX_PLUGIN_ARCHIVE = 8 * 1024 * 1024
MAX_PLUGIN_ARCHIVE_EXPANDED = 32 * 1024 * 1024
MAX_PLUGIN_ARCHIVE_FILES = 128
MAX_REGISTRY_INDEX = 2 * 1024 * 1024
MAX_PLUGIN_MANIFEST = 64 * 1024

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pydantic import ValidationError
from server.config import ROOT
from server.contracts.registry import RegistryIndex
from server.contracts.catalog import (CONTENT_FORMATS, CONTENT_MODELS, CORE_MODELS,
                                      PRESET_MODELS, schema_for)
from server.contracts.plugin import validate_manifest
from server.presets.codec import load_folder


def _strict_json(raw: bytes):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'JSON 字段重复：{key}')
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f'JSON 不允许非有限数字：{value}')

    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_pairs,
                          parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f'JSON 无效：{exc}') from exc


def _safe_file(root: Path, relative: str, *, directory=False) -> Path:
    root = root.resolve()
    path = root / relative
    current = root
    for part in Path(relative).parts:
        if part in ('', '.', '..'):
            raise ValueError(f'registry 路径不安全：{relative}')
        current = current / part
        if current.is_symlink():
            raise ValueError(f'registry 不接受符号链接：{relative}')
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f'registry 路径越过仓库边界：{relative}')
    if directory and not resolved.is_dir():
        raise ValueError(f'registry 目录不存在：{relative}')
    if not directory and not resolved.is_file():
        raise ValueError(f'registry 文件不存在：{relative}')
    return resolved


def _check_plugin_archive(entry, archive_path: Path):
    if archive_path.stat().st_size > MAX_PLUGIN_ARCHIVE:
        raise ValueError(f"插件 {entry.id} ZIP 超过 {MAX_PLUGIN_ARCHIVE} 字节上限")
    raw = archive_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry.sha256:
        raise ValueError(f"插件 {entry.id}@{entry.version} 的 ZIP SHA256 与 registry 不符")
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = archive.namelist()
            if not infos or len(infos) > MAX_PLUGIN_ARCHIVE_FILES:
                raise ValueError(f"插件 {entry.id} ZIP 文件数为空或超过上限")
            if len(names) != len(set(names)) or len(names) != len({name.casefold() for name in names}):
                raise ValueError(f"插件 {entry.id} ZIP 包含重复／大小写冲突路径")
            expanded = 0
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                if info.is_dir() or mode not in (0, 0o100000) or info.flag_bits & 1:
                    raise ValueError(f"插件 {entry.id} ZIP 只接受未加密普通文件")
                name = info.filename.replace('\\', '/')
                parts = name.split('/')
                if (len(name) > 180 or name.startswith('/') or '\\' in info.filename
                        or any(part in ('', '.', '..') or part.startswith('.') or ':' in part for part in parts)):
                    raise ValueError(f"插件 {entry.id} ZIP 路径不安全：{info.filename}")
                if info.file_size > MAX_PLUGIN_ARCHIVE:
                    raise ValueError(f"插件 {entry.id} ZIP 单文件解压大小超过限制")
                actual_size = 0
                with archive.open(info) as source:
                    while chunk := source.read(64 * 1024):
                        actual_size += len(chunk)
                        if actual_size > MAX_PLUGIN_ARCHIVE or expanded + actual_size > MAX_PLUGIN_ARCHIVE_EXPANDED:
                            raise ValueError(f"插件 {entry.id} ZIP 解压大小超过限制")
                if actual_size != info.file_size:
                    raise ValueError(f"插件 {entry.id} ZIP 文件长度声明与内容不符：{info.filename}")
                expanded += actual_size
            manifests = [name for name in names if name == 'plugin.json' or name.endswith('/plugin.json')]
            if len(manifests) != 1 or archive.getinfo(manifests[0]).file_size > MAX_PLUGIN_MANIFEST:
                raise ValueError(f"插件 {entry.id} ZIP 必须仅含一个且不超过 64 KiB 的 plugin.json")
            manifest = _strict_json(archive.read(manifests[0]))
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, RuntimeError,
            NotImplementedError, EOFError, OSError) as exc:
        raise ValueError(f"插件 {entry.id} ZIP 无法读取清单：{exc}") from exc
    try:
        manifest = validate_manifest(manifest)
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"插件 {entry.id} ZIP 清单契约无效：{exc}") from exc
    prefix = manifests[0].rsplit('/', 1)[0] if '/' in manifests[0] else ''
    for script in (manifest.get('backend'), manifest.get('frontend')):
        if script and (f'{prefix}/{script}' if prefix else script) not in names:
            raise ValueError(f"插件 {entry.id} ZIP 缺少清单声明的入口文件：{script}")
    return manifest


def _check_plugin_summary(entry, manifest, *, source):
    actual = {
        'id': manifest['id'],
        'name': manifest['name'],
        'description': manifest['description'],
        'category': manifest['category'],
        'version': manifest['version'],
        'minimum_host': manifest['minimum_host'],
        'api_version': manifest['api_version'],
        'backend': bool(manifest.get('backend')),
        'capabilities': sorted(manifest.get('capabilities', [])),
        'requires': sorted(manifest.get('requires', [])),
        'uses': sorted(manifest.get('uses', [])),
        'provides': sorted(manifest.get('provides', [])),
        'license': manifest.get('license') or 'UNLICENSED',
        'authors': manifest.get('authors', []),
    }
    expected = {
        'id': entry.id,
        'name': entry.name,
        'description': entry.description,
        'category': entry.category,
        'version': entry.version,
        'minimum_host': entry.minimum_host,
        'api_version': entry.api_version,
        'backend': entry.backend,
        'capabilities': sorted(entry.capabilities),
        'requires': sorted(entry.requires),
        'uses': sorted(entry.uses),
        'provides': sorted(entry.provides),
        'license': entry.license,
        'authors': entry.authors,
    }
    if actual != expected:
        raise ValueError(f"插件 {entry.id} registry 摘要与{source}不符")


def _check_schema_document(root, kind, relative):
    path = _safe_file(root, relative)
    if path.stat().st_size > MAX_REGISTRY_INDEX:
        raise ValueError(f'{kind} Schema 超过大小上限：{relative}')
    try:
        actual = _strict_json(path.read_bytes())
        expected = schema_for(kind)
    except (OSError, ValueError) as exc:
        raise ValueError(f'{kind} Schema 无法读取或生成：{relative}') from exc
    if actual != expected:
        raise ValueError(f'{kind} Schema 与版本化合同不符：{relative}')


def _check_template_document(root, kind, relative, expected_format, model):
    path = _safe_file(root, relative)
    if path.stat().st_size > 512 * 1024:
        raise ValueError(f'{kind} 模板超过 512 KiB：{relative}')
    try:
        document = _strict_json(path.read_bytes())
        if document.get('format') != expected_format:
            raise ValueError(f'{kind} 模板格式标识不符：{relative}')
        model.model_validate(document)
    except (OSError, AttributeError, ValidationError, ValueError) as exc:
        raise ValueError(f'{kind} 模板不符合版本化合同：{relative}') from exc


def validate_registry(index_path: Path | str | None = None, *, root: Path | str | None = None):
    root = Path(root or ROOT).resolve()
    index_path = Path(index_path or root / 'registry/index.json')
    if not index_path.is_absolute():
        index_path = root / index_path
    try:
        relative_index = index_path.absolute().relative_to(root)
        index_path = _safe_file(root, relative_index.as_posix())
        if index_path.stat().st_size > MAX_REGISTRY_INDEX:
            raise ValueError(f'registry 索引超过 {MAX_REGISTRY_INDEX} 字节上限')
        registry = RegistryIndex.model_validate(_strict_json(index_path.read_bytes()))
    except (OSError, ValidationError, RecursionError) as exc:
        raise ValueError(f'registry 契约无效：{exc}') from exc

    warnings = []
    checked_plugins = []
    for entry in registry.plugins:
        template = _safe_file(root, entry.template_path, directory=True)
        manifest_path = _safe_file(template, 'plugin.json')
        if manifest_path.stat().st_size > MAX_PLUGIN_MANIFEST:
            raise ValueError(f"插件 {entry.id} 源码模板的 plugin.json 超过 {MAX_PLUGIN_MANIFEST} 字节")
        try:
            manifest = validate_manifest(_strict_json(manifest_path.read_bytes()), template)
        except (OSError, ValidationError, ValueError) as exc:
            raise ValueError(f"插件 {entry.id} 模板清单无效：{exc}") from exc
        _check_plugin_summary(entry, manifest, source='源码模板')
        if entry.package:
            archive_path = _safe_file(root, f'plugin-packages/{entry.package}')
            archive_manifest = _check_plugin_archive(entry, archive_path)
            _check_plugin_summary(entry, archive_manifest, source='锁定 ZIP')
        if entry.review_status == 'legacy-reference-only':
            warnings.append(f"插件 {entry.id}：保留旧下载引用；未联网验证且不作为新推荐")
        elif entry.review_status in ('community-playtested', 'official-recommended') and entry.license.upper() == 'UNLICENSED':
            # Also guarded by the Pydantic contract; retain an explicit policy assertion here.
            raise ValueError(f"插件 {entry.id} 没有可供社区发行的明确许可")
        checked_plugins.append(entry.id)

    checked_presets = []
    for entry in registry.preset_library:
        folder = _safe_file(root, entry.source_path, directory=True)
        try:
            package = load_folder(folder)
        except Exception as exc:
            raise ValueError(f"预设 {entry.id}@{entry.version} 数据包无效：{exc}") from exc
        manifest = package.manifest
        if package.package_hash != entry.package_hash:
            raise ValueError(f"预设 {entry.id}@{entry.version} 锁定 package_hash 已漂移")
        actual = {
            'id': manifest['metadata']['id'],
            'name': manifest['metadata']['name'],
            'description': manifest['metadata']['description'],
            'tags': manifest['metadata']['tags'],
            'version': manifest['metadata']['version'],
            'license': manifest['metadata']['license'],
            'authors': manifest['metadata']['authors'],
            'rule_system': manifest['rule_system'],
            'rule_version': manifest['rule_version'],
            'minimum_host': manifest['minimum_host'],
            'plugin_api': manifest['plugin_api'],
            'language': manifest['language'],
            'play_mode': manifest['play_mode'],
            'min_players': manifest['min_players'],
            'max_players': manifest['max_players'],
            'duration_minutes': manifest['duration_minutes'],
            'difficulty': manifest['difficulty'],
            'content_warnings': manifest['content_warnings'],
            'plugins': manifest['plugins'],
        }
        for field, value in actual.items():
            expected = ([pin.model_dump(mode='json') for pin in entry.plugins]
                        if field == 'plugins' else getattr(entry, field))
            if expected != value:
                raise ValueError(f"预设 {entry.id} registry 字段 {field} 与锁定清单不符")
        if entry.download_url and entry.license.upper() == 'UNLICENSED':
            raise ValueError(f"预设 {entry.id} 未获再分发许可，不能标注为公开下载")
        if entry.status in ('community-playtested', 'official-recommended') and not entry.evidence:
            raise ValueError(f"预设 {entry.id} 的分级缺少证据链接")
        checked_presets.append(entry.id)

    if {item.kind for item in registry.content_templates} != set(CONTENT_MODELS):
        raise ValueError('registry 必须列出全部内容模板类型')
    if {item.kind for item in registry.gameplay_templates} != set(PRESET_MODELS):
        raise ValueError('registry 必须列出全部玩法模板类型')
    expected_core_schemas = set(CORE_MODELS) - {'registry-index'}
    if {item.kind for item in registry.core_schemas} != expected_core_schemas:
        raise ValueError('registry 核心 Schema 列表与宿主合同不一致')
    for item in registry.content_templates:
        if item.format != CONTENT_FORMATS[item.kind]:
            raise ValueError(f'{item.kind} registry 格式标识不符')
        _check_schema_document(root, item.kind, item.schema_path)
        _check_template_document(root, item.kind, item.template_path, item.format, CONTENT_MODELS[item.kind])
    gameplay_formats = {'preset': 'ember.preset/v1', 'scenario': 'ember.scenario/v1'}
    for item in registry.gameplay_templates:
        _check_schema_document(root, item.kind, item.schema_path)
        _check_template_document(root, item.kind, item.template_path,
                                 gameplay_formats[item.kind], PRESET_MODELS[item.kind])
    for item in registry.core_schemas:
        _check_schema_document(root, item.kind, item.schema_path)

    return {
        'valid': True,
        'registry_version': registry.registry_version,
        'plugins_checked': len(checked_plugins),
        'presets_checked': len(checked_presets),
        'warnings': warnings,
        'code_executed': False,
        'network_access': False,
    }


def main():
    parser = argparse.ArgumentParser(description='验证本地作品索引；不联网、不运行包内代码')
    parser.add_argument('--index', default=str(ROOT / 'registry/index.json'))
    args = parser.parse_args()
    try:
        result = validate_registry(args.index, root=ROOT)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({'valid': False, 'message': str(exc), 'code_executed': False,
                          'network_access': False}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
