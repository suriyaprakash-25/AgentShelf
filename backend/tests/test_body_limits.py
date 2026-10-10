import asyncio

from fastapi.testclient import TestClient

from app.body_limits import BodySizeLimitMiddleware
from app.main import create_app


def test_json_transport_limit_and_no_input_reflection(db_clean):
    with TestClient(create_app()) as client:
        for path in ["/api/playground/chat", "/api/auth/request-link", "/mcp"]:
            response = client.post(
                path,
                content=b"private-address" * 5000,
                headers={"content-type": "application/json"},
            )
            assert response.status_code == 413
            assert "private-address" not in response.text
            assert response.headers["x-content-type-options"] == "nosniff"


def test_chunked_limit_prevents_downstream_parsing():
    called = []

    async def downstream(scope, receive, send):
        called.append(True)

    async def receive():
        return {"type": "http.request", "body": b"x" * 40, "more_body": True}

    async def send(message):
        called.append(message)

    asyncio.run(
        BodySizeLimitMiddleware(downstream, limit=64)(
            {"type": "http", "method": "POST", "path": "/api/playground/chat", "headers": []},
            receive,
            send,
        )
    )
    assert True not in called
    assert called[0]["status"] == 413
