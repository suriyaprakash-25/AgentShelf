# AgentShelf — Devpost submission

Copy each block into the matching Devpost field. Every number below comes from a recorded
run (see `docs/STATUS.md`); keep it that way when editing.

## Elevator pitch (183 / 200 characters)

Turn WhatsApp product photos into a store any AI shopping agent can find, quote and buy from, with human-approved PayPal checkout. Made by small sellers, found by AI, paid via PayPal.

## About the project (paste everything between the lines)

---

## Inspiration

Meera makes block-printed scarves in Jaipur. Her whole business lives in WhatsApp: photos, voice notes, "is this still available?", a PayPal link typed by hand. Buyers are starting to shop through AI assistants, and those assistants can't read a WhatsApp thread. They need a catalog they can search, a price they can trust and a checkout they can call.

PayPal's agentic commerce work reaches merchants who already sit on a platform. Sellers like Meera aren't on any platform, so they're about to become invisible. We wanted to give them an agent-ready store without asking them to learn e-commerce.

## What it does

**For the seller: photos in, store out.**
- The seller sends product photos (WhatsApp or our web Listing Studio). A vision model drafts the title, description, category, attributes and a *suggested* price.
- **AI never sets the price.** The seller confirms price and stock before anything goes live, then edits by text (`price 45 #12`, `stock 0 #12`).
- Every store gets a public page with schema.org product data and its own **MCP endpoint**.

**For the buyer's agent: a store it can actually buy from.**
- Any MCP client can call four tools: `search_products`, `get_quote`, `create_checkout`, `get_order_status`.
- `get_quote` snapshots item price, shipping and an expiry on the server. The model can't invent or change an amount.
- `create_checkout` locks stock and the shopper's budget in Postgres, then creates a **PayPal Orders v2** order paid straight to that seller.
- **A human always approves the payment on PayPal.** Agents find and propose; people pay.

**After the sale.** Verified PayPal webhooks update the order, the seller gets a WhatsApp alert, and `track #A123 DHL 1234567890` pushes tracking to the PayPal order. A seller dashboard built on AG Grid and AG Studio shows products and orders, plus refunds, invoices and a 7-day sales summary.

**Try it without installing anything:** the Buyer Playground is a chat with an AI shopping agent wired to our real MCP server. Every tool call shows live, under a budget cap.

## How we built it

- **Backend:** Python, FastAPI and the official MCP Python SDK (stateless Streamable HTTP), so the MCP server scales behind a load balancer. SQLAlchemy 2 and Alembic on PostgreSQL 17.
- **Money is integer minor units end to end.** Reservations use `SELECT … FOR UPDATE`; the job queue uses `SKIP LOCKED` with LISTEN/NOTIFY wake-ups, retries and dedupe.
- **PayPal (REST, idempotent `PayPal-Request-Id`):** Orders v2 create and capture, webhook signature verification, order tracking, refunds, invoicing, Catalog Products and dispute reads. A circuit breaker isolates PayPal outages.
- **AI:** a provider strategy over Gemini and Claude. A strict schema checks every draft, and we screen captions and chat for personal data and prompt injection.
- **Frontend:** React 19, TypeScript and Vite, with AG Grid and AG Studio for the seller dashboard.
- **Storage:** private Cloudflare R2 for photos, with EXIF stripped first.
- **Quality:** 340 backend tests against real Postgres (locking, constraints, migrations) and 16 Playwright browser tests with axe accessibility checks.

## Challenges we ran into

- **Gemini 3 tool calling broke on round two.** The first real-key run showed that every buyer chat failed after the first search: Gemini 3 requires its `thoughtSignature` back on each function call. Our provider-neutral history now carries it and strips it before any other model sees it.
- **Reasoning ate the answer.** One listing draft spent 1,150 of 1,200 output tokens thinking, so the JSON got cut off. We now set an explicit reasoning level and reserve a separate token allowance. Real drafts take 4.4 s and 10.0 s.
- **Agents and money don't mix by default.** We made the server the only source of truth for price, stock, budget and payment status, and kept a human approval step on every payment.
- **Load spikes and failures.** We moved to ranked full-text search with indexes, a short read-through cache and an optional read replica. Request deadlines turn a hung database into a fast 503 instead of a hang.

