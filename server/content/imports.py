"""Normalize supported JSON formats without executing code or fetching URLs."""
from copy import deepcopy
import hashlib
import json
import re

from pydantic import ValidationError

from ..contracts.content import CONTENT_MODELS, WorldData
from ..contracts.catalog import CONTENT_FORMATS

MAX_CONTENT_BYTES = 512 * 1024


class ContentError(ValueError):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []


def bounded_document(document):
    if not isinstance(document, dict):
        raise ContentError('创作文件的顶层必须是 JSON 对象')
    # Bound both recursive complexity and encoded size, including extension fields.
    queue = [(document, 0)]
    count = 0
    while queue:
        value, depth = queue.pop()
        count += 1
        if depth > 16 or count > 20000:
            raise ContentError('JSON 嵌套或节点数量超过限制')
        if isinstance(value, dict):
            queue.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            queue.extend((child, depth + 1) for child in value)
    try:
        encoded = json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    except (ValueError, TypeError, RecursionError):
        raise ContentError('文件包含非标准 JSON 数据')
    if len(encoded) > MAX_CONTENT_BYTES:
        raise ContentError('创作文件不能超过 512 KiB')
    return encoded


def metadata(kind, name):
    return {'id': f'imported-{kind}', 'name': name, 'version': '1.0.0',
            'description': '从兼容格式转换，请作者补充署名和许可。', 'authors': [], 'license': ''}


def convert_worldbook(document):
    if 'lore' in document and 'title' in document:
        return {'format': 'ember.worldbook/v1', 'metadata': metadata('worldbook', document['title']),
                'world': deepcopy(document)}, 'ember-legacy-world', ['旧版世界数据已转换；未标记的条目默认公共、按关键词启用。']
    entries = document.get('entries')
    if not isinstance(entries, (dict, list)):
        raise ContentError('不支持的世界书格式。支持余烬 v1、旧版世界 JSON、SillyTavern entries JSON。')
    source = list(entries.items()) if isinstance(entries, dict) else list(enumerate(entries))
    if len(source) > 160:
        raise ContentError('世界书最多 160 个条目，请拆分后导入')
    lore, warnings = [], set()
    for index, (entry_id, item) in enumerate(source):
        if not isinstance(item, dict):
            raise ContentError(f'条目 {entry_id} 不是对象')
        keys = item.get('key', item.get('keys', []))
        if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
            raise ContentError(f'条目 {entry_id} 的关键词必须是字符串数组')
        enabled = not item.get('disable', False) and item.get('enabled', True)
        if item.get('useRegex') or item.get('use_regex'):
            enabled = False
            warnings.add('正则条目已停用：导入器只执行字面关键词匹配，请修改关键词后手动启用。')
        if item.get('selective') or item.get('keysecondary') or item.get('secondary_keys'):
            warnings.add('选择性／次级关键词逻辑未实现，只保留主关键词；请检查转换后的触发条件。')
        if any(key in item for key in ('position', 'depth', 'role', 'outletName', 'probability')):
            warnings.add('注入位置、深度、角色、出口和概率字段未移植；宿主使用固定、安全的上下文组装。')
        content = item.get('content', '')
        # Disabled empty placeholders do not provide playable content.
        if isinstance(content, str) and not content.strip() and not enabled:
            warnings.add('已跳过停用且为空的占位条目。')
            continue
        raw_id = str(item.get('uid', item.get('id', entry_id)))
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '-', raw_id)[:52] or str(index)
        lore.append({'id': 'st-' + safe_id, 'title': item.get('comment') or item.get('name') or f'导入条目 {index + 1}',
                     'content': content, 'keys': keys, 'enabled': enabled,
                     'activation': 'always' if item.get('constant') else 'keywords',
                     'visibility': 'public', 'kind': 'lore', 'priority': 0})
    title = document.get('name') or '导入的世界书'
    world = {'title': title, 'premise': document.get('description') or '导入的世界书。请房主补充冒险前提与叙事基调。', 'lore': lore}
    warnings.add('兼容转换默认所有条目为公共设定，不推断主持秘密或可执行规则；导入前请检查。')
    return {'format': 'ember.worldbook/v1', 'metadata': metadata('worldbook', title), 'world': world}, 'sillytavern-entries', sorted(warnings)


