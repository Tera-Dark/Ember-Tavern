import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from ..auth import current_user
from ..db import connection, append_event, event_dict, now
from ..schemas import Rollback
from ..state import load_state
from ..projection import project_event
from ..retrieval import retrieve
from ..runtime import game_lock, get_room_member, check_revision, receipt, save_receipt, finish, pack_room

router = APIRouter()


@router.post('/api/rooms/{room_id}/rollback')
async def rollback(room_id:str,data:Rollback,user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con,room_id,user,True)
            if not receipt(con,room_id,user,data.request_key):
                check_revision(room,data.expected_revision)
                target = con.execute('SELECT * FROM events WHERE room_id=? AND id=? AND active=1',(room_id,data.target_event_id)).fetchone()
                if not target:
                    raise HTTPException(422,'只能回到当前时间线中的历史节点')
                archived = con.execute('SELECT COUNT(*) FROM events WHERE room_id=? AND active=1 AND seq>?',(room_id,target['seq'])).fetchone()[0]
                if archived == 0:
                    raise HTTPException(422,'该节点已经是最新记录，无需回档')
                state = load_state(target['snapshot_json'])
                con.execute('UPDATE events SET active=0 WHERE room_id=? AND active=1 AND seq>?',(room_id,target['seq']))
                con.execute('UPDATE rooms SET branch=branch+1 WHERE id=?',(room_id,))
                append_event(con,room_id,'rewind',f"回到事件 #{target['seq']} 之后的状态。{archived} 条后续记录已封存。原因：{data.reason}",
                             state,user,payload={'target_event_id':target['id'],'target_seq':target['seq'],'archived':archived,'reason':data.reason})
                save_receipt(con,room_id,user,data.request_key)
    return await finish(room_id,user)


@router.get('/api/rooms/{room_id}/context')
def context_search(room_id:str,q:str=Query(default='',max_length=200),user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con,room_id,user)
        state = load_state(room['state_json'])
    return {'query':q,'method':'中文双字词 / 英文词项匹配（非向量检索）','results':retrieve(room_id,state,q,20,include_gm=room['owner_id']==user['id'])}


@router.get('/api/rooms/{room_id}/events')
def events(room_id:str,archived:bool=False,before_seq:int|None=None,user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con,room_id,user,archived)
        rows = con.execute('SELECT * FROM events WHERE room_id=? AND active=? AND seq<? ORDER BY seq DESC LIMIT 200',
                           (room_id,0 if archived else 1,before_seq or 2**62)).fetchall()
    return [project_event(event_dict(row), room['owner_id']==user['id']) for row in rows]


@router.get('/api/rooms/{room_id}/export')
def export(room_id:str,user=Depends(current_user)):
    with connection() as con:
        room = get_room_member(con,room_id,user,True)
        rows = con.execute('SELECT * FROM events WHERE room_id=? ORDER BY seq',(room_id,)).fetchall()
        all_events = [event_dict(r) | {'snapshot':load_state(r['snapshot_json'])} for r in rows]
        lock_row = con.execute('SELECT package_hash FROM room_preset_locks WHERE room_id=?',(room_id,)).fetchone()
        source_bundle = None
        if lock_row:
            from ..presets.library import get_package
            source_bundle = get_package(con,lock_row['package_hash']).envelope()
    data = {'format':'ember-tavern/v1','exported_at':now(),'room':pack_room(room_id,user),'all_events':all_events}
    if source_bundle is not None: data['preset_bundle'] = source_bundle
    return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="ember-session-{room_id[:8]}.json"'})
