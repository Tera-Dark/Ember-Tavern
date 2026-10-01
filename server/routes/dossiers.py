from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from ..contracts.content import WorldData
from ..auth import current_user
from ..db import connection, append_event, uid
from ..schemas import CharacterInput, Assign, Revision, WorldUpdate
from ..domain import character
from ..rules import engine_for
from ..state import load_state
from ..runtime import game_lock, get_room_member, check_revision, receipt, save_receipt, finish

router = APIRouter()


@router.post('/api/rooms/{room_id}/characters')
async def add_character(room_id:str,data:CharacterInput,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = load_state(room['state_json'])
                if len(state['characters']) >= 12:
                    raise HTTPException(422,'首版每房间最多12个角色')
                char = data.model_dump(exclude={'expected_revision','request_key'}) | {'id':uid()}
                state['characters'].append(char)
                append_event(con,room_id,'character',f"房主创建了角色「{char['name']}」。",state,user,char['id'])
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@router.put('/api/rooms/{room_id}/characters/{character_id}')
async def update_character(room_id:str,character_id:str,data:CharacterInput,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = load_state(room['state_json'])
                char = character(state,character_id)
                if state['pending_check'] and state['pending_check']['character_id'] == character_id:
                    raise HTTPException(409,'该角色正在等待检定，先完成或取消检定再修改属性')
                char.update(data.model_dump(exclude={'expected_revision','request_key'}))
                append_event(con,room_id,'character',f"房主更新了「{char['name']}」的角色记录。",state,user,character_id)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@router.delete('/api/rooms/{room_id}/characters/{character_id}')
async def delete_character(room_id:str,character_id:str,data:Revision,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = load_state(room['state_json'])
                char = character(state,character_id)
                if len(state['characters']) <= 1:
                    raise HTTPException(422,'请至少保留一个角色')
                if (state['pending_check'] and state['pending_check']['character_id']==character_id) or (state['awaiting_gm'] and state['continuation'] and state['continuation']['character_id']==character_id):
                    raise HTTPException(409,'请先完成该角色的主持或检定，再移除角色')
                state['characters'] = [c for c in state['characters'] if c['id']!=character_id]
                con.execute('DELETE FROM assignments WHERE room_id=? AND character_id=?',(room_id,character_id))
                append_event(con,room_id,'character',f"房主移除了角色「{char['name']}」。",state,user,character_id)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@router.post('/api/rooms/{room_id}/characters/{character_id}/assign')
async def assign_character(room_id:str,character_id:str,data:Assign,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = load_state(room['state_json'])
                char = character(state,character_id)
                name = '未分配'
                if data.user_id:
                    row = con.execute('SELECT u.display_name FROM users u JOIN members m ON u.id=m.user_id WHERE m.room_id=? AND u.id=?',(room_id,data.user_id)).fetchone()
                    if not row:
                        raise HTTPException(422,'只能分配给当前房间成员')
                    name = row['display_name']
                    con.execute('DELETE FROM assignments WHERE room_id=? AND user_id=?',(room_id,data.user_id))
                con.execute('DELETE FROM assignments WHERE room_id=? AND character_id=?',(room_id,character_id))
                if data.user_id:
                    con.execute('INSERT INTO assignments VALUES (?,?,?)',(room_id,character_id,data.user_id))
                append_event(con,room_id,'system',f"「{char['name']}」的操控者已设为：{name}。",state,user)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@router.put('/api/rooms/{room_id}/world')
async def update_world(room_id:str,data:WorldUpdate,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                state = load_state(room['state_json'])
                lore = [item.model_dump() | {'id':item.id or uid()} for item in data.lore]
                if len({x['id'] for x in lore}) != len(lore):
                    raise HTTPException(422,'世界书条目ID不能重复')
                world = data.model_dump(exclude={'expected_revision', 'request_key'}) | {'lore': lore}
                try:
                    state['world'] = WorldData.model_validate(world).model_dump(mode='json')
                except ValidationError as exc:
                    raise HTTPException(422, '补全条目 ID 后世界数据超过 384 KiB，请缩短内容') from exc
                state['rules'] = engine_for(state).description
                append_event(con,room_id,'world','房主更新了世界设定与世界书。',state,user)
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)
