"""Dry-run-first, bounded cleanup of old unreferenced images in one environment."""

import uuid
from datetime import timedelta

from sqlalchemy import Text, func, select

from app import storage
from app.db import session_factory
from app.errors import DomainError
from app.models import ListingRequest, MediaAsset, OpsAudit, Product, Seller, utcnow


def cleanup(actor_id=None, apply=False, days=7, limit=100, cursor=None):
    if days < 7:
        raise ValueError("Use at least seven days of upload grace.")
    cutoff = utcnow() - timedelta(days=days)
    entries, next_cursor = storage.inventory(limit, cursor)
    result = {
        "scanned": len(entries),
        "eligible": 0,
        "deleted": 0,
        "retained": 0,
        "failed": 0,
        "next_cursor": next_cursor,
    }
    for entry in entries:
        try:
            storage.local_path(entry["key"])
            if entry["modified_at"] > cutoff:
                result["retained"] += 1
                continue
            asset_id = uuid.UUID(entry["key"].rsplit("/", 1)[-1][:-4])
            with session_factory() as db, db.begin():
                if apply:
                    actor = db.get(Seller, actor_id)
                    if not actor or not actor.is_operator or actor.status != "active":
                        raise DomainError("OPERATOR_REQUIRED", "Verified operator required.", 403)
                db.execute(
                    select(func.pg_advisory_xact_lock(func.hashtextextended(str(asset_id), 0)))
                )
                asset = db.scalar(
                    select(MediaAsset).where(MediaAsset.id == asset_id).with_for_update()
                )
                referenced = db.scalar(
                    select(ListingRequest.id)
                    .where(ListingRequest.media_ids.contains([str(asset_id)]))
                    .limit(1)
                )
                product_reference = db.scalar(
                    select(Product.id)
                    .where(Product.images.cast(Text).contains(f"/api/media/{asset_id}"))
                    .limit(1)
                )
                if (
                    referenced
                    or product_reference
                    or (
                        asset
                        and (
                            asset.product_id
                            or asset.created_at > cutoff
                            or asset.object_key != entry["key"]
                        )
                    )
                ):
                    result["retained"] += 1
                    continue
                result["eligible"] += 1
                if apply:
                    storage.delete(entry["key"])
                    if asset:
                        db.delete(asset)
                    db.add(
                        OpsAudit(
                            actor_id=actor_id,
                            action="delete_orphan_media",
                            resource_id=str(asset_id),
                        )
                    )
                    result["deleted"] += 1
        except DomainError as exc:
            if exc.status == 403:
                raise
            result["failed"] += 1
        except (OSError, ValueError):
            result["failed"] += 1
    return result
