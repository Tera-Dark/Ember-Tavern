"""Creator contracts and room content commands. Preview never writes game state."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field

from ..auth import current_user
from ..config import ROOT
from ..contracts.common import Contract
from ..contracts.content import CONTENT_MODELS, CharacterData, WorldData
from ..contracts.catalog import schema_for, CONTENT_FORMATS
from ..contracts.resources import CORE_CAPABILITIES
from ..db import append_event, connection, dump, now, uid
from ..domain import character
from ..retrieval import model_context
from ..rules import ENGINES, engine_for
from ..version import HOST_VERSION
from ..runtime import check_revision, finish, game_lock, get_room_member, receipt, save_receipt, throttle
from ..schemas import Revision
from ..state import load_state
from .imports import ContentError, MAX_CONTENT_BYTES, merge_world, metadata, normalize

router = APIRouter()
Kind = Literal['worldbook', 'character', 'theme']


class Preview(Contract):
    kind: Kind
    document: dict


class RoomPreview(Preview):
    mode: Literal['merge', 'replace'] = 'merge'


class Import(Revision, RoomPreview):
    pass


def checked(kind, document):
    try:
        return normalize(kind, document)
    except ContentError as exc:
        raise HTTPException(422, {'message': str(exc), 'errors': exc.errors}) from exc


@router.get('/api/creators')
def creator_catalog():
    return {'api_version': 1, 'host_version':HOST_VERSION, 'max_bytes': MAX_CONTENT_BYTES,
            'contracts': [{'kind': kind, 'format': CONTENT_FORMATS[kind],
                           'schema_url': f'/api/contracts/{kind}', 'template_url': f'/api/creators/templates/{kind}'}
                          for kind, model in CONTENT_MODELS.items()],
            'plugin_schema_url': '/api/contracts/plugin',
            'core_resources': [{'name':name,'capability':cap,'owner':'@core'} for name,cap in CORE_CAPABILITIES.items()],
            'rule_systems': [engine.contract() for engine in ENGINES.values()],
            'guide_url': '/api/creators/guide', 'cli': 'python scripts/creator.py'}


@router.get('/api/contracts/{kind}')
def schema(kind: str):
    try:
        return schema_for(kind)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get('/api/creators/templates/{kind}')
def template(kind: str):
    if kind not in CONTENT_MODELS:
        raise HTTPException(404, '不存在的创作模板')
    path = ROOT / 'templates' / kind / f'{kind}.json'
    return json.loads(path.read_text(encoding='utf-8'))


@router.get('/api/creators/guide')
def creator_guide():
    path = ROOT / 'docs/CREATOR_GUIDE.md'
    return {'text': path.read_text(encoding='utf-8') if path.exists() else '创作指南正在整理。'}


@router.post('/api/content/validate')
def validate_content(data: Preview, user=Depends(current_user)):
    throttle(('content-validate', user['id']), 60, 60)
    return checked(data.kind, data.document)


def import_effects(state, kind, document, mode):
    if kind == 'theme':
        raise HTTPException(422, '主题是个人界面偏好，请校验后在本机应用，不写入剧情')
    if kind == 'character':
        if mode != 'merge':
            raise HTTPException(422, '角色卡只能添加新角色，不能覆盖现有角色或权限')
        if len(state['characters']) >= 12:
            raise HTTPException(422, '每个房间最多 12 个角色')
        return {'operation': 'add-character', 'added': 1, 'unassigned': True}
    existing = {entry['id'] for entry in state['world']['lore']}
    incoming = {entry['id'] for entry in document['world']['lore']}
    try:
        if mode == 'merge':
            merge_world(state['world'], document['world'])
    except ContentError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'operation': mode, 'added': len(incoming - existing), 'updated': len(incoming & existing),
            'removed': len(existing - incoming) if mode == 'replace' else 0,
            'keeps_world_settings': mode == 'merge'}


@router.post('/api/rooms/{room_id}/content/preview')
def preview_room(room_id: str, data: RoomPreview, user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con, room_id, user, True)
        state = load_state(room['state_json'])
    parsed = checked(data.kind, data.document)
    parsed['effects'] = import_effects(state, data.kind, parsed['document'], data.mode)
    parsed['revision'] = room['revision']
    parsed['branch'] = room['branch']
    return parsed


@router.post('/api/rooms/{room_id}/content/import')
async def import_room(room_id: str, data: Import, user=Depends(current_user)):
    throttle(('content-import', user['id']), 20, 60)
    # Authorization before interpreting a potentially private book.
    with connection() as con:
        get_room_member(con, room_id, user, True)
    parsed = checked(data.kind, data.document)
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            if not receipt(con, room_id, user, data.request_key):
                check_revision(room, data.expected_revision)
                state = load_state(room['state_json'])
                effects = import_effects(state, data.kind, parsed['document'], data.mode)
                char_id = None
                if data.kind == 'worldbook':
                    incoming = parsed['document']['world']
                    state['world'] = merge_world(state['world'], incoming) if data.mode == 'merge' else incoming
                    state['rules'] = engine_for(state).description
                    message = f"房主{'合并' if data.mode == 'merge' else '替换'}了世界书。新增 {effects['added']}，更新 {effects['updated']}，移除 {effects['removed']} 个条目。"
                    event_type = 'world'
                else:
                    char_id = uid()
                    char = parsed['document']['character'] | {'id': char_id}
                    state['characters'].append(char)
                    message = f"房主导入了角色「{char['name']}」，等待分配操控者。"
                    event_type = 'character'
                provenance = {'kind': data.kind, 'metadata': parsed['document']['metadata'],
                              'sha256': parsed['sha256'], 'source_format': parsed['source_format'], 'applied_at': now()}
                sources = state.setdefault('_content', {}).setdefault('sources', [])
                sources.append(provenance)
                state['_content']['sources'] = sources[-20:]
                append_event(con, room_id, event_type, message, state, user, char_id,
                             {'label': '标准创作包导入', 'kind': data.kind, 'mode': data.mode})
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.get('/api/rooms/{room_id}/content/worldbook/export')
def export_worldbook(room_id: str, user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con, room_id, user, True)
        state = load_state(room['state_json'])
    document = {'format': 'ember.worldbook/v1', 'metadata': metadata('worldbook', state['world']['title']),
                'world': WorldData.model_validate(state['world']).model_dump(mode='json')}
    document['metadata']['id'] = f'room-world-{room_id[:8]}'
    document['metadata']['description'] = '房间世界书导出草稿，可能含主持秘密。多来源署名与许可请作者核对补充，分享前清理。'
    return download(document, f'worldbook-{room_id[:8]}.json')


@router.get('/api/rooms/{room_id}/content/characters/{character_id}/export')
def export_character(room_id: str, character_id: str, user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con, room_id, user, True)
        state = load_state(room['state_json'])
    char = {key: value for key, value in character(state, character_id).items() if key in CharacterData.model_fields}
    document = {'format': 'ember.character/v1', 'metadata': metadata('character', char['name']),
                'rule_system': engine_for(state).id, 'character': CharacterData.model_validate(char).model_dump(mode='json')}
    document['metadata']['id'] = f'character-{character_id[:8]}'
    document['metadata']['description'] = '房间角色导出草稿，含主持备注。分享前清理，并核对原作者署名与许可。'
    return download(document, f'character-{character_id[:8]}.json')


@router.get('/api/rooms/{room_id}/gm/context-preview')
def context_preview(room_id: str, q: str = '', user=Depends(current_user)):
    if len(q) > 2000:
        raise HTTPException(422, '上下文测试文本最多 2000 字符')
    with connection() as con:
        room = get_room_member(con, room_id, user, True)
        state = load_state(room['state_json'])
    return {'revision': room['revision'], 'branch': room['branch'], 'context': model_context(room_id, state, q),
            'notice': '仅预览，不调用外部模型；字符预算不是 token 数或费用承诺。'}


def download(document, filename):
    return Response(json.dumps(document, ensure_ascii=False, separators=(',', ':')), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})
