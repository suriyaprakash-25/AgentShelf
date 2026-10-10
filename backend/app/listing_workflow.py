"""Shared web/WhatsApp photo-to-draft workflow with explicit seller publication."""

import hashlib
import re
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app import llm, rate_limits, storage
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.guards import safe_text
from app.listing import preprocess_image, validate_draft
from app.models import Job, ListingRequest, MediaAsset, Product, RateBucket, Seller, utcnow


def caption_text(value):
    if len(value) > 600:
        raise DomainError("INVALID_CAPTION", "Use a caption of 600 characters or fewer.")
    value = safe_text(value, 600)
    if re.search(
        r"[\w.+-]+@[\w.-]+|\b(?:\+?\d[\d ()-]{7,}\d)\b|"
        r"\b(address|postcode|postal code|ship to|api[_ -]?key)\b|"
        r"\b\d+\s+\w+\s+(street|road|avenue|lane|drive)\b",
        value,
        re.I,
    ):
        raise DomainError(
            "PERSONAL_CAPTION", "Remove contact, address and secret details from the caption."
        )
    return value


def upload(seller_id, raw, asset_id=None):
    clean = preprocess_image(raw)
    asset_id = asset_id or uuid.uuid4()
    with session_factory() as db:
        existing = db.get(MediaAsset, asset_id)
        if existing and existing.seller_id == seller_id:
            return {
                "id": str(existing.id),
                "url": get_settings().public_api_url + f"/api/media/{existing.id}",
            }
    rate_limits.consume_ip(str(seller_id), "uploads", 120, 3600)
    key = f"{get_settings().paypal_mode}/{seller_id}/{asset_id}.jpg"
    storage.put(key, clean)
    with session_factory() as db, db.begin():
        db.add(
            MediaAsset(
                id=asset_id,
                seller_id=seller_id,
                object_key=key,
                sha256=hashlib.sha256(clean).hexdigest(),
            )
        )
    return {"id": str(asset_id), "url": get_settings().public_api_url + f"/api/media/{asset_id}"}


def create(seller_id, media_ids, caption, request_id=None, phone=None):
    caption = caption_text(caption)
    if not 1 <= len(media_ids) <= 4 or len(set(media_ids)) != len(media_ids):
        raise DomainError("INVALID_MEDIA", "Select one to four different product images.")
    if not get_settings().anthropic_api_key:
        raise DomainError(
            "AI_NOT_CONFIGURED", "AI is not configured. Create a manual draft instead.", 503
        )
    with session_factory() as db, db.begin():
        existing = db.get(ListingRequest, request_id) if request_id else None
        if existing and existing.seller_id == seller_id:
            return {"id": str(existing.id), "status": existing.status}
        key = f"listings:{seller_id}"
        now = utcnow()
        db.execute(
            insert(RateBucket)
            .values(key=key, used=0, expires_at=now + timedelta(hours=1))
            .on_conflict_do_nothing()
        )
        bucket = db.scalar(select(RateBucket).where(RateBucket.key == key).with_for_update())
        if bucket.expires_at <= now:
            bucket.used, bucket.expires_at = 0, now + timedelta(hours=1)
        if bucket.used >= 30:
            raise DomainError("RATE_LIMITED", "You can request 30 listing drafts per hour.", 429)
        assets = list(
            db.scalars(
                select(MediaAsset).where(
                    MediaAsset.id.in_(media_ids),
                    MediaAsset.seller_id == seller_id,
                    MediaAsset.product_id.is_(None),
                )
            )
        )
        if len(assets) != len(media_ids):
            raise DomainError(
                "MEDIA_NOT_FOUND", "Select unlisted images from your own account.", 404
            )
        bucket.used += 1
        request = ListingRequest(
            **({"id": request_id} if request_id else {}),
            seller_id=seller_id,
            media_ids=[str(i) for i in media_ids],
            caption=caption,
        )
        db.add(request)
        db.flush()
        db.add(
            Job(
                kind="listing_draft",
                dedupe_key=f"listing:{request.id}",
                payload={
                    "listing_id": str(request.id),
                    **({"whatsapp_phone": phone} if phone else {}),
                },
                **({"run_after": utcnow() + timedelta(seconds=2)} if phone else {}),
            )
        )
        return {"id": str(request.id), "status": "queued"}


