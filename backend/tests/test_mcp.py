"""Validate the actual mounted Streamable HTTP transport through an SDK client."""

import asyncio
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from mcp import Client

from tests.test_orders import fixture_data


@pytest.mark.integration
def test_real_http_mcp_search_and_quote(db_clean):
    product_id, session_id, _ = fixture_data()
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
    finally:
        process.terminate()
        process.wait(timeout=10)
