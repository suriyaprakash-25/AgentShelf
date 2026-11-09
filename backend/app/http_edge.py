"""Request middleware: correlation IDs, edge quotas, error envelopes and browser headers."""

import asyncio
import json
import logging
import time
import uuid

from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app import observability, rate_limits
from app.config import get_settings, parse_browser_sentry_dsn
from app.errors import DomainError

logger = logging.getLogger("agentshelf")

IMMUTABLE_ASSET_CACHE = "public, max-age=31536000, immutable"
NO_STORE_PREFIXES = ("/api/me", "/api/ops", "/api/auth")
HSTS = "max-age=31536000; includeSubDomains"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), usb=()"
UNAVAILABLE = {"error": {"code": "SERVICE_UNAVAILABLE", "message": "Please try again later."}}
# Routes that legitimately wait on PayPal or a model provider get the longer deadline.
PROVIDER_PREFIXES = (
    "/mcp",
    "/checkout/",
    "/api/checkouts",
    "/api/playground/chat",
    "/api/me/",
    "/api/products/",
    "/webhooks/",
)


_ABANDONED: set[asyncio.Task] = set()  # Strong references until drained.


def deadline_for(path, settings):
    """Bound how long any request may wait on a hung dependency before failing fast."""
    if path.startswith(PROVIDER_PREFIXES):
        return settings.provider_request_deadline_seconds
    return settings.request_deadline_seconds


def content_security_policy(settings):
    """Same-origin CSP; inline styles stay allowed for React ``style`` attributes."""
    monitoring_origin = (
        " " + parse_browser_sentry_dsn(settings.browser_sentry_dsn)
        if settings.browser_sentry_dsn
        else ""
    )
    return (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        f"img-src 'self' data: https:; connect-src 'self'{monitoring_origin}; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    )


def security_headers(settings):
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Permissions-Policy": PERMISSIONS_POLICY,
        "Content-Security-Policy": content_security_policy(settings),
    }
    if settings.app_env in rate_limits.PROXIED_ENVIRONMENTS:
        # Deployed origins are HTTPS-only (validated in config), so pin browsers to HTTPS.
        headers["Strict-Transport-Security"] = HSTS
    return headers


def _is_no_store(path):
    return path == "/healthz" or any(
        path == prefix or path.startswith(prefix + "/") for prefix in NO_STORE_PREFIXES
    )


def apply_cache_policy(path, response):
    if path.startswith("/assets/") and response.status_code == 200:
        response.headers["Cache-Control"] = IMMUTABLE_ASSET_CACHE
    elif _is_no_store(path):
        response.headers["Cache-Control"] = "no-store"


def error_response(exc, request_id):
    """Map failures to stable public envelopes; never echo internals."""
    if isinstance(exc, DomainError):
        return JSONResponse(exc.payload(), status_code=exc.status, headers={"Retry-After": "60"})
    if isinstance(exc, TimeoutError):
        observability.report("REQUEST_DEADLINE_EXCEEDED")
        return JSONResponse(UNAVAILABLE, status_code=503, headers={"Retry-After": "5"})
    if isinstance(exc, SQLAlchemyError):
        observability.report("DATABASE_UNAVAILABLE")
        return JSONResponse(UNAVAILABLE, status_code=503, headers={"Retry-After": "5"})
    observability.report("REQUEST_FAILED")
    logger.error('{"event":"request_failed","request_id":"%s"}', request_id)
    return JSONResponse(UNAVAILABLE, status_code=500)


async def _drain(task):
    """Let an abandoned handler finish and consume its body so the ASGI cycle ends."""
    try:
        response = await task
        async for _ in response.body_iterator:
            pass
    except Exception:  # noqa: BLE001 - the client already received a safe 503
        pass


async def within_deadline(call, seconds):
    """Return the downstream response, or raise TimeoutError after ``seconds``.

    Sync handlers run in worker threads that cannot be cancelled, and cancelling the
    awaiting task would block on that thread. Instead the request stops *waiting*: the
    client gets a prompt 503 while the late handler completes in the background. Every
    write path is idempotent, so a client retry cannot duplicate an effect.
    """
    task = asyncio.ensure_future(call)
    done, _ = await asyncio.wait({task}, timeout=seconds)
    if task in done:
        return task.result()
    background = asyncio.ensure_future(_drain(task))
    _ABANDONED.add(background)
    background.add_done_callback(_ABANDONED.discard)
    raise TimeoutError


async def request_context(request, call_next):
    """Attach a request ID, apply edge quotas and add browser security headers."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        abandoned = asyncio.Event()

        async def downstream():
            if rate_limits.is_guarded(request):
                # Quotas hit the database, so they run off the event loop.
                await run_in_threadpool(rate_limits.guard_request, request)
            if abandoned.is_set():
                # The client already got a 503; never start the handler after that.
                raise TimeoutError
            return await call_next(request)

        try:
            response = await within_deadline(
                downstream(), deadline_for(request.url.path, get_settings())
            )
        except TimeoutError:
            abandoned.set()
            raise
    except Exception as exc:  # noqa: BLE001 - every failure becomes a safe envelope
        response = error_response(exc, request_id)
    apply_cache_policy(request.url.path, response)
    response.headers["X-Request-ID"] = request_id
    response.headers.update(security_headers(get_settings()))
    logger.info(
        json.dumps(
            {
                "event": "request",
                "request_id": request_id,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
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
