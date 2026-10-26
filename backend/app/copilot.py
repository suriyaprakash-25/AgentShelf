"""Seller copilot workflows (S-1): 7-day transaction summary, verified refunds, and invoices."""

import re
import uuid
from datetime import timedelta

from sqlalchemy import String, cast, func, select

from app import orders, paypal
from app.db import session_factory
from app.errors import DomainError
from app.guards import safe_text
from app.models import Order, PaymentAdjustment, Seller, utcnow

EMAIL_RE = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


def weekly_summary(db, seller_id):
    """Compute a 7-day transaction summary for the seller from authoritative Postgres rows."""
    cutoff = utcnow() - timedelta(days=7)
    rows = db.execute(
        select(Order.status, func.count(), func.coalesce(func.sum(Order.amount_minor), 0))
        .where(Order.seller_id == seller_id, Order.created_at >= cutoff)
        .group_by(Order.status)
    ).all()
    counts = {row[0]: int(row[1]) for row in rows}
    amounts = {row[0]: int(row[2]) for row in rows}
    refunded_minor = int(
        db.scalar(
            select(func.coalesce(func.sum(PaymentAdjustment.amount_minor), 0))
            .join(Order, Order.id == PaymentAdjustment.order_id)
            .where(
                Order.seller_id == seller_id,
                PaymentAdjustment.kind == "refund",
                PaymentAdjustment.status == "COMPLETED",
                PaymentAdjustment.created_at >= cutoff,
            )
        )
        or 0
    )
    gross_paid_minor = (
        amounts.get("paid", 0) + amounts.get("shipped", 0) + amounts.get("refunded", 0)
    )
    paid_count = counts.get("paid", 0) + counts.get("shipped", 0)
    refunded_count = counts.get("refunded", 0)
    text = (
        f"7-day summary: {paid_count} paid/shipped orders "
        f"({paypal.money(gross_paid_minor)} USD gross), "
        f"{refunded_count} refunded ({paypal.money(refunded_minor)} USD refunded)."
    )
    return {
        "window_days": 7,
        "currency": "USD",
        "paid_or_shipped_orders": paid_count,
        "refunded_orders": refunded_count,
        "gross_paid_minor": gross_paid_minor,
        "refunded_minor": refunded_minor,
        "summary": text,
    }


def issue_refund(seller_id, order_prefix: str, confirm: bool = False):
    """Issue a full PayPal capture refund for a seller-owned order after confirmation."""
    if not confirm:
        raise DomainError("CONFIRMATION_REQUIRED", "Confirm the refund before calling PayPal.")
    prefix = order_prefix.strip().lstrip("#").lower()
    if not re.fullmatch(r"[0-9a-f-]{8,36}", prefix):
        raise DomainError("ORDER_NOT_FOUND", "Use a valid order identifier.")
    with session_factory() as db, db.begin():
        matches = list(
            db.scalars(
                select(Order)
                .where(
                    Order.seller_id == seller_id,
                    cast(Order.id, String).like(prefix + "%"),
                )
                .with_for_update()
                .limit(2)
            )
        )
        if len(matches) != 1:
            raise DomainError("ORDER_NOT_FOUND", "Use a unique order identifier from orders.")
        order = matches[0]
        if order.status == "refunded":
            return {
                "order_id": str(order.id),
                "status": "refunded",
                "amount": paypal.money(order.amount_minor),
                "currency": order.currency,
            }
        if order.status not in {"paid", "shipped"} or not order.capture_id:
            raise DomainError(
                "INVALID_TRANSITION",
                "Only paid or shipped orders with a capture can be refunded.",
                409,
            )
        order_id = order.id
        capture_id = order.capture_id
        amount_minor = order.amount_minor
        currency = order.currency

    data = paypal.refund_capture(capture_id, amount_minor, currency, f"refund-{order_id}")
    provider_status = data.get("status", "COMPLETED")
    if provider_status not in {"COMPLETED", "PENDING"}:
        raise DomainError("PAYPAL_UNAVAILABLE", "PayPal refund was not accepted.", 502)
    refund_id = data.get("id") or f"refund-{order_id}"

    with session_factory() as db, db.begin():
        order = db.scalar(
            select(Order)
            .where(Order.id == order_id, Order.seller_id == seller_id)
            .with_for_update()
        )
        if order.status in {"paid", "shipped"}:
            existing = db.scalar(
                select(PaymentAdjustment).where(PaymentAdjustment.resource_id == refund_id)
            )
            if not existing:
                db.add(
                    PaymentAdjustment(
                        resource_id=refund_id,
                        order_id=order.id,
                        kind="refund",
                        status=provider_status,
                        amount_minor=amount_minor,
                    )
                )
            orders.transition(db, order, "refund", "seller_copilot")
        return {
            "order_id": str(order.id),
            "refund_id": refund_id,
            "status": order.status,
            "amount": paypal.money(order.amount_minor),
            "currency": order.currency,
        }


def send_invoice(
    seller_id, recipient_email: str, amount_minor: int, note: str, confirm: bool = False
):
    """Create and send a PayPal invoice for the authenticated seller after confirmation."""
    if not confirm:
        raise DomainError("CONFIRMATION_REQUIRED", "Confirm the invoice details before sending.")
    email_clean = recipient_email.strip().lower()
    if not EMAIL_RE.fullmatch(email_clean) or len(email_clean) > 254:
        raise DomainError("INVALID_INPUT", "Provide a valid recipient email address.")
    if type(amount_minor) is not int or not 1 <= amount_minor <= 100_000_000:
        raise DomainError("INVALID_INPUT", "Provide a valid invoice amount.")
    clean_note = safe_text(note.strip() or "Thank you for your order.", 400)
    with session_factory() as db:
        seller = db.get(Seller, seller_id)
        if not seller or seller.status != "active":
            raise DomainError("SELLER_UNAVAILABLE", "Seller account is unavailable.", 403)
    request_key = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"invoice:{seller_id}:{email_clean}:{amount_minor}:{clean_note}",
        )
    )
    result = paypal.create_and_send_invoice(
        seller, email_clean, amount_minor, "USD", clean_note, request_key
    )
    return {
        "invoice_id": result["invoice_id"],
        "status": result["status"],
        "amount": paypal.money(amount_minor),
        "currency": "USD",
    }
