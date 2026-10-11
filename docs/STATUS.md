# AgentShelf status and evidence

Updated October 11, 2026. **Must workflow implementations substantially expanded; production and pilot acceptance remain open.**
Checkout: `D:\PayPal\PayPal AI Hackathon\AgentShelf`, branch `feat/foundations`.
The unchanged source PDF has SHA-256
`69EA49D89F45A4752E72B90FCBA2C8BFFFDDFDD076523F00559BC4F5EF19D8A4`.
`COMPLETION_REPORT.md` is the historical October 9 audit of 113 source checkboxes,
12 Must requirements, 14 stories and three gates. Its counts are historical;
they must not be read as a current implementation assessment.

## Current local evidence

| Check | Result | Evidence boundary |
| --- | --- | --- |
| Full backend suite | 190 passed, 103.45 seconds | Python 3.12, isolated local PostgreSQL 17; external services controlled in tests |
| Alembic upgrade/downgrade/upgrade and schema drift | Passed | Dedicated local migration database |
| Dependency audit | No known backend/frontend vulnerabilities | Installed dependency snapshot |
| Frontend lint, format and production build | Passed after AG Studio integration | No staging performance claim |
| Development browser suite | Thirteen tests passed, 12.2 seconds | Actual API catalog/mobile plus controlled listing/SSE/Studio/operator recovery and actual browser SDK fixtures |
| Packaged browser suite | Twelve tests passed, 14.7 seconds | Built dist on strict port 5174; controlled providers; missing licence gate verified |
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
| M11 | Same-origin container, API/worker/Postgres Render blueprint, CI, maintenance tools | Funded HTTPS deployment, managed backups and independent five-minute purchase |
| M12 | Shared DB quotas, ownership/CSRF, caption guards, minimized logs/webhooks, bounded images, Sentry scrubbing | Complete deployed red-team/image evaluation, proxy/CSP/accessibility acceptance |

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
through ADR-001 before release. Unknown create IDs can now be correlated through the operator screen: verified provider identity, amount, currency, payee and custom ID are required; this action does not initiate approval or capture. Real recovery drills remain pending.

WhatsApp delivery is at least once across a crash after sending. Multi-photo messages
are grouped up to four images with a short debounce; duplicates use stable IDs.
Hourly cleanup removes expired auth records/stale quota buckets and clears old chat
text after 30 days while preserving payment/budget records. Bounded, operator-audited orphan media and historical inbox/address maintenance are implemented with dry-run defaults. Referenced images, pending work, payment records and dispute/reversal addresses are preserved. Owner retention approval and managed backup acceptance remain open.

## Deployment and release boundaries

API serves the built frontend from one HTTPS origin; worker uses the same database,
private R2 bucket and provider/email secrets. Docker now builds successfully. The non-root packaged API starts against an isolated
PostgreSQL 17 container and serves the catalog/UI with security headers; migrations
report no drift. The full native suite uses PostgreSQL 18.4. The preceding revision 4ee8a82 has fully green GitHub CI: https://github.com/suriyaprakash-25/AgentShelf/actions/runs/38037184879. Current phase checks are recorded below; remote CI is rerun after pushing each change.
The seller bundle is approximately 1 MB and optional Studio approximately 4.36 MB before compression; The October 10 local mobile storefront audit scores performance 91, accessibility 100 and LCP 2.0 seconds after local fonts, compression and heading fixes. Hosted targets and all authenticated screens remain unverified.
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

Latest credential-free phase: 182 backend tests and 8 browser tests pass, including PostgreSQL 17 backup/restore and recovery/privacy safeguards. Docker Desktop recovered; the newly built non-root container passes local catalog, frontend, auth, gzip/cache, worker heartbeat and migration checks against an isolated PostgreSQL 17 database. See OWNER_HANDOFF.md for evidence and the remaining acceptance checklist. Should features
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


## October 11 operator and recovery verification

The operations screen has explicit loading and empty states. Three controlled browser
checks verify confirmation/cancellation, session CSRF on correlation/retry, mismatch
messages without hiding the recovery form, successful refresh, access-denied controls,
and 375px layout. These are interface checks, not actual provider recovery evidence.
Seven added backend cases protect legacy product image references and addresses for
active fulfilment, uncertain payments and resolved dispute/reversal review; R2 cursor,
exact-key deletion and generic provider error handling use signed-client stubs.
The full 182-test suite passes without skips, including real dump/restore to a separate
random drill database. Old native Postgres was not running; verification used a fresh
isolated Docker PostgreSQL 17 instance with separate test/demo databases.
Original database files were not modified. The source PDF hash remains unchanged.


## Browser monitoring phase

