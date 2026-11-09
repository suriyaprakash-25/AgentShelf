"""Durable Postgres job polling with atomic claiming and bounded retries."""

import logging
from datetime import timedelta

from sqlalchemy import select

from app import observability, orders, paypal, whatsapp
from app.db import session_factory
from app.errors import DomainError
from app.guards import parse_id
from app.models import Job, Order, Quote, Seller, WebhookEvent, utcnow

logger = logging.getLogger("agentshelf")

MAX_ATTEMPTS = 5
MAX_BACKOFF_SECONDS = 300
ORDERED_CHANNEL_WAIT = timedelta(seconds=1)
ADJUSTMENT_EVENT_TYPES = frozenset({"PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"})


def process_paypal(db, job):
    """Re-read the provider order to avoid trusting stale/out-of-order event payloads."""
    event = db.get(WebhookEvent, job.payload["event_id"])
    if not event or not event.verified or event.processed_at:
        return
    if (
        event.event_type.startswith("CUSTOMER.DISPUTE.")
        or event.event_type in ADJUSTMENT_EVENT_TYPES
    ):
        from app.payment_adjustments import process

        process(db, event)
        return
    resource = event.raw["resource"]
    order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
    if event.event_type.startswith("CHECKOUT.ORDER."):
        order_id = resource["id"]
    if not order_id:
        # Refund/dispute mappings need capture lookup, not a guessed order identifier.
        related = resource.get("supplementary_data", {}).get("related_ids", {})
        capture_id = related.get("capture_id") or resource.get("capture_id")
        order = (
            db.scalar(select(Order).where(Order.capture_id == capture_id).with_for_update())
            if capture_id
            else None
        )
    else:
        order = db.scalar(select(Order).where(Order.paypal_order_id == order_id).with_for_update())
    if not order:
        raise DomainError(
            "WEBHOOK_ORDER_UNKNOWN", "Event cannot be correlated to a local order.", 409
        )
    data = paypal.read_order(order.paypal_order_id)
    orders.apply_capture(db, order, data)
    event.processed_at = utcnow()


def format_ship_to(ship_to):
    if not isinstance(ship_to, dict):
        return "Address on file in Seller Dashboard"
    name = (
        ship_to.get("name", {}).get("full_name") if isinstance(ship_to.get("name"), dict) else None
    )
    address = ship_to.get("address") if isinstance(ship_to.get("address"), dict) else {}
    parts = [
        name,
        address.get("address_line_1"),
        address.get("address_line_2"),
        address.get("admin_area_2"),
        address.get("admin_area_1"),
        address.get("postal_code"),
        address.get("country_code"),
    ]
    formatted = ", ".join(str(part).strip() for part in parts if part and str(part).strip())
    return formatted or "Address on file in Seller Dashboard"


def process_notification(db, job):
    """Only send paid alerts once a verified completed capture webhook is present."""
    order = db.get(Order, parse_id(job.payload["order_id"]))
    if not order or order.status not in {"paid", "shipped"}:
        return
    verified_event = db.scalar(
        select(WebhookEvent).where(
            WebhookEvent.verified.is_(True),
            WebhookEvent.resource_id == order.capture_id,
            WebhookEvent.event_type == "PAYMENT.CAPTURE.COMPLETED",
        )
    )
    if not verified_event:
        raise DomainError(
            "AWAITING_VERIFIED_WEBHOOK", "Paid notification awaits a verified webhook.", 409
        )
    seller = db.get(Seller, order.seller_id)
    if not seller.whatsapp_phone:
        raise DomainError("SELLER_CHANNEL_MISSING", "Seller has no WhatsApp destination.", 409)
    quote = db.get(Quote, order.quote_id)
    # This is a fulfilment notification, not a model input or a log entry.
    whatsapp.send_paid(
        seller.whatsapp_phone,
        str(order.id)[:8],
        f"{quote.title} x{quote.qty}",
        f"{paypal.money(order.amount_minor)} {order.currency}",
        format_ship_to(order.ship_to),
    )


