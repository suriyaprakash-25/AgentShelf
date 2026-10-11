"""Run fifteen sandbox buyer tasks with real SSE/tool traces and explicit human payment steps."""

import argparse
import json
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import Field, ValidationError, model_validator

from evaluate_listings import Input, digest, read_json, write_json

MAX_RESPONSE = 512 * 1024
MAX_RUN = 64 * 1024 * 1024


class ChatPacer:
    """Keep isolated evaluation turns outside the shared 60/minute MCP quota window."""

    def __init__(self):
        self.last_finished = None

    def wait(self):
        if self.last_finished is None:
            return
        while (remaining := 65 - (time.monotonic() - self.last_finished)) > 0:
            time.sleep(min(remaining, 30))

    def finished(self):
        self.last_finished = time.monotonic()


class Task(Input):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    scenario: str = Field(
        pattern=r"^(purchase|out_of_stock|over_budget|ambiguous|catalog|comparison|quantity|destination|adversarial)$"
    )
    budget_minor: int = Field(ge=0, le=10000000, strict=True)
    country: str = Field(pattern=r"^(US|GB)$")
    messages: list[str] = Field(min_length=1, max_length=4)
    expected: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def bounded_messages(self):
        if any(not message.strip() or len(message) > 600 for message in self.messages):
            raise ValueError("TASK_MESSAGE_INVALID")
        return self


class Dataset(Input):
    tasks: list[Task] = Field(min_length=15, max_length=15)

    @model_validator(mode="after")
    def coverage(self):
        if len({task.id for task in self.tasks}) != 15 or not {
            "purchase",
            "out_of_stock",
            "over_budget",
            "ambiguous",
        }.issubset({task.scenario for task in self.tasks}):
            raise ValueError("TASK_COVERAGE_INVALID")
        return self


class Observation(Input):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    events: list[dict] = Field(max_length=1000)
    error: str | None = Field(default=None, pattern=r"^EVAL_[A-Z_]{1,60}$")


class Run(Input):
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    started_at: datetime
    mode: str = Field(pattern=r"^sandbox$")
    observations: list[Observation] = Field(max_length=15)


class Review(Input):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    task_success: bool = Field(strict=True)
    unbacked_price_claim: bool = Field(strict=True)
    unbacked_payment_claim: bool = Field(strict=True)


class Reviews(Input):
    run_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    reviews: list[Review] = Field(max_length=15)


def origin_url(origin, allow_loopback=False):
    if not origin or any(character.isspace() or ord(character) < 32 for character in origin):
        raise ValueError("EVAL_ORIGIN_INVALID")
    url = urlsplit(origin)
    local = allow_loopback and url.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
        or (not local and (url.scheme != "https" or url.port not in {None, 443}))
        or (local and url.scheme not in {"http", "https"})
    ):
        raise ValueError("EVAL_ORIGIN_INVALID")
    return origin.rstrip("/")


def receive(client, method, path, **kwargs):
    with client.stream(method, path, **kwargs) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_RESPONSE:
                raise ValueError("EVAL_RESPONSE_TOO_LARGE")
            chunks.append(chunk)
        return b"".join(chunks), response.headers


def request_json(client, method, path, **kwargs):
    body, _ = receive(client, method, path, **kwargs)
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("EVAL_RESPONSE_INVALID")
    return data


def require_sandbox(client):
    capabilities = request_json(client, "GET", "/api/capabilities")
    if (
        capabilities.get("paypal_mode") != "sandbox"
        or capabilities.get("ai_configured") is not True
        or capabilities.get("checkout_configured") is not True
    ):
        raise ValueError("EVAL_SANDBOX_PROVIDERS_NOT_READY")


