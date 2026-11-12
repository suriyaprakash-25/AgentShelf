"""Composition root: wires middleware, routers, the MCP transport and static assets.

No business rules live here. Public handlers are in ``app.routes.public``, edge
middleware in ``app.http_edge``, and domain logic in service modules.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.gzip import GZipMiddleware

from app import auth, observability
from app.body_limits import BodySizeLimitMiddleware
from app.config import get_settings
from app.db import dispose_engines, get_engine  # noqa: F401 - get_engine is a test seam
from app.errors import DomainError
from app.http_edge import domain_error, invalid_request, request_context
from app.mcp_server import create_mcp_server
from app.routes.analytics import router as analytics_router
from app.routes.listings import router as listings_router
from app.routes.operations import router as operations_router
from app.routes.playground import router as playground_router
from app.routes.public import router as public_router
from app.routes.sellers import router as sellers_router
from app.routes.webhooks import router as webhooks_router

logger = logging.getLogger("agentshelf")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("uvicorn.access").disabled = True
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
SPA_ROUTES = (
    "/",
    "/playground",
    "/dashboard",
    "/onboarding",
    "/operations",
    "/receipt",
    "/s/{slug}",
)
ROUTERS = (
    public_router,
    webhooks_router,
    sellers_router,
    analytics_router,
    listings_router,
    playground_router,
    operations_router,
)
GZIP_MIN_BYTES = 512


def mcp_transport(settings):
    """Stateless Streamable HTTP: any worker or replica can serve any MCP request.

    The four tools carry their own session capability, so no per-process MCP session
    state is needed and the endpoint can sit behind a plain round-robin load balancer.
    """
    server = create_mcp_server()
    hosts = {urlsplit(settings.public_api_url).netloc, urlsplit(settings.direct_api_url).netloc}
    app = server.streamable_http_app(
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[*sorted(hosts), "localhost:*", "127.0.0.1:*", "testserver"],
            allowed_origins=[settings.frontend_url, settings.public_api_url],
        ),
    )
    return server, app


def add_frontend(application):
    if not (FRONTEND_DIST / "index.html").is_file():
        return

    def frontend_page():
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-store"})

    for path in SPA_ROUTES:
        application.add_api_route(path, frontend_page, methods=["GET"], include_in_schema=False)
    application.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    if (FRONTEND_DIST / "products").is_dir():
        application.mount(
            "/products", StaticFiles(directory=FRONTEND_DIST / "products"), name="products"
        )


def create_app():
    """Create a fresh API and MCP lifecycle for each server or test instance."""
    settings = get_settings()
    server, transport = mcp_transport(settings)

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
        dispose_engines()

    application = FastAPI(title="AgentShelf", version="0.2.0", lifespan=lifespan)
    allowed_origins = [settings.frontend_url]
    if settings.app_env in {"local", "test"}:
        allowed_origins = list(dict.fromkeys(allowed_origins + sorted(auth.DEV_ORIGINS)))
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
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
    application.add_middleware(GZipMiddleware, minimum_size=GZIP_MIN_BYTES, compresslevel=6)
    application.add_middleware(BodySizeLimitMiddleware)
    application.middleware("http")(request_context)
    application.add_exception_handler(DomainError, domain_error)
    application.add_exception_handler(RequestValidationError, invalid_request)
    for router in ROUTERS:
        application.include_router(router)
    add_frontend(application)
    application.mount("/", transport)
    return application


app = create_app()
