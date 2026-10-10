import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import quotes
from app.db import session_factory
from app.main import create_app
from app.models import Product
from tests.test_orders import fixture_data


@pytest.mark.integration
def test_thousand_product_catalog_has_bounded_nonoverlapping_pages(db_clean):
    product_id, _, _ = fixture_data()
    with session_factory() as db, db.begin():
        seller_id = db.get(Product, uuid.UUID(product_id)).seller_id
        db.add_all(
            [
                Product(
                    seller_id=seller_id,
                    short_no=i,
                    title=f"Textile {i}",
                    description="Synthetic scale fixture",
                    price_minor=1000,
                    stock=1,
                    status="live",
                )
                for i in range(2, 1002)
            ]
        )
    with TestClient(create_app()) as client:
        first = client.get("/api/products?limit=10").json()
        second = client.get(
            "/api/products", params={"limit": 10, "after": first["next_cursor"]}
        ).json()
        assert len(first["products"]) == len(second["products"]) == 10
        assert not {p["product_id"] for p in first["products"]} & {
            p["product_id"] for p in second["products"]
        }
        assert client.get("/api/products?after=invalid").status_code == 422
        assert client.get("/api/stores/test").json()["next_cursor"]
    durations = []
    with session_factory() as db:
        for _ in range(20):
            start = time.perf_counter()
            assert len(quotes.search_products(db, query="textile", limit=10)) == 10
            durations.append(time.perf_counter() - start)
    # This is local database evidence on synthetic data, not staged network latency.
    assert sorted(durations)[18] < 1
