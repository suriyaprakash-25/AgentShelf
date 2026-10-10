import asyncio

from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import StreamingResponse


def test_sse_is_not_buffered_or_compressed():
    messages = []

    async def app(scope, receive, send):
        async def events():
            yield b"data: " + b"x" * 1024 + b"\n\n"

        await StreamingResponse(events(), media_type="text/event-stream")(scope, receive, send)

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/chat",
        "headers": [(b"accept-encoding", b"gzip")],
        "asgi": {"spec_version": "2.4"},
    }
    asyncio.run(GZipMiddleware(app, minimum_size=512)(scope, receive, send))
    headers = dict(messages[0]["headers"])
    assert b"content-encoding" not in headers
    assert any(b"data: " in message.get("body", b"") for message in messages)
