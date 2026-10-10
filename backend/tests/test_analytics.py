import json

import pytest
from fastapi.testclient import TestClient

from app import email, llm
from app.main import create_app
from tests.test_sellers import login

pytestmark = pytest.mark.integration


def test_analytics_scope_csrf_and_no_client_supplied_facts(db_clean, monkeypatch):
    delivered = []
    monkeypatch.setattr(email, "require_ready", lambda: None)
    monkeypatch.setattr(email, "send_login", lambda address, link, key: delivered.append(link))
    seen = []

    async def analyst(question, facts):
        seen.append(json.loads(facts))
        return "Your store has two available units."

    monkeypatch.setattr(llm, "analytics_summary", analyst)
    with (
        TestClient(create_app(), base_url="https://testserver") as owner,
        TestClient(create_app(), base_url="https://testserver") as other,
    ):
        assert owner.get("/api/me/analytics").status_code == 401
        _, headers, _ = login(owner, delivered)
        login(other, delivered, "other@example.invalid")
        assert (
            owner.post(
                "/api/me/products",
                headers=headers,
                json={
                    "title": "Scarf",
                    "description": "Blue scarf",
                    "price_minor": 4500,
                    "stock": 2,
                },
            ).status_code
            == 201
        )
        result = owner.get("/api/me/analytics")
        assert result.headers["cache-control"] == "no-store"
        assert result.json()["products"] == [{"status": "draft", "count": 1, "available_stock": 2}]
        assert other.get("/api/me/analytics").json()["products"] == []
        assert (
            owner.post("/api/me/analytics/chat", json={"message": "Summarize my shop"}).status_code
            == 403
        )
        assert (
            owner.post(
                "/api/me/analytics/chat",
                headers=headers,
                json={"message": "Summarize my shop", "facts": "invented"},
            ).status_code
            == 422
        )
        assert (
            owner.post(
                "/api/me/analytics/chat",
                headers=headers,
                json={"message": "My email is buyer@example.invalid"},
            ).status_code
            == 400
        )
        reply = owner.post(
            "/api/me/analytics/chat", headers=headers, json={"message": "Summarize my shop"}
        )
        assert reply.status_code == 200
        assert seen[0]["products"][0]["available_stock"] == 2
        assert "Scarf" not in json.dumps(seen)
        assert "@" not in json.dumps(seen)
