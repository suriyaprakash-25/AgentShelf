"""Treat catalog content as untrusted data and constrain caller-controlled input."""

import re
import uuid

from app.errors import DomainError

INJECTION = re.compile(
    r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions|"
    r"(system|assistant)\s*:\s*|set\s+price\s+to|reveal\s+(your\s+)?(secret|key)",
    re.IGNORECASE,
)


def safe_text(value: str, limit: int = 500):
    """Return bounded text or reject explicit instruction-like payloads."""
    if INJECTION.search(value):
        raise DomainError("UNSAFE_CONTENT", "Remove instructions aimed at the shopping agent.")
    return value[:limit]


def parse_id(value: str):
    """Parse an opaque UUID without surfacing internal parser errors."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise DomainError("INVALID_ID", "Use the identifier returned by the server.") from exc
