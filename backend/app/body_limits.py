"""Bound JSON transports before parsing, including requests without Content-Length."""

from starlette.responses import JSONResponse


class BodySizeLimitMiddleware:
    def __init__(self, app, limit=64 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        bounded = path.startswith(("/api/", "/mcp")) and path != "/api/me/media"
        if (
            scope["type"] != "http"
            or scope.get("method") not in {"POST", "PATCH", "PUT"}
            or not bounded
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length is not None and (
            not length.isdigit() or len(length) > 10 or int(length) > self.limit
        ):
            await self.reject(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                await self.reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def reject(self, scope, receive, send):
        response = JSONResponse(
            {
                "error": {
                    "code": "BODY_TOO_LARGE",
                    "message": "The request exceeds the allowed size.",
                }
            },
            status_code=413,
        )
        await response(scope, receive, send)
