"""Tests for pilot-ready Should features S-1 through S-6."""

import hashlib
import hmac
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select

from app import email, jobs, llm, paypal, storage, whatsapp
from app.config import get_settings
from app.db import session_factory
from app.listing import validate_draft
from app.main import create_app
from app.models import Conversation, Job, Product, Seller, utcnow
from tests.test_listing_workflow import DRAFT
from tests.test_orders import fixture_data
from tests.test_sellers import ORIGIN
from tests.test_tracking import paid_order

pytestmark = pytest.mark.integration
PHONE = "15555550199"


@pytest.fixture
def delivery(monkeypatch):
    sent = []
    monkeypatch.setattr(email, "require_ready", lambda: None)
    monkeypatch.setattr(email, "send_login", lambda recipient, link, key: sent.append(link))
    monkeypatch.setattr(get_settings(), "app_env", "test")
    return sent


def test_agent_discovery_and_schema_org_json_ld(db_clean):
    product_id, _, _ = fixture_data()
    with TestClient(create_app()) as client:
        mcp_doc = client.get("/.well-known/mcp.json")
        assert mcp_doc.status_code == 200
        body = mcp_doc.json()
        assert body["transport"]["type"] == "streamable-http"
        assert body["transport"]["endpoint"].endswith("/mcp")
        assert "search_products" in body["tools"]
        assert "create_checkout" in body["tools"]

        schema_doc = client.get("/api/stores/test/schema.json")
        assert schema_doc.status_code == 200
        schema_body = schema_doc.json()
        assert schema_body["@context"] == "https://schema.org"
        assert schema_body["@type"] == "ItemList"
        first = schema_body["itemListElement"][0]["item"]
        assert first["@type"] == "Product"
        assert first["sku"] == product_id
        assert first["offers"]["priceCurrency"] == "USD"


def test_multi_language_listing_translation_preserves_money(db_clean, monkeypatch):
    product_id, _, _ = fixture_data()
    monkeypatch.setattr(
        llm,
        "translate_listing",
        lambda title, description, lang: {
            "title": "Bufanda Indigo",
            "description": "Algodon impreso a mano en Jaipur.",
            "language": lang,
        },
    )
    with TestClient(create_app()) as client:
        res = client.get(f"/api/products/{product_id}/translate?lang=es")
        assert res.status_code == 200
        payload = res.json()
        assert payload["title"] == "Bufanda Indigo"
        assert payload["language"] == "es"
        assert payload["source_title"] == "Scarf"
        assert payload["price"] == "45.00"
        assert payload["currency"] == "USD"
        assert payload["in_stock"] is True


def test_seller_copilot_summary_invoice_refund_and_catalog_mirror(
    db_clean, delivery, provider, monkeypatch
):
    order_id, seller_id, _ = paid_order(provider)
    with session_factory() as db, db.begin():
        seller = db.get(Seller, seller_id)
        seller.email = "seller@example.invalid"
        product = db.scalar(select(Product).where(Product.seller_id == seller_id))
        product_id = str(product.id)

    monkeypatch.setattr(
        paypal,
        "refund_capture",
        lambda capture_id, amount_minor, currency, request_id: {
            "id": "REFUND-123",
            "status": "COMPLETED",
        },
    )
    monkeypatch.setattr(
        paypal,
        "create_and_send_invoice",
        lambda seller, recipient_email, amount_minor, currency, note, request_id: {
            "invoice_id": "INV2-ABCD-1234",
            "status": "SENT",
        },
    )
    monkeypatch.setattr(
        paypal,
        "sync_catalog_product",
        lambda product: {
            "paypal_product_id": f"AGENTSHELF-{str(product.id).replace('-', '')[:24]}",
            "status": "SYNCED",
        },
    )
    with TestClient(create_app(), base_url="https://testserver") as client:
        assert (
            client.post(
                "/api/auth/request-link",
                headers=ORIGIN,
                json={"email": "seller@example.invalid"},
            ).status_code
            == 202
        )
        token = delivery[-1].split("#sign-in=")[1]
        assert (
            client.post("/api/auth/redeem", headers=ORIGIN, json={"token": token}).status_code
            == 200
        )
        me = client.get("/api/me").json()
        headers = {**ORIGIN, "x-csrf-token": me["csrf_token"]}

        summary = client.get("/api/me/copilot/summary")
        assert summary.status_code == 200
        assert summary.json()["paid_or_shipped_orders"] == 1
        assert summary.json()["gross_paid_minor"] == 5500
        assert "7-day summary" in summary.json()["summary"]

        catalog_sync = client.post(
            f"/api/me/products/{product_id}/paypal-catalog",
            headers=headers,
            json={},
        )
        assert catalog_sync.status_code == 200
        assert catalog_sync.json()["paypal_product_id"].startswith("AGENTSHELF-")

        invoice = client.post(
            "/api/me/copilot/invoices",
            headers=headers,
            json={
                "recipient_email": "buyer@example.invalid",
                "amount_minor": 6500,
                "note": "Custom indigo quilt",
                "confirm": True,
            },
        )
        assert invoice.status_code == 200
        assert invoice.json()["invoice_id"] == "INV2-ABCD-1234"
        assert invoice.json()["amount"] == "65.00"
        assert invoice.json()["currency"] == "USD"

        refund = client.post(
            f"/api/me/orders/{order_id}/refund",
            headers=headers,
            json={"confirm": True},
        )
        assert refund.status_code == 200
        assert refund.json()["status"] == "refunded"
        assert refund.json()["refund_id"] == "REFUND-123"


