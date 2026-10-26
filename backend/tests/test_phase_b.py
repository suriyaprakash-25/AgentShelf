"""Controlled protocol tests for Phase B preflight, ADR-001 spike and gate verification."""

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

import verify_phase_b
from app import paypal
from app.config import get_settings
from app.errors import DomainError


def test_preflight_reports_missing_credentials_without_leaking_secrets():
    cfg = SimpleNamespace(
        app_env="local",
        paypal_mode="sandbox",
        paypal_client_id=SecretStr("private-client-id"),
        paypal_client_secret=None,
        paypal_webhook_id=None,
        anthropic_api_key=SecretStr("private-anthropic-key"),
        whatsapp_app_secret=None,
        whatsapp_verify_token=None,
        whatsapp_access_token=None,
        whatsapp_phone_number_id=None,
        whatsapp_paid_template=None,
        resend_api_key=None,
        email_from=None,
        media_backend="local",
        r2_endpoint=None,
        r2_bucket=None,
        r2_access_key_id=None,
        r2_secret_access_key=None,
        sentry_dsn=None,
        browser_sentry_dsn=None,
        public_api_url="http://localhost:8000",
        frontend_url="http://localhost:5173",
    )
    report = verify_phase_b.check_preflight(cfg)
    assert report["ready_for_staging_gates"] is False
    assert report["gate_approval"] is False
    assert report["checks"]["anthropic_api_key"] is True
    assert report["checks"]["paypal_sandbox_credentials"] is False
    assert "private-" not in json.dumps(report)


def test_adr001_spike_verifies_custom_payee_and_redacts_email(monkeypatch):
    monkeypatch.setattr(get_settings(), "paypal_mode", "sandbox")
    monkeypatch.setattr(paypal, "require_ready", lambda: None)
    monkeypatch.setattr(
        paypal,
        "create_order",
        lambda order, quote, seller: (
            "PAYPAL-SPIKE-1",
            "https://sandbox.paypal.com/checkoutnow?token=PAYPAL-SPIKE-1",
        ),
    )
    monkeypatch.setattr(
        paypal,
        "read_order",
        lambda order_id: {
            "id": order_id,
            "status": "CREATED",
            "purchase_units": [
                {
                    "payee": {"email_address": "seller-sandbox@example.invalid"},
                    "payments": {"captures": [{"id": "CAPTURE-SPIKE-1", "status": "COMPLETED"}]},
                    "shipping": {"address": {"country_code": "GB"}},
                }
            ],
        },
    )
    created = verify_phase_b.run_adr001_create("seller-sandbox@example.invalid", 2500)
    assert created["paypal_order_id"] == "PAYPAL-SPIKE-1"
    assert created["payee_matches_requested_seller"] is True
    assert created["approval_host"] == "sandbox.paypal.com"
    assert created["gate_approval"] is False
    assert "seller-sandbox@example.invalid" not in json.dumps(created)

    inspected = verify_phase_b.run_adr001_inspect(
        "PAYPAL-SPIKE-1", "seller-sandbox@example.invalid"
    )
    assert inspected["capture_id"] == "CAPTURE-SPIKE-1"
    assert inspected["capture_status"] == "COMPLETED"
    assert inspected["payee_matches_requested_seller"] is True
    assert "seller-sandbox@example.invalid" not in json.dumps(inspected)


def test_adr001_spike_refuses_live_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "paypal_mode", "live")
    with pytest.raises(DomainError) as exc:
        verify_phase_b.run_adr001_create("seller@example.invalid")
    assert exc.value.code == "SANDBOX_REQUIRED"


def test_verify_gates_binds_health_capabilities_and_evaluation_artifacts(monkeypatch, tmp_path):
    listings_file = tmp_path / "listings.json"
    buyers_file = tmp_path / "buyers.json"
    search_file = tmp_path / "search.json"
    for path in (listings_file, buyers_file, search_file):
        path.write_text(json.dumps({"decision": "targets_met"}), encoding="utf-8")

    def handler(request):
        if request.url.path == "/healthz":
            return httpx.Response(
                200, json={"status": "ok", "database": "reachable", "paypal_mode": "sandbox"}
            )
        return httpx.Response(
            200,
            json={
                "paypal_mode": "sandbox",
                "checkout_configured": True,
                "ai_configured": True,
                "whatsapp_configured": True,
                "seller_login_configured": True,
            },
        )

    actual_client = httpx.Client
    monkeypatch.setattr(
        verify_phase_b.httpx,
        "Client",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    report = verify_phase_b.verify_gates(
        "https://stage.example.test",
        str(listings_file),
        str(buyers_file),
        str(search_file),
    )
    assert report["gate1_evidence_complete"] is True
    assert report["gate2_evidence_complete"] is True
    assert report["gate_approval"] is False
