"""Seller-scoped aggregate analytics; no buyer identities or financial actions."""

import asyncio
import json

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app import auth, llm, rate_limits
from app.db import session_factory
from app.errors import DomainError
from app.listing_workflow import caption_text
from app.models import Order, Product

router = APIRouter()


def summary(seller_id):
    with session_factory() as db:
        products = db.execute(
            select(Product.status, func.count(), func.sum(Product.stock))
            .where(Product.seller_id == seller_id)
            .group_by(Product.status)
        ).all()
        orders = db.execute(
            select(Order.status, func.count(), func.sum(Order.amount_minor))
            .where(Order.seller_id == seller_id)
            .group_by(Order.status)
        ).all()
    return {
        "currency": "USD",
        "products": [
            {"status": row[0], "count": row[1], "available_stock": int(row[2] or 0)}
            for row in products
        ],
        "orders": [
            {"status": row[0], "count": row[1], "gross_amount_minor": int(row[2] or 0)}
            for row in orders
        ],
        "notice": (
            "Gross order amounts are not net revenue; "
            "refunds and payment reviews require separate inspection."
        ),
    }


@router.get("/api/me/analytics")
def analytics(request: Request, response: Response):
    seller_id, _ = auth.seller_access(request)
    response.headers["Cache-Control"] = "no-store"
    return summary(seller_id)


class AnalystInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=600)


@router.post("/api/me/analytics/chat")
async def chat(body: AnalystInput, request: Request, response: Response):
    seller_id, _ = auth.seller_access(request, write=True)
    response.headers["Cache-Control"] = "no-store"
    message = caption_text(body.message)
    await asyncio.to_thread(rate_limits.consume_ip, str(seller_id), "studio_analyst", 20)
    facts = await asyncio.to_thread(summary, seller_id)
    try:
        async with asyncio.timeout(45):
            text = await llm.analytics_summary(message, json.dumps(facts))
    except TimeoutError:
        raise DomainError(
            "AI_UNAVAILABLE", "Analysis took too long. Use the dashboard totals.", 503
        ) from None
    return {"text": text}
