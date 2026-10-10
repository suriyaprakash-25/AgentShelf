"""Read authoritative refund/dispute resources; never infer or initiate money movements."""

import re
from urllib.parse import urlsplit

from sqlalchemy import func, select

from app import orders, paypal
from app.errors import DomainError
from app.models import Order, PaymentAdjustment, utcnow


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,100}", value):
        raise DomainError(
            "PAYMENT_RESOURCE_INVALID", "Provider resource could not be verified.", 502
        )
    return value


def process(db, event):
    resource_id = identifier(event.resource_id)
    if event.event_type == "PAYMENT.CAPTURE.REFUNDED":
        data = paypal.request("GET", f"/v2/payments/refunds/{resource_id}")
        if data.get("id") != resource_id or data.get("status") != "COMPLETED":
            raise DomainError("REFUND_UNCONFIRMED", "Refund is not confirmed by PayPal.", 409)
        capture_ids = []
        for link in data.get("links", []):
            url = urlsplit(link.get("href", ""))
            match = re.fullmatch(r"/v2/payments/captures/([A-Za-z0-9]{1,64})", url.path)
            if (
                link.get("rel") == "up"
                and url.hostname == urlsplit(paypal.api_base()).hostname
                and url.scheme == "https"
                and match
            ):
                capture_ids.append(match[1])
        if len(set(capture_ids)) != 1:
            raise DomainError(
                "REFUND_CORRELATION_FAILED", "Refund capture needs operator review.", 409
            )
        order = db.scalar(select(Order).where(Order.capture_id == capture_ids[0]).with_for_update())
        if not order or order.status not in {"paid", "shipped", "refunded"}:
            raise DomainError(
                "WEBHOOK_ORDER_UNKNOWN", "Refund does not match a paid local order.", 409
            )
        amount = data.get("amount", {})
        minor = paypal.parse_money(amount.get("value"))
        if amount.get("currency_code") != order.currency or not 0 < minor <= order.amount_minor:
            raise DomainError("REFUND_AMOUNT_MISMATCH", "Refund amount needs operator review.", 409)
        existing = db.get(PaymentAdjustment, resource_id)
        if existing:
            if (
                existing.order_id != order.id
                or existing.amount_minor != minor
                or existing.kind != "refund"
            ):
                raise DomainError("REFUND_AMOUNT_MISMATCH", "Refund record changed.", 409)
        else:
            db.add(
                PaymentAdjustment(
                    resource_id=resource_id,
                    order_id=order.id,
                    kind="refund",
                    status="COMPLETED",
                    amount_minor=minor,
                )
            )
            db.flush()
        total = db.scalar(
            select(func.coalesce(func.sum(PaymentAdjustment.amount_minor), 0)).where(
                PaymentAdjustment.order_id == order.id,
                PaymentAdjustment.kind == "refund",
                PaymentAdjustment.status == "COMPLETED",
            )
        )
        if total > order.amount_minor:
            raise DomainError("REFUND_TOTAL_MISMATCH", "Refund totals exceed the payment.", 409)
        if total == order.amount_minor and order.status in {"paid", "shipped"}:
            orders.transition(db, order, "refund", "webhook")
            order.reconciliation_error = None
        elif total < order.amount_minor:
            order.reconciliation_error = "PARTIAL_REFUND_REVIEW"
    elif event.event_type.startswith("CUSTOMER.DISPUTE."):
        data = paypal.request("GET", f"/v1/customer/disputes/{resource_id}")
        if data.get("dispute_id") != resource_id or not isinstance(data.get("status"), str):
            raise DomainError("DISPUTE_UNCONFIRMED", "Dispute details could not be verified.", 409)
        capture_ids = [
            t.get("seller_transaction_id") for t in data.get("disputed_transactions", [])
        ]
        if len(capture_ids) != 1:
            raise DomainError(
                "DISPUTE_CORRELATION_FAILED", "Multiple disputed transactions need review.", 409
            )
        order = db.scalar(select(Order).where(Order.capture_id == capture_ids[0]).with_for_update())
        if not order:
            raise DomainError(
                "WEBHOOK_ORDER_UNKNOWN", "Dispute cannot be matched to a local capture.", 409
            )
        adjustment = db.get(PaymentAdjustment, resource_id)
        if not adjustment:
            adjustment = PaymentAdjustment(
                resource_id=resource_id,
                order_id=order.id,
                kind="dispute",
                status=data["status"][:80],
            )
            db.add(adjustment)
        elif adjustment.order_id != order.id or adjustment.kind != "dispute":
            raise DomainError("DISPUTE_CORRELATION_FAILED", "Dispute correlation changed.", 409)
        else:
            adjustment.status = data["status"][:80]
        order.reconciliation_error = (
            "DISPUTE_RESOLUTION_REVIEW" if data["status"] == "RESOLVED" else "DISPUTE_OPEN"
        )
    elif event.event_type == "PAYMENT.CAPTURE.REVERSED":
        order = db.scalar(select(Order).where(Order.capture_id == resource_id).with_for_update())
        if not order:
            raise DomainError("WEBHOOK_ORDER_UNKNOWN", "Reversal capture needs review.", 409)
        data = paypal.request("GET", f"/v2/payments/captures/{resource_id}")
        if data.get("id") != resource_id:
            raise DomainError("PAYMENT_MISMATCH", "Reversal resource does not match.", 409)
        if not db.get(PaymentAdjustment, resource_id):
            db.add(
                PaymentAdjustment(
                    resource_id=resource_id,
                    order_id=order.id,
                    kind="reversal",
                    status="REVIEW_REQUIRED",
                )
            )
        order.reconciliation_error = "REVERSAL_REVIEW_REQUIRED"
    else:
        raise DomainError("PAYMENT_RESOURCE_INVALID", "Unsupported adjustment event.")
    event.processed_at = utcnow()
