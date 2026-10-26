"""WhatsApp boundary: signatures and bounded Cloud API calls."""

import hashlib
import hmac
import re
from urllib.parse import urlsplit

import httpx

from app.config import get_settings
from app.errors import DomainError


def download_media(media_id, allowed_mimes, invalid_message):
    settings = get_settings()
    if not settings.whatsapp_access_token:
        raise DomainError("WHATSAPP_NOT_CONFIGURED", "WhatsApp media is not configured.", 503)
    if not isinstance(media_id, str) or not re.fullmatch(r"\d{1,80}", media_id):
        raise DomainError("INVALID_MEDIA", "Invalid WhatsApp media identifier.")
    headers = {"Authorization": "Bearer " + settings.whatsapp_access_token.get_secret_value()}
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            response = client.get(f"https://graph.facebook.com/v23.0/{media_id}", headers=headers)
            response.raise_for_status()
            metadata = response.json()
            url = urlsplit(metadata["url"])
            if (
                url.scheme != "https"
                or url.hostname != "lookaside.fbsbx.com"
                or url.port not in {None, 443}
                or url.username
                or url.password
            ):
                raise DomainError("INVALID_MEDIA", "The media download host is unsupported.")
            if (
                metadata.get("mime_type") not in allowed_mimes
                or not 0 < int(metadata.get("file_size", 0)) <= 5 * 1024 * 1024
            ):
                raise DomainError("INVALID_IMAGE", invalid_message)
            with client.stream("GET", metadata["url"], headers=headers) as download:
                download.raise_for_status()
                raw = bytearray()
                for chunk in download.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 5 * 1024 * 1024:
                        raise DomainError("INVALID_IMAGE", "The media file exceeds 5 MB.")
                return bytes(raw)
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise DomainError(
            "WHATSAPP_MEDIA_UNAVAILABLE",
            "Media download failed. Send it again or use the dashboard.",
            502,
        ) from exc


def download_audio(media_id):
    return download_media(
        media_id,
        {"audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "audio/aac"},
        "Use an OGG, MP3, MP4, WAV or AAC voice note up to 5 MB.",
    )


def download_image(media_id):
    settings = get_settings()
    if not settings.whatsapp_access_token:
        raise DomainError("WHATSAPP_NOT_CONFIGURED", "WhatsApp media is not configured.", 503)
    if not isinstance(media_id, str) or not re.fullmatch(r"\d{1,80}", media_id):
        raise DomainError("INVALID_MEDIA", "Invalid WhatsApp media identifier.")
    headers = {"Authorization": "Bearer " + settings.whatsapp_access_token.get_secret_value()}
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            response = client.get(f"https://graph.facebook.com/v23.0/{media_id}", headers=headers)
            response.raise_for_status()
            metadata = response.json()
            url = urlsplit(metadata["url"])
            if (
                url.scheme != "https"
                or url.hostname != "lookaside.fbsbx.com"
                or url.port not in {None, 443}
                or url.username
                or url.password
            ):
                raise DomainError("INVALID_MEDIA", "The media download host is unsupported.")
            if (
                metadata.get("mime_type") not in {"image/jpeg", "image/png", "image/webp"}
                or not 0 < int(metadata.get("file_size", 0)) <= 5 * 1024 * 1024
            ):
                raise DomainError("INVALID_IMAGE", "Use a JPEG, PNG or WebP photo up to 5 MB.")
            with client.stream("GET", metadata["url"], headers=headers) as download:
                download.raise_for_status()
                raw = bytearray()
                for chunk in download.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 5 * 1024 * 1024:
                        raise DomainError("INVALID_IMAGE", "The image exceeds 5 MB.")
                return bytes(raw)
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise DomainError(
            "WHATSAPP_MEDIA_UNAVAILABLE",
            "Photo download failed. Send it again or use the dashboard.",
            502,
        ) from exc


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
    return send(phone, {"type": "text", "text": {"body": message}})


def send_paid(phone, order_number, item, amount, address):
    settings = get_settings()
    if settings.whatsapp_paid_template:
        return send(
            phone,
            {
                "type": "template",
                "template": {
                    "name": settings.whatsapp_paid_template,
                    "language": {"code": settings.whatsapp_template_language},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": str(value)}
                                for value in (order_number, item, amount, address)
                            ],
                        }
                    ],
                },
            },
        )
    return send_text(
        phone,
        f"Paid order #{order_number}: {item}. {amount}. Ship to: {address}. "
        "Add tracking in the dashboard.",
    )


def send(phone, content):
    """Send only through configured Meta credentials; never simulate delivery."""
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
                **content,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["messages"][0]["id"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise DomainError(
            "WHATSAPP_UNAVAILABLE", "Message delivery failed. Retry later.", 502
        ) from exc
