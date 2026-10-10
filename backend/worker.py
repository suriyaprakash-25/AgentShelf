"""Run the durable job worker separately from the API."""

import logging
import time

from sqlalchemy.dialects.postgresql import insert

from app.db import session_factory
from app.jobs import run_one
from app.models import WorkerHeartbeat, utcnow
from app.observability import setup
from app.reconciliation import schedule

logger = logging.getLogger("agentshelf")


def main():
    """Poll until interrupted; let unexpected failures surface for supervision."""
    setup()
    next_scan = 0
    next_cleanup = 0
    while True:
        if time.monotonic() >= next_cleanup:
            from maintenance import cleanup_expired

            cleanup_expired()
            next_cleanup = time.monotonic() + 3600
        if time.monotonic() >= next_scan:
            schedule()
            with session_factory() as db, db.begin():
                db.execute(
                    insert(WorkerHeartbeat)
                    .values(name="main", seen_at=utcnow())
                    .on_conflict_do_update(
                        index_elements=[WorkerHeartbeat.name], set_={"seen_at": utcnow()}
                    )
                )
            next_scan = time.monotonic() + 5
        if not run_one():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
