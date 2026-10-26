"""Phase B preflight, ADR-001 PayPal payee spike, and staging gate evidence verifier."""

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx

from app import paypal
from app.config import get_settings
from app.errors import DomainError
from evaluate_buyers import origin_url, request_json
from evaluate_listings import read_json, write_json


def check_preflight(settings=None):
    """Inspect configured Phase B provider readiness without exposing secret values."""
    cfg = settings or get_settings()
    checks = {
        "paypal_sandbox_credentials": bool(
            cfg.paypal_mode == "sandbox" and cfg.paypal_client_id and cfg.paypal_client_secret
        ),
        "paypal_webhook_id": bool(cfg.paypal_webhook_id),
        "anthropic_api_key": bool(cfg.anthropic_api_key or cfg.gemini_api_key),
        "whatsapp_cloud_api": bool(
            cfg.whatsapp_app_secret
            and cfg.whatsapp_verify_token
            and cfg.whatsapp_access_token
            and cfg.whatsapp_phone_number_id
        ),
        "whatsapp_paid_template": bool(cfg.whatsapp_paid_template),
        "resend_email": bool(cfg.resend_api_key and cfg.email_from),
        "cloudflare_r2": bool(
            cfg.media_backend == "r2"
            and cfg.r2_endpoint
            and cfg.r2_bucket
            and cfg.r2_access_key_id
            and cfg.r2_secret_access_key
        ),
        "sentry_backend": bool(cfg.sentry_dsn),
        "sentry_browser": bool(cfg.browser_sentry_dsn),
        "https_same_origin": bool(
            cfg.public_api_url.startswith("https://")
            and cfg.public_api_url.rstrip("/") == cfg.frontend_url.rstrip("/")
        ),
    }
    missing = [name for name, ready in checks.items() if not ready]
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "app_env": cfg.app_env,
        "paypal_mode": cfg.paypal_mode,
        "checks": checks,
        "missing": missing,
        "ready_for_staging_gates": len(missing) == 0,
        "gate_approval": False,
    }


def run_adr001_create(payee_email: str, amount_minor: int = 2500, currency: str = "USD"):
    """Run ADR-001 custom payee order creation in PayPal Sandbox and return sanitized evidence."""
    settings = get_settings()
    if settings.paypal_mode != "sandbox":
        raise DomainError("SANDBOX_REQUIRED", "ADR-001 spike must run in PayPal sandbox mode.", 409)
    paypal.require_ready()
    order_ref = uuid.uuid4()
    order = SimpleNamespace(id=order_ref)
    quote = SimpleNamespace(
        currency=currency,
        total_minor=amount_minor,
        item_total_minor=amount_minor - 500 if amount_minor > 500 else amount_minor,
        shipping_minor=500 if amount_minor > 500 else 0,
        title="ADR-001 Custom Payee Verification Item",
        qty=1,
        unit_minor=amount_minor - 500 if amount_minor > 500 else amount_minor,
    )
    seller = SimpleNamespace(
        paypal_email=payee_email.strip(),
        name="ADR-001 Sandbox Seller",
        live_eligible=False,
        paypal_merchant_id=None,
    )
    paypal_order_id, approval_url = paypal.create_order(order, quote, seller)
    readback = paypal.read_order(paypal_order_id)
    units = readback.get("purchase_units") or [{}]
    returned_payee = (units[0].get("payee") or {}).get("email_address", "")
    payee_matches = returned_payee.casefold() == payee_email.strip().casefold()
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "step": "create_order_with_custom_payee",
        "local_reference_id": str(order_ref),
        "paypal_order_id": paypal_order_id,
        "provider_status": readback.get("status"),
        "payee_matches_requested_seller": payee_matches,
        "approval_host": urlsplit(approval_url).hostname,
        "approval_url": approval_url,
        "gate_approval": False,
    }


def run_adr001_inspect(paypal_order_id: str, expected_payee_email: str):
    """Inspect an approved or captured Sandbox order for ADR-001 without leaking PII."""
    settings = get_settings()
    if settings.paypal_mode != "sandbox":
        raise DomainError("SANDBOX_REQUIRED", "ADR-001 spike must run in PayPal sandbox mode.", 409)
    paypal.require_ready()
    data = paypal.read_order(paypal_order_id)
    units = data.get("purchase_units") or [{}]
    unit = units[0]
    returned_payee = (unit.get("payee") or {}).get("email_address", "")
    captures = (unit.get("payments") or {}).get("captures") or []
    capture = captures[0] if captures else {}
    shipping = (unit.get("shipping") or {}).get("address") or {}
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "step": "inspect_order",
        "paypal_order_id": data.get("id"),
        "provider_status": data.get("status"),
        "payee_matches_requested_seller": (
            returned_payee.casefold() == expected_payee_email.strip().casefold()
        ),
        "capture_id": capture.get("id"),
        "capture_status": capture.get("status"),
        "shipping_country_code": shipping.get("country_code"),
        "gate_approval": False,
    }


