"""Reserved host resource capabilities. Unknown core resources fail closed."""
CORE_CAPABILITIES = {
    'core.world/v1': 'read:room',
    'core.characters/v1': 'read:room',
    'core.rules/v1': 'read:room',
    'core.events/v1': 'read:events',
    'core.dice/v1': 'dice:roll',
}
