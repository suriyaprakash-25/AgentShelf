"""Shared database quotas, trusted-proxy client identity and signed internal callers.

Quotas live in Postgres so every web replica and worker enforces the same window.
Each consumption is one atomic ``INSERT ... ON CONFLICT DO UPDATE ... RETURNING``
round trip instead of an insert, a locking read and a later update.
"""

import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.models import RateBucket, utcnow

PROXIED_ENVIRONMENTS = frozenset({"staging", "production"})
PLAYGROUND_HEADER = "x-agentshelf-playground"
PLAYGROUND_TOKEN_TTL_SECONDS = 120


@dataclass(frozen=True)
class RatePolicy:
    """A named quota: ``limit`` uses per ``window_seconds`` for one hashed identity."""

    scope: str
    limit: int
    window_seconds: int
    message: str = "Wait a minute before trying again."


# Roadmap AI-design limits: MCP 60/min per IP; Playground 20 messages/min per session.
MCP_PER_IP = RatePolicy("mcp", 60, 60)
PLAYGROUND_PER_IP = RatePolicy("playground", 60, 60)
# One chat turn makes up to ~28 MCP calls (handshake, tool listing, six model rounds of up
# to four tools); the per-session chat quota (20/min) bounds this budget for each buyer.
PLAYGROUND_MCP_PER_SESSION = RatePolicy("mcp-session", 120, 60)
CHAT_PER_SESSION = RatePolicy("chat", 20, 60, "You can send 20 messages per minute.")
SIGN_IN_LINKS = RatePolicy("signin", 3, 600, "Wait ten minutes before requesting another link.")
STUDIO_ANALYST = RatePolicy("studio_analyst", 20, 60)
MEDIA_UPLOADS = RatePolicy("uploads", 120, 3600)


def hashed_key(prefix, identity):
    """Never store raw IPs, emails or seller identifiers in quota keys."""
    return prefix + ":" + hashlib.sha256(str(identity).encode()).hexdigest()


def consume(db, key, limit, window_seconds, message="Wait a minute before trying again."):
    """Atomically count one use inside the caller's transaction or raise ``RATE_LIMITED``.

    Raising rolls the caller's transaction back, so a rejected request is not counted.
    """
    now = utcnow()
    renewed = now + timedelta(seconds=window_seconds)
    expired = RateBucket.__table__.c.expires_at <= now
    statement = insert(RateBucket).values(key=key, used=1, expires_at=renewed)
    statement = statement.on_conflict_do_update(
        index_elements=[RateBucket.key],
        set_={
            "used": case((expired, 1), else_=RateBucket.__table__.c.used + 1),
            "expires_at": case((expired, renewed), else_=RateBucket.__table__.c.expires_at),
        },
    ).returning(RateBucket.used)
    if db.scalar(statement) > limit:
        raise DomainError("RATE_LIMITED", message, 429)


def enforce(policy, identity, db=None):
    """Apply a policy in its own transaction, or in ``db`` when the caller owns one."""
    key = hashed_key(policy.scope, identity)
    if db is not None:
        return consume(db, key, policy.limit, policy.window_seconds, policy.message)
    with session_factory() as own, own.begin():
        consume(own, key, policy.limit, policy.window_seconds, policy.message)


def trusted_hops(settings):
    if settings.trusted_proxy_hops is not None:
        return settings.trusted_proxy_hops
    return 1 if settings.app_env in PROXIED_ENVIRONMENTS else 0


def client_ip(request):
    """Return the address appended by the nearest trusted proxy.

    Proxies append the peer they saw to ``X-Forwarded-For``; anything left of the
    trusted hops is client-controlled and therefore never used as an identity.
    """
    hops_trusted = trusted_hops(get_settings())
    if hops_trusted:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(hops) >= hops_trusted:
            return hops[-hops_trusted]
    return request.client.host if request.client and request.client.host else "unknown"


@lru_cache
def _signing_key():
    """Prefer an explicit shared key; otherwise derive one from the shared DB secret.

    Every replica already shares DATABASE_URL, so an HMAC-derived, purpose-labelled key
    lets replicas verify each other's Playground calls without exposing the URL itself.
    """
    settings = get_settings()
    if settings.service_signing_key:
        material = settings.service_signing_key.get_secret_value().encode()
    else:
        material = settings.database_url.encode()
    return hmac.new(material, b"agentshelf/playground-mcp/v1", hashlib.sha256).digest()


def _signature(session_id, expires):
    message = f"{session_id}.{expires}".encode()
    digest = hmac.new(_signing_key(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def playground_token(session_id, now=None):
    """Sign a short-lived claim that MCP traffic belongs to one Playground session."""
    expires = int(now if now is not None else time.time()) + PLAYGROUND_TOKEN_TTL_SECONDS
    return f"{session_id}.{expires}.{_signature(session_id, expires)}"


def playground_session(request, now=None):
    """Return the verified Playground session ID behind an MCP request, if any."""
    raw = request.headers.get(PLAYGROUND_HEADER, "")
    parts = raw.split(".")
    if len(parts) != 3 or len(raw) > 200:
        return None
    session_id, expires, signature = parts
    try:
        parsed = uuid.UUID(session_id)
        deadline = int(expires)
    except ValueError:
        return None
    current = int(now if now is not None else time.time())
    if deadline < current or deadline > current + PLAYGROUND_TOKEN_TTL_SECONDS:
        return None
    if not hmac.compare_digest(signature, _signature(session_id, deadline)):
        return None
    return parsed


GUARDED_PREFIXES = ("/mcp", "/api/playground")


def is_guarded(request):
    """Cheap, I/O-free check so unguarded requests skip the threadpool hop."""
    return request.method != "OPTIONS" and request.url.path.startswith(GUARDED_PREFIXES)


def guard_request(request):
    """Apply the edge quota that matches this request path, before routing."""
    path = request.url.path
    if not is_guarded(request):
        return
    if path.startswith("/mcp"):
        session = playground_session(request)
        if session is not None:
            return enforce(PLAYGROUND_MCP_PER_SESSION, session)
        return enforce(MCP_PER_IP, client_ip(request))
    if path.startswith("/api/playground"):
        return enforce(PLAYGROUND_PER_IP, client_ip(request))
