# AgentShelf status and evidence

Updated October 10, 2026. **Local seller workflows built; pilot/release not complete.**
The historical October 9 source-checkbox audit is in `COMPLETION_REPORT.md`: all 113 checkboxes,
12 Must requirements, 14 stories and three gates are assessed. Of the 41 production
checks, five have local component/document evidence, 23 are partial and 13 pending;
none of the gates or full staged Must acceptance criteria is signed off.
Current implementation progress is tracked in `DELIVERY_CHECKLIST.md` and below;
the October 9 audit counts are not a new assessment of today's changes.
Checkout: `D:\PayPal\PayPal AI Hackathon\AgentShelf`; feature branch `feat/foundations`.
The repository was empty when cloned. No pre-existing implementation was replaced.
The source PDF copy has SHA-256
`69EA49D89F45A4752E72B90FCBA2C8BFFFDDFDD076523F00559BC4F5EF19D8A4`,
matching the supplied original. A user-requested memory note points to this project.

## Verified locally

| Evidence | Result | Boundary |
| --- | --- | --- |
| Backend pytest, Python 3.12.10 | 122 passed | October 10; real Postgres 18.4; provider calls mocked where marked |
| Seller auth/CSRF/ownership | Six integration tests pass | Email delivery mocked; actual hashed/single-use/expiry/concurrent session logic and DB |
| Auth migration up/down/up + schema drift check | Pass | Dedicated agentshelf_migration_test DB; dev DB also has no drift |
| Verified webhook PII minimization | Pass | Buyer email/address removed from new inbox writes after verification; existing historical data needs audit |
| Seller browser workflow | Assertions pass | Synthetic test-only email-link fixture -> draft -> confirm/publish -> 375px -> logout; Chrome teardown hangs |
| Worker handler rollback, retry limit and concurrent claims | Pass | Real Postgres savepoints and SKIP LOCKED; no external delivery proof |
| Ruff lint and format | Pass | Locked Ruff 0.16.10 |
| Alembic up/down/up and schema check | Pass | Dedicated test DB; local DB also has no drift |
| Stock 1 / 20 distinct concurrent buyers | Exactly one checkout succeeds | Database invariant; not 20 real PayPal payments |
| Concurrent same quote and capture return retries | One order / one capture call | Mock provider with real locks/transactions |
| Session ownership and shipping-inclusive budget | Pass | Local service logic |
| Bad signatures and verified duplicate inbox | Pass | Local negative tests; verification success mocked |
| Mounted HTTP MCP via SDK client | Search and quote pass; four tools listed | Actual socket/transport and database; no external host purchase |
| Image decoding, resizing, EXIF removal | Pass | Synthetic image tests, not model quality evidence |
| Playwright / installed Chrome | 2 passed | Real API/catalog/quote and 375px layouts; no approved payment |
| TypeScript, ESLint, Prettier, Vite build | Pass | Local browser build |
| pip-audit and npm audit | No known vulnerabilities reported | Snapshot of the installed dependencies |
| `/healthz` and demo storefront | DB reachable, 6 products | Local only; no public staging URL |

Local browser: `http://127.0.0.1:5173`; API: `http://127.0.0.1:8000/docs`.
Docker Desktop failed before engine startup due to its secrets-engine socket.
A project-local native PostgreSQL 18.4 runtime is listening on 127.0.0.1:5433.
Docker Compose/CI still target Postgres 17; that separate environment is not yet verified.
The frontend preview was visually inspected. Product illustrations are labelled synthetic.

## Must requirements

| ID | Current implementation | What still proves completion |
| --- | --- | --- |
| M1 | Verified Meta inbox/echo; working web email-verification onboarding | Real WhatsApp onboarding, actual email delivery and S1 staged timing |
| M2 | Image preprocessing, strict listing schema and Anthropic adapter | Media storage, draft delivery/YES, 20 real-product model evaluation and S2 latency |
| M3 | Postgres schema/seed, public catalog/quotes; owned draft/create/price/stock/archive/publication and paginated seller lists | WhatsApp edits, public catalog pagination and S3 staging latency |
| M4 | Four MCP tools, actual Streamable HTTP search/quote test | Inspector and Playground agent B1-B4 on staging; verified checkout/status |
| M5 | Candidate direct-payee create/read/capture, locks, stable request IDs | ADR-001 and real sandbox approval/capture/refresh evidence |
| M6 | Five-header API verification, verified inbox and deduplication | Real signed sandbox delivery, deployed timing, retries/reconciliation |
| M7 | Notification job waits for a verified completed-capture event | Real WhatsApp paid alert including approved address within 10 seconds |
| M8 | Order tracking fields only | Authenticated tracking command/API and actual PayPal tracking evidence |
| M9 | Manual REST catalog explorer, exact quote/confirmation and activity | Anthropic buyer agent using MCP, SSE chat, complete server-bound session controls |
| M10 | Magic links, secure hashed sessions, web/email fallback, custom AG Grid Community product/order tables, filters/sort/current-page CSV, ownership tests | Real email delivery, AG Studio framework/licence, complete staged S6 and fulfilment UX |
| M11 | Render blueprint, local startup/CI config | Funded HTTPS staging, real CI runs, backups/restore and external 5-minute test |
| M12 | Server-owned money, bounded catalog, UUID scope, basic process limiter | Full red-team set, shared rate limits, image-instruction eval, all ownership/PII checks |

