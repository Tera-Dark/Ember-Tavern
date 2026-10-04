"""Public rule catalog and typed, authoritative M3 rule commands."""
import secrets

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..db import append_event, connection
from ..runtime import (authorize_character, check_revision, finish, game_lock,
                       get_room_member, receipt, save_receipt, throttle)
from ..rules import adapter_catalog, engine_for
from ..schemas import (DndActionRequest, DndEncounterStart, DndRestRequest,
                       DndSheetUpdate, StrategyOrderRequest, StrategySettleRequest)
from ..state import load_state

router = APIRouter()


def _require_adapter(state, expected):
    engine = engine_for(state)
    if engine.id != expected:
        raise HTTPException(409, f'本房间锁定规则为 {engine.id}；该命令仅适用于 {expected}')
    return engine


def _check_branch(room, expected):
    if room['branch'] != expected:
        raise HTTPException(409, '时间线已变化，请刷新状态后重试；本次操作未提交')


@router.get('/api/rules')
def list_rule_adapters():
    return adapter_catalog()


@router.put('/api/rooms/{room_id}/rules/dnd5e/sheets/{character_id}')
async def update_dnd_sheet(room_id: str, character_id: str,
                           data: DndSheetUpdate, user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                _check_branch(room, data.branch)
                state = load_state(room['state_json'])
                engine = _require_adapter(state, 'dnd5e-srd-5.2.1/v1')
                sheet = data.model_dump(exclude={'expected_revision', 'request_key', 'branch'})
                result = engine.update_sheet(state, character_id, sheet)
                append_event(con, room_id, 'rules_state', result['text'], state, user,
                             character_id, result['payload'])
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.post('/api/rooms/{room_id}/rules/dnd5e/encounters')
async def start_dnd_encounter(room_id: str, data: DndEncounterStart,
                              user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                _check_branch(room, data.branch)
                state = load_state(room['state_json'])
                engine = _require_adapter(state, 'dnd5e-srd-5.2.1/v1')
                setup = data.model_dump(exclude={'expected_revision', 'request_key', 'branch'})
                result = engine.start_encounter(state, setup, secrets.randbelow)
                append_event(con, room_id, 'rules_action', result['text'], state, user,
                             payload=result['payload'])
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.post('/api/rooms/{room_id}/rules/dnd5e/actions')
async def dnd_action(room_id: str, data: DndActionRequest, user=Depends(current_user)):
    throttle(('dnd-action', user['id']), 30, 60)
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                _check_branch(room, data.branch)
                state = load_state(room['state_json'])
                engine = _require_adapter(state, 'dnd5e-srd-5.2.1/v1')
                authorize_character(con, room, user, state, data.character_id)
                action = data.model_dump(include={'character_id', 'action'})
                result = engine.take_turn(state, action, secrets.randbelow)
                append_event(con, room_id, 'rules_action', result['text'], state, user,
                             data.character_id, result['payload'])
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.post('/api/rooms/{room_id}/rules/dnd5e/rest')
async def dnd_rest(room_id: str, data: DndRestRequest, user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                _check_branch(room, data.branch)
                state = load_state(room['state_json'])
                engine = _require_adapter(state, 'dnd5e-srd-5.2.1/v1')
                authorize_character(con, room, user, state, data.character_id)
                rest = data.model_dump(include={'character_id', 'kind'})
                result = engine.rest(state, rest, secrets.randbelow)
                append_event(con, room_id, 'rules_action', result['text'], state, user,
                             data.character_id, result['payload'])
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.post('/api/rooms/{room_id}/rules/dnd5e/encounters/end')
async def end_dnd_encounter(room_id: str, data: StrategySettleRequest,
                            user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                _check_branch(room, data.branch)
                state = load_state(room['state_json'])
                engine = _require_adapter(state, 'dnd5e-srd-5.2.1/v1')
                result = engine.end_encounter(state)
                append_event(con, room_id, 'rules_action', result['text'], state, user,
                             payload=result['payload'])
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.post('/api/rooms/{room_id}/rules/strategy/orders')
async def plan_strategy_order(room_id: str, data: StrategyOrderRequest,
                              user=Depends(current_user)):
    throttle(('strategy-order', user['id']), 30, 60)
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                _check_branch(room, data.branch)
                state = load_state(room['state_json'])
                engine = _require_adapter(state, 'ember-coop-settlement/v1')
                order = data.model_dump(exclude={'expected_revision', 'request_key', 'branch'})
                member_count = con.execute('SELECT COUNT(*) FROM members WHERE room_id=?',
                                           (room_id,)).fetchone()[0]
                result = engine.plan_order(state, order, user, member_count)
                append_event(con, room_id, 'rules_state', result['text'], state, user,
                             payload=result['payload'])
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.post('/api/rooms/{room_id}/rules/strategy/settle')
async def settle_strategy_turn(room_id: str, data: StrategySettleRequest,
                               user=Depends(current_user)):
    async with game_lock(room_id):
        duplicate = False
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                _check_branch(room, data.branch)
                state = load_state(room['state_json'])
                engine = _require_adapter(state, 'ember-coop-settlement/v1')
                result = engine.settle_turn(state, secrets.randbelow)
                append_event(con, room_id, 'rules_action', result['text'], state, user,
                             payload=result['payload'])
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)
