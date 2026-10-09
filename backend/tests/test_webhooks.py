import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import paypal
from app.config import get_settings
from app.db import session_factory
from app.main import create_app
from app.models import Job, WebhookEvent


def test_unsigned_events_are_rejected_before_processing():
    with TestClient(create_app()) as client:
        event = {
            "id": "TEST",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {"id": "CAPTURE"},
        }
        assert client.post("/webhooks/paypal", json=event).status_code == 403
        assert client.post("/webhooks/whatsapp", json={}).status_code == 403


@pytest.mark.integration
def test_verified_duplicate_is_one_job(db_clean, monkeypatch):
    monkeypatch.setattr(paypal, "verify_webhook", lambda headers, event: True)
    with TestClient(create_app()) as client:
        event = {
            "id": "TEST",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {"id": "CAPTURE"},
        }
        replies = [client.post("/webhooks/paypal", json=event) for _ in range(5)]
        assert all(r.status_code == 200 for r in replies)
        assert sum(r.json()["duplicate"] is False for r in replies) == 1
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(WebhookEvent)) == 1
        assert db.scalar(select(func.count()).select_from(Job)) == 1


@pytest.mark.integration
def test_meta_hmac_and_message_deduplication(db_clean, monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", SecretStr("test-fixture-secret"))
    raw = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "MESSAGE-1",
                                        "from": "15555550101",
                                        "text": {"body": "help"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()
    signature = "sha256=" + hmac.new(b"test-fixture-secret", raw, hashlib.sha256).hexdigest()
    with TestClient(create_app()) as client:
        for _ in range(2):
            assert (
                client.post(
                    "/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": signature}
                ).status_code
                == 200
            )
        assert (
            client.post(
                "/webhooks/whatsapp", content=raw + b" ", headers={"x-hub-signature-256": signature}
            ).status_code
            == 403
        )
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 1


@pytest.mark.integration
def test_verified_inbox_does_not_retain_buyer_pii(db_clean, monkeypatch):
    monkeypatch.setattr(paypal, "verify_webhook", lambda headers, event: True)
    event = {
        "id": "PII-FIXTURE",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "CAPTURE",
            "amount": {"value": "55.00", "currency_code": "USD"},
            "payer": {"email_address": "private@example.invalid"},
            "shipping": {"address": {"address_line_1": "private-home-address"}},
            "supplementary_data": {
                "related_ids": {"order_id": "ORDER"},
                "private_note": "private-home-address",
            },
        },
    }
    with TestClient(create_app()) as client:
        assert client.post("/webhooks/paypal", json=event).status_code == 200
    with session_factory() as db:
        stored = db.get(WebhookEvent, "PII-FIXTURE").raw
        assert "private" not in json.dumps(stored)
        assert stored["resource"]["supplementary_data"]["related_ids"]["order_id"] == "ORDER"
        assert stored["resource"]["amount"]["value"] == "55.00"
