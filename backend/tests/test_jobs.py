from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import select

from app import jobs
from app.db import session_factory
from app.models import Conversation, Job, utcnow

pytestmark = pytest.mark.integration


def enqueue():
    with session_factory() as db, db.begin():
        job = Job(kind="paypal_event", payload={"event_id": "fixture"})
        db.add(job)
        db.flush()
        return job.id


def test_unexpected_failure_rolls_back_and_eventually_dead_letters(db_clean, monkeypatch, caplog):
    job_id = enqueue()

    def fail_after_write(db, job):
        db.add(Conversation(whatsapp_phone="15555550101", state="test", context={}))
        db.flush()
        raise RuntimeError("private-address-and-provider-secret")

    monkeypatch.setattr(jobs, "process_paypal", fail_after_write)
    for attempt in range(1, 6):
        assert jobs.run_one() is True
        with session_factory() as db, db.begin():
            job = db.get(Job, job_id)
            assert job.attempts == attempt
            assert job.status == ("failed" if attempt == 5 else "queued")
            assert job.last_error == "JOB_HANDLER_FAILED"
            assert job.run_after > utcnow()
            assert db.scalar(select(Conversation)) is None
            job.run_after = utcnow() - timedelta(seconds=1)
    assert jobs.run_one() is False
    assert "private-address-and-provider-secret" not in caplog.text
    assert caplog.text.count("JOB_HANDLER_FAILED") == 5


def test_locked_job_is_skipped_and_other_job_can_complete(db_clean, monkeypatch):
    first, second = enqueue(), enqueue()
    entered, release = Event(), Event()
    processed = []

    def process(db, job):
        processed.append(job.id)
        if job.id == first:
            entered.set()
            assert release.wait(10), "Test failed to release the claimed job"

    monkeypatch.setattr(jobs, "process_paypal", process)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = pool.submit(jobs.run_one)
        try:
            assert entered.wait(10)
            assert pool.submit(jobs.run_one).result(timeout=10) is True
        finally:
            release.set()
        assert claimed.result(timeout=10) is True
    assert set(processed) == {first, second}
    assert len(processed) == 2
    with session_factory() as db:
        assert all(job.status == "done" for job in db.scalars(select(Job)))
    assert jobs.run_one() is False
