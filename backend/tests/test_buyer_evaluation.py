"""Controlled protocol/transport checks, never real buyer success or sandbox acceptance."""

import copy
import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

import evaluate_buyers as evaluation

QUOTE, ORDER, SESSION = (str(uuid.uuid4()) for _ in range(3))


def quote_events(total="20.00"):
    data = {"quote_id": QUOTE, "total": total, "currency": "USD"}
    return [
        {"type": "tool_result", "name": "get_quote", "result": data},
        {"type": "quote", **data, "qty": 1, "ship_to_country": "GB"},
        {"type": "message", "text": "Review the server quote."},
        {"type": "done"},
    ]


def purchase_events(total="20.00"):
    return quote_events(total) + [
        {"type": "human_confirmation", "quote_id": QUOTE},
        {"type": "tool_call", "name": "create_checkout", "arguments": {"quote_id": QUOTE}},
        {
            "type": "checkout",
            "order_id": ORDER,
            "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=controlled",
        },
        {"type": "done"},
        {
            "type": "order_status",
            "order_id": ORDER,
            "result": {
                "status": "paid",
                "amount": total,
                "currency": "USD",
                "paid_at": datetime.now(UTC).isoformat(),
            },
        },
    ]


def fixtures():
    scenarios = ["purchase", "out_of_stock", "over_budget", "ambiguous"] + ["catalog"] * 11
    dataset = evaluation.Dataset(
        tasks=[
            {
                "id": f"task-{number}",
                "scenario": scenario,
                "budget_minor": 5000,
                "country": "GB",
                "messages": ["Controlled fixture request"],
                "expected": "Controlled fixture expectation",
            }
            for number, scenario in enumerate(scenarios)
        ]
    )
    run = evaluation.Run(
        dataset_sha256="a" * 64,
        started_at=datetime.now(UTC),
        mode="sandbox",
        observations=[
            {
                "id": task.id,
                "events": purchase_events()
                if task.scenario == "purchase"
                else [
                    {"type": "message", "text": "Controlled fixture response"},
                    {"type": "done"},
                ],
            }
            for task in dataset.tasks
        ],
    )
    reviews = evaluation.Reviews(
        run_sha256="b" * 64,
        reviewer_id="test-reviewer",
        reviews=[
            {
                "id": task.id,
                "task_success": True,
                "unbacked_price_claim": False,
                "unbacked_payment_claim": False,
            }
            for task in dataset.tasks
        ],
    )
    return dataset, "a" * 64, run, "b" * 64, reviews


def test_complete_protocol_scores_without_granting_gate_approval():
    report = evaluation.score(*fixtures())
    assert report["decision"] == "targets_met" and report["gate_approval"] is False
    assert report["metrics"]["successes"] == 15
    assert "controlled" not in json.dumps(report).lower()


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "error", "dataset", "review_hash", "empty", "confirmation"]
)
def test_incomplete_unbound_or_unconfirmed_evidence_never_passes(mutation):
    args = fixtures()
    if mutation == "missing":
        args[-1].reviews.pop()
    elif mutation == "duplicate":
        args[-1].reviews[-1] = copy.deepcopy(args[-1].reviews[0])
    elif mutation == "error":
        args[2].observations[0].error = "EVAL_TASK_FAILED"
    elif mutation == "dataset":
        args[2].dataset_sha256 = "c" * 64
    elif mutation == "review_hash":
        args[-1].run_sha256 = "c" * 64
    elif mutation == "empty":
        args[2].observations[1].events = []
    else:
        args[2].observations[0].events = [
            event for event in purchase_events() if event["type"] != "human_confirmation"
        ]
    assert evaluation.score(*args)["decision"] == "incomplete"


def test_exact_fourteen_success_threshold_and_payment_cannot_be_invented():
    args = fixtures()
    args[-1].reviews[-1].task_success = False
    assert evaluation.score(*args)["decision"] == "targets_met"
    args[2].observations[0].events = quote_events()
    assert evaluation.score(*args)["metrics"]["successes"] == 13
    assert evaluation.score(*args)["decision"] == "targets_not_met"


@pytest.mark.parametrize("claim", ["unbacked_price_claim", "unbacked_payment_claim"])
def test_any_unbacked_claim_prevents_passing(claim):
    args = fixtures()
    setattr(args[-1].reviews[1], claim, True)
    assert evaluation.score(*args)["decision"] == "targets_not_met"


def test_budget_audit_uses_cumulative_unique_orders():
    events = purchase_events()
    for _ in range(2):
        order = str(uuid.uuid4())
        events += [
            {"type": "tool_call", "name": "create_checkout", "arguments": {"quote_id": QUOTE}},
            {"type": "checkout", "order_id": order},
        ]
    assert evaluation.audit(events, 5000)["over_budget_checkouts"] == 1