## Accomplishments that we're proud of

- **A real end-to-end agent purchase in PayPal sandbox:** Gemini made 4 MCP searches and requested a quote in 12.7 s, and after human confirmation the order was created in 3.1 s. Our $40.00 and PayPal's $40.00 match, paid to the right seller.
- **Load:** 151 requests/s on product search from a single local worker (p95 2.8 s, 0 errors at 100 concurrent requests).
- **Failover:** zero errors across 2,000 requests while one of two web replicas was stopped mid-burst.
- **Accessibility:** axe finds zero violations on our phone-width screens.

## What we learned

Agentic commerce is mostly a trust problem. The model is great at finding and explaining; it shouldn't own prices or payments. Clear tool contracts plus a human approval step make agent shopping feel safe. Testing against real providers early catches the bugs that mocks hide.

## What's next for AgentShelf

- A pilot with real sellers in India selling to overseas buyers. Live payments are enabled one merchant at a time, after PayPal eligibility checks.
- More agent surfaces through the same MCP endpoint, and voice-first listing in regional languages.
- Payouts for sellers who can't receive payments directly, and shipping-label integration.

---

## Built with (Devpost tags)

python, fastapi, postgresql, sqlalchemy, alembic, model-context-protocol, paypal, paypal-orders-v2, paypal-webhooks, gemini, anthropic-claude, react, typescript, vite, ag-grid, ag-studio, cloudflare-r2, whatsapp-cloud-api, resend, docker, nginx, render, playwright, pillow, server-sent-events

## "Try it out" links

1. GitHub: https://github.com/suriyaprakash-25/AgentShelf
2. Live demo: the Render URL once deployed (Buyer Playground at `/playground`)
3. MCP endpoint: `<live URL>/mcp`, discovery at `<live URL>/.well-known/mcp.json`

## Image gallery (3:2, under 5 MB each)

1. Landing page hero.
2. Buyer Playground mid-conversation, with the MCP tool trace visible.
3. Quote card, then the PayPal sandbox approval screen.
4. Seller Listing Studio showing an AI draft from a photo.
5. Seller dashboard (AG Grid products and orders).
6. A public store page (`/s/meera-jaipur`).
7. Architecture diagram (from `docs/ARCHITECTURE.md`).

## Demo video (YouTube, public or unlisted, under 3:00)

| Time | Scene | Say |
| --- | --- | --- |
| 0:00–0:15 | Store page for Meera's Jaipur Studio | "Meera sells scarves from Jaipur on WhatsApp. AI shopping agents can't see her. AgentShelf fixes that." |
| 0:15–0:50 | Listing Studio: upload a scarf photo, draft appears, set price and stock, publish | "She sends a photo. AI drafts the listing in seconds, but she sets the price. AI never does." |
| 0:50–1:40 | Buyer Playground: "a handmade gift from Jaipur under $60, shipped to the US"; tool trace shows `search_products`, then `get_quote` | "Any AI agent can shop her store through MCP. The server writes the quote, so the model can't change the price." |
| 1:40–2:20 | Confirm, then PayPal sandbox approval, then receipt | "A human approves every payment on PayPal. The order is paid straight to Meera." |
| 2:20–2:45 | Seller dashboard: the new paid order | "Meera sees the order and gets a WhatsApp alert." (Show the alert only if it was recorded live.) |
| 2:45–2:58 | Logo and links | "AgentShelf: made by you, found by AI, paid with PayPal." |

Record against the deployed URL when possible, and only show flows that work live on camera.
