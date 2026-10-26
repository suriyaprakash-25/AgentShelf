# AgentShelf — Devpost Submission & Demo Video Guide

> **Note:** Preserve placeholder credentials until staging gates (`Gate 1`, `Gate 2`, `Gate 3`) are verified with real provider keys via `make phase-b-preflight` and `backend/verify_phase_b.py`.

---

## 1. Elevator Pitch (One Sentence)

**AgentShelf** turns WhatsApp product photos and voice notes from independent artisans into an AI-discoverable MCP storefront with server-verified quotes, human-approved PayPal Orders v2 checkout, and automated tracking sync.

---

## 2. Devpost Project Description

### Inspiration
Millions of artisans and small merchants sell over WhatsApp and social DMs using photos and voice notes, yet remain invisible to AI shopping agents that require structured schemas, deterministic inventory locks, and programmable checkout APIs. We built **AgentShelf** so a textile studio in Jaipur—or any independent craftsperson—can publish an agent-ready storefront in 60 seconds without surrendering control of pricing, stock, or payment approval.

### What It Does
- **WhatsApp & Web Listing Studio (`M-2`, `S-3`)**: Sellers send up to 4 product photos (plus an optional voice note or caption). Multimodal AI drafts a structured listing (`title`, `description`, `category`, `attributes`, `tags`, and a non-authoritative `suggested_price_minor`), while the seller explicitly sets and confirms the real price and stock before anything goes live.
- **MCP Streamable HTTP Server (`M-4`, `S-4`, `S-5`)**: Exposes `search_catalog`, `get_product`, `get_quote`, `create_checkout`, and `get_order_status` over `/mcp`, backed by `/.well-known/mcp.json` discovery metadata and `schema.org/Product` JSON-LD on every public store page.
- **Server-Owned Quotes & PayPal Orders v2 (`M-5`, `M-6`, `M-7`, `M-8`)**: AI models never invent prices, shipping, budgets, or payment status. Postgres row locks (`SELECT ... FOR UPDATE`) enforce stock and cumulative session budgets in integer minor units, create PayPal Orders v2 checkouts with direct merchant `payee.email_address`, verify 5-header PayPal webhook signatures, notify the seller on WhatsApp, and push shipping tracking back to PayPal (`POST /v1/shipping/trackers-batch`).
- **Seller Copilot & Multi-Language Storefront (`S-1`, `S-2`, `S-6`)**: Sellers can request 7-day sales & low-stock summaries, issue PayPal capture refunds (`POST /v2/payments/captures/{id}/refund`), send PayPal Invoices (`POST /v2/invoicing/invoices`), mirror products to the PayPal Catalog (`POST /v1/catalogs/products`), and let buyers translate listing copy while keeping server-side USD pricing authoritative.

### How We Built It
- **Backend**: Python 3.12, FastAPI, official `mcp` Python SDK (Streamable HTTP transport), SQLAlchemy 2, Alembic, PostgreSQL 17/18 with full-text GIN indexing, Pillow EXIF-stripping image pipeline, and a durable PostgreSQL job queue (`SELECT ... FOR UPDATE SKIP LOCKED`).
- **Frontend**: React 19, TypeScript, Vite, AG Grid Community, lazy-loaded AG Studio analytics widget, and SSE streaming Buyer Playground.
- **Security & Privacy**: Zero PII or street addresses sent to LLMs; strict input/caption/chat prompt-injection guards; single-use hashed magic links; CSRF double-submit tokens; and privacy-scrubbed Sentry telemetry.

---

## 3. 2:58 Demo Video Shot List (`ROADMAP_SOURCE.md` §13)

| Timestamp | Scene | Action & Key Visuals |
| --- | --- | --- |
| `0:00–0:20` | **The Problem** | Show Meera in Jaipur with textile photos on WhatsApp vs. an AI shopping agent unable to buy from unindexed chat threads. |
| `0:20–0:55` | **WhatsApp Photo + Voice Listing** | Send product photo + voice note on WhatsApp → AI returns structured draft → Meera sets `price 45`, `stock 4`, and replies `YES` → Product appears live on `/s/meera-jaipur`. |
| `0:55–1:40` | **AI Buyer Playground (MCP)** | Open `/playground` with a `$60.00` budget and `GB` destination → Ask `"Find an indigo cotton scarf under $60 shipped to the UK"` → Show live MCP tool trace (`search_catalog` → `get_quote`) in the right-hand Activity panel. |
| `1:40–2:15` | **PayPal Sandbox Checkout** | Click **Confirm total & continue to PayPal** → Approve in PayPal Sandbox buyer popup → Return to `/receipt` showing `paid` status. |
| `2:15–2:40` | **Webhook, WhatsApp Alert & Tracking** | Show verified `PAYMENT.CAPTURE.COMPLETED` webhook → Meera receives formatted WhatsApp paid alert → Meera replies `ship #1001 DHL 1234567890` → PayPal tracker verified and `/receipt` shows `DHL 1234567890`. |
| `2:40–2:58` | **Seller Dashboard & Copilot** | Show `/dashboard` with AG Grid catalog/orders, Seller Copilot 7-day summary, PayPal Catalog mirror, and `/.well-known/mcp.json`. |

---

## 4. Pre-Recording Reset Command

```bash
make demo-reset
```
