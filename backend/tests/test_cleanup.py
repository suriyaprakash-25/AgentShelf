from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import session_factory
from app.models import AgentSession, LoginChallenge, Seller, SellerSession, utcnow
from maintenance import cleanup_expired
from tests.test_orders import fixture_data


@pytest.mark.integration
def test_cleanup_expires_capabilities_and_keeps_budget_and_active_sessions(db_clean):
    fixture_data()
    now = utcnow()
    with session_factory() as db, db.begin():
        seller = db.scalar(select(Seller))
        old = AgentSession(
            budget_minor=100,
            spent_minor=50,
            chat_history=[{"role": "user", "content": "old chat"}],
            created_at=now - timedelta(days=31),
        )
        db.add(old)
        for label, expiry in [
            ("a", now - timedelta(minutes=1)),
            ("b", now + timedelta(minutes=10)),
        ]:
            db.add(
                LoginChallenge(
                    token_hash=label * 64, email="fixture@example.invalid", expires_at=expiry
                )
            )
            db.add(
                SellerSession(
                    token_hash=label * 64,
                    seller_id=seller.id,
                    csrf_token=label * 64,
                    expires_at=expiry,
                )
            )
        db.flush()
        old_id = old.id
    cleanup_expired()
    with session_factory() as db:
        assert db.query(LoginChallenge).count() == db.query(SellerSession).count() == 1
        old = db.get(AgentSession, old_id)
        assert old.chat_history == [] and old.budget_minor == 100 and old.spent_minor == 50
