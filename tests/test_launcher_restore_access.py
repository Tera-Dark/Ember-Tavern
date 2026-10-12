import sqlite3
from scripts.launcher_restore_access import prepare
import pytest


def database(path, current=False):
    con = sqlite3.connect(path)
    con.executescript('''
    CREATE TABLE users(id TEXT PRIMARY KEY, password_hash TEXT);
    CREATE TABLE rooms(id TEXT PRIMARY KEY, owner_id TEXT, state_json TEXT);
    CREATE TABLE members(room_id TEXT, user_id TEXT);
    CREATE TABLE assignments(room_id TEXT, character_id TEXT, user_id TEXT);
    CREATE TABLE sessions(token_hash TEXT, user_id TEXT);
    CREATE TABLE room_access(room_id TEXT, accepting_players INTEGER);
    CREATE TABLE guest_invites(id TEXT, enabled INTEGER);
    ''')
    con.executemany('INSERT INTO users VALUES (?,?)', [('owner', 'current-password' if current else 'old-password'), ('removed-player', 'historical-password')])
    con.execute('INSERT INTO rooms VALUES (?,?,?)', ('room', 'owner', '{"schema_version":4,"_preset_lock":{"hash":"unchanged"}}'))
    con.executemany('INSERT INTO members VALUES (?,?)', [('room', 'owner'), ('room', 'removed-player')])
    con.execute('INSERT INTO assignments VALUES (?,?,?)', ('room', 'character', 'removed-player'))
    con.execute('INSERT INTO sessions VALUES (?,?)', ('old-private-session', 'removed-player'))
    con.execute('INSERT INTO room_access VALUES (?,?)', ('room', 1))
    con.execute('INSERT INTO guest_invites VALUES (?,?)', ('revoked-after-backup', 1))
    con.commit()
    con.close()


def test_restored_new_instance_requires_owner_review_without_reviving_access_or_changing_plot(tmp_path):
    source, target = tmp_path/'原数据 # source.sqlite3', tmp_path/'恢复 restored.sqlite3'
    database(source, True)
    database(target)
    before = source.read_bytes()
    prepare(source, target)
    assert source.read_bytes() == before
    with sqlite3.connect(target) as con:
        assert con.execute('SELECT state_json FROM rooms').fetchone()[0] == '{"schema_version":4,"_preset_lock":{"hash":"unchanged"}}'
        assert con.execute('SELECT password_hash FROM users WHERE id="owner"').fetchone()[0] == 'current-password'
        assert con.execute('SELECT user_id FROM members').fetchall() == [('owner',)]
        assert con.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM assignments').fetchone()[0] == 0
        assert con.execute('SELECT enabled FROM guest_invites').fetchone()[0] == 0
        assert con.execute('SELECT accepting_players FROM room_access').fetchone()[0] == 0


def test_restore_access_refuses_missing_current_owner_and_rolls_back_target(tmp_path):
    source, target = tmp_path/'source.sqlite3', tmp_path/'target.sqlite3'
    database(source, True)
    database(target)
    with sqlite3.connect(source) as con:
        con.execute('DELETE FROM users WHERE id="owner"')
    with pytest.raises(ValueError):
        prepare(source, target)
    with sqlite3.connect(target) as con:
        assert con.execute('SELECT password_hash FROM users WHERE id="owner"').fetchone()[0] == 'old-password'
        assert con.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 1
    with pytest.raises(ValueError):
        prepare(source, source)
