"""Private processed-image storage: actual local files or R2's S3 API."""

import re
from contextlib import closing
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.errors import DomainError

ROOT = Path(__file__).resolve().parents[2] / "work" / "media"


def local_path(key):
    if not re.fullmatch(r"(sandbox|live)/[0-9a-f-]{36}/[0-9a-f-]{36}\.jpg", key):
        raise DomainError("INVALID_MEDIA", "Invalid image identifier.")
    return ROOT / key


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


def put(key, content):
    path = local_path(key)  # Validate keys on both backends; callers cannot select URLs.
    try:
        if get_settings().media_backend == "local":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        else:
            with closing(client()) as s3:
                s3.put_object(
                    Bucket=get_settings().r2_bucket, Key=key, Body=content, ContentType="image/jpeg"
                )
    except (OSError, BotoCoreError, ClientError) as exc:
        raise DomainError(
            "STORAGE_UNAVAILABLE", "Image storage is unavailable. Try later.", 503
        ) from exc


def get(key):
    path = local_path(key)
    try:
        if get_settings().media_backend == "local":
            with path.open("rb") as body:
                content = body.read(5 * 1024 * 1024 + 1)
        else:
            with closing(client()) as s3:
                response = s3.get_object(Bucket=get_settings().r2_bucket, Key=key)
                with response["Body"] as body:
                    content = body.read(5 * 1024 * 1024 + 1)
        if len(content) > 5 * 1024 * 1024:
            raise DomainError("INVALID_MEDIA", "The stored image exceeds the allowed size.", 503)
        return content
    except (OSError, BotoCoreError, ClientError) as exc:
        raise DomainError(
            "STORAGE_UNAVAILABLE", "This image is unavailable. Try later.", 503
        ) from exc
