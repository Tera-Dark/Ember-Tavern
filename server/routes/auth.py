import hashlib
import secrets
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Request
from ..auth import current_user, create_user, issue_session, user_public, verify_password, password_hash, session_token
from ..config import settings
from ..db import connection
from ..schemas import Register, Login, RoomCreate
from ..runtime import throttle, hub
from ..room_service import create_room

router = APIRouter()


@router.post('/api/auth/register',status_code=201)
def register(data:Register,request:Request):
    throttle(('register',request.client.host),10,300)
    try:
        user = create_user(data.username,data.display_name,data.password)
    except sqlite3.IntegrityError:
        raise HTTPException(409,'用户名已被使用')
    return {'token':issue_session(user),'user':user_public(user)}


@router.post('/api/auth/login')
def login(data:Login,request:Request):
    throttle(('login',request.client.host),20,300)
    with connection() as con:
        row = con.execute('SELECT * FROM users WHERE username=? AND guest=0',(data.username.lower(),)).fetchone()
    user = dict(row) if row else None
    if user is None:
        password_hash(data.password,'0'*32)
    if user is None or not verify_password(user,data.password):
        raise HTTPException(401,'用户名或密码错误')
    return {'token':issue_session(user),'user':user_public(user)}


@router.post('/api/auth/demo')
def demo(request:Request):
    if not settings.enable_demo:
        raise HTTPException(403,'此部署未开启游客试玩')
    throttle(('demo',request.client.host),10,300)
    suffix = secrets.token_hex(3)
    user = create_user('guest_'+suffix,'旅人·'+suffix[:4].upper(),secrets.token_urlsafe(24),guest=True)
    room_id = create_room(user,RoomCreate(title='雾港的第一夜'))
    return {'token':issue_session(user),'user':user_public(user),'room_id':room_id}


@router.get('/api/auth/me')
def me(user=Depends(current_user)):
    return user_public(user)


@router.post('/api/auth/logout')
async def logout(request:Request,user=Depends(current_user)):
    raw = session_token(request.headers.get('authorization',''),request.headers.get('x-ember-session',''))
    with connection() as con:
        con.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(raw.encode()).hexdigest(),))
    await hub.disconnect_session(raw)
    return {'ok':True}
