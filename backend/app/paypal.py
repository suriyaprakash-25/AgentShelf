"""The only module permitted to call PayPal; prices come from immutable quotes."""

import re
import threading
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx

from app.config import get_settings
from app.errors import DomainError

_token = None
_token_expires = 0.0
_token_lock = threading.Lock()


def money(minor: int):
    """Format nonnegative integer USD minor units without floating point."""
    if isinstance(minor, bool) or not isinstance(minor, int) or minor < 0:
        raise ValueError("Money requires a nonnegative integer")
    return f"{minor // 100}.{minor % 100:02d}"


def parse_money(value: str):
    """Parse an exact nonnegative two-decimal provider amount."""
    try:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,2})?", value):
            raise ValueError("Invalid amount")
        number = Decimal(value)
        if not number.is_finite() or number < 0 or number * 100 != (number * 100).to_integral():
            raise ValueError("Invalid amount")
        return int(number * 100)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DomainError(
            "PAYMENT_AMOUNT_INVALID", "Payment amount could not be verified.", 502
        ) from exc


def require_ready():
    """Fail explicitly instead of producing a simulated checkout."""
    settings = get_settings()
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        raise DomainError(
            "PAYPAL_NOT_CONFIGURED", "PayPal sandbox credentials are not configured.", 503
        )


def api_base():
    """Select an environment from validated configuration only."""
    return (
        "https://api-m.sandbox.paypal.com"
        if get_settings().paypal_mode == "sandbox"
        else "https://api-m.paypal.com"
    )


def get_token():
    """Cache a client-credentials token until sixty seconds before expiry."""
    global _token, _token_expires
    require_ready()
    with _token_lock:
        if _token and time.monotonic() < _token_expires:
            return _token
        settings = get_settings()
        try:
            response = httpx.post(
                api_base() + "/v1/oauth2/token",
                auth=(
                    settings.paypal_client_id.get_secret_value(),
                    settings.paypal_client_secret.get_secret_value(),
                ),
                data={"grant_type": "client_credentials"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            _token = data["access_token"]
            _token_expires = time.monotonic() + max(0, int(data["expires_in"]) - 60)
            return _token
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise DomainError(
                "PAYPAL_UNAVAILABLE", "PayPal authentication is unavailable. Try again later.", 502
            ) from exc


def request(method: str, path: str, body=None, request_id=None):
    """Make a bounded provider call without logging secrets or buyer details."""
    headers = {"Authorization": "Bearer " + get_token(), "Prefer": "return=representation"}
    if method == "POST":
        if not request_id:
            raise ValueError("Every PayPal POST requires an idempotency key")
        headers["PayPal-Request-Id"] = request_id
    try:
        response = httpx.request(method, api_base() + path, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json() if response.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise DomainError(
            "PAYPAL_UNAVAILABLE", "Payment status is uncertain. Retry the same order.", 502
        ) from exc


def create_order(order, quote, seller):
    """Create an approval-required physical-goods order from a server quote."""
    settings = get_settings()
    if settings.paypal_mode == "live" and (
        not seller.live_eligible or seller.paypal_merchant_id != settings.live_merchant_id
    ):
        raise DomainError(
            "MERCHANT_NOT_ELIGIBLE", "This merchant is not enabled for live checkout.", 403
        )
    cur = quote.currency
    base = settings.public_api_url.rstrip("/")
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": str(order.id),
                "custom_id": str(order.id),
                "payee": {"email_address": seller.paypal_email},
                "amount": {
                    "currency_code": cur,
                    "value": money(quote.total_minor),
                    "breakdown": {
                        "item_total": {
                            "currency_code": cur,
                            "value": money(quote.item_total_minor),
                        },
                        "shipping": {"currency_code": cur, "value": money(quote.shipping_minor)},
                    },
                },
                "items": [
                    {
                        "name": quote.title[:127],
                        "quantity": str(quote.qty),
                        "unit_amount": {"currency_code": cur, "value": money(quote.unit_minor)},
                        "category": "PHYSICAL_GOODS",
                    }
                ],
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": seller.name[:127],
                    "shipping_preference": "GET_FROM_FILE",
                    "user_action": "PAY_NOW",
                    "return_url": base + "/checkout/return",
                    "cancel_url": base + "/checkout/cancel",
                }
            }
        },
    }
    data = request("POST", "/v2/checkout/orders", body, "create-" + str(order.id))
    return data["id"], approval_link(data)


