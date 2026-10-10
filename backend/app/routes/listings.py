"""Private uploads and asynchronous drafts, with seller-controlled publication."""

import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app import auth, listing_workflow, storage
from app.db import session_factory
from app.errors import DomainError
from app.models import Job, ListingRequest, MediaAsset, Product, Seller

router = APIRouter()


@router.post("/api/me/media", status_code=201)
async def upload(request: Request):
    seller_id, _ = await run_in_threadpool(auth.seller_access, request, True)
    # Stream raw bytes so the bound applies before decoding or disk spooling.
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 5 * 1024 * 1024:
            raise DomainError("INVALID_IMAGE", "Use a product photo no larger than 5 MB.", 413)
    return await run_in_threadpool(listing_workflow.upload, seller_id, raw)


@router.get("/api/media/{asset_id}")
def media(asset_id: uuid.UUID, request: Request):
    with session_factory() as db:
        asset = db.get(MediaAsset, asset_id)
        if not asset:
            raise DomainError("MEDIA_NOT_FOUND", "This image is unavailable.", 404)
        product = db.get(Product, asset.product_id) if asset.product_id else None
        seller = db.get(Seller, asset.seller_id)
        public = bool(product and product.status == "live" and seller.status == "active")
        if not public:
            seller_id, _ = auth.seller_access(request)
            if seller_id != asset.seller_id:
                raise DomainError("MEDIA_NOT_FOUND", "This image is unavailable.", 404)
        etag = '"' + asset.sha256 + '"'
        headers = {
            "Cache-Control": "public, max-age=86400" if public else "private, no-store",
            "ETag": etag,
            "X-Content-Type-Options": "nosniff",
        }
        if public and request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(storage.get(asset.object_key), media_type="image/jpeg", headers=headers)


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    media_ids: list[uuid.UUID] = Field(min_length=1, max_length=4)
    caption: str = Field(default="", max_length=600)


@router.post("/api/me/listings", status_code=202)
def create(body: DraftInput, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    return listing_workflow.create(seller_id, body.media_ids, body.caption)


@router.get("/api/me/listings")
def list_drafts(request: Request, response: Response):
    seller_id, _ = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    with session_factory() as db:
        rows = db.scalars(
            select(ListingRequest)
            .where(ListingRequest.seller_id == seller_id)
            .order_by(ListingRequest.created_at.desc())
            .limit(30)
        )
        return {"items": [{"id": str(r.id), "status": r.status} for r in rows]}


@router.get("/api/me/listings/{listing_id}")
def get_draft(listing_id: uuid.UUID, request: Request, response: Response):
    seller_id, _ = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    with session_factory() as db:
        listing = db.scalar(
            select(ListingRequest).where(
                ListingRequest.id == listing_id, ListingRequest.seller_id == seller_id
            )
        )
        if not listing:
            raise DomainError("LISTING_NOT_FOUND", "This listing is unavailable.", 404)
        job = db.scalar(select(Job).where(Job.dedupe_key == f"listing:{listing.id}"))
        return {
            "id": str(listing.id),
            "status": "failed" if job and job.status == "failed" else listing.status,
            "draft": listing.draft,
            "product_id": str(listing.product_id) if listing.product_id else None,
            "error_code": job.last_error if job else None,
            "media_urls": [f"/api/media/{i}" for i in listing.media_ids],
        }


class PublicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=600)
    price_minor: int = Field(strict=True, ge=1, le=100_000_000)
    stock: int = Field(strict=True, ge=0, le=1_000_000)


@router.post("/api/me/listings/{listing_id}/publish")
def publish(listing_id: uuid.UUID, body: PublicationInput, request: Request):
    seller_id, _ = auth.seller_access(request, write=True)
    if not body.confirm:
        raise DomainError(
            "CONFIRMATION_REQUIRED", "Review the listing and selling price, then confirm."
        )
    return listing_workflow.publish(
        seller_id, listing_id, body.title, body.description, body.price_minor, body.stock
    )
