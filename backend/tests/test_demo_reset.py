import pytest
from sqlalchemy import select

import maintenance
from app import orders, quotes
from app.config import get_settings
from app.db import session_factory
from app.models import AgentSession, Order, Product
from seed import seed

pytestmark = pytest.mark.integration


def test_sandbox_reset_refuses_pending_reservation_and_preserves_history(
    db_clean, provider, monkeypatch
):
    monkeypatch.setattr(get_settings(), "paypal_mode", "sandbox")
    monkeypatch.setattr(get_settings(), "app_env", "test")
    seed()
    with session_factory() as db, db.begin():
        product = db.scalar(select(Product).where(Product.short_no == 1))
        product.stock = 3
        buyer = AgentSession(budget_minor=10000)
        db.add(buyer)
        db.flush()
        quote = quotes.get_quote(db, str(product.id), 1, "GB", str(buyer.id))
        buyer_id = str(buyer.id)
    orders.create_checkout(quote["quote_id"], buyer_id)
    with pytest.raises(ValueError, match="outstanding"):
        maintenance.demo_reset("RESET_SYNTHETIC_SANDBOX_STOCK")
    with session_factory() as db, db.begin():
        order = db.scalar(select(Order))
        orders.transition(db, order, "cancel", "test")
    maintenance.demo_reset("RESET_SYNTHETIC_SANDBOX_STOCK")
    with session_factory() as db:
        assert db.scalar(select(Product.stock).where(Product.short_no == 1)) == 8
        assert db.query(Order).count() == 1
        assert db.scalar(select(Order)).status == "cancelled"


def test_reset_requires_exact_phrase_and_never_live(monkeypatch):
    monkeypatch.setattr(get_settings(), "paypal_mode", "sandbox")
    with pytest.raises(ValueError):
        maintenance.demo_reset("yes")
    monkeypatch.setattr(get_settings(), "paypal_mode", "live")
    with pytest.raises(ValueError):
        maintenance.demo_reset("RESET_SYNTHETIC_SANDBOX_STOCK")