Implemented optional browser Sentry SDK 11.6.0 with runtime public DSN configuration,
exact ingestion-origin CSP, disabled default integrations/data collection, fixed-code
payload allowlist, attachment removal and bounded deduplication. The SDK chunk loads
only when enabled. React failures show a usable reload screen and avoid raw React
error logging through root callbacks. Eight backend config/CSP/privacy cases and
three actual-SDK browser transport/recovery/privacy cases pass. Full suites: 190
backend tests (including actual PostgreSQL 17 restore) and 11 browser tests. SDK
transport is intercepted in browser tests; real Sentry receipt/alerts remain open.
Frontend dependencies were reinstalled as an ordinary local node_modules directory;
the earlier E: junction is no longer the active dependency path. Preserved E: files
remain untouched. Source roadmap/PDF remain unchanged.

## Optional SDK optimization and packaged browser checks

The optional SDK chunk is 93.29 KB (32.02 KB gzip), down from 435.88 KB
(146.72 KB gzip). This is a measured build-size improvement, not a hosted
performance result. Disabled/unavailable monitoring does not download the SDK
and preserves catalog use. Thirteen development and twelve packaged browser
tests pass. The packaged suite checks the deployment-licence gate rather than
bypassing it; the source-module privacy unit check stays in development.
CI now runs both browser suites. Previous monitoring revision ac6f21d passed
all five jobs: https://github.com/suriyaprakash-25/AgentShelf/actions/runs/38110401055.
The optimized revision CI is separate evidence. Provider receipt, licensed
Studio deployment and all staging/live gates remain unaccepted.

## External uptime probe implementation

The optimized revision 63cd60c passed all five CI jobs, including packaged browser
workflows: https://github.com/suriyaprakash-25/AgentShelf/actions/runs/38110769391.
Implemented a standard-library external /healthz probe and a five-minute scheduled
workflow, inactive until STAGING_ORIGIN is configured on the default branch.
Fourteen controlled transport/validation/CLI cases pass (2.207 seconds); these are
additional operations tests, not a change to the 190-test backend count. Local
packaged API/PostgreSQL verification returned HEALTHY/200, then HTTP_FAILURE/503
when the owned isolated database was stopped. Lint and format checks pass.
No staging address, hosted schedule or operator notification receipt is verified.
The source external-uptime acceptance checkbox therefore remains open. The probe
does not replace nightly provider tests, worker outage drills or real alert receipt.

Health cache follow-up: /healthz now sets no-store for successful and failed responses.
Two added backend tests check the SQL health query, outage response, cache headers
and private-error exclusion (2 passed in 6.41 seconds). Container smoke now requires
the health cache header on the packaged API. Full updated backend/packaged behavior
is checked separately by the follow-up revision CI; the earlier 190 count is historical.

## Studio omission for unlicensed production builds

The preceding health-cache revision 26a0d4e passed all five CI jobs:
https://github.com/suriyaprakash-25/AgentShelf/actions/runs/38111351621.
Unlicensed production now checks the licence before importing Studio. The built dist
contains no AnalyticsStudio chunk; clicking the licence notice fetches neither Studio
code nor analytics API data. The seller chunk shrank from 1,007.30 KB (283.31 KB gzip)
to 885.89 KB (249.45 KB gzip). Previously Studio was 4,363.84 KB (1,242.29 KB gzip).
These are build-size measurements, not new Lighthouse or hosted latency evidence.
Frontend lint, format and build pass; 13 development tests pass in 14.2 seconds and
12 packaged tests in 16.7 seconds. The actual Studio widget/analyst still works in
development with controlled data/model responses. Fixed three damaged loading labels.
The Render blueprint explicitly lists the existing Docker licence build argument.
Licence acquisition/validation, a licensed production rebuild and real Anthropic
acceptance remain open; no fake key, trial activation or provider call was used.

## Listing evaluation runner and scorer

The preceding Studio optimization 8a6c26d passed all five CI jobs:
https://github.com/suriyaprakash-25/AgentShelf/actions/runs/38111656286.
Added an actual-provider listing runner and strict scorer for the roadmap's 20 real
products, balanced 5/5/5/5. Input preflight validates image paths/content/captions and
rejects duplicates before calls. Records bind dataset, processed images, run and human
reviews by hashes. Twenty focused protocol tests pass (3.22 seconds), including
incomplete/failure rejection, exact category/rating/p95 boundaries and private-output
exclusion. Fixtures are synthetic; no real photograph/model/quality run is claimed.
Public summaries distinguish local model-call latency from hosted workflow latency
and never grant gate approval. Templates remain invalid until actual photos, labels
and ratings are entered. Private artifacts are ignored. Full quality, hosted latency,
buyer task and review gate acceptance remain open; see evals/README.md.

## Buyer evaluation and confirmed stream completion