def test_whatsapp_voice_note_and_copilot_commands(db_clean, monkeypatch, tmp_path):
    messages, links = [], []
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", SecretStr("signed-message-fixture"))
    monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr("model-fixture"))
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(email, "require_ready", lambda: None)
    monkeypatch.setattr(email, "send_login", lambda address, link, key: links.append(link))
    monkeypatch.setattr(whatsapp, "send_text", lambda phone, text: messages.append((phone, text)))
    monkeypatch.setattr(llm, "draft_listing", lambda *args: validate_draft(DRAFT))
    monkeypatch.setattr(
        llm,
        "transcribe_voice_note",
        lambda audio_bytes, mime="audio/ogg": "Hand-loomed indigo scarf with soft fringe",
    )
    monkeypatch.setattr(whatsapp, "download_audio", lambda media_id: b"OggS-voice-bytes")
    raw_img = io.BytesIO()
    Image.new("RGB", (40, 40), "blue").save(raw_img, format="PNG")
    monkeypatch.setattr(whatsapp, "download_image", lambda key: raw_img.getvalue())
    monkeypatch.setattr(
        paypal,
        "create_and_send_invoice",
        lambda *args, **kwargs: {"invoice_id": "INV2-WA-999", "status": "SENT"},
    )

    def post_wa(client, msg_payload):
        raw = json.dumps(
            {"entry": [{"changes": [{"value": {"messages": [msg_payload]}}]}]}
        ).encode()
        sig = "sha256=" + hmac.new(b"signed-message-fixture", raw, hashlib.sha256).hexdigest()
        assert (
            client.post(
                "/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": sig}
            ).status_code
            == 200
        )
        for _ in range(10):
            if not jobs.run_one():
                with session_factory() as db, db.begin():
                    pending = db.scalar(select(Job).where(Job.status == "queued"))
                    if not pending:
                        break
                    pending.run_after = utcnow()

    with TestClient(create_app()) as client:
        for idx, text in enumerate(
            [
                "help",
                "Jaipur Loom",
                "IN",
                "wa-seller@example.invalid",
                "wa-payee@example.invalid",
                "YES",
            ]
        ):
            post_wa(
                client,
                {"from": PHONE, "id": f"WA-INIT-{idx}", "type": "text", "text": {"body": text}},
            )
        token = links[-1].split("#sign-in=")[1]
        assert (
            client.post("/api/auth/redeem", headers=ORIGIN, json={"token": token}).status_code
            == 200
        )

        post_wa(
            client,
            {"from": PHONE, "id": "WA-VOICE-1", "type": "audio", "audio": {"id": "999"}},
        )
        assert "Voice note transcribed" in messages[-1][1]
        with session_factory() as db:
            conv = db.get(Conversation, PHONE)
            assert "Hand-loomed indigo scarf" in conv.context["voice_caption"]

        post_wa(
            client,
            {"from": PHONE, "id": "WA-SUM-1", "type": "text", "text": {"body": "summary"}},
        )
        assert "7-day summary" in messages[-1][1]

        post_wa(
            client,
            {
                "from": PHONE,
                "id": "WA-INV-1",
                "type": "text",
                "text": {"body": "invoice buyer@example.invalid 42.50 Custom runner"},
            },
        )
        assert "INV2-WA-999" in messages[-1][1]


def test_mcp_client_config_template_is_valid():
    config_path = Path(__file__).resolve().parents[2] / "evals" / "mcp_client_config.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert data["mcpServers"]["agentshelf-local"]["transport"] == "streamable-http"
    assert data["mcpServers"]["agentshelf-local"]["url"].endswith("/mcp")


def test_gemini_provider_support_across_all_ai_boundaries(monkeypatch):
    import asyncio

    import httpx

    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("gemini-fixture-key"))
    monkeypatch.setattr(settings, "gemini_model", "gemini-flash-latest")

    with TestClient(create_app()) as client:
        assert client.get("/api/capabilities").json()["ai_configured"] is True

    calls = []

    class FakeSyncClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, headers=None, json=None):
            calls.append((url, headers, json))
            if "schema" in str(json):
                payload = DRAFT
            elif "target_language" in str(json):
                payload = {"title": "Echarpe Indigo", "description": "Coton doux"}
            else:
                payload = "Handcrafted indigo cotton scarf"
            text = payload if isinstance(payload, str) else __import__("json").dumps(payload)
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
                request=httpx.Request("POST", url),
            )

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers=None, json=None):
            calls.append((url, headers, json))
            if "tools" in (json or {}):
                parts = [
                    {"text": "Checking catalog"},
                    {"functionCall": {"name": "search_products", "args": {"query": "scarf"}}},
                ]
            else:
                parts = [{"text": "Gross orders total 55.00 USD."}]
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": parts}}]},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "Client", FakeSyncClient)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    draft = llm.draft_listing([b"jpeg-bytes"], "Indigo scarf")
    assert draft.category == DRAFT["category"]
    assert "gemini-flash-latest:generateContent" in calls[-1][0]
    assert calls[-1][1]["X-goog-api-key"] == "gemini-fixture-key"

    voice_text = llm.transcribe_voice_note(b"ogg-bytes", "audio/ogg")
    assert "Handcrafted indigo" in voice_text

    translated = llm.translate_listing("Indigo Scarf", "Soft cotton", "fr")
    assert translated["title"] == "Echarpe Indigo"
    assert translated["language"] == "fr"

    blocks = asyncio.run(
        llm.buyer_turn(
            [{"role": "user", "content": "Find a scarf"}],
            [
                {
                    "name": "search_products",
                    "description": "Search",
                    "input_schema": {"properties": {"query": {"type": "string"}}},
                }
            ],
            "60.00",
            "GB",
        )
    )
    assert blocks[0] == {"type": "text", "text": "Checking catalog"}
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["name"] == "search_products"

    summary = asyncio.run(llm.analytics_summary("How are sales?", '{"orders": []}'))
    assert "55.00 USD" in summary