def _reconcile_order(db, job):
    from app.reconciliation import reconcile

    reconcile(parse_id(job.payload["order_id"]))


def _listing_draft(db, job):
    from app.listing_workflow import process

    process(db, job)


def _whatsapp_message(db, job):
    from app.whatsapp_workflow import process

    process(db, job)


def _whatsapp_draft_reply(db, job):
    from app.whatsapp_workflow import draft_reply

    draft_reply(db, job)


def _whatsapp_send(db, job):
    whatsapp.send_text(job.payload["phone"], job.payload["text"])


def _paypal_event(db, job):
    process_paypal(db, job)  # Resolved at call time so the handler can be substituted.


def _paid_notification(db, job):
    process_notification(db, job)


# Registry of job kinds (Open/Closed): a new kind adds an entry, not a branch.
# Handlers needing workflow modules import lazily to avoid import cycles.
HANDLERS = {
    "paypal_event": _paypal_event,
    "reconcile_order": _reconcile_order,
    "listing_draft": _listing_draft,
    "paid_notification": _paid_notification,
    "whatsapp_message": _whatsapp_message,
    "whatsapp_draft_reply": _whatsapp_draft_reply,
    "whatsapp_send": _whatsapp_send,
}


def dispatch(db, job):
    handler = HANDLERS.get(job.kind)
    if handler is None:
        raise DomainError("UNKNOWN_JOB", "This job type has no handler.")
    handler(db, job)


def backoff(attempts):
    """Exponential retry delay, capped so a failing job is revisited within minutes."""
    return timedelta(seconds=min(MAX_BACKOFF_SECONDS, 2**attempts))


def schedule_retry(db, job, code):
    """Record a failed attempt; give up after MAX_ATTEMPTS and run any compensation."""
    job.attempts += 1
    job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "queued"
    job.last_error = code
    job.run_after = utcnow() + backoff(job.attempts)
    logger.warning('{"event":"job_retry","code":"%s"}', code)
    if job.status == "failed":
        observability.report(code)
        compensate(db, job)


def compensate(db, job):
    """Tell a WhatsApp seller their draft failed instead of leaving them waiting."""
    if job.kind == "listing_draft" and job.payload.get("whatsapp_phone"):
        db.add(
            Job(
                kind="whatsapp_draft_reply",
                dedupe_key=f"failed-reply:{job.id}",
                payload={
                    "phone": job.payload["whatsapp_phone"],
                    "listing_id": job.payload["listing_id"],
                },
            )
        )


def claim(db):
    """Lock the next due job; concurrent workers skip rows another worker holds."""
    return db.scalar(
        select(Job)
        .where(Job.status == "queued", Job.run_after <= utcnow())
        .order_by(Job.run_after)
        .with_for_update(skip_locked=True)
        .limit(1)
    )


def run_one():
    """Run a locked job; a crash rolls back its claim so it can be recovered."""
    # Network calls currently hold the job lock. This bounds duplicate local processing,
    # but Meta delivery is at-least-once after a crash, not exactly-once.
    with session_factory() as db, db.begin():
        job = claim(db)
        if not job:
            return False
        try:
            with db.begin_nested():
                dispatch(db, job)
                job.status = "done"
                job.last_error = None
        except Exception as exc:
            # The savepoint rolls back handler writes before retry metadata is saved.
            # Unexpected payload/provider errors must not poison the queue indefinitely.
            # Never persist exception text or a traceback containing customer/provider data.
            code = exc.code if isinstance(exc, DomainError) else "JOB_HANDLER_FAILED"
            if code == "CHANNEL_ORDER_WAIT":
                job.run_after = utcnow() + ORDERED_CHANNEL_WAIT
                return True
            schedule_retry(db, job, code)
        return True
