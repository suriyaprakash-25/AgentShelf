import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import listing_workflow, media_maintenance, storage
from app.db import session_factory
from app.errors import DomainError
from app.models import ListingRequest, MediaAsset, OpsAudit, Product, Seller, utcnow
from tests.test_listing_workflow import photo
from tests.test_orders import fixture_data

pytestmark = pytest.mark.integration


def test_cleanup_dry_run_protects_references_recent_uploads_and_published_assets(
    db_clean, monkeypatch, tmp_path
):
    monkeypatch.setattr(storage, "ROOT", tmp_path / "images")
    product_id, _, _ = fixture_data()
    ids = [uuid.uuid4() for _ in range(5)]
    with session_factory() as db, db.begin():
        product = db.get(Product, uuid.UUID(product_id))
        seller_id = product.seller_id
        db.get(Seller, seller_id).is_operator = True
        for n, asset_id in enumerate(ids):
            key = f"sandbox/{seller_id}/{asset_id}.jpg"
            storage.put(key, b"processed-fixture")
            old = utcnow() - timedelta(days=10)
            os.utime(storage.local_path(key), (old.timestamp(), old.timestamp()))
            if n != 0:
                db.add(
                    MediaAsset(
                        id=asset_id,
                        seller_id=seller_id,
                        product_id=product.id if n == 2 else None,
                        object_key=key,
                        sha256="a" * 64,
                        created_at=utcnow() if n == 4 else old,
                    )
                )
        db.add(
            ListingRequest(
                seller_id=seller_id, media_ids=[str(ids[3])], status="drafted", caption=""
            )
        )
    preview = media_maintenance.cleanup()
    assert preview["eligible"] == 2 and preview["deleted"] == 0
    result = media_maintenance.cleanup(seller_id, apply=True)
    assert result["deleted"] == 2 and result["retained"] == 3
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(MediaAsset)) == 3
        assert db.scalar(select(func.count()).select_from(OpsAudit)) == 2
    for asset_id in ids[2:]:
        assert storage.local_path(f"sandbox/{seller_id}/{asset_id}.jpg").exists()


def test_stable_upload_id_is_serialized_and_cannot_overwrite_another_seller(
    db_clean, monkeypatch, tmp_path
):
    monkeypatch.setattr(storage, "ROOT", tmp_path / "images")
    product_id, _, _ = fixture_data()
    with session_factory() as db:
        seller_id = db.get(Product, uuid.UUID(product_id)).seller_id
    asset_id = uuid.uuid4()
    raw = photo()
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(
            pool.map(lambda _: listing_workflow.upload(seller_id, raw, asset_id), range(5))
        )
    assert all(result["id"] == str(asset_id) for result in results)
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(MediaAsset)) == 1
    with pytest.raises(Exception, match="unavailable"):
        listing_workflow.upload(uuid.uuid4(), raw, asset_id)


def test_storage_delete_refuses_traversal_and_other_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "ROOT", tmp_path / "images")
    for key in ["../private.env", f"live/{uuid.uuid4()}/{uuid.uuid4()}.jpg"]:
        with pytest.raises(DomainError):
            storage.delete(key)


def test_cleanup_preserves_legacy_product_photo_reference(db_clean, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "ROOT", tmp_path / "images")
    product_id, _, _ = fixture_data()
    asset_id = uuid.uuid4()
    old = utcnow() - timedelta(days=10)
    with session_factory() as db, db.begin():
        product = db.get(Product, uuid.UUID(product_id))
        seller_id = product.seller_id
        db.get(Seller, seller_id).is_operator = True
        key = f"sandbox/{seller_id}/{asset_id}.jpg"
        storage.put(key, b"processed-fixture")
        os.utime(storage.local_path(key), (old.timestamp(), old.timestamp()))
        product.images = [f"/api/media/{asset_id}"]
        db.add(
            MediaAsset(
                id=asset_id, seller_id=seller_id, object_key=key, sha256="a" * 64, created_at=old
            )
        )
    result = media_maintenance.cleanup(seller_id, apply=True)
    assert result["eligible"] == 0 and result["deleted"] == 0 and result["retained"] == 1
    assert storage.local_path(key).exists()
    with session_factory() as db:
        assert db.get(MediaAsset, asset_id)
        assert db.scalar(select(func.count()).select_from(OpsAudit)) == 0
