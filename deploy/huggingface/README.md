---
title: AgentShelf API
emoji: 🛍️
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 5.23.1
python_version: "3.12"
app_file: space_main.py
pinned: false
short_description: MCP storefront API with PayPal sandbox checkout
---

# AgentShelf API

Backend for AgentShelf: FastAPI, the MCP server (`/mcp`), PayPal Orders v2 checkout and
the durable job worker. The browser app runs on Vercel and forwards API traffic here.
The Gradio runtime only hosts the process; there is no Gradio UI.

Source code and documentation: https://github.com/suriyaprakash-25/AgentShelf
