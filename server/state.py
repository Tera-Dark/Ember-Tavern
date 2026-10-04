"""Monotonic core state migrations. Old event snapshots migrate on read/rewind."""
import json
from copy import deepcopy

STATE_VERSION = 4
LORE_DEFAULTS = {
    'keys': [], 'kind': 'lore', 'visibility': 'public', 'enabled': True,
    'activation': 'keywords', 'priority': 0,
}


def migrate_state(value):
    state = deepcopy(value)
    version = state.get('schema_version', 0)
    if type(version) is not int or not 0 <= version <= STATE_VERSION:
        raise ValueError('不支持的游戏状态版本；请备份数据并使用兼容的宿主')
    if version == 0:
        state['world'].setdefault('rule_system', 'ember-light/v1')
        state['world'].setdefault('extensions', {})
        for entry in state['world']['lore']:
            for field, default in LORE_DEFAULTS.items():
                entry.setdefault(field, deepcopy(default))
        for char in state['characters']:
            char.setdefault('gm_notes', '')
            char.setdefault('extensions', {})
        state['schema_version'] = 1
    # M1 compositions require schema 2. Older hosts must refuse these
    # snapshots rather than accidentally projecting private scenario documents.
    if ('_scenario' in state or '_preset_lock' in state) and state.get('schema_version', 0) < 2:
        state['schema_version'] = 2
    # M2 stores structured campaign state, action-round collection and curated
    # memory in snapshots. Old snapshots migrate forward; unknown future state
    # remains a hard error rather than being silently discarded.
    if state.get('schema_version', 0) < 3:
        from .campaign_state import empty_ledger
        state.setdefault('_campaign_state', empty_ledger())
        state.setdefault('_action_mode', 'free')
        state.setdefault('_action_round', None)
        state.setdefault('_memory_summary', None)
        state['schema_version'] = 3
    # M3 adds a typed, adapter-owned snapshot slot. Existing light-rules rooms
    # migrate to an empty slot; experimental adapters initialize only when the
    # room was created with that reviewed rule identity.
    if state.get('schema_version', 0) < 4:
        state.setdefault('_rule_state', None)
        state['schema_version'] = 4
        rule_id = state.get('world', {}).get('rule_system', 'ember-light/v1')
        if rule_id != 'ember-light/v1':
            from .rules import engine_for
            engine = engine_for(state)
            initialize = getattr(engine, 'initial_rule_state', None)
            if initialize is None:
                raise ValueError('规则适配器未提供 M3 状态初始化器')
            state['_rule_state'] = initialize(state)
    return state


def load_state(encoded):
    return migrate_state(json.loads(encoded))
