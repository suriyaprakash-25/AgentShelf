"""Shared database quotas; deployment must trust forwarded IPs only from its proxy."""

import hashlib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import session_factory
from app.errors import DomainError
from app.models import RateBucket, utcnow


def consume_ip(ip, scope, limit=60, window_seconds=60):
    key = scope + ":" + hashlib.sha256(ip.encode()).hexdigest()
    with session_factory() as db, db.begin():
        now = utcnow()
        db.execute(
            insert(RateBucket)
            .values(key=key, used=0, expires_at=now + timedelta(seconds=window_seconds))
            .on_conflict_do_nothing()
        )
        bucket = db.scalar(select(RateBucket).where(RateBucket.key == key).with_for_update())
        if bucket.expires_at <= now:
            bucket.used, bucket.expires_at = 0, now + timedelta(seconds=window_seconds)
        if bucket.used >= limit:
            raise DomainError("RATE_LIMITED", "Wait a minute before trying again.", 429)
        bucket.used += 1
