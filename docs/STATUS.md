# AgentShelf status and evidence

Updated October 10, 2026. **Must workflow implementations substantially expanded; production and pilot acceptance remain open.**
Checkout: `D:\PayPal\PayPal AI Hackathon\AgentShelf`, branch `feat/foundations`.
The unchanged source PDF has SHA-256
`69EA49D89F45A4752E72B90FCBA2C8BFFFDDFDD076523F00559BC4F5EF19D8A4`.
`COMPLETION_REPORT.md` is the historical October 9 audit of 113 source checkboxes,
12 Must requirements, 14 stories and three gates. Its counts are historical;
they must not be read as a current implementation assessment.

## Current local evidence

| Check | Result | Evidence boundary |
| --- | --- | --- |
| Full backend suite | 163 passed, 88.67 seconds | Python 3.12, real local PostgreSQL 18.4; external services controlled in tests |
| Alembic upgrade/downgrade/upgrade and schema drift | Passed | Dedicated local migration database |
| Dependency audit | No known backend/frontend vulnerabilities | Installed dependency snapshot |
| Frontend lint, format and production build | Passed after AG Studio integration | No staging performance claim |
| Browser suite | Five tests passed, 14.8 seconds | Actual API catalog/mobile plus controlled listing/SSE/Studio browser fixtures |
| PostgreSQL 17 container payment/worker checks | 24 passed, 11.65 seconds | Orders, capture, webhooks, jobs and reconciliation; controlled providers |
| Docker build/runtime | Built; UID 10001, PG17 migrations/no drift, DB health, six products and frontend/security headers | Isolated local container; no hosted deployment |
| Backup and restore | Actual dump restored catalog stock, session budget and quote amount | Separate random empty loopback test DB; no managed-provider backup proof |
| Catalog scale | 1,000-product pagination/FTS check passed, local p95 under one second | Synthetic catalog, local DB, no staging load claim |
| Stock/budget/capture concurrency | Passed | Real DB locks, controlled PayPal responses |
| Real MCP client | Four tools discovered and invoked over an actual socket | Controlled Anthropic and PayPal responses in agent tests |

## Must implementation versus acceptance

| ID | Implemented locally | Remaining acceptance |
| --- | --- | --- |
| M1 | Email verification, consent, hashed sessions; WhatsApp onboarding binds a phone only after email verification | Actual Meta/email delivery and staged S1 timing |
| M2 | Private processed photos, R2 adapter, asynchronous vision drafts, review/history, explicit seller price/stock and publication in web/WhatsApp | Real R2/Anthropic; five-photo spike, 20-product quality and image-instruction/PII evaluation, S2 latency |
| M3 | Owned product edits/archive/publication, seller lists; public keyset pagination and photos | Real WhatsApp edits, staged S3 latency |
| M4 | Official SDK Streamable HTTP tools and buyer agent using actual MCP transport | Inspector and independent external-client purchase/status on staging |
| M5 | Direct-payee candidate, stable IDs, locked stock/budget and durable capture intent | ADR-001 receiving permissions, real approval/capture/refresh |
| M6 | Signature verification, durable deduplicated inbox, bounded worker retries and payment reconciliation | Actual signed sandbox events, timing/outages and expiry-policy decision |
| M7 | Verified capture-event paid notification; approved-template adapter | Meta template approval/window policy and actual alert within ten seconds |
| M8 | Owned web/API and WhatsApp tracking with stable PayPal tracker verification | Real sandbox tracking permissions and provider acceptance |
| M9 | SSE buyer chat, visible tool trace, server-bound country/session, bounded calls and explicit quote approval | Real model 15-task evaluation, deployed money-path browser test |
| M10 | Secure auth, catalog/order grids, filters/sort/CSV, fulfilment and lazy-loaded AG Studio analytics | Studio custom widget/theme and real framework analyst locally implemented; deployed licence, real model and staged S6 pending |
| M11 | Same-origin container, API/worker/Postgres Render blueprint, CI, maintenance tools | Remote CI, funded HTTPS deployment, managed backups and independent five-minute purchase |
| M12 | Shared DB quotas, ownership/CSRF, caption guards, minimized logs/webhooks, bounded images, Sentry scrubbing | Complete deployed red-team/image evaluation, proxy/CSP/accessibility and secret-history scan |

All 14 staged stories and Gate 1/2/3 remain unsigned. Local component tests do not
establish staged Must acceptance. No real provider payment, message, model request,
public deployment, live merchant acceptance or hackathon submission is claimed.

## Operations and payment safety

Operators can inspect failed jobs, worker heartbeat ages, correlated payment reviews,
refunds/disputes and retry failures with CSRF and audit records. Role grants are CLI-only.
Verified completed partial/full refunds are deduplicated and displayed without automatic
restocking or relaxing the buyer's cumulative budget. Dispute/reversal states require
human PayPal review; there is no automatic refund or settlement decision.

Reconciliation re-reads known PayPal orders and retries approved captures with stable
IDs. Uncertain creation/capture keeps stock and budget reserved. Only provider VOIDED
proof releases an abandoned checkout. This deliberately does not satisfy the source's
unconditional 15-minute release requirement yet: resolve the provider-expiry policy
through ADR-001 before release. Unknown create IDs need manual correlation.

WhatsApp delivery is at least once across a crash after sending. Multi-photo messages
are grouped up to four images with a short debounce; duplicates use stable IDs.
Hourly cleanup removes expired auth records/stale quota buckets and clears old chat
text after 30 days while preserving payment/budget records. Unreferenced media cleanup,
historical inbox/address retention audit and managed backup retention remain open.

## Deployment and release boundaries

API serves the built frontend from one HTTPS origin; worker uses the same database,
private R2 bucket and provider/email secrets. Docker now builds successfully. The non-root packaged API starts against an isolated
PostgreSQL 17 container and serves the catalog/UI with security headers; migrations
report no drift. The full native suite uses PostgreSQL 18.4. Remote CI remains unverified.
The seller bundle is approximately 1 MB and optional Studio approximately 4.36 MB before compression; Lighthouse/LCP/accessibility targets are unverified.
AG Studio 3.0.0 is integrated with a custom shop widget, theme and Studio Agent Framework analyst.
The actual component/analyst browser flow passes using controlled aggregate/AI responses.
It loads on demand; production activation requires VITE_AG_STUDIO_LICENSE_KEY.
No trial was activated. A licence covering judging and real Anthropic acceptance remain open.

The user has no credentials and requests building code first. Missing services fail
explicitly or offer manual catalog/listing fallback; production does not expose test
login links, fabricated model responses or simulated delivery. Later credentials still
require provider setup, permissions, webhooks, templates, domains and acceptance tests.
Worldwide access is a product goal; receiving eligibility remains merchant-specific.
USD and US/UK shipping are the initial supported commerce policy.

Next: finish local verification and reviewable commit, then run the provider/staging
acceptance checklist in the runbook when account access is available. Should features
remain deferred until Gate 2, as required by the source roadmap.

## AG Studio analytics boundary

/api/me/analytics computes all-store seller-scoped aggregate counts, stock and gross
order amounts from the database; it exposes no product title, buyer email or address.
The authenticated/CSRF-protected analyst receives these server-computed facts and a
bounded question, never client-supplied totals. It is read-only, receives no business
mutation tools, and reports gross amounts separately from net revenue/refunds.
The Studio framework owns the browser conversation; the server handles Anthropic
credentials. This initial analyst answers standalone questions, not arbitrary dashboard
layout tool calls. Product/order editing continues through the owned seller controls.
