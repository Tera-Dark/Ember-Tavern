"""Bound API request bodies before JSON parsing, including chunked uploads."""
from starlette.responses import JSONResponse

MAX_API_BODY_BYTES = 2 * 1024 * 1024


class RequestBodyLimit:
    def __init__(self, app, maximum=MAX_API_BODY_BYTES):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope.get('path', '').startswith('/api/') or scope.get('method') not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        length = headers.get(b'content-length')
        if length:
            try:
                declared = int(length)
                if declared < 0:
                    raise ValueError()
            except ValueError:
                return await JSONResponse({'detail': '无效的 Content-Length'}, status_code=400)(scope, receive, send)
            if declared > self.maximum:
                return await self.reject(scope, receive, send)
        parts, count = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body = message.get('body', b'')
            count += len(body)
            if count > self.maximum:
                return await self.reject(scope, receive, send)
            parts.append(body)
            if not message.get('more_body', False):
                break
        buffered, delivered = b''.join(parts), False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': buffered, 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)

    async def reject(self, scope, receive, send):
        return await JSONResponse({'detail': 'API 请求体不能超过 2 MiB；创作文件另限 512 KiB'}, status_code=413)(scope, receive, send)
