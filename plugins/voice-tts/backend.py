import hashlib
from fastapi import HTTPException
from server.config import settings
from server.db import uid
from server.plugin_runtime.sdk import Plugin,Result
from server.plugin_runtime.services import synthesize
class Extension(Plugin):
    def initial(self,ctx):return {'clips':[]}
    def resources(self,ctx,data):return {'narration.audio/v1':dict(data,configured=bool(settings.tts_api_key and settings.tts_model),model=settings.tts_model or '尚未指定',voice=settings.tts_voice)}
    async def action(self,ctx,name,payload,data):
        ctx.require_owner()
        if ctx.user['guest']:raise HTTPException(403,'体验账号不能调用付费 TTS；可使用浏览器朗读')
        if name!='synthesize':raise HTTPException(404,'操作不存在')
        resource=ctx.resource('narration.script/v1');lines=resource['data'].get('lines',[]) if resource else []
        line=next((x for x in lines if x['id']==payload.get('line_id')),None)
        if not line:raise HTTPException(404,'台本片段不存在或属于其他时间线')
        audio=await synthesize(line['text']);asset=ctx.save_asset(audio,'audio/mpeg');asset_id=asset['id']
        clip={'id':asset_id,'line_id':line['id'],'speaker':line['speaker'],'text_hash':hashlib.sha256(line['text'].encode()).hexdigest(),
              'source_event_id':line.get('source_event_id'),'bytes':len(audio),'mime':'audio/mpeg','provider':'外部 TTS','model':settings.tts_model,'voice':settings.tts_voice}
        return Result(data={'clips':(data.get('clips',[])+[clip])[-100:],'_assets':(data.get('_assets',[])+[asset])[-100:]},message='外部 TTS 音频已生成并保存。',output={'clip':clip})
