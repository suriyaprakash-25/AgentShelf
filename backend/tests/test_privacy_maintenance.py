import uuid
from datetime import timedelta

import pytest

from app import privacy_maintenance
from app.db import session_factory
from app.models import Job, OpsAudit, Order, Seller, WebhookEvent, utcnow
from tests.test_tracking import paid_order

pytestmark = pytest.mark.integration


def test_retention_preview_and_apply_preserve_accounting_and_unprocessed_data(db_clean, provider):
    order_id, seller_id, _ = paid_order(provider)
    with session_factory() as db, db.begin():
        db.get(Seller, seller_id).is_operator = True
        order = db.get(Order, order_id)
        order.status = "shipped"
        order.ship_to = {"address": "private-address"}
        order.updated_at = utcnow() - timedelta(days=40)
        order.amount_minor = 5500
        db.add(
            Job(
                kind="whatsapp_send",
                status="done",
                created_at=order.updated_at,
                payload={"phone": "private-phone", "text": "private-address"},
            )
        )
        db.add(
            Job(
                kind="whatsapp_send",
                status="failed",
                created_at=order.updated_at,
                payload={"phone": "retry-needed"},
            )
        )
        for identifier, processed in [("OLD", True), ("PENDING", False)]:
            db.add(
                WebhookEvent(
                    paypal_event_id=identifier,
                    event_type="PAYMENT.CAPTURE.COMPLETED",
                    resource_id="CAPTURE",
                    verified=True,
                    processed_at=utcnow() if processed else None,
                    raw={
                        "id": identifier,
                        "event_type": "PAYMENT.CAPTURE.COMPLETED",
                        "resource": {"id": "CAPTURE", "shipping": "private-address"},
                        "payer": "private-email",
                    },
                )
            )
    preview = privacy_maintenance.review()
    assert preview["legacy_inboxes"] == 1 and preview["terminal_addresses"] == 1
    with session_factory() as db:
        assert db.get(Order, order_id).ship_to
    applied = privacy_maintenance.review(seller_id, True)
    assert applied["old_completed_message_payloads"] == 1
    with session_factory() as db:
        order = db.get(Order, order_id)
        assert (
            order.ship_to is None and order.amount_minor == 5500 and order.capture_id == "CAPTURE"
        )
        assert "private" not in str(db.get(WebhookEvent, "OLD").raw)
        assert "private" in str(db.get(WebhookEvent, "PENDING").raw)
        failed = db.query(Job).filter_by(status="failed").one()
        assert failed.payload["phone"] == "retry-needed"
        assert db.query(OpsAudit).count() == 3


def test_retention_refuses_unverified_operator_and_short_policy(db_clean):
    with pytest.raises(ValueError):
        privacy_maintenance.review(days=1)
    with pytest.raises(Exception, match="operator"):
        privacy_maintenance.review(uuid.uuid4(), True)