def process(db, job):
    listing = db.scalar(
        select(ListingRequest)
        .where(ListingRequest.id == uuid.UUID(job.payload["listing_id"]))
        .with_for_update()
    )
    if not listing or listing.status != "queued":
        return
    assets = [db.get(MediaAsset, uuid.UUID(i)) for i in listing.media_ids]
    if any(not asset or asset.seller_id != listing.seller_id for asset in assets):
        raise DomainError("MEDIA_NOT_FOUND", "Listing images are unavailable.", 404)
    images = [storage.get(a.object_key) for a in assets]
    if any(
        hashlib.sha256(content).hexdigest() != asset.sha256
        for asset, content in zip(assets, images, strict=True)
    ):
        raise DomainError("MEDIA_CORRUPT", "The stored photo changed. Upload it again.", 409)
    try:
        draft = llm.draft_listing(images, caption_text(listing.caption))
    except DomainError as exc:
        if exc.code in {"AI_INVALID_DRAFT", "UNSAFE_CONTENT", "PERSONAL_CAPTION"}:
            listing.status = "failed"
            if job.payload.get("whatsapp_phone"):
                db.add(
                    Job(
                        kind="whatsapp_draft_reply",
                        dedupe_key=f"draft-reply:{listing.id}",
                        payload={
                            "phone": job.payload["whatsapp_phone"],
                            "listing_id": str(listing.id),
                        },
                    )
                )
            return
        raise
    listing.draft, listing.status = draft.model_dump(), "drafted"
    if job.payload.get("whatsapp_phone"):
        db.add(
            Job(
                kind="whatsapp_draft_reply",
                dedupe_key=f"draft-reply:{listing.id}",
                payload={"phone": job.payload["whatsapp_phone"], "listing_id": str(listing.id)},
            )
        )


def publish(seller_id, listing_id, title, description, price_minor, stock):
    if (
        type(price_minor) is not int
        or not 1 <= price_minor <= 100_000_000
        or type(stock) is not int
        or not 0 <= stock <= 1_000_000
        or not title.strip()
        or not description.strip()
    ):
        raise DomainError("INVALID_LISTING", "Set a valid title, description, price and stock.")
    with session_factory() as db, db.begin():
        seller = db.scalar(select(Seller).where(Seller.id == seller_id).with_for_update())
        if not seller or seller.status != "active":
            raise DomainError("SELLER_UNAVAILABLE", "This seller is unavailable.", 403)
        listing = db.scalar(
            select(ListingRequest)
            .where(ListingRequest.id == listing_id, ListingRequest.seller_id == seller_id)
            .with_for_update()
        )
        if not listing:
            raise DomainError("LISTING_NOT_FOUND", "This listing is unavailable.", 404)
        if listing.status == "published":
            return {
                "product_id": str(listing.product_id),
                "status": db.get(Product, listing.product_id).status,
            }
        if listing.status != "drafted":
            raise DomainError(
                "DRAFT_REQUIRED", "Wait for a valid draft or create one manually.", 409
            )
        draft = validate_draft(listing.draft)
        assets = list(
            db.scalars(
                select(MediaAsset)
                .where(MediaAsset.id.in_([uuid.UUID(i) for i in listing.media_ids]))
                .with_for_update()
            )
        )
        if len(assets) != len(listing.media_ids) or any(
            a.seller_id != seller_id or a.product_id for a in assets
        ):
            raise DomainError(
                "MEDIA_IN_USE", "One of these photos is already attached to a listing.", 409
            )
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
            title=safe_text(title, 80),
            description=safe_text(description, 600),
            price_minor=price_minor,
            stock=stock,
            status="live",
            attributes={**draft.attributes.model_dump(), "category": draft.category},
            images=[get_settings().public_api_url + f"/api/media/{a.id}" for a in assets],
        )
        db.add(product)
        db.flush()
        for asset in assets:
            asset.product_id = product.id
        listing.product_id, listing.status = product.id, "published"
        return {"product_id": str(product.id), "status": "live"}
