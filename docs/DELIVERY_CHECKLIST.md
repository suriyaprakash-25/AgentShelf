# AgentShelf delivery checklist

Updated October 11, 2026. Checked boxes mean tested local implementation only.
Source roadmap acceptance and independent release gates remain separate.

## Implemented and checked locally

- [x] Preserve original roadmap and historical 113-checkbox completion audit.
- [x] PostgreSQL schema, migrations, catalog, locked stock and budget invariants.
- [x] Secure email verification, consent, seller sessions, CSRF and ownership.
- [x] WhatsApp onboarding with email verification before binding phone ownership.
- [x] Private image processing/storage adapter, asynchronous AI drafts and review history.
- [x] Web/WhatsApp publication requires seller-entered price/stock and confirmation.
- [x] WhatsApp multi-photo grouping, edits/archive, orders and tracking commands.
- [x] Public photos and catalog keyset pagination; seller product/order pagination.
- [x] Real MCP buyer agent transport, streamed tool results and explicit quote confirmation.
- [x] Server-bound session/country, shared quotas, bounded history/tool/model calls.
- [x] Stable checkout/capture/tracking IDs and durable approved capture intent.
- [x] Signed/deduplicated inbox, bounded job retries and known-order reconciliation.
- [x] Paid-notification adapter gated by verified capture event; utility-template support.
- [x] Verified refund accounting and visible dispute/reversal review states.
- [x] Role-protected operations UI, audited failure retry and worker heartbeats.
- [x] Privacy-filtered API/worker Sentry and actual browser SDK, recovery screen, request logging and expired auth/chat cleanup.
- [x] Actual local backup/restore drill and guarded synthetic sandbox reset.
- [x] Local 1,000-product search/pagination check and completed browser runner.
- [x] Axe WCAG 2.1 A/AA browser scans for public/mobile screens and controlled populated seller/operator, quote and listing-review states; contrast and keyboard skip-focus fixes. Lighthouse/manual acceptance remains open.
- [x] Twenty-search actual MCP latency evaluator with catalog count/hash stability and expected ID/price checks; hosted latency and index acceptance remain open.
- [x] Actual AG Studio custom widget/theme and framework analyst, locally browser tested.
- [x] Unlicensed production omits Studio entirely and avoids analytics calls; development component still verified. Render licence build variable is documented.
- [x] Same-origin deployment container built; non-root runtime/migrations/catalog/UI checked with PostgreSQL 17.
- [x] API/worker/private-storage blueprint authored.
- [x] Listing evaluation runner/scorer and blank dataset/review templates; two distinct complete human review panels required. Real quality/latency evaluation remains pending.
- [x] Installed model SDK timeout/error/schema tests; hidden transport retries disabled and durable listing retry/recovery verified against PostgreSQL. Hosted model latency remains open.
- [x] Fifteen-task sandbox buyer runner/scorer with human payment steps and task/review templates; controlled protocol tests pass. Real task success remains pending.
- [x] Confirmed checkout SSE now emits done after session cleanup; actual HTTP/MCP/PG17 regression verified.
- [x] External API/database uptime probe, sanitized failure evidence, inactive scheduled workflow and 14 operations tests; local database outage detected.
- [x] Bounded JSON/MCP bodies, verified lost-order correlation and auditable dry-run retention tools.
- [x] October 11 full local suite: 190 backend tests, 13 development and 12 packaged browser tests, PostgreSQL 17 restore and no migration drift.
- [x] Smaller optional monitoring SDK and packaged dist workflows, including missing-licence gate.
- [x] Operator confirmation/error/retry/denial/mobile browser checks and retention/R2 regression cases.
- [x] Recovered local Docker: fresh image, non-root API, worker heartbeat, gzip/cache/auth smoke checks.
- [x] Local mobile storefront: performance 91, accessibility 100, LCP 2.0 seconds.
- [x] Phase A codebase review remediations (proxy IP isolation, PayPal hostname validation, decoupled chat PII filter, 15-minute unapproved checkout reservation expiry, formatted WhatsApp address notifications, receipt tracking display, Playground MCP trace wiring, `useParams()` storefront routing, split dashboard pagination, `make demo-reset`).
- [x] Phase B verification CLI (`backend/verify_phase_b.py`, `make phase-b-preflight`), nightly sandbox workflow (`.github/workflows/nightly-sandbox.yml`), Devpost submission & demo video script (`docs/DEVPOST_SUBMISSION.md`), and 9-section `README.md`.
- [x] Local implementation of Should features S-1 through S-6 (Seller Copilot summaries/refunds/invoicing, PayPal Catalog Products mirror, WhatsApp voice-note transcription, `/.well-known/mcp.json` + `schema.org` JSON-LD discovery metadata, `evals/mcp_client_config.json`, and multi-language listing copy translation with authoritative server pricing).

## Required before full Must and pilot acceptance

- [ ] Real PayPal sandbox ADR-001 with three sellers and US/UK buyers.
- [ ] Actual approval/capture, signed webhooks, duplicate/retry and tracking evidence.
- [ ] Decide safe provider-expiry policy: current release is VOIDED-only, not unconditional 15 minutes.
- [ ] Real Meta onboarding/photos/edits/tracking, approved template and paid alert timing.
- [ ] Real email domain/delivery and private R2 API/worker acceptance.
- [ ] Anthropic spike/model choice, 20-product quality, image-instruction/PII tests and draft latency.
- [ ] Fifteen buyer tasks, money-path browser flow and independent MCP Inspector/client tests.
- [ ] AG Studio deployment licence covering judging and real model acceptance.
- [x] Remote PostgreSQL 17 backend/container checks and complete-history secret scan and fully green CI on preceding monitoring revision ac6f21d.
- [ ] Funded hosted startup and real provider checks.
- [ ] Funded HTTPS staging; verify origin/cookies/CSP/proxy quotas and external purchase under five minutes.
- [ ] Managed backups/restore/retention and owner-approved execution of media/personal-data maintenance.
- [ ] Real human dispute/reversal and verified unknown-create-ID correlation drills.
- [ ] Real Sentry/alert delivery, worker outage/retry drills and nightly provider checks.
- [ ] Lighthouse LCP/accessibility, deployed search/load targets and all mobile layouts.
- [ ] All 12 Must criteria and 14 stories pass on staging; Gate 1 and Gate 2 signoff.

## Release and live pilot

- [ ] Should features staged acceptance after Gate 2 signoff.
- [ ] Final judge credentials/public links, walkthrough video, evaluation and runbook drills.
- [ ] Team review, Devpost draft, Gate 3 signoff and independent link verification.
- [ ] Merchant-specific live eligibility/permissions/policies and separate live app/database/storage.
- [ ] Merchant-approved controlled live transaction and funded operations through judging.
- [ ] User/team completes submission.

Secrets belong in ignored env files or managed secrets, never chat or commits.
Provider credentials alone do not replace setup and acceptance evidence.
