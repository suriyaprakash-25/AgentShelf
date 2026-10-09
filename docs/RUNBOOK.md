# Local operation and integration verification

## Start locally

Prerequisites: Python 3.12, uv, Node 22, Docker with a working engine.
PowerShell from the repository root: `./scripts/start-local.ps1`.
The script installs locked dependencies, starts Postgres, migrates, seeds and runs
the API and browser app. Logs and process IDs live in ignored `work/`.

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
Meta delivery is at-least-once after network uncertainty; do not claim exactly-once texts.

## Secrets and live release

Rotate credentials in the provider console and deployment secret store, restart the
API/worker and run readiness plus a sandbox transaction. No secret value goes into
logs, screenshots or source. Sandbox and live have different apps/webhook IDs/databases.
Live mode requires explicit enablement plus a verified merchant account ID and an
eligible seller; this configuration gate is not proof of account eligibility.
Do not enable a merchant until the live release checklist and controlled test pass.

## Backups and demo reset

Managed Postgres backups, a measured restore drill and the safe sandbox reset command
are required release work, currently unverified. Do not erase live order history to
reset a demo. `seed.py` is additive/idempotent, sandbox-only and refuses production.
