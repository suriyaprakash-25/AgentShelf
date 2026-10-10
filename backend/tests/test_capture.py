"""Exercise repeated approval returns and uncertain capture replies with real DB locks."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app import orders, paypal
from app.db import session_factory
from app.errors import DomainError
from app.models import Order, Product
from tests.test_orders import capture_data, fixture_data

pytestmark = pytest.mark.integration


def approved_data(order):
    return {
        "id": order.paypal_order_id,
        "status": "APPROVED",
        "purchase_units": [
            {
                "custom_id": str(order.id),
                "payee": {"email_address": "sandbox@example.invalid"},
                "shipping": {"address": {"country_code": "GB"}},
                "amount": {"currency_code": "USD", "value": "55.00"},
            }
        ],
    }


def test_concurrent_return_refreshes_capture_once(db_clean, provider, monkeypatch):
    _, session_id, quote = fixture_data()
    checkout = orders.create_checkout(quote["quote_id"], session_id)
    with session_factory() as db:
        order = db.get(Order, uuid.UUID(checkout["order_id"]))
        approved = approved_data(order)
        completed = capture_data(str(order.id), order.paypal_order_id)
        paypal_id = order.paypal_order_id
    calls = []
    monkeypatch.setattr(paypal, "read_order", lambda _: approved)

    def capture(order):
        calls.append(order.id)
        return completed

    monkeypatch.setattr(paypal, "capture_order", capture)
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: orders.capture_on_return(paypal_id), range(10)))
    assert all(result["status"] == "paid" for result in results)
    assert len(calls) == 1


def test_uncertain_capture_is_reconciled_not_recreated(db_clean, provider, monkeypatch):
    _, session_id, quote = fixture_data()
    checkout = orders.create_checkout(quote["quote_id"], session_id)
    with session_factory() as db:
        order = db.get(Order, uuid.UUID(checkout["order_id"]))
        responses = iter(
            [
                approved_data(order),
                approved_data(order),
                capture_data(str(order.id), order.paypal_order_id),
            ]
        )
        paypal_id = order.paypal_order_id
    monkeypatch.setattr(paypal, "read_order", lambda _: next(responses))

    def uncertain(order):
        raise DomainError("PAYPAL_UNAVAILABLE", "Lost response", 502)

    monkeypatch.setattr(paypal, "capture_order", uncertain)
    assert orders.capture_on_return(paypal_id)["status"] == "paid"


def test_wrong_country_is_refused_before_capture(db_clean, provider, monkeypatch):
    _, session_id, quote = fixture_data()
    checkout = orders.create_checkout(quote["quote_id"], session_id)
    with session_factory() as db:
        order = db.get(Order, uuid.UUID(checkout["order_id"]))
        data = approved_data(order)
        data["purchase_units"][0]["shipping"]["address"]["country_code"] = "US"
        paypal_id = order.paypal_order_id
    monkeypatch.setattr(paypal, "read_order", lambda _: data)

    def forbidden(order):
        pytest.fail("Capture must not run for a different shipping country")

    monkeypatch.setattr(paypal, "capture_order", forbidden)
    with pytest.raises(DomainError) as error:
        orders.capture_on_return(paypal_id)
    assert error.value.code == "PAYMENT_MISMATCH"


def test_cancel_callback_is_idempotent(db_clean, provider, monkeypatch):
    _, session_id, quote = fixture_data()
    checkout = orders.create_checkout(quote["quote_id"], session_id)
    with session_factory() as db:
        paypal_id = db.get(Order, uuid.UUID(checkout["order_id"])).paypal_order_id
    monkeypatch.setattr(
        paypal,
        "read_order",
        lambda _: {
            "id": paypal_id,
            "status": "VOIDED",
            "purchase_units": [{"custom_id": checkout["order_id"]}],
        },
    )
    assert orders.cancel_checkout(paypal_id)["status"] == "cancelled"
    assert orders.cancel_checkout(paypal_id)["status"] == "cancelled"
    with session_factory() as db:
        assert db.scalar(select(Product.stock)) == 1
