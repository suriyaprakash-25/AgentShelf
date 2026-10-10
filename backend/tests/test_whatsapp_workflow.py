"""Signed inbox through real DB/worker state; external messages and models are mocked."""

import hashlib
import hmac
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select

from app import email, jobs, llm, paypal, storage, whatsapp
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.listing import validate_draft
from app.main import create_app
from app.models import Conversation, Job, ListingRequest, Product, Seller, utcnow
from tests.test_listing_workflow import DRAFT
from tests.test_orders import fixture_data
from tests.test_sellers import ORIGIN
from tests.test_tracking import confirmation, paid_order

pytestmark = pytest.mark.integration
PHONE = "15555550101"


@pytest.fixture
def channels(monkeypatch, tmp_path):
    messages, links = [], []
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", SecretStr("signed-message-fixture"))
    monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr("model-fixture"))
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(email, "require_ready", lambda: None)
    monkeypatch.setattr(email, "send_login", lambda address, link, key: links.append(link))
    monkeypatch.setattr(whatsapp, "send_text", lambda phone, text: messages.append((phone, text)))
    monkeypatch.setattr(llm, "draft_listing", lambda *args: validate_draft(DRAFT))
    return messages, links


def send(client, text, number, image=False, phone=PHONE):
    message = {"from": phone, "id": f"MESSAGE-{number}", "type": "image" if image else "text"}
    message["image" if image else "text"] = (
        {"id": "123", "caption": text} if image else {"body": text}
    )
    raw = json.dumps({"entry": [{"changes": [{"value": {"messages": [message]}}]}]}).encode()
    signature = "sha256=" + hmac.new(b"signed-message-fixture", raw, hashlib.sha256).hexdigest()
    for _ in range(2):
        assert (
            client.post(
                "/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": signature}
            ).status_code
            == 200
        )
    for _ in range(15):
        if not jobs.run_one():
            with session_factory() as db, db.begin():
                pending = db.scalar(
                    select(Job).where(Job.kind == "listing_draft", Job.status == "queued")
                )
                if not pending:
                    break
                pending.run_after = utcnow()
    else:
        pytest.fail("Worker did not drain bounded fixture jobs")


def test_email_verified_onboarding_photo_yes_and_live_edits(db_clean, channels, monkeypatch):
    messages, links = channels
    raw = io.BytesIO()
    Image.new("RGB", (40, 40), "blue").save(raw, format="PNG")
    monkeypatch.setattr(whatsapp, "download_image", lambda key: raw.getvalue())
    with TestClient(create_app()) as client:
        for i, text in enumerate(
            [
                "help",
                "Blue textiles",
                "IN",
                "seller@example.invalid",
                "payee@example.invalid",
                "YES",
            ]
        ):
            send(client, text, i)
        with session_factory() as db:
            assert db.scalar(select(Seller)) is None
        assert len(links) == 1
        token = links[0].split("#sign-in=")[1]
        assert (
            client.post("/api/auth/redeem", headers=ORIGIN, json={"token": token}).status_code
            == 200
        )
        with session_factory() as db:
            seller = db.scalar(select(Seller))
            assert seller.whatsapp_phone == PHONE and not seller.live_eligible
            seller_id = seller.id
        send(client, "help", 10)
        assert "/mcp" in messages[-1][1] and "/s/store-" in messages[-1][1]
        send(client, "Blue scarf", 11, image=True)
        with session_factory() as db:
            assert db.query(Product).count() == 0
            assert db.get(Conversation, PHONE).state == "review"
        assert "Suggested price only" in messages[-1][1]
        send(client, "YES", 12)
        assert "First set" in messages[-1][1]
        send(client, "price 39", 13)
        send(client, "stock 2", 14)
        send(client, "YES", 15)
        with session_factory() as db:
            product = db.scalar(select(Product))
            assert (
                product.seller_id == seller_id
                and product.price_minor == 3900
                and product.stock == 2
                and product.status == "live"
            )
            number = product.short_no
        send(client, f"price 41 #{number}", 16)
        send(client, f"stock 0 #{number}", 17)
        send(client, f"remove #{number}", 18)
        with session_factory() as db:
            product = db.scalar(select(Product))
            assert (
                product.price_minor == 4100 and product.stock == 0 and product.status == "archived"
            )
            assert all(job.status == "done" for job in db.scalars(select(Job)))
        # Duplicate signed inbox messages never repeat a completed local command.
        assert len(messages) == 16


