# AgentShelf

## 1. One-Sentence Pitch & Live Demo Links

**Made by you. Found by AI.** AgentShelf turns WhatsApp product photos and voice notes from independent sellers into an AI-discoverable MCP storefront with server-verified quotes, human-approved PayPal Orders v2 checkout, and automated tracking sync.

- **Local Storefront**: `http://localhost:5173/s/meera-jaipur`
- **Buyer Playground (SSE + MCP Trace)**: `http://localhost:5173/playground`
- **Seller Dashboard & Copilot**: `http://localhost:5173/dashboard`
- **MCP Streamable HTTP Endpoint**: `http://localhost:8000/mcp`
- **Agent Discovery Metadata**: `http://localhost:8000/.well-known/mcp.json`
- **Devpost Submission & Demo Script**: [docs/DEVPOST_SUBMISSION.md](docs/DEVPOST_SUBMISSION.md)

**Status: Must (`M-1`–`M-12`) and Should (`S-1`–`S-6`) workflows are implemented and locally tested against PostgreSQL with controlled provider responses. Production/pilot acceptance remains open (`gate_approval: False`) until real provider credentials and HTTPS staging evidence are recorded.**
The source guide is preserved unchanged in [docs/BUILD_GUIDE.pdf](docs/BUILD_GUIDE.pdf). Read [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md), [docs/STATUS.md](docs/STATUS.md), and [docs/OWNER_HANDOFF.md](docs/OWNER_HANDOFF.md) before judging release readiness.

## 2. The Problem

Independent artisans and small merchants often have product photos and customer conversations on WhatsApp, but no structured catalog that AI shopping agents can search, quote, or purchase from safely.

## 3. Architecture Diagram & Data Flow

```text
Seller (WhatsApp / Web Studio)
  │  photos + caption / voice note
  ▼
FastAPI + PostgreSQL 17/18 + Durable Worker Queue
  ├── Listing Workflow (EXIF strip → private R2 → Vision draft → Seller price/stock confirm)
  ├── Public Storefront (/s/{slug}, schema.org JSON-LD, multi-language copy translation)
  ├── MCP Server (/mcp, /.well-known/mcp.json: search_catalog, get_product, get_quote, create_checkout, get_order_status)
  └── PayPal Boundary (Orders v2 create/capture, 5-header Webhook verify, Trackers Batch, Refunds, Invoices, Catalog sync)
```

1. Seller supplies photos (and optional voice note); AI drafts a listing; seller confirms details, price, and stock.
2. An MCP client searches live PostgreSQL products via `/mcp`.
3. The server snapshots a 15-minute quote with item and shipping totals in integer minor units.
4. Checkout reserves stock (`SELECT ... FOR UPDATE`), checks cumulative session budget, and creates one PayPal order for that quote.
5. The human buyer approves on PayPal; the server verifies and captures.
6. A verified PayPal webhook reconciles capture and queues the seller's WhatsApp notification.
7. Seller tracking is pushed back to PayPal (`POST /v1/shipping/trackers-batch`) and appears on the buyer receipt.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/MCP.md](docs/MCP.md) for the full technical design.

## 4. PayPal Integration Matrix

| PayPal capability | Endpoint / API | Implementation module |
| --- | --- | --- |
| OAuth 2.0 token | `POST /v1/oauth2/token` | Cached client credentials in `backend/app/paypal.py` |
| Create order with direct payee | `POST /v2/checkout/orders` | Server quote, `PayPal-Request-Id`, `payee.email_address`, approval URL validation |
| Read order | `GET /v2/checkout/orders/{id}` | Approval, 15-minute reservation expiry, and capture reconciliation |
| Capture order | `POST /v2/checkout/orders/{id}/capture` | Locked local order and exact minor-unit amount verification |
| Verify webhook signature | `POST /v1/notifications/verify-webhook-signature` | Five signature headers + registered `PAYPAL_WEBHOOK_ID` |
| Shipping trackers | `POST /v1/shipping/trackers-batch` | Seller-owned tracking push via web dashboard or WhatsApp `ship #<order>` |
| Capture refunds (`S-1`) | `POST /v2/payments/captures/{id}/refund` | Seller Copilot refund command + verified webhook accounting |
| Invoicing (`S-1`) | `POST /v2/invoicing/invoices` + `/send` | Seller Copilot custom order invoicing |
| Catalog Products (`S-2`) | `POST /v1/catalogs/products` | Mirror live AgentShelf products to PayPal Catalog |

