"""Use a dedicated test database, refusing accidental production destruction."""

import os

import pytest
from sqlalchemy import text

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://agentshelf:local-development-only@127.0.0.1:5433/agentshelf",
)
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def db_clean(monkeypatch):
    from sqlalchemy import create_engine

    from app import db
    from app.models import Base

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated database ending in _test")
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        pytest.fail("Tests require a dedicated database ending in _test")
    engine = create_engine(url, pool_size=25, max_overflow=0, connect_args={"connect_timeout": 5})
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    from app import main

    monkeypatch.setattr(main, "get_engine", lambda: engine)
    yield engine
    engine.dispose()


@pytest.fixture
def provider(monkeypatch):
    """Substitute provider calls only to test local invariants, never payment feasibility."""
    from app import paypal

    monkeypatch.setattr(paypal, "require_ready", lambda: None)
    calls = []

    def create(order, quote, seller):
        calls.append(str(order.id))
        return "TEST" + str(order.id).replace(
            "-", ""
        ), "https://www.sandbox.paypal.com/checkoutnow?token=TEST"

    monkeypatch.setattr(paypal, "create_order", create)
    return calls
