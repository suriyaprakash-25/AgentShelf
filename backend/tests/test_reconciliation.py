import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import orders, paypal, reconciliation
from app.db import session_factory
from app.errors import DomainError
from app.models import AgentSession, Job, Order, Product, utcnow
from tests.test_capture import approved_data
from tests.test_orders import capture_data, fixture_data

pytestmark = pytest.mark.integration


def checkout(provider):
    _, buyer, quote = fixture_data()
    result = orders.create_checkout(quote["quote_id"], buyer)
    with session_factory() as db:
        order = db.get(Order, uuid.UUID(result["order_id"]))
        return order.id, buyer, order.paypal_order_id, approved_data(order)


def test_capture_uncertainty_keeps_durable_intent_and_reconciles_once(
    db_clean, provider, monkeypatch
):
    order_id, buyer, paypal_id, approved = checkout(provider)
    monkeypatch.setattr(paypal, "read_order", lambda _: approved)

    def lost(order):
        raise DomainError("PAYPAL_UNAVAILABLE", "Lost provider response", 502)

    monkeypatch.setattr(paypal, "capture_order", lost)
    with pytest.raises(DomainError):
        orders.capture_on_return(paypal_id)
    with session_factory() as db, db.begin():
        order = db.get(Order, order_id)
        assert order.status == "approved" and db.scalar(select(Product.stock)) == 0
        order.reserved_until = utcnow() - timedelta(hours=1)
    monkeypatch.setattr(paypal, "read_order", lambda _: capture_data(str(order_id), paypal_id))
    reconciliation.reconcile(order_id)
    reconciliation.reconcile(order_id)
    with session_factory() as db:
        assert db.get(Order, order_id).status == "paid"
        assert db.get(AgentSession, uuid.UUID(buyer)).spent_minor == 5500
        assert db.scalar(select(Product.stock)) == 0


@pytest.mark.parametrize(
    "provider_status,expired_window,expected_stock,expected_state",
    [
        ("CREATED", False, 0, "checkout_created"),
        ("CREATED", True, 1, "expired"),
        ("PAYER_ACTION_REQUIRED", True, 1, "expired"),
        ("VOIDED", True, 1, "expired"),
    ],
)
def test_unapproved_reservation_expires_after_fifteen_minute_window(
    db_clean, provider, monkeypatch, provider_status, expired_window, expected_stock, expected_state
):
    order_id, _, paypal_id, data = checkout(provider)
    data["status"] = provider_status
    monkeypatch.setattr(paypal, "read_order", lambda _: data)
    with session_factory() as db, db.begin():
        db.get(Order, order_id).reserved_until = utcnow() + (
            timedelta(minutes=-1) if expired_window else timedelta(minutes=10)
        )
    reconciliation.reconcile(order_id)
    reconciliation.reconcile(order_id)
    with session_factory() as db:
        assert db.get(Order, order_id).status == expected_state
        assert db.scalar(select(Product.stock)) == expected_stock


def test_scheduler_deduplicates_and_missing_create_response_is_visible(db_clean, provider):
    order_id, _, _, _ = checkout(provider)
    with session_factory() as db, db.begin():
        db.get(Order, order_id).paypal_order_id = None
    reconciliation.schedule()
    reconciliation.schedule()
    reconciliation.reconcile(order_id)
    with session_factory() as db:
        assert db.query(Job).filter(Job.kind == "reconcile_order").count() == 1
        assert db.get(Order, order_id).reconciliation_error == "CREATE_RESPONSE_UNCERTAIN"
        assert db.scalar(select(Product.stock)) == 0


def test_unconfirmed_cancel_preserves_reservation(db_clean, provider, monkeypatch):
    order_id, _, paypal_id, data = checkout(provider)
    data["status"] = "CREATED"
    monkeypatch.setattr(paypal, "read_order", lambda _: data)
    assert orders.cancel_checkout(paypal_id)["status"] == "checkout_created"
    with session_factory() as db:
        assert db.scalar(select(Product.stock)) == 0
        assert db.get(Order, order_id).reconciliation_error == "CANCELLATION_UNCONFIRMED"
