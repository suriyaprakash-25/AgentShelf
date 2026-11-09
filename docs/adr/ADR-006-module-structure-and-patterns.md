# ADR-006: Module boundaries, SOLID and the design patterns in use

Status: ACCEPTED (November 9, 2026).

## Refactorings applied

| Smell (evaluation) | Refactoring | Result |
| --- | --- | --- |
| Business rules in seller route handlers (against AGENTS.md) | Extract Class / Move Method | `app/seller_catalog.py`; `routes/sellers.py` only authenticates, validates shapes and delegates |
| 442-line `main.py` mixing middleware, rules and wiring | Extract Module | `main.py` is the composition root; `http_edge.py` holds middleware; `routes/public.py` holds handlers; `storefront.py` holds public reads |
| `if anthropic … else gemini` repeated in 5 functions | Replace Conditional with Polymorphism; Introduce Interface | `ai_providers.ModelProvider` Protocol with `AnthropicProvider` and `GeminiProvider`, plus a factory `select()`; `llm.py` keeps the policy |
| `if media_backend == "local"` repeated in 4 functions | Same | `storage.MediaStore` with `LocalMediaStore` and `R2MediaStore`, plus `media_store()` |
| `if/elif` job dispatch | Replace Conditional with Registry | `jobs.HANDLERS`, with `dispatch`, `schedule_retry`, `compensate` and `claim` extracted |
| Payment-match check copied 3 times | Extract Method | `orders.matches_quote` and `require_approved_match`; `create_checkout` split into `reserve` and `ensure_provider_order` |
| Quota logic copied 4 times | Extract Method | `rate_limits.consume`, `enforce` and the `RatePolicy` value objects |
| Magic numbers | Replace Magic Number with Named Constant | Quotas, TTLs, limits, attempts, backoff, timeouts and page sizes |
| 1,508-line `App.tsx` | Extract Module, plus lazy routes | `src/pages/{Home,StorePage,Playground,Receipt}.tsx`; `App.tsx` is the router (117 lines) |

## Patterns

| Pattern | Use |
| --- | --- |
| Strategy + Factory | AI providers and media stores, selected from configuration at call time |
| Facade | `llm.*`, `storage.*` and `paypal.*`; the only modules that talk to vendors |
| Registry (open for extension) | Job handlers |
| State machine (table-driven) | `orders.TRANSITIONS` |
| Circuit Breaker | `resilience.CircuitBreaker` around PayPal |
| Cache-aside with single flight | `cache.TTLCache` |
| Transactional outbox/inbox + Observer | Jobs table with LISTEN/NOTIFY wake-ups |
| Idempotency key | PayPal-Request-Id; dedupe keys |
| Singleton (process-scoped) | `lru_cache` settings and engines; shared cache instance |
| Chain of Responsibility | ASGI middleware stack |
| Value Object | `RatePolicy`; provider `TextPart`, `ImagePart` and `AudioPart` |

## SOLID notes

* **SRP:** routes handle HTTP; services hold rules; providers handle transport.
* **OCP:** a new model vendor, media backend or job kind is one class or registry entry.
* **LSP:** every provider and store honours the same Protocol, enforced by a test that
  checks every registered provider implements the interface.
* **ISP:** `ModelProvider` has three methods; `MediaStore` has four.
* **DIP:** policy depends on Protocols resolved by factories, not on vendor SDKs.
  Remaining gap: services still obtain sessions from `db.session_factory()` instead of
  injected units of work, and tests substitute through module attributes. A full
  repository and unit-of-work layer was judged not worth the churn and risk to the
  locking code at this stage.
