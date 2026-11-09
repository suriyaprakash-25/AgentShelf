"""Public, anonymous storefront reads shared by REST and MCP.

These reads tolerate seconds of staleness, so they use the read pool (a replica when
configured) and the in-process TTL cache. Anything that prices, reserves or charges
goes through ``quotes``/``orders`` on the primary under row locks instead.
"""

import hashlib
import uuid

from sqlalchemy import func, select

from app import cache, llm, quotes
from app.config import get_settings
from app.db import read_session, session_factory
from app.errors import DomainError
from app.models import AgentSession, Product, Seller

STORE_PAGE_SIZE = 10
STATS_TTL_SECONDS = 60
TRANSLATION_TTL_SECONDS = 3600


def _active_store(db, slug):
    seller = db.scalar(select(Seller).where(Seller.store_slug == slug, Seller.status == "active"))
    if not seller:
        raise DomainError("STORE_NOT_FOUND", "This store is unavailable.", 404)
    return seller


def search(
    query="",
    max_price_minor=None,
    currency="USD",
    ship_to_country=None,
    limit=5,
    store_slug=None,
    after=None,
):
    """Relevance-ranked live products; identical arguments share one cached result."""

    def load():
        with read_session() as db:
            return quotes.search_products(
                db,
                query=query,
                max_price_minor=max_price_minor,
                currency=currency,
                ship_to_country=ship_to_country,
                limit=limit,
                store_slug=store_slug,
                after=after,
            )

    key = ("search", query, max_price_minor, currency, ship_to_country, limit, store_slug, after)
    return cache.cached(cache.CATALOG, key, load)


def page(items, limit):
    """Keyset cursor: the last product ID of a full page; None when exhausted."""
    return {
        "products": items,
        "next_cursor": items[-1]["product_id"] if len(items) == limit else None,
    }


def store_page(slug, after=None):
    """Public store information with no merchant account details."""
    settings = get_settings()

    def load():
        with read_session() as db:
            seller = _active_store(db, slug)
            return {
                "name": seller.name,
                "slug": seller.store_slug,
                "country": seller.country,
                "currency": seller.currency,
            }

    header = cache.cached(cache.CATALOG, ("store", slug), load)
    items = search(limit=STORE_PAGE_SIZE, store_slug=slug, after=after)
    return {
        **header,
        "mcp_url": settings.public_api_url + "/mcp",
        **page(items, STORE_PAGE_SIZE),
    }


def store_schema(slug):
    """schema.org ItemList JSON-LD for a public merchant storefront."""
    store = store_page(slug)
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": store["name"],
        "url": f"{get_settings().frontend_url}/s/{store['slug']}",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": idx + 1,
                "item": {
                    "@type": "Product",
                    "sku": item["product_id"],
                    "name": item["title"],
                    "description": item["description"],
                    "offers": {
                        "@type": "Offer",
                        "price": item["price"],
                        "priceCurrency": item["currency"],
                        "availability": (
                            "https://schema.org/InStock"
                            if item["in_stock"]
                            else "https://schema.org/OutOfStock"
                        ),
                    },
                },
            }
            for idx, item in enumerate(store["products"])
        ],
    }


def platform_stats():
    """Counts measured from the catalog itself; the landing page shows nothing invented."""

    def load():
        with read_session() as db:
            active = (Seller.status == "active", Seller.consent_at.is_not(None))
            sellers = db.scalar(select(func.count()).select_from(Seller).where(*active))
            countries = db.scalar(select(func.count(func.distinct(Seller.country))).where(*active))
            products = db.scalar(
                select(func.count())
                .select_from(Product)
                .join(Seller)
                .where(Product.status == "live", Product.stock > 0, *active)
            )
        return {"sellers": sellers, "live_products": products, "seller_countries": countries}

    return cache.cached(cache.STATS, ("platform",), load, STATS_TTL_SECONDS)


def translated_product(product_id: uuid.UUID, lang: str):
    """Translate copy while keeping server-side price, currency and stock authoritative."""
    with read_session() as db:
        row = db.execute(
            select(Product, Seller)
            .join(Seller, Seller.id == Product.seller_id)
            .where(Product.id == product_id, Product.status == "live", Seller.status == "active")
        ).first()
        if not row:
            raise DomainError("PRODUCT_NOT_FOUND", "Product is unavailable.", 404)
        product, seller = row
        serialized = quotes.product_json(product, seller)
        title, description = product.title, product.description
    # Paid model calls are cached per exact source text, so an edit invalidates naturally.
    fingerprint = hashlib.sha256(f"{title}\x00{description}".encode()).hexdigest()
    translated = cache.cached(
        cache.TRANSLATIONS,
        (str(product_id), lang, fingerprint),
        lambda: llm.translate_listing(title, description, lang),
        TRANSLATION_TTL_SECONDS,
    )
    return {
        **serialized,
        "title": translated["title"],
        "description": translated["description"],
        "language": translated["language"],
        "source_title": title,
    }


def create_buyer_session(budget_minor, currency):
    """A buyer session; its random identifier acts as a scoped capability."""
    with session_factory() as db, db.begin():
        session = AgentSession(budget_minor=budget_minor, currency=currency)
        db.add(session)
        db.flush()
        return {
            "session_id": str(session.id),
            "budget_minor": session.budget_minor,
            "currency": session.currency,
        }
