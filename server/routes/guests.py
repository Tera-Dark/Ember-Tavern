"""Named, revocable LAN guest seats; the host owns the server, not the guests."""
import hashlib
import hmac
import secrets
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator

from ..auth import current_user, insert_session, insert_user, user_public
from ..contracts.common import Contract
from ..db import append_event, connection, now, uid
from ..runtime import check_revision, finish, game_lock, get_room_member, hub, receipt, save_receipt, throttle
from ..schemas import Revision

router = APIRouter()


def canonical_identity(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


class Identity(Contract):
    identity: str = Field(min_length=1, max_length=24)

    @field_validator('identity')
    @classmethod
    def readable_identity(cls, value):
        if any(unicodedata.category(c).startswith('C') for c in value):
            raise ValueError('身份不能包含控制字符')
        return value


class GuestJoin(Identity):
    verification_key: str = Field(min_length=24, max_length=80)


class IssueGuest(Revision, Identity):
    pass


def public_invite(row):
    return {key: row[key] for key in ('id', 'identity', 'key_hint', 'user_id', 'created_at')} | {'enabled': bool(row['enabled'])}


@router.get('/api/rooms/{room_id}/guest-access')
def list_guest_access(room_id: str, user=Depends(current_user)):
    with connection() as con:
        get_room_member(con, room_id, user, True)
        return [public_invite(row) for row in con.execute('SELECT * FROM guest_invites WHERE room_id=? ORDER BY created_at', (room_id,))]


@router.post('/api/rooms/{room_id}/guest-access')
async def issue_guest_access(room_id: str, data: IssueGuest, user=Depends(current_user)):
    throttle(('guest-issue', user['id']), 24, 60)
    key = 'ET-' + secrets.token_urlsafe(24)
    issued = None
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            if not receipt(con, room_id, user, data.request_key):
                check_revision(room, data.expected_revision)
                identity_key = canonical_identity(data.identity)
                if identity_key == canonical_identity(user['display_name']):
                    raise HTTPException(422, '请为同伴使用不同于房主的身份')
                existing = con.execute('SELECT * FROM guest_invites WHERE room_id=? AND identity_key=?', (room_id, identity_key)).fetchone()
                if not existing and con.execute('SELECT COUNT(*) FROM guest_invites WHERE room_id=?', (room_id,)).fetchone()[0] >= 11:
                    raise HTTPException(422, '每桌最多管理 11 个访客身份')
                invite_id = existing['id'] if existing else uid()
                key_hash = hashlib.sha256(key.encode()).hexdigest()
                con.execute('''INSERT INTO guest_invites(id,room_id,identity,identity_key,key_hash,key_hint,created_at)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(room_id,identity_key) DO UPDATE SET
                    identity=excluded.identity,key_hash=excluded.key_hash,key_hint=excluded.key_hint,enabled=1''',
                    (invite_id, room_id, data.identity, identity_key, key_hash, '…' + key[-4:], now()))
                append_event(con, room_id, 'system', '房主更新了一位同伴的浏览器入座凭据。', actor=user)
                save_receipt(con, room_id, user, data.request_key)
                issued = public_invite(con.execute('SELECT * FROM guest_invites WHERE id=?', (invite_id,)).fetchone()) | {'verification_key': key}
    return {'room': await finish(room_id, user), 'invite': issued,
            'notice': '密钥仅此一次显示；重复请求不会再显示。丢失请重新生成，旧密钥立即失效。'}


@router.post('/api/rooms/{room_id}/guest-access/{invite_id}/revoke')
async def revoke_guest_access(room_id: str, invite_id: str, data: Revision, user=Depends(current_user)):
    member = None
    async with game_lock(room_id):
        with connection() as con:
            room = get_room_member(con, room_id, user, True)
            if not receipt(con, room_id, user, data.request_key):
                check_revision(room, data.expected_revision)
                invite = con.execute('SELECT * FROM guest_invites WHERE id=? AND room_id=?', (invite_id, room_id)).fetchone()
                if not invite:
                    raise HTTPException(404, '访客身份不存在')
                member = invite['user_id']
                con.execute('UPDATE guest_invites SET enabled=0 WHERE id=?', (invite_id,))
                if member:
                    con.execute('DELETE FROM assignments WHERE room_id=? AND user_id=?', (room_id, member))
                    con.execute('DELETE FROM members WHERE room_id=? AND user_id=?', (room_id, member))
                append_event(con, room_id, 'system', '房主撤销了一位访客的入座凭据。', actor=user)
                save_receipt(con, room_id, user, data.request_key)
    if member:
        await hub.disconnect_user(room_id, member)
    return await finish(room_id, user)


@router.post('/api/auth/guest-join')
async def guest_join(data: GuestJoin, request: Request):
    # Remote identity is not taken from an untrusted forwarded-for header.
    throttle(('guest-login', request.client.host if request.client else 'unknown'), 15, 60)
    key_hash = hashlib.sha256(data.verification_key.encode()).hexdigest()
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        invite = con.execute('SELECT * FROM guest_invites WHERE key_hash=? AND enabled=1', (key_hash,)).fetchone()
        if not invite or not hmac.compare_digest(canonical_identity(data.identity).encode(), invite['identity_key'].encode()):
            raise HTTPException(401, '身份或验证密钥无效，请联系房主')
        room_id = invite['room_id']
        access = con.execute('SELECT accepting_players FROM room_access WHERE room_id=?', (room_id,)).fetchone()
        user = con.execute('SELECT * FROM users WHERE id=?', (invite['user_id'],)).fetchone() if invite['user_id'] else None
        existing = user and con.execute('SELECT 1 FROM members WHERE room_id=? AND user_id=?', (room_id, user['id'])).fetchone()
        if not existing:
            if access and not access[0]:
                raise HTTPException(403, '房主已暂停新成员加入')
            if con.execute('SELECT COUNT(*) FROM members WHERE room_id=?', (room_id,)).fetchone()[0] >= 12:
                raise HTTPException(422, '房间已满')
            if not user:
                user = insert_user(con, 'seat_' + uid()[:20], invite['identity'], secrets.token_urlsafe(32), guest=True)
                con.execute('UPDATE guest_invites SET user_id=? WHERE id=?', (user['id'], invite['id']))
            con.execute('INSERT INTO members VALUES (?,?,?)', (room_id, user['id'], now()))
        token = insert_session(con, user)
    await hub.broadcast(room_id)
    return {'token': token, 'user': user_public(user), 'room_id': room_id}
