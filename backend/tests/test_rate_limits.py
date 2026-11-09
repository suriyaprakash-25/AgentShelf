"""Edge identity, signed Playground claims and atomic shared quotas."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app import rate_limits
from app.config import get_settings
from app.db import session_factory
from app.errors import DomainError
from app.models import RateBucket


def request(headers=None, host="10.0.0.9", path="/mcp", method="POST"):
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=host),
        url=SimpleNamespace(path=path),
        method=method,
    )


@pytest.mark.parametrize(
    ("hops", "header", "expected"),
    [
        (1, "6.6.6.6, 203.0.113.5", "203.0.113.5"),
        (1, "203.0.113.5", "203.0.113.5"),
        (2, "6.6.6.6, 203.0.113.5, 10.1.1.1", "203.0.113.5"),
        (2, "203.0.113.5", "10.0.0.9"),  # Fewer hops than proxies: not trustworthy.
        (0, "6.6.6.6", "10.0.0.9"),  # No trusted proxy: header is ignored.
        (None, "6.6.6.6, 203.0.113.5", "203.0.113.5"),  # Deployed default: one proxy.
    ],
)
def test_client_ip_uses_rightmost_trusted_hop(monkeypatch, hops, header, expected):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", hops)
    assert rate_limits.client_ip(request({"x-forwarded-for": header})) == expected


def test_forwarded_header_is_ignored_outside_deployed_proxies(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "local")
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", None)
    assert rate_limits.client_ip(request({"x-forwarded-for": "6.6.6.6"})) == "10.0.0.9"


def test_playground_token_round_trip_and_rejections():
    session = uuid.uuid4()
    token = rate_limits.playground_token(session, now=1_000)
    header = rate_limits.PLAYGROUND_HEADER
    assert rate_limits.playground_session(request({header: token}), now=1_010) == session
    expired = 1_000 + rate_limits.PLAYGROUND_TOKEN_TTL_SECONDS + 1
    assert rate_limits.playground_session(request({header: token}), now=expired) is None
    sid, deadline, signature = token.split(".")
    forged = f"{uuid.uuid4()}.{deadline}.{signature}"
    assert rate_limits.playground_session(request({header: forged}), now=1_010) is None
    stretched = f"{sid}.{int(deadline) + 3600}.{signature}"
    assert rate_limits.playground_session(request({header: stretched}), now=1_010) is None
    for junk in ("", "a.b", "not-a-uuid.1.x", "x" * 500):
        assert rate_limits.playground_session(request({header: junk}), now=1_010) is None


def test_unguarded_paths_and_preflight_skip_quotas():
    assert not rate_limits.is_guarded(request(path="/api/products", method="GET"))
    assert not rate_limits.is_guarded(request(path="/mcp", method="OPTIONS"))
    assert rate_limits.is_guarded(request(path="/mcp"))
    assert rate_limits.is_guarded(request(path="/api/playground/chat"))


@pytest.mark.integration
def test_atomic_quota_counts_resets_and_rolls_back(db_clean):
    policy = rate_limits.RatePolicy("unit", 3, 60)
    for _ in range(3):
        rate_limits.enforce(policy, "client")
    with pytest.raises(DomainError) as error:
        rate_limits.enforce(policy, "client")
    assert error.value.code == "RATE_LIMITED" and error.value.status == 429
    key = rate_limits.hashed_key("unit", "client")
    with session_factory() as db:
        assert db.get(RateBucket, key).used == 3  # The rejected call was rolled back.
    with session_factory() as db, db.begin():
        db.get(RateBucket, key).expires_at = db.get(RateBucket, key).expires_at.replace(year=2000)
    rate_limits.enforce(policy, "client")  # An expired window restarts at one.
    with session_factory() as db:
        assert db.get(RateBucket, key).used == 1


@pytest.mark.integration
def test_concurrent_quota_admits_exactly_the_limit(db_clean):
    policy = rate_limits.RatePolicy("burst", 10, 60)

    def attempt(_):
        try:
            rate_limits.enforce(policy, "same-client")
            return True
        except DomainError:
            return False

    with ThreadPoolExecutor(20) as pool:
        admitted = sum(pool.map(attempt, range(40)))
    assert admitted == 10


@pytest.mark.integration
def test_signed_playground_mcp_uses_session_bucket(db_clean, monkeypatch):
    session = uuid.uuid4()
    signed = request({rate_limits.PLAYGROUND_HEADER: rate_limits.playground_token(session)})
    rate_limits.guard_request(signed)
    rate_limits.guard_request(request())  # Unsigned callers still use the per-IP quota.
    with session_factory() as db:
        assert db.get(RateBucket, rate_limits.hashed_key("mcp-session", session)).used == 1
        assert db.get(RateBucket, rate_limits.hashed_key("mcp", "10.0.0.9")).used == 1
