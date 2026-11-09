"""Single-use email capabilities, hashed sessions, ownership and CSRF enforcement."""

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select

from app import email, rate_limits
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.models import LoginChallenge, RateBucket, Seller, SellerSession, utcnow

COOKIE = "agentshelf_seller"
LINK_TTL = timedelta(minutes=15)
SESSION_TTL = timedelta(days=7)
DEFAULT_SHIPPING_MINOR = {"US": 800, "GB": 1000}
DEV_ORIGINS = frozenset({"http://localhost:5173", "http://127.0.0.1:5173"})


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def consume_quota(db, key, limit=rate_limits.SIGN_IN_LINKS.limit):
    """Count one sign-in link against an already-hashed email or IP key."""
    policy = rate_limits.SIGN_IN_LINKS
    rate_limits.consume(db, key, limit, policy.window_seconds, policy.message)


def request_link(address, profile, ip):
    email.require_ready()
    address = address.lower()
    token = secrets.token_urlsafe(32)
    with session_factory() as db, db.begin():
        # Hash identity keys, use a common lock order, and persist limits across processes.
        for key in sorted(["email:" + digest(address), "ip:" + digest(ip)]):
            consume_quota(db, key)
        db.add(
            LoginChallenge(
                token_hash=digest(token),
                email=address,
                profile=profile,
                expires_at=utcnow() + LINK_TTL,
            )
        )
    # URL fragments are not included in HTTP requests or ordinary access logs.
    link = get_settings().frontend_url.rstrip("/") + "/dashboard#sign-in=" + token
    email.send_login(address, link, "login-" + uuid.uuid4().hex)
    return {"message": "Check your email for a single-use sign-in link."}


def redeem(token):
    session_token = secrets.token_urlsafe(32)
    with session_factory() as db, db.begin():
        challenge = db.scalar(
            select(LoginChallenge)
            .where(LoginChallenge.token_hash == digest(token))
            .with_for_update()
        )
        if not challenge or challenge.consumed_at or challenge.expires_at <= utcnow():
            raise DomainError(
                "LINK_INVALID", "This link expired or was used. Request another.", 401
            )
        # Serialize different valid onboarding links for the same verified email.
        db.execute(
            select(RateBucket)
            .where(RateBucket.key == "email:" + digest(challenge.email))
            .with_for_update()
        )
        seller = db.scalar(select(Seller).where(Seller.email == challenge.email))
        if not seller:
            if not challenge.profile:
                raise DomainError(
                    "ONBOARDING_REQUIRED", "Create your store before signing in.", 409
                )
            seller = Seller(
                **challenge.profile,
                email=challenge.email,
                store_slug="store-" + uuid.uuid4().hex[:12],
                status="active",
                consent_at=utcnow(),
                shipping_rates=dict(DEFAULT_SHIPPING_MINOR),
            )
            db.add(seller)
            db.flush()
        if seller.status != "active":
            raise DomainError("SELLER_UNAVAILABLE", "This seller account is unavailable.", 403)
        phone = (challenge.profile or {}).get("whatsapp_phone")
        if phone:
            # A Meta sender can claim an email, but cannot bind it until email verification.
            if seller.whatsapp_phone and seller.whatsapp_phone != phone:
                raise DomainError(
                    "PHONE_ALREADY_BOUND", "Manage the existing phone from your dashboard.", 409
                )
            other = db.scalar(
                select(Seller).where(Seller.whatsapp_phone == phone, Seller.id != seller.id)
            )
            if other:
                raise DomainError(
                    "PHONE_ALREADY_BOUND", "This phone is linked to another store.", 409
                )
            seller.whatsapp_phone = phone
        challenge.consumed_at = utcnow()
        db.add(
            SellerSession(
                token_hash=digest(session_token),
                seller_id=seller.id,
                csrf_token=secrets.token_hex(32),
                expires_at=utcnow() + SESSION_TTL,
            )
        )
    return session_token


def allowed_origins():
    """Browser origins allowed to make credentialed state changes."""
    settings = get_settings()
    origins = {settings.frontend_url}
    if settings.app_env in {"local", "test"}:
        origins.update(DEV_ORIGINS)
    return origins


def require_origin(request):
    """Reject cross-site form posts before they reach unauthenticated state changes."""
    if request.headers.get("origin") not in allowed_origins():
        raise DomainError("CSRF_REJECTED", "Open AgentShelf to request sign-in.", 403)


def seller_access(request: Request, write=False):
    token = request.cookies.get(COOKIE, "")
    if not 20 <= len(token) <= 128:
        raise DomainError("SIGN_IN_REQUIRED", "Sign in to your seller account.", 401)
    with session_factory() as db:
        session = db.get(SellerSession, digest(token))
        if not session or session.expires_at <= utcnow():
            raise DomainError("SIGN_IN_REQUIRED", "Your session expired. Sign in again.", 401)
        seller = db.get(Seller, session.seller_id)
        if not seller or seller.status != "active":
            raise DomainError("SELLER_UNAVAILABLE", "This seller account is unavailable.", 403)
        if write and (
            request.headers.get("origin") not in allowed_origins()
            or not hmac.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf_token)
        ):
            raise DomainError("CSRF_REJECTED", "Reload your dashboard before trying again.", 403)
        return seller.id, session.csrf_token
