import hashlib
import hmac
import secrets
import time
from fastapi import HTTPException, Header
from .config import settings
from .db import connection, uid, now


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()


def user_public(user):
    return {'id': user['id'], 'username': user['username'], 'display_name': user['display_name'], 'guest': bool(user['guest'])}


def create_user(username, display_name, password, guest=False):
    salt = secrets.token_hex(16)
    user_id = uid()
    encoded = password_hash(password, salt)
    with connection() as con:
        con.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?)',
                    (user_id, username.lower(), display_name, encoded, salt, int(guest), now()))
        user = con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    return dict(user)


def issue_session(user):
    token = secrets.token_urlsafe(40)
    with connection() as con:
        con.execute('DELETE FROM sessions WHERE expires_at<?', (time.time(),))
        con.execute('INSERT INTO sessions VALUES (?,?,?)',
                    (hashlib.sha256(token.encode()).hexdigest(), user['id'], time.time() + settings.session_hours * 3600))
    return token


def user_from_token(token):
    if not token or len(token) > 200:
        return None
    with connection() as con:
        row = con.execute('''SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
            WHERE s.token_hash=? AND s.expires_at>?''',
            (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    return dict(row) if row else None


def current_user(authorization: str = Header(default='')):
    if not authorization.startswith('Bearer '):
        raise HTTPException(401, '请先登录')
    user = user_from_token(authorization[7:])
    if not user:
        raise HTTPException(401, '登录已过期，请重新登录')
    return user


def verify_password(user, password):
    return hmac.compare_digest(user['password_hash'], password_hash(password, user['salt']))
