"""Run the durable job worker separately from the API.

Idle workers block on Postgres LISTEN/NOTIFY instead of polling every half second;
they still wake at least every ``IDLE_WAIT_SECONDS`` (or when a delayed job is due)
so reconciliation scans, heartbeats and lost notifications are always covered.
Several workers can run at once: jobs are claimed with ``FOR UPDATE SKIP LOCKED``.
"""

import logging
import time

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.db import get_engine, session_factory
from app.job_signals import JobListener
from app.jobs import run_one
from app.models import Job, WorkerHeartbeat, utcnow
from app.observability import setup
from app.reconciliation import schedule

logger = logging.getLogger("agentshelf")

SCAN_INTERVAL_SECONDS = 5
CLEANUP_INTERVAL_SECONDS = 3600
IDLE_WAIT_SECONDS = SCAN_INTERVAL_SECONDS
MIN_WAIT_SECONDS = 0.05


def heartbeat(name="main"):
    with session_factory() as db, db.begin():
        db.execute(
            insert(WorkerHeartbeat)
            .values(name=name, seen_at=utcnow())
            .on_conflict_do_update(
                index_elements=[WorkerHeartbeat.name], set_={"seen_at": utcnow()}
            )
        )


def seconds_until_next_job(cap):
    """How long the queue can stay idle: until the earliest delayed job, at most ``cap``."""
    with session_factory() as db:
        due = db.scalar(select(func.min(Job.run_after)).where(Job.status == "queued"))
    if due is None:
        return cap
    return max(MIN_WAIT_SECONDS, min(cap, (due - utcnow()).total_seconds()))


def main():
    """Process until interrupted; let unexpected failures surface for supervision."""
    setup()
    listener = JobListener(get_engine().url)
    next_scan = 0.0
    next_cleanup = 0.0
    try:
        while True:
            now = time.monotonic()
            if now >= next_cleanup:
                from maintenance import cleanup_expired

                cleanup_expired()
                next_cleanup = now + CLEANUP_INTERVAL_SECONDS
            if now >= next_scan:
                schedule()
                heartbeat()
                next_scan = now + SCAN_INTERVAL_SECONDS
            if run_one():
                continue
            cap = max(MIN_WAIT_SECONDS, min(IDLE_WAIT_SECONDS, next_scan - time.monotonic()))
            listener.wait(seconds_until_next_job(cap))
    finally:
        listener.close()


if __name__ == "__main__":
    main()
