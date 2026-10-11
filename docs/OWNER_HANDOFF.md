# AgentShelf engineering completion and owner handoff

Updated October 11, 2026. This report supersedes the October 9 local engineering snapshot.

AgentShelf has implemented the core pilot workflows and the additional credential-free
hardening below. It is **not yet accepted for a production launch or a real merchant pilot**.
All 14 staged stories and Gates 1, 2 and 3 remain unsigned. Credentials, service setup,
real provider tests, deployed measurements and merchant decisions are still required.

## Work completed and checked

- AI listing draft/review/publication, MCP buyer tools and explicit buyer confirmation,
  WhatsApp onboarding/photo/edit/tracking jobs, reconciliation/refund accounting,
  operator dashboard, deployment blueprint and actual AG Studio integration are implemented.
  Provider substitutes establish local behavior only, not real-service acceptance.
- Added 64 KB API/MCP JSON body limits, including chunked requests, before parsing.
- Added bounded media and legacy personal-data review with dry-run defaults,
  active-operator approval, audit records and protected financial/pending/dispute data.
  Upload, cleanup and draft creation share database locking to prevent image races.
- Added operator recovery for a lost PayPal order-create response. Provider identity,
  payee, quoted amount, currency and local correlation must match. Recovery does not
  initiate buyer approval or payment capture. PayPal approval redirects are restricted
  to HTTPS PayPal hosts for the configured sandbox/live environment.
- Added compression that preserves event streaming, local fonts, immutable hashed
  asset caching, private screen no-store headers, lazy page loading and corrected headings.
- Strengthened CI with isolated packaged API/worker smoke checks and mandatory CI
  PostgreSQL backup clients; added compose.verify.yaml and a sanitized smoke report tool.
- Full backend suite: **190 passed in 103.45 seconds**, including actual local native
  PostgreSQL 17 backup and restore; no skipped tests in the final run.
- Browser suite: **13 development checks passed in 12.2 seconds**, plus **12 packaged checks in 14.7 seconds**: real seeded catalog/quote/mobile layout
  and controlled AI, listing and actual AG Studio flows. Real checkout is not covered.
- Frontend build, lint and formatting passed. Dependency audits found no known
  vulnerabilities at audit time. Ruff passed. The migrated application database
  reports no new migration operations. Test fixtures are not used as migration proof.
- Local mobile storefront Lighthouse: **performance 91, accessibility 100, LCP 2.0 s**;
  before fixes: 69, 98, 4.2 s. One local route/run, not a hosted or all-screen result.
- The preceding monitoring revision ac6f21d has fully green GitHub CI, including browser cleanup:
  https://github.com/suriyaprakash-25/AgentShelf/actions/runs/38110401055.
  New changes are committed/pushed after verification; their CI is separate evidence.
- Added operator loading/empty states and controlled recovery/retry/denial/mobile
  browser coverage; seven new retention and R2 adapter regression cases pass.
- Recovered local Docker: newly built image serves UI/catalog, rejects unauthorized
  and oversized requests, round-trips gzip with immutable caching, runs as UID 10001,
  and records a fresh worker heartbeat. Migrations report no drift.


## Verification limits and workstation follow-up

Docker Desktop and disk availability recovered on October 11. The local rebuild and
isolated PostgreSQL 17 packaged API/worker verification now pass. The previous native
Postgres was stopped; tests used fresh, separate demo/test databases. Original database
files were untouched. Frontend dependencies were reinstalled locally; the earlier E: junction is no longer active. Preserved E: files remain untouched.
This container evidence does not establish funded deployment or provider acceptance.

Seller and optional AG Studio chunks remain large (approximately 1.01 MB and 4.36 MB
before compression); they load separately. Test authenticated seller/Studio performance
on hosted devices before enabling the licensed Studio pilot. Local media cleanup is a
bounded first page; use R2 continuation tokens for a complete production inventory.

## Your next steps, in order

1. **Accounts and configuration.** Create PayPal sandbox business/buyer accounts,
   Anthropic API access, Meta/WhatsApp business access, an email provider with verified
   sending domain, a private R2 bucket, deployment access and Sentry/alert destination.
   Obtain an AG Studio deployment licence covering judging. Configure secrets in the
   ignored environment or managed secret store; never paste secrets into chat. Use
   .env.example and the runbook for exact variables, webhook URLs and setup.
2. **Merchant and policy decisions.** Complete ADR-001 with three sellers and US/UK
   buyers; verify receiving eligibility, currency, address/country and tracking support,
   including the intended India-based merchant arrangement. Approve privacy/retention,
   shipping, cancellation/refund and dispute handling. Worldwide access does not prove
   worldwide merchant/payment support. Resolve the roadmap's 15-minute expiry requirement:
   current code releases abandoned reservations only after provider VOIDED proof.
3. **Real provider acceptance.** Test actual approval/capture, signed and duplicate
   webhooks, missing-create recovery, interrupted capture, refunds and disputes.
   Approve the WhatsApp paid-order template and verify real onboarding, four-photo
   drafts, confirmation, edits, tracking and alert timing. Verify email receipt and
   API/worker access to private R2. Credentials alone do not establish these outcomes.
4. **Deploy funded HTTPS staging.** Run remote CI and fresh container verification;
   configure the domain, secrets, licensed build and database migrations. Verify cookies,
   CSP, proxy limits, health checks, worker and actual alert delivery. Establish managed
   backup retention; perform hosted restore and worker/provider outage/retry drills.
5. **Run the roadmap evaluations.** Use 20 real products: at least 18/20 correct
   categories, quality at least 4/5, no invented claims and draft p95 below 20 s.
   Run 15 buyer tasks with at least 14/15 success, independent MCP client/Inspector,
   1,000-product search p95 below 1 s, all-screen accessibility at least 90 and hosted
   LCP below 2.5 s. Have an independent judge complete a real sandbox purchase under
   five minutes. Record the exact provider/model, dataset and timing evidence.
6. **Approve staged gates and pilot.** Complete all 12 Must criteria and 14 stories,
   obtain Gate 1/2 review, then implement/accept the source's Should items in order.
   Prepare judge credentials, public links, walkthrough and submission; obtain Gate 3.
   Verify merchant-specific live permissions and separate live configuration before
   an owner-approved controlled live transaction. Fund operations through judging.

Use DELIVERY_CHECKLIST.md to track acceptance and RUNBOOK.md for execution. These are
concrete remaining tasks, not a claim that adding credentials automatically completes
production readiness. I can perform further engineering and staged verification once
account access and the required policy decisions are available.


## Browser monitoring addition

Optional BROWSER_SENTRY_DSN enables the actual pinned browser SDK at runtime. Its
public DSN is validated and its exact ingestion origin is allowed by CSP. Default
instrumentation, breadcrumbs, tracing and personal-data collection are disabled.
Fixed error codes are deduplicated and event payloads/attachments are filtered;
React rendering failures have a reload screen with existing-order guidance.
Actual-SDK browser tests intercept transport and pass; account receipt and alert
routing still require owner-provided Sentry configuration and staged evidence.
Use the browser monitoring section of RUNBOOK.md for setup and acceptance.

## Packaged frontend verification

The monitoring SDK wrapper cuts its optional chunk from 435.88 KB to 93.29 KB
(146.72 KB to 32.02 KB gzip). CI runs the built dist workflows on port 5174
in addition to development checks. Missing/unavailable monitoring keeps the
catalog working without fetching the SDK. The packaged Studio check verifies
its missing-licence gate and continuing catalog access; actual licensed Studio
acceptance remains open. See RUNBOOK.md for the production-check command.
