import uuid

import pytest
from sqlalchemy import select

from app import operator_recovery, paypal, reconciliation
from app.db import session_factory
from app.models import OpsAudit, Order, Product, Seller
from tests.test_reconciliation import checkout

pytestmark = pytest.mark.integration


def test_recovery_verifies_reference_amount_and_payee_without_capturing(
    db_clean, provider, monkeypatch
):
    order_id, _, paypal_id, approved = checkout(provider)
    approved["links"] = [
        {"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=fixture"}
    ]
    with session_factory() as db, db.begin():
        order = db.get(Order, order_id)
        actor_id = order.seller_id
        db.get(Seller, actor_id).is_operator = True
        order.paypal_order_id = None
        order.approval_url = None
    calls = []
    monkeypatch.setattr(paypal, "read_order", lambda identifier: approved)
    monkeypatch.setattr(paypal, "capture_order", lambda order: calls.append("capture"))
    assert (
        operator_recovery.correlate(actor_id, order_id, paypal_id)["status"] == "checkout_created"
    )
    assert (
        operator_recovery.correlate(actor_id, order_id, paypal_id)["status"] == "checkout_created"
    )
    reconciliation.reconcile(order_id)
    assert calls == []
    with session_factory() as db:
        assert db.get(Order, order_id).paypal_order_id == paypal_id
        assert db.scalar(select(Product.stock)) == 0
        assert db.query(OpsAudit).count() == 1


def test_recovery_mismatch_rolls_back_binding(db_clean, provider, monkeypatch):
    order_id, _, paypal_id, data = checkout(provider)
    with session_factory() as db, db.begin():
        order = db.get(Order, order_id)
        actor = order.seller_id
        db.get(Seller, actor).is_operator = True
        order.paypal_order_id = None
    data["purchase_units"][0]["amount"]["value"] = "0.01"
    monkeypatch.setattr(paypal, "read_order", lambda _: data)
    with pytest.raises(Exception, match="does not match"):
        operator_recovery.correlate(actor, order_id, paypal_id)
    with session_factory() as db:
        assert db.get(Order, order_id).paypal_order_id is None
        assert db.query(OpsAudit).count() == 0


def test_correlation_endpoint_requires_operator_csrf_and_confirmation(
    db_clean, provider, monkeypatch
):
    from fastapi.testclient import TestClient

    from app import email
    from app.main import create_app
    from tests.test_sellers import login

    delivered = []
    monkeypatch.setattr(email, "require_ready", lambda: None)
    monkeypatch.setattr(email, "send_login", lambda address, link, key: delivered.append(link))
    order_id, _, paypal_id, data = checkout(provider)
    data["links"] = [
        {"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=fixture"}
    ]
    monkeypatch.setattr(paypal, "read_order", lambda _: data)
    with session_factory() as db, db.begin():
        db.get(Order, order_id).paypal_order_id = None
    with TestClient(create_app(), base_url="https://testserver") as client:
        me, headers, _ = login(client, delivered)
        path = f"/api/ops/orders/{order_id}/correlate"
        body = {"paypal_order_id": paypal_id, "confirmed": True}
        assert client.post(path, headers=headers, json=body).status_code == 403
        with session_factory() as db, db.begin():
            db.get(Seller, uuid.UUID(me["id"])).is_operator = True
        assert client.post(path, json=body).status_code == 403
        assert (
            client.post(path, headers=headers, json={**body, "confirmed": False}).status_code == 409
        )
        assert (
            client.post(
                path, headers=headers, json={**body, "paypal_order_id": "../bad"}
            ).status_code
            == 422
        )
        assert client.post(path, headers=headers, json=body).status_code == 200
