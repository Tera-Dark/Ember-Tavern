"""Room-scoped lexical retrieval. Active timeline only; intentionally not labelled vector RAG."""
import re
import json
import math
from .db import connection


def terms(text):
    lowered = text.lower()
    tokens = set(re.findall(r'[a-z0-9_]{2,}', lowered))
    for block in re.findall(r'[\u4e00-\u9fff]+', lowered):
        if len(block) == 1:
            tokens.add(block)
        else:
            tokens.update(block[i:i+2] for i in range(len(block)-1))
    return tokens


def retrieve(room_id, state, query, limit=8):
    query_terms = terms(query)
    candidates = []
    for item in state['world']['lore']:
        candidates.append({'id':item['id'], 'source':'lore', 'title':item['title'], 'text':item['content'], 'tags':item.get('tags',''), 'seq':0})
    for index, fact in enumerate(state['facts']):
        candidates.append({'id':f'fact-{index}', 'source':'fact', 'title':'已确认事实', 'text':fact, 'seq':0, 'tags':''})
    with connection() as con:
        rows = con.execute("SELECT id,seq,type,text FROM events WHERE room_id=? AND active=1 AND type IN ('action','gm','prologue','gm_note','dice') ORDER BY seq DESC", (room_id,)).fetchall()
    for row in rows:
        candidates.append({'id':row['id'], 'source':'event', 'title':f"事件 #{row['seq']}", 'text':row['text'], 'seq':row['seq'], 'tags':''})
    for item in candidates:
        searchable = f"{item['title']} {item['tags']} {item['text']}".lower()
        overlap = sum(1 + min(searchable.count(term), 3) * .2 for term in query_terms if term in searchable)
        item['score'] = round(overlap * (1.4 if item['source'] == 'lore' else 1), 2)
    matches = [item for item in candidates if item['score'] > 0] if query_terms else candidates
    matches.sort(key=lambda item:(item['score'], item['source'] == 'lore', item['seq']), reverse=True)
    return [{k:v for k,v in item.items() if k != 'tags'} for item in matches[:limit]]


def model_context(room_id, state, action_text):
    retrieved = retrieve(room_id, state, action_text, 6)
    with connection() as con:
        recent = con.execute("SELECT id,type,actor_name,text FROM events WHERE room_id=? AND active=1 AND type NOT IN ('chat','error','extension') ORDER BY seq DESC LIMIT 10", (room_id,)).fetchall()
    return {
        'world':{k:state['world'][k] for k in ('title','premise','tone')},
        'scene':state['scene'], 'rules':state['rules'], 'characters':state['characters'],
        'facts':state['facts'][-20:], 'retrieved':retrieved,
        'recent_events':[{'id':r['id'],'type':r['type'],'actor':r['actor_name'],'text':r['text'][:1500]} for r in reversed(recent)],
        'continuation':state['continuation']
    }
