# Local operation and integration verification

## Start locally

Prerequisites: Python 3.12, uv, Node 22, Docker with a working engine.
PowerShell from the repository root: `./scripts/start-local.ps1`.
The script installs locked dependencies, starts Postgres, migrates, seeds and runs
the API, browser app and job worker. Logs and process IDs live in ignored `work/`.

Manual equivalent: copy `.env.example` to `.env`, `docker compose up -d --wait db`,
then in `backend` run `uv sync --frozen`, `uv run --env-file ../.env alembic upgrade head`,
`uv run --env-file ../.env python seed.py`, and
`uv run --env-file ../.env uvicorn app.main:app --host 127.0.0.1 --port 8000`.
In `frontend`, `npm ci` then `npm run dev`.

Docker failure does not authorize a factory reset. A project-local native Postgres
runtime can serve the same database on localhost:5433; use `-SkipDatabase` only after
it is listening. Native cluster startup is a development fallback, not deployment.
Tests use a separate database with a name ending in `_test`; they truncate its tables.

## Sandbox accounts and ADR-001

Create the AgentShelf REST app, three business seller sandbox accounts, and two
personal buyer sandbox accounts (US and UK). Configure client ID/secret in an ignored
env file, never the README. Replace the fictional seeded seller email with an actual
sandbox business account using a controlled database update. That account must match
the payee receiving the test capture. Never point demo catalog data at live credentials.

Register the publicly reachable HTTPS `/webhooks/paypal` URL and put its ID in the
same deployment's secret configuration. Subscribe to the seven events in the guide.
Use real sandbox payments for signature tests; simulator payloads are not evidence.
Perform the five ADR-001 checks and record sanitized order/capture/event IDs and
pass/fail results. Credentials and full emails are excluded from committed evidence.
Provider error responses are deliberately not logged because they can contain PII.

## Uncertain payment

Keep the same quote and local order; repeat create/capture with the same request ID.
Read the provider order before marking paid or releasing stock. Never manually set an
uncertain order to paid. The candidate implementation persists reservations before
provider creation; automated expiry/reconciliation remains tracked in STATUS.md.

## Webhook replay and failed jobs

Keep PayPal's event ID stable; delivery duplicates are verified then acknowledged
without additional processing. Do not bypass signature verification for a replay.
Worker startup: `uv run --env-file ../.env python worker.py` in backend.
Jobs retry at most five times and store only error codes. Inspect failed job codes in
Postgres until the authenticated operations screen is implemented.
Handler exceptions roll back their database writes before scheduling the retry.
Unexpected handler errors use `JOB_HANDLER_FAILED`; sensitive exception text is excluded.
Database connection/commit failures still surface to the process supervisor.
Meta delivery is at-least-once after network uncertainty; do not claim exactly-once texts.

## Email sign-in and dashboard configuration

Configure `RESEND_API_KEY` and a verified sender in `EMAIL_FROM`; register the same
values as managed secrets on staging. The adapter uses Resend's bounded email API.
No email or authentication bypass is provided when credentials are missing.
Web onboarding verifies the sign-in email with a single-use 15-minute link before
creating a store. It does not verify ownership of the submitted PayPal email or
payment receiving eligibility. Links use a URL fragment, consumed by a POST, so
access logs do not receive the secret. Seller session values are hashed in Postgres.
Cookies are HttpOnly/Secure/Lax outside `APP_ENV=local`; local HTTP is development only.

For deployed credentialed cookies, use a same-origin API proxy or frontend/API
subdomains sharing your own site. Separate unrelated hosts will not reliably send
SameSite=Lax cookies. `FRONTEND_URL` must exactly match the browser origin; configure
the proxy/CORS and verify the real browser flow before release. Seller writes require
both that Origin and the session-bound CSRF token from `/api/me`.

The dashboard currently uses AG Grid Community, with a custom theme, filters,
sorting, pagination and current-page CSV exports. It is not an AG Studio integration
or a claim that the sponsor checklist passes. Session/link expiry cleanup and a full
policy/merchant verification workflow remain release work.