## 5. AI & Agent Capabilities

- **Multimodal Listing Agent (`M-2`, `S-3`, `S-6`)**: Drafts structured listings from 1–4 photos, transcribes WhatsApp voice notes, and translates public listing copy into buyer languages (`es`, `fr`, `de`, `hi`, `ja`) while keeping server-side USD prices and stock authoritative.
- **MCP Buyer Agent (`M-4`, `M-9`)**: Connects over actual Streamable HTTP MCP transport, streams tool traces over SSE, and enforces explicit human confirmation before checkout.
- **Seller Copilot & Analytics (`M-10`, `S-1`)**: Provides 7-day sales/stock summaries, custom PayPal invoicing, capture refunds, and a read-only AG Studio analytics assistant over aggregated store metrics.
- **Trust Boundary**: Models never own prices, stock, shipping, budgets, or payment approval. Street addresses, emails, phones, and secrets are blocked from prompts and logs.

## 6. Evaluation Results & Benchmarks

The [evaluation guide](evals/README.md) provides three reproducible evaluation harnesses:
- **Listing Quality (`backend/evaluate_listings.py`)**: 20-product runner + two-reviewer human-rating scorer (`>= 4.0/5`, zero hallucinated claims, `p95 < 8s`).
- **Buyer Agent (`backend/evaluate_buyers.py`)**: 15-task sandbox runner covering stock, budget, ambiguity, destination, and prompt-injection cases.
- **MCP Search Latency (`backend/evaluate_search.py`)**: 20-query MCP Streamable HTTP benchmark over `>= 1,000` products (`p95 < 1.0s` verified locally against PostgreSQL 17).
- **Phase B Readiness (`backend/verify_phase_b.py`)**: Preflight verifier for provider env vars and ADR-001 Sandbox payee spike (`make phase-b-preflight`).

Real-provider quality and buyer-task scores remain unaccepted (`gate_approval: False`) until run with real credentials on staging.

## 7. Quickstart (`< 10` Minutes)

Install Python 3.12, `uv`, Node 22, and Docker. From PowerShell in the repository root:

```powershell
./scripts/start-local.ps1
```

Or via Make:

```bash
make dev
make demo-reset
```

Open `http://localhost:5173` for the storefront and buyer playground, `http://localhost:8000/docs` for the OpenAPI spec, and `http://localhost:8000/mcp` for the MCP endpoint. Third-party MCP clients (Claude Desktop, Cursor, MCP Inspector) can load [evals/mcp_client_config.json](evals/mcp_client_config.json). See [docs/RUNBOOK.md](docs/RUNBOOK.md) for full configuration and recovery procedures.

## 8. Repository Structure

- `backend/app/` — FastAPI application, MCP server (`mcp_server.py`), PayPal boundary (`paypal.py`), WhatsApp boundary (`whatsapp.py`, `whatsapp_workflow.py`), Seller Copilot (`copilot.py`), listing/buyer agents (`llm.py`, `buyer_agent.py`), and background worker (`jobs.py`, `reconciliation.py`).
- `backend/tests/` — Real PostgreSQL integration, concurrency, security, evaluation protocol, Phase B, and Should-feature test suites.
- `frontend/src/` — React 19 + TypeScript storefront (`App.tsx`), SSE Buyer Playground (`AiBuyer.tsx`), Seller Dashboard & Copilot (`Seller.tsx`), Listing Studio (`ListingStudio.tsx`), and Operations console (`Operations.tsx`).
- `evals/` — Evaluation datasets, review templates, and third-party MCP client config (`mcp_client_config.json`).
- `docs/` — Immutable `BUILD_GUIDE.pdf`, `ROADMAP_SOURCE.md`, `IMPLEMENTATION_PLAN.md`, `STATUS.md`, `DELIVERY_CHECKLIST.md`, `OWNER_HANDOFF.md`, `DEVPOST_SUBMISSION.md`, and `adr/ADR-001-paypal-payee.md`.

## 9. Team, License & Acknowledgements

MIT licensed. Built for the PayPal AI Hackathon with Python, FastAPI, Official MCP SDK, PostgreSQL, and React/Vite. No production merchant eligibility, live payment guarantee, or winning outcome is implied.
