"""TTL cache semantics, provider circuit breaking and the PayPal transport policy."""

import threading
import time

import httpx
import pytest

from app import paypal
from app.cache import TTLCache
from app.errors import DomainError
from app.resilience import CLOSED, HALF_OPEN, OPEN, CircuitBreaker, CircuitOpenError


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_cache_expires_bounds_and_invalidates_by_namespace():
    clock = Clock()
    cache = TTLCache(max_entries=2, clock=clock)
    loads = []

    def loader(value):
        def load():
            loads.append(value)
            return value

        return load

    assert cache.get_or_load(("catalog", 1), 10, loader("a")) == "a"
    assert cache.get_or_load(("catalog", 1), 10, loader("b")) == "a"
    clock.now = 11
    assert cache.get_or_load(("catalog", 1), 10, loader("c")) == "c"
    cache.get_or_load(("stats", 1), 10, loader("s"))
    cache.get_or_load(("catalog", 2), 10, loader("d"))
    assert len(cache) == 2  # Least recently used entry was evicted.
    cache.invalidate("catalog")
    assert len(cache) == 1
    assert cache.get_or_load(("stats", 1), 10, loader("x")) == "s"
    assert loads == ["a", "c", "s", "d"]


def test_cache_zero_ttl_bypasses_and_errors_are_not_cached():
    cache = TTLCache()
    assert cache.get_or_load("k", 0, lambda: 1) == 1
    assert len(cache) == 0

    def fail():
        raise DomainError("STORE_NOT_FOUND", "missing", 404)

    with pytest.raises(DomainError):
        cache.get_or_load("k", 10, fail)
    assert cache.get_or_load("k", 10, lambda: "loaded") == "loaded"


def test_cache_single_flight_loads_once_under_concurrent_misses():
    cache = TTLCache()
    calls = []
    barrier = threading.Barrier(16)

    def slow():
        calls.append(1)
        time.sleep(0.05)
        return "value"

    def worker(results):
        barrier.wait()
        results.append(cache.get_or_load(("catalog", "hot"), 10, slow))

    results = []
    threads = [threading.Thread(target=worker, args=(results,)) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == ["value"] * 16 and len(calls) == 1


def test_breaker_opens_half_opens_and_recloses():
    clock = Clock()
    breaker = CircuitBreaker("test", failure_threshold=2, reset_after_seconds=30, clock=clock)
    breaker.before_call()
    breaker.record_failure()
    assert breaker.state == CLOSED
    breaker.record_failure()
    assert breaker.state == OPEN
    with pytest.raises(CircuitOpenError):
        breaker.before_call()
    clock.now = 31
    assert breaker.state == HALF_OPEN
    breaker.before_call()  # One trial call is admitted ...
    with pytest.raises(CircuitOpenError):
        breaker.before_call()  # ... and concurrent callers still fail fast.
    breaker.record_failure()
    assert breaker.state == OPEN  # A failed trial reopens for a full period.
    clock.now = 62
    breaker.before_call()
    breaker.record_success()
    assert breaker.state == CLOSED


@pytest.fixture
def paypal_transport(monkeypatch):
    paypal.breaker.reset()
    calls = []

    def install(handler):
        def fake_request(method, url, timeout=None, **kwargs):
            calls.append((method, url, timeout))
            return handler(httpx.Request(method, url))

        monkeypatch.setattr(paypal.httpx, "request", fake_request)
        return calls

    yield install
    paypal.breaker.reset()


def test_paypal_connect_failure_retries_once_then_counts(paypal_transport):
    def refuse(request):
        raise httpx.ConnectError("private-network-detail", request=request)

    calls = paypal_transport(refuse)
    with pytest.raises(httpx.ConnectError):
        paypal.send("GET", "https://api-m.sandbox.paypal.com/v2/checkout/orders/X")
    assert len(calls) == 2 and calls[0][2] == paypal.TIMEOUT
    assert paypal.breaker._failures == 1


def test_paypal_client_errors_do_not_trip_breaker(paypal_transport):
    paypal_transport(lambda request: httpx.Response(422, request=request))
    for _ in range(paypal.breaker.failure_threshold + 1):
        with pytest.raises(httpx.HTTPStatusError):
            paypal.send("POST", "https://api-m.sandbox.paypal.com/v2/checkout/orders")
    assert paypal.breaker.state == CLOSED


def test_paypal_outage_fails_fast_once_open(paypal_transport):
    calls = paypal_transport(lambda request: httpx.Response(503, request=request))
    for _ in range(paypal.breaker.failure_threshold):
        with pytest.raises(httpx.HTTPStatusError):
            paypal.send("GET", "https://api-m.sandbox.paypal.com/v2/checkout/orders/X")
    attempted = len(calls)
    with pytest.raises(CircuitOpenError):
        paypal.send("GET", "https://api-m.sandbox.paypal.com/v2/checkout/orders/X")
    assert len(calls) == attempted  # No network call while open.


def test_open_breaker_surfaces_as_uncertain_payment_error(paypal_transport, monkeypatch):
    calls = paypal_transport(lambda request: httpx.Response(200, request=request))
    monkeypatch.setattr(paypal, "get_token", lambda: "controlled-token")
    for _ in range(paypal.breaker.failure_threshold):
        paypal.breaker.record_failure()
    with pytest.raises(DomainError) as error:
        paypal.read_order("ORDER123")
    assert error.value.code == "PAYPAL_UNAVAILABLE" and calls == []
