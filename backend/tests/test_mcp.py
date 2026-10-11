"""Validate the actual mounted Streamable HTTP transport through an SDK client."""

import asyncio
import os
import socket
import subprocess
import sys
import time
import uuid

import httpx
import pytest
from mcp import Client

import evaluate_search
from app import quotes
from app.db import session_factory
from app.models import Product
from tests.test_orders import fixture_data


@pytest.mark.integration
def test_real_http_mcp_search_and_quote(db_clean):
    product_id, session_id, _ = fixture_data()
    colors = ["red", "green", "gold", "silver", "violet"]
    with session_factory() as db, db.begin():
        seller_id = db.get(Product, uuid.UUID(product_id)).seller_id
        db.add_all(
            Product(
                seller_id=seller_id,
                short_no=i + 2,
                title=f"Textile {colors[i % 5]} {i}",
                description="Synthetic scale fixture",
                price_minor=1000,
                stock=1,
                status="live",
            )
            for i in range(1000)
        )
    with session_factory() as db:
        cases = [
            {
                "query": color,
                "expected_ids": [
                    item["product_id"] for item in quotes.search_products(db, query=color, limit=10)
                ],
            }
            for color in colors
        ]
    search_dataset = evaluate_search.Dataset.model_validate({"searches": cases * 4})
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    env = dict(os.environ, DATABASE_URL=os.environ["TEST_DATABASE_URL"], APP_ENV="test")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail("MCP server exited before readiness")
            try:
                if httpx.get(base + "/healthz", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("MCP server did not become ready")

        async def exercise():
            async with Client(base + "/mcp") as client:
                tools = await client.list_tools()
                assert {tool.name for tool in tools.tools} == {
                    "search_products",
                    "get_quote",
                    "create_checkout",
                    "get_order_status",
                }
                search = await client.call_tool("search_products", {"query": "scarf"})
                assert search.structured_content["products"][0]["product_id"] == product_id
                quote = await client.call_tool(
                    "get_quote",
                    {
                        "product_id": product_id,
                        "qty": 1,
                        "ship_to_country": "GB",
                        "session_id": session_id,
                    },
                )
                assert quote.structured_content["total"] == "55.00"
                assert not quote.is_error

        asyncio.run(exercise())
        report = evaluate_search.run(base, search_dataset, "a" * 64, allow_loopback=True)
        assert report["catalog_products"] == 1001
        assert report["samples"] == 20
        assert report["decision"] == "targets_met"
        assert report["environment"] == "loopback"
        assert report["gate_approval"] is False
    finally:
        process.terminate()
        process.wait(timeout=10)
