"""Bounded data-only preset codec. Never extracts archives or executes components."""
import base64
import hashlib
import io
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from ..contracts.content import Worldbook, CharacterCard, Theme
from ..contracts.presets import Preset, Scenario

MAX_ARCHIVE = 1024 * 1024
MAX_EXPANDED = 1536 * 1024
MAX_PACKAGE = 2 * 1024 * 1024
MAX_FILE = 512 * 1024
MAX_FILES = 48
MAX_CATALOG_BYTES = 64 * 1024 * 1024
MAX_CATALOG_PACKAGES = 128
PATH_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_/-]*\.(json|md|txt)$')


class PresetError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def safe_path(path):
    if not isinstance(path, str) or len(path) > 160 or not PATH_PATTERN.fullmatch(path):
        raise PresetError('包路径只能用小写 ASCII 相对路径，文件只支持 JSON / Markdown / TXT')
    for segment in path.split('/'):
        if not segment or segment.startswith('.') or segment.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(10)],*[f'LPT{i}' for i in range(10)]}:
            raise PresetError('包路径含空段、隐藏段或 Windows 保留名')
    return path


def json_data(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PresetError('JSON 含重复字段；请明确唯一值')
            result[key] = value
        return result
    def constant(_):
        raise PresetError('不允许 NaN / Infinity')
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=constant)
        stack, nodes = [(value,0)], 0
        while stack:
            child, depth = stack.pop(); nodes += 1
            if depth > 20 or nodes > 50000:
                raise PresetError('JSON 超过嵌套 / 节点上限')
            if isinstance(child,dict): stack.extend((item,depth+1) for item in child.values())
            elif isinstance(child,list): stack.extend((item,depth+1) for item in child)
        if not isinstance(value,dict):
            raise PresetError('JSON 顶层必须为对象')
        return value
    except (UnicodeError,ValueError,RecursionError) as exc:
        if isinstance(exc,PresetError): raise
        raise PresetError('JSON 无法解析；请使用有限、UTF-8 标准数据') from exc


def validate_model(model,raw):
    try:
        return model.model_validate(json_data(raw)).model_dump(mode='json',by_alias=True)
    except ValidationError as exc:
        messages = ['.'.join(map(str,error['loc']))+': '+error['msg'] for error in exc.errors(include_input=False,include_url=False)[:12]]
        raise PresetError('组件不符合 '+model.__name__+' 契约：'+'；'.join(messages)) from exc


@dataclass(frozen=True)
class Package:
    manifest: dict
    files: dict[str,str]
    worldbook: dict
    scenario: dict
    characters: list[dict]
    theme: dict | None
    package_hash: str
    warnings: tuple[str,...]

    def envelope(self):
        return {'format':'ember.preset-bundle/v1','files':self.files}

    def summary(self):
        m=self.manifest
        return {'id':m['metadata']['id'],'name':m['metadata']['name'],'version':m['metadata']['version'],
                'description':m['metadata']['description'],'authors':m['metadata']['authors'],'license':m['metadata']['license'],
                'tags':m['metadata']['tags'],'language':m['language'],'play_mode':m['play_mode'],
                'min_players':m['min_players'],'max_players':m['max_players'],'duration_minutes':m['duration_minutes'],
                'difficulty':m['difficulty'],'content_warnings':m['content_warnings'],'rule_system':m['rule_system'],
                'profile':m['profile'],'minimum_host':m['minimum_host'],'package_hash':self.package_hash,
                'has_theme':bool(self.theme),'character_count':len(self.characters),'scene_count':len(self.scenario['scenes']),
                'ending_count':sum(scene['kind']=='ending' for scene in self.scenario['scenes']),
                'plugins':m['plugins'],'warnings':list(self.warnings),'data_only':True,'default_ai_mode':'demo',
                'possible_costs':'默认演示不调用外部模型；房主显式切换真实主持或生成音频等可能收费。'}