The preceding listing-tool revision b7263bc passed all five CI jobs:
https://github.com/suriyaprakash-25/AgentShelf/actions/runs/38112163654.
Implemented a sandbox-only fifteen-task HTTP/SSE runner and bound human-review scorer.
Purchase cases require explicit quote confirmation, human PayPal sandbox approval and
matching session-owned paid readback before model status review. The runner validates
origins/approval hosts, repeats sandbox preflight before checkout, bounds response/event
sizes, redacts exception text and paces turns without bypassing production rate limits.
Task templates include stock/budget/ambiguity, quantities, destination and attacks.
Review placeholders are invalid. Public summaries contain no prompts/capabilities and
never grant gate approval. Pricing/payment claim grounding remains human-reviewed.

Found and fixed confirmed chat returning without done. Both confirmation and model
branches now reach the shared cleanup/completion path. The actual HTTP/MCP socket test
checks exactly one done event and released lease after checkout. Local isolated PG17:
48 focused tests passed in 12.73 seconds; full pre-pacing-test suite 236 passed in
85.12 seconds without skips, including actual restore. The added pacing check and
evaluation suites pass: 45 tests in 3.87 seconds. Latest full count/CI is separate evidence.
No real model request, PayPal approval/payment or buyer-success evaluation was performed.
Real fifteen-task results and all external acceptance gates remain open.

## Twenty-search transport evaluation

Added a read-only actual MCP SDK/HTTP evaluator for twenty searches over at least
1,000 searchable products. Bounded public cursor enumeration binds complete catalog
records before/after; expected ordered IDs and server prices must match. At least five
distinct queries are required. No sample or failure is discarded, SDK caching is
disabled, and nearest-rank p95 must be strictly below one second. Invalid templates,
catalog changes and transport failures cannot produce successful evidence. Aggregates
exclude records/queries/host URLs; index verification and gate approval remain false.
The evaluator measures round trips, excluding connection setup and enumeration. Local
measurement cannot establish hosted latency, concurrent load, transactional catalog
stability or installed/used full-text index. See evals/README.md for these limitations.

Nineteen controlled protocol tests pass in 4.56 seconds. Actual loopback MCP/socket and
isolated PostgreSQL 17 evaluation with 1,001 products passed; full native backend suite
passed 256 tests in 90.69 seconds, with no skips. The subsequent explicit cache-disable
and scan-deadline changes have separate focused verification. Invalid template CLI
rejected input and wrote no result. Source PDF hash remains unchanged. Hosted twenty
searches, provider acceptance, licences, policies and Gates 1/2/3 remain unaccepted.

## Accessibility checks and corrections

Added locked axe-core Playwright scans for WCAG 2.1 A/AA with no disabled rules or
excluded elements. Eight public screens are scanned at 375 px; controlled populated
seller grids/fulfilment forms and operator screens at 1,280/375 px; quote-confirmation
and listing-review states are scanned inside their existing interaction tests. Scans
retain violations and incomplete/manual-review findings. CI retains packaged JSON
reports for seven days, including success. Tests keep provider/authentication fixtures
isolated in the browser; production permissions and adapters remain real.

Found and corrected home heading/illustration-note/step-number and playground notice
contrast. Darkened muted text, made main focusable for the keyboard skip link and
extended visible focus to textarea, summary and main. Actual keyboard activation now
checks focus reaches main. Development suite: 16 passed in 24.3 seconds. Packaged
unlicensed build: 15 passed in 24.2 seconds. Fourteen packaged scans had zero automated
violations; complex illustration and AG Grid header contrast retain incomplete checks.
These findings require manual review, not a claimed conformance result. Lint, Prettier,
TypeScript/Vite build and npm audit pass with zero reported vulnerabilities. Lighthouse
scores, real licensed/provider states and human screen-reader assessment remain open.

## Two-teammate listing quality review

The source success metric explicitly requires two teammates to rate all twenty products;
the previous scorer accepted one. Scoring now requires two complete panels with distinct
anonymous reviewer IDs and the same run hash. Missing/duplicate/unbound second records
leave evaluation incomplete. CLI requires exactly two repeated --reviews arguments.
All forty ratings contribute to the average >=4/5; summaries retain individual averages
and canonical review hashes. An invented claim flagged by either reviewer prevents a
pass, with each flagged product counted once. Categories and nearest-rank latency retain
the source thresholds. Legacy one-review summaries cannot satisfy the two-person metric.

Local isolated PostgreSQL 17 full suite: 265 passed in 95.88 seconds, with zero skips,
failures or errors. Targeted listing/buyer/search protocol suites: 73 passed in 7.55
seconds, including twenty-nine listing tests and the actual CLI/hash binding. Ruff lint
and format pass; source PDF hash unchanged. No real photographs, model request or human
quality evaluation was performed. Distinct IDs do not independently prove human identity
or independent judgement. Provider, staging and roadmap gate acceptance remain open.
