"""Room-scoped lexical retrieval and deterministic, budgeted GM context.

This is not vector RAG and a character count is not a tokenizer/cost estimate.
"""
import json
import re

from .config import settings
from .db import connection
from .rules import engine_for


def terms(text):
    lowered = text.lower()
    tokens = set(re.findall(r'[a-z0-9_]{2,}', lowered))
    for block in re.findall(r'[\u4e00-\u9fff]+', lowered):
        if len(block) == 1:
            tokens.add(block)
        else:
            tokens.update(block[i:i + 2] for i in range(len(block) - 1))
    return tokens


def active_lore(state, include_gm):
    return [entry for entry in state['world']['lore'] if entry.get('enabled', True)
            and (include_gm or entry.get('visibility', 'public') == 'public')]


def relevance(text, query_terms):
    text = text.lower()
    return round(sum(1 + min(text.count(term), 3) * .2 for term in query_terms if term in text), 2)


def retrieve(room_id, state, query, limit=8, *, include_gm=False, include_lore=True):
    query_terms = terms(query)
    candidates = []
    if include_lore:
        for item in active_lore(state, include_gm):
            candidates.append({'id': item['id'], 'source': 'lore', 'title': item['title'], 'text': item['content'],
                               'tags': item.get('tags', '') + ' ' + ' '.join(item.get('keys', [])),
                               'visibility': item.get('visibility', 'public'), 'seq': 0})
    for index, fact in enumerate(state['facts']):
        candidates.append({'id': f'fact-{index}', 'source': 'fact', 'title': '已确认事实', 'text': fact, 'seq': 0, 'tags': ''})
    with connection() as con:
        rows = con.execute("SELECT id,seq,type,text FROM events WHERE room_id=? AND active=1 AND type IN ('action','gm','prologue','gm_note','dice') ORDER BY seq DESC", (room_id,)).fetchall()
    for row in rows:
        candidates.append({'id': row['id'], 'source': 'event', 'title': f"事件 #{row['seq']}", 'text': row['text'], 'seq': row['seq'], 'tags': ''})
    for item in candidates:
        score = relevance(f"{item['title']} {item['tags']} {item['text']}", query_terms)
        item['score'] = round(score * (1.4 if item['source'] == 'lore' else 1), 2)
    matches = [item for item in candidates if item['score'] > 0] if query_terms else candidates
    matches.sort(key=lambda item: (item['score'], item['source'] == 'lore', item['seq']), reverse=True)
    return [{k: v for k, v in item.items() if k != 'tags'} for item in matches[:limit]]


