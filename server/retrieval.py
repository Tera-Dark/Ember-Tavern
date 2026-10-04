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
        room_row = con.execute('SELECT branch FROM rooms WHERE id=?', (room_id,)).fetchone()
        current_branch = room_row['branch'] if room_row else None
        recent = con.execute("SELECT id,type,actor_name,text FROM events WHERE room_id=? AND active=1 AND type IN ('action','action_intent','gm','prologue','gm_note','dice') ORDER BY seq DESC LIMIT 10", (room_id,)).fetchall()
        memory_summary = state.get('_memory_summary')
        memory_valid = bool(memory_summary and memory_summary.get('branch') == current_branch)
        if memory_valid:
            source_ids = memory_summary.get('source_event_ids', [])
            if not source_ids:
                memory_valid = False
            else:
                placeholders = ','.join('?' for _ in source_ids)
                active_sources = con.execute(f"SELECT COUNT(*) FROM events WHERE room_id=? AND active=1 AND id IN ({placeholders})",
                                             (room_id, *source_ids)).fetchone()[0]
                memory_valid = active_sources == len(source_ids)
    from .campaign_state import ledger_context
    engine = engine_for(state)
    context = {'world': {key: state['world'][key] for key in ('title', 'premise', 'tone')},
               'scene': {'title': state['scene']['title'], 'text': state['scene']['text'][:1200]},
               'rule_system': engine.id, 'rules': engine.description,
               'characters': characters, 'facts': state['facts'][-8:], 'campaign_state': ledger_context(state),
               'retrieved': [], 'recent_events': [], 'continuation': state['continuation']}
    if getattr(engine, 'status', 'implemented') == 'experimental':
        game_rules = engine.project_state(state)
        game_rules.pop('implementation_sha256', None)
        if engine.id == 'dnd5e-srd-5.2.1/v1' and game_rules.get('encounter'):
            game_rules['encounter']['log'] = game_rules['encounter'].get('log', [])[-6:]
        elif engine.id == 'ember-coop-settlement/v1':
            game_rules['settlements'] = game_rules.get('settlements', [])[-2:]
        context['game_rules'] = game_rules
    action_round = state.get('_action_round')
    if action_round and action_round.get('status') == 'resolving' and action_round.get('branch') == current_branch:
        context['action_round'] = {'number': action_round.get('number'),
                                   'participant_character_ids': [item['character_id'] for item in action_round.get('submissions', [])],
                                   'submitted_count': len(action_round.get('submissions', [])),
                                   'required_count': len(action_round.get('required', [])),
                                   'missing_character_ids': [item['character_id'] for item in action_round.get('required', [])
                                                             if item['character_id'] not in {s['character_id'] for s in action_round.get('submissions', [])}]}
    from .presets.scenario import model_brief
    brief = model_brief(state)
    if brief:
        brief['gm_notes'] = brief['gm_notes'][:600]
        brief['clues'] = [{**clue,'text':clue['text'][:220],'gm_notes':clue['gm_notes'][:120]} for clue in brief['clues'][:6]]
        brief['transitions'] = [{**edge,'gm_guidance':edge['gm_guidance'][:180]} for edge in brief['transitions'][:6]]
        context['campaign'] = brief
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
    if brief and encoded_chars(context) > total_budget - 1200:
        context['campaign']['gm_notes'] = context['campaign']['gm_notes'][:120]
        context['campaign']['objective'] = context['campaign']['objective'][:200]
        context['campaign']['clues'] = context['campaign']['clues'][:2]
        context['campaign']['transitions'] = context['campaign']['transitions'][:2]
    if encoded_chars(context) > total_budget - 1200:
        for key in ('quests', 'npcs', 'resources'):
            context['campaign_state'][key] = context['campaign_state'][key][:3]
        for item in context['campaign_state']['quests']:
            item['summary'] = item['summary'][:60]
        for item in context['campaign_state']['npcs']:
            item['summary'] = item['summary'][:60]
    for row in recent[:2]:
        context['recent_events'].insert(0, {'id': row['id'], 'type': row['type'], 'actor': row['actor_name'], 'text': row['text'][:500]})
    if encoded_chars(context) > total_budget:
        raise ValueError('核心行动与角色信息超过主持上下文预算，请增大 CONTEXT_MAX_CHARS')

    memory_selection = {'included': False, 'source_event_ids': [], 'chars': 0, 'truncated': False}
    if memory_valid:
        source_ids = memory_summary['source_event_ids']
        memory_limit = max(0, min(8000, settings.memory_summary_context_chars))
        record = {'text': memory_summary.get('text', ''), 'source_event_ids': source_ids,
                  'source_seq_max': memory_summary.get('source_seq_max')}
        available = max(0, total_budget - encoded_chars(context) - 700)
        record['text'] = record['text'][:min(memory_limit, available)]
        candidate = dict(context, memory_summary=record)
        while record['text'] and encoded_chars(candidate) > total_budget:
            record['text'] = record['text'][:-max(1, (encoded_chars(candidate) - total_budget) // 2)]
            candidate = dict(context, memory_summary=record)
        if record['text']:
            context['memory_summary'] = record
            memory_selection = {'included': True, 'source_event_ids': source_ids,
                                'chars': len(record['text']), 'truncated': len(record['text']) < len(memory_summary.get('text', ''))}

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
    selection['memory_summary'] = memory_selection
    selection['context_chars'] = encoded_chars(context)
    selection['context_budget_chars'] = total_budget
    included = {item['id'] for item in context['retrieved']}
    selection['entries'] = [entry for entry in selection['entries'] if entry['id'] in included]
    # Diagnostics travel to the host trace, not to a model's prompt.
    context['_selection'] = selection
    return context
