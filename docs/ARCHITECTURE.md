# Architecture

```mermaid
flowchart LR
  Seller[Seller: WhatsApp or web] --> API[FastAPI REST and verified webhooks]
  API --> DB[(Postgres: catalog, quotes, orders, jobs)]
  Worker[Worker: listings, alerts, reconciliation] --> DB
  Worker --> LLM[Anthropic: untrusted listing drafts]
  Worker --> Meta[WhatsApp Cloud API]
  Browser[Store / Dashboard / Playground] --> API
  Agent[Buyer agent: normal MCP client] --> MCP[MCP /mcp: four tools]
  MCP --> DB
  MCP --> PayPal[PayPal create order]
  Human[Human buyer] --> Approval[PayPal approval]
  Approval --> API
  API --> Capture[PayPal capture / verify / tracking]
```

One backend and worker share business functions and Postgres. Money is integer USD
minor units. Quote snapshots are immutable. Only available stock is shown; every
reservation and terminal release is transactional. The model cannot supply a price.
Sandbox and live use separate deployments and databases. The live merchant and its
permissions must be verified before live checkout is enabled.

See IMPLEMENTATION_PLAN.md for correctness details and STATUS.md for actual coverage.
