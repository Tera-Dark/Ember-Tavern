from fastapi import HTTPException
from server.plugin_runtime.sdk import Plugin,Result

class Extension(Plugin):
    schema_version=1
    def initial(self,ctx):return {'notes':[]}
    async def action(self,ctx,name,payload,data):
        ctx.require_owner()
        if name!='append':raise HTTPException(404,'未知便签操作')
        text=payload.get('text')
        if not isinstance(text,str) or not 1<=len(text.strip())<=500:raise HTTPException(422,'便签必须1–500字符')
        return Result(data={'notes':(data.get('notes',[])+[text.strip()])[-20:]},message='新增场景便签。',output={'saved':True})
