import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import orders, quotes
from app.db import session_factory
from app.errors import DomainError
from app.models import AgentSession, Order, Product, Quote, Seller, utcnow

pytestmark = pytest.mark.integration


def fixture_data(stock=1, budget=6000):
    with session_factory() as db, db.begin():
        seller = Seller(
            name="Test store",
            country="IN",
            paypal_email="sandbox@example.invalid",
            store_slug="test",
            consent_at=utcnow(),
            status="active",
            shipping_rates={"GB": 1000, "US": 800},
        )
        db.add(seller)
        db.flush()
        product = Product(
            seller_id=seller.id,
            short_no=1,
            title="Scarf",
            description="Blue scarf",
            price_minor=4500,
            stock=stock,
            status="live",
        )
        db.add(product)
        buyer = AgentSession(budget_minor=budget)
        db.add(buyer)
        db.flush()
        quote = quotes.get_quote(db, str(product.id), 1, "GB", str(buyer.id))
        return str(product.id), str(buyer.id), quote


def test_quote_and_immutable_snapshot(db_clean):
    product_id, session_id, quote = fixture_data()
    assert quote["total"] == "55.00"
    with session_factory() as db, db.begin():
        db.get(Product, uuid.UUID(product_id)).price_minor = 1
    with session_factory() as db:
        assert db.get(Quote, uuid.UUID(quote["quote_id"])).total_minor == 5500


def test_same_quote_is_idempotent(db_clean, provider):
    _, session_id, quote = fixture_data()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: orders.create_checkout(quote["quote_id"], session_id), range(8))
        )
    assert len({r["order_id"] for r in results}) == 1
    assert len(provider) == 1
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 1
        assert db.scalar(select(Product.stock)) == 0


def test_twenty_checkouts_on_stock_one(db_clean, provider):
    product_id, _, _ = fixture_data()
    buyers = []
    for _ in range(20):
        with session_factory() as db, db.begin():
            buyer = AgentSession(budget_minor=6000)
            db.add(buyer)
            db.flush()
            quote = quotes.get_quote(db, product_id, 1, "GB", str(buyer.id))
            buyers.append((quote["quote_id"], str(buyer.id)))

    def attempt(pair):
        try:
            return orders.create_checkout(*pair)
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(attempt, buyers))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count("OUT_OF_STOCK") == 19
    with session_factory() as db:
        assert db.scalar(select(Product.stock)) == 0


def test_budget_includes_shipping(db_clean, provider):
    _, session_id, quote = fixture_data(budget=5000)
    with pytest.raises(DomainError) as error:
        orders.create_checkout(quote["quote_id"], session_id)
    assert error.value.code == "BUDGET_EXCEEDED"
    assert provider == []


def test_other_session_cannot_use_quote(db_clean, provider):
    _, _, quote = fixture_data()
    with session_factory() as db, db.begin():
        other = AgentSession(budget_minor=9999)
        db.add(other)
        db.flush()
        other_id = str(other.id)
    with pytest.raises(DomainError) as error:
        orders.create_checkout(quote["quote_id"], other_id)
    assert error.value.code == "QUOTE_NOT_FOUND"


def test_expired_quote_cannot_reserve(db_clean, provider):
    _, session_id, quote = fixture_data()
    with session_factory() as db, db.begin():
        db.get(Quote, uuid.UUID(quote["quote_id"])).expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(DomainError) as error:
        orders.create_checkout(quote["quote_id"], session_id)
    assert error.value.code == "QUOTE_EXPIRED"


def test_cancel_releases_once(db_clean, provider):
    _, session_id, quote = fixture_data()
    checkout = orders.create_checkout(quote["quote_id"], session_id)
    with session_factory() as db, db.begin():
        order = db.get(Order, uuid.UUID(checkout["order_id"]))
        orders.transition(db, order, "cancel", "buyer")
        with pytest.raises(DomainError):
            orders.transition(db, order, "cancel", "buyer")
    with session_factory() as db:
        assert db.scalar(select(Product.stock)) == 1


def capture_data(order_id, paypal_id, value="55.00"):
    return {
        "id": paypal_id,
        "status": "COMPLETED",
        "purchase_units": [
            {
                "custom_id": order_id,
                "payee": {"email_address": "sandbox@example.invalid"},
                "shipping": {"address": {"country_code": "GB"}},
                "payments": {
                    "captures": [
                        {
                            "id": "CAPTURE-1",
                            "status": "COMPLETED",
                            "amount": {"currency_code": "USD", "value": value},
                        }
                    ]
                },
            }
        ],
    }


def test_capture_amount_mismatch_never_marks_paid(db_clean, provider):
    _, session_id, quote = fixture_data()
    checkout = orders.create_checkout(quote["quote_id"], session_id)
    with session_factory() as db, db.begin():
        order = db.get(Order, uuid.UUID(checkout["order_id"]))
        with pytest.raises(DomainError):
            orders.apply_capture(
                db, order, capture_data(str(order.id), order.paypal_order_id, "0.01")
            )
        assert order.status == "checkout_created"


def test_completed_capture_is_idempotent(db_clean, provider):
    _, session_id, quote = fixture_data()
    checkout = orders.create_checkout(quote["quote_id"], session_id)
    with session_factory() as db, db.begin():
        order = db.get(Order, uuid.UUID(checkout["order_id"]))
        data = capture_data(str(order.id), order.paypal_order_id)
        orders.apply_capture(db, order, data)
        orders.apply_capture(db, order, data)
        assert order.status == "paid"
    with session_factory() as db:
        assert db.get(AgentSession, uuid.UUID(session_id)).spent_minor == 5500
        assert db.scalar(select(Product.stock)) == 0
