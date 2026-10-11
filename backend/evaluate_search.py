"""Measure twenty real MCP searches against a stable, enumerated catalog."""

import argparse
import asyncio
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from mcp import Client
from pydantic import Field, model_validator

from app.paypal import parse_money
from evaluate_buyers import origin_url, request_json
from evaluate_listings import Input, digest, read_json, write_json


class Search(Input):
    query: str = Field(min_length=1, max_length=500)
    expected_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


class Dataset(Input):
    searches: list[Search] = Field(min_length=20, max_length=20)

    @model_validator(mode="after")
    def distinct_queries(self):
        if len({case.query.strip().casefold() for case in self.searches}) < 5:
            raise ValueError("EVAL_SEARCH_COVERAGE_INVALID")
        for case in self.searches:
            if not case.query.strip() or len(set(case.expected_ids)) != len(case.expected_ids):
                raise ValueError("EVAL_SEARCH_INVALID")
        return self


def catalog_snapshot(client):
    """Read public, searchable records; refuse cycles, duplicates and unbounded scans."""
    products, cursor = {}, None
    deadline = time.monotonic() + 120
    for _ in range(1001):
        if time.monotonic() >= deadline:
            raise ValueError("EVAL_CATALOG_TIMEOUT")
        params = {"limit": 10}
        if cursor:
            params["after"] = cursor
        page = request_json(client, "GET", "/api/products", params=params)
        items = page.get("products")
        if not isinstance(items, list) or len(items) > 10:
            raise ValueError("EVAL_CATALOG_INVALID")
        for item in items:
            product_id = str(uuid.UUID(item["product_id"]))
            if product_id in products or item.get("in_stock") is not True:
                raise ValueError("EVAL_CATALOG_INVALID")
            if item.get("currency") != "USD" or parse_money(item.get("price", "")) <= 0:
                raise ValueError("EVAL_CATALOG_PRICE_INVALID")
            # Bind the complete public record, including server price and currency.
            products[product_id] = item
        following = page.get("next_cursor")
        if following is None:
            if not 1000 <= len(products) <= 10000:
                raise ValueError("EVAL_CATALOG_SCALE_INVALID")
            return products
        if len(items) != 10 or following != items[-1]["product_id"] or following == cursor:
            raise ValueError("EVAL_CATALOG_CURSOR_INVALID")
        cursor = following
    raise ValueError("EVAL_CATALOG_TOO_LARGE")


def fingerprint(products):
    return digest(json.dumps(products, sort_keys=True).encode())


def validate_result(result, case, catalog):
    if result.is_error or not isinstance(result.structured_content, dict):
        raise ValueError("EVAL_TOOL_FAILED")
    products = result.structured_content.get("products")
    if not isinstance(products, list) or len(products) > 10:
        raise ValueError("EVAL_RESULTS_INVALID")
    ids = [item.get("product_id") for item in products]
    if ids != [str(value) for value in case.expected_ids]:
        raise ValueError("EVAL_RESULTS_MISMATCH")
    if any(item != catalog.get(item["product_id"]) for item in products):
        raise ValueError("EVAL_CATALOG_CHANGED_OR_PRICE_MISMATCH")


async def measure(endpoint, dataset, catalog):
    durations = []
    # Connection/initialization are bounded but excluded from per-search latency.
    async with asyncio.timeout(240), Client(endpoint + "/mcp", cache=None) as client:
        for case in dataset.searches:
            start = time.perf_counter()
            async with asyncio.timeout(10):
                result = await client.call_tool(
                    "search_products", {"query": case.query, "limit": 10}
                )
            elapsed = time.perf_counter() - start
            validate_result(result, case, catalog)
            durations.append(elapsed)
    return durations


def run(origin, dataset, dataset_hash, allow_loopback=False):
    endpoint = origin_url(origin, allow_loopback)
    with httpx.Client(base_url=endpoint, timeout=10, follow_redirects=False) as client:
        before = catalog_snapshot(client)
        if any(str(key) not in before for case in dataset.searches for key in case.expected_ids):
            raise ValueError("EVAL_EXPECTED_PRODUCT_MISSING")
        durations = asyncio.run(measure(endpoint, dataset, before))
        after = catalog_snapshot(client)
    if fingerprint(before) != fingerprint(after):
        raise ValueError("EVAL_CATALOG_CHANGED")
    p95 = sorted(durations)[18]
    return {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": dataset_hash,
        "catalog_sha256": fingerprint(before),
        "catalog_products": len(before),
        "samples": 20,
        "search_seconds": durations,
        "search_p95_seconds": p95,
        "decision": "targets_met" if p95 < 1 else "targets_not_met",
        "measurement_scope": "MCP tool round trip; excludes connection setup and catalog scans",
        "environment": "loopback"
        if urlsplit(endpoint).hostname in {"localhost", "127.0.0.1", "::1"}
        else "HTTPS endpoint",
        "postgres_index_verified": False,
        "gate_approval": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-loopback", action="store_true")
    args = parser.parse_args()
    try:
        if Path(args.output).exists():
            raise FileExistsError("EVAL_OUTPUT_EXISTS")
        data, dataset_hash = read_json(args.dataset)
        report = run(args.origin, Dataset.model_validate(data), dataset_hash, args.allow_loopback)
        write_json(args.output, report)
        print(json.dumps({"decision": report["decision"], "gate_approval": False}))
        return 0 if report["decision"] == "targets_met" else 1
    except Exception:
        # SDK/transport errors may contain hostnames, public records or proxy credentials.
        print(json.dumps({"status": "failed", "code": "EVAL_SEARCH_INCOMPLETE"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
