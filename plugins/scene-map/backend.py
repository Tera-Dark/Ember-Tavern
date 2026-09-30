from server.plugin_runtime.sdk import Plugin,Result
from fastapi import HTTPException
from server.db import uid
class Extension(Plugin):
    def initial(self,ctx):return {'map':None}
    def resources(self,ctx,data):return {'scene.map/v1':data.get('map')}
    async def action(self,ctx,name,payload,data):
        ctx.require_owner()
        if name!='set_map':raise HTTPException(404,'操作不存在')
        grid=payload.get('grid',[])
        if not isinstance(grid,list) or not 8<=len(grid)<=32 or not all(isinstance(r,str) for r in grid):raise HTTPException(422,'地图需要8–32行')
        width=len(grid[0])
        if not 8<=width<=48 or any(len(r)!=width or any(c not in '.#~t=' for c in r) for r in grid):raise HTTPException(422,'非法网格尺寸或地形')
        if sum(r.count('.')+r.count('=') for r in grid)<12:raise HTTPException(422,'至少需要12个可行走格')
        title=str(payload.get('title','新的场景'))[:80]
        layout={'id':uid(),'title':title,'width':width,'height':len(grid),'grid':grid,'theme':str(payload.get('theme','harbor'))[:32],
                'source':str(payload.get('source','procedural'))[:32],'seed':payload.get('seed'),'legend':{'.':'地面','#':'墙体','~':'水域','t':'树林','=':'路径'}}
        return Result(data={'map':layout},message='地图布局已更新，角色图层按新地图重新定位。')
