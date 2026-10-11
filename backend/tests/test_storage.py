import io
import uuid

import pytest
from botocore.stub import Stubber
from pydantic import SecretStr, ValidationError

from app import storage
from app.config import Settings, get_settings
from app.errors import DomainError


def test_r2_signed_private_put_get_and_bounded_read(monkeypatch):
    settings = get_settings()
    for name, value in {
        "media_backend": "r2",
        "r2_endpoint": "https://example.r2.cloudflarestorage.com",
        "r2_bucket": "private-test",
        "r2_access_key_id": SecretStr("test-access"),
        "r2_secret_access_key": SecretStr("test-secret"),
    }.items():
        monkeypatch.setattr(settings, name, value)
    s3 = storage.client()
    assert s3.meta.config.signature_version == "s3v4"
    monkeypatch.setattr(storage, "client", lambda: s3)
    key = f"sandbox/{uuid.uuid4()}/{uuid.uuid4()}.jpg"
    with Stubber(s3) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "private-test",
                "Key": key,
                "Body": b"processed-photo",
                "ContentType": "image/jpeg",
            },
        )
        stub.add_response(
            "get_object",
            {"Body": io.BytesIO(b"processed-photo")},
            {"Bucket": "private-test", "Key": key},
        )
        storage.put(key, b"processed-photo")
        assert storage.get(key) == b"processed-photo"
        stub.assert_no_pending_responses()
    with pytest.raises(DomainError):
        storage.get("../../outside.jpg")


def test_deployed_storage_cannot_silently_use_ephemeral_local_files():
    with pytest.raises(ValidationError, match="private R2 bucket"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://fixture@localhost/db",
            app_env="staging",
            public_api_url="https://app.example.invalid",
            frontend_url="https://app.example.invalid",
        )


def test_paypal_approval_url_cannot_leave_expected_environment(monkeypatch):
    from app import paypal

    monkeypatch.setattr(get_settings(), "paypal_mode", "sandbox")
    for href in [
        "https://evil.invalid/checkout",
        "https://www.paypal.com/checkout",
        "https://www.sandbox.paypal.com@evil.invalid/checkout",
        "http://www.sandbox.paypal.com/checkout",
        "https://www.sandbox.paypal.com:444/checkout",
    ]:
        with pytest.raises(DomainError, match="verified"):
            paypal.approval_link({"links": [{"rel": "approve", "href": href}]})
    assert paypal.approval_link(
        {
            "links": [
                {
                    "rel": "approve",
                    "href": "https://www.sandbox.paypal.com/checkoutnow?token=fixture",
                }
            ]
        }
    ).startswith("https://www.sandbox.paypal.com/")


def test_r2_inventory_cursor_and_exact_environment_object_deletion(monkeypatch):
    from datetime import UTC, datetime

    settings = get_settings()
    for name, value in {
        "media_backend": "r2",
        "r2_endpoint": "https://example.r2.cloudflarestorage.com",
        "r2_bucket": "private-test",
        "r2_access_key_id": SecretStr("test-access"),
        "r2_secret_access_key": SecretStr("test-secret"),
    }.items():
        monkeypatch.setattr(settings, name, value)
    s3 = storage.client()
    monkeypatch.setattr(storage, "client", lambda: s3)
    key = f"sandbox/{uuid.uuid4()}/{uuid.uuid4()}.jpg"
    modified = datetime.now(UTC)
    with Stubber(s3) as stub:
        stub.add_response(
            "list_objects_v2",
            {
                "Contents": [{"Key": key, "LastModified": modified}],
                "NextContinuationToken": "next-page",
            },
            {
                "Bucket": "private-test",
                "Prefix": "sandbox/",
                "MaxKeys": 10,
                "ContinuationToken": "previous-page",
            },
        )
        stub.add_response("delete_object", {}, {"Bucket": "private-test", "Key": key})
        entries, cursor = storage.inventory(10, "previous-page")
        assert entries == [{"key": key, "modified_at": modified}]
        assert cursor == "next-page"
        storage.delete(key)
        stub.assert_no_pending_responses()


def test_r2_maintenance_provider_errors_are_generic(monkeypatch):
    settings = get_settings()
    for name, value in {
        "media_backend": "r2",
        "r2_endpoint": "https://example.r2.cloudflarestorage.com",
        "r2_bucket": "private-test",
        "r2_access_key_id": SecretStr("test-access"),
        "r2_secret_access_key": SecretStr("test-secret"),
    }.items():
        monkeypatch.setattr(settings, name, value)
    s3 = storage.client()
    monkeypatch.setattr(storage, "client", lambda: s3)
    key = f"sandbox/{uuid.uuid4()}/{uuid.uuid4()}.jpg"
    with Stubber(s3) as stub:
        stub.add_client_error(
            "list_objects_v2",
            service_error_code="AccessDenied",
            service_message="private-provider-details",
        )
        stub.add_client_error(
            "delete_object",
            service_error_code="AccessDenied",
            service_message="private-provider-details",
        )
        for action in [lambda: storage.inventory(), lambda: storage.delete(key)]:
            with pytest.raises(DomainError) as error:
                action()
            assert error.value.status == 503 and "private-provider-details" not in str(error.value)
        stub.assert_no_pending_responses()
