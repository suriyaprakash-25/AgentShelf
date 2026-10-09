"""Shared synchronous Postgres unit of work."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings


@lru_cache
def get_engine():
    """Create a bounded, connection-checked pool."""
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 5},
        pool_timeout=5,
    )


def session_factory():
    """Return a session that commits only through an explicit transaction."""
    return sessionmaker(get_engine(), expire_on_commit=False)()
