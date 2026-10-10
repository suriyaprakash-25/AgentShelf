"""Read-only provider correlation for an uncertain create; never initiate a payment."""

from sqlalchemy import select

from app import paypal
from app.db import session_factory
from app.errors import DomainError
from app.models import Job, OpsAudit, Order, OrderEvent, Quote, Seller, utcnow


def correlate(actor_id, order_id, provider_id):
    with session_factory() as db, db.begin():
        actor = db.get(Seller, actor_id)
        if not actor or not actor.is_operator or actor.status != "active":
            raise DomainError("OPERATOR_REQUIRED", "Verified operator required.", 403)
        order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if not order:
            raise DomainError("ORDER_NOT_FOUND", "Order is unavailable.", 404)
        if order.paypal_order_id:
            if order.paypal_order_id != provider_id:
                raise DomainError(
                    "ORDER_ALREADY_CORRELATED",
                    "This order already has a different PayPal reference.",
                    409,
                )
            return {"status": order.status, "paypal_order_id": provider_id}
        if order.status != "checkout_created":
            raise DomainError(
                "CHECKOUT_CLOSED", "Only uncertain checkout creation can be correlated.", 409
            )
        if db.scalar(select(Order.id).where(Order.paypal_order_id == provider_id).limit(1)):
            raise DomainError(
                "ORDER_ALREADY_CORRELATED", "PayPal reference belongs to another order.", 409
            )
        data = paypal.read_order(provider_id)
        units = data.get("purchase_units", [])
        if data.get("id") != provider_id or len(units) != 1:
            raise DomainError(
                "PAYMENT_MISMATCH", "Provider order identity could not be verified.", 409
            )
        unit = units[0]
        quote = db.get(Quote, order.quote_id)
        seller = db.get(Seller, order.seller_id)
        if (
            unit.get("custom_id") != str(order.id)
            or unit.get("amount", {}).get("currency_code") != quote.currency
            or paypal.parse_money(unit.get("amount", {}).get("value")) != quote.total_minor
            or unit.get("payee", {}).get("email_address", "").casefold()
            != seller.paypal_email.casefold()
        ):
            raise DomainError(
                "PAYMENT_MISMATCH", "Provider reference, recipient or amount does not match.", 409
            )
        if data.get("status") not in {
            "CREATED",
            "PAYER_ACTION_REQUIRED",
            "APPROVED",
            "COMPLETED",
            "VOIDED",
        }:
            raise DomainError("PAYMENT_STATUS_UNKNOWN", "Provider status requires review.", 409)
        order.paypal_order_id = provider_id
        if data.get("status") in {"CREATED", "PAYER_ACTION_REQUIRED", "APPROVED"}:
            order.approval_url = paypal.approval_link(data)
        # The next worker read verifies captures/country and handles provider VOIDED proof.
        # An APPROVED read alone does not create a new capture intent or move funds.
        order.reconcile_after = utcnow()
        order.reconciliation_error = "CORRELATED_PENDING_VERIFICATION"
        db.add(
            Job(
                kind="reconcile_order",
                dedupe_key=f"operator_correlate:{order.id}",
                payload={"order_id": str(order.id)},
            )
        )
        db.add(
            OpsAudit(
                actor_id=actor_id, action="correlate_provider_order", resource_id=str(order.id)
            )
        )
        db.add(
            OrderEvent(
                order_id=order.id,
                type="correlate_provider_order",
                source="operator",
                payload={"paypal_order_id": provider_id},
            )
        )
        return {"status": order.status, "paypal_order_id": provider_id}
