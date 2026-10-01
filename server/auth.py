import hashlib
import hmac
import secrets
import time
from fastapi import HTTPException, Header
from .config import settings
from .db import connection, uid, now


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()


def named_guest(user):
    return bool(user['guest']) and user['username'].startswith('seat_')


def user_public(user):
    return {'id': user['id'], 'username': user['username'], 'display_name': user['display_name'], 'guest': bool(user['guest']), 'guest_kind': 'room' if named_guest(user) else ('demo' if user['guest'] else '')}


def insert_user(con, username, display_name, password, guest=False):
    salt = secrets.token_hex(16)
    user_id = uid()
    encoded = password_hash(password, salt)
    con.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?)',
                (user_id, username.lower(), display_name, encoded, salt, int(guest), now()))
    return dict(con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())


def create_user(username, display_name, password, guest=False):
    with connection() as con:
        return insert_user(con, username, display_name, password, guest)


def insert_session(con, user):
    token = secrets.token_urlsafe(40)
    con.execute('DELETE FROM sessions WHERE expires_at<?', (time.time(),))
    con.execute('INSERT INTO sessions VALUES (?,?,?)',
                (hashlib.sha256(token.encode()).hexdigest(), user['id'], time.time() + settings.session_hours * 3600))
    return token


def issue_session(user):
    with connection() as con:
        return insert_session(con, user)


def user_from_token(token):
    if not token or len(token) > 200:
        return None
    with connection() as con:
        row = con.execute('''SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
            WHERE s.token_hash=? AND s.expires_at>?''',
            (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    return dict(row) if row else None


def session_token(authorization='', x_ember_session=''):
    # Some access gateways consume Authorization; prefer the explicit app header.
    return x_ember_session or (authorization[7:] if authorization.startswith('Bearer ') else '')


def current_user(authorization: str = Header(default=''), x_ember_session: str = Header(default='')):
    token = session_token(authorization, x_ember_session)
    if not token:
        raise HTTPException(401, '请先登录')
    user = user_from_token(token)
    if not user:
        raise HTTPException(401, '登录已过期，请重新登录')
    return user


def verify_password(user, password):
    return hmac.compare_digest(user['password_hash'], password_hash(password, user['salt']))