## Seller fulfilment

Authenticated sellers can view their own shipping details and submit a single-parcel
carrier/tracking number. The provider adapter confirms the tracker ID before moving
paid to shipped; uncertain POST results re-read the same order. Repeating the same
parcel is idempotent. Changing an already shipped parcel currently requires operations
review; multi-parcel shipping and corrections are not implemented. No notification
email is requested from PayPal by this endpoint. WhatsApp tracking commands and actual
sandbox receiving/tracking permissions still need acceptance evidence.

Provider references: [Resend email API](https://resend.com/docs/api-reference/emails/send-email),
[FastAPI cookies](https://fastapi.tiangolo.com/advanced/response-cookies/),
[AG Grid React](https://www.ag-grid.com/react-data-grid/getting-started/) and
[PayPal tracking](https://developer.paypal.com/api/orders-v2/track-orders/use/).

## Secrets and live release

Rotate credentials in the provider console and deployment secret store, restart the
API/worker and run readiness plus a sandbox transaction. No secret value goes into
logs, screenshots or source. Sandbox and live have different apps/webhook IDs/databases.
Live mode requires explicit enablement plus a verified merchant account ID and an
eligible seller; this configuration gate is not proof of account eligibility.
Do not enable a merchant until the live release checklist and controlled test pass.

## Backups and demo reset

The local backup/restore drill and guarded sandbox reset are implemented and tested.
Managed Postgres backups, retention and a staged restore drill remain release requirements. Do not erase live order history to
reset a demo. `seed.py` is additive/idempotent, sandbox-only and refuses production.

## Listing, buyer and WhatsApp setup

Set ANTHROPIC_API_KEY and select ANTHROPIC_MODEL only after the measured photo spike.
The dashboard accepts one to four photos via authenticated, CSRF-protected raw uploads,
processes EXIF-free bounded JPEGs and queues the model job. Run the worker separately:
`uv run --env-file ../.env python worker.py` from backend. Inspect draft history; enter
seller-approved price and stock, then confirm publication. Missing model credentials
leave manual product creation available; missing credentials never generate fake drafts.

Use MEDIA_BACKEND=r2 outside development. Configure R2_ENDPOINT, R2_BUCKET,
R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY identically in API and worker. Keep the bucket
private: the API authorizes draft photos and only serves photos of active public products.
Local files in work/media are a development fallback, not durable deployment storage.
Verify one API upload -> worker read -> public photo after publication before release.

Configure Meta app signature/verify secrets, access token and phone-number ID. Register
the HTTPS WhatsApp webhook and approved recipients. Onboarding asks store name, country,
email, PayPal email and consent; redeem the email challenge before the phone is bound.
The worker also needs RESEND_API_KEY and EMAIL_FROM. Send up to four photos; nearby
messages are grouped for a single draft. Price and stock must be seller-entered before
YES. Web review is the fallback for title/description changes. Duplicate messages use
stable IDs, but a crash after a successful Meta send can repeat a text.

For paid alerts outside the permitted conversation window, configure
WHATSAPP_PAID_TEMPLATE to a Meta-approved utility template with four body parameters:
order reference, item title, formatted amount, and shipping address.
WHATSAPP_TEMPLATE_LANGUAGE defaults to en_US and must match its approval. Without a
template, free-form sends require an active provider-permitted window; delivery can fail.
Do not mark alerts accepted until actual approved-template delivery/timing is recorded.

Playground chat uses the actual /mcp server, not private business shortcuts. The server
injects buyer session/country, enforces a budget, exposes tool results and requires quote
confirmation before creating an approval link. The buyer still approves on PayPal.
Missing Anthropic credentials expose the manual catalog explorer. Missing PayPal
credentials return an explicit unavailable error rather than a pretend payment.

## Operator and recovery procedures

From backend, grant an already verified active seller the operator role using
`uv run --env-file ../.env python maintenance.py operator <verified-email>`.
Use `--revoke` to remove it. This is a local administrative action with an audit record;
ordinary sellers cannot grant roles. Sign in and open /operations. Inspect worker ages,
failed-job codes, order/provider references and adjustments. Retry only after resolving
the cause; retries are role/CSRF protected and audited. Stale heartbeat >90 seconds is
visible locally; test the actual external alert channel separately.

SENTRY_DSN is optional. Only explicitly emitted sanitized application messages are sent;
request bodies, URLs, user details, exception locals and model/provider payloads are
excluded. Real Sentry receipt and operational alert routing remain acceptance checks.

Reconciliation runs while the worker is alive. A lost capture response retains the
approved intent and stable capture key; re-read the same PayPal order before retrying.
Approved captures older than the automated window enter review. A lost create response
without a known provider ID cannot be safely guessed: correlate through PayPal using
sanitized request/order references. Do not create a replacement order or release stock
without verified payment/void evidence. Current expiry releases only provider VOIDED
orders; the guide's 15-minute requirement needs an explicit validated policy decision.

Partial/full refunds are recorded only after reading a completed PayPal refund and
matching its capture/currency/amount. Refunds do not automatically restock goods or
relax cumulative buyer budgets. Partial refunds block fulfilment for human review.
Disputes and reversals preserve review states even after a dispute is resolved until
its financial outcome is verified. There is no automatic refund action or operator
button that silently clears an unresolved payment. Resolve with PayPal and record a
reviewed financial/fulfilment decision before changing local records.

## Local backup, restore drill and cleanup

Use PostgreSQL clients matching the server major version. From backend:
`uv run --env-file ../.env python maintenance.py backup <new-private-path> --pg-dump <client-path>`.
Existing backups are never overwritten. Keep dumps outside shared/public directories;
Windows permissions require a separately verified private ACL. Encrypt and retain
managed backups according to the approved policy; a local dump is not managed backup proof.

Create a new empty loopback sandbox database ending `_restore_test`; put its URL in
RESTORE_DATABASE_URL locally. Then run
`uv run --env-file ../.env python maintenance.py restore-drill <dump-path> --pg-restore <client-path>`.
The command refuses live, remote and ordinary databases and uses a single transaction.
Verify catalog, quotes, reservations, budgets and audit records, then remove only the
specific temporary drill database you created. Never restore over live payment history.
The automated test creates and removes its own random isolated drill database.

`uv run --env-file ../.env python maintenance.py demo-reset --confirm RESET_SYNTHETIC_SANDBOX_STOCK`
only resets the unchanged fictional sandbox seed's stock. It refuses pending reservations,
production/live mode or a changed seed merchant/payee; it preserves payment history.
It is not suitable for a store already changed to a real sandbox seller without an
explicit separately reviewed reset policy.

Hourly worker cleanup deletes expired authentication records and sufficiently stale
quota buckets and clears buyer chat text after 30 days. Payment/budget/audit records
are retained. It can also run via `maintenance.py cleanup-expired`. Orphaned media,
legacy webhook personal data and address retention need their own audited cleanup plan.

## Same-origin deployment and acceptance

Build the root Dockerfile: frontend assets and API run in one non-root container.
The API serves UI routes and /assets; the worker uses the same image. render.yaml
contains the web service, worker and database. Set PUBLIC_API_URL and FRONTEND_URL to
the exact same HTTPS origin; deployed startup rejects differing origins or absent R2
and PayPal configuration. Run migrations before the new API starts, configure all
secrets on both services as applicable, and ensure external MCP self-calls can reach
PUBLIC_API_URL. Do not publish the fictional catalog as a real merchant.

Local container build and isolated PostgreSQL 17 startup/migration/catalog/UI checks passed.
Hosted deployment is not verified. CI now includes a container build
and matching PostgreSQL 17 backup clients, but remote results are not yet available.
Validate the image, clean-machine startup, migrations, readiness, worker heartbeat,
private storage, proxy IP trust/shared quotas, secure cookie/CSRF/CSP, provider callbacks,
backups and actual alerts on funded staging. Keep sandbox/live secrets, database and
storage isolated. Do not enable live mode solely because credentials exist.

Before signing off: record ADR-001; real email/Meta/R2/Anthropic acceptance; signed
PayPal money-path and tracking tests; 20 real listing products and 15 buyer tasks;
image injection/PII evaluation; 1,000-product staging latency; full red-team, Lighthouse
and mobile results; required AG Studio framework/licence; independent external-client
purchase under five minutes; managed restore and operator recovery drills. Then obtain
the source gate reviews. Only after Gate 2 implement Should items; Gate 3 and live
merchant eligibility/approved transaction remain separate release steps.

## AG Studio analytics and licence

Open shop analytics from the seller dashboard. The actual Studio component shows a
custom shop-summary widget and two aggregate data sources; its framework analyst asks
the API for seller-owned totals. No buyer identities, product text or provider secret
is sent from the browser to the model. Questions are standalone and bounded; the
analyst cannot update stock, prices, orders or payments. Real model quality still
requires acceptance even though controlled browser and ownership tests pass.

Local development can render Studio without activating a trial. Production activation
requires the sponsor's deployment licence covering judging, configured as frontend
build variable VITE_AG_STUDIO_LICENSE_KEY. This licence is browser-visible; never use
that variable for an Anthropic/PayPal/Meta secret. The Docker frontend stage accepts
`--build-arg VITE_AG_STUDIO_LICENSE_KEY=<licence>`; configure the managed build argument
through the deployment owner. Without it, production preserves ordinary seller tables
and shows an unavailable analytics notice. No trial or external account was activated.
The optional Studio chunk is large; assess mobile layout, CSP and loading performance
on staging before enabling it for the pilot.

SDK reference: https://www.ag-grid.com/studio/react/installation/ and
https://www.ag-grid.com/studio/react/ai-direct-llm-runner/ .


## Bounded retention review and lost-create recovery

Run `uv run python maintenance.py media-cleanup --days 7 --limit 100` or
`uv run python maintenance.py privacy-review --days 30 --limit 100` first.
Both default to dry-run and return counts without personal data. R2 inventory and
legacy inboxes return a continuation cursor; pass it with `--cursor`. Local media
inventory scans only its first bounded page and has no pagination; do not infer a
whole-storage audit from that result. Every draft/product reference is retained.

Apply only after the owner approves the retention policy and the dry-run findings:
add `--apply --operator-email <verified-operator-email> --confirm APPLY_REVIEWED_RETENTION`.
An active operator is checked again in the mutation transaction. No production
retention action has been executed during local verification. Keep managed backup
retention and recovery requirements aligned with the approved policy.

For an unknown create response, inspect the seller PayPal account and independently
identify the candidate PayPal order. The operator dashboard correlation form performs
only a provider GET and verifies the one purchase unit, local custom ID, seller payee,
currency and exact quoted amount. It records an audit and queues reconciliation;
it cannot approve a buyer or initiate a new capture. Review mismatches in PayPal.
Uncertain reservations remain held; VOIDED proof is still required for safe release.

## October 10 workstation verification incident

D: filled during verification. Generated dependencies/caches were preserved on E:;
frontend/node_modules currently points to E:/AgentShelf-local-frontend-20261010/node_modules.
For local Node commands use NODE_OPTIONS=--preserve-symlinks --preserve-symlinks-main
if required. Source, lockfiles, database and roadmap stayed in their original locations.
No unrelated files or Docker volumes were deleted. Automatic review rejected cache
deletion; the fallback preserved the named caches instead. Free adequate D: space
and restore Docker Desktop health before repeating compose.verify.yaml verification.
The local Docker engine responds HTTP 500. GitHub CI on e38a0f9 builds and verifies
the new hardening revision against PostgreSQL 17; use that exact run as evidence,
not the earlier local image. No actual provider or funded host is verified by it.