def parse_files(files):
    if not isinstance(files,dict) or not 1 <= len(files) <= MAX_FILES or 'preset.json' not in files:
        raise PresetError('数据包需要 preset.json，最多 48 个文件')
    raw_files={}
    total=0
    for path,text in files.items():
        safe_path(path)
        if not isinstance(text,str): raise PresetError('文件内容必须是 UTF-8 文本，不是代码对象或二进制')
        try: raw=text.encode('utf-8')
        except UnicodeError as exc: raise PresetError('文件含无效 Unicode') from exc
        total+=len(raw)
        if len(raw)>MAX_FILE or total>MAX_EXPANDED: raise PresetError('单文件最多 512 KiB，全包解压文本最多 1.5 MiB')
        raw_files[path]=raw
    manifest=validate_model(Preset,raw_files['preset.json'])
    refs=[manifest['worldbook'],manifest['scenario'],*manifest['characters'],*([manifest['theme']] if manifest['theme'] else []),*manifest['documents']]
    expected={'preset.json',*(ref['path'] for ref in refs)}
    if set(files)!=expected: raise PresetError('文件清单不完整或有未声明文件；不接受脚本、HTML、.env、数据库或任意附带文件')
    for ref in refs:
        path=safe_path(ref['path'])
        if digest(raw_files[path])!=ref['sha256']: raise PresetError('组件 SHA256 不匹配：'+path+'；请重新锁定后打包')
    def component(ref,model):
        if not ref['path'].endswith('.json'): raise PresetError('内容组件必须是 JSON')
        value=validate_model(model,raw_files[ref['path']])
        if value['metadata']['id']!=ref['id'] or value['metadata']['version']!=ref['version']:
            raise PresetError('组件 ID / 版本与清单不符：'+ref['path'])
        return value
    worldbook=component(manifest['worldbook'],Worldbook)
    # Native packages require stable entry IDs; use existing content conversion
    # tools first if importing a legacy / SillyTavern worldbook.
    if any(not item['id'] for item in worldbook['world']['lore']): raise PresetError('玩法包世界书条目必须有稳定 ID')
    scenario=component(manifest['scenario'],Scenario)
    characters=[component(ref,CharacterCard) for ref in manifest['characters']]
    theme=component(manifest['theme'],Theme) if manifest['theme'] else None
    for ref in manifest['documents']:
        if not ref['path'].endswith(('.md','.txt')): raise PresetError('附带说明只支持 Markdown / TXT')
    systems={worldbook['world']['rule_system'],scenario['rule_system'],*[char['rule_system'] for char in characters]}
    if systems!={manifest['rule_system']}: raise PresetError('所有组件必须使用同一可执行规则系统')
    warnings=[]
    for value in [manifest,worldbook,scenario,*characters,*([theme] if theme else [])]:
        if not value['metadata']['license'] or value['metadata']['license'].upper()=='UNLICENSED':
            warnings.append(value['metadata']['name']+' 尚无再分发许可；公开发布前由作者明确授权。')
        if not value['metadata']['authors']: warnings.append(value['metadata']['name']+' 未填写作者。')
    if canonical({'format':'ember.preset-bundle/v1','files':files}).__len__()>MAX_PACKAGE:
        raise PresetError('规范包超过 2 MiB')
    identity=digest(canonical({'manifest':manifest,'files':{path:files[path] for path in sorted(files) if path!='preset.json'}}))
    return Package(manifest,dict(files),worldbook,scenario,characters,theme,identity,tuple(dict.fromkeys(warnings)))


def parse_envelope(document):
    if not isinstance(document,dict) or set(document)!={'format','files'} or document['format']!='ember.preset-bundle/v1':
        raise PresetError('需要 ember.preset-bundle/v1；未知版本不会自动降级')
    return parse_files(document['files'])


def parse_archive(raw):
    if len(raw)>MAX_ARCHIVE: raise PresetError('预设 ZIP 最多 1 MiB')
    files={};total=0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist())>MAX_FILES: raise PresetError('ZIP 文件数超过 48')
            seen=set()
            for entry in archive.infolist():
                path=safe_path(entry.filename)
                if path.casefold() in seen: raise PresetError('ZIP 含重复路径')
                seen.add(path.casefold())
                mode=entry.external_attr>>16
                if entry.is_dir() or entry.flag_bits&1 or stat.S_IFMT(mode) not in (0,stat.S_IFREG):
                    raise PresetError('ZIP 不允许目录项、加密、链接或特殊文件；只打包已声明普通文本文件')
                total+=entry.file_size
                if entry.file_size>MAX_FILE or total>MAX_EXPANDED: raise PresetError('ZIP 解压超过文本大小限制')
                with archive.open(entry) as source:
                    content=source.read(MAX_FILE+1)
                if len(content)>MAX_FILE or len(content)!=entry.file_size: raise PresetError('ZIP 声明与实际文件长度不符')
                files[path]=content.decode('utf-8')
    except (zipfile.BadZipFile,UnicodeError,RuntimeError,OSError,NotImplementedError,EOFError) as exc:
        raise PresetError('ZIP 无效或不能解码；不会解压到磁盘或执行文件') from exc
    return parse_files(files)


def decode_input(archive_base64=None,document=None):
    if (archive_base64 is None)==(document is None): raise PresetError('只能提交 ZIP 或规范 JSON 包其中一种')
    if document is not None: return parse_envelope(document)
    if not isinstance(archive_base64,str) or len(archive_base64)>((MAX_ARCHIVE+2)//3)*4: raise PresetError('ZIP 编码过大或无效')
    try: raw=base64.b64decode(archive_base64,validate=True)
    except (ValueError,base64.binascii.Error) as exc: raise PresetError('ZIP Base64 无效') from exc
    return parse_archive(raw)


def load_folder(folder):
    folder=Path(folder)
    if folder.is_symlink() or not folder.is_dir(): raise PresetError('预设目录必须为普通目录')
    files={}
    for path in folder.rglob('*'):
        if path.is_symlink(): raise PresetError('预设目录不能含符号链接')
        if path.is_dir(): continue
        if not path.is_file(): raise PresetError('预设目录不能含特殊文件')
        relative=safe_path(path.relative_to(folder).as_posix())
        if path.stat().st_size>MAX_FILE: raise PresetError('预设文件超过 512 KiB')
        files[relative]=path.read_bytes().decode('utf-8')
        if len(files)>MAX_FILES: raise PresetError('文件数超过 48')
    return parse_files(files)


def archive_bytes(package):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path,text in sorted(package.files.items()):
            info=zipfile.ZipInfo(path,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(stat.S_IFREG|0o600)<<16
            archive.writestr(info,text.encode('utf-8'))
    raw=output.getvalue()
    if len(raw)>MAX_ARCHIVE: raise PresetError('打包结果超过 1 MiB')
    return raw
