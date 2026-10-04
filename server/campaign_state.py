"""Core campaign ledger, action-round collection, and safe public projections."""
from copy import deepcopy

from fastapi import HTTPException

from .db import uid, now


def empty_ledger():
    return {'format': 'ember.campaign-state/v1', 'quests': [], 'npcs': [], 'resources': []}


def ledger_for(state):
    return state.setdefault('_campaign_state', empty_ledger())


def ledger_view(state, include_gm=False):
    value = deepcopy(ledger_for(state))
    if not include_gm:
        for key in ('quests', 'npcs', 'resources'):
            value[key] = [item for item in value.get(key, []) if item.get('visibility', 'public') == 'public']
    return value


def ledger_context(state, max_each=12):
    """Bound ledger material before it competes for the model's character budget."""
    value = ledger_for(state)
    quests = [q for q in value.get('quests', []) if q.get('status') in ('active', 'proposed', 'paused')]
    quests += [q for q in value.get('quests', []) if q.get('status') in ('completed', 'failed')]
    npcs = list(value.get('npcs', []))
    resources = list(value.get('resources', []))
    result = {'format': value.get('format', 'ember.campaign-state/v1'),
              'quests': [], 'npcs': [], 'resources': []}
    for item in quests[:max_each]:
        result['quests'].append({**{k: item.get(k) for k in ('id', 'title', 'status', 'visibility')},
                                 'summary': item.get('summary', '')[:160]})
    for item in npcs[:max_each]:
        result['npcs'].append({**{k: item.get(k) for k in ('id', 'name', 'role', 'status', 'relationship', 'visibility')},
                               'summary': item.get('summary', '')[:120]})
    for item in resources[:max_each * 2]:
        result['resources'].append({k: item.get(k) for k in ('id', 'name', 'value', 'minimum', 'maximum', 'unit', 'visibility')})
    return result


def _new_round(state, room, con):
    required = []
    rows = con.execute('''SELECT a.character_id,a.user_id,u.display_name
                          FROM assignments a JOIN users u ON u.id=a.user_id
                          WHERE a.room_id=? ORDER BY a.character_id''', (room['id'],)).fetchall()
    character_by_id = {char['id']: char for char in state.get('characters', [])}
    for row in rows:
        char = character_by_id.get(row['character_id'])
        if char:
            required.append({'character_id': char['id'], 'character_name': char['name'],
                             'user_id': row['user_id'], 'display_name': row['display_name']})
    value = {'id': uid(), 'branch': room['branch'], 'number': state.get('turn', 0) + 1,
             'status': 'collecting', 'required': required, 'submissions': []}
    state['_action_round'] = value
    return value


def action_round_view(state):
    value = state.get('_action_round')
    if not value:
        return None
    result = deepcopy(value)
    submitted = {item['character_id'] for item in value.get('submissions', [])}
    for seat in result.get('required', []):
        seat['submitted'] = seat['character_id'] in submitted
    result['submitted_count'] = len(submitted)
    result['required_count'] = len(result.get('required', []))
    result['ready'] = bool(result.get('required')) and submitted.issuperset(
        seat['character_id'] for seat in result.get('required', []))
    result['missing_character_ids'] = [seat['character_id'] for seat in result.get('required', [])
                                       if seat['character_id'] not in submitted]
    return result


def set_action_mode(state, room, con, mode):
    if state.get('pending_check') or state.get('awaiting_gm'):
        raise HTTPException(409, '请先完成当前检定或主持，再切换行动模式')
    current = state.get('_action_round')
    if current and current.get('status') == 'collecting' and current.get('submissions'):
        raise HTTPException(409, '本轮已有行动；请先结算后再切换模式')
    state['_action_mode'] = mode
    if mode == 'round':
        _new_round(state, room, con)
    else:
        state['_action_round'] = None


def collect_action(state, room, con, user, character, text):
    if state.get('pending_check') or state.get('awaiting_gm'):
        raise HTTPException(409, '请先完成待处理检定或主持')
    current = state.get('_action_round')
    if not current or current.get('status') != 'collecting' or current.get('branch') != room['branch']:
        current = _new_round(state, room, con)
    seat = next((item for item in current['required'] if item['character_id'] == character['id']), None)
    if seat is None:
        if room['owner_id'] != user['id']:
            raise HTTPException(409, '本轮参与角色已锁定；请房主在下一轮重新分配或开始新轮')
        seat = {'character_id': character['id'], 'character_name': character['name'],
                'user_id': user['id'], 'display_name': user['display_name']}
        current['required'].append(seat)
    elif seat['user_id'] != user['id']:
        raise HTTPException(403, '本轮角色已锁定给另一位参与者')
    if any(item['character_id'] == character['id'] for item in current['submissions']):
        raise HTTPException(409, '该角色已经提交本轮行动；每轮每个角色只能提交一次')
    current['submissions'].append({'character_id': character['id'], 'character_name': character['name'],
                                   'user_id': user['id'], 'actor_name': user['display_name'],
                                   'text': text, 'submitted_at': now()})
    return current


def settle_action_round(state, room):
    current = state.get('_action_round')
    if state.get('_action_mode') != 'round' or not current:
        raise HTTPException(422, '当前没有待结算的行动轮次')
    if current.get('branch') != room['branch']:
        raise HTTPException(409, '行动轮次属于旧时间线，请刷新房间后重试')
    if current.get('status') != 'collecting':
        raise HTTPException(409, '本轮已在结算或已经完成')
    if not current.get('submissions'):
        raise HTTPException(422, '至少需要一位参与者提交行动才能结算')
    missing = [seat['character_name'] for seat in current['required']
               if seat['character_id'] not in {item['character_id'] for item in current['submissions']}]
    text = '\n'.join(f"{item['character_name']}（{item['actor_name']}）：{item['text']}"
                      for item in current['submissions'])
    current['status'] = 'resolving'
    state['turn'] = state.get('turn', 0) + 1
    state['awaiting_gm'] = True
    state['gm_error'] = None
    first = current['submissions'][0]
    state['continuation'] = {'phase': 'action', 'text': text, 'character_id': first['character_id'],
                             'action_mode': 'round', 'round_id': current['id'],
                             'participants': [item['character_id'] for item in current['submissions']]}
    return text, len(current['submissions']), len(current['required']), missing
