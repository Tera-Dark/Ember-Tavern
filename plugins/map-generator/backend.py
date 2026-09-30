import random,secrets
from fastapi import HTTPException
from server.plugin_runtime.sdk import Plugin,Result
from server.config import settings
from server.plugin_runtime.services import structured_map
class Extension(Plugin):
    def resources(self,ctx,data):return {'map.generator/v1':{'ai_configured':bool(settings.decision_api_key and settings.decision_model)}}
    async def action(self,ctx,name,payload,data):
        ctx.require_owner()
        if name!='generate':raise HTTPException(404,'操作不存在')
        width=int(payload.get('width',24));height=int(payload.get('height',16));theme=payload.get('theme','harbor');mode=payload.get('mode','procedural')
        if not 8<=width<=40 or not 8<=height<=28 or theme not in ('harbor','ruins','forest','cave') or mode not in ('procedural','ai'):raise HTTPException(422,'地图生成参数无效')
        value=payload.get('seed');seed=int(value) if value not in (None,'') else secrets.randbelow(1000000);rng=random.Random(seed)
        if mode=='ai':
            if ctx.user['guest']:raise HTTPException(403,'体验账号不能调用付费模型')
            layout=await structured_map(ctx.state['world'],width,height)
        else:
            grid=[]
            for y in range(height):
                row=[]
                for x in range(width):
                    char='.'
                    if x==0 or y==0 or x==width-1 or y==height-1:char='#'
                    elif theme=='harbor' and x>width*.72:char='~'
                    elif rng.random()<(.15 if theme=='forest' else .10):char='t' if theme=='forest' else '#'
                    if 1<=x<width-1 and abs(y-height//2)<=1:char='='
                    if 1<=x<=4 and abs(y-height//2)<=3:char='.'
                    row.append(char)
                grid.append(''.join(row))
            layout={'title':{'harbor':'雾港 · 旧码头','ruins':'石门 · 遗迹大厅','forest':'边境 · 林间驿路','cave':'地下 · 回声洞穴'}[theme],'grid':grid}
        layout.update(theme=theme,seed=seed,source=mode)
        return Result(data={'seed':seed,'theme':theme,'mode':mode},calls=[{'plugin':'scene-map','action':'set_map','payload':layout}],
                      message=('AI 生成' if mode=='ai' else '程序生成')+'地图已应用。',output={'seed':seed})
