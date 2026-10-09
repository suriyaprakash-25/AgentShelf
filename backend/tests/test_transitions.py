"""Check every state/event pair, including forbidden paths and stock effects."""

import uuid

import pytest

from app import orders
from app.db import session_factory
from app.errors import DomainError
from app.models import AgentSession, Order, Product, Quote
from tests.test_orders import fixture_data

STATES = {state for state, event in orders.TRANSITIONS} | set(orders.TRANSITIONS.values())
EVENTS = {event for state, event in orders.TRANSITIONS}


@pytest.mark.integration
@pytest.mark.parametrize(
    "state,event", sorted((state, event) for state in STATES for event in EVENTS)
)
def test_each_state_event_pair(db_clean, state, event):
    _, session_id, quote_result = fixture_data()
    with session_factory() as db, db.begin():
        quote = db.get(Quote, uuid.UUID(quote_result["quote_id"]))
        product = db.get(Product, quote.product_id)
        product.stock = 0
        order = Order(
            quote_id=quote.id,
            seller_id=product.seller_id,
            amount_minor=quote.total_minor,
            currency=quote.currency,
            reserved_until=quote.expires_at,
            status=state,
        )
        db.add(order)
        db.flush()
        expected = orders.TRANSITIONS.get((state, event))
        if expected is None:
            with pytest.raises(DomainError) as error:
                orders.transition(db, order, event, "system")
            assert error.value.code == "INVALID_TRANSITION"
            assert order.status == state
            assert product.stock == 0
        else:
            orders.transition(db, order, event, "system")
            assert order.status == expected
            assert product.stock == (1 if expected in {"failed", "expired", "cancelled"} else 0)
            if expected == "paid":
                assert db.get(AgentSession, uuid.UUID(session_id)).spent_minor == quote.total_minor
