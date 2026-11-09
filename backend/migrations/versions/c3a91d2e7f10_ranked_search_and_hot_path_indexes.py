"""ranked search vector and hot-path indexes

Replaces the expression GIN index with a stored, weighted tsvector so search can rank
by relevance without re-parsing text per row, and indexes the foreign keys and filters
used by budget checks, seller pages, operator review and paid notifications.

Revision ID: c3a91d2e7f10
Revises: bfa937649fe0
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3a91d2e7f10"
down_revision = "bfa937649fe0"
branch_labels = None
depends_on = None

SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english'::regconfig, (title)::text), 'A') || "
    "setweight(to_tsvector('english'::regconfig, (description)::text), 'B')"
)
LEGACY_SEARCH_SQL = (
    "to_tsvector('english'::regconfig, (title::text || ' '::text) || description::text)"
)


def upgrade():
    op.add_column(
        "products",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_SQL, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_products_search_vector", "products", ["search_vector"], postgresql_using="gin"
    )
    op.drop_index("ix_products_search", table_name="products")
    op.create_index("ix_quotes_agent_session_id", "quotes", ["agent_session_id"])
    op.create_index("ix_quotes_product_id", "quotes", ["product_id"])
    op.create_index("ix_orders_seller_created", "orders", ["seller_id", "created_at"])
    op.create_index(
        "ix_orders_reconciliation_open",
        "orders",
        ["updated_at"],
        postgresql_where=sa.text("reconciliation_error IS NOT NULL"),
    )
    op.create_index("ix_order_events_order_id", "order_events", ["order_id"])
    op.create_index(
        "ix_webhook_events_resource_type", "webhook_events", ["resource_id", "event_type"]
    )


def downgrade():
    op.drop_index("ix_webhook_events_resource_type", table_name="webhook_events")
    op.drop_index("ix_order_events_order_id", table_name="order_events")
    op.drop_index("ix_orders_reconciliation_open", table_name="orders")
    op.drop_index("ix_orders_seller_created", table_name="orders")
    op.drop_index("ix_quotes_product_id", table_name="quotes")
    op.drop_index("ix_quotes_agent_session_id", table_name="quotes")
    op.create_index(
        "ix_products_search", "products", [sa.text(LEGACY_SEARCH_SQL)], postgresql_using="gin"
    )
    op.drop_index("ix_products_search_vector", table_name="products")
    op.drop_column("products", "search_vector")
