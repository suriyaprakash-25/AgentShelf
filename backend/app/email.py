"""Transactional mail boundary; delivery is never simulated in application code."""

import httpx

from app.config import get_settings
from app.errors import DomainError


def require_ready():
    settings = get_settings()
    if not settings.resend_api_key or not settings.email_from:
        raise DomainError("EMAIL_NOT_CONFIGURED", "Email sign-in is not configured yet.", 503)


def send_login(recipient, link, request_id):
    require_ready()
    settings = get_settings()
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": "Bearer " + settings.resend_api_key.get_secret_value(),
                "Idempotency-Key": request_id,
            },
            json={
                "from": settings.email_from,
                "to": [recipient],
                "subject": "Sign in to AgentShelf",
                "text": f"Open this single-use link within 15 minutes:\n{link}\n"
                "If you did not request it, ignore this email.",
            },
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise DomainError(
            "EMAIL_UNAVAILABLE", "Email delivery is unavailable. Try later.", 503
        ) from exc
