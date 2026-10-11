# AgentShelf

**Made by you. Found by AI.** A seller-first storefront that AI shopping agents can
discover, with server-verified quotes and human-approved PayPal checkout.

Small sellers often have photos and DM conversations, but no catalog a shopping
agent can read. AgentShelf turns seller-approved listings into an agent-readable
store and connects purchases to PayPal. Our first demo follows Meera, a fictional
Jaipur textile seller, selling to overseas buyers.

**Status: listing, buyer-agent, WhatsApp and operations workflows implemented and locally tested. Production/pilot acceptance is still open; no public deployment or real provider payment is verified.**
The source guide is preserved in [docs/BUILD_GUIDE.pdf](docs/BUILD_GUIDE.pdf).
Read [the implementation plan](docs/IMPLEMENTATION_PLAN.md) and [actual status](docs/STATUS.md)
before judging readiness. Sandbox is the judge environment; live rollout is a separate gate.
See [the owner handoff](docs/OWNER_HANDOFF.md) for verified October 11 results and the remaining account, policy, deployment and acceptance tasks.

## Try the local build

Install Python 3.12, uv, Node 22 and Docker. From PowerShell in the repo:

```powershell
./scripts/start-local.ps1
```

Open `http://localhost:5173`, then the demo collection. Choose a product in the buyer
Playground to get a real server quote from the seeded Postgres catalog. No payment
is simulated; checkout remains unavailable until PayPal credentials are configured.
API docs: `http://localhost:8000/docs`. MCP: `http://localhost:8000/mcp`.
See [the runbook](docs/RUNBOOK.md) for configuration, manual setup and verification.

## Money path

1. Seller supplies photos; AI drafts a listing; seller confirms details and price.
2. An MCP client searches live database products.
3. The server snapshots a 15-minute quote with item and shipping totals.
4. Checkout reserves stock and creates one PayPal order for that quote.
5. The human buyer approves on PayPal; the server verifies and captures.
6. A verified webhook reconciles capture and drives seller notification.
7. Seller tracking is sent back to PayPal.

These workflows are implemented and locally tested with controlled provider responses;
the full path still requires real-service acceptance on HTTPS staging. The
[architecture](docs/ARCHITECTURE.md) and [MCP contract](docs/MCP.md) describe the design.

| PayPal capability | Candidate implementation |
| --- | --- |
| OAuth token | Cached client credentials in `paypal.py` |
| Create order with payee | Server quote, stable request ID, approval link |
| Read order | Approval and capture reconciliation |
| Capture | Locked local order and exact amount verification |
| Verify webhook | Five signature headers, registered webhook ID |
| Tracking | Seller-owned tracking push and provider acknowledgement verification |
| Refunds/disputes | Verified event accounting and operator review; no automatic refund decision |
| Catalog | Public storefront and MCP search over PostgreSQL products |

## AI and trust

Anthropic is the selected provider. Model choice requires the Sprint 0 evaluation;
listing and agent results are not fabricated. Models never own prices, stock, budget
or payment approval. Buyer addresses must not enter a model or log.
Listing quality, buyer task success and real latency metrics are pending.
The [evaluation guide](evals/README.md) provides the real-photo listing runner, strict
scoring and human-review templates. Its protocol tests are not quality results.
The same guide provides the fifteen-task sandbox buyer runner, explicit human payment
steps and grounded-price/payment review. Real buyer-task outcomes remain pending.

## Quality checks

```powershell
cd backend
uv run --env-file ../.env ruff check .
uv run --env-file ../.env pytest
cd ../frontend
npm run lint
npm run build
npm run test:e2e
npm run test:e2e:production
```

Browser tests require the seeded local API on port 8000; production checks use the
built dist on port 5174 and verify the missing AG Studio licence gate. Operations
probe tests: `python scripts/tests/test_uptime.py`. See the runbook for the external
uptime workflow setup and notification acceptance; hosted monitoring is not active.

Set `TEST_DATABASE_URL` to a dedicated `_test` Postgres database for integration tests.
Provider mocks prove local failure handling only. Real sandbox tests, public staging,
20-product human evaluation, review gates and the demo video are release prerequisites.

MIT licensed. Built for the PayPal AI Hackathon with Python/FastAPI/MCP/Postgres and
React/Vite. No production eligibility, winning outcome or error-free guarantee is implied.