def encoded_chars(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def select_lore(state, query, budget, *, include_gm=True):
    candidates = []
    query_lower, query_terms = query.lower(), terms(query)
    for index, entry in enumerate(active_lore(state, include_gm)):
        keys = entry.get('keys', []) + re.split(r'[\s,，]+', entry.get('tags', '').strip())
        keyword_match = any(key and key.lower() in query_lower for key in keys)
        score = relevance(entry['title'] + ' ' + entry['content'], query_terms)
        always = entry.get('kind') == 'rule' or entry.get('activation') == 'always'
        if not always and not keyword_match and not score:
            continue
        reason = 'rule' if entry.get('kind') == 'rule' else 'always' if always else 'keyword' if keyword_match else 'lexical'
        candidates.append((0 if always else 1 if keyword_match else 2, -entry.get('priority', 0), -score, index, reason, entry))
    candidates.sort(key=lambda item: item[:4])
    selected, details, omitted = [], [], []
    used = 0
    for _, _, neg_score, _, reason, entry in candidates:
        record = {'id': entry['id'], 'source': 'lore', 'title': entry['title'], 'text': entry['content'],
                  'kind': entry.get('kind', 'lore'), 'visibility': entry.get('visibility', 'public'), 'score': -neg_score}
        remaining = budget - used
        overhead = encoded_chars(dict(record, text=''))
        if len(selected) >= 32 or remaining < overhead + 100:
            omitted.append(entry['id'])
            continue
        truncated = encoded_chars(record) > remaining
        if truncated:
            # JSON escaping can cost more than one character; measure after trimming.
            record['text'] = record['text'][:max(0, remaining - overhead - 4)]
            while record['text'] and encoded_chars(record) > remaining:
                record['text'] = record['text'][:-max(1, (encoded_chars(record) - remaining) // 2)]
        size = encoded_chars(record)
        used += size
        selected.append(record)
        details.append({'id': entry['id'], 'title': entry['title'], 'visibility': record['visibility'],
                        'reason': reason, 'chars': size, 'truncated': truncated})
    return selected, {'budget_chars': budget, 'used_chars': used, 'entries': details, 'omitted_ids': omitted,
                      'method': '字面关键词 / 中文双字词；非向量检索'}


def model_context(room_id, state, action_text):
    total_budget = max(8000, min(96000, settings.context_max_chars))
    current_id = (state.get('continuation') or {}).get('character_id')
    characters = []
    for char in state['characters']:
        view = {key: char[key] for key in ('id', 'name', 'archetype', 'hp', 'max_hp', 'stress', 'attributes')}
        view['description'] = char.get('description', '')[:400 if char['id'] == current_id else 160]
        view['gm_notes'] = char.get('gm_notes', '')[:400 if char['id'] == current_id else 160]
        view['inventory'] = char.get('inventory', [])[:8] if char['id'] == current_id else []
        characters.append(view)
    with connection() as con:
        recent = con.execute("SELECT id,type,actor_name,text FROM events WHERE room_id=? AND active=1 AND type IN ('action','gm','prologue','gm_note','dice') ORDER BY seq DESC LIMIT 10", (room_id,)).fetchall()
    context = {'world': {key: state['world'][key] for key in ('title', 'premise', 'tone')},
               'scene': {'title': state['scene']['title'], 'text': state['scene']['text'][:1200]},
               'rule_system': engine_for(state).id, 'rules': engine_for(state).description,
               'characters': characters, 'facts': state['facts'][-8:], 'retrieved': [], 'recent_events': [],
               'continuation': state['continuation']}
    context['world']['premise'] = context['world']['premise'][:3000]
    # Preserve structured action/roll and all character stats even at a small budget.
    if encoded_chars(context) > total_budget - 1200:
        context['world']['premise'] = context['world']['premise'][:800]
        context['scene']['text'] = context['scene']['text'][:400]
        context['facts'] = context['facts'][-3:]
        for char in context['characters']:
            char['description'] = char['description'][:80]
            char['gm_notes'] = char['gm_notes'][:80]
            char['inventory'] = char['inventory'][:3]
    for row in recent[:2]:
        context['recent_events'].insert(0, {'id': row['id'], 'type': row['type'], 'actor': row['actor_name'], 'text': row['text'][:500]})
    if encoded_chars(context) > total_budget:
        raise ValueError('核心行动与角色信息超过主持上下文预算，请增大 CONTEXT_MAX_CHARS')
    lore_budget = max(0, min(settings.lore_context_chars, total_budget - encoded_chars(context) - 300))
    selected, selection = select_lore(state, action_text, lore_budget)
    # Account for separators as well as each entry; never exceed the global cap.
    for record in selected:
        context['retrieved'].append(record)
        if encoded_chars(context) > total_budget:
            context['retrieved'].pop()
            selection['omitted_ids'].append(record['id'])
    for record in retrieve(room_id, state, action_text, 6, include_lore=False):
        record['text'] = record['text'][:900]
        context['retrieved'].append(record)
        if encoded_chars(context) > total_budget:
            context['retrieved'].pop()
    retrieved_ids = {item['id'] for item in context['retrieved']}
    for row in recent[2:]:
        if row['id'] in retrieved_ids:
            continue
        record = {'id': row['id'], 'type': row['type'], 'actor': row['actor_name'], 'text': row['text'][:900]}
        context['recent_events'].insert(0, record)
        if encoded_chars(context) > total_budget:
            context['recent_events'].pop(0)
    selection['context_chars'] = encoded_chars(context)
    selection['context_budget_chars'] = total_budget
    included = {item['id'] for item in context['retrieved']}
    selection['entries'] = [entry for entry in selection['entries'] if entry['id'] in included]
    # Diagnostics travel to the host trace, not to a model's prompt.
    context['_selection'] = selection
    return context
