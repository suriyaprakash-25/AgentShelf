"""Durable Postgres job polling with atomic claiming and bounded retries."""

import logging
from datetime import timedelta

from sqlalchemy import select

from app import observability, orders, paypal, whatsapp
from app.db import session_factory
from app.errors import DomainError
from app.models import Job, Order, Quote, Seller, WebhookEvent, utcnow

logger = logging.getLogger("agentshelf")


def process_paypal(db, job):
    """Re-read the provider order to avoid trusting stale/out-of-order event payloads."""
    event = db.get(WebhookEvent, job.payload["event_id"])
    if not event or not event.verified or event.processed_at:
        return
    if event.event_type.startswith("CUSTOMER.DISPUTE.") or event.event_type in {
        "PAYMENT.CAPTURE.REFUNDED",
        "PAYMENT.CAPTURE.REVERSED",
    }:
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


def process_notification(db, job):
    """Only send paid alerts once a verified completed capture webhook is present."""
    from app.guards import parse_id

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
        str(order.ship_to),
    )


def run_one():
    """Run a locked job; a crash rolls back its claim so it can be recovered."""
    # Network calls currently hold the job lock. This bounds duplicate local processing,
    # but Meta delivery is at-least-once after a crash, not exactly-once.
    with session_factory() as db, db.begin():
        job = db.scalar(
            select(Job)
            .where(Job.status == "queued", Job.run_after <= utcnow())
            .order_by(Job.run_after)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        try:
            with db.begin_nested():
                if job.kind == "paypal_event":
                    process_paypal(db, job)
                elif job.kind == "reconcile_order":
                    from app.guards import parse_id
                    from app.reconciliation import reconcile

                    reconcile(parse_id(job.payload["order_id"]))
                elif job.kind == "listing_draft":
                    from app.listing_workflow import process

                    process(db, job)
                elif job.kind == "paid_notification":
                    process_notification(db, job)
                elif job.kind == "whatsapp_message":
                    from app.whatsapp_workflow import process

                    process(db, job)
                elif job.kind == "whatsapp_draft_reply":
                    from app.whatsapp_workflow import draft_reply

                    draft_reply(db, job)
                elif job.kind == "whatsapp_send":
                    whatsapp.send_text(job.payload["phone"], job.payload["text"])
                else:
                    raise DomainError("UNKNOWN_JOB", "This job type has no handler.")
                job.status = "done"
                job.last_error = None
        except Exception as exc:
            # The savepoint rolls back handler writes before retry metadata is saved.
            # Unexpected payload/provider errors must not poison the queue indefinitely.
            # Never persist exception text or a traceback containing customer/provider data.
            code = exc.code if isinstance(exc, DomainError) else "JOB_HANDLER_FAILED"
            if code == "CHANNEL_ORDER_WAIT":
                job.run_after = utcnow() + timedelta(seconds=1)
                return True
            job.attempts += 1
            job.status = "failed" if job.attempts >= 5 else "queued"
            job.last_error = code
            job.run_after = utcnow() + timedelta(seconds=min(300, 2**job.attempts))
            logger.warning('{"event":"job_retry","code":"%s"}', code)
            if job.status == "failed":
                observability.report(code)
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
        return True
