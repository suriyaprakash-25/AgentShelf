"""FastAPI REST app and MCP transport; integrations report their real readiness."""

import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from app import llm, observability, orders, quotes, rate_limits
from app.body_limits import BodySizeLimitMiddleware
from app.config import get_settings, parse_browser_sentry_dsn
from app.db import get_engine, session_factory
from app.errors import DomainError
from app.mcp_server import create_mcp_server
from app.models import AgentSession, Product, Seller
from app.routes.analytics import router as analytics_router
from app.routes.listings import router as listings_router
from app.routes.operations import router as operations_router
from app.routes.playground import router as playground_router
from app.routes.sellers import router as sellers_router
from app.routes.webhooks import router as webhooks_router

logger = logging.getLogger("agentshelf")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("uvicorn.access").disabled = True
settings = get_settings()
router = APIRouter()
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


async def request_context(request, call_next):
    """Attach a request ID, limit local pilot traffic and add browser security headers."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    ip = rate_limits.client_ip(request)
    try:
        if request.url.path.startswith(("/mcp", "/api/playground")) and request.method != "OPTIONS":
            scope = "mcp" if request.url.path.startswith("/mcp") else "playground"
            await run_in_threadpool(rate_limits.consume_ip, ip, scope)
        response = await call_next(request)
    except DomainError as exc:
        response = JSONResponse(
            exc.payload(), status_code=exc.status, headers={"Retry-After": "60"}
        )
    except SQLAlchemyError:
        observability.report("DATABASE_UNAVAILABLE")
        response = JSONResponse(
            {"error": {"code": "SERVICE_UNAVAILABLE", "message": "Please try again later."}},
            status_code=503,
        )
    except Exception:
        observability.report("REQUEST_FAILED")
        logger.error('{"event":"request_failed","request_id":"%s"}', request_id)
        response = JSONResponse(
            {"error": {"code": "SERVICE_UNAVAILABLE", "message": "Please try again later."}},
            status_code=500,
        )
    if request.url.path.startswith("/assets/") and response.status_code == 200:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif request.url.path == "/healthz" or any(
        request.url.path == prefix or request.url.path.startswith(prefix + "/")
        for prefix in ("/api/me", "/api/ops", "/api/auth")
    ):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    monitoring_origin = (
        " " + parse_browser_sentry_dsn(settings.browser_sentry_dsn)
        if settings.browser_sentry_dsn
        else ""
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        f"img-src 'self' data: https:; connect-src 'self'{monitoring_origin}; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    )
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


@router.get("/.well-known/mcp.json")
def mcp_discovery():
    """Publish MCP Streamable HTTP endpoint and tool metadata for agent crawlers."""
    return {
        "schema_version": "2025-11-25",
        "name": "AgentShelf",
        "description": "WhatsApp-seeded merchant catalog with PayPal Orders v2 checkout.",
        "transport": {
            "type": "streamable-http",
            "endpoint": settings.public_api_url + "/mcp",
        },
        "tools": [
            "search_products",
            "get_quote",
            "create_checkout",
            "get_order_status",
        ],
    }


@router.get("/api/monitoring-config")
def monitoring_config():
    """Expose only the opt-in public browser DSN, never server/provider secrets."""
    return JSONResponse(
        {"dsn": settings.browser_sentry_dsn, "environment": settings.app_env},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/capabilities")
def capabilities():
    """Tell the UI what is actually configured; never expose secret values."""
    return {
        "paypal_mode": settings.paypal_mode,
        "checkout_configured": bool(settings.paypal_client_id and settings.paypal_client_secret),
        "ai_configured": llm.ai_configured(settings),
        "whatsapp_configured": bool(
            settings.whatsapp_access_token and settings.whatsapp_phone_number_id
        ),
        "seller_login_configured": bool(settings.resend_api_key and settings.email_from),
        "live_checkout_enabled": settings.live_checkout_enabled,
        "supported_currencies": ["USD"],
        "shipping_destinations": ["US", "GB"],
    }


@router.get("/api/stores/{slug}")
def store(slug: str, after: uuid.UUID | None = None):
    """Return public store information with no merchant account details."""
    with session_factory() as db:
        seller = db.scalar(
            select(Seller).where(Seller.store_slug == slug, Seller.status == "active")
        )
        if not seller:
            raise DomainError("STORE_NOT_FOUND", "This store is unavailable.", 404)
        items = quotes.search_products(db, limit=10, store_slug=slug, after=after)
        return {
            "name": seller.name,
            "slug": seller.store_slug,
            "country": seller.country,
            "currency": seller.currency,
            "mcp_url": settings.public_api_url + "/mcp",
            "products": items,
            "next_cursor": items[-1]["product_id"] if len(items) == 10 else None,
        }


@router.get("/api/stores/{slug}/schema.json")
def store_schema(slug: str):
    """Return schema.org Product JSON-LD for a public merchant storefront."""
    with session_factory() as db:
        seller = db.scalar(
            select(Seller).where(Seller.store_slug == slug, Seller.status == "active")
        )
        if not seller:
            raise DomainError("STORE_NOT_FOUND", "This store is unavailable.", 404)
        items = quotes.search_products(db, limit=10, store_slug=slug)
        return {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": seller.name,
            "url": f"{settings.frontend_url}/s/{seller.store_slug}",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": idx + 1,
                    "item": {
                        "@type": "Product",
                        "sku": item["product_id"],
                        "name": item["title"],
                        "description": item["description"],
                        "offers": {
                            "@type": "Offer",
                            "price": item["price"],
                            "priceCurrency": item["currency"],
                            "availability": (
                                "https://schema.org/InStock"
                                if item["in_stock"]
                                else "https://schema.org/OutOfStock"
                            ),
                        },
                    },
                }
                for idx, item in enumerate(items)
            ],
        }


@router.get("/api/products")
def products(
    query: str = "",
    limit: int = 5,
    ship_to_country: str | None = None,
    after: uuid.UUID | None = None,
):
    """Expose the same search semantics as the MCP tool."""
    with session_factory() as db:
        items = quotes.search_products(
            db, query=query, limit=limit, ship_to_country=ship_to_country, after=after
        )
        return {
            "products": items,
            "next_cursor": items[-1]["product_id"] if len(items) == limit else None,
        }


@router.get("/api/products/{product_id}/translate")
def translate_product(product_id: uuid.UUID, lang: str = "es"):
    """Translate listing copy while keeping server-side price, currency and stock authoritative."""
    with session_factory() as db:
        row = db.execute(
            select(Product, Seller)
            .join(Seller, Seller.id == Product.seller_id)
            .where(
                Product.id == product_id,
                Product.status == "live",
                Seller.status == "active",
            )
        ).first()
        if not row:
            raise DomainError("PRODUCT_NOT_FOUND", "Product is unavailable.", 404)
        product, seller = row
        translated = llm.translate_listing(product.title, product.description, lang)
        serialized = quotes.product_json(product, seller)
        return {
            **serialized,
            "title": translated["title"],
            "description": translated["description"],
            "language": translated["language"],
            "source_title": product.title,
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
        observability.setup()
        if (
            settings.app_env in {"staging", "production"}
            and not (FRONTEND_DIST / "index.html").is_file()
        ):
            raise RuntimeError("Build frontend assets before starting the deployed web service")
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
    application.add_middleware(GZipMiddleware, minimum_size=512, compresslevel=6)
    application.add_middleware(BodySizeLimitMiddleware)
    application.middleware("http")(request_context)
    application.add_exception_handler(DomainError, domain_error)
    application.add_exception_handler(RequestValidationError, invalid_request)
    application.include_router(router)
    application.include_router(webhooks_router)
    application.include_router(sellers_router)
    application.include_router(analytics_router)
    application.include_router(listings_router)
    application.include_router(playground_router)
    application.include_router(operations_router)
    if (FRONTEND_DIST / "index.html").is_file():

        def frontend_page():
            return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-store"})

        for path in (
            "/",
            "/playground",
            "/dashboard",
            "/onboarding",
            "/operations",
            "/receipt",
            "/s/{slug}",
        ):
            application.add_api_route(path, frontend_page, methods=["GET"], include_in_schema=False)
        application.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    application.mount("/", transport)
    return application


app = create_app()
