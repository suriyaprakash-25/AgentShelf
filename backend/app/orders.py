"""Locked stock reservation, budget accounting, capture and transition audit."""

from sqlalchemy import func, select

from app import paypal
from app.db import session_factory
from app.errors import DomainError
from app.guards import parse_id
from app.models import (
    AgentSession,
    Job,
    Order,
    OrderEvent,
    PaymentAdjustment,
    Product,
    Quote,
    Seller,
    utcnow,
)

TRANSITIONS = {
    ("checkout_created", "approve"): "approved",
    ("approved", "capture_completed"): "paid",
    ("approved", "capture_pending"): "capture_pending",
    ("capture_pending", "capture_completed"): "paid",
    ("approved", "decline"): "failed",
    ("capture_pending", "decline"): "failed",
    ("checkout_created", "expire"): "expired",
    ("checkout_created", "cancel"): "cancelled",
    ("paid", "track"): "shipped",
    ("paid", "refund"): "refunded",
    ("shipped", "refund"): "refunded",
}
RESERVED_STATES = {"checkout_created", "approved", "capture_pending"}
PAID_STATES = frozenset({"paid", "shipped", "refunded"})
CLOSED_STATES = frozenset({"expired", "cancelled", "failed", "refunded"})
RELEASES_STOCK = frozenset({"failed", "expired", "cancelled"})
PROVIDER_LINKED_STATES = frozenset({"approved", "capture_pending", "paid", "shipped"})
AWAITING_CAPTURE = frozenset({"approved", "capture_pending"})


def transition(db, order, event, source):
    """Apply one allowed transition and persist its stock effect and audit entry."""
    old = order.status
    new = TRANSITIONS.get((old, event))
    if new is None:
        raise DomainError("INVALID_TRANSITION", "This order cannot accept that action.", 409)
    quote = db.get(Quote, order.quote_id)
    if new in RELEASES_STOCK:
        product = db.scalar(select(Product).where(Product.id == quote.product_id).with_for_update())
        product.stock += quote.qty
    if new == "paid":
        session = db.scalar(
            select(AgentSession).where(AgentSession.id == quote.agent_session_id).with_for_update()
        )
        session.spent_minor += order.amount_minor
        order.paid_at = utcnow()
        db.add(
            Job(
                kind="paid_notification",
                dedupe_key=f"paid:{order.id}",
                payload={"order_id": str(order.id)},
            )
        )
    order.status = new
    order.updated_at = utcnow()
    db.add(
        OrderEvent(order_id=order.id, type=event, source=source, payload={"from": old, "to": new})
    )


def order_ref(order):
    return {"order_id": str(order.id), "status": order.status}


def checkout_json(order):
    """Return only approval instructions and stable order identifiers."""
    return {
        "order_id": str(order.id),
        "approval_url": order.approval_url,
        "expires_at": order.reserved_until.isoformat(),
        "instruction": "Show this approval link to the human. Only PayPal can approve payment.",
    }


def create_checkout(quote_id, session_id):
    """Persist a reservation first, then retry external creation with one stable key."""
    paypal.require_ready()
    # Persisting before the network call lets retries recover after an uncertain provider result.
    reserved = reserve(parse_id(quote_id), parse_id(session_id))
    if isinstance(reserved, dict):
        return reserved
    return ensure_provider_order(reserved)


def _within_budget(db, buyer, quote):
    pending = db.scalar(
        select(func.coalesce(func.sum(Order.amount_minor), 0))
        .join(Quote, Quote.id == Order.quote_id)
        .where(Quote.agent_session_id == buyer.id, Order.status.in_(RESERVED_STATES))
    )
    return buyer.spent_minor + pending + quote.total_minor <= buyer.budget_minor


def _reserve_stock(db, quote):
    product = db.scalar(select(Product).where(Product.id == quote.product_id).with_for_update())
    seller = db.get(Seller, product.seller_id)
    if (
        product.status != "live"
        or seller.status != "active"
        or not seller.consent_at
        or product.stock < quote.qty
    ):
        raise DomainError("OUT_OF_STOCK", "This product is no longer available.", 409)
    product.stock -= quote.qty
    return product


