"""Validated runtime configuration, with explicit integration readiness."""

import re
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    database_url: str
    # Optional streaming replica for anonymous catalog reads; falls back to the primary.
    database_read_url: str | None = None
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_timeout_seconds: int = Field(default=5, ge=1, le=60)
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    # Bounds a hung query and, via tcp_user_timeout, unacknowledged writes to a lost host.
    db_statement_timeout_ms: int = Field(default=15_000, ge=1_000, le=600_000)
    db_network_timeout_ms: int = Field(default=10_000, ge=1_000, le=120_000)
    # Reverse proxies that append X-Forwarded-For. Unset means one in staging/production
    # (the platform load balancer) and none locally, where the header is never trusted.
    trusted_proxy_hops: int | None = Field(default=None, ge=0, le=5)
    # Shared HMAC key for signed internal calls; derived from DATABASE_URL when unset.
    service_signing_key: SecretStr | None = None
    # Client-side deadlines: a hung (not just unreachable) dependency still yields a 503.
    request_deadline_seconds: float = Field(default=15, ge=1, le=120)
    provider_request_deadline_seconds: float = Field(default=75, ge=5, le=300)
    # Seconds to reuse anonymous catalog reads in-process; 0 disables the cache.
    public_cache_seconds: int = Field(default=10, ge=0, le=300)
    public_api_url: str = "http://localhost:8000"
    # The host this API answers on directly. Hosting platforms set it automatically
    # (Hugging Face Spaces: SPACE_HOST; Render: RENDER_EXTERNAL_HOSTNAME). When the
    # browser origin is a proxy in front of it (Vercel rewrites), MCP also accepts this
    # host and server-side MCP calls go straight to it.
    # False when another host (Vercel) serves the browser app and forwards API paths
    # here; the deployed web service then starts without bundled frontend assets.
    serve_frontend: bool = True
    direct_api_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DIRECT_API_HOST", "SPACE_HOST", "RENDER_EXTERNAL_HOSTNAME"),
    )
    frontend_url: str = "http://localhost:5173"
    paypal_mode: Literal["sandbox", "live"] = "sandbox"
    paypal_client_id: SecretStr | None = None
    paypal_client_secret: SecretStr | None = None
    paypal_webhook_id: str | None = None
    live_checkout_enabled: bool = False
    live_merchant_id: str | None = None
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-flash-latest"
    # Gemini 3 reasoning depth. Reasoning tokens count against the output limit, so the
    # provider adds a matching allowance on top of each call's answer budget.
    gemini_thinking_level: Literal["minimal", "low", "medium", "high"] = "low"
    whatsapp_app_secret: SecretStr | None = None
    whatsapp_verify_token: SecretStr | None = None
    whatsapp_access_token: SecretStr | None = None
    whatsapp_phone_number_id: str | None = None
    resend_api_key: SecretStr | None = None
    email_from: str | None = None
    media_backend: Literal["local", "r2"] = "local"
    r2_endpoint: str | None = None
    r2_bucket: str | None = None
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    sentry_dsn: SecretStr | None = None
    browser_sentry_dsn: str | None = Field(default=None, max_length=2048)
    whatsapp_paid_template: str | None = None
    whatsapp_template_language: str = "en_US"

    @field_validator("database_url", "database_read_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, url):
        """Accept the plain scheme hosting providers hand out and select psycopg 3."""
        if isinstance(url, str):
            for prefix in ("postgres://", "postgresql://"):
                if url.startswith(prefix):
                    return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def direct_api_url(self) -> str:
        """Where the server reaches its own API, bypassing any browser-facing proxy."""
        if self.direct_api_host:
            return "https://" + self.direct_api_host
        return self.public_api_url

    @model_validator(mode="after")
    def validate_environment(self):
        """Reject unsafe or incomplete deployed configurations."""
        if self.browser_sentry_dsn:
            parse_browser_sentry_dsn(self.browser_sentry_dsn)
        for url in (self.database_url, self.database_read_url):
            if url is not None and not url.startswith("postgresql+psycopg://"):
                raise ValueError("Database URLs must use postgresql+psycopg://")
        if self.paypal_mode == "live" and (
            not self.live_checkout_enabled or not self.live_merchant_id
        ):
            raise ValueError("Live mode requires explicit enablement and LIVE_MERCHANT_ID")
        if self.app_env in {"staging", "production"}:
            if self.public_api_url.rstrip("/") != self.frontend_url.rstrip("/"):
                raise ValueError("Deployed API and frontend must share the same HTTPS origin")
            if self.media_backend != "r2" or not all(
                [self.r2_endpoint, self.r2_bucket, self.r2_access_key_id, self.r2_secret_access_key]
            ):
                raise ValueError("Deployed media requires a configured private R2 bucket")
            if not self.r2_endpoint.startswith("https://"):
                raise ValueError("R2 endpoint must use HTTPS")
            if not self.public_api_url.startswith("https://") or not self.frontend_url.startswith(
                "https://"
            ):
                raise ValueError("Deployed URLs must use HTTPS")
            required = [self.paypal_client_id, self.paypal_client_secret, self.paypal_webhook_id]
            if not all(required):
                raise ValueError(
                    "Deployed payment service requires PayPal credentials and webhook ID"
                )
        return self


def parse_browser_sentry_dsn(dsn):
    """Validate an intentionally public browser DSN and return its exact HTTPS origin."""
    try:
        parsed = urlsplit(dsn)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname)
            and re.fullmatch(r"[a-fA-F0-9]{32}", parsed.username or "")
            and parsed.password is None
            and parsed.port in (None, 443)
            and re.fullmatch(r"/[0-9]+", parsed.path)
            and not parsed.query
            and not parsed.fragment
        )
        if valid:
            return "https://" + parsed.hostname + (":443" if parsed.port else "")
    except ValueError:
        pass
    raise ValueError("BROWSER_SENTRY_DSN requires a public-key-only HTTPS project DSN")


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process."""
    return Settings()