def normalize(kind, document):
    if kind not in CONTENT_MODELS:
        raise ContentError('未知创作类型')
    encoded = bounded_document(document)
    source_format = document.get('format', '')
    warnings = []
    if source_format:
        expected = CONTENT_FORMATS[kind]
        if source_format != expected:
            raise ContentError(f'不支持的格式版本：需要 {expected}。不会自动降级未知版本。')
        converted = document
    elif kind == 'worldbook':
        converted, source_format, warnings = convert_worldbook(document)
    elif kind == 'character' and 'name' in document:
        converted = {'format': 'ember.character/v1', 'metadata': metadata('character', document['name']),
                     'character': deepcopy(document)}
        source_format = 'ember-legacy-character'
        warnings = ['普通角色 JSON 已转换；运行时 ID、操控者和账号信息不属于角色卡，不能导入。']
    else:
        raise ContentError('缺少支持的 format 标识，请从标准模板开始')
    try:
        parsed = CONTENT_MODELS[kind].model_validate(converted)
    except ValidationError as exc:
        errors = [{'path': '.'.join(map(str, error['loc'])), 'message': error['msg']}
                  for error in exc.errors(include_input=False, include_url=False)[:30]]
        raise ContentError('创作文件不符合标准，请检查字段与长度限制', errors) from exc
    value = parsed.model_dump(mode='json', by_alias=True)
    if kind == 'worldbook':
        # Missing IDs get reproducible IDs. Re-importing the same book can merge safely.
        for index, entry in enumerate(value['world']['lore']):
            if not entry['id']:
                identity = json.dumps([index, entry['title'], entry['content']], ensure_ascii=False).encode()
                entry['id'] = 'entry-' + hashlib.sha256(identity).hexdigest()[:24]
        ids = [entry['id'] for entry in value['world']['lore']]
        if len(set(ids)) != len(ids):
            raise ContentError('转换后的条目 ID 重复，请先修正文件')
        try:
            value['world'] = WorldData.model_validate(value['world']).model_dump(mode='json')
        except ValidationError as exc:
            raise ContentError('补全条目 ID 后世界数据超过 384 KiB，请缩短内容') from exc
    if not value['metadata']['license']:
        warnings.append('未声明作品许可；分享或再发布前请确认作者授权。')
    bounded_document(value)
    return {'kind': kind, 'document': value, 'source_format': source_format or value['format'],
            'warnings': warnings, 'sha256': hashlib.sha256(encoded).hexdigest(),
            'summary': summarize(kind, value)}


def summarize(kind, value):
    if kind == 'worldbook':
        lore = value['world']['lore']
        return {'name': value['metadata']['name'], 'title': value['world']['title'], 'entries': len(lore),
                'rules': sum(entry['kind'] == 'rule' for entry in lore),
                'gm_only': sum(entry['visibility'] == 'gm' for entry in lore),
                'disabled': sum(not entry['enabled'] for entry in lore), 'rule_system': value['world']['rule_system']}
    if kind == 'character':
        char = value['character']
        return {'name': char['name'], 'archetype': char['archetype'], 'hp': char['hp'],
                'max_hp': char['max_hp'], 'rule_system': value['rule_system']}
    return {'name': value['metadata']['name'], 'modes': [mode for mode, palette in value['modes'].items() if palette]}


def merge_world(current, incoming):
    # Merge has deliberately narrow semantics: only entries are added/updated.
    # Existing premise, tone, rules and extensions are never silently replaced.
    merged = deepcopy(current)
    entries = {entry['id']: deepcopy(entry) for entry in merged['lore']}
    for entry in incoming['lore']:
        entries[entry['id']] = deepcopy(entry)
    merged['lore'] = list(entries.values())
    if len(merged['lore']) > 160:
        raise ContentError('合并后超过 160 个条目；请改用替换或先整理世界书')
    try:
        return WorldData.model_validate(merged).model_dump(mode='json')
    except ValidationError as exc:
        raise ContentError('合并后的世界书超出字段或 384 KiB 总量限制') from exc