S1-S6, B1-B4, H1-H2 and J1-J2 remain open as staged stories. Local tests cover parts
of B1/B2/B3/H1/H2; this is not evidence that the full story passes on staging.
Each of the source's security, reliability, observability, testing, performance,
accessibility, documentation and submission checks remains a release requirement.
Local lint/security/locking evidence covers only the rows above. Not yet verified:
deployed auth/CORS/CSP, shared limits, secret history scan, all resource ownership,
failure admin UI, expiry and automatic reconciliation, provider outages/fallbacks,
backups, Sentry/alerts, nightly provider tests, model/agent/performance targets,
Lighthouse/mobile accessibility, production runbook drills and safe demo-reset.
CI now includes the real API/seeded Postgres browser flow; the remote GitHub workflow
has not run. The Windows startup script now launches the worker as well as the API/UI;
its Docker-based startup remains unverified while Docker Desktop is unavailable.
October 9 rerun: both browser assertions passed, but installed Chrome hung during
teardown and the runner was interrupted. The prior completed 2-test run remains the
browser-suite evidence; this teardown issue must be resolved before release.

## Gates and external prerequisites

- Sprint 0 is open: ADR-001, five-photo vision spike, Meta echo, staging and AG Studio
  licence/account setup are not established. Account keys are not configured.
- Gate 1/`gate-1` not earned: no verified sandbox money path on staging.
- Gate 2/`gate-2` not earned: twelve Must features are not complete.
- Gate 3/`rc-1` not earned: full checklists, video, reviewer findings and submission pending.
- All Should/Could features are deferred. Copilot refunds require seller CONFIRM
  if/when implemented; no working seller copilot is claimed.
- Live pilot is additionally open: merchant country/account verification, own app,
  permissions, policies, isolated deployment, operational checks and controlled real
  transaction. `live_eligible` is an admission gate, not an automatic verification service.
- Public hosting, branch protection, external review, human ratings, video and Devpost
  submission have not been performed. User/team owns account registration and submission.

## Known implementation limitations to resolve next

Quote sessions are required by the proposed interface extension. Outside agents must
start a session through REST before buying. Budget changes in the browser create a new
session; session lifetime/budget persistence will be hardened with the full Playground.
The current store API returns up to ten products; seller catalogs need pagination.
Quotes intentionally retain the accepted server price until expiry; stock/merchant
availability is rechecked at checkout. A provider create error retains its reservation;
automated reconciliation must handle uncertainty before expiry can safely release it.
PayPal callbacks validate amount/country/recipient; post-provider uncertainty remains
an operations case and is never guessed as payment success. Partial refunds and
disputes currently enter review/failure jobs, not automatic settlement decisions.
Jobs hold a row lock through bounded provider calls; process crash can resend a Meta
text after an uncertain response. Process-only rate limiting is not deployment-ready.
The listing adapter is not exposed to unauthenticated uploads and is not connected to
the seller workflow; caption PII filtering/model red-team behavior remains required.

October 10: user explicitly has no provider credentials and requests building all code
first. Auth requires RESEND_API_KEY and EMAIL_FROM; it never returns links/tokens as a
credential-free application shortcut. Browser QA uses an ignored synthetic database
fixture only. Domain/proxy configuration must preserve same-site Lax cookies; deployed
origin/CSRF/CORS behavior remains a release test. Sign-in challenges expire in 15 minutes;
session/link cleanup and merchant verification remain open. Community grids are not AG Studio.
The seller chunk is lazy loaded; public JS remains approximately 284 kB, seller chunk
approximately 879 kB before compression. No Lighthouse/performance target is claimed.
Chrome teardown still hangs; assertions passed but the runner was interrupted.

Next dependency-critical work: configure sandbox/Meta/Anthropic credentials securely,
run and record ADR-001, validate Render blueprint and staging configuration, then
complete Gate 1 before proceeding through the remaining staged acceptance criteria.
