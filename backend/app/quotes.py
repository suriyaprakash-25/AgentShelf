"""Catalog search and immutable, server-priced, single-product quotes."""

from datetime import timedelta

from sqlalchemy import and_, func, or_, select

from app.config import get_settings
from app.errors import DomainError
from app.guards import parse_id, safe_text
from app.models import AgentSession, Product, Quote, Seller, utcnow
from app.paypal import money

MAX_SEARCH_RESULTS = 10
MAX_QUERY_CHARS = 500
MAX_QUOTE_QTY = 100
QUOTE_TTL = timedelta(minutes=15)
SHIPPING_DESTINATIONS = frozenset({"US", "GB"})


def product_json(product, seller):
    """Expose bounded catalog data without seller account identifiers."""
    return {
        "product_id": str(product.id),
        "store_name": safe_text(seller.name),
        "title": safe_text(product.title),
        "description": safe_text(product.description),
        "price": money(product.price_minor),
        "currency": product.currency,
        "in_stock": product.stock > 0,
        "image_url": product.images[0] if product.images else None,
        "product_url": f"{get_settings().frontend_url}/s/{seller.store_slug}?product={product.id}",
    }


def ranked(statement, query, after_id=None):
    """Filter by the GIN-indexed vector and order by relevance, then ID for stability.

    The keyset cursor stays an opaque product ID: the server recomputes that product's
    rank for this query, so pages never overlap even though order is by relevance.
    """
    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank(Product.search_vector, tsquery)
    statement = statement.where(Product.search_vector.op("@@")(tsquery))
    if after_id:
        after_rank = (
            select(func.ts_rank(Product.search_vector, tsquery))
            .where(Product.id == after_id)
            .scalar_subquery()
        )
        statement = statement.where(
            or_(rank < after_rank, and_(rank == after_rank, Product.id > after_id))
        )
    return statement.order_by(rank.desc(), Product.id)


def search_products(
    db,
    query="",
    max_price_minor=None,
    currency="USD",
    ship_to_country=None,
    limit=5,
    store_slug=None,
    after=None,
):
    """Search indexed live products and exclude unsafe catalog entries."""
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_SEARCH_RESULTS
        or len(query) > MAX_QUERY_CHARS
    ):
        raise DomainError(
            "INVALID_SEARCH", "Search accepts 1-10 results and at most 500 characters."
        )
    statement = (
        select(Product, Seller)
        .join(Seller)
        .where(
            Product.status == "live",
            Product.stock > 0,
            Seller.status == "active",
            Seller.consent_at.is_not(None),
            Product.currency == currency,
        )
    )
    if max_price_minor is not None:
        statement = statement.where(Product.price_minor <= max_price_minor)
    if store_slug:
        statement = statement.where(Seller.store_slug == store_slug)
    if ship_to_country:
        statement = statement.where(Seller.shipping_rates.has_key(ship_to_country))  # noqa: W601
    after_id = parse_id(str(after)) if after else None
    if query.strip():
        statement = ranked(statement, query, after_id)
    else:
        if after_id:
            statement = statement.where(Product.id > after_id)
        statement = statement.order_by(Product.id)
    results = []
    for product, seller in db.execute(statement.limit(limit)):
        try:
            results.append(product_json(product, seller))
        except DomainError:
            continue
    return results


def get_quote(db, product_id, qty, ship_to_country, session_id):
    """Snapshot product price and fixed destination shipping for fifteen minutes."""
    if (
        isinstance(qty, bool)
        or not isinstance(qty, int)
        or not 1 <= qty <= MAX_QUOTE_QTY
        or ship_to_country not in SHIPPING_DESTINATIONS
    ):
        raise DomainError(
            "INVALID_QUOTE", "Choose 1-100 items and a supported destination (US or GB)."
        )
    session = db.get(AgentSession, parse_id(session_id))
    if not session:
        raise DomainError("SESSION_NOT_FOUND", "Start a buyer session first.", 404)
    product = db.get(Product, parse_id(product_id))
    if not product or product.status != "live" or product.stock < qty:
        raise DomainError(
            "OUT_OF_STOCK", "This product is unavailable in the requested quantity.", 409
        )
    seller = db.get(Seller, product.seller_id)
    if seller.status != "active" or not seller.consent_at:
        raise DomainError("STORE_UNAVAILABLE", "This store is not accepting orders.", 409)
    if ship_to_country == seller.country and seller.country == "IN":
        raise DomainError("DESTINATION_UNSUPPORTED", "This store accepts overseas orders only.")
    if session.currency != product.currency:
        raise DomainError("CURRENCY_MISMATCH", "Use a session in the product currency.")
    shipping = seller.shipping_rates.get(ship_to_country)
    if not isinstance(shipping, int) or isinstance(shipping, bool) or shipping < 0:
        raise DomainError("DESTINATION_UNSUPPORTED", "The seller has not configured shipping here.")
    safe_text(product.title)
    safe_text(product.description)
    quote = Quote(
        product_id=product.id,
        qty=qty,
        ship_to_country=ship_to_country,
        title=product.title,
        unit_minor=product.price_minor,
        item_total_minor=product.price_minor * qty,
        shipping_minor=shipping,
        total_minor=product.price_minor * qty + shipping,
        currency=product.currency,
        expires_at=utcnow() + QUOTE_TTL,
        agent_session_id=session.id,
    )
    db.add(quote)
    db.flush()
    return {
        "quote_id": str(quote.id),
        "item_total": money(quote.item_total_minor),
        "shipping": money(shipping),
        "total": money(quote.total_minor),
        "currency": quote.currency,
        "expires_at": quote.expires_at.isoformat(),
    }