def reserve(quote_uuid, session_uuid):
    """Lock session, quote and stock; return an existing checkout or the new order ID."""
    with session_factory() as db, db.begin():
        buyer = db.scalar(
            select(AgentSession).where(AgentSession.id == session_uuid).with_for_update()
        )
        if not buyer:
            raise DomainError("SESSION_NOT_FOUND", "Start a buyer session first.", 404)
        quote = db.scalar(select(Quote).where(Quote.id == quote_uuid).with_for_update())
        if not quote or quote.agent_session_id != buyer.id:
            raise DomainError("QUOTE_NOT_FOUND", "This quote does not belong to this session.", 404)
        existing = db.scalar(select(Order).where(Order.quote_id == quote.id))
        if existing:
            if existing.status in CLOSED_STATES:
                raise DomainError(
                    "CHECKOUT_CLOSED", "This checkout is closed. Request a new quote.", 409
                )
            return checkout_json(existing) if existing.approval_url else existing.id
        if quote.expires_at <= utcnow():
            raise DomainError("QUOTE_EXPIRED", "This quote expired. Request a new quote.", 409)
        if not _within_budget(db, buyer, quote):
            raise DomainError(
                "BUDGET_EXCEEDED",
                "The total including shipping exceeds your remaining budget.",
                409,
            )
        product = _reserve_stock(db, quote)
        order = Order(
            quote_id=quote.id,
            seller_id=product.seller_id,
            amount_minor=quote.total_minor,
            currency=quote.currency,
            reserved_until=quote.expires_at,
        )
        db.add(order)
        db.flush()
        db.add(
            OrderEvent(
                order_id=order.id,
                type="create_checkout",
                source="agent",
                payload={"to": "checkout_created"},
            )
        )
        return order.id


def ensure_provider_order(order_id):
    """Create the PayPal order once per reservation, under the order row lock."""
    with session_factory() as db, db.begin():
        order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order.status != "checkout_created":
            if order.approval_url and order.status in PROVIDER_LINKED_STATES:
                return checkout_json(order)
            raise DomainError("CHECKOUT_CLOSED", "This checkout is closed.", 409)
        if not order.paypal_order_id:
            quote = db.get(Quote, order.quote_id)
            seller = db.get(Seller, order.seller_id)
            order.paypal_order_id, order.approval_url = paypal.create_order(order, quote, seller)
        return checkout_json(order)


def matches_quote(unit, quote, seller, amount):
    """True when provider shipping country, money and payee all equal our records."""
    return (
        unit.get("shipping", {}).get("address", {}).get("country_code") == quote.ship_to_country
        and amount.get("currency_code") == quote.currency
        and paypal.parse_money(amount.get("value")) == quote.total_minor
        and unit.get("payee", {}).get("email_address", "").casefold()
        == seller.paypal_email.casefold()
    )


def require_approved_match(db, order, data, message, check_reference):
    """Validate an APPROVED (uncaptured) provider order before money moves."""
    unit = data["purchase_units"][0]
    quote = db.get(Quote, order.quote_id)
    seller = db.get(Seller, order.seller_id)
    reference_ok = not check_reference or unit.get("custom_id") == str(order.id)
    if not reference_ok or not matches_quote(unit, quote, seller, unit.get("amount", {})):
        raise DomainError("PAYMENT_MISMATCH", message, 409)


def _verify_capture(db, order, unit, amount):
    """Each mismatch keeps its own message so operators can see which field differed."""
    quote = db.get(Quote, order.quote_id)
    if (
        amount.get("currency_code") != quote.currency
        or paypal.parse_money(amount.get("value")) != quote.total_minor
    ):
        raise DomainError("PAYMENT_MISMATCH", "Captured amount does not match the quote.", 502)
    seller = db.get(Seller, order.seller_id)
    payee = unit.get("payee", {})
    if payee.get("email_address", "").casefold() != seller.paypal_email.casefold():
        raise DomainError("PAYMENT_MISMATCH", "Payment recipient does not match.", 502)
    shipping = unit.get("shipping", {}).get("address", {})
    if shipping.get("country_code") != quote.ship_to_country:
        raise DomainError(
            "PAYMENT_MISMATCH", "Approved shipping country does not match the quote.", 502
        )


def apply_capture(db, order, data):
    """Reconcile exact provider identity, currency and captured amount before payment."""
    if data.get("id") != order.paypal_order_id:
        raise DomainError("PAYMENT_MISMATCH", "PayPal order identity does not match.", 502)
    units = data.get("purchase_units", [])
    if len(units) != 1:
        raise DomainError("PAYMENT_MISMATCH", "Unexpected purchase units.", 502)
    unit = units[0]
    if unit.get("custom_id") != str(order.id):
        raise DomainError("PAYMENT_MISMATCH", "PayPal reference does not match.", 502)
    captures = unit.get("payments", {}).get("captures", [])
    if not captures:
        return False
    if len(captures) != 1:
        raise DomainError("PAYMENT_MISMATCH", "Unexpected capture count.", 502)
    capture = captures[0]
    _verify_capture(db, order, unit, capture.get("amount", {}))
    if order.status in PAID_STATES:
        return True
    if order.status == "checkout_created":
        transition(db, order, "approve", "paypal")
    status = capture.get("status")
    order.capture_id = capture["id"]
    order.ship_to = unit.get("shipping")
    if status == "COMPLETED":
        transition(db, order, "capture_completed", "paypal")
        order.reconciliation_error = None
    elif status == "PENDING" and order.status == "approved":
        transition(db, order, "capture_pending", "paypal")
    elif status in {"DECLINED", "FAILED"}:
        transition(db, order, "decline", "paypal")
    else:
        if status != "PENDING":
            raise DomainError(
                "PAYMENT_STATUS_UNKNOWN", "Payment status requires reconciliation.", 502
            )
    return True


