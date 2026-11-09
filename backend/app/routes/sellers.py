"""Authenticated web onboarding and seller-owned catalog/order resources.

Handlers authenticate, validate request shapes and delegate to ``auth``,
``seller_catalog``, ``tracking`` and ``copilot``; no business rules live here.
"""

import uuid

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app import auth, copilot, rate_limits, seller_catalog, tracking
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.guards import safe_text
from app.models import SellerSession

router = APIRouter()
PAGE = Query(1, ge=1)
PAGE_SIZE = Query(seller_catalog.DEFAULT_PAGE_SIZE, ge=1, le=seller_catalog.MAX_PAGE_SIZE)


class TrackingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    carrier: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$")
    tracking_number: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


@router.post("/api/me/orders/{order_id}/tracking")
def add_tracking(order_id: uuid.UUID, body: TrackingInput, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    return tracking.track(seller_id, order_id, body.carrier, body.tracking_number)


@router.get("/api/me/orders/{order_id}")
def order_detail(order_id: uuid.UUID, request: Request, response: Response):
    seller_id, _ = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    return seller_catalog.order_detail(seller_id, order_id)


EMAIL_PATTERN = r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$"


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LinkInput(Input):
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)


class OnboardingInput(LinkInput):
    name: str = Field(min_length=2, max_length=100)
    country: str = Field(pattern="^[A-Z]{2}$")
    paypal_email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)
    consent: bool


@router.post("/api/auth/request-link", status_code=202)
def request_link(body: LinkInput, request: Request):
    auth.require_origin(request)
    return auth.request_link(body.email, None, rate_limits.client_ip(request))


@router.post("/api/onboarding", status_code=202)
def onboard(body: OnboardingInput, request: Request):
    auth.require_origin(request)
    if not body.consent:
        raise DomainError("CONSENT_REQUIRED", "Accept the seller terms before creating a store.")
    profile = {
        "name": safe_text(body.name),
        "country": body.country,
        "paypal_email": body.paypal_email.lower(),
    }
    return auth.request_link(body.email, profile, rate_limits.client_ip(request))


class RedeemInput(Input):
    token: str = Field(min_length=20, max_length=128, pattern="^[A-Za-z0-9_-]+$")


@router.post("/api/auth/redeem")
def redeem(body: RedeemInput, request: Request, response: Response):
    auth.require_origin(request)
    token = auth.redeem(body.token)
    response.set_cookie(
        auth.COOKIE,
        token,
        max_age=int(auth.SESSION_TTL.total_seconds()),
        httponly=True,
        secure=get_settings().app_env != "local",
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Signed in."}


@router.get("/api/me")
def me(request: Request, response: Response):
    seller_id, csrf = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    return seller_catalog.seller_profile(seller_id, csrf)


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    auth.seller_access(request, write=True)
    with session_factory() as db, db.begin():
        session = db.get(SellerSession, auth.digest(request.cookies[auth.COOKIE]))
        if session:
            db.delete(session)
    response.delete_cookie(
        auth.COOKIE,
        path="/",
        secure=get_settings().app_env != "local",
        httponly=True,
        samesite="lax",
    )
    return {"message": "Signed out."}


@router.get("/api/me/products")
def products(request: Request, response: Response, page: int = PAGE, page_size: int = PAGE_SIZE):
    seller_id, _ = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    return seller_catalog.list_products(seller_id, page, page_size)


class ProductInput(Input):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(max_length=600)
    price_minor: int = Field(strict=True, ge=1, le=100_000_000)
    stock: int = Field(strict=True, ge=0, le=1_000_000)
    media_id: uuid.UUID | None = None


@router.post("/api/me/products", status_code=201)
def create_product(body: ProductInput, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    return seller_catalog.create_product(
        seller_id, body.title, body.description, body.price_minor, body.stock, body.media_id
    )


class ProductPatch(Input):
    price_minor: int | None = Field(default=None, strict=True, ge=1, le=100_000_000)
    stock: int | None = Field(default=None, strict=True, ge=0, le=1_000_000)
    media_id: uuid.UUID | None = None


@router.patch("/api/me/products/{product_id}")
def update_product(product_id: uuid.UUID, body: ProductPatch, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    return seller_catalog.update_product(seller_id, product_id, body.model_dump(exclude_unset=True))


class ConfirmInput(Input):
    confirm: bool


@router.post("/api/me/products/{product_id}/publish")
def publish(product_id: uuid.UUID, body: ConfirmInput, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    return seller_catalog.publish_product(seller_id, product_id, body.confirm)


@router.post("/api/me/products/{product_id}/archive")
def archive(product_id: uuid.UUID, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    return seller_catalog.archive_product(seller_id, product_id)


@router.post("/api/me/products/{product_id}/paypal-catalog")
def mirror_paypal_catalog(product_id: uuid.UUID, request: Request):
    """Mirror a published seller product to the PayPal Catalog Products API (S-2)."""
    seller_id, _ = auth.seller_access(request, write=True)
    return seller_catalog.mirror_to_paypal(seller_id, product_id)


class RefundInput(Input):
    confirm: bool


@router.get("/api/me/copilot/summary")
def copilot_summary(request: Request, response: Response):
    """Return a 7-day seller transaction summary for the Seller Copilot (S-1)."""
    seller_id, _ = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    with session_factory() as db:
        return copilot.weekly_summary(db, seller_id)


@router.post("/api/me/orders/{order_id}/refund")
def copilot_refund(order_id: uuid.UUID, body: RefundInput, request: Request):
    """Issue a verified PayPal capture refund for a seller-owned order (S-1)."""
    seller_id, _ = auth.seller_access(request, write=True)
    return copilot.issue_refund(seller_id, str(order_id), confirm=body.confirm)


class InvoiceInput(Input):
    recipient_email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)
    amount_minor: int = Field(strict=True, ge=1, le=100_000_000)
    note: str = Field(default="Thank you for your order.", max_length=400)
    confirm: bool


@router.post("/api/me/copilot/invoices")
def copilot_invoice(body: InvoiceInput, request: Request):
    """Create and send a PayPal invoice for the authenticated seller (S-1)."""
    seller_id, _ = auth.seller_access(request, write=True)
    return copilot.send_invoice(
        seller_id, body.recipient_email, body.amount_minor, body.note, confirm=body.confirm
    )


@router.get("/api/me/orders")
def orders(request: Request, response: Response, page: int = PAGE, page_size: int = PAGE_SIZE):
    seller_id, _ = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    return seller_catalog.list_orders(seller_id, page, page_size)
