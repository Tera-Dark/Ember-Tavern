import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import uuid
from .config import settings
from .state import load_state


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def uid():
    return uuid.uuid4().hex


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


@contextmanager
def connection():
    con = sqlite3.connect(settings.db_path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with connection() as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
            salt TEXT NOT NULL, guest INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
            expires_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL,
            owner_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
            ai_mode TEXT NOT NULL DEFAULT 'demo', state_json TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0, branch INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS members (
            room_id TEXT NOT NULL REFERENCES rooms(id), user_id TEXT NOT NULL REFERENCES users(id),
            joined_at TEXT NOT NULL, PRIMARY KEY(room_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS assignments (
            room_id TEXT NOT NULL REFERENCES rooms(id), character_id TEXT NOT NULL,
            user_id TEXT NOT NULL REFERENCES users(id),
            PRIMARY KEY(room_id, character_id), UNIQUE(room_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id),
            seq INTEGER NOT NULL, branch INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            type TEXT NOT NULL, actor_id TEXT, actor_name TEXT NOT NULL,
            character_id TEXT, text TEXT NOT NULL, payload_json TEXT NOT NULL,
            snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(room_id, seq)
        );
        CREATE INDEX IF NOT EXISTS events_room_active ON events(room_id, active, seq);
        CREATE TABLE IF NOT EXISTS room_plugins (
            room_id TEXT PRIMARY KEY REFERENCES rooms(id), flags_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS room_access (
            room_id TEXT PRIMARY KEY REFERENCES rooms(id),
            accepting_players INTEGER NOT NULL DEFAULT 1 CHECK(accepting_players IN (0,1))
        );
        CREATE TABLE IF NOT EXISTS guest_invites (
            id TEXT PRIMARY KEY, room_id TEXT NOT NULL REFERENCES rooms(id),
            identity TEXT NOT NULL, identity_key TEXT NOT NULL, key_hash TEXT UNIQUE NOT NULL,
            key_hint TEXT NOT NULL, user_id TEXT REFERENCES users(id), enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, UNIQUE(room_id,identity_key)
        );
        CREATE TABLE IF NOT EXISTS receipts (
            room_id TEXT NOT NULL REFERENCES rooms(id), user_id TEXT NOT NULL REFERENCES users(id),
            request_key TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(room_id, user_id, request_key)
        );
        ''')


def append_event(con, room_id, event_type, text, state=None, actor=None, character_id=None, payload=None):
    room = con.execute('SELECT * FROM rooms WHERE id=?', (room_id,)).fetchone()
    if state is None:
        state = load_state(room['state_json'])
    seq = con.execute('SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE room_id=?', (room_id,)).fetchone()[0]
    event_id, timestamp = uid(), now()
    from .plugin_runtime.manager import manager
    # Preserve concurrent extension updates during an asynchronous GM turn.
    # Rewinds are the sole intentional exception: restore their full snapshot.
    if event_type != 'rewind':
        latest = load_state(room['state_json'])
        for pid, namespace in latest.get('_plugins', {}).items():
            if namespace['revision'] > state.get('_plugins', {}).get(pid, {}).get('revision', -1):
                state.setdefault('_plugins', {})[pid] = namespace
    manager.on_event(con, room, state, {'id': event_id, 'seq': seq, 'type': event_type, 'text': text, 'payload': payload or {}})
    state_json = dump(state)
    con.execute('''INSERT INTO events
        (id,room_id,seq,branch,type,actor_id,actor_name,character_id,text,payload_json,snapshot_json,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (event_id, room_id, seq, room['branch'], event_type,
         actor['id'] if actor else None, actor['display_name'] if actor else '余烬主持',
         character_id, text, dump(payload or {}), state_json, timestamp))
    con.execute('UPDATE rooms SET state_json=?, revision=revision+1, updated_at=? WHERE id=?',
                (state_json, timestamp, room_id))
    return event_id


def event_dict(row):
    return {key: row[key] for key in ('id','seq','branch','type','actor_id','actor_name','character_id','text','created_at')} | {
        'active': bool(row['active']), 'payload': json.loads(row['payload_json'])
    }
