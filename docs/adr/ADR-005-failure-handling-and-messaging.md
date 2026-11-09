# ADR-005: Bounded failure, provider isolation and push-signalled messaging

Status: ACCEPTED locally (November 9, 2026). Hosted provider outage drills remain open.

## Problems found

With the database container paused, `/healthz`, search and `/mcp` hung for more than
40 s with no fail-fast. PayPal calls had a 30 s timeout, no breaker, and were made while
holding database row locks. Idle workers polled the jobs table every 0.5 s.

## Decision

| Failure | Mechanism | Where |
| --- | --- | --- |
| Lost network to Postgres | `tcp_user_timeout` (10 s), TCP keepalives, 5 s connect timeout | `app/db.py: connect_args` |
| Slow query | Server-side `statement_timeout` (15 s) and `idle_in_transaction_session_timeout` (120 s) | Same; asserted against the real server |
| Hung dependency that accepts TCP but never answers | Per-request deadline: 15 s, or 75 s for provider routes. The client gets a 503 while the uncancellable thread finishes and its body is drained. A request abandoned during its quota check never starts its handler. | `app/http_edge.py: within_deadline` |
| Health under a hung database | Async probe with a 3 s bound, so load balancers stop routing quickly | `routes/public.py: healthz` |
| Pool exhaustion | `pool_timeout` 5 s maps to a 503 with `Retry-After` | `db.py`, `http_edge.error_response` |
| PayPal outage | Circuit breaker: 5 transport or 5xx failures open it for 30 s, then one half-open trial. A 4xx never trips it. One retry on connect errors only, which is safe because nothing reached PayPal and PayPal-Request-Id makes POSTs idempotent. Timeout is 15 s read, 5 s connect. | `app/resilience.py`, `paypal.send` |
| Uncertain payment | Unchanged: approved orders stay reserved and the reconciler and queue retry. An open breaker surfaces as the existing `PAYPAL_UNAVAILABLE`. | `orders.py`, `reconciliation.py` |

**Messaging (Step 8):** the jobs table remains the durable source of truth: an inbox and
outbox with savepoints, bounded exponential backoff, dedupe keys and compensation. A
trigger (`jobs_notify`) issues `pg_notify` when a job becomes queued, which happens at
commit, so rolled-back work never signals. Workers block on LISTEN until the next
delayed job is due, or for at most 5 s, instead of polling every 0.5 s. A lost
notification only costs a timed poll.

## Evidence (local)

| Scenario | Before | After |
| --- | --- | --- |
| Database hung (`docker pause`) | `/healthz`, search and `/mcp` hang for more than 40 s | `/healthz` 503 in 3.1 s; reads 503 in 5.1–15.1 s; session POST 503 in 5.1 s; static 200 in 0.1 s; recovers on the first check; no late write |
| Database partitioned (iptables DROP) | Not tested | `/healthz` 503 in 3.1 s; other routes 503 in 5.1–15.1 s; recovers on the first check |
| Committed job wakes an idle worker | 0.5 s polling | Under 1 s, asserted; rolled-back and finished jobs send no signal |
| Breaker open, then half-open, then closed; 4xx ignored; open breaker makes no network call | n/a | `tests/test_cache_and_resilience.py` |

## Trade-offs

* An abandoned handler keeps its worker thread until the dependency answers. The
  deadline protects clients and the load balancer, not thread capacity. That is
  bounded by pool size and replicas.
* The breaker is per process, so replicas trip independently. That is acceptable: each
  replica isolates its own threads.
