"""Versioned campaign-state, action-round and provenance-backed memory commands."""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..campaign_state import ledger_view, set_action_mode, settle_action_round
from ..config import settings
from ..db import append_event, connection, now
from ..runtime import (check_revision, finish, game_lock, get_room_member, hub,
                       receipt, save_receipt)
from ..schemas import (ActionModeUpdate, ActionRoundSettle, CampaignStateUpdate,
                       MemorySummaryUpdate)
from ..state import load_state

router = APIRouter()


def check_branch(room, expected):
    if room['branch'] != expected:
        raise HTTPException(409, '时间线已变化，请刷新状态后重试；本次操作未提交')


@router.get('/api/rooms/{room_id}/campaign-state')
def read_campaign_state(room_id: str, user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con, room_id, user)
        state = load_state(room['state_json'])
    return {'format': 'ember.campaign-state/v1', 'revision': room['revision'],
            'branch': room['branch'], 'ledger': ledger_view(state, room['owner_id'] == user['id'])}


@router.put('/api/rooms/{room_id}/campaign-state')
async def update_campaign_state(room_id: str, data: CampaignStateUpdate, user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                check_branch(room, data.branch)
                state = load_state(room['state_json'])
                replacement = data.ledger.model_dump(mode='json')
                existing = ledger_view(state, True)
                if existing != replacement:
                    state['_campaign_state'] = replacement
                    changed = []
                    for key in ('quests', 'npcs', 'resources'):
                        before = {item['id']: item for item in existing.get(key, [])}
                        after = {item['id']: item for item in replacement.get(key, [])}
                        changed.extend(key + ':' + identity for identity in sorted(before.keys() | after.keys())
                                       if before.get(identity) != after.get(identity))
                    append_event(con, room_id, 'campaign_state', '房主更新了战役状态记录。', state, user,
                                 payload={'changed_ids': changed[:120], 'format': replacement['format']})
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.put('/api/rooms/{room_id}/action-mode')
async def change_action_mode(room_id: str, data: ActionModeUpdate, user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                check_branch(room, data.branch)
                state = load_state(room['state_json'])
                previous = state.get('_action_mode', 'free')
                set_action_mode(state, room, con, data.mode)
                if previous != data.mode or data.mode == 'round':
                    label = '小队轮次收集' if data.mode == 'round' else '自由行动'
                    append_event(con, room_id, 'action_round', f'房主将行动模式切换为「{label}」。', state, user,
                                 payload={'mode': data.mode, 'branch': room['branch']})
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.post('/api/rooms/{room_id}/action-round/settle')
async def settle_round(room_id: str, data: ActionRoundSettle, user=Depends(current_user)):
    async with game_lock(room_id):
        duplicate = False
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                check_branch(room, data.branch)
                state = load_state(room['state_json'])
                _, submitted, required, missing = settle_action_round(state, room)
                round_no = state['_action_round']['number']
                summary = f'第 {round_no} 轮行动已汇总：{submitted}/{required} 个角色已提交。'
                if missing:
                    summary += '房主选择在仍有人未提交时提前结算。'
                append_event(con, room_id, 'action_round', summary, state, user,
                             payload={'round': round_no, 'submitted': submitted, 'required': required,
                                      'missing_count': len(missing)})
                save_receipt(con, room_id, user, data.request_key)
        if not duplicate:
            await hub.broadcast(room_id)
            # Keep the room lock through the existing host decision pipeline, as
            # the ordinary free-action endpoint does.
            from ..app import complete_gm
            await complete_gm(room_id)
    return await finish(room_id, user)


@router.get('/api/rooms/{room_id}/memory')
def read_memory(room_id: str, user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con, room_id, user, True)
        state = load_state(room['state_json'])
        rows = con.execute('''SELECT id,seq,type,actor_name,character_id,text,created_at
                              FROM events WHERE room_id=? AND active=1 AND type!='memory_summary'
                              ORDER BY seq DESC LIMIT 200''', (room_id,)).fetchall()
    summary = state.get('_memory_summary')
    if summary and summary.get('branch') != room['branch']:
        summary = None
    return {'branch': room['branch'], 'revision': room['revision'],
            'summary': summary,
            'sources': [dict(row) for row in rows],
            'summary_context_budget_chars': max(0, min(8000, settings.memory_summary_context_chars)),
            'source_limit': 50,
            'notice': '摘要由房主编辑并绑定当前有效事件；它是有来源的辅助记忆，不是权威事实。'}


@router.put('/api/rooms/{room_id}/memory/summary')
async def update_memory_summary(room_id: str, data: MemorySummaryUpdate, user=Depends(current_user)):
    if len(data.source_event_ids) != len(set(data.source_event_ids)):
        raise HTTPException(422, '记忆摘要来源不能重复')
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            duplicate = receipt(con, room_id, user, data.request_key)
            if not duplicate:
                check_revision(room, data.expected_revision)
                check_branch(room, data.branch)
                state = load_state(room['state_json'])
                text = data.text.strip()
                if text:
                    if not data.source_event_ids:
                        raise HTTPException(422, '非空记忆摘要至少需要绑定一条有效时间线事件')
                    if len(data.source_event_ids) > 50:
                        raise HTTPException(422, '一次最多绑定 50 个来源事件')
                    placeholders = ','.join('?' for _ in data.source_event_ids)
                    rows = con.execute(f'''SELECT id,seq,type FROM events
                                           WHERE room_id=? AND active=1 AND type!='memory_summary'
                                           AND id IN ({placeholders})''', (room_id, *data.source_event_ids)).fetchall()
                    if len(rows) != len(data.source_event_ids):
                        raise HTTPException(409, '摘要来源含其他房间或已封存事件；请重新选择当前时间线来源')
                    seq_by_id = {row['id']: row['seq'] for row in rows}
                    source_ids = sorted(data.source_event_ids, key=lambda identity: seq_by_id[identity])
                    state['_memory_summary'] = {'text': text, 'source_event_ids': source_ids,
                                                'source_seq_max': max(seq_by_id.values()),
                                                'branch': room['branch'], 'updated_at': now()}
                    event_text = f'房主更新了主持记忆摘要，绑定 {len(source_ids)} 条来源事件。'
                    payload = {'source_event_ids': source_ids, 'source_count': len(source_ids),
                               'branch': room['branch']}
                else:
                    if data.source_event_ids:
                        raise HTTPException(422, '清除摘要时来源列表必须为空')
                    state['_memory_summary'] = None
                    event_text = '房主清除了主持记忆摘要。'
                    payload = {'source_count': 0, 'branch': room['branch']}
                append_event(con, room_id, 'memory_summary', event_text, state, user, payload=payload)
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)
