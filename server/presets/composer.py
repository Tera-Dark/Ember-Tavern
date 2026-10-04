"""A composition is data + reviewed server policy, not package-supplied code."""
from copy import deepcopy
from fastapi import HTTPException
from ..db import uid
from ..domain import initial_state
from ..rules import engine_for, contract_hash
from ..state import migrate_state
from .library import compatibility


def compose(package,manager):
    ready=compatibility(package,manager)
    if not ready['can_create']:
        raise HTTPException(422,{'message':'预设依赖不满足；房间未创建','blockers':ready['blockers']})
    m=package.manifest
    state=initial_state('custom')
    state['world']=deepcopy(package.worldbook['world'])
    state['characters']=[deepcopy(card['character'])|{'id':uid()} for card in package.characters]
    scenario=deepcopy(package.scenario)
    scene=next(item for item in scenario['scenes'] if item['id']==scenario['start_scene'])
    state['scene']={'title':scene['title'],'text':scene['text']}
    state['schema_version']=2
    state['_scenario']={'document':scenario,'current_scene':scene['id'],'revealed_clues':[]}
    components=[]
    for kind,refs in [('worldbook',[m['worldbook']]),('scenario',[m['scenario']]),('character',m['characters']),('theme',[m['theme']] if m['theme'] else [])]:
        components.extend({'kind':kind,**ref} for ref in refs)
    engine=engine_for(state)
    state['_preset_lock']={'format':'ember.content-lock/v1','package_hash':package.package_hash,
                           'preset':deepcopy(m['metadata']),'components':components,
                           'rule':{'id':engine.id,'version':engine.contract()['implementation_version'],
                                   'contract_sha256':contract_hash(engine)},
                           'plugins':deepcopy(ready['plugins']),'profile':deepcopy(m['profile'])}
    if package.theme: state['_preset_theme']=deepcopy(package.theme)
    state = migrate_state(state)
    # Explicitly disable undeclared modules. The package grants no installation,
    # Python trust or high-risk capability; readiness uses existing approvals.
    flags={pid:False for pid in manager.items}
    flags.update({pin['id']:pin['enabled'] for pin in ready['plugins']})
    return state,flags
