"""Actual socket MCP agent flow; controlled model/provider responses are not acceptance."""

import socket
import threading
import time
import uuid

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import buyer_agent, llm, quotes
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.main import create_app
from app.models import AgentSession, Order, RateBucket
from tests.test_orders import fixture_data

pytestmark = pytest.mark.integration


@pytest.fixture
def socket_server(db_clean, monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    monkeypatch.setattr(get_settings(), "public_api_url", base)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr("controlled-model-fixture"))
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        yield base
    finally:
        server.should_exit = True
        thread.join(10)
        assert not thread.is_alive()


def use(name, arguments, number):
    return {"type": "tool_use", "id": f"tool-{number}", "name": name, "input": arguments}


def test_agent_uses_real_mcp_and_human_confirmation(socket_server, provider, monkeypatch):
    product, session, _ = fixture_data()
    calls = []

    async def model(messages, tools, budget, country):
        assert budget == "60.00" and country == "GB"
        assert {t["name"] for t in tools} == {"search_products", "get_quote", "get_order_status"}
        assert all("session_id" not in t["input_schema"]["properties"] for t in tools)
        calls.append(messages)
        if len(calls) == 1:
            return [use("search_products", {"query": "scarf"}, 1)]
        if len(calls) == 2:
            return [
                use(
                    "get_quote",
                    {
                        "product_id": product,
                        "qty": 1,
                        "ship_to_country": "US",
                        "session_id": str(uuid.uuid4()),
                    },
                    2,
                )
            ]
        if len(calls) == 3:
            return [use("create_checkout", {"quote_id": "fabricated"}, 3)]
        return [{"type": "text", "text": "Review the quote in the interface."}]

    monkeypatch.setattr(llm, "buyer_turn", model)
    response = httpx.post(
        socket_server + "/api/playground/chat",
        json={"session_id": session, "ship_to_country": "GB", "message": "Find a scarf"},
        timeout=40,
    )
    assert response.status_code == 200 and response.headers["content-type"].startswith(
        "text/event-stream"
    )
    import json

    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    review = next(e for e in events if e["type"] == "quote")
    assert review["total"] == "55.00" and review["ship_to_country"] == "GB"
    assert any(
        e.get("result", {}).get("error", {}).get("code") == "CONFIRMATION_REQUIRED" for e in events
    )
    assert events[-1]["type"] == "done" and provider == []
    with session_factory() as db:
        assert db.query(Order).count() == 0
        assert db.get(AgentSession, uuid.UUID(session)).chat_lease is None
    confirmation = httpx.post(
        socket_server + "/api/playground/chat",
        json={
            "session_id": session,
            "ship_to_country": "GB",
            "confirmed_quote_id": review["quote_id"],
        },
        timeout=40,
    )
    assert confirmation.status_code == 200
    confirmed = [
        json.loads(line[6:]) for line in confirmation.text.splitlines() if line.startswith("data: ")
    ]
    assert any(e["type"] == "checkout" for e in confirmed)
    assert confirmed[-1] == {"type": "done"}
    assert sum(e["type"] == "done" for e in confirmed) == 1
    assert len(provider) == 1
    with session_factory() as db:
        assert db.query(Order).count() == 1
        assert db.get(AgentSession, uuid.UUID(session)).pending_quote_id is None
        assert db.get(AgentSession, uuid.UUID(session)).chat_lease is None


def test_concurrent_chat_and_quote_ownership_and_quota(db_clean):
    product, session, _ = fixture_data()
    session_id = uuid.UUID(session)
    first = buyer_agent.acquire(session_id, "Find a scarf", None)
    with pytest.raises(DomainError, match="current reply"):
        buyer_agent.acquire(session_id, "Another request", None)
    buyer_agent.finish(session_id, first, [], None)
    with session_factory() as db, db.begin():
        quote = quotes.get_quote(db, product, 1, "GB", session)
    with pytest.raises(DomainError, match="fresh quote"):
        buyer_agent.acquire(session_id, "", uuid.UUID(quote["quote_id"]))
    with session_factory() as db, db.begin():
        db.get(RateBucket, f"chat:{session}").used = 20
    with pytest.raises(DomainError) as error:
        buyer_agent.acquire(session_id, "Find another scarf", None)
    assert error.value.code == "RATE_LIMITED"


def test_failed_model_releases_lease_without_persisting_partial_tools(socket_server, monkeypatch):
    _, session, _ = fixture_data()

    async def fail(*args):
        raise RuntimeError("provider credential must never appear in output")

    monkeypatch.setattr(llm, "buyer_turn", fail)
    response = httpx.post(
        socket_server + "/api/playground/chat",
        json={"session_id": session, "ship_to_country": "US", "message": "Find a gift"},
        timeout=30,
    )
    assert "CHAT_UNAVAILABLE" in response.text and "credential" not in response.text
    with session_factory() as db:
        buyer = db.get(AgentSession, uuid.UUID(session))
        assert buyer.chat_lease is None and buyer.chat_history == []


def test_chat_missing_provider_and_personal_input_are_safe(db_clean, monkeypatch):
    _, session, _ = fixture_data()
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/playground/chat",
            json={"session_id": session, "ship_to_country": "US", "message": "Find a gift"},
        )
        assert (
            response.status_code == 503 and response.json()["error"]["code"] == "AI_NOT_CONFIGURED"
        )
    state = buyer_agent.acquire(
        uuid.UUID(session), "Find me a handmade silk scarf under $60, ship to London", None
    )
    assert "ship to London" in state["message"]
    buyer_agent.finish(uuid.UUID(session), state, [], None)
    with pytest.raises(DomainError) as error:
        buyer_agent.acquire(uuid.UUID(session), "Ship to 123 Main Street", None)
    assert error.value.code == "PERSONAL_CAPTION"