def approval_link(data):
    links = [
        link.get("href")
        for link in data.get("links", [])
        if link.get("rel") in {"payer-action", "approve"}
    ]
    expected = (
        {"www.sandbox.paypal.com", "sandbox.paypal.com"}
        if get_settings().paypal_mode == "sandbox"
        else {"www.paypal.com", "paypal.com"}
    )
    if not links or not isinstance(links[0], str) or len(links[0]) > 4096:
        raise DomainError("PAYPAL_LINK_MISSING", "PayPal did not return an approval link.", 502)
    try:
        url = urlsplit(links[0])
        valid = (
            url.scheme == "https"
            and url.hostname in expected
            and not url.username
            and not url.password
            and url.port in {None, 443}
        )
    except ValueError:
        valid = False
    if not valid:
        raise DomainError("PAYPAL_LINK_INVALID", "Approval link could not be verified.", 502)
    return links[0]


def read_order(paypal_order_id: str):
    """Read authoritative approval and capture state."""
    return request("GET", "/v2/checkout/orders/" + paypal_order_id)


def capture_order(order):
    """Retry capture only with the same order and idempotency key."""
    return request(
        "POST",
        f"/v2/checkout/orders/{order.paypal_order_id}/capture",
        {},
        "capture-" + str(order.id),
    )


def verify_webhook(headers, event):
    """Verify all five PayPal signature headers with the registered webhook ID."""
    webhook_id = get_settings().paypal_webhook_id
    required = [
        "paypal-auth-algo",
        "paypal-cert-url",
        "paypal-transmission-id",
        "paypal-transmission-sig",
        "paypal-transmission-time",
    ]
    if not webhook_id or any(not headers.get(name) for name in required):
        return False
    body = {
        "auth_algo": headers[required[0]],
        "cert_url": headers[required[1]],
        "transmission_id": headers[required[2]],
        "transmission_sig": headers[required[3]],
        "transmission_time": headers[required[4]],
        "webhook_id": webhook_id,
        "webhook_event": event,
    }
    data = request(
        "POST", "/v1/notifications/verify-webhook-signature", body, "verify-" + str(event["id"])
    )
    return data.get("verification_status") == "SUCCESS"


def refund_capture(capture_id: str, amount_minor: int, currency: str, request_id: str):
    """Issue a bounded capture refund with a deterministic idempotency key."""
    body = {
        "amount": {
            "value": money(amount_minor),
            "currency_code": currency,
        }
    }
    return request("POST", f"/v2/payments/captures/{capture_id}/refund", body, request_id)


def create_and_send_invoice(
    seller, recipient_email: str, amount_minor: int, currency: str, note: str, request_id: str
):
    """Create and send a PayPal invoice on behalf of the seller with idempotency keys."""
    draft_body = {
        "detail": {
            "currency_code": currency,
            "note": note[:400],
        },
        "invoicer": {
            "email_address": seller.paypal_email,
        },
        "primary_recipients": [
            {
                "billing_info": {
                    "email_address": recipient_email,
                }
            }
        ],
        "items": [
            {
                "name": f"{seller.name[:80]} order",
                "quantity": "1",
                "unit_amount": {
                    "currency_code": currency,
                    "value": money(amount_minor),
                },
            }
        ],
    }
    created = request("POST", "/v2/invoicing/invoices", draft_body, "inv-create-" + request_id)
    invoice_id = created.get("id")
    if not isinstance(invoice_id, str) or not invoice_id:
        raise DomainError("PAYPAL_UNAVAILABLE", "PayPal did not return an invoice ID.", 502)
    request(
        "POST",
        f"/v2/invoicing/invoices/{invoice_id}/send",
        {"send_to_invoicer": False},
        "inv-send-" + request_id,
    )
    return {"invoice_id": invoice_id, "status": "SENT"}


def sync_catalog_product(product):
    """Mirror a live seller product to the PayPal Catalog Products API (S-2)."""
    body = {
        "id": str(product.id),
        "name": product.title[:127],
        "description": (product.description or product.title)[:256],
        "type": "PHYSICAL",
        "category": "MERCHANDISE",
    }
    data = request("POST", "/v1/catalogs/products", body, "catalog-" + str(product.id))
    return {"paypal_product_id": data.get("id", str(product.id)), "status": "SYNCED"}
