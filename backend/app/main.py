"""FastAPI REST app and MCP transport; integrations report their real readiness."""

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app import orders, quotes
from app.config import get_settings
from app.db import get_engine, session_factory
from app.errors import DomainError
from app.mcp_server import create_mcp_server
from app.models import AgentSession, Seller
from app.routes.sellers import router as sellers_router
from app.routes.webhooks import router as webhooks_router

logger = logging.getLogger("agentshelf")
logging.basicConfig(level=logging.INFO, format="%(message)s")
settings = get_settings()
router = APIRouter()
_windows = defaultdict(deque)


async def request_context(request, call_next):
    """Attach a request ID, limit local pilot traffic and add browser security headers."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _windows[ip]
    while bucket and bucket[0] < now - 60:
        bucket.popleft()
    if len(bucket) >= 60 and request.url.path.startswith(("/mcp", "/api/playground")):
        response = JSONResponse(
            {"error": {"code": "RATE_LIMITED", "message": "Wait a minute before trying again."}},
            status_code=429,
            headers={"Retry-After": "60"},
        )
    else:
        bucket.append(now)
        response = await call_next(request)
    # Bound process-local bookkeeping. A shared limiter is a later hardening requirement.
    if len(_windows) > 10000:
        for key in list(_windows):
            if not _windows[key] or _windows[key][-1] < now - 60:
                del _windows[key]
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    logger.info(
        json.dumps(
            {
                "event": "request",
                "request_id": request_id,
                "method": request.method,
                "status": response.status_code,
            }
        )
    )
    return response


async def domain_error(request, exc):
    """Serialize public errors without internal trace or provider payload."""
    return JSONResponse(exc.payload(), status_code=exc.status)


async def invalid_request(request, exc):
    """Avoid reflecting sensitive invalid inputs into error responses."""
    return JSONResponse(
        {"error": {"code": "INVALID_INPUT", "message": "Check the required fields and limits."}},
        status_code=422,
    )


@router.get("/healthz")
def healthz():
    """Report database readiness without leaking connection details."""
    try:
        with get_engine().connect() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable", "paypal_mode": settings.paypal_mode}
    except SQLAlchemyError:
        return JSONResponse({"status": "unavailable", "database": "unreachable"}, status_code=503)


@router.get("/api/capabilities")
def capabilities():
    """Tell the UI what is actually configured; never expose secret values."""
    return {
        "paypal_mode": settings.paypal_mode,
        "checkout_configured": bool(settings.paypal_client_id and settings.paypal_client_secret),
        "ai_configured": bool(settings.anthropic_api_key),
        "whatsapp_configured": bool(
            settings.whatsapp_access_token and settings.whatsapp_phone_number_id
        ),
        "seller_login_configured": bool(settings.resend_api_key and settings.email_from),
        "live_checkout_enabled": settings.live_checkout_enabled,
        "supported_currencies": ["USD"],
        "shipping_destinations": ["US", "GB"],
    }


@router.get("/api/stores/{slug}")
def store(slug: str):
    """Return public store information with no merchant account details."""
    with session_factory() as db:
        seller = db.scalar(
            select(Seller).where(Seller.store_slug == slug, Seller.status == "active")
        )
        if not seller:
            raise DomainError("STORE_NOT_FOUND", "This store is unavailable.", 404)
        return {
            "name": seller.name,
            "slug": seller.store_slug,
            "country": seller.country,
            "currency": seller.currency,
            "mcp_url": settings.public_api_url + "/mcp",
            "products": quotes.search_products(db, limit=10, store_slug=slug),
        }


@router.get("/api/products")
def products(query: str = "", limit: int = 5, ship_to_country: str | None = None):
    """Expose the same search semantics as the MCP tool."""
    with session_factory() as db:
        return {
            "products": quotes.search_products(
                db, query=query, limit=limit, ship_to_country=ship_to_country
            )
        }


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionInput(InputModel):
    budget_minor: int = Field(ge=0, le=10000000, strict=True)
    currency: str = Field(default="USD", pattern="^USD$")


@router.post("/api/playground/sessions", status_code=201)
def create_session(body: SessionInput):
    """Create a buyer session; its random identifier acts as a scoped capability."""
    with session_factory() as db, db.begin():
        session = AgentSession(budget_minor=body.budget_minor, currency=body.currency)
        db.add(session)
        db.flush()
        return {
            "session_id": str(session.id),
            "budget_minor": session.budget_minor,
            "currency": session.currency,
        }


class QuoteInput(InputModel):
    product_id: uuid.UUID
    session_id: uuid.UUID
    qty: int = Field(ge=1, le=100, strict=True)
    ship_to_country: str = Field(pattern="^(US|GB)$")


@router.post("/api/quotes", status_code=201)
def create_quote(body: QuoteInput):
    """Create a quote using only server-owned money fields."""
    with session_factory() as db, db.begin():
        return quotes.get_quote(
            db, str(body.product_id), body.qty, body.ship_to_country, str(body.session_id)
        )


class CheckoutInput(InputModel):
    quote_id: uuid.UUID
    session_id: uuid.UUID


@router.post("/api/checkouts")
def checkout(body: CheckoutInput):
    """Start approval-required checkout with an idempotent reservation."""
    return orders.create_checkout(str(body.quote_id), str(body.session_id))


@router.get("/api/orders/{order_id}")
def order_status(order_id: uuid.UUID, session_id: uuid.UUID):
    """Show only an order owned by the buyer's session."""
    with session_factory() as db:
        return orders.get_order_status(db, str(order_id), str(session_id))


@router.get("/checkout/return")
def checkout_return(token: str):
    """Capture only after independently checking PayPal approval."""
    if not token.isalnum() or len(token) > 64:
        raise DomainError("INVALID_ORDER", "Invalid PayPal order identifier.")
    result = orders.capture_on_return(token)
    return RedirectResponse(
        settings.frontend_url + "/receipt?order=" + result["order_id"], status_code=303
    )


@router.get("/checkout/cancel")
def checkout_cancel(token: str):
    """Release an unpaid reservation once; preserve approved/captured orders."""
    if not token.isalnum() or len(token) > 64:
        raise DomainError("INVALID_ORDER", "Invalid PayPal order identifier.")
    result = orders.cancel_checkout(token)
    return RedirectResponse(
        settings.frontend_url + "/receipt?order=" + result["order_id"], status_code=303
    )


def create_app():
    """Create a fresh API and MCP lifecycle for each server or test instance."""
    server = create_mcp_server()
    hostname = urlsplit(settings.public_api_url).netloc
    transport = server.streamable_http_app(
        transport_security=TransportSecuritySettings(
            allowed_hosts=[hostname, "localhost:*", "127.0.0.1:*", "testserver"],
            allowed_origins=[settings.frontend_url, settings.public_api_url],
        )
    )

    @asynccontextmanager
    async def lifespan(application):
        async with server.session_manager.run():
            yield
        get_engine().dispose()

    application = FastAPI(title="AgentShelf", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "Mcp-Session-Id",
            "Mcp-Protocol-Version",
            "X-CSRF-Token",
        ],
        expose_headers=["X-Request-ID", "Mcp-Session-Id"],
    )
    application.middleware("http")(request_context)
    application.add_exception_handler(DomainError, domain_error)
    application.add_exception_handler(RequestValidationError, invalid_request)
    application.include_router(router)
    application.include_router(webhooks_router)
    application.include_router(sellers_router)
    application.mount("/", transport)
    return application


app = create_app()
