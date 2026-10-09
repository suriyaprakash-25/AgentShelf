"""Roadmap entities and database-enforced integrity constraints."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    """Return a timezone-aware timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Seller(Base):
    __tablename__ = "sellers"
    __table_args__ = (
        CheckConstraint("status IN ('onboarding','active','suspended')"),
        UniqueConstraint("email", name="uq_sellers_email"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    whatsapp_phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(254))
    country: Mapped[str] = mapped_column(String(2))
    paypal_email: Mapped[str] = mapped_column(String(254))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    store_slug: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="onboarding")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipping_rates: Mapped[dict] = mapped_column(JSONB, default=dict)
    live_eligible: Mapped[bool] = mapped_column(default=False)
    paypal_merchant_id: Mapped[str | None] = mapped_column(String(64))


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("seller_id", "short_no"),
        CheckConstraint("price_minor > 0 AND stock >= 0"),
        CheckConstraint("status IN ('draft','live','archived')"),
        Index("ix_products_seller_status", "seller_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sellers.id"))
    short_no: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(600))
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    price_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    stock: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    images: Mapped[list] = mapped_column(JSONB, default=list)
    source_message_id: Mapped[str | None] = mapped_column(String(200), unique=True)


Product.__table__.append_constraint(
    Index(
        "ix_products_search",
        text("to_tsvector('english'::regconfig, (title::text || ' '::text) || description::text)"),
        postgresql_using="gin",
    )
)


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (CheckConstraint("budget_minor >= 0 AND spent_minor >= 0"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    budget_minor: Mapped[int] = mapped_column(BigInteger)
    spent_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint("qty > 0 AND unit_minor > 0 AND shipping_minor >= 0"),
        CheckConstraint("item_total_minor = unit_minor * qty"),
        CheckConstraint("total_minor = item_total_minor + shipping_minor"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[int] = mapped_column(Integer)
    ship_to_country: Mapped[str] = mapped_column(String(2))
    title: Mapped[str] = mapped_column(String(80))
    unit_minor: Mapped[int] = mapped_column(BigInteger)
    item_total_minor: Mapped[int] = mapped_column(BigInteger)
    shipping_minor: Mapped[int] = mapped_column(BigInteger)
    total_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    agent_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_sessions.id"))


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount_minor > 0"),
        CheckConstraint(
            "status IN ('checkout_created','approved','paid','shipped','capture_pending',"
            "'failed','expired','cancelled','refunded')"
        ),
        Index("ix_orders_status_reservation", "status", "reserved_until"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quotes.id"), unique=True)
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sellers.id"))
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="checkout_created")
    approval_url: Mapped[str | None] = mapped_column(Text)
    capture_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    ship_to: Mapped[dict | None] = mapped_column(JSONB)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    reserved_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    carrier: Mapped[str | None] = mapped_column(String(100))
    tracking_number: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    type: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    paypal_event_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(100))
    verified: Mapped[bool]
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSONB)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','failed')"),
        Index("ix_jobs_poll", "status", "run_after"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(60))
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_error: Mapped[str | None] = mapped_column(Text)


class Conversation(Base):
    __tablename__ = "conversations"
    whatsapp_phone: Mapped[str] = mapped_column(String(20), primary_key=True)
    state: Mapped[str] = mapped_column(String(40))
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=func.now()
    )


class LoginChallenge(Base):
    __tablename__ = "login_challenges"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    profile: Mapped[dict | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SellerSession(Base):
    __tablename__ = "seller_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sellers.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    used: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
