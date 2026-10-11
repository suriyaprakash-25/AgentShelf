# AgentShelf implementation and release plan

## Source, intent and evidence

`BUILD_GUIDE.pdf` is the supplied 32-page roadmap, preserved unchanged.
`ROADMAP_SOURCE.md` is its supplied text companion. The roadmap defines the
feature order, acceptance tests and review gates; this plan records implementation
details and the user's explicit extensions. Maintain `STATUS.md` with test evidence
and integration gaps. Checkboxes represent verified staging behavior, never intent.

Build a production-quality, seller-first commerce pilot. International merchants can
access the product, but payment receiving is enabled only after checking account and
country eligibility. The user selected Anthropic credits, fixed USD shipping initially
to US/UK, email login fallback, and live payments before submission. These extend the
guide's sandbox-only scope. No claim of error-free or globally eligible payments is made.

## Architecture and contracts

- Python 3.12, FastAPI, official MCP SDK v2 with Streamable HTTP at `/mcp`.
- SQLAlchemy 2 and Alembic against PostgreSQL; no SQLite replacement for locking tests.
- Polling jobs with `FOR UPDATE SKIP LOCKED`; bounded retries and persistent deduplication.
- React/TypeScript/Vite for storefront, onboarding, seller dashboard and buyer Playground.
- Anthropic vision and tool calling behind `llm.py`; provider model name is configured
  and locked only after the five-photo spike passes. SDK retries must respect latency limits.
- `paypal.py` alone makes PayPal calls. `whatsapp.py` alone calls Meta.
- R2-compatible image storage; Render same-origin Docker web service, Docker worker and paid Postgres.
- Email magic links via a transactional email adapter; provider defaults to Resend.
- Preserve the guide's four tool names and money-string outputs. Require a session ID
  on quote, checkout and status to bind capabilities to buyers. Buyer sessions carry
  opaque random IDs, passed outside model-generated arguments by the Playground.
- Quotes snapshot title, unit price and fixed shipping. Positive USD integer minor
  units only initially; no model-supplied amounts or currency conversion.
- Add explicit `cancelled` state for the documented cancel endpoint. Include internal
  states in status responses rather than incorrectly labelling failed/pending orders paid.
- Stock means available stock. Reservation decrements it once; cancellation, expiry
  or decline releases it once. Paid orders remain deducted. Session row locking
  enforces spent plus all reserved totals against the budget under concurrent orders.
- Persist a checkout reservation before the external create call and use a stable
  PayPal request ID so uncertain responses can be reconciled rather than recreated.
- Capture verifies approval, identity, recipient, country and exact quote amount.
  Webhook deliveries verify all five signature headers; duplicates are acknowledged
  without repeat effects. Verification failures never reach business processing.
- Process capture responses as authoritative; real signed webhooks reconcile and
  trigger the paid notification. Never send buyer addresses to models or logs.
- Admission and approval links do not authorize seller resource access. Seller auth
  uses hashed, single-use 15-minute links and HttpOnly/Secure/Lax sessions, ownership
  checks and CSRF protection. Email login must work when WhatsApp is unavailable.
- Outside clients use the same MCP tools as the Playground. UI shows tool calls and
  results plus brief summaries, not hidden model reasoning. Human confirms the quote
  before checkout; PayPal remains the final payment approval surface.

## Roadmap and exit gates

### Sprint 0: foundations, October 8-11

Clone the supplied repo to the requested checkout; preserve the source roadmap;
add MIT licence, CI, local setup, architecture, ADRs and progress tracking. Save a
memory note pointing future work to these sources. Bootstrap Postgres and migration
workflow, service configuration and `/healthz`. Freeze REST/MCP contracts, wireframes
and design system. Provide a working MCP transport and test it through a real client.

Run ADR-001 with three sandbox sellers and US/UK buyers: capture to another account,
tracking, signed webhooks, refund permissions and India USD receiving. Record each
result with sanitized evidence. No checkout architecture is declared approved until
this spike passes. If payee capture fails, evaluate the guide's platform/Payouts
fallback and its permissions; do not assume Payouts works or settle sellers silently.
Meta echo, five-photo Anthropic JSON/latency spike, Render staging, cost estimate and
AG Studio trial eligibility are external prerequisites. Prepare everything possible
locally while keys/accounts remain unavailable. No trial activation or service purchase
without the user's approval of a concrete costed setup.

Exit: spikes verified or explicitly chosen feasible fallbacks, CI green, staging live.

### Sprint 1: walking skeleton, October 12-18; Gate 1

Migration `0001_init`, one fictional store and six products. Implement database-backed
search, quotes, checkout and status; token cache, PayPal create/capture, verified
webhooks, audit trail and minimal buyer agent. Render public store at `/s/{slug}`.
Ship WhatsApp onboarding and web fallback; deploy reviewed changes from main.
Reservation correctness ships with checkout even though its UI/expiry polish follows.

Exit: staged MCP search -> quote -> human sandbox approval -> single capture with
database audit. Hand over tag `gate-1`, staging, tests and known gaps for review.

### Sprint 2: real product, October 19-25

Photo processing: at most four 5 MB JPEG/PNG/WebP files; validate decoded format and
dimensions, strip EXIF, resize to 1024 px, store durable images. Schema-validated
drafts, one repair attempt, explicit seller price confirmation and YES publication.
Collect twenty labelled real-product samples. Implement WhatsApp commands, signed
message deduplication, paid notifications, reservation expiry and recoverable jobs.
Ship polished Playground with budget/confirmation/tool trace, seller dashboard with
AG Grid, session auth and email fallback. Web onboarding grants no verified payment
eligibility by itself. All seller writes require ownership and anti-CSRF checks.

Exit: a new tester lists via WhatsApp and buys via Playground on staging.

