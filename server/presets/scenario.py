"""Small deterministic scene/ clue workflow. AI narrates, only host commands advance."""
from copy import deepcopy
from fastapi import HTTPException


def scenario_state(state):
    value=state.get('_scenario')
    if not value: raise HTTPException(422,'此房间没有结构化剧本；旧世界仍可自由游玩')
    return value


def scene_for(value):
    return next(scene for scene in value['document']['scenes'] if scene['id']==value['current_scene'])


def _rule_status_ready(state,edge):
    required=edge.get('requires_rule_status')
    if required is None: return True
    return (state.get('_rule_state') or {}).get('status')==required


def view(state,include_gm=False):
    value=state.get('_scenario')
    if not value: return None
    document=value['document'];scene=scene_for(value)
    revealed=set(value['revealed_clues'])
    clues={clue['id']:clue for clue in document['clues']}
    lock=state['_preset_lock']
    result={'title':document['metadata']['name'],'version':document['metadata']['version'],
            'objective':document['objective'],'current_scene':scene['id'],'scene_title':scene['title'],
            'brief':scene['text'],'completed':scene['kind']=='ending',
            'profile':deepcopy(lock['profile']),
            'preset':{'id':lock['preset']['id'],'name':lock['preset']['name'],'version':lock['preset']['version'],
                      'package_hash':lock['package_hash']},
            'revealed_clues':[{'id':clue['id'],'title':clue['title'],'text':clue['text']} for clue in document['clues'] if clue['id'] in revealed]}
    if include_gm:
        result['gm_notes']=scene['gm_notes']
        result['clues']=[{**deepcopy(clues[cid]),'revealed':cid in revealed} for cid in scene['clues']]
        result['transitions']=[{**deepcopy(edge),
                                'rule_status_ready':_rule_status_ready(state,edge),
                                'ready':set(edge['requires_clues'])<=revealed and _rule_status_ready(state,edge)}
                               for edge in scene['transitions']]
        result['lock']=deepcopy(lock)
    return result


def ensure_idle(state):
    if state.get('pending_check') or state.get('awaiting_gm'):
        raise HTTPException(409,'请先完成检定 / 主持，或由房主取消 / 补述，再推进剧本')


def reveal(state,scene_id,clue_id):
    value=scenario_state(state);scene=scene_for(value)
    if scene['id']!=scene_id: raise HTTPException(409,'当前场景已变化，请刷新；未揭示线索')
    ensure_idle(state)
    if clue_id not in scene['clues']: raise HTTPException(422,'该线索不属于当前场景，不允许跳过剧情读取未来秘密')
    if clue_id in value['revealed_clues']: return None
    clue=next(clue for clue in value['document']['clues'] if clue['id']==clue_id)
    value['revealed_clues'].append(clue_id)
    fact=clue['title']+'：'+clue['text']
    if fact not in state['facts']: state['facts'].append(fact)
    state['facts']=state['facts'][-100:]
    return '揭示线索「'+clue['title']+'」：'+clue['text']


def advance(state,scene_id,transition_id):
    value=scenario_state(state);scene=scene_for(value)
    if scene['id']!=scene_id: raise HTTPException(409,'当前场景已变化，请刷新；未推进剧情')
    ensure_idle(state)
    edge=next((edge for edge in scene['transitions'] if edge['id']==transition_id),None)
    if not edge: raise HTTPException(422,'只能使用当前场景中已声明的推进路线')
    if not set(edge['requires_clues'])<=set(value['revealed_clues']):
        raise HTTPException(422,'仍缺少这条路线要求的已揭示线索；文字叙事不能绕过前置条件')
    required_status=edge.get('requires_rule_status')
    if required_status and not _rule_status_ready(state,edge):
        raise HTTPException(409,f'此结局要求服务端规则状态为 {required_status}；当前规则目标尚未到达该状态')
    target=next(scene for scene in value['document']['scenes'] if scene['id']==edge['target'])
    value['current_scene']=target['id']
    state['scene']={'title':target['title'],'text':target['text']}
    state['continuation']=None;state['gm_error']=None
    return ('冒险收束：' if target['kind']=='ending' else '进入场景：')+target['title']+'\n\n'+target['text']


def model_brief(state):
    if not state.get('_scenario'): return None
    value=view(state,True)
    # Only current scene + current available clues, not the entire future graph.
    return {key:value[key] for key in ('objective','current_scene','scene_title','completed','profile','gm_notes','clues','transitions')}