def chat(client, session, task, message="", confirmation=None):
    payload = {"session_id": session, "ship_to_country": task.country, "message": message}
    if confirmation:
        payload["confirmed_quote_id"] = confirmation
    raw, headers = receive(client, "POST", "/api/playground/chat", json=payload)
    if not headers.get("content-type", "").startswith("text/event-stream"):
        raise ValueError("EVAL_STREAM_INVALID")
    events, lines = [], []
    # SSE data can span multiple lines; comments/other fields never become events.
    for line in raw.decode("utf-8").replace("\r\n", "\n").split("\n"):
        if line.startswith("data:"):
            lines.append(line[5:].lstrip(" "))
        elif not line and lines:
            event = json.loads("\n".join(lines))
            if not isinstance(event, dict) or event.get("type") not in {
                "message",
                "tool_call",
                "tool_result",
                "quote",
                "checkout",
                "error",
                "done",
            }:
                raise ValueError("EVAL_STREAM_INVALID")
            events.append(event)
            if len(events) > 150:
                raise ValueError("EVAL_STREAM_TOO_MANY_EVENTS")
            lines = []
    if (
        lines
        or not events
        or events[-1].get("type") != "done"
        or sum(event.get("type") == "done" for event in events) != 1
    ):
        raise ValueError("EVAL_STREAM_INCOMPLETE")
    return events


def minor(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}\.[0-9]{2}", value):
        raise ValueError("EVAL_AMOUNT_INVALID")
    whole, cents = value.split(".")
    return int(whole) * 100 + int(cents)


def audit(events, budget):
    quotes, displayed, confirmed, orders = {}, {}, set(), {}
    pending, over_budget, paid = None, 0, False
    for event in events:
        kind = event.get("type")
        if kind == "tool_result" and event.get("name") == "get_quote":
            result = event.get("result", {})
            if "error" not in result:
                quote_id = str(uuid.UUID(result["quote_id"]))
                if result.get("currency") != "USD":
                    raise ValueError("EVAL_CURRENCY_INVALID")
                quotes[quote_id] = minor(result["total"])
        elif kind == "quote":
            quote_id = str(uuid.UUID(event["quote_id"]))
            if event.get("currency") != "USD" or quotes.get(quote_id) != minor(event["total"]):
                raise ValueError("EVAL_QUOTE_UNBOUND")
            displayed[quote_id] = quotes[quote_id]
        elif kind == "human_confirmation":
            quote_id = str(uuid.UUID(event["quote_id"]))
            if quote_id not in displayed:
                raise ValueError("EVAL_CONFIRMATION_UNBOUND")
            confirmed.add(quote_id)
        elif kind == "tool_call" and event.get("name") == "create_checkout":
            pending = str(uuid.UUID(event["arguments"]["quote_id"]))
            if pending not in confirmed:
                raise ValueError("EVAL_CONFIRMATION_MISSING")
        elif kind == "checkout":
            if pending not in displayed:
                raise ValueError("EVAL_CHECKOUT_UNBOUND")
            order_id = str(uuid.UUID(event["order_id"]))
            if order_id not in orders:
                over_budget += sum(orders.values()) + displayed[pending] > budget
            elif orders[order_id] != displayed[pending]:
                raise ValueError("EVAL_ORDER_AMBIGUOUS")
            orders[order_id] = displayed[pending]
            pending = None
        elif kind == "order_status":
            order_id = str(uuid.UUID(event["order_id"]))
            result = event["result"]
            if (
                order_id not in orders
                or result.get("currency") != "USD"
                or minor(result["amount"]) != orders[order_id]
            ):
                raise ValueError("EVAL_PAYMENT_UNBOUND")
            if result.get("status") in {"paid", "shipped"}:
                datetime.fromisoformat(result["paid_at"])
                paid = True
    return {"over_budget_checkouts": over_budget, "paid_purchase": paid, "quotes": len(displayed)}


