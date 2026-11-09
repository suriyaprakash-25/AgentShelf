"""Failure isolation for outbound provider calls.

A provider outage must not tie up request threads and database connections waiting
on doomed calls. After ``failure_threshold`` consecutive transport failures, the
breaker fails fast for ``reset_after_seconds``, then lets one trial call through
(half-open). Business errors (HTTP 4xx) never trip the breaker.
"""

import threading
import time

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised instead of calling a provider that is currently failing."""


class CircuitBreaker:
    def __init__(self, name, failure_threshold=5, reset_after_seconds=30.0, clock=time.monotonic):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_after_seconds = reset_after_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at = None
        self._trial_in_flight = False

    @property
    def state(self):
        with self._lock:
            return self._state()

    def _state(self):
        if self._opened_at is None:
            return CLOSED
        if self._clock() - self._opened_at >= self.reset_after_seconds:
            return HALF_OPEN
        return OPEN

    def before_call(self):
        """Raise ``CircuitOpenError`` unless a call may proceed now."""
        with self._lock:
            state = self._state()
            if state == OPEN or (state == HALF_OPEN and self._trial_in_flight):
                raise CircuitOpenError(self.name)
            if state == HALF_OPEN:
                self._trial_in_flight = True

    def record_success(self):
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._trial_in_flight = False

    def record_failure(self):
        with self._lock:
            self._trial_in_flight = False
            self._failures += 1
            if self._opened_at is not None or self._failures >= self.failure_threshold:
                self._opened_at = self._clock()

    def reset(self):
        self.record_success()
