"""Explicit viewer projections. Filtering in React alone is not a permission boundary."""
from copy import deepcopy


def project_state(state, include_gm=False, viewer_id=None):
    view = deepcopy(state)
    from .campaign_state import action_round_view, ledger_view
    from .presets.scenario import view as campaign_view
    campaign = campaign_view(state,include_gm)
    if campaign: view['campaign'] = campaign
    view['campaign_state'] = ledger_view(state, include_gm)
    view['action_mode'] = state.get('_action_mode', 'free')
    view['action_round'] = action_round_view(state)
    from .rules import engine_for
    engine = engine_for(state)
    if getattr(engine, 'status', 'implemented') == 'experimental':
        rule_view = engine.project_state(state)
        if engine.id == 'ember-coop-settlement/v1' and viewer_id is not None:
            internal = state.get('_rule_state') or {}
            rule_view['my_order_submitted'] = any(
                order.get('actor_id') == viewer_id for order in internal.get('orders', []))
        view['game_rules'] = rule_view
    if include_gm and state.get('_memory_summary'):
        view['memory_summary'] = deepcopy(state['_memory_summary'])
    if state.get('_preset_theme'): view['preset_theme'] = deepcopy(state['_preset_theme'])
    # M2 internal state is always exposed through the typed projection above,
    # never as raw snapshot implementation details or a generic JSON patch.
    for key in ('_campaign_state', '_action_mode', '_action_round', '_memory_summary', '_rule_state'):
        view.pop(key, None)
    if not include_gm:
        view['world']['lore'] = [entry for entry in view['world']['lore'] if entry.get('visibility', 'public') == 'public']
        for char in view['characters']:
            char.pop('gm_notes', None)
        view.pop('_content', None)
        view.pop('_scenario', None)
        view.pop('_preset_lock', None)
        view.pop('_preset_theme', None)
    return view


def project_event(event, include_gm=False):
    view = deepcopy(event)
    if not include_gm:
        # The narrative is public; the host's evidence selection is not.
        for field in ('context_ids', 'context_selection'):
            view.get('payload', {}).pop(field, None)
        if view.get('type') == 'memory_summary':
            view['text'] = '主持记忆摘要已更新；内容仅房主与主持上下文可见。'
            view['payload'] = {'label': '主持私有记忆更新'}
        elif view.get('type') == 'campaign_state':
            view['text'] = '房主更新了战役状态记录。'
            view['payload'] = {'label': '战役状态更新'}
    return view
