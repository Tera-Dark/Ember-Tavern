from server.plugin_runtime.sdk import Plugin
class Extension(Plugin):
    async def gm(self,ctx,state,mode):
        return await ctx.services['gm'](ctx.room_id,state,mode)