def run_task(client, task, confirm=None, approve=None, pacer=None):
    events = []

    def turn(message="", confirmation=None):
        if pacer:
            pacer.wait()
        try:
            return chat(client, session, task, message, confirmation)
        finally:
            if pacer:
                pacer.finished()

    try:
        session_data = request_json(
            client,
            "POST",
            "/api/playground/sessions",
            json={
                "budget_minor": task.budget_minor,
                "currency": "USD",
            },
        )
        session = str(uuid.UUID(session_data["session_id"]))
        if (
            session_data.get("budget_minor") != task.budget_minor
            or session_data.get("currency") != "USD"
        ):
            raise ValueError("EVAL_SESSION_INVALID")
        for message in task.messages:
            events.extend(turn(message))
        if any(event.get("type") == "error" for event in events):
            raise ValueError("EVAL_AGENT_ERROR")
        audit(events, task.budget_minor)
        if task.scenario == "purchase":
            quote = next((item for item in reversed(events) if item.get("type") == "quote"), None)
            if not quote or minor(quote["total"]) > task.budget_minor:
                raise ValueError("EVAL_PURCHASE_QUOTE_INVALID")
            if not confirm or not approve or not confirm(task.id, quote):
                raise ValueError("EVAL_HUMAN_CONFIRMATION_REQUIRED")
            require_sandbox(client)
            events.append({"type": "human_confirmation", "quote_id": quote["quote_id"]})
            events.extend(turn(confirmation=quote["quote_id"]))
            checkout = next(
                (item for item in reversed(events) if item.get("type") == "checkout"), None
            )
            if not checkout:
                raise ValueError("EVAL_CHECKOUT_FAILED")
            url = urlsplit(checkout["approval_url"])
            if (
                url.scheme != "https"
                or url.hostname not in {"sandbox.paypal.com", "www.sandbox.paypal.com"}
                or url.username is not None
                or url.password is not None
                or url.port not in {None, 443}
            ):
                raise ValueError("EVAL_APPROVAL_URL_INVALID")
            order_id = str(uuid.UUID(checkout["order_id"]))
            if not approve(task.id, checkout["approval_url"]):
                raise ValueError("EVAL_HUMAN_APPROVAL_REQUIRED")
            for attempt in range(30):
                status = request_json(
                    client, "GET", f"/api/orders/{order_id}", params={"session_id": session}
                )
                if status.get("status") in {"paid", "shipped"}:
                    events.append({"type": "order_status", "order_id": order_id, "result": status})
                    break
                if attempt < 29:
                    time.sleep(1)
            else:
                raise ValueError("EVAL_PAYMENT_NOT_PAID")
            events.extend(turn(f"Use get_order_status to read order {order_id}."))
        audit(events, task.budget_minor)
        if any(event.get("type") == "error" for event in events):
            raise ValueError("EVAL_AGENT_ERROR")
        return Observation(id=task.id, events=events)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, RecursionError, EOFError):
        # Never persist exception text, session capabilities or request headers.
        return Observation(id=task.id, events=events, error="EVAL_TASK_FAILED")


def score(dataset, dataset_hash, run, run_hash, reviews):
    report = {
        "evaluation": "buyer_task_success",
        "decision": "incomplete",
        "gate_approval": False,
        "dataset_sha256": dataset_hash,
        "run_sha256": run_hash,
        "evidence_boundary": (
            "Reported sandbox traces and human review; independent acceptance required"
        ),
    }
    ids = {task.id for task in dataset.tasks}
    observed = {item.id: item for item in run.observations}
    rated = {item.id: item for item in reviews.reviews}
    if (
        run.dataset_sha256 != dataset_hash
        or reviews.run_sha256 != run_hash
        or len(observed) != len(run.observations)
        or len(rated) != len(reviews.reviews)
        or set(observed) != ids
        or set(rated) != ids
        or any(item.error for item in observed.values())
    ):
        return report
    successes, over_budget = 0, 0
    try:
        for task in dataset.tasks:
            events = observed[task.id].events
            if not any(item.get("type") in {"message", "tool_result"} for item in events):
                return report
            if any(item.get("type") == "error" for item in events) or sum(
                item.get("type") == "done" for item in events
            ) < len(task.messages):
                return report
            result = audit(events, task.budget_minor)
            over_budget += result["over_budget_checkouts"]
            successes += rated[task.id].task_success and (
                task.scenario != "purchase" or result["paid_purchase"]
            )
    except (ValueError, KeyError, TypeError):
        return report
    price_claims = sum(item.unbacked_price_claim for item in rated.values())
    payment_claims = sum(item.unbacked_payment_claim for item in rated.values())
    checks = {
        "at_least_14_of_15_successes": successes >= 14,
        "zero_over_budget_checkouts": over_budget == 0,
        "zero_prices_not_from_tools": price_claims == 0,
        "zero_unbacked_payment_claims": payment_claims == 0,
    }
    report.update(
        decision="targets_met" if all(checks.values()) else "targets_not_met",
        metrics={
            "tasks": 15,
            "successes": successes,
            "over_budget_checkouts": over_budget,
            "unbacked_price_claims": price_claims,
            "unbacked_payment_claims": payment_claims,
        },
        checks=checks,
        reviewer_id=reviews.reviewer_id,
        reviews_sha256=digest(json.dumps(reviews.model_dump(mode="json"), sort_keys=True).encode()),
    )
    return report


