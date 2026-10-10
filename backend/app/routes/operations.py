"""Operator-only failures and payment correlation, with audited bounded retries."""

import uuid

from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select

from app import auth
from app.db import session_factory
from app.errors import DomainError
from app.models import Job, OpsAudit, Order, PaymentAdjustment, Seller, WorkerHeartbeat, utcnow

router = APIRouter()


def access(request, write=False):
    actor, _ = auth.seller_access(request, write=write)
    with session_factory() as db:
        if not db.get(Seller, actor).is_operator:
            raise DomainError("OPERATOR_REQUIRED", "Operator access is required.", 403)
    return actor


@router.get("/api/ops")
def overview(request: Request, response: Response):
    access(request)
    response.headers["Cache-Control"] = "no-store"
    with session_factory() as db:
        jobs = list(
            db.scalars(
                select(Job).where(Job.status == "failed").order_by(Job.run_after.desc()).limit(100)
            )
        )
        orders = list(
            db.scalars(
                select(Order)
                .where(Order.reconciliation_error.is_not(None))
                .order_by(Order.updated_at)
                .limit(100)
            )
        )
        workers = list(db.scalars(select(WorkerHeartbeat)))
        adjustments = db.scalars(
            select(PaymentAdjustment).order_by(PaymentAdjustment.created_at.desc()).limit(100)
        )
        return {
            "adjustments": [
                {
                    "order_id": str(a.order_id),
                    "resource_id": a.resource_id,
                    "kind": a.kind,
                    "status": a.status,
                    "amount_minor": a.amount_minor,
                }
                for a in adjustments
            ],
            "failed_total": db.scalar(
                select(func.count()).select_from(Job).where(Job.status == "failed")
            ),
            "failed_jobs": [
                {"id": str(j.id), "kind": j.kind, "attempts": j.attempts, "code": j.last_error}
                for j in jobs
            ],
            "orders": [
                {
                    "id": str(o.id),
                    "status": o.status,
                    "paypal_order_id": o.paypal_order_id,
                    "code": o.reconciliation_error,
                }
                for o in orders
            ],
            "workers": [
                {"name": w.name, "age_seconds": int((utcnow() - w.seen_at).total_seconds())}
                for w in workers
            ],
        }


@router.post("/api/ops/jobs/{job_id}/retry")
def retry(job_id: uuid.UUID, request: Request):
    actor = access(request, write=True)
    with session_factory() as db, db.begin():
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job:
            raise DomainError("JOB_NOT_FOUND", "This job is unavailable.", 404)
        if job.status != "failed":
            raise DomainError("JOB_NOT_FAILED", "Only failed jobs can be retried.", 409)
        job.status, job.attempts, job.last_error, job.run_after = "queued", 0, None, utcnow()
        db.add(OpsAudit(actor_id=actor, action="retry_job", resource_id=str(job.id)))
    return {"status": "queued"}
