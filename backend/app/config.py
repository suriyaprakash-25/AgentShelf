"""Validated runtime configuration, with explicit integration readiness."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "staging", "production"] = "local"
    database_url: str
    public_api_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    paypal_mode: Literal["sandbox", "live"] = "sandbox"
    paypal_client_id: SecretStr | None = None
    paypal_client_secret: SecretStr | None = None
    paypal_webhook_id: str | None = None
    live_checkout_enabled: bool = False
    live_merchant_id: str | None = None
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    whatsapp_app_secret: SecretStr | None = None
    whatsapp_verify_token: SecretStr | None = None
    whatsapp_access_token: SecretStr | None = None
    whatsapp_phone_number_id: str | None = None

    @model_validator(mode="after")
    def validate_environment(self):
        """Reject unsafe or incomplete deployed configurations."""
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        if self.paypal_mode == "live" and (
            not self.live_checkout_enabled or not self.live_merchant_id
        ):
            raise ValueError("Live mode requires explicit enablement and LIVE_MERCHANT_ID")
        if self.app_env in {"staging", "production"}:
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


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process."""
    return Settings()
