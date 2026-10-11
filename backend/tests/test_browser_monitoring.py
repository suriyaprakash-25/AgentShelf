import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.config import Settings, get_settings

DSN = "https://" + "a" * 32 + "@o999.ingest.sentry.io/999"


def test_browser_monitoring_exposes_only_public_config_and_exact_csp_origin(monkeypatch):
    monkeypatch.setattr(get_settings(), "browser_sentry_dsn", DSN)
    with TestClient(main.create_app()) as client:
        response = client.get("/api/monitoring-config")
        assert response.json() == {"dsn": DSN, "environment": get_settings().app_env}
        assert response.headers["cache-control"] == "no-store"
        csp = response.headers["content-security-policy"]
        assert "connect-src 'self' https://o999.ingest.sentry.io;" in csp
        assert "a" * 32 not in csp and "*.sentry" not in csp


def test_browser_monitoring_missing_configuration_is_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "browser_sentry_dsn", None)
    with TestClient(main.create_app()) as client:
        response = client.get("/api/monitoring-config")
        assert response.json()["dsn"] is None
        assert "connect-src 'self';" in response.headers["content-security-policy"]


@pytest.mark.parametrize(
    "dsn",
    [
        "http://" + "a" * 32 + "@o999.ingest.sentry.io/999",
        "https://" + "a" * 32 + ":private-secret@o999.ingest.sentry.io/999",
        DSN + "?private=query",
        DSN + "#private-fragment",
        "https://" + "a" * 32 + "@o999.ingest.sentry.io:444/999",
        "https://" + "a" * 32 + "@o999.ingest.sentry.io/not-a-project",
    ],
)
def test_browser_dsn_rejects_private_parts_or_unexpected_protocol(dsn):
    with pytest.raises(ValidationError, match="public-key-only") as error:
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test@127.0.0.1/test",
            browser_sentry_dsn=dsn,
        )
    assert "private-secret" not in str(error.value)
