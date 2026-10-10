import pytest

from app import jobs, orders, paypal, tracking
from app.db import session_factory
from app.models import Job, Order, PaymentAdjustment, Quote, WebhookEvent
from tests.test_tracking import paid_order

pytestmark = pytest.mark.integration


def event(kind, resource, number):
    with session_factory() as db, db.begin():
        identifier = f"EVENT-{number}"
        db.add(
            WebhookEvent(
                paypal_event_id=identifier,
                event_type=kind,
                resource_id=resource,
                verified=True,
                raw={"resource": {"id": resource}},
            )
        )
        job = Job(kind="paypal_event", payload={"event_id": identifier})
        db.add(job)
        db.flush()
        return job.id


def refund_data(resource, amount):
    return {
        "id": resource,
        "status": "COMPLETED",
        "amount": {"currency_code": "USD", "value": amount},
        "links": [
            {"rel": "up", "href": "https://api-m.sandbox.paypal.com/v2/payments/captures/CAPTURE"}
        ],
    }


def test_partial_then_full_refund_deduplicates_without_restock(db_clean, provider, monkeypatch):
    order_id, seller_id, _ = paid_order(provider)
    responses = {
        "REFUND1": refund_data("REFUND1", "20.00"),
        "REFUND2": refund_data("REFUND2", "35.00"),
    }
    monkeypatch.setattr(paypal, "request", lambda method, path: responses[path.rsplit("/", 1)[-1]])
    first = event("PAYMENT.CAPTURE.REFUNDED", "REFUND1", 1)
    assert jobs.run_one()
    with session_factory() as db:
        assert db.get(Job, first).status == "done"
        assert db.get(Order, order_id).status == "paid"
        assert db.get(Order, order_id).reconciliation_error == "PARTIAL_REFUND_REVIEW"
        order = db.get(Order, order_id)
        buyer = db.get(Quote, order.quote_id).agent_session_id
        summary = orders.get_order_status(db, str(order_id), str(buyer))
        assert summary["refunded_amount"] == "20.00"
        assert summary["payment_review"] == "PARTIAL_REFUND_REVIEW"
    with pytest.raises(Exception, match="review"):
        tracking.track(seller_id, order_id, "DHL", "12345")
    event("PAYMENT.CAPTURE.REFUNDED", "REFUND1", 2)
    assert jobs.run_one()
    event("PAYMENT.CAPTURE.REFUNDED", "REFUND2", 3)
    assert jobs.run_one()
    with session_factory() as db:
        assert db.get(Order, order_id).status == "refunded"
        assert db.query(PaymentAdjustment).count() == 2


def test_dispute_uses_provider_current_state_and_never_infers_refund(
    db_clean, provider, monkeypatch
):
    order_id, _, _ = paid_order(provider)
    data = {
        "dispute_id": "PP-DISPUTE",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "disputed_transactions": [{"seller_transaction_id": "CAPTURE"}],
    }
    monkeypatch.setattr(paypal, "request", lambda method, path: data)
    event("CUSTOMER.DISPUTE.CREATED", "PP-DISPUTE", 1)
    assert jobs.run_one()
    with session_factory() as db:
        assert db.get(Order, order_id).reconciliation_error == "DISPUTE_OPEN"
    data["status"] = "RESOLVED"
    event("CUSTOMER.DISPUTE.RESOLVED", "PP-DISPUTE", 2)
    assert jobs.run_one()
    with session_factory() as db:
        assert db.get(Order, order_id).status == "paid"
        assert db.get(Order, order_id).reconciliation_error == "DISPUTE_RESOLUTION_REVIEW"
        assert db.get(PaymentAdjustment, "PP-DISPUTE").status == "RESOLVED"


def test_refund_mismatched_capture_rolls_back_accounting(db_clean, provider, monkeypatch):
    order_id, _, _ = paid_order(provider)
    data = refund_data("REFUND", "55.00")
    data["links"][0]["href"] = "https://attacker.invalid/v2/payments/captures/CAPTURE"
    monkeypatch.setattr(paypal, "request", lambda *args: data)
    job_id = event("PAYMENT.CAPTURE.REFUNDED", "REFUND", 1)
    assert jobs.run_one()
    with session_factory() as db:
        assert db.get(Job, job_id).last_error == "REFUND_CORRELATION_FAILED"
        assert db.query(PaymentAdjustment).count() == 0
        assert db.get(Order, order_id).status == "paid"
