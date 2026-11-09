"""Shared synchronous Postgres units of work: a primary pool and an optional read pool.

Every connection is bounded so a slow or partitioned database fails fast instead of
pinning request threads: a connect timeout, a server-side statement timeout, an idle
transaction timeout, TCP keepalives and ``tcp_user_timeout`` for unacknowledged writes.
"""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

KEEPALIVE_IDLE_SECONDS = 15
KEEPALIVE_INTERVAL_SECONDS = 5
KEEPALIVE_COUNT = 3
# Above the worst-case provider budget a locked capture can spend (three bounded calls).
IDLE_TRANSACTION_TIMEOUT_MS = 120_000


def connect_args(settings, application_name="agentshelf"):
    """libpq options that bound every network wait and server-side query."""
    options = (
        f"-c statement_timeout={settings.db_statement_timeout_ms} "
        f"-c idle_in_transaction_session_timeout={IDLE_TRANSACTION_TIMEOUT_MS}"
    )
    return {
        "connect_timeout": settings.db_connect_timeout_seconds,
        "application_name": application_name,
        "options": options,
        "keepalives": 1,
        "keepalives_idle": KEEPALIVE_IDLE_SECONDS,
        "keepalives_interval": KEEPALIVE_INTERVAL_SECONDS,
        "keepalives_count": KEEPALIVE_COUNT,
        "tcp_user_timeout": settings.db_network_timeout_ms,
    }


def build_engine(url, settings, application_name):
    return create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=1800,
        connect_args=connect_args(settings, application_name),
    )


@lru_cache
def get_engine():
    """Create the bounded, connection-checked primary pool."""
    settings = get_settings()
    return build_engine(settings.database_url, settings, "agentshelf")


@lru_cache
def _replica_engine():
    settings = get_settings()
    return build_engine(settings.database_read_url, settings, "agentshelf-read")


def get_read_engine():
    """Return the replica pool when configured, otherwise the primary pool.

    Resolved at call time so tests and single-database deployments share one pool.
    """
    if get_settings().database_read_url:
        return _replica_engine()
    return get_engine()


def session_factory():
    """Return a primary session that commits only through an explicit transaction."""
    return sessionmaker(get_engine(), expire_on_commit=False)()


def read_session():
    """Return a session for anonymous reads that tolerate replica lag.

    Never use it for quotes, checkout, authentication, or anything that writes.
    """
    return sessionmaker(get_read_engine(), expire_on_commit=False)()


def dispose_engines():
    get_engine().dispose()
    if get_settings().database_read_url:
        _replica_engine().dispose()
