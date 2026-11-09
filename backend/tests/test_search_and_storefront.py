"""Relevance ranking, keyset pages, measured stats, cached reads and read routing."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app import cache, db, storefront
from app.config import get_settings
from app.db import session_factory
from app.main import create_app
from app.models import Product, Seller, utcnow

pytestmark = pytest.mark.integration


def catalog(products):
    with session_factory() as session, session.begin():
        seller = Seller(
            name="Ranked store",
            country="IN",
            paypal_email="ranked@example.invalid",
            store_slug="ranked",
            consent_at=utcnow(),
            status="active",
            shipping_rates={"GB": 1000, "US": 800},
        )
        session.add(seller)
        session.flush()
        ids = []
        for number, (title, description) in enumerate(products, start=1):
            product = Product(
                seller_id=seller.id,
                short_no=number,
                title=title,
                description=description,
                price_minor=1000 + number,
                stock=1,
                status="live",
            )
            session.add(product)
            session.flush()
            ids.append(str(product.id))
        return seller.id, ids


def test_title_matches_outrank_description_matches(db_clean):
    _, ids = catalog(
        [
            ("Cotton tote", "A bag that pairs well with a silk scarf."),
            ("Silk scarf", "Hand-rolled edges."),
            ("Brass lamp", "No textiles here."),
        ]
    )
    with TestClient(create_app()) as client:
        found = client.get("/api/products", params={"query": "silk scarf", "limit": 5}).json()
    assert [p["product_id"] for p in found["products"]] == [ids[1], ids[0]]
    assert found["next_cursor"] is None


def test_ranked_pages_are_complete_and_non_overlapping(db_clean):
    rows = [(f"Indigo scarf {i}", "Indigo dyed.") for i in range(7)]
    rows += [(f"Shawl {i}", "Indigo scarf weave.") for i in range(6)]
    catalog(rows)
    seen = []
    with TestClient(create_app()) as client:
        cursor = None
        while True:
            params = {"query": "indigo scarf", "limit": 4}
            if cursor:
                params["after"] = cursor
            page = client.get("/api/products", params=params).json()
            seen += [p["title"] for p in page["products"]]
            cursor = page["next_cursor"]
            if not cursor:
                break
    assert len(seen) == len(set(seen)) == 13
    # Every strong (title) match precedes every weaker (description-only) match.
    assert all(title.startswith("Indigo") for title in seen[:7])


def test_websearch_syntax_supports_or_and_exclusion(db_clean):
    catalog([("Silk scarf", "Soft."), ("Wool shawl", "Warm."), ("Silk tie", "Formal.")])
    with TestClient(create_app()) as client:
        either = client.get("/api/products", params={"query": "scarf OR shawl"}).json()
        excluded = client.get("/api/products", params={"query": "silk -tie"}).json()
    assert {p["title"] for p in either["products"]} == {"Silk scarf", "Wool shawl"}
    assert [p["title"] for p in excluded["products"]] == ["Silk scarf"]


def test_platform_stats_are_measured_not_invented(db_clean):
    catalog([("Silk scarf", "Soft."), ("Wool shawl", "Warm.")])
    with TestClient(create_app()) as client:
        response = client.get("/api/stats")
    assert response.json() == {"sellers": 1, "live_products": 2, "seller_countries": 1}
    assert response.headers["cache-control"] == "public, max-age=60"


def test_cached_reads_skip_the_database_until_a_seller_write(db_clean, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_cache_seconds", 30)
    cache.shared().invalidate()
    seller_id, ids = catalog([("Silk scarf", "Soft.")])
    statements = []

    def count(*args):
        statements.append(1)

    event.listen(db_clean, "before_cursor_execute", count)
    try:
        first = storefront.search(query="scarf")
        warm = len(statements)
        assert storefront.search(query="scarf") == first
        assert len(statements) == warm  # Served from cache: zero queries.
        from app import seller_catalog

        seller_catalog.archive_product(seller_id, uuid.UUID(ids[0]))
        assert storefront.search(query="scarf") == []  # Invalidated by the write.
    finally:
        event.remove(db_clean, "before_cursor_execute", count)
        cache.shared().invalidate()


def test_read_pool_falls_back_to_primary(db_clean, monkeypatch):
    assert db.get_read_engine() is db_clean
    settings = get_settings()
    monkeypatch.setattr(settings, "database_read_url", os.environ["TEST_DATABASE_URL"])
    db._replica_engine.cache_clear()
    try:
        replica = db.get_read_engine()
        assert replica is not db_clean
        with db.read_session() as session:
            assert session.get_bind() is replica
    finally:
        db._replica_engine().dispose()
        db._replica_engine.cache_clear()


def test_server_enforces_statement_timeout_and_application_name(db_clean, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "db_statement_timeout_ms", 1500)
    engine = db.build_engine(os.environ["TEST_DATABASE_URL"], settings, "agentshelf-probe")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SHOW statement_timeout").scalar() == "1500ms"
            assert connection.exec_driver_sql("SHOW application_name").scalar() == (
                "agentshelf-probe"
            )
            with pytest.raises(OperationalError):
                connection.exec_driver_sql("SELECT pg_sleep(3)")
    finally:
        engine.dispose()
