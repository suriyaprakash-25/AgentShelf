"""Verified webhook inboxes persist deduplicated jobs before acknowledging."""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from app import paypal, whatsapp
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.models import Job, WebhookEvent

router = APIRouter()
logger = logging.getLogger("agentshelf")


async def bounded_body(request):
    """Reject oversized webhook bodies while streaming, before JSON parsing."""
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 1024 * 1024:
            raise DomainError("BODY_TOO_LARGE", "Webhook payload is too large.", 413)
    return bytes(raw)


def parse_event(raw):
    """Decode a JSON object without reflecting input into error messages."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Expected object")
        return data
    except (ValueError, UnicodeDecodeError) as exc:
        raise DomainError("INVALID_EVENT", "Expected a valid JSON event.", 400) from exc


def persist_paypal(event):
    """Insert a verified event and its job atomically, or recognize a duplicate."""
    # Signature verification uses the full original body first. The durable inbox
    # retains only correlation/accounting fields; shipping details belong on orders.
    resource = event["resource"]
    related = resource.get("supplementary_data", {}).get("related_ids", {})
    resource_id = resource.get("id") or resource.get("dispute_id")
    minimal = {"id": resource_id}
    if "amount" in resource:
        minimal["amount"] = {
            key: resource["amount"][key]
            for key in ("currency_code", "value")
            if key in resource["amount"]
        }
    if "capture_id" in resource:
        minimal["capture_id"] = resource["capture_id"]
    if related:
        minimal["supplementary_data"] = {
            "related_ids": {
                key: related[key] for key in ("order_id", "capture_id") if key in related
            }
        }
    stored = {"id": event["id"], "event_type": event["event_type"], "resource": minimal}
    with session_factory() as db, db.begin():
        inserted = db.scalar(
            insert(WebhookEvent)
            .values(
                paypal_event_id=event["id"],
                event_type=event["event_type"],
                resource_id=resource_id,
                verified=True,
                raw=stored,
            )
            .on_conflict_do_nothing()
            .returning(WebhookEvent.paypal_event_id)
        )
        if inserted:
            db.add(
                Job(
                    kind="paypal_event",
                    dedupe_key="paypal:" + event["id"],
                    payload={"event_id": event["id"]},
                )
            )
        return bool(inserted)


@router.post("/webhooks/paypal")
async def paypal_event(request: Request):
    """Require a real PayPal verification SUCCESS before inbox insertion."""
    event = parse_event(await bounded_body(request))
    if (
        not isinstance(event.get("id"), str)
        or len(event["id"]) > 100
        or not isinstance(event.get("event_type"), str)
        or len(event["event_type"]) > 100
        or not isinstance(event.get("resource"), dict)
        or not isinstance(event["resource"].get("id") or event["resource"].get("dispute_id"), str)
        or len(event["resource"].get("id") or event["resource"].get("dispute_id")) > 100
    ):
        raise DomainError("INVALID_EVENT", "Missing valid event identifiers.", 400)
    if not await run_in_threadpool(paypal.verify_webhook, request.headers, event):
        logger.warning(
            json.dumps(
                {
                    "event": "webhook_rejected",
                    "provider": "paypal",
                    "request_id": request.state.request_id,
                }
            )
        )
        raise DomainError("INVALID_SIGNATURE", "Webhook signature verification failed.", 403)
    inserted = await run_in_threadpool(persist_paypal, event)
    return {"accepted": True, "duplicate": not inserted}


@router.get("/webhooks/whatsapp")
def whatsapp_handshake(request: Request):
    """Respond to Meta verification only for our configured verification token."""
    import hmac

    secret = get_settings().whatsapp_verify_token
    token = request.query_params.get("hub.verify_token", "")
    if (
        request.query_params.get("hub.mode") != "subscribe"
        or not secret
        or not hmac.compare_digest(token, secret.get_secret_value())
    ):
        raise DomainError("INVALID_VERIFICATION", "Verification token did not match.", 403)
    return PlainTextResponse(request.query_params.get("hub.challenge", ""))


def persist_whatsapp(event):
    """Deduplicate signed messages by Meta's stable message ID."""
    with session_factory() as db, db.begin():
        for entry in event.get("entry", []):
            for change in entry.get("changes", []):
                for message in change.get("value", {}).get("messages", []):
                    message_id = message.get("id")
                    if not isinstance(message_id, str) or len(message_id) > 180:
                        raise DomainError("INVALID_EVENT", "Missing valid message ID.")
                    db.execute(
                        insert(Job)
                        .values(
                            kind="whatsapp_message",
                            dedupe_key="meta:" + message_id,
                            payload=message,
                            status="queued",
                            attempts=0,
                        )
                        .on_conflict_do_nothing()
                    )


@router.post("/webhooks/whatsapp")
async def whatsapp_event(request: Request):
    """Verify Meta's raw body before persisting messages."""
    raw = await bounded_body(request)
    if not whatsapp.verify_signature(raw, request.headers.get("x-hub-signature-256")):
        logger.warning(
            json.dumps(
                {
                    "event": "webhook_rejected",
                    "provider": "whatsapp",
                    "request_id": request.state.request_id,
                }
            )
        )
        raise DomainError("INVALID_SIGNATURE", "Webhook signature verification failed.", 403)
    await run_in_threadpool(persist_whatsapp, parse_event(raw))
    return {"accepted": True}
