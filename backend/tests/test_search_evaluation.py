import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

import evaluate_search as evaluation


def product(number):
    return {
        "product_id": f"00000000-0000-0000-0000-{number:012d}",
        "price": "10.00",
        "currency": "USD",
        "in_stock": True,
    }


def dataset():
    return evaluation.Dataset.model_validate(
        {
            "searches": [
                {"query": f"textile {i % 5}", "expected_ids": [product(1)["product_id"]]}
                for i in range(20)
            ]
        }
    )


def test_dataset_requires_twenty_varied_searches():
    data = dataset().model_dump(mode="json")
    data["searches"].pop()
    with pytest.raises(ValidationError):
        evaluation.Dataset.model_validate(data)
    data = dataset().model_dump(mode="json")
    for case in data["searches"]:
        case["query"] = "same"
    with pytest.raises(ValidationError):
        evaluation.Dataset.model_validate(data)


@pytest.mark.parametrize("count", [999, 1000, 1001])
def test_catalog_enumerates_real_bounded_pages(count):
    def respond(request):
        after = request.url.params.get("after")
        offset = int(after[-12:]) if after else 0
        items = [product(i) for i in range(offset + 1, min(offset + 10, count) + 1)]
        return httpx.Response(
            200,
            json={
                "products": items,
                "next_cursor": items[-1]["product_id"] if len(items) == 10 else None,
            },
        )

    with httpx.Client(
        base_url="https://example.com", transport=httpx.MockTransport(respond)
    ) as client:
        if count < 1000:
            with pytest.raises(ValueError, match="SCALE"):
                evaluation.catalog_snapshot(client)
        else:
            assert len(evaluation.catalog_snapshot(client)) == count


@pytest.mark.parametrize("bad", ["duplicate", "cursor", "price", "currency", "stock"])
def test_catalog_rejects_invalid_records(monkeypatch, bad):
    items = [product(i) for i in range(1, 11)]
    cursor = items[-1]["product_id"]
    if bad == "duplicate":
        items[1] = items[0]
    elif bad == "cursor":
        cursor = items[0]["product_id"]
    elif bad == "price":
        items[0]["price"] = "0.00"
    elif bad == "currency":
        items[0]["currency"] = "GBP"
    else:
        items[0]["in_stock"] = False
    monkeypatch.setattr(
        evaluation, "request_json", lambda *a, **k: {"products": items, "next_cursor": cursor}
    )
    with pytest.raises(ValueError):
        evaluation.catalog_snapshot(None)


@pytest.mark.parametrize("bad", ["error", "ids", "price", "too_many"])
def test_tool_response_must_match_expected_server_records(bad):
    original = product(1)
    products = [dict(original)]
    if bad == "ids":
        products = [product(2)]
    elif bad == "price":
        products[0]["price"] = "0.01"
    elif bad == "too_many":
        products *= 11
    response = SimpleNamespace(is_error=bad == "error", structured_content={"products": products})
    with pytest.raises(ValueError):
        evaluation.validate_result(
            response, dataset().searches[0], {original["product_id"]: original}
        )


def test_measure_calls_actual_sdk_interface_twenty_times(monkeypatch):
    item = product(1)
    call = AsyncMock(
        return_value=SimpleNamespace(is_error=False, structured_content={"products": [item]})
    )

    class Client:
        async def __aenter__(self):
            return SimpleNamespace(call_tool=call)

        async def __aexit__(self, *args):
            pass

    def connect(endpoint, *, cache):
        assert endpoint.endswith("/mcp")
        assert cache is None
        return Client()

    monkeypatch.setattr(evaluation, "Client", connect)
    durations = asyncio.run(
        evaluation.measure("https://example.com", dataset(), {item["product_id"]: item})
    )
    assert len(durations) == call.await_count == 20
    assert all(value >= 0 for value in durations)
    assert all(args.args[0] == "search_products" for args in call.await_args_list)


@pytest.mark.parametrize("p95,decision", [(0.999, "targets_met"), (1, "targets_not_met")])
def test_summary_p95_boundary_and_no_gate_approval(monkeypatch, p95, decision):
    items = {product(i)["product_id"]: product(i) for i in range(1, 1001)}
    monkeypatch.setattr(evaluation, "catalog_snapshot", lambda client: items)
    monkeypatch.setattr(evaluation, "measure", AsyncMock(return_value=[0.1] * 18 + [p95, 5]))
    report = evaluation.run("https://example.com", dataset(), "a" * 64)
    assert report["decision"] == decision
    assert report["search_p95_seconds"] == p95
    assert report["gate_approval"] is report["postgres_index_verified"] is False
    assert "price" not in json_text(report)


def json_text(report):
    import json

    return json.dumps(report)


def test_catalog_change_leaves_evaluation_incomplete(monkeypatch):
    items = {product(i)["product_id"]: product(i) for i in range(1, 1001)}
    changed = {key: dict(value) for key, value in items.items()}
    changed[product(1)["product_id"]]["price"] = "11.00"
    snapshots = iter([items, changed])
    monkeypatch.setattr(evaluation, "catalog_snapshot", lambda client: next(snapshots))
    monkeypatch.setattr(evaluation, "measure", AsyncMock(return_value=[0.1] * 20))
    with pytest.raises(ValueError, match="CHANGED"):
        evaluation.run("https://example.com", dataset(), "a" * 64)


def test_cli_transport_failure_is_private_and_does_not_write_success(monkeypatch, tmp_path, capsys):
    import json
    import sys

    manifest, output = tmp_path / "dataset.json", tmp_path / "result.json"
    manifest.write_text(json.dumps(dataset().model_dump(mode="json")), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_search.py",
            "--origin",
            "https://example.com",
            "--dataset",
            str(manifest),
            "--output",
            str(output),
        ],
    )

    def fail(*args):
        raise RuntimeError("private-provider-error-and-record")

    monkeypatch.setattr(evaluation, "run", fail)
    assert evaluation.main() == 2
    assert not output.exists()
    assert "private-provider-error" not in capsys.readouterr().out


def test_cli_never_overwrites_evidence(monkeypatch, tmp_path):
    import sys

    output = tmp_path / "result.json"
    output.write_text("retained-evidence", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_search.py",
            "--origin",
            "https://example.com",
            "--dataset",
            "missing.json",
            "--output",
            str(output),
        ],
    )
    assert evaluation.main() == 2
    assert output.read_text(encoding="utf-8") == "retained-evidence"
