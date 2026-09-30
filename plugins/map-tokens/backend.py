from fastapi import HTTPException
from server.plugin_runtime.sdk import Plugin,Result
class Extension(Plugin):
    def initial(self,ctx):return {'map_id':None,'positions':{}}
    def reconcile(self,ctx,data):
        resource=ctx.resource('scene.map/v1');layout=resource['data'] if resource else None
        if not layout:return data
        positions=data.get('positions',{}) if data.get('map_id')==layout['id'] else {}
        spawn=[(x,y) for y,row in enumerate(layout['grid']) for x,tile in enumerate(row) if tile in '.=']
        spawn.sort(key=lambda p:abs(p[1]-layout['height']//2)+p[0]*.7)
        characters=ctx.characters();positions={k:v for k,v in positions.items() if any(c['id']==k for c in characters)}
        for i,c in enumerate(characters):
            if c['id'] not in positions:
                x,y=spawn[i%len(spawn)];positions[c['id']]={'x':x,'y':y}
        return {'map_id':layout['id'],'positions':positions}
    def on_event(self,ctx,event,data):
        updated=self.reconcile(ctx,data)
        return updated if updated!=data else None
    def resources(self,ctx,data):
        data=self.reconcile(ctx,data)
        return {'scene.tokens/v1':dict(data,tokens=[dict(c,position=data.get('positions',{}).get(c['id'])) for c in ctx.characters()])}
    def target(self,ctx,payload,committed=True):
        c=ctx.control(payload.get('character_id',''));res=ctx.resource('scene.map/v1');layout=res['data'] if res else None
        if not layout or payload.get('map_id')!=layout['id']:raise HTTPException(409,'地图已变化，请重新选择位置')
        try:x=float(payload['x']);y=float(payload['y'])
        except Exception:raise HTTPException(422,'位置格式无效')
        if not 0<=x<layout['width'] or not 0<=y<layout['height']:raise HTTPException(422,'位置超出地图')
        if committed:
            if x!=int(x) or y!=int(y) or layout['grid'][int(y)][int(x)] not in '.=':raise HTTPException(422,'目标必须是可行走的格子')
            x,y=int(x),int(y)
        return c,layout,x,y
    async def action(self,ctx,name,payload,data):
        if name!='move':raise HTTPException(404,'操作不存在')
        c,layout,x,y=self.target(ctx,payload)
        updated=self.reconcile(ctx,data);updated['positions'][c['id']]={'x':x,'y':y}
        return Result(data=updated,message=f"{c['name']} 移动到 ({x+1}, {y+1})。",output={'x':x,'y':y})
    def signal(self,ctx,name,payload,data):
        if name!='preview':raise HTTPException(404,'信号不存在')
        c,layout,x,y=self.target(ctx,payload,False)
        return {'character_id':c['id'],'map_id':layout['id'],'x':round(x,2),'y':round(y,2)}
