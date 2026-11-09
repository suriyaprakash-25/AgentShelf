# ADR-003: Read-through caching and read replicas for anonymous catalog reads

Status: ACCEPTED locally (November 9, 2026). Managed-replica behaviour on a hosting
provider is not accepted until a funded staging deployment exists.

## Decision

**What is cached** (`app/cache.py`, used by `app/storefront.py`):

| Read | TTL | Invalidation |
| --- | --- | --- |
| Search results (REST `/api/products` and MCP `search_products`) | `PUBLIC_CACHE_SECONDS` (default 10 s) | Seller product writes and listing publication in the same process |
| Store header and store page | Same | Same |
| `/api/stats` landing counts | 60 s (also `Cache-Control: public, max-age=60`) | Same |
| Model translations | 1 h, keyed by product, language and SHA-256 of the source text | An edited title or description changes the key |

**What is never cached:** sessions, quotes, orders, budgets, authentication, seller
dashboards and anything with personal data. Quotes and checkout always re-read the
primary under row locks, so a stale listing cannot change a price, over-reserve stock
or exceed a budget.

The cache is a bounded LRU (2,048 entries) with **single-flight** loading: concurrent
misses for one key run one query. A unit test asserts 16 threads cause one load.
Failed loads are never cached.

**Read replica:** `DATABASE_READ_URL` (optional) routes anonymous storefront reads to a
streaming replica through `db.read_session()`. When it is unset, reads use the primary
pool, so tests and single-database deployments are unchanged. `/healthz` reports the
replica separately. A lost replica is a degradation, not an outage.

## Trade-offs (Step 12)

* **In-process versus shared cache.** Each replica caches independently and converges
  within one TTL; there is no cross-replica invalidation. This was chosen over Redis to
  avoid a new stateful dependency at pilot scale. If staleness matters, move to Redis
  with pub/sub invalidation.
* **Replica lag.** Measured locally at about 2 ms. A buyer may briefly see a listing that
  just sold out. The quote step rejects it with `OUT_OF_STOCK`, so correctness is
  preserved.
* **Tests disable the cache** (`PUBLIC_CACHE_SECONDS=0` in `tests/conftest.py`) because
  integration tests assert read-after-write. Dedicated tests cover TTL, LRU,
  invalidation, single flight and a zero-query cached read (`tests/test_cache_and_resilience.py`,
  `tests/test_search_and_storefront.py`).

## Evidence

The `deploy/scale` stack showed the following:

* `pg_stat_replication` reports `streaming`.
* The replica holds four `agentshelf-read` connections; the primary holds none.
* The replica rejects writes (`read-only transaction`).
* Writes through the load balancer still succeed on the primary.
