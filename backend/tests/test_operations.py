import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import email
from app.db import session_factory
from app.main import create_app
from app.models import Job, OpsAudit, Seller, WorkerHeartbeat, utcnow
from tests.test_sellers import ORIGIN, login

pytestmark = pytest.mark.integration


def test_operator_privilege_csrf_retry_audit_and_payload_privacy(db_clean, monkeypatch):
    delivered = []
    monkeypatch.setattr(email, "require_ready", lambda: None)
    monkeypatch.setattr(email, "send_login", lambda address, link, key: delivered.append(link))
    with TestClient(create_app(), base_url="https://testserver") as client:
        assert client.get("/api/ops").status_code == 401
        me, headers, _ = login(client, delivered)
        assert client.get("/api/ops").status_code == 403
        with session_factory() as db, db.begin():
            db.get(Seller, uuid.UUID(me["id"])).is_operator = True
            job = Job(
                kind="whatsapp_send",
                status="failed",
                attempts=5,
                last_error="WHATSAPP_UNAVAILABLE",
                payload={"phone": "private-phone", "text": "private-address"},
            )
            db.add(job)
            db.add(WorkerHeartbeat(name="fixture", seen_at=utcnow()))
            db.flush()
            job_id = job.id
        overview = client.get("/api/ops")
        assert overview.status_code == 200 and overview.headers["cache-control"] == "no-store"
        assert "private-phone" not in overview.text and "private-address" not in overview.text
        assert (
            overview.json()["failed_total"] == 1
            and overview.json()["workers"][0]["age_seconds"] < 10
        )
        path = f"/api/ops/jobs/{job_id}/retry"
        assert client.post(path, headers=ORIGIN).status_code == 403
        assert client.post(path, headers=headers).status_code == 200
        assert client.post(path, headers=headers).status_code == 409
        with session_factory() as db:
            job = db.get(Job, job_id)
            assert job.status == "queued" and job.attempts == 0 and job.last_error is None
            assert db.scalar(select(OpsAudit)).resource_id == str(job_id)
