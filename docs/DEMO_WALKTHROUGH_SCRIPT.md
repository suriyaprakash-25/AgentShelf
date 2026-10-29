# AgentShelf — 3-Minute Demo Video Walkthrough Script

**Target Duration**: 2 minutes 45 seconds (Limit: 3 minutes)  
**Platform URL**: `http://localhost:5173`  
**Audio / Delivery Style**: Confident, articulate, developer-to-developer tone.  

---

## Storyboard Overview

```
 [0:00-0:35] Hook & Landing Page  -->  [0:35-1:15] Artisan Catalog & Studio
                                                      │
 [2:35-2:50] Operations & Wrap-Up <--  [2:05-2:35] PayPal Checkout & Receipt  <--  [1:15-2:05] AI Buyer Playground & MCP
```

---

## Segment-by-Segment Run Sheet

### 1. The Hook: The Missing Bridge for Independent Commerce (0:00 – 0:35)
- **Screen**: Start on `http://localhost:5173` (Top of the landing page).
- **Action**: Smoothly scroll from Hero banner past the live proof bar (127+ sellers, 100% server-verified stock) down to the 3-Pillar Ecosystem cards.
- **Voiceover**:
  > *"Autonomous AI agents are revolutionizing shopping. But for millions of independent artisans and global makers who run their business on WhatsApp, agentic commerce has been completely out of reach.*  
  > *Meet **AgentShelf**: the world's first open-standard, agent-ready commerce platform. It gives independent makers sovereign control over their craft, exposes their live inventory to autonomous shopping agents via the official Model Context Protocol (MCP), and settles every transaction through PayPal's trusted global infrastructure."*

---

### 2. The Artisan Experience: Authentic Crafts & Sovereign Control (0:35 – 1:15)
- **Screen**: Click into **Suriya Craft Studio** (`http://localhost:5173/s/suriya-craft-studio`).
- **Action**: Hover over the product cards (Terracotta Filter Coffee Cups, Thanjavur Hammered Brass Lamp, Chettinad Granite Mortar and Pestle, Kanchipuram Silk Runner). Then switch briefly to **Seller Dashboard** (`http://localhost:5173/dashboard`).
- **Voiceover**:
  > *"Here is Suriya Craft Studio, showcasing authentic South Indian handcrafted goods. Notice the high-fidelity imagery and server-verified availability.*  
  > *Artisans list their products in seconds simply by texting photos and a quick voice note over WhatsApp or through our web Listing Studio. Our vision pipeline drafts accurate titles, descriptions, and categories.*  
  > *Crucially: AI never sets the price. The artisan explicitly confirms their price in integer minor units and their available inventory before anything goes live."*

---

### 3. The Buyer Experience: MCP Protocol & Agent Playground (1:15 – 2:05)
- **Screen**: Navigate to **Buyer Playground** (`http://localhost:5173/playground`).
- **Action**:
  1. Show the shopping session settings (Budget: `$60.00 USD`, Ship to: `United Kingdom`).
  2. Click on the prompt suggestion pill or select a product: **"Terracotta Filter Coffee Cup Set" ($24.00)**.
  3. Expand the **"MCP Tool Activity"** trace accordion to show the `search_catalog` and `get_quote` events.
- **Voiceover**:
  > *"Now let's switch to the buyer. Autonomous AI shopping agents don't browse HTML like humans — they query AgentShelf using the official Model Context Protocol at `/.well-known/mcp.json`.*  
  > *In our Buyer Playground, a shopper specifies their budget and destination. When the agent finds a match, AgentShelf generates an **immutable, cryptographically bound quote**.*  
  > *The quote snapshots the title, exact unit price, and shipping calculation with an authoritative expiry timer. No prompt injection or hallucinatory pricing can alter the transaction amount."*

---

### 4. Seamless Checkout: PayPal Sandbox Authorization & Receipt (2:05 – 2:35)
- **Screen**: Click **"Confirm this quote and create checkout"**.
- **Action**: Click **"Approve payment on PayPal"**, complete the approval, and land on the confirmation page (`/receipt?order=...`).
- **Voiceover**:
  > *"When the buyer confirms the quote, AgentShelf acquires an atomic row lock on the inventory and reserves the budget before communicating with PayPal.*  
  > *The buyer is redirected to PayPal for final human authorization. Once approved, our background worker executes an authoritative capture, locks the financial audit trail, and immediately issues a digital receipt with end-to-end carrier tracking."*

---

### 5. Enterprise Invariants & Operations (2:35 – 2:50)
- **Screen**: Open the **Operations Console** (`http://localhost:5173/operations`).
- **Action**: Show worker heartbeats, recent jobs, and atomic lock statistics.
- **Voiceover**:
  > *"Under the hood, AgentShelf is built on PostgreSQL 17 with strict ACID guarantees: zero floating-point arithmetic, idempotent webhooks, and automatic 15-minute unapproved reservation release.*  
  > *AgentShelf: Made by you. Found by AI. Settled by PayPal."*

---

## Practice Checklist Before Recording

- [ ] Chrome / browser window set to standard 1080p (1920×1080) at 100% zoom.
- [ ] Backend running (`http://127.0.0.1:8000`) and Vite running (`http://127.0.0.1:5173`).
- [ ] Docker PostgreSQL container healthy on `127.0.0.1:5433`.
- [ ] Test tabs pre-opened in order:
  1. Tab 1: `http://localhost:5173/` (Home)
  2. Tab 2: `http://localhost:5173/s/suriya-craft-studio` (Suriya Craft Studio)
  3. Tab 3: `http://localhost:5173/playground` (Buyer Playground)
  4. Tab 4: `http://localhost:5173/operations` (Operations)
