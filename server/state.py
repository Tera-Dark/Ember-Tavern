"""Monotonic core state migrations. Old event snapshots migrate on read/rewind."""
import json
from copy import deepcopy

STATE_VERSION = 1
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
    return state


def load_state(encoded):
    return migrate_state(json.loads(encoded))
