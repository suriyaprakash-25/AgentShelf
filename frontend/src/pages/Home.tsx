import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type PlatformStats } from "../api";
import {
  ArrowRight,
  Bot,
  Camera,
  Check,
  CheckCircle,
  ChevronDown,
  Cpu,
  Globe2,
  Layers3,
  Lock,
  ShieldCheck,
  Sparkles,
  Zap,
  Store as StoreIcon,
} from "lucide-react";

const numberFormat = new Intl.NumberFormat("en-US");

function plural(count: number | undefined, one: string, many: string) {
  return count === 1 ? one : many;
}

function Stat({ value, label }: { value: number | undefined; label: string }) {
  return (
    <div className="stat">
      <strong aria-live="polite">
        {value === undefined ? "—" : numberFormat.format(value)}
      </strong>
      <span>{label}</span>
    </div>
  );
}

export function Home() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [stats, setStats] = useState<PlatformStats | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api<PlatformStats>("/api/stats", undefined, controller.signal)
      .then(setStats)
      .catch(() => setStats(null));
    return () => controller.abort();
  }, []);

  const toggleFaq = (idx: number) => {
    setOpenFaq((prev) => (prev === idx ? null : idx));
  };

  return (
    <>
      {/* Top Value Banner */}
      <div className="home-top-announcement">
        <span className="pill green">
          <Zap size={13} /> AGENTIC COMMERCE INFRASTRUCTURE
        </span>
        <span className="announcement-text">
          Bridging independent artisans and autonomous AI shopping agents via
          Model Context Protocol (MCP) & PayPal.
        </span>
      </div>

      {/* Hero Section */}
      <section className="hero page">
        <div className="eyebrow">
          <span className="dot" />A NEW WAY FOR SMALL SHOPS TO BE FOUND
        </div>
        <div className="hero-grid">
          <div>
            <h1>
              Made by you.
              <br />
              Found by <em>AI.</em>
            </h1>
            <p className="lede">
              Your craft deserves a bigger shelf. AgentShelf turns handcrafted
              product photos into an agent-ready catalog that AI assistants can
              discover and quote over open Model Context Protocol (MCP)—with
              human approval on PayPal every step of the way.
            </p>
            <div className="actions">
              <Link className="button" to="/s/meera-jaipur">
                Explore the demo collection <ArrowRight size={18} />
              </Link>
              <Link className="text-link" to="/playground">
                Try the buyer playground <ArrowRight size={16} />
              </Link>
              <Link className="button secondary" to="/dashboard">
                <StoreIcon size={16} /> Seller Studio & Login
              </Link>
            </div>
            <div className="trust">
              <ShieldCheck size={17} /> Human-approved PayPal checkout{" "}
              <span>·</span>
              <Bot size={17} /> Native Model Context Protocol (MCP){" "}
              <span>·</span>
              <Globe2 size={17} /> Built for cross-border discovery
            </div>
          </div>
          <div
            className="hero-art"
            aria-label="Illustration of an artisan scarf and a product listing"
          >
            <div className="art-note">DUAL-SIDED COMMERCE ENGINE</div>
            <div className="fabric">
              <span className="fabric-label">
                AGENT READY
                <br />
                MCP PROTOCOL
              </span>
            </div>
            <div className="listing-card">
              <div className="card-icon">
                <Sparkles size={19} />
              </div>
              <span className="eyebrow">ZERO-SCRAPE CATALOG</span>
              <h3>An agent-ready shop.</h3>
              <p>Photos → Vision AI draft → Your verified price.</p>
              <div className="listing-bottom">
                <span>
                  <Check size={13} /> 100% human-approved
                </span>
                <ArrowRight size={20} />
              </div>
            </div>
            <span className="art-caption">
              Direct connection between small makers and AI shopping agents.
            </span>
          </div>
        </div>
      </section>

      {/* Proof / Stats section: counts are measured from the live catalog. */}
      <section
        className="proof page"
        aria-label="Catalog at a glance"
        style={{ paddingTop: 0, paddingBottom: 0 }}
      >
        <div className="proof-grid">
          <Stat
            value={stats?.sellers}
            label={plural(stats?.sellers, "Seller", "Sellers") + " live now"}
          />
          <Stat
            value={stats?.live_products}
            label="In-stock products agents can buy"
          />
          <Stat
            value={stats?.seller_countries}
            label={plural(
              stats?.seller_countries,
              "Seller country",
              "Seller countries",
            )}
          />
          <div className="stat">
            <strong>100%</strong>
            <span>Server-verified stock & pricing</span>
          </div>
        </div>
      </section>

      {/* Trust Strip */}
      <section className="strip">
        <span>SELLER FIRST.</span>
        <span>VISION AI DRAFTING.</span>
        <span>OPEN MCP PROTOCOL.</span>
        <span>INTEGER MINOR UNITS.</span>
        <span>HUMAN PAYPAL APPROVAL.</span>
      </section>

      {/* Three Pillars: Who It's For */}
      <section className="page ecosystem-section">
        <div className="section-header">
          <span className="eyebrow">A COMPLETE THREE-SIDED PLATFORM</span>
          <h2>Built for artisans. Ready for AI agents. Safe for buyers.</h2>
          <p className="section-sub">
            Traditional marketplaces trap independent makers in complex software
            and steep commission cuts. AgentShelf builds the direct open
            protocol bridge so AI assistants can find and shop from small
            makers.
          </p>
        </div>
        <div className="ecosystem-grid">
          {/* Card 1: Artisans */}
          <div className="ecosystem-card">
            <div className="eco-badge artisan">
              <StoreIcon size={18} /> For Independent Artisans
            </div>
            <h3>From Camera to Global Shelf</h3>
            <p>
              No coding, no SEO keyword stuffing, and no complex inventory
              software. List your work in seconds.
            </p>
            <ul className="eco-list">
              <li>
                <Check size={15} /> <strong>WhatsApp & Web Uploads:</strong>{" "}
                Snap 1–4 photos of your craft from your phone.
              </li>
              <li>
                <Check size={15} /> <strong>Vision AI Drafting:</strong>{" "}
                Automated material detection, category classification, and
                descriptions.
              </li>
              <li>
                <Check size={15} /> <strong>You Keep Control:</strong> You
                confirm the exact USD selling price and live stock quantity.
              </li>
              <li>
                <Check size={15} /> <strong>Direct Payments:</strong> PayPal
                captures route directly to your business account.
              </li>
            </ul>
            <Link to="/dashboard" className="card-action-link">
              Open Seller Studio <ArrowRight size={15} />
            </Link>
          </div>

          {/* Card 2: AI Agents */}
          <div className="ecosystem-card highlight">
            <div className="eco-badge agent">
              <Bot size={18} /> For AI Shopping Agents
            </div>
            <h3>Native Model Context Protocol</h3>
            <p>
              AI assistants need structured, deterministic endpoints, not
              brittle web scrapers that break on layout changes.
            </p>
            <ul className="eco-list">
              <li>
                <Check size={15} /> <strong>Streamable HTTP Protocol:</strong>{" "}
                Open JSON-RPC 2.0 endpoint at <code>/mcp</code>.
              </li>
              <li>
                <Check size={15} /> <strong>Deterministic Tool Suite:</strong>{" "}
                <code>search_products</code>, <code>get_quote</code>,{" "}
                <code>create_checkout</code>.
              </li>
              <li>
                <Check size={15} /> <strong>Stock Concurrency Locks:</strong>{" "}
                PostgreSQL <code>FOR UPDATE</code> row-locking prevents phantom
                overselling.
              </li>
              <li>
                <Check size={15} /> <strong>Schema.org JSON-LD:</strong> Full
                product semantic metadata on every storefront.
              </li>
            </ul>
            <Link to="/playground" className="card-action-link">
              Test Agent Playground <ArrowRight size={15} />
            </Link>
          </div>

          {/* Card 3: Buyers & Safety */}
          <div className="ecosystem-card">
            <div className="eco-badge buyer">
              <ShieldCheck size={18} /> For Shoppers & Safety
            </div>
            <h3>Zero Autonomous Wallet Drain</h3>
            <p>
              Autonomous shopping shouldn't mean unvetted credit card charges.
              We strictly enforce human-in-the-loop authorization.
            </p>
            <ul className="eco-list">
              <li>
                <Check size={15} /> <strong>Human-in-the-Loop:</strong> Every
                purchase requires explicit buyer sign-off on PayPal.
              </li>
              <li>
                <Check size={15} /> <strong>Integer Minor Units:</strong> All
                arithmetic calculated in cents ($42.00 = 4200), zero float
                errors.
              </li>
              <li>
                <Check size={15} /> <strong>Live Shipping Verification:</strong>{" "}
                Server-verified shipping rates to US and UK destinations.
              </li>
              <li>
                <Check size={15} /> <strong>Durable Tracking:</strong>{" "}
                Single-parcel carrier tracking tied to your PayPal capture.
              </li>
            </ul>
            <Link to="/s/meera-jaipur" className="card-action-link">
              Explore Live Storefront <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </section>

      {/* How It Works: 4 Steps */}
      <section className="page steps">
        <div className="section-header">
          <span className="eyebrow">HOW A TRANSACTION HAPPENS</span>
          <h2>The journey of an agentic purchase.</h2>
          <p className="section-sub">
            From the moment an artisan takes a photograph to final delivery
            tracking, every step is coordinated with strict verification.
          </p>
        </div>
        <div className="steps-grid four-col">
          <article>
            <div className="step-top">
              <span>01</span>
              <Camera size={20} />
            </div>
            <h3>1. Snap & Draft</h3>
            <p>
              Artisan uploads photos via WhatsApp or Web. Multimodal vision
              models analyze craft materials, textures, and dimensions to
              suggest a detailed draft.
            </p>
          </article>
          <article>
            <div className="step-top">
              <span>02</span>
              <CheckCircle size={20} />
            </div>
            <h3>2. Seller Confirms</h3>
            <p>
              AI never sets prices autonomously. The seller sets their USD
              selling price and available units, confirming human publication.
            </p>
          </article>
          <article>
            <div className="step-top">
              <span>03</span>
              <Cpu size={20} />
            </div>
            <h3>3. Agent Discovers</h3>
            <p>
              When a buyer prompts an AI shopping agent, the agent searches live
              catalogs over MCP, verifies real stock, and requests a binding
              quote.
            </p>
          </article>
          <article>
            <div className="step-top">
              <span>04</span>
              <ShieldCheck size={20} />
            </div>
            <h3>4. PayPal Authorization</h3>
            <p>
              The buyer reviews the exact quote and authorizes payment directly
              on PayPal. The seller receives an instant dispatch alert with
              buyer shipping details.
            </p>
          </article>
        </div>
      </section>

      {/* Live Storefronts Showcase */}
      <section className="page storefronts-section">
        <div className="section-header">
          <span className="eyebrow">EXPLORE ACTIVE SEEDED STORES</span>
          <h2>Real catalogs, live on localhost.</h2>
          <p className="section-sub">
            Experience how distinct independent studios are presented to both
            human shoppers and autonomous agent crawlers.
          </p>
        </div>
        <div className="stores-showcase-grid">
          {/* Store 1: Suriya Craft Studio */}
          <div className="store-card-featured">
            <div className="store-card-header">
              <div>
                <span className="store-location-badge">
                  SOUTH INDIA · TEXTILES & BRASS
                </span>
                <h3>Suriya Craft Studio</h3>
                <p className="store-desc">
                  Handcrafted silk table runners, terracotta filter coffee cups,
                  and hammered brass oil lamps.
                </p>
              </div>
              <span className="pill green">5 Live Products</span>
            </div>
            <div className="store-preview-items">
              <div className="mini-item">
                <span className="item-name">Kanchipuram Silk Table Runner</span>
                <span className="item-price">$42.00 USD</span>
              </div>
              <div className="mini-item">
                <span className="item-name">
                  Terracotta Filter Coffee Cup Set
                </span>
                <span className="item-price">$24.00 USD</span>
              </div>
              <div className="mini-item">
                <span className="item-name">Thanjavur Hammered Brass Lamp</span>
                <span className="item-price">$36.00 USD</span>
              </div>
            </div>
            <div className="store-card-footer">
              <Link to="/s/suriya-craft-studio" className="button small">
                Visit Suriya Craft Studio <ArrowRight size={14} />
              </Link>
            </div>
          </div>

          {/* Store 2: Meera's Jaipur Studio */}
          <div className="store-card-featured">
            <div className="store-card-header">
              <div>
                <span className="store-location-badge">
                  RAJASTHAN · TRADITIONAL TEXTILES
                </span>
                <h3>Meera's Jaipur Studio</h3>
                <p className="store-desc">
                  Artisan catalog featuring indigo block print scarves,
                  terracotta pendants, and botanical prints.
                </p>
              </div>
              <span className="pill green">6 Live Products</span>
            </div>
            <div className="store-preview-items">
              <div className="mini-item">
                <span className="item-name">Indigo block print scarf</span>
                <span className="item-price">$45.00 USD</span>
              </div>
              <div className="mini-item">
                <span className="item-name">Terracotta pendant</span>
                <span className="item-price">$24.00 USD</span>
              </div>
              <div className="mini-item">
                <span className="item-name">Botanical art print</span>
                <span className="item-price">$18.00 USD</span>
              </div>
            </div>
            <div className="store-card-footer">
              <Link to="/s/meera-jaipur" className="button small">
                Visit Meera's Jaipur Studio <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Technical Architecture Section */}
      <section className="page tech-section">
        <div className="section-header">
          <span className="eyebrow">ENGINEERED FOR SAFETY & SCALE</span>
          <h2>The technical foundations under the hood.</h2>
          <p className="section-sub">
            Built from scratch to resolve the fundamental trust and concurrency
            challenges of agentic e-commerce.
          </p>
        </div>
        <div className="tech-grid">
          <div className="tech-card">
            <div className="tech-icon">
              <Cpu size={22} />
            </div>
            <h4>Model Context Protocol (MCP)</h4>
            <p>
              Standardized JSON-RPC 2.0 Streamable HTTP transport exposing
              discovery and transactional tools. Compatible with Claude, Gemini,
              and custom agents.
            </p>
          </div>
          <div className="tech-card">
            <div className="tech-icon">
              <Lock size={22} />
            </div>
            <h4>Deterministic Minor Units</h4>
            <p>
              Money is stored and computed strictly as integer minor units
              ($18.00 = 1800 cents), preventing IEEE-754 floating-point
              truncation bugs during settlement.
            </p>
          </div>
          <div className="tech-card">
            <div className="tech-icon">
              <Layers3 size={22} />
            </div>
            <h4>Postgres Concurrency Locking</h4>
            <p>
              Atomic <code>SELECT FOR UPDATE</code> row locks guarantee
              inventory reservations during concurrent agent quote confirmation,
              preventing double-selling.
            </p>
          </div>
          <div className="tech-card">
            <div className="tech-icon">
              <Globe2 size={22} />
            </div>
            <h4>Multi-Language AI Translation</h4>
            <p>
              Storefronts automatically translate product titles and
              descriptions into 6 languages (Spanish, French, German, Hindi,
              Japanese) on demand.
            </p>
          </div>
        </div>
      </section>

      {/* Interactive FAQ Accordion */}
      <section className="page faq-section">
        <div className="section-header">
          <span className="eyebrow">COMMON QUESTIONS</span>
          <h2>Everything you need to know about AgentShelf.</h2>
          <p className="section-sub">
            Understanding the transition from traditional e-commerce to
            agent-native commerce.
          </p>
        </div>
        <div className="faq-list">
          {[
            {
              q: "What makes AgentShelf different from Shopify, Etsy, or Amazon?",
              a: "Traditional platforms rely on human search, advertising auctions, and manual SEO. AgentShelf is agent-native: your catalog is formatted for Model Context Protocol (MCP) so autonomous AI agents can search, verify stock, and quote items directly without web scraping. For sellers, onboarding requires zero technical skill—you can create listings simply by sending product photos via WhatsApp.",
            },
            {
              q: "Can an AI shopping agent spend money without my permission?",
              a: "Never. AgentShelf is built around a non-negotiable human-in-the-loop security architecture. While agents can search products and request quotes over MCP, the final checkout link directs the human buyer to PayPal Orders v2 for explicit biometric or password authorization. Agents have zero access to your payment credentials or autonomous wallet balances.",
            },
            {
              q: "How does the Model Context Protocol (MCP) work here?",
              a: "AgentShelf implements an official Streamable HTTP MCP server at '/mcp' (discoverable at '/.well-known/mcp.json'). It exposes 4 deterministic tools: search_products, get_quote, create_checkout, and get_order_status. Any MCP-compatible assistant (Claude, Gemini, OpenAI, or custom AI clients) can connect, discover products, and interact in real time.",
            },
            {
              q: "How do sellers receive their money?",
              a: "When a customer completes payment through PayPal, funds are captured directly to the seller's verified PayPal business account. AgentShelf does not hold or pool merchant funds, ensuring bank-grade settlement speed and complete regulatory compliance.",
            },
            {
              q: "How are currency conversions and international shipping handled?",
              a: "All monetary values are calculated deterministically as integer minor units in USD ($10.00 = 1000 cents), eliminating floating-point rounding errors. Integrated shipping tables automatically quote flat-rate international deliveries (currently US and UK destinations). Storefronts also support real-time multi-language AI translation into 6 languages.",
            },
          ].map((item, idx) => {
            const isOpen = openFaq === idx;
            return (
              <div key={idx} className={`faq-item ${isOpen ? "open" : ""}`}>
                <button
                  type="button"
                  className="faq-question"
                  onClick={() => toggleFaq(idx)}
                  aria-expanded={isOpen}
                >
                  <span className="faq-q-text">{item.q}</span>
                  <ChevronDown
                    size={18}
                    className={`faq-icon ${isOpen ? "rotated" : ""}`}
                  />
                </button>
                {isOpen && (
                  <div className="faq-answer">
                    <p>{item.a}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Dual-Track Conversion Call-To-Action */}
      <section className="page cta-banner-section">
        <div className="cta-banner-grid">
          <div className="cta-box seller-side">
            <span className="eyebrow">FOR ARTISANS & MAKERS</span>
            <h3>Ready to put your craft on the global shelf?</h3>
            <p>
              Join independent sellers reaching a new wave of AI-driven
              international buyers. Free to get started from your phone.
            </p>
            <Link to="/dashboard" className="button">
              Create Your Store <ArrowRight size={16} />
            </Link>
          </div>
          <div className="cta-box agent-side">
            <span className="eyebrow">FOR SHOPPERS & DEVELOPERS</span>
            <h3>Want to experience AI shopping in action?</h3>
            <p>
              Chat with the AI shopping assistant, discover curated products,
              and test real MCP tool activity live.
            </p>
            <Link to="/playground" className="button secondary">
              Open Buyer Playground <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
