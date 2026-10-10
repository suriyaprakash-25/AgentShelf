"""Explicit retention review: dry-run defaults, no change to payment/budget history."""

from datetime import timedelta

from sqlalchemy import select

from app.db import session_factory
from app.errors import DomainError
from app.models import Job, OpsAudit, Order, PaymentAdjustment, Seller, WebhookEvent, utcnow
from app.routes.webhooks import minimize_paypal


def review(actor_id=None, apply=False, days=30, limit=100, cursor=None):
    if days < 30 or not 1 <= limit <= 1000:
        raise ValueError("Use at least 30 days and a batch of 1..1000 records.")
    result = {
        "legacy_inboxes": 0,
        "old_completed_message_payloads": 0,
        "terminal_addresses": 0,
        "applied": apply,
        "next_cursor": None,
    }
    with session_factory() as db, db.begin():
        if apply:
            actor = db.get(Seller, actor_id)
            if not actor or not actor.is_operator or actor.status != "active":
                raise DomainError("OPERATOR_REQUIRED", "Verified operator required.", 403)
        inboxes = db.scalars(
            select(WebhookEvent)
            .where(
                WebhookEvent.verified.is_(True),
                WebhookEvent.processed_at.is_not(None),
                WebhookEvent.paypal_event_id > (cursor or ""),
            )
            .order_by(WebhookEvent.paypal_event_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        for event in inboxes:
            result["next_cursor"] = event.paypal_event_id
            old_resource = event.raw.get("resource", {})
            minimal = minimize_paypal(
                {
                    "id": event.paypal_event_id,
                    "event_type": event.event_type,
                    "resource": {**old_resource, "id": event.resource_id},
                }
            )
            if minimal != event.raw:
                result["legacy_inboxes"] += 1
                if apply:
                    event.raw = minimal
                    db.add(
                        OpsAudit(
                            actor_id=actor_id,
                            action="minimize_legacy_inbox",
                            resource_id=event.paypal_event_id,
                        )
                    )
        cutoff = utcnow() - timedelta(days=days)
        messages = db.scalars(
            select(Job)
            .where(
                Job.status == "done",
                Job.kind.in_(["whatsapp_send", "whatsapp_message"]),
                Job.created_at < cutoff,
                Job.payload != {},
            )
            .order_by(Job.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        for job in messages:
            result["old_completed_message_payloads"] += 1
            if apply:
                job.payload = {}
                db.add(
                    OpsAudit(
                        actor_id=actor_id, action="clear_completed_message", resource_id=str(job.id)
                    )
                )
        terminal = db.scalars(
            select(Order)
            .where(
                Order.status.in_(["shipped", "refunded", "failed", "expired", "cancelled"]),
                Order.updated_at < cutoff,
                Order.ship_to.is_not(None),
                Order.reconciliation_error.is_(None),
            )
            .order_by(Order.updated_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        for order in terminal:
            if db.scalar(
                select(PaymentAdjustment.resource_id)
                .where(
                    PaymentAdjustment.order_id == order.id,
                    PaymentAdjustment.kind.in_(["dispute", "reversal"]),
                )
                .limit(1)
            ):
                continue
            result["terminal_addresses"] += 1
            if apply:
                order.ship_to = None
                db.add(
                    OpsAudit(
                        actor_id=actor_id,
                        action="erase_terminal_address",
                        resource_id=str(order.id),
                    )
                )
    return result
