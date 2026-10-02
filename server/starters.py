"""Public metadata for existing, built-in starter worlds.

This is intentionally not the future ember.preset package loader: no code,
dependencies, imported content or campaign secrets are included.
"""
from .domain import PRESETS

STARTER_DETAILS = {
    'harbor': {
        'name': '雾港 · 第十三盏灯',
        'category': '合作调查',
        'description': '从一封没有署名的邀请开始，观察港口、询问人物，共同追查灯塔的异常。',
        'first_action': '选择一位角色，观察码头的灯光，或向渡船人打听灯塔。',
    },
    'frontier': {
        'name': '边境 · 失联的驿路',
        'category': '奇幻探索',
        'description': '一匹无人骑乘的黑马带回神秘邮袋。检查线索、与驿站长交涉，再选择探索路线。',
        'first_action': '选择一位角色，检查邮袋、安抚黑马，或询问驿站长。',
    },
}


def starter_worlds():
    return [dict(id=key, **details, world_title=PRESETS[key]['title'],
                 rule_system='ember-light/v1', suggested_players='2–4 人，也可单人试用',
                 ai_mode='demo', label='内置入门世界 · 非完整玩法包', external_calls=False)
            for key, details in STARTER_DETAILS.items()]
