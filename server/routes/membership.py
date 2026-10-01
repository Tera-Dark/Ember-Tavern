"""Membership and invitation settings are operational, not rewindable story state."""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..db import append_event, connection
from ..room_service import invitation_code
from ..runtime import check_revision, finish, game_lock, get_room_member, hub, receipt, save_receipt
from ..schemas import Revision

router = APIRouter()


class Invitation(Revision):
    accepting_players: bool
    rotate_code: bool = False


@router.post('/api/rooms/{room_id}/invitation')
async def invitation(room_id: str, data: Invitation, user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            if not receipt(con, room_id, user, data.request_key):
                check_revision(room, data.expected_revision)
                con.execute('INSERT INTO room_access VALUES (?,?) ON CONFLICT(room_id) DO UPDATE SET accepting_players=excluded.accepting_players',
                            (room_id, int(data.accepting_players)))
                if data.rotate_code:
                    con.execute('UPDATE rooms SET code=? WHERE id=?', (invitation_code(con), room_id))
                message = '房主已' + ('开放' if data.accepting_players else '暂停') + '新成员加入。'
                if data.rotate_code:
                    message += '旧邀请码已失效，现有成员不受影响。'
                append_event(con, room_id, 'system', message, actor=user)
                save_receipt(con, room_id, user, data.request_key)
    return await finish(room_id, user)


@router.post('/api/rooms/{room_id}/members/{member_id}/remove')
async def remove_member(room_id: str, member_id: str, data: Revision, user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            if member_id == room['owner_id']:
                raise HTTPException(422, '不能移除房主')
            if not receipt(con, room_id, user, data.request_key):
                check_revision(room, data.expected_revision)
                target = con.execute('SELECT 1 FROM members WHERE room_id=? AND user_id=?', (room_id, member_id)).fetchone()
                if not target:
                    raise HTTPException(404, '成员不在该房间')
                con.execute('DELETE FROM assignments WHERE room_id=? AND user_id=?', (room_id, member_id))
                con.execute('DELETE FROM members WHERE room_id=? AND user_id=?', (room_id, member_id))
                append_event(con, room_id, 'system', '房主移除了一位成员，相关角色已解除分配。', actor=user)
                save_receipt(con, room_id, user, data.request_key)
    await hub.disconnect_user(room_id, member_id)
    return await finish(room_id, user)


@router.post('/api/rooms/{room_id}/leave')
async def leave_room(room_id: str, data: Revision, user=Depends(current_user)):
    async with game_lock(room_id):
        with connection() as con:
            if not receipt(con, room_id, user, data.request_key):
                room = get_room_member(con, room_id, user)
                if room['owner_id'] == user['id']:
                    raise HTTPException(422, '房主不能直接退出；可暂停邀请并继续保留冒险')
                check_revision(room, data.expected_revision)
                con.execute('DELETE FROM assignments WHERE room_id=? AND user_id=?', (room_id, user['id']))
                con.execute('DELETE FROM members WHERE room_id=? AND user_id=?', (room_id, user['id']))
                append_event(con, room_id, 'system', '一位成员离开了房间，相关角色已解除分配。', actor=user)
                save_receipt(con, room_id, user, data.request_key)
    await hub.disconnect_user(room_id, user['id'])
    await hub.broadcast(room_id)
    return {'left': True, 'room_id': room_id}