def capture_on_return(paypal_order_id):
    """Persist verified capture intent before calling the provider under a second lock."""
    with session_factory() as db, db.begin():
        order = db.scalar(
            select(Order).where(Order.paypal_order_id == paypal_order_id).with_for_update()
        )
        if not order:
            raise DomainError("ORDER_NOT_FOUND", "This PayPal order is not ours.", 404)
        if order.status in PAID_STATES:
            return order_ref(order)
        if order.status not in RESERVED_STATES:
            raise DomainError("CHECKOUT_CLOSED", "This checkout is closed.", 409)
        data = paypal.read_order(paypal_order_id)
        if apply_capture(db, order, data):
            return order_ref(order)
        if data.get("status") != "APPROVED":
            raise DomainError("APPROVAL_REQUIRED", "Approve the payment on PayPal first.", 409)
        # Validate destination and amount BEFORE moving money.
        require_approved_match(
            db, order, data, "Approved payment does not match your quote.", check_reference=True
        )
        if order.status == "checkout_created":
            transition(db, order, "approve", "buyer")
    # A timeout, crash or failed re-read cannot roll the approval back to a releasable state.
    return capture_after_intent(paypal_order_id)


def capture_after_intent(paypal_order_id):
    """Capture an approved order once, reconciling any lost provider response."""
    with session_factory() as db, db.begin():
        order = db.scalar(
            select(Order).where(Order.paypal_order_id == paypal_order_id).with_for_update()
        )
        if order.status in PAID_STATES:
            return order_ref(order)
        if order.status not in AWAITING_CAPTURE:
            raise DomainError("CHECKOUT_CLOSED", "This checkout is closed.", 409)
        data = paypal.read_order(paypal_order_id)
        if apply_capture(db, order, data):
            return order_ref(order)
        if data.get("status") != "APPROVED":
            raise DomainError("CAPTURE_UNCERTAIN", "Keep this reservation for reconciliation.", 502)
        require_approved_match(
            db,
            order,
            data,
            "Approved payment changed. Review before capture.",
            check_reference=False,
        )
        try:
            data = paypal.capture_order(order)
        except DomainError:
            # A lost response or already-captured error must be reconciled, never guessed.
            data = paypal.read_order(paypal_order_id)
        if not apply_capture(db, order, data):
            raise DomainError(
                "CAPTURE_UNCERTAIN", "Capture is not confirmed. Retry the same order.", 502
            )
        return order_ref(order)


def get_order_status(db, order_id, session_id):
    """Return a session-owned order summary without personal data."""
    order = db.get(Order, parse_id(order_id))
    if not order or db.get(Quote, order.quote_id).agent_session_id != parse_id(session_id):
        raise DomainError("ORDER_NOT_FOUND", "This order does not belong to this session.", 404)
    return {
        "status": order.status,
        "amount": paypal.money(order.amount_minor),
        "currency": order.currency,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "carrier": order.carrier,
        "tracking_number": order.tracking_number,
        "payment_review": order.reconciliation_error,
        "refunded_amount": paypal.money(
            int(
                db.scalar(
                    select(func.coalesce(func.sum(PaymentAdjustment.amount_minor), 0)).where(
                        PaymentAdjustment.order_id == order.id,
                        PaymentAdjustment.kind == "refund",
                        PaymentAdjustment.status == "COMPLETED",
                    )
                )
            )
        ),
    }


def cancel_checkout(paypal_order_id):
    """Cancel an unpaid checkout after checking the provider under the order lock."""
    with session_factory() as db, db.begin():
        order = db.scalar(
            select(Order).where(Order.paypal_order_id == paypal_order_id).with_for_update()
        )
        if not order:
            raise DomainError("ORDER_NOT_FOUND", "This PayPal order is not ours.", 404)
        if order.status == "checkout_created":
            data = paypal.read_order(paypal_order_id)
            if not apply_capture(db, order, data):
                if data.get("status") == "APPROVED":
                    transition(db, order, "approve", "paypal")
                elif data.get("status") == "VOIDED":
                    transition(db, order, "cancel", "buyer")
                elif data.get("status") in {"CREATED", "PAYER_ACTION_REQUIRED"}:
                    order.reconciliation_error = "CANCELLATION_UNCONFIRMED"
                else:
                    raise DomainError(
                        "PAYMENT_STATUS_UNKNOWN", "Recheck the payment before cancellation.", 409
                    )
        return order_ref(order)
