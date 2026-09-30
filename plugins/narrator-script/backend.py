import json,re
from fastapi import HTTPException
from server.db import uid
from server.plugin_runtime.sdk import Plugin,Result

def segments(text,event_id=None,speaker='旁白'):
    parts=[x.strip() for x in re.split(r'\n\s*\n',text) if x.strip()]
    return [{'id':uid(),'speaker':speaker,'text':part[:3000],'source_event_id':event_id,'kind':'narration'} for part in parts[:20]]
class Extension(Plugin):
    def initial(self,ctx):
        records=[r for r in ctx.events(30) if r['type'] in ('gm','gm_note','prologue')]
        last=records[-1] if records else None
        return {'lines':segments(last['text'] if last else ctx.state['scene']['text'],last['id'] if last else None)}
    def on_event(self,ctx,event,data):
        if event['type'] not in ('gm','gm_note','prologue'):return None
        return {'lines':(data.get('lines',[])+segments(event['text'],event['id']))[-40:]}
    def resources(self,ctx,data):return {'narration.script/v1':data}
    async def action(self,ctx,name,payload,data):
        ctx.require_owner()
        if name=='rebuild':
            rows=[r for r in ctx.events(80) if r['type'] in ('gm','gm_note','prologue') or (payload.get('include_actions') and r['type']=='action')]
            lines=[]
            for r in rows:lines+=segments(r['text'],r['id'],'旁白' if r['type']!='action' else json.loads(r['payload_json']).get('character_name',r['actor_name']))
            return Result(data={'lines':lines[-40:]},message='已从当前有效时间线重建台本（最多40段）。')
        if name=='edit':
            target=next((x for x in data.get('lines',[]) if x['id']==payload.get('line_id')),None)
            if not target:raise HTTPException(404,'台本片段不存在')
            text=str(payload.get('text','')).strip();speaker=str(payload.get('speaker','旁白')).strip()
            if not text or len(text)>3000 or not speaker or len(speaker)>32:raise HTTPException(422,'台本文本或说话者长度无效')
            target.update(text=text,speaker=speaker,kind='dialogue' if speaker!='旁白' else 'narration')
            return Result(data=data,message='台本已保存；不会改写原剧情事件。')
        raise HTTPException(404,'操作不存在')
