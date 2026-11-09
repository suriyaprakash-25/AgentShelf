"""Workers are woken by committed queue changes, never by uncommitted or finished jobs."""

import time

import pytest

from app.db import session_factory
from app.job_signals import JobListener
from app.models import Job, utcnow

pytestmark = pytest.mark.integration


def test_committed_queued_job_wakes_listener_promptly(db_clean):
    listener = JobListener(db_clean.url)
    try:
        assert listener.wait(0.2) is False  # Idle queue: times out quietly.
        with session_factory() as db, db.begin():
            job = Job(kind="whatsapp_send", payload={"phone": "x", "text": "y"})
            db.add(job)
            db.flush()
            job_id = job.id
        started = time.perf_counter()
        assert listener.wait(5) is True
        assert time.perf_counter() - started < 1.0
        with session_factory() as db, db.begin():
            db.get(Job, job_id).status = "done"  # Finished work signals nothing.
        assert listener.wait(0.3) is False
        with session_factory() as db, db.begin():
            retried = db.get(Job, job_id)
            retried.status, retried.run_after = "queued", utcnow()  # Operator retry.
        assert listener.wait(5) is True
    finally:
        listener.close()


def test_rolled_back_job_sends_no_signal(db_clean):
    listener = JobListener(db_clean.url)
    try:
        listener.wait(0.05)
        with session_factory() as db:
            db.begin()
            db.add(Job(kind="whatsapp_send", payload={}))
            db.flush()
            db.rollback()
        assert listener.wait(0.3) is False
    finally:
        listener.close()
