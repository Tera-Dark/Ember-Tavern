"""Explicit viewer projections. Filtering in React alone is not a permission boundary."""
from copy import deepcopy


def project_state(state, include_gm=False):
    view = deepcopy(state)
    from .presets.scenario import view as campaign_view
    campaign = campaign_view(state,include_gm)
    if campaign: view['campaign'] = campaign
    if state.get('_preset_theme'): view['preset_theme'] = deepcopy(state['_preset_theme'])
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
    return view
