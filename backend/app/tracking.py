"""Seller-owned single-parcel fulfilment with verified provider acknowledgement."""

import hashlib

from sqlalchemy import select

from app import orders, paypal
from app.db import session_factory
from app.errors import DomainError
from app.models import Order


def track(seller_id, order_id, carrier, number):
    label = carrier.strip()
    code = label.upper() if label.upper() in {"DHL", "FEDEX", "UPS", "USPS"} else "OTHER"
    with session_factory() as db, db.begin():
        order = db.scalar(
            select(Order)
            .where(Order.id == order_id, Order.seller_id == seller_id)
            .with_for_update()
        )
        if not order:
            raise DomainError("ORDER_NOT_FOUND", "This order is unavailable.", 404)
        if order.status not in {"paid", "shipped"} or not order.capture_id:
            raise DomainError(
                "PAYMENT_REQUIRED", "Only a confirmed paid order can be shipped.", 409
            )
        if order.reconciliation_error in {
            "PARTIAL_REFUND_REVIEW",
            "DISPUTE_OPEN",
            "DISPUTE_RESOLUTION_REVIEW",
            "REVERSAL_REVIEW_REQUIRED",
        }:
            raise DomainError(
                "PAYMENT_REVIEW_REQUIRED", "Resolve this payment review before fulfilment.", 409
            )
        if order.status == "shipped":
            if order.carrier == label and order.tracking_number == number:
                return {"status": "shipped", "carrier": label, "tracking_number": number}
            raise DomainError("TRACKING_ALREADY_SET", "This parcel already has tracking.", 409)
        body = {
            "capture_id": order.capture_id,
            "tracking_number": number,
            "carrier": code,
            "notify_payer": False,
        }
        if code == "OTHER":
            body["carrier_name_other"] = label
        key = "track-" + hashlib.sha256(f"{order.id}:{label}:{number}".encode()).hexdigest()[:32]
        try:
            data = paypal.request(
                "POST", f"/v2/checkout/orders/{order.paypal_order_id}/track", body, key
            )
        except DomainError:
            # Lost successful response: inspect the same order, do not invent shipment.
            data = paypal.read_order(order.paypal_order_id)
        tracker_id = order.capture_id + "-" + number
        confirmed = data.get("id") == order.paypal_order_id and any(
            tracker.get("id") == tracker_id
            for unit in data.get("purchase_units", [])
            for tracker in unit.get("shipping", {}).get("trackers", [])
        )
        if not confirmed:
            raise DomainError(
                "TRACKING_UNCONFIRMED", "Tracking is not confirmed. Retry this parcel.", 502
            )
        order.carrier, order.tracking_number = label, number
        orders.transition(db, order, "track", "seller")
        return {"status": order.status, "carrier": label, "tracking_number": number}
