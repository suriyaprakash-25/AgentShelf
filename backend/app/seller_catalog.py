"""Seller-owned catalog and order use cases, independent of HTTP.

Route handlers authenticate, validate shapes and delegate here. Every query is scoped
to the authenticated seller, and every catalog write invalidates cached public reads.
"""

from sqlalchemy import func, select

from app import cache, paypal
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.guards import safe_text
from app.models import MediaAsset, Order, Product, Quote, Seller

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


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


def order_summary(order):
    return {
        "id": str(order.id),
        "status": order.status,
        "amount_minor": order.amount_minor,
        "currency": order.currency,
        "created_at": order.created_at.isoformat(),
        "carrier": order.carrier,
        "tracking_number": order.tracking_number,
    }


def media_url(asset):
    return get_settings().public_api_url + f"/api/media/{asset.id}"


def _paginate(db, model, condition, order_by, page, page_size):
    """Bounded offset page plus total; the composite index serves both queries."""
    total = db.scalar(select(func.count()).select_from(model).where(condition))
    rows = db.scalars(
        select(model)
        .where(condition)
        .order_by(order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


def list_products(seller_id, page=1, page_size=DEFAULT_PAGE_SIZE):
    with session_factory() as db:
        rows, total = _paginate(
            db,
            Product,
            Product.seller_id == seller_id,
            Product.short_no.desc(),
            page,
            page_size,
        )
        return {"items": [product_json(p) for p in rows], "total": total, "page": page}


def list_orders(seller_id, page=1, page_size=DEFAULT_PAGE_SIZE):
    with session_factory() as db:
        rows, total = _paginate(
            db, Order, Order.seller_id == seller_id, Order.created_at.desc(), page, page_size
        )
        return {"items": [order_summary(o) for o in rows], "total": total, "page": page}


def order_detail(seller_id, order_id):
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
            "payment_review": order.reconciliation_error,
        }


def seller_profile(seller_id, csrf_token):
    with session_factory() as db:
        seller = db.get(Seller, seller_id)
        return {
            "id": str(seller.id),
            "name": seller.name,
            "country": seller.country,
            "store_slug": seller.store_slug,
            "csrf_token": csrf_token,
            "live_eligible": seller.live_eligible,
            "is_operator": seller.is_operator,
        }


def unlisted_photo(db, seller_id, media_id):
    """Lock one of the seller's own photos that is not yet attached to a product."""
    asset = db.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.id == media_id,
            MediaAsset.seller_id == seller_id,
            MediaAsset.product_id.is_(None),
        )
        .with_for_update()
    )
    if not asset:
        raise DomainError("MEDIA_NOT_FOUND", "Select an unlisted photo from your account.", 404)
    return asset


def owned_product(db, product_id, seller_id):
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.seller_id == seller_id)
        .with_for_update()
    )
    if not product:
        raise DomainError("PRODUCT_NOT_FOUND", "This product is unavailable.", 404)
    return product


def next_short_no(db, seller_id):
    """Seller-scoped listing number; callers hold the seller row lock to serialize it."""
    current = db.scalar(
        select(func.coalesce(func.max(Product.short_no), 0)).where(Product.seller_id == seller_id)
    )
    return current + 1


def create_product(seller_id, title, description, price_minor, stock, media_id=None):
    """Create a draft; nothing is public until the seller publishes it."""
    with session_factory() as db, db.begin():
        db.scalar(select(Seller).where(Seller.id == seller_id).with_for_update())
        asset = unlisted_photo(db, seller_id, media_id) if media_id else None
        product = Product(
            seller_id=seller_id,
            short_no=next_short_no(db, seller_id),
            title=safe_text(title),
            description=safe_text(description),
            price_minor=price_minor,
            stock=stock,
            status="draft",
            images=[media_url(asset)] if asset else [],
        )
        db.add(product)
        db.flush()
        if asset:
            asset.product_id = product.id
        return product_json(product)


def update_product(seller_id, product_id, updates):
    """Apply a partial price/stock/photo change to a seller-owned product."""
    if not updates or any(value is None for value in updates.values()):
        raise DomainError("INVALID_INPUT", "Set a valid price, stock quantity, or photo.")
    updates = dict(updates)
    with session_factory() as db, db.begin():
        product = owned_product(db, product_id, seller_id)
        media_id = updates.pop("media_id", None)
        if media_id:
            asset = unlisted_photo(db, seller_id, media_id)
            asset.product_id = product.id
            product.images = [media_url(asset)]
        for key, value in updates.items():
            setattr(product, key, value)
        result = product_json(product)
    cache.invalidate_catalog()
    return result


def publish_product(seller_id, product_id, confirm):
    if not confirm:
        raise DomainError("CONFIRMATION_REQUIRED", "Confirm the listing details and price first.")
    with session_factory() as db, db.begin():
        product = owned_product(db, product_id, seller_id)
        if product.status == "archived":
            raise DomainError(
                "PRODUCT_ARCHIVED", "Create a new draft for an archived listing.", 409
            )
        product.status = "live"
        result = product_json(product)
    cache.invalidate_catalog()
    return result


def archive_product(seller_id, product_id):
    with session_factory() as db, db.begin():
        product = owned_product(db, product_id, seller_id)
        product.status = "archived"
        result = product_json(product)
    cache.invalidate_catalog()
    return result


def mirror_to_paypal(seller_id, product_id):
    """Mirror a published seller product to the PayPal Catalog Products API (S-2)."""
    with session_factory() as db:
        product = db.scalar(
            select(Product).where(Product.id == product_id, Product.seller_id == seller_id)
        )
        if not product or product.status != "live":
            raise DomainError("PRODUCT_NOT_FOUND", "Publish this product before mirroring.", 404)
    return paypal.sync_catalog_product(product)
