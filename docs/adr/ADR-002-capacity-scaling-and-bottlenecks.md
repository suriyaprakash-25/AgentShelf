# ADR-002: Capacity estimate, horizontal scaling and known bottlenecks

Status: ACCEPTED for local verification (November 9, 2026). Hosted staging capacity
is **not** accepted: no funded deployment or provider credentials exist yet.

## Context

The roadmap sets latency targets (search p95 < 1 s at 1,000 products; draft p95
< 20 s) but no traffic estimate. The evaluation found throughput collapsing under
concurrency and nothing that would let the service scale out.

## Estimate (design envelope, not a measurement)

| Quantity | Pilot (judging) | Design envelope | Basis |
| --- | --- | --- | --- |
| Sellers / live products | 2 / about 11 | 1,000 / 50,000 | Hackathon pilot to a regional marketplace |
| Catalog reads (search, store, MCP) | < 5 req/s | 50 req/s peak | Agents poll search; humans browse |
| Quotes / checkouts | < 1/s | 5 / 1 per s | Most searches never quote |
| Webhooks + jobs | < 1/s | 5/s | About three events per paid order, plus drafts |
| Listing drafts | Few per hour | 30/h per seller (enforced quota) | Roadmap AI design limit |
| Product rows | KB | about 100 MB, plus tsvector and GIN index | 2 KB per row including JSONB and vector |
| Orders and events / year | Hundreds | about 5 GB | 1 order/s at peak is far above the envelope |
| Postgres connections | about 30 | 2 web × 2 workers × (10 + 10) + workers ≤ 120 of 200 | Bounded per pool (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`) |

The envelope fits one Postgres primary with one streaming replica. Sharding is not
needed and would add risk to the locking invariants (stock, budget, capture).

## Decision

* **Stateless web tier.** Correctness state lives in Postgres: quotas, sessions, jobs
  and reservations. MCP runs in Streamable HTTP **stateless** mode
  (`app/main.py: mcp_transport`), so any worker or replica can serve any request.
* **Scale inside a container** with `WEB_CONCURRENCY` uvicorn workers, and **across
  containers** behind a round-robin, least-connections load balancer. The verified
  reference is `deploy/scale/` (nginx, two web replicas, two workers, primary and replica).
* **Workers scale independently.** `FOR UPDATE SKIP LOCKED` claims jobs without
  double processing; LISTEN/NOTIFY wakes idle workers (ADR-005).
* **Trusted proxy hops** configure client identity behind the load balancer (ADR-004).

## Evidence (local, Windows + Docker Desktop; relative, not production numbers)

| Probe | Before refactor | After |
| --- | --- | --- |
| `GET /api/products?limit=10`, concurrency 100, 1 worker | 29 req/s, p95 9.1 s, 1 error | 151 req/s, p95 2.8 s, 0 errors |
| `GET /api/stores/{slug}`, concurrency 50, 1 worker | 28 req/s, p95 4.2 s | 117 req/s, p95 1.2 s |
| Load balancer spread (nginx → 2 replicas) | Not possible (stateful MCP) | 305 / 305 requests; 4 MCP sessions succeeded across replicas |
| Replica killed during a 2,000-request burst | n/a | 2,000 × 200, 0 errors (nginx retried idempotent requests) |
| Landing-page JavaScript preloaded | about 370 KB gzipped (grid and Sentry included) | about 95 KB gzipped (React and entry chunk only) |

Requests/s through the Docker stack are lower than direct host numbers. Every request
crosses Docker Desktop's Windows port proxy, and all containers share one VM, so that
stack demonstrates distribution and failover, not capacity.

## Bottlenecks that remain (Step 11)

1. **Single primary for writes.** Quotes, checkouts and quotas all write to one primary.
   This is fine for the envelope. Next steps would be quota counters in Redis and
   PgBouncer in transaction mode.
2. **Synchronous handlers in a thread pool.** The thread count bounds concurrency per
   worker. Mitigations: more workers or replicas, short deadlines (ADR-005) and caching.
3. **Provider calls under row locks** during capture. This is deliberate: it serializes
   capture per order. It affects one order row, not global throughput, and is bounded by
   PayPal timeouts and the circuit breaker.
4. **Offset pagination** in seller pages (maximum 100 per page) is fine at thousands of
   rows per seller. The public catalog already uses keyset cursors.
5. **Quota row hot spot** for one very busy IP or session. Each request is now a single
   atomic upsert round trip; Redis would remove it from Postgres entirely.
