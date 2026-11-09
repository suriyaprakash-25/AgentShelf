"""Private processed-image storage behind one interface: local files or R2's S3 API.

``MediaStore`` is the Strategy; ``media_store()`` picks the configured backend at call
time. The module-level ``put``/``get``/``inventory``/``delete`` functions are the stable
facade used by workflows, so a new backend never changes a caller (Open/Closed).
Key validation happens once in the facade for every backend.
"""

import re
from contextlib import closing
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.errors import DomainError

ROOT = Path(__file__).resolve().parents[2] / "work" / "media"
MAX_OBJECT_BYTES = 5 * 1024 * 1024
MAX_INVENTORY_PAGE = 1000
KEY_PATTERN = re.compile(r"(sandbox|live)/[0-9a-f-]{36}/[0-9a-f-]{36}\.jpg")
STORAGE_ERRORS = (OSError, BotoCoreError, ClientError)


class MediaStore(Protocol):
    def put(self, key: str, content: bytes) -> None: ...

    def read(self, key: str, limit: int) -> bytes: ...

    def list_page(self, prefix: str, limit: int, cursor: str | None) -> tuple[list, str | None]: ...

    def remove(self, key: str) -> None: ...


def local_path(key):
    if not KEY_PATTERN.fullmatch(key):
        raise DomainError("INVALID_MEDIA", "Invalid image identifier.")
    root, target = ROOT.resolve(), (ROOT / key).resolve()
    if ROOT.is_symlink() or not target.is_relative_to(root):
        raise DomainError("INVALID_MEDIA", "Image path is outside private storage.")
    return target


def client():
    settings = get_settings()
    if not all(
        [
            settings.r2_endpoint,
            settings.r2_bucket,
            settings.r2_access_key_id,
            settings.r2_secret_access_key,
        ]
    ):
        raise DomainError("STORAGE_NOT_CONFIGURED", "Image storage is not configured.", 503)
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        region_name="auto",
        aws_access_key_id=settings.r2_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.r2_secret_access_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=10,
            retries={"total_max_attempts": 1},
        ),
    )


class LocalMediaStore:
    """Development backend; ``ROOT`` is resolved per call so tests can redirect it."""

    def put(self, key, content):
        path = local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def read(self, key, limit):
        with local_path(key).open("rb") as body:
            return body.read(limit)

    def list_page(self, prefix, limit, cursor):
        if cursor:
            raise ValueError("Local inventory has no continuation token.")
        entries = []
        for path in islice((ROOT / prefix).glob("*/*.jpg"), limit):
            key = path.relative_to(ROOT).as_posix()
            actual = local_path(key)
            entries.append(
                {"key": key, "modified_at": datetime.fromtimestamp(actual.stat().st_mtime, UTC)}
            )
        return entries, None

    def remove(self, key):
        local_path(key).unlink(missing_ok=True)


class R2MediaStore:
    """Deployed backend: a private bucket reached through the S3-compatible API."""

    def put(self, key, content):
        with closing(client()) as s3:
            s3.put_object(
                Bucket=get_settings().r2_bucket, Key=key, Body=content, ContentType="image/jpeg"
            )

    def read(self, key, limit):
        with closing(client()) as s3:
            response = s3.get_object(Bucket=get_settings().r2_bucket, Key=key)
            with response["Body"] as body:
                return body.read(limit)

    def list_page(self, prefix, limit, cursor):
        with closing(client()) as s3:
            response = s3.list_objects_v2(
                Bucket=get_settings().r2_bucket,
                Prefix=prefix + "/",
                MaxKeys=limit,
                **({"ContinuationToken": cursor} if cursor else {}),
            )
        entries = [
            {"key": item["Key"], "modified_at": item["LastModified"]}
            for item in response.get("Contents", [])
        ]
        return entries, response.get("NextContinuationToken")

    def remove(self, key):
        with closing(client()) as s3:
            s3.delete_object(Bucket=get_settings().r2_bucket, Key=key)


BACKENDS = {"local": LocalMediaStore, "r2": R2MediaStore}


def media_store() -> MediaStore:
    """Factory for the configured backend."""
    return BACKENDS[get_settings().media_backend]()


def put(key, content):
    local_path(key)  # Validate keys on both backends; callers cannot select URLs.
    try:
        media_store().put(key, content)
    except STORAGE_ERRORS as exc:
        raise DomainError(
            "STORAGE_UNAVAILABLE", "Image storage is unavailable. Try later.", 503
        ) from exc


def get(key):
    local_path(key)
    try:
        content = media_store().read(key, MAX_OBJECT_BYTES + 1)
    except STORAGE_ERRORS as exc:
        raise DomainError(
            "STORAGE_UNAVAILABLE", "This image is unavailable. Try later.", 503
        ) from exc
    if len(content) > MAX_OBJECT_BYTES:
        raise DomainError("INVALID_MEDIA", "The stored image exceeds the allowed size.", 503)
    return content


def inventory(limit=100, cursor=None):
    """One bounded mode-specific page; never enumerate another deployment's namespace."""
    limit = min(max(limit, 1), MAX_INVENTORY_PAGE)
    store = media_store()
    try:
        return store.list_page(get_settings().paypal_mode, limit, cursor)
    except (BotoCoreError, ClientError) as exc:
        raise DomainError("STORAGE_UNAVAILABLE", "Image inventory is unavailable.", 503) from exc


def delete(key):
    """Delete exactly one validated object; retries of a missing object are safe."""
    local_path(key)
    if not key.startswith(get_settings().paypal_mode + "/"):
        raise DomainError("INVALID_MEDIA", "Image belongs to another payment environment.")
    try:
        media_store().remove(key)
    except STORAGE_ERRORS as exc:
        raise DomainError("STORAGE_UNAVAILABLE", "Image cleanup is unavailable.", 503) from exc
