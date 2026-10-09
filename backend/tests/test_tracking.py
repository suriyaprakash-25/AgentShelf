import uuid

import pytest

from app import orders, paypal, tracking
from app.db import session_factory
from app.errors import DomainError
from app.models import Order
from tests.test_orders import fixture_data

pytestmark = pytest.mark.integration


def paid_order(provider):
    _, buyer, quote = fixture_data()
    checkout = orders.create_checkout(quote["quote_id"], buyer)
    with session_factory() as db, db.begin():
        order = db.get(Order, uuid.UUID(checkout["order_id"]))
        order.status = "paid"
        order.capture_id = "CAPTURE"
        return order.id, order.seller_id, order.paypal_order_id


def confirmation(provider_id, number="12345"):
    return {
        "id": provider_id,
        "purchase_units": [{"shipping": {"trackers": [{"id": "CAPTURE-" + number}]}}],
    }


def test_tracking_verified_once_and_unknown_carrier_maps_to_other(db_clean, provider, monkeypatch):
    order_id, seller_id, provider_id = paid_order(provider)
    calls = []

    def post(method, path, body, key):
        calls.append((method, path, body, key))
        return confirmation(provider_id)

    monkeypatch.setattr(paypal, "request", post)
    assert tracking.track(seller_id, order_id, "Local Courier", "12345")["status"] == "shipped"
    assert tracking.track(seller_id, order_id, "Local Courier", "12345")["status"] == "shipped"
    assert len(calls) == 1
    assert calls[0][2]["carrier"] == "OTHER"
    assert calls[0][2]["carrier_name_other"] == "Local Courier"
    assert calls[0][2]["capture_id"] == "CAPTURE"
    assert calls[0][3].startswith("track-")


def test_tracking_cross_seller_is_refused_before_provider(db_clean, provider, monkeypatch):
    order_id, _, _ = paid_order(provider)
    monkeypatch.setattr(paypal, "request", lambda *args: pytest.fail("Unauthorized provider call"))
    with pytest.raises(DomainError) as error:
        tracking.track(uuid.uuid4(), order_id, "DHL", "12345")
    assert error.value.status == 404


def test_tracking_lost_response_is_reconciled(db_clean, provider, monkeypatch):
    order_id, seller_id, provider_id = paid_order(provider)

    def uncertain(*args):
        raise DomainError("PAYPAL_UNAVAILABLE", "uncertain", 502)

    monkeypatch.setattr(paypal, "request", uncertain)
    monkeypatch.setattr(paypal, "read_order", lambda key: confirmation(provider_id))
    assert tracking.track(seller_id, order_id, "DHL", "12345")["status"] == "shipped"


def test_unconfirmed_tracking_never_changes_paid_order(db_clean, provider, monkeypatch):
    order_id, seller_id, provider_id = paid_order(provider)
    monkeypatch.setattr(paypal, "request", lambda *args: confirmation(provider_id, "WRONG"))
    with pytest.raises(DomainError) as error:
        tracking.track(seller_id, order_id, "DHL", "12345")
    assert error.value.code == "TRACKING_UNCONFIRMED"
    with session_factory() as db:
        order = db.get(Order, order_id)
        assert order.status == "paid" and order.tracking_number is None


def test_unpaid_orders_cannot_be_shipped(db_clean, provider):
    order_id, seller_id, _ = paid_order(provider)
    with session_factory() as db, db.begin():
        db.get(Order, order_id).status = "approved"
    with pytest.raises(DomainError) as error:
        tracking.track(seller_id, order_id, "DHL", "12345")
    assert error.value.code == "PAYMENT_REQUIRED"