def verify_gates(
    origin: str,
    listing_summary: str | None = None,
    buyer_summary: str | None = None,
    search_summary: str | None = None,
    allow_loopback: bool = False,
):
    """Check live staging capabilities and bound evaluation summary artifacts for Gates 1-3."""
    endpoint = origin_url(origin, allow_loopback)
    with httpx.Client(base_url=endpoint, timeout=10, follow_redirects=False) as client:
        health = request_json(client, "GET", "/healthz")
        capabilities = request_json(client, "GET", "/api/capabilities")

    summaries = {}
    for label, path in (
        ("listings", listing_summary),
        ("buyers", buyer_summary),
        ("search", search_summary),
    ):
        if not path or not Path(path).is_file():
            summaries[label] = {"present": False, "decision": "incomplete"}
            continue
        payload, digest_hex = read_json(path)
        summaries[label] = {
            "present": True,
            "sha256": digest_hex,
            "decision": payload.get("decision", "incomplete"),
        }

    gate1_ready = bool(
        health.get("status") == "ok"
        and capabilities.get("ai_configured")
        and capabilities.get("whatsapp_configured")
        and summaries["listings"]["decision"] == "targets_met"
    )
    gate2_ready = bool(
        gate1_ready
        and capabilities.get("paypal_mode") == "sandbox"
        and capabilities.get("checkout_configured")
        and summaries["buyers"]["decision"] == "targets_met"
        and summaries["search"]["decision"] == "targets_met"
    )
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "health": {
            "status": health.get("status"),
            "database": health.get("database"),
            "paypal_mode": health.get("paypal_mode"),
        },
        "capabilities": {
            "paypal_mode": capabilities.get("paypal_mode"),
            "checkout_configured": bool(capabilities.get("checkout_configured")),
            "ai_configured": bool(capabilities.get("ai_configured")),
            "whatsapp_configured": bool(capabilities.get("whatsapp_configured")),
            "seller_login_configured": bool(capabilities.get("seller_login_configured")),
        },
        "evaluations": summaries,
        "gate1_evidence_complete": gate1_ready,
        "gate2_evidence_complete": gate2_ready,
        "gate_approval": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("preflight")
    pre.add_argument("--output")

    create = sub.add_parser("adr001-create")
    create.add_argument("--payee-email", required=True)
    create.add_argument("--amount-minor", type=int, default=2500)
    create.add_argument("--output")

    inspect_cmd = sub.add_parser("adr001-inspect")
    inspect_cmd.add_argument("--paypal-order-id", required=True)
    inspect_cmd.add_argument("--payee-email", required=True)
    inspect_cmd.add_argument("--output")

    gates = sub.add_parser("gate-status")
    gates.add_argument("--origin", required=True)
    gates.add_argument("--listing-summary")
    gates.add_argument("--buyer-summary")
    gates.add_argument("--search-summary")
    gates.add_argument("--allow-loopback", action="store_true")
    gates.add_argument("--output")

    args = parser.parse_args()
    try:
        if args.command == "preflight":
            report = check_preflight()
        elif args.command == "adr001-create":
            report = run_adr001_create(args.payee_email, args.amount_minor)
        elif args.command == "adr001-inspect":
            report = run_adr001_inspect(args.paypal_order_id, args.payee_email)
        else:
            report = verify_gates(
                args.origin,
                args.listing_summary,
                args.buyer_summary,
                args.search_summary,
                args.allow_loopback,
            )
        if getattr(args, "output", None):
            write_json(args.output, report)
        # Never print approval URLs with session tokens to stdout if writing to file,
        # or keep stdout strictly sanitized.
        sanitized = {k: v for k, v in report.items() if k != "approval_url"}
        print(json.dumps(sanitized))
        return 0
    except Exception as exc:
        code = exc.code if isinstance(exc, DomainError) else "PHASE_B_CHECK_FAILED"
        print(json.dumps({"status": "failed", "code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
