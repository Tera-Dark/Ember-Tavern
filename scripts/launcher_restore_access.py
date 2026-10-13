"""Prepare a restored NEW instance for owner review. Never touches the source DB.

Keeps plot/version locks and historical users, but does not resurrect sessions,
player membership, assignments or invitation permissions from a backup.
"""
import argparse
import json
from pathlib import Path
import sqlite3


def prepare(source, target):
    source, target = Path(source), Path(target)
    if source.is_symlink() or target.is_symlink() or not source.is_file() or not target.is_file():
        raise ValueError('Source and target must be ordinary databases')
    source, target = source.resolve(strict=True), target.resolve(strict=True)
    if source == target:
        raise ValueError('Source and target must be different ordinary databases')
    src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    dst = sqlite3.connect(target)
    src.row_factory = dst.row_factory = sqlite3.Row
    try:
        if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed')
        tables = {row[0] for row in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'users', 'rooms', 'members', 'assignments', 'sessions'}.issubset(tables):
            raise ValueError('Restored host account schema is unsupported')
        columns = [row[1] for row in dst.execute('PRAGMA table_info(users)')]
        source_columns = {row[1] for row in src.execute('PRAGMA table_info(users)')}
        if not set(columns).issubset(source_columns):
            raise ValueError('Source owner schema is incompatible')
        # Identifiers come only from SQLite schema, quoted rather than interpolated
        # as expressions. Values always use parameters; no plugin import / execution.
        quoted = ','.join('"' + value.replace('"', '""') + '"' for value in columns)
        with dst:
            owners = {row[0] for row in dst.execute('SELECT DISTINCT owner_id FROM rooms')}
            if len(owners) > 10000:
                raise ValueError('Too many restored owners')
            for owner in owners:
                current = src.execute('SELECT ' + quoted + ' FROM users WHERE id=?', (owner,)).fetchone()
                if current is None:
                    raise ValueError('Restored owner no longer exists in current source; original data preserved')
                updates = ','.join('"' + value.replace('"', '""') + '"=?' for value in columns if value != 'id')
                dst.execute('UPDATE users SET ' + updates + ' WHERE id=?', (*[current[value] for value in columns if value != 'id'], owner))
            dst.execute('DELETE FROM sessions')
            dst.execute('DELETE FROM assignments')
            dst.execute('DELETE FROM members WHERE NOT EXISTS (SELECT 1 FROM rooms r WHERE r.id=members.room_id AND r.owner_id=members.user_id)')
            if 'guest_invites' in tables:
                dst.execute('UPDATE guest_invites SET enabled=0')
            if 'room_access' in tables:
                dst.execute('UPDATE room_access SET accepting_players=0')
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Prepared database failed integrity check')
        return {'prepared': True, 'sessions': 'cleared', 'admission': 'owner-review-required'}
    finally:
        dst.close()
        src.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.source, args.target)))
    except Exception:
        raise SystemExit('Restored access could not be safely prepared; original instance unchanged')
