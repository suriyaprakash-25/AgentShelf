---
title: AgentShelf API
emoji: 🛍️
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: MCP storefront API with PayPal sandbox checkout
---

# AgentShelf API

Backend for AgentShelf: FastAPI, the MCP server (`/mcp`), PayPal Orders v2 checkout and
the durable job worker. The browser app runs on Vercel and forwards API traffic here.
This is a Docker Space: the image installs the backend from `backend/uv.lock`, and
`start.sh` runs migrations, the sandbox demo seed, the supervised worker and the API
on port 7860 as uid 1000. It needs no GPU and runs on CPU basic hardware.

Source code and documentation: https://github.com/suriyaprakash-25/AgentShelf
