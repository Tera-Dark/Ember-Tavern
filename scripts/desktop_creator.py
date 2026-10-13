"""Local desktop creator adapter. No submitted Python/JS is imported or executed.

Only this reviewed tool reads selected draft files. Responses never include
Pydantic input_value, exception text or private content bodies.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import creator
from server.contracts.common import Metadata

KINDS = ('worldbook', 'character', 'theme', 'scenario', 'preset', 'plugin')
FILES = {kind: kind + '.json' for kind in KINDS}
MAX_FILES = 1000
MAX_BYTES = 20 * 1024 * 1024


class DraftError(ValueError):
    def __init__(self, code):
        self.code = code


def ordinary(path):
    if not isinstance(path, (str, Path)) or not Path(path).is_absolute():
        raise DraftError('unsafe_path')
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise DraftError('unsafe_path')
    return path


def inventory(folder, publishing=False):
    folder = ordinary(folder)
    if not folder.is_dir():
        raise DraftError('project_missing')
    files = []
    total = 0
    for path in sorted(folder.rglob('*')):
        ordinary(path)
        if not path.is_file() and not path.is_dir():
            raise DraftError('unsafe_path')
        if not path.is_file():
            continue
        if len(files) >= MAX_FILES:
            raise DraftError('project_too_large')
        total += path.stat().st_size
        if total > MAX_BYTES:
            raise DraftError('project_too_large')
        relative = path.relative_to(folder).as_posix()
        if publishing:
            if (path.name.startswith('.env') and path.name != '.env.example') or '.private.' in path.name or re.search(r'\.(?:db|sqlite3?)(?:$|[-.])',path.name,re.I) or path.suffix.lower() in ('.exe', '.log', '.pem', '.key'):
                raise DraftError('sensitive_file')
            # Known key shapes are rejected, never returned or logged.
            if re.search(rb'(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,})', path.read_bytes()):
                raise DraftError('credential_detected')
        files.append((relative, hashlib.sha256(path.read_bytes()).hexdigest()))
    encoded = json.dumps(files, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def project(folder):
    folder = ordinary(folder)
    revision = inventory(folder)
    entries = [(kind, folder / FILES[kind]) for kind in ('preset', 'plugin') if (folder / FILES[kind]).is_file()]
    if not entries:
        entries = [(kind, folder / FILES[kind]) for kind in KINDS if (folder / FILES[kind]).is_file()]
    if len(entries) != 1:
        raise DraftError('project_entry_ambiguous')
    kind, entry = entries[0]
    if entry.stat().st_size > 512 * 1024:
        raise DraftError('project_too_large')
    document = json.loads(entry.read_text(encoding='utf-8-sig'))
    metadata = document if kind == 'plugin' else document.get('metadata', {})
    # Validate only the common header, so an edited preset with stale component
    # hashes remains openable and can be explicitly re-locked.
    fields = {key: metadata.get(key, default) for key, default in
              [('id', ''), ('name', ''), ('version', '1.0.0'), ('description', ''), ('authors', []), ('license', ''), ('tags', [])]}
    normalized = Metadata.model_validate(fields).model_dump(mode='json')
    return {'kind': kind, 'metadata': normalized, 'revision': revision}, document, entry


def require_revision(folder, expected):
    if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected) or inventory(folder) != expected:
        raise DraftError('source_changed')


def create(kind, destination, identity, name):
    if kind not in creator.KINDS:
        raise DraftError('unsupported_operation')
    destination = ordinary(destination)
    ordinary(destination.parent)
    if destination.exists():
        raise DraftError('output_exists')
    stage = Path(tempfile.mkdtemp(prefix='.ember-create-', dir=destination.parent))
    try:
        creator.scaffold(kind, stage, identity, name)
        if destination.exists():
            raise DraftError('output_exists')
        stage.rename(destination)
    finally:
        # Only the exact owned temporary child is removed, never a draft folder.
        if stage.exists():
            if stage.resolve().parent != destination.parent.resolve() or not stage.name.startswith('.ember-create-'):
                raise DraftError('unsafe_path')
            shutil.rmtree(stage)
    return project(destination)[0]


def package(folder, output, expected):
    folder, output = ordinary(folder), ordinary(output)
    if output.exists() or output.is_relative_to(folder):
        raise DraftError('output_exists')
    require_revision(folder, expected)
    inventory(folder, publishing=True)
    summary, _, entry = project(folder)
    kind = summary['kind']
    if output.suffix.lower() != ('.zip' if kind in ('preset', 'plugin') else '.json'):
        raise DraftError('output_format')
    ordinary(output.parent)
    handle, temporary = tempfile.mkstemp(prefix='.ember-package-', suffix=output.suffix, dir=output.parent)
    os.close(handle)
    temporary = Path(temporary)
    try:
        if kind == 'preset':
            temporary.unlink()  # package_preset requires a new output.
            creator.package_preset(folder, temporary)
        elif kind == 'plugin':
            from scripts.plugins import package as plugin_package
            with contextlib.redirect_stdout(io.StringIO()):
                plugin_package(folder, temporary)
        else:
            creator.validate(entry, kind)
            temporary.write_bytes(entry.read_bytes())
        require_revision(folder, expected)
        raw = temporary.read_bytes()
        with output.open('xb') as stream:
            try:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                stream.close()
                output.unlink()  # Newly created by this call only.
                raise
        return {'kind': kind, 'archive_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    finally:
        temporary.unlink(missing_ok=True)


def operate(request):
    if not isinstance(request, dict):
        raise DraftError('unsupported_operation')
    operation = request.get('operation')
    folder = ordinary(request.get('directory', ''))
    if operation == 'create':
        return create(request.get('kind'), folder, request.get('identity'), request.get('name'))
    summary, document, entry = project(folder)
    kind = summary['kind']
    if operation == 'inspect':
        return summary
    require_revision(folder, request.get('revision'))
    if operation == 'validate':
        result = creator.validate(folder if kind in ('preset', 'plugin') else entry, None if kind in ('preset', 'plugin') else kind)
        return {'kind': kind, 'valid': True, 'package_hash': result.get('package_hash')}
    if operation == 'metadata':
        patch = request.get('metadata')
        allowed = {'name', 'version', 'description', 'authors', 'license', 'tags'}
        if not isinstance(patch, dict) or set(patch) - allowed:
            raise DraftError('metadata_invalid')
        normalized = Metadata.model_validate({**summary['metadata'], **patch}).model_dump(mode='json')
        target = document if kind == 'plugin' else document['metadata']
        target.update({key: normalized[key] for key in allowed if kind != 'plugin' or key != 'tags'})
        require_revision(folder, request['revision'])
        creator.write_json(entry, document)
        return project(folder)[0]
    if operation == 'lock':
        if kind != 'preset':
            raise DraftError('unsupported_operation')
        creator.lock_preset(folder, request.get('refresh_plugins') is True)
        return project(folder)[0]
    if operation == 'publication':
        inventory(folder, publishing=True)
        try:
            result = creator.release_check(folder if kind in ('preset', 'plugin') else entry, None if kind in ('preset', 'plugin') else kind)
        except ValueError as error:
            # These are fixed categories. Never send the exception's user input.
            text = str(error)
            if '发布前检查未通过' not in text:
                raise
            codes = []
            if '署名' in text:
                codes.append('authors_required')
            if '许可' in text:
                codes.append('license_required')
            return {'kind': kind, 'publication_ready': False, 'issues': codes or ['publication_blocked']}
        return {'kind': kind, 'publication_ready': True, 'expected_tag': result['expected_tag'], 'package_hash': result.get('package_hash')}
    if operation == 'package':
        return package(folder, request.get('output', ''), request['revision'])
    raise DraftError('unsupported_operation')


def safe_error(error):
    code = error.code if isinstance(error, DraftError) else 'contract_invalid'
    if isinstance(error, FileExistsError):
        code = 'output_exists'
    if isinstance(error, PermissionError):
        code = 'permission_denied'
    # Only contract field names and numeric indexes; never arbitrary extension
    # names, input values or exception messages.
    allowed = {'metadata', 'id', 'name', 'version', 'description', 'authors', 'license', 'tags', 'world', 'characters', 'scenes', 'theme', 'format', 'plugins', 'lore', 'content', 'visibility'}
    positions = []
    errors = getattr(error, 'errors', None)
    if callable(errors):
        for issue in errors()[:20]:
            path = [part for part in issue.get('loc', ()) if type(part) is int and 0 <= part <= 10000 or isinstance(part, str) and part in allowed]
            if path:
                positions.append('.'.join(map(str, path)))
    return {'ok': False, 'code': code, 'positions': positions}


if __name__ == '__main__':
    try:
        raw = sys.stdin.buffer.read(48 * 1024 + 1)
        if len(raw) > 48 * 1024:
            raise DraftError('request_too_large')
        result = {'ok': True, **operate(json.loads(raw))}
    except Exception as error:
        result = safe_error(error)
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
