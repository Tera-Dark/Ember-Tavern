"""Same-origin WebSocket authentication; no wildcard trust of other preview tenants."""
from urllib.parse import urlsplit
from .config import settings


def websocket_origin_allowed(headers):
    origin = headers.get('origin', '')
    if not origin:
        return True # Non-browser clients must still authenticate and be room members.
    parsed = urlsplit(origin)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        return False
    allowed = {value.strip().rstrip('/') for value in settings.allowed_origins.split(',') if value.strip()}
    if origin.rstrip('/') in allowed:
        return True
    # A reverse proxy must strip client-supplied forwarding headers. See deployment docs.
    hosts = {headers.get('host', '').lower(), headers.get('x-forwarded-host', '').lower()}
    return parsed.netloc.lower() in hosts
