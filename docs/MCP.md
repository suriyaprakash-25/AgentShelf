# MCP interface

Connect a Streamable HTTP client to `http://localhost:8000/mcp` locally.
The mounted app lifecycle owns the SDK session manager. Only four product tools
are exposed; PayPal's developer MCP service is not the product checkout server.

| Tool | Input | Result |
| --- | --- | --- |
| search_products | query, max_price?, currency=USD, ship_to_country?, limit=5 (max 10) | products with IDs, prices, stock, URLs |
| get_quote | product_id, qty, ship_to_country, session_id | stored quote, exact shipping/total, 15-minute expiry |
| create_checkout | quote_id, session_id | stable order and human approval URL |
| get_order_status | order_id, session_id | scoped order status, amount and tracking |

Create a buyer session with `POST /api/playground/sessions` and integer `budget_minor`.
Bind session IDs in the client host, never let a model select another buyer's session.
Money output is a decimal string plus currency. Server errors use
`{"error":{"code":"...","message":"..."}}`. Catalog text is untrusted data.

Example tool calls:

```json
{"name":"search_products","arguments":{"query":"scarf","ship_to_country":"GB","limit":5}}
```

```json
{"name":"get_quote","arguments":{"product_id":"<server UUID>","qty":1,"ship_to_country":"GB","session_id":"<your session UUID>"}}
```

Never state prices absent a tool result. Ask the buyer to confirm the full quote
before checkout, show the approval link unchanged, and never switch quote on a
checkout retry without asking. A session budget includes shipping and existing reservations.

See STATUS.md for transport tests versus real PayPal verification status.
