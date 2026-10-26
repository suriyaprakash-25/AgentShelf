"""Bounded polling that preserves stock and budget while payment is uncertain."""

from datetime import timedelta

from sqlalchemy import select

from app import orders, paypal
from app.db import session_factory
from app.errors import DomainError
from app.models import Job, Order, utcnow


def schedule():
    with session_factory() as db, db.begin():
        now = utcnow()
        rows = db.scalars(
            select(Order)
            .where(Order.status.in_(orders.RESERVED_STATES), Order.reconcile_after <= now)
            .order_by(Order.reconcile_after)
            .with_for_update(skip_locked=True)
            .limit(100)
        )
        for order in rows:
            db.add(
                Job(
                    kind="reconcile_order",
                    dedupe_key=f"reconcile:{order.id}:{now.strftime('%Y%m%d%H%M')}",
                    payload={"order_id": str(order.id)},
                )
            )
            order.reconcile_after = now + timedelta(seconds=65)


def reconcile(order_id):
    retry_capture = None
    with session_factory() as db, db.begin():
        order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if not order or order.status not in orders.RESERVED_STATES:
            return
        if not order.paypal_order_id:
            # Unknown create responses need the original request key, never guessed IDs.
            order.reconciliation_error = "CREATE_RESPONSE_UNCERTAIN"
            return
        data = paypal.read_order(order.paypal_order_id)
        order.reconciliation_error = None
        if orders.apply_capture(db, order, data):
            return
        if data.get("status") == "VOIDED" and order.status == "checkout_created":
            orders.transition(
                db, order, "expire" if order.reserved_until <= utcnow() else "cancel", "reconciler"
            )
        elif (
            order.status == "checkout_created"
            and order.reserved_until <= utcnow()
            and data.get("status") in {"CREATED", "PAYER_ACTION_REQUIRED"}
        ):
            orders.transition(db, order, "expire", "reconciler")
        elif order.status == "approved" and data.get("status") == "APPROVED":
            if order.updated_at < utcnow() - timedelta(hours=6):
                order.reconciliation_error = "CAPTURE_WINDOW_REVIEW"
            else:
                retry_capture = order.paypal_order_id
        else:
            order.reconciliation_error = "PAYMENT_NOT_TERMINAL"
    if retry_capture:
        try:
            orders.capture_after_intent(retry_capture)
        except DomainError:
            # The durable approved state remains reserved; the queue handles bounded retries.
            raise
