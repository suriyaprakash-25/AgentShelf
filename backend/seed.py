"""Idempotent demo seeding; never runs in production or resets live orders."""

import json
import os
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import session_factory
from app.models import Product, Seller, utcnow


def seed():
    """Load the fictional demo store and six explicitly synthetic catalog entries."""
    if get_settings().paypal_mode != "sandbox" or get_settings().app_env == "production":
        raise RuntimeError("Demo seeding is sandbox-only")
    source = Path(__file__).resolve().parents[1] / "seed" / "demo_store.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    # The fictional payee cannot receive sandbox payments; point the demo store at a
    # real PayPal sandbox business account so judges can complete a purchase.
    payee = os.environ.get("DEMO_SELLER_PAYPAL_EMAIL", "").strip()
    if payee:
        data["store"]["paypal_email"] = payee
    with session_factory() as db, db.begin():
        seller = db.scalar(select(Seller).where(Seller.store_slug == data["store"]["store_slug"]))
        if seller:
            if payee:
                seller.paypal_email = payee
            return
        seller = Seller(**data["store"], consent_at=utcnow(), status="active")
        db.add(seller)
        db.flush()
        for i, product in enumerate(data["products"], 1):
            db.add(Product(**product, seller_id=seller.id, short_no=i, status="live"))


if __name__ == "__main__":
    seed()
