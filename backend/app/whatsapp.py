"""WhatsApp boundary: signatures and bounded Cloud API calls."""

import hashlib
import hmac

import httpx

from app.config import get_settings
from app.errors import DomainError


def verify_signature(raw: bytes, signature: str | None):
    """Check Meta's raw-body SHA-256 signature before parsing events."""
    secret = get_settings().whatsapp_app_secret
    if not secret or not signature:
        return False
    expected = (
        "sha256=" + hmac.new(secret.get_secret_value().encode(), raw, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def send_text(phone: str, message: str):
    """Send a text only through configured Meta credentials; never simulate delivery."""
    settings = get_settings()
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        raise DomainError("WHATSAPP_NOT_CONFIGURED", "WhatsApp delivery is not configured.", 503)
    try:
        response = httpx.post(
            f"https://graph.facebook.com/v23.0/{settings.whatsapp_phone_number_id}/messages",
            headers={
                "Authorization": "Bearer " + settings.whatsapp_access_token.get_secret_value()
            },
            json={
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "text",
                "text": {"body": message},
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["messages"][0]["id"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise DomainError(
            "WHATSAPP_UNAVAILABLE", "Message delivery failed. Retry later.", 502
        ) from exc