### Sprint 3: trust and fulfilment, October 26-November 1; Gate 2

Push tracking to PayPal; handle pending/declined/refunded/reversed captures and disputes.
Reconcile uncertain/stuck orders older than ten minutes, including lost create responses
before releasing stock. Implement admin failed jobs/webhooks, structured logs, Sentry,
shared rate limiting, uptime monitoring and retry/dead-letter handling. Run concurrency,
red-team, buyer tasks and listing evaluations; commit measured results. Finish mobile,
keyboard, accessibility, errors, empty states and performance. Restore a real backup.

Exit: all M1-M12 and S1-S6/B1-B4/H1-H2/J1-J2 pass on staging. Gate-2 evidence
includes test results, evaluation inputs/results and recording. If any Must fails,
drop every Should feature and fix Must work. Approved fallback limitations stay visible
and require a documented change to acceptance; they are not falsely marked passed.

### Sprint 4: hardening and story, November 2-8; Gate 3

After Gate 2 only: seller copilot with CONFIRM for each money action, then catalog mirror;
continue remaining Should items in the exact guide order if time permits. Voice notes,
third-party purchase and copilot appear in demo claims only when actually verified.
Feature freeze November 5 at 23:59 IST; record November 7, edit November 8.
Prepare public README, local setup, sandbox-only judge credentials, runbook and Devpost
draft. Public demo seller access cannot operate live inventory or real refunds.

Separate live release: one verified pilot merchant uses its own app/account credentials.
Isolate live and sandbox database, bucket, secrets, hostnames and webhook registrations.
Apply eligibility checks before checkout; no unrelated seller uses this live account.
Expand independent sellers only through verified PayPal onboarding/permissions; this is
an additional approval-dependent track, not a promise of universal availability.
Require HTTPS, real fulfilment/refund/contact/privacy policies, backup restoration,
monitoring, merchant signoff, checkout kill switch and user-approved controlled transaction.
If prerequisites fail, live remains disabled and the live milestone stays incomplete.

Exit: both source checklists have evidence, real video under three minutes, review tag
`rc-1`, all P0/P1 findings resolved. Live evidence tracked separately from sandbox evidence.

### Launch: November 9-11

Fix release blockers only. Submit target November 11 at 21:00 IST; official deadline
November 13 at 01:30 IST. User/team performs final publication/submission and external
review. Keep sandbox demo and storage available through December 15, 2026.

## Validation and operations

- Each story gets an acceptance test or repeatable staged script linked to its ID.
- Unit tests: money, quote arithmetic, schema checks and every allowed/forbidden transition.
- Real Postgres: up/down/up migrations, uniqueness/constraints, 20 buyers on stock one,
  same-quote retries, budget oversubscription, concurrent approval/expiry/cancellation,
  crash recovery and duplicate job/event effects.
- Integration: unauthorized cross-seller writes, forged links/CSRF, expired/cross-session
  quotes, signed/unsigned/replayed webhooks, capture mismatches and tracking permissions.
- Real sandbox nightly tests: create, human approval, capture, read, tracking, refund and
  real event verification. Mocks test failure handling but never establish integration success.
- Playwright: onboarding -> draft -> confirmation -> public product -> buyer quote ->
  PayPal approval -> receipt -> seller order -> tracking. External approval remains a
  clearly labelled manual sandbox step where automation cannot cover it honestly.
- Targets: 18/20 listing categories, average human quality >=4/5, zero invented claims;
  14/15 agent tasks, zero over-budget checkouts; draft p95 <20s, search p95 <1s at 1,000
  products; LCP <2.5s; accessibility >=90; 375px screen layout; judge purchase <5 minutes.
- CI: Ruff, pytest, real Postgres integration/red-team, TypeScript, ESLint/Prettier,
  build, secret scanning and high/critical dependency audit. Provider tests run separately.
- Logs carry request/order IDs without personal data. Runbook covers uncertain capture,
  webhook replay, retry failures, secret rotation, backup restore and sandbox reset.

## Dependencies and release boundaries

Needed from account owners: PayPal sandbox app/accounts; registered Meta app/test
recipients; Anthropic API access; Render/bucket/email credentials and verified email
domain; AG Studio licence if used. Names/roles stay unassigned until supplied. Payments
spike and three reviews stay as gates; this agent does not invent their outcomes or
contact reviewers. Secret values belong in local ignored env files or managed secrets.

Global access is a product goal. USD plus US/UK shipping is the user's initial commerce
policy, not a claim that all countries can receive funds. Broad destination/currency
support and marketplace live onboarding require further verified merchant rules.

## October 10 implementation checkpoint

The working checklist now records media/listing publication, real MCP buyer chat,
WhatsApp onboarding and catalog/fulfilment commands, durable capture intent,
reconciliation, refund/dispute review, operator UI and deployment/maintenance code.
See STATUS.md for exact test evidence and remaining gates. Configuration does not
establish provider acceptance. Reservation release currently requires PayPal VOIDED
proof; resolve the difference from the source 15-minute policy before Gate 2.
The deployed frontend and API must share one HTTPS origin to preserve secure sessions.

The October 11 evaluation tooling now includes twenty actual MCP search timings with
at least 1,000 enumerated products, expected result/price checks, catalog hash stability
and explicit SDK cache disablement. Use evals/README.md to run against quiet staging;
retain separate database index/query-plan evidence. Local tests and tools do not replace
the roadmap's hosted latency or human/provider acceptance gates.

Local accessibility verification now runs axe scans in development and packaged browser
suites, with retained reports and an actual keyboard skip-focus check. Public/mobile and
controlled populated seller/operator plus quote/listing-review states are covered. Keep
Lighthouse scores, manual screen-reader/keyboard assessment and real licensed/provider
states as separate unaccepted release requirements.
