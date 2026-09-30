import re
import secrets
from .db import uid
from fastapi import HTTPException

ATTR_NAMES = {'strength':'力量', 'dexterity':'敏捷', 'knowledge':'学识', 'insight':'洞察', 'charisma':'魅力'}
RULES = '轻规则 v1：d20 + 属性修正 ≥ 难度。天然20大成功、天然1大失败。难度8–20。失败时，仅明确标注生命风险扣1生命，压力风险加1压力。生命0无法继续行动；压力上限6。自由掷骰不改变角色状态。'

PRESETS = {
    'harbor': {
        'title': '雾港 · 第十三盏灯',
        'premise': '雾港连续三晚有人失踪。每逢午夜，废弃灯塔会亮起本不存在的第十三盏灯。你们在余烬酒馆收到一封无署名的求援信，信封里是一枚冰冷的黄铜钥匙。今夜，只剩最后一班渡船。',
        'tone': '低魔、海港悬疑、克制的危险；给玩家自由选择，不强迫唯一解',
        'scene_title': '序章 · 余烬酒馆',
        'opening': '雨水沿着酒馆的窗棂滑落，壁炉只剩一簇暗红的余烬。\n\n酒保把一封潮湿的信推到你们面前。没有署名，只有一行字：「如果第十三盏灯再次亮起，请别相信渡船上的人。」\n\n一枚黄铜钥匙从信封里落下。远处，港口的钟声响了十一下。你们打算怎么做？',
        'lore': [
            {'title':'第十三盏灯', 'content':'灯塔原本只有十二盏灯。守塔人三日前失踪，港民传闻第十三盏灯会引导不存在的船。传闻尚未证实。', 'tags':'灯塔 灯 守塔人'},
            {'title':'黄铜钥匙', 'content':'钥匙柄刻着一只闭眼的海鸥，与旧港海关的印章相似。它不是酒馆的钥匙。', 'tags':'钥匙 海鸥 海关'},
            {'title':'雾港渡船', 'content':'午夜是渡船最后一班。船长阿洛每夜把一只空箱子运向灯塔，但拒绝解释。', 'tags':'渡船 船长 阿洛 港口'}
        ]
    },
    'frontier': {
        'title': '余烬边境 · 无声的邮差',
        'premise': '边境驿站已经两周没收到来信。一匹无人骑乘的黑马在黄昏来到酒馆，马鞍上绑着一个封蜡未破的邮袋。你们受托调查失联的驿路。',
        'tone':'边境冒险、古老遗迹、温暖但有风险',
        'scene_title':'序章 · 边境驿站',
        'opening':'夕阳落在荒草之间，酒馆门外响起马蹄声。\n\n一匹黑马独自停在门口，鞍边的邮袋上沾着银色的尘土。驿站长低声说：「这不是我们这里的泥。」\n\n你们可以检查邮袋、安抚黑马，或先向驿站长打听失联的邮差。',
        'lore':[
            {'title':'失联驿路', 'content':'北方驿路经过古老石门。每年初秋石门旁会出现银色粉尘。', 'tags':'驿路 石门 尘土'},
            {'title':'黑马', 'content':'黑马名叫夜信，只听邮差米娅的口哨。马匹疲惫但没有伤口。', 'tags':'黑马 夜信 米娅'}
        ]
    }
}


def initial_state(preset='harbor', premise=''):
    base = PRESETS.get(preset, {
        'title':'未命名世界', 'premise':premise or '一群旅人在陌生的酒馆相遇。请房主完善世界书，然后开始冒险。',
        'tone':'尊重角色选择、清晰的因果关系', 'scene_title':'序章 · 新的旅程',
        'opening':'新的故事还未被书写。你们在酒馆相遇，桌上放着一张空白的地图。\n\n请房主在「世界书」补充设定，再决定第一步行动。', 'lore':[]
    }).copy()
    if premise:
        base['premise'] = premise
        base['opening'] = f"{premise}\n\n故事由你们的选择展开。你们打算怎么做？"
    characters = [
        {'id':uid(), 'name':'伊芙·灰羽', 'archetype':'斥候 / 路径寻找者', 'description':'熟悉港口的小巷，习惯先观察，再下决定。', 'avatar':'feather', 'hp':12, 'max_hp':12, 'stress':0,
         'attributes':{'strength':0,'dexterity':2,'knowledge':1,'insight':2,'charisma':0}, 'inventory':['短弓','麻绳','旧港地图']},
        {'id':uid(), 'name':'洛恩·灯誓', 'archetype':'守卫 / 流浪骑士', 'description':'相信每个承诺都有重量。随身的灯从未熄灭。', 'avatar':'shield', 'hp':14, 'max_hp':14, 'stress':0,
         'attributes':{'strength':2,'dexterity':0,'knowledge':1,'insight':1,'charisma':2}, 'inventory':['长剑','提灯','旅行斗篷']}
    ]
    return {
        'world':{'title':base['title'],'premise':base['premise'],'tone':base['tone'],
                 'lore':[dict(item, id=uid()) for item in base['lore']]},
        'scene':{'title':base['scene_title'],'text':base['opening']},
        'characters':characters, 'facts':[], 'turn':0, 'pending_check':None,
        'awaiting_gm':False, 'continuation':None, 'gm_error':None, 'rules':RULES
    }


def character(state, character_id):
    found = next((item for item in state['characters'] if item['id'] == character_id), None)
    if not found:
        raise HTTPException(404, '角色不存在于当前时间线')
    return found


def parse_dice(expression):
    match = re.fullmatch(r'(\d{1,2})d(\d{1,3})([+-]\d{1,3})?', expression.lower().replace(' ', ''))
    if not match:
        raise HTTPException(422, '骰子格式应为 1d20、2d6 或 1d20+2')
    count, sides, modifier = int(match[1]), int(match[2]), int(match[3] or 0)
    if not 1 <= count <= 20 or not 2 <= sides <= 100 or abs(modifier) > 100:
        raise HTTPException(422, '仅支持1–20颗、2–100面骰，修正值±100以内')
    return count, sides, modifier


def free_roll(expression):
    count, sides, modifier = parse_dice(expression)
    rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
    return {'expression':f'{count}d{sides}' + (f'{modifier:+d}' if modifier else ''), 'rolls':rolls, 'modifier':modifier, 'total':sum(rolls)+modifier, 'kind':'free'}


def resolve_check(state):
    check = state['pending_check']
    char = character(state, check['character_id'])
    raw = secrets.randbelow(20) + 1
    modifier = check['modifier']
    total = raw + modifier
    success = raw == 20 or (raw != 1 and total >= check['dc'])
    outcome = '大成功' if raw == 20 else '大失败' if raw == 1 else '成功' if success else '失败'
    consequence = '无属性变化'
    if not success and check['risk'] == 'harm':
        char['hp'] = max(0, char['hp'] - 1)
        consequence = f"{char['name']} 生命 −1"
    elif not success and check['risk'] == 'stress':
        char['stress'] = min(6, char['stress'] + 1)
        consequence = f"{char['name']} 压力 +1"
    result = dict(check, rolls=[raw], total=total, success=success, outcome=outcome,
                  consequence=consequence, expression=f'1d20{modifier:+d}', kind='check', character_name=char['name'])
    state['pending_check'] = None
    return result
