"""Preset authoring/library and new-room commands; no code installation endpoint."""
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field
from ..auth import current_user, named_guest
from ..contracts.common import Contract
from ..contracts.presets import SHA256, LOCAL_ID
from ..db import connection, append_event
from ..config import ROOT
from ..plugin_runtime.manager import manager
from ..room_service import create_preset_room
from ..runtime import (pack_room, throttle, game_lock, get_room_member, check_revision, receipt, save_receipt, finish)
from ..schemas import Revision
from ..state import load_state
from .codec import decode_input, PresetError, archive_bytes
from .library import put_package, get_package, compatibility, catalog, authorize_package
from . import scenario

router=APIRouter()


class PackageInput(Contract):
    archive_base64: str | None = Field(default=None,max_length=1398104)
    document: dict | None = None


class PackageImport(PackageInput):
    expected_hash: SHA256
    confirm_data_only: Literal[True]


class PresetRoomCreate(Contract):
    title: str = Field(min_length=1,max_length=60)
    package_hash: SHA256
    ai_mode: Literal['demo','single','live'] = 'demo'
    host_plays: bool = True
    request_key: str = Field(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')


class Reveal(Revision):
    scene_id: LOCAL_ID
    clue_id: LOCAL_ID


class Advance(Revision):
    scene_id: LOCAL_ID
    transition_id: LOCAL_ID


def author(user):
    if user['guest'] or named_guest(user): raise HTTPException(403,'请用正式房主账号管理本机预设库；受邀同伴不能安装作品')


def checked(data):
    try: return decode_input(data.archive_base64,data.document)
    except (PresetError,ValueError,RecursionError) as exc: raise HTTPException(422,str(exc)) from exc


@router.get('/api/presets/guide')
def author_guide():
    path=ROOT/'docs/PRESET_AUTHORING.md'
    return {'text':path.read_text(encoding='utf-8') if path.exists() else '玩法预设作者指南正在整理。'}


@router.get('/api/presets')
def list_presets(user=Depends(current_user)):
    return {'format':'ember.preset-catalog/v1','entries':catalog(manager,user),
            'notice':'作品是数据组合，不是代码安装或完整规则认证；新版本不会自动更新旧房间。'}


@router.post('/api/presets/preview')
def preview_preset(data:PackageInput,user=Depends(current_user)):
    author(user);throttle(('preset-preview',user['id']),30,60)
    package=checked(data)
    return {'valid':True,'package_hash':package.package_hash,'summary':package.summary(),
            'compatibility':compatibility(package,manager),'code_executed':False,'writes':False}


@router.post('/api/presets/import')
def import_preset(data:PackageImport,user=Depends(current_user)):
    author(user);throttle(('preset-import',user['id']),12,60)
    package=checked(data)
    if package.package_hash!=data.expected_hash: raise HTTPException(409,'包与已确认预览不一致；未写入本机库')
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        added=put_package(con,package,'local',user['id'])
    return {'imported':True,'added':added,'package_hash':package.package_hash,'summary':package.summary(),
            'compatibility':compatibility(package,manager),'code_executed':False,
            'notice':'只导入数据；依赖代码必须另行受信任安装，导入不会授予能力或运行 Python。'}


@router.get('/api/presets/{package_hash}/export')
def export_preset(package_hash:str,user=Depends(current_user)):
    author(user)
    if not re.fullmatch(r'[a-f0-9]{64}',package_hash): raise HTTPException(422,'包散列无效')
    with connection() as con:
        authorize_package(con,package_hash,user)
        package=get_package(con,package_hash)
    return Response(archive_bytes(package),media_type='application/zip',
                    headers={'Content-Disposition':'attachment; filename="'+package.manifest['metadata']['id']+'-'+package.manifest['metadata']['version']+'.zip"'})


@router.post('/api/rooms/from-preset',status_code=201)
def room_from_preset(data:PresetRoomCreate,user=Depends(current_user)):
    if named_guest(user): raise HTTPException(403,'受邀同伴不能创建房间，请联系房主')
    return pack_room(create_preset_room(user,data),user)


@router.get('/api/rooms/{room_id}/campaign')
def read_campaign(room_id:str,user=Depends(current_user)):
    with connection() as con:
        room=get_room_member(con,room_id,user)
        state=load_state(room['state_json'])
    return {'revision':room['revision'],'branch':room['branch'],'campaign':scenario.view(state,room['owner_id']==user['id'])}


async def campaign_command(room_id,data,user,operation):
    async with game_lock(room_id):
        with connection() as con:
            room=get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state=load_state(room['state_json'])
                text=operation(state)
                if text:
                    append_event(con,room_id,'system',text,state,user,payload={'label':'结构化剧本 · 房主确认'})
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@router.post('/api/rooms/{room_id}/campaign/reveal')
async def reveal_clue(room_id:str,data:Reveal,user=Depends(current_user)):
    return await campaign_command(room_id,data,user,lambda state:scenario.reveal(state,data.scene_id,data.clue_id))


@router.post('/api/rooms/{room_id}/campaign/advance')
async def advance_scene(room_id:str,data:Advance,user=Depends(current_user)):
    return await campaign_command(room_id,data,user,lambda state:scenario.advance(state,data.scene_id,data.transition_id))
