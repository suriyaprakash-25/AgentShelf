"""Authenticated web onboarding and seller-owned catalog/order resources."""

import uuid

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app import auth, tracking
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.guards import safe_text
from app.models import Order, Product, Quote, Seller, SellerSession

router = APIRouter()


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
    with session_factory() as db:
        order = db.scalar(select(Order).where(Order.id == order_id, Order.seller_id == seller_id))
        if not order:
            raise DomainError("ORDER_NOT_FOUND", "This order is unavailable.", 404)
        quote = db.get(Quote, order.quote_id)
        return {
            "id": str(order.id),
            "title": quote.title,
            "qty": quote.qty,
            "status": order.status,
            "ship_to": order.ship_to,
            "carrier": order.carrier,
            "tracking_number": order.tracking_number,
        }


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


def require_origin(request):
    if request.headers.get("origin") != get_settings().frontend_url:
        raise DomainError("CSRF_REJECTED", "Open AgentShelf to request sign-in.", 403)


@router.post("/api/auth/request-link", status_code=202)
def request_link(body: LinkInput, request: Request):
    require_origin(request)
    return auth.request_link(body.email, None, request.client.host)


@router.post("/api/onboarding", status_code=202)
def onboard(body: OnboardingInput, request: Request):
    require_origin(request)
    if not body.consent:
        raise DomainError("CONSENT_REQUIRED", "Accept the seller terms before creating a store.")
    profile = {
        "name": safe_text(body.name),
        "country": body.country,
        "paypal_email": body.paypal_email.lower(),
    }
    return auth.request_link(body.email, profile, request.client.host)


class RedeemInput(Input):
    token: str = Field(min_length=20, max_length=128, pattern="^[A-Za-z0-9_-]+$")


@router.post("/api/auth/redeem")
def redeem(body: RedeemInput, request: Request, response: Response):
    require_origin(request)
    token = auth.redeem(body.token)
    response.set_cookie(
        auth.COOKIE,
        token,
        max_age=7 * 24 * 3600,
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
    with session_factory() as db:
        seller = db.get(Seller, seller_id)
        return {
            "id": str(seller.id),
            "name": seller.name,
            "country": seller.country,
            "store_slug": seller.store_slug,
            "csrf_token": csrf,
            "live_eligible": seller.live_eligible,
        }


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


def product_json(product):
    return {
        "id": str(product.id),
        "short_no": product.short_no,
        "title": product.title,
        "description": product.description,
        "price_minor": product.price_minor,
        "currency": product.currency,
        "stock": product.stock,
        "status": product.status,
        "images": product.images,
    }


@router.get("/api/me/products")
def products(
    request: Request,
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    seller_id, _ = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    with session_factory() as db:
        condition = Product.seller_id == seller_id
        count = db.scalar(select(func.count()).select_from(Product).where(condition))
        rows = db.scalars(
            select(Product)
            .where(condition)
            .order_by(Product.short_no.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {"items": [product_json(p) for p in rows], "total": count, "page": page}


class ProductInput(Input):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(max_length=600)
    price_minor: int = Field(strict=True, ge=1, le=100_000_000)
    stock: int = Field(strict=True, ge=0, le=1_000_000)


@router.post("/api/me/products", status_code=201)
def create_product(body: ProductInput, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    with session_factory() as db, db.begin():
        db.scalar(select(Seller).where(Seller.id == seller_id).with_for_update())
        number = (
            db.scalar(
                select(func.coalesce(func.max(Product.short_no), 0)).where(
                    Product.seller_id == seller_id
                )
            )
            + 1
        )
        product = Product(
            seller_id=seller_id,
            short_no=number,
            title=safe_text(body.title),
            description=safe_text(body.description),
            price_minor=body.price_minor,
            stock=body.stock,
            status="draft",
        )
        db.add(product)
        db.flush()
        return product_json(product)


class ProductPatch(Input):
    price_minor: int | None = Field(default=None, strict=True, ge=1, le=100_000_000)
    stock: int | None = Field(default=None, strict=True, ge=0, le=1_000_000)


def owned_product(db, product_id, seller_id):
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.seller_id == seller_id)
        .with_for_update()
    )
    if not product:
        raise DomainError("PRODUCT_NOT_FOUND", "This product is unavailable.", 404)
    return product


@router.patch("/api/me/products/{product_id}")
def update_product(product_id: uuid.UUID, body: ProductPatch, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    updates = body.model_dump(exclude_unset=True)
    if not updates or any(value is None for value in updates.values()):
        raise DomainError("INVALID_INPUT", "Set a valid price or available stock quantity.")
    with session_factory() as db, db.begin():
        product = owned_product(db, product_id, seller_id)
        for key, value in updates.items():
            setattr(product, key, value)
        return product_json(product)


class ConfirmInput(Input):
    confirm: bool


@router.post("/api/me/products/{product_id}/publish")
def publish(product_id: uuid.UUID, body: ConfirmInput, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    if not body.confirm:
        raise DomainError("CONFIRMATION_REQUIRED", "Confirm the listing details and price first.")
    with session_factory() as db, db.begin():
        product = owned_product(db, product_id, seller_id)
        if product.status == "archived":
            raise DomainError(
                "PRODUCT_ARCHIVED", "Create a new draft for an archived listing.", 409
            )
        product.status = "live"
        return product_json(product)


@router.post("/api/me/products/{product_id}/archive")
def archive(product_id: uuid.UUID, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    with session_factory() as db, db.begin():
        product = owned_product(db, product_id, seller_id)
        product.status = "archived"
        return product_json(product)


@router.get("/api/me/orders")
def orders(
    request: Request,
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    seller_id, _ = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    with session_factory() as db:
        condition = Order.seller_id == seller_id
        count = db.scalar(select(func.count()).select_from(Order).where(condition))
        rows = db.scalars(
            select(Order)
            .where(condition)
            .order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [
                {
                    "id": str(o.id),
                    "status": o.status,
                    "amount_minor": o.amount_minor,
                    "currency": o.currency,
                    "created_at": o.created_at.isoformat(),
                    "carrier": o.carrier,
                    "tracking_number": o.tracking_number,
                }
                for o in rows
            ],
            "total": count,
            "page": page,
        }