def test_signed_sender_tracking_is_seller_scoped(db_clean, channels, provider, monkeypatch):
    messages, _ = channels
    order_id, seller_id, provider_id = paid_order(provider)
    with session_factory() as db, db.begin():
        db.get(Seller, seller_id).whatsapp_phone = PHONE
    monkeypatch.setattr(paypal, "request", lambda *args: confirmation(provider_id))
    with TestClient(create_app()) as client:
        send(client, "orders", 30)
        assert str(order_id)[:8] in messages[-1][1]
        send(client, f"track #{str(order_id)[:8]} DHL 12345", 31)
        assert "Tracking verified" in messages[-1][1]
        send(client, f"track #{str(order_id)[:8]} DHL 12345", 32, phone="15555550102")
        assert "store name" in messages[-1][1]


def test_photos_sent_together_share_one_reviewed_draft(db_clean, channels, monkeypatch):
    fixture_data()
    with session_factory() as db, db.begin():
        db.scalar(select(Seller)).whatsapp_phone = PHONE
    image = io.BytesIO()
    Image.new("RGB", (40, 40), "blue").save(image, format="PNG")
    monkeypatch.setattr(whatsapp, "download_image", lambda key: image.getvalue())
    counts = []

    def vision(images, caption):
        counts.append(len(images))
        return validate_draft(DRAFT)

    monkeypatch.setattr(llm, "draft_listing", vision)
    raw = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": PHONE,
                                        "id": f"PHOTO-{i}",
                                        "type": "image",
                                        "image": {"id": str(100 + i)},
                                    }
                                    for i in range(2)
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()
    signature = "sha256=" + hmac.new(b"signed-message-fixture", raw, hashlib.sha256).hexdigest()
    with TestClient(create_app()) as client:
        assert (
            client.post(
                "/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": signature}
            ).status_code
            == 200
        )
    assert jobs.run_one() and jobs.run_one()
    with session_factory() as db, db.begin():
        listing = db.scalar(select(ListingRequest))
        assert len(listing.media_ids) == 2 and db.query(ListingRequest).count() == 1
        db.scalar(select(Job).where(Job.kind == "listing_draft")).run_after = utcnow()
    for _ in range(8):
        if not jobs.run_one():
            break
    assert counts == [2]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "https://attacker.invalid/a",
        "https://lookaside.fbsbx.com@attacker.invalid/a",
    ],
)
def test_media_boundary_rejects_credential_leak_hosts(monkeypatch, url):
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", SecretStr("private-test-token"))
    actual_client = httpx.Client
    requests = []

    def handle(request):
        requests.append(str(request.url))
        return httpx.Response(200, json={"url": url, "mime_type": "image/jpeg", "file_size": 100})

    monkeypatch.setattr(
        whatsapp.httpx,
        "Client",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    with pytest.raises(DomainError) as error:
        whatsapp.download_image("123")
    assert error.value.code == "INVALID_MEDIA" and len(requests) == 1


def test_media_boundary_downloads_only_bounded_supported_data(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", SecretStr("private-test-token"))
    actual_client = httpx.Client
    requests = []

    def handle(request):
        requests.append(str(request.url))
        assert request.headers["authorization"] == "Bearer private-test-token"
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/photo",
                    "mime_type": "image/png",
                    "file_size": 100,
                },
            )
        return httpx.Response(200, content=b"bounded-test-image")

    monkeypatch.setattr(
        whatsapp.httpx,
        "Client",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    assert whatsapp.download_image("123") == b"bounded-test-image" and len(requests) == 2
