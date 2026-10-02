"""Filesystem package digests. Reading a manifest/hash never imports plugin Python."""
import hashlib


def package_hash(folder):
    digest=hashlib.sha256()
    for path in sorted(folder.rglob('*')):
        if '__pycache__' in path.parts or path.name.endswith('.pyc'): continue
        if path.is_symlink(): raise ValueError('package symlinks are not allowed')
        if path.is_file(): digest.update(path.relative_to(folder).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()
