"""Anonymous REST surface: discovery, storefront reads, buyer sessions and checkout.

Handlers only translate HTTP to service calls; rules live in ``storefront``, ``quotes``
and ``orders`` so REST and MCP share one implementation.
"""

import asyncio
import uuid

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app import db as database
from app import llm, orders, paypal, quotes, storefront
from app.config import get_settings
from app.errors import DomainError

router = APIRouter()

MCP_TOOLS = ("search_products", "get_quote", "create_checkout", "get_order_status")
SUPPORTED_CURRENCIES = ("USD",)
SHIPPING_DESTINATIONS = ("US", "GB")
MAX_BUDGET_MINOR = 10_000_000
MAX_QUOTE_QTY = 100
PAYPAL_TOKEN_MAX = 64
HEALTH_TIMEOUT = 3.0
# A bounded BCP 47-style tag keeps prompts and translation cache keys well-formed.
LANGUAGE_TAG = r"^[A-Za-z]{2,3}(-[A-Za-z]{2})?$"


def _reachable(engine):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


async def _probe(engine):
    """A database that accepts TCP but never answers must not hang the probe."""
    try:
        return await asyncio.wait_for(run_in_threadpool(_reachable, engine), HEALTH_TIMEOUT)
    except TimeoutError:
        return False


@router.get("/healthz")
async def healthz():
    """Report database readiness within a few seconds, without connection details."""
    settings = get_settings()
    if not await _probe(database.get_engine()):
        return JSONResponse({"status": "unavailable", "database": "unreachable"}, status_code=503)
    body = {"status": "ok", "database": "reachable", "paypal_mode": settings.paypal_mode}
    if settings.database_read_url:
        # A lagging or lost replica degrades reads to the primary; it is not an outage.
        body["read_replica"] = (
            "reachable" if await _probe(database.get_read_engine()) else "unreachable"
        )
    return body


@router.get("/.well-known/mcp.json")
def mcp_discovery():
    """Publish MCP Streamable HTTP endpoint and tool metadata for agent crawlers."""
    return {
        "schema_version": "2025-11-25",
        "name": "AgentShelf",
        "description": "WhatsApp-seeded merchant catalog with PayPal Orders v2 checkout.",
        "transport": {
            "type": "streamable-http",
            "endpoint": get_settings().public_api_url + "/mcp",
        },
        "tools": list(MCP_TOOLS),
    }


@router.get("/api/monitoring-config")
def monitoring_config():
    """Expose only the opt-in public browser DSN, never server/provider secrets."""
    settings = get_settings()
    return JSONResponse(
        {"dsn": settings.browser_sentry_dsn, "environment": settings.app_env},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/capabilities")
def capabilities():
    """Tell the UI what is actually configured; never expose secret values."""
    settings = get_settings()
    return {
        "paypal_mode": settings.paypal_mode,
        "checkout_configured": bool(settings.paypal_client_id and settings.paypal_client_secret),
        "ai_configured": llm.ai_configured(settings),
        "whatsapp_configured": bool(
            settings.whatsapp_access_token and settings.whatsapp_phone_number_id
        ),
        "seller_login_configured": bool(settings.resend_api_key and settings.email_from),
        "live_checkout_enabled": settings.live_checkout_enabled,
        "supported_currencies": list(SUPPORTED_CURRENCIES),
        "shipping_destinations": list(SHIPPING_DESTINATIONS),
    }


@router.get("/api/stats")
def stats():
    """Measured catalog counts for the landing page (cached for one minute)."""
    return JSONResponse(
        storefront.platform_stats(), headers={"Cache-Control": "public, max-age=60"}
    )


@router.get("/api/stores/{slug}")
def store(slug: str, after: uuid.UUID | None = None):
    """Return public store information with no merchant account details."""
    return storefront.store_page(slug, after)


@router.get("/api/stores/{slug}/schema.json")
def store_schema(slug: str):
    """Return schema.org Product JSON-LD for a public merchant storefront."""
    return storefront.store_schema(slug)


@router.get("/api/products")
def products(
    query: str = "",
    limit: int = 5,
    ship_to_country: str | None = None,
    after: uuid.UUID | None = None,
):
    """Expose the same ranked search semantics as the MCP tool, with a keyset cursor."""
    items = storefront.search(
        query=query, limit=limit, ship_to_country=ship_to_country, after=after
    )
    return storefront.page(items, limit)


@router.get("/api/products/{product_id}/translate")
def translate_product(product_id: uuid.UUID, lang: str = Query("es", pattern=LANGUAGE_TAG)):
    """Translate listing copy while keeping server-side price, currency and stock."""
    return storefront.translated_product(product_id, lang)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionInput(InputModel):
    budget_minor: int = Field(ge=0, le=MAX_BUDGET_MINOR, strict=True)
    currency: str = Field(default="USD", pattern="^USD$")


@router.post("/api/playground/sessions", status_code=201)
def create_session(body: SessionInput):
    """Create a buyer session; its random identifier acts as a scoped capability."""
    return storefront.create_buyer_session(body.budget_minor, body.currency)


class QuoteInput(InputModel):
    product_id: uuid.UUID
    session_id: uuid.UUID
    qty: int = Field(ge=1, le=MAX_QUOTE_QTY, strict=True)
    ship_to_country: str = Field(pattern="^(US|GB)$")


@router.post("/api/quotes", status_code=201)
def create_quote(body: QuoteInput):
    """Create a quote using only server-owned money fields."""
    with database.session_factory() as db, db.begin():
        return quotes.get_quote(
            db, str(body.product_id), body.qty, body.ship_to_country, str(body.session_id)
        )


class CheckoutInput(InputModel):
    quote_id: uuid.UUID
    session_id: uuid.UUID


@router.post("/api/checkouts")
def checkout(body: CheckoutInput):
    """Start approval-required checkout with an idempotent reservation."""
    paypal.require_ready()
    return orders.create_checkout(str(body.quote_id), str(body.session_id))


@router.get("/api/orders/{order_id}")
def order_status(order_id: uuid.UUID, session_id: uuid.UUID):
    """Show only an order owned by the buyer's session."""
    with database.session_factory() as db:
        return orders.get_order_status(db, str(order_id), str(session_id))


def _paypal_token(token):
    if not token.isalnum() or len(token) > PAYPAL_TOKEN_MAX:
        raise DomainError("INVALID_ORDER", "Invalid PayPal order identifier.")
    return token


def _receipt(result):
    return RedirectResponse(
        get_settings().frontend_url + "/receipt?order=" + result["order_id"], status_code=303
    )


@router.get("/checkout/return")
def checkout_return(token: str):
    """Capture only after independently checking PayPal approval."""
    return _receipt(orders.capture_on_return(_paypal_token(token)))


@router.get("/checkout/cancel")
def checkout_cancel(token: str):
    """Release an unpaid reservation once; preserve approved/captured orders."""
    return _receipt(orders.cancel_checkout(_paypal_token(token)))