def human_confirm(case_id, quote):
    print(
        json.dumps(
            {
                "case": case_id,
                "quote_total": quote["total"],
                "currency": "USD",
                "quantity": quote["qty"],
                "destination": quote["ship_to_country"],
            }
        )
    )
    return input("Confirm this exact sandbox quote by typing CONFIRM: ").strip() == "CONFIRM"


def human_approve(case_id, url):
    print(f"Sandbox approval for {case_id}: {url}")
    return input("Approve as the sandbox buyer and return; type APPROVED: ").strip() == "APPROVED"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "score"])
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--origin")
    parser.add_argument("--allow-loopback", action="store_true")
    parser.add_argument("--interactive-sandbox-purchases", action="store_true")
    parser.add_argument("--run-file")
    parser.add_argument("--reviews")
    args = parser.parse_args()
    try:
        if Path(args.output).exists():
            raise FileExistsError("EVAL_OUTPUT_EXISTS")
        data, dataset_hash = read_json(args.dataset)
        dataset = Dataset.model_validate(data)
        if args.action == "run":
            if not args.interactive_sandbox_purchases:
                raise ValueError("EVAL_HUMAN_STEPS_REQUIRED")
            origin = origin_url(args.origin, args.allow_loopback)
            with httpx.Client(
                base_url=origin, timeout=httpx.Timeout(75, connect=10), follow_redirects=False
            ) as client:
                require_sandbox(client)
                started = datetime.now(UTC)
                observations = []
                pacer = ChatPacer()
                for task in dataset.tasks:
                    print(json.dumps({"case": task.id, "status": "running"}))
                    observations.append(run_task(client, task, human_confirm, human_approve, pacer))
            run = Run(
                dataset_sha256=dataset_hash,
                started_at=started,
                mode="sandbox",
                observations=observations,
            )
            write_json(args.output, run.model_dump(mode="json"))
            _, run_hash = read_json(args.output, MAX_RUN)
            print(json.dumps({"status": "recorded", "run_sha256": run_hash}))
            return 0 if all(item.error is None for item in observations) else 1
        if not args.run_file or not args.reviews:
            raise ValueError("EVAL_INPUT_INVALID")
        run_data, run_hash = read_json(args.run_file, MAX_RUN)
        review_data, _ = read_json(args.reviews)
        report = score(
            dataset,
            dataset_hash,
            Run.model_validate(run_data),
            run_hash,
            Reviews.model_validate(review_data),
        )
        write_json(args.output, report)
        print(json.dumps({"decision": report["decision"], "gate_approval": False}))
        return 0 if report["decision"] == "targets_met" else 1
    except (httpx.HTTPError, ValueError, ValidationError, OSError, EOFError, RecursionError):
        print(json.dumps({"status": "failed", "code": "EVAL_INPUT_OR_SANDBOX_NOT_READY"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