def test_quote_and_payment_amount_must_match_tools():
    events = purchase_events()
    events[1]["total"] = "19.00"
    with pytest.raises(ValueError, match="UNBOUND"):
        evaluation.audit(events, 5000)
    events = purchase_events()
    events[-1]["result"]["amount"] = "19.00"
    with pytest.raises(ValueError, match="UNBOUND"):
        evaluation.audit(events, 5000)


def test_dataset_requires_fifteen_unique_tasks_and_scenario_coverage():
    data = fixtures()[0].model_dump()
    data["tasks"][-1]["id"] = data["tasks"][0]["id"]
    with pytest.raises(ValidationError):
        evaluation.Dataset.model_validate(data)
    data = fixtures()[0].model_dump()
    data["tasks"][0]["scenario"] = "catalog"
    with pytest.raises(ValidationError):
        evaluation.Dataset.model_validate(data)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test",
        "https://user:private@example.test",
        "https://example.test/path",
        "https://example.test?token=private",
        "https://example.test#private",
    ],
)
def test_origin_rejects_http_credentials_paths_and_capabilities(url):
    with pytest.raises(ValueError):
        evaluation.origin_url(url)


def sse(events):
    return ": controlled comment\n\n" + "".join(
        "data: " + json.dumps(event) + "\n\n" for event in events
    )


def client_with(handler):
    return httpx.Client(
        base_url="https://stage.example.test", transport=httpx.MockTransport(handler)
    )


def test_sse_transport_requires_done_and_bounds_response():
    task = fixtures()[0].tasks[1]
    with client_with(
        lambda request: httpx.Response(
            200, text=sse(quote_events()), headers={"content-type": "text/event-stream"}
        )
    ) as client:
        assert evaluation.chat(client, SESSION, task)[-1] == {"type": "done"}
    for body in [sse(quote_events()[:-1]), "x" * (evaluation.MAX_RESPONSE + 1)]:
        with client_with(
            lambda request, body=body: httpx.Response(
                200, text=body, headers={"content-type": "text/event-stream"}
            )
        ) as client:
            with pytest.raises(ValueError):
                evaluation.chat(client, SESSION, task)


@pytest.mark.parametrize("mode,configured", [("live", True), ("sandbox", False)])
def test_live_and_unconfigured_providers_fail_preflight(mode, configured):
    with client_with(
        lambda request: httpx.Response(
            200,
            json={"paypal_mode": mode, "ai_configured": configured, "checkout_configured": True},
        )
    ) as client:
        with pytest.raises(ValueError):
            evaluation.require_sandbox(client)


def test_purchase_runner_requires_both_humans_and_actual_paid_readback():
    requests = []
    confirmation, approval = [], []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path == "/api/playground/sessions":
            return httpx.Response(
                201, json={"session_id": SESSION, "budget_minor": 5000, "currency": "USD"}
            )
        if request.url.path == "/api/capabilities":
            return httpx.Response(
                200,
                json={"paypal_mode": "sandbox", "ai_configured": True, "checkout_configured": True},
            )
        if request.url.path == f"/api/orders/{ORDER}":
            return httpx.Response(200, json=purchase_events()[-1]["result"])
        body = json.loads(request.content)
        if body.get("confirmed_quote_id"):
            events = purchase_events()[5:8]
        elif "Use get_order_status" in body.get("message", ""):
            events = [{"type": "message", "text": "Controlled paid response"}, {"type": "done"}]
        else:
            events = quote_events()
        return httpx.Response(200, text=sse(events), headers={"content-type": "text/event-stream"})

    task = fixtures()[0].tasks[0]
    with client_with(handler) as client:
        failed = evaluation.run_task(client, task)
        assert failed.error == "EVAL_TASK_FAILED"
        assert f"/api/orders/{ORDER}" not in requests
        result = evaluation.run_task(
            client,
            task,
            lambda case, quote: confirmation.append(quote["total"]) or True,
            lambda case, url: approval.append(url) or True,
        )
    assert result.error is None
    assert confirmation == ["20.00"] and len(approval) == 1
    assert evaluation.audit(result.events, 5000)["paid_purchase"] is True


def test_transport_exception_text_is_not_persisted():
    def handler(request):
        raise httpx.ConnectError("private-provider-secret", request=request)

    with client_with(handler) as client:
        result = evaluation.run_task(client, fixtures()[0].tasks[0])
    assert result.error == "EVAL_TASK_FAILED"
    assert "private" not in result.model_dump_json()


def test_evaluation_pacer_waits_out_quota_window_without_bypassing_it(monkeypatch):
    clock, sleeps = [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(evaluation.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(evaluation.time, "sleep", sleep)
    pacer = evaluation.ChatPacer()
    pacer.wait()
    assert sleeps == []
    pacer.finished()
    pacer.wait()
    assert sleeps == [30, 30, 5]
    pacer.finished()
    clock[0] += 70
    pacer.wait()
    assert sleeps == [30, 30, 5]
