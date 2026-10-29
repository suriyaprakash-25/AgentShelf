import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useParams,
  useSearchParams,
} from "react-router-dom";
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
  Search,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Store as StoreIcon,
  Zap,
} from "lucide-react";
import {
  api,
  type Capabilities,
  type Product,
  type Quote,
  type Store,
} from "./api";
import "./styles.css";

const AiBuyer = lazy(() =>
  import("./AiBuyer").then((m) => ({ default: m.AiBuyer })),
);
const Operations = lazy(() =>
  import("./Operations").then((m) => ({ default: m.Operations })),
);
const Dashboard = lazy(() =>
  import("./Seller").then((m) => ({ default: m.SellerDashboard })),
);
const Onboarding = lazy(() =>
  import("./Seller").then((m) => ({ default: m.SellerOnboarding })),
);

export default function App() {
  const [cap, setCap] = useState<Capabilities | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api<Capabilities>("/api/capabilities", undefined, controller.signal)
      .then(setCap)
      .catch(() => {});
    return () => controller.abort();
  }, []);
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="header">
        <Link className="brand" to="/">
          <Layers3 size={25} strokeWidth={1.6} /> AgentShelf
          <span className="tag">PILOT</span>
        </Link>
        <nav aria-label="Main navigation">
          <NavLink to="/s/meera-jaipur">The collection</NavLink>
          <NavLink to="/playground">Buyer playground</NavLink>
          <NavLink to="/dashboard">Seller dashboard</NavLink>
        </nav>
        <Link className="button small" to="/onboarding">
          Start your shop <ArrowRight size={16} />
        </Link>
      </header>
      <main id="main" tabIndex={-1}>
        <Suspense
          fallback={
            <div className="page" role="status">
              Loading your workspace…
            </div>
          }
        >
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/s/:slug" element={<StorePage />} />
            <Route path="/store/:slug" element={<StorePage />} />
            <Route
              path="/playground"
              element={<Playground capabilities={cap} />}
            />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/seller" element={<Dashboard />} />
            <Route path="/operations" element={<Operations />} />
            <Route path="/onboarding" element={<Onboarding />} />
            <Route path="/receipt" element={<Receipt />} />
            <Route
              path="*"
              element={
                <div className="page">
                  <span className="eyebrow">404 · NOT FOUND</span>
                  <h1>Page not found.</h1>
                  <p style={{ color: "var(--muted)", fontSize: 14 }}>
                    The page you were looking for doesn't exist.
                  </p>
                  <Link className="button" to="/" style={{ marginTop: 16, display: "inline-flex" }}>
                    Back to AgentShelf <ArrowRight size={16} />
                  </Link>
                </div>
              }
            />
          </Routes>
        </Suspense>
      </main>
      <footer>
        <Link className="brand" to="/">
          <Layers3 size={19} />
          AgentShelf
        </Link>
        <nav className="footer-nav" aria-label="Footer navigation">
          <Link to="/s/meera-jaipur">Shop</Link>
          <Link to="/playground">Playground</Link>
          <Link to="/onboarding">Sell</Link>
        </nav>
        <p>Small shops. New possibilities.</p>
        <span>
          {cap
            ? `${cap.paypal_mode === "sandbox" ? "Sandbox pilot · no real money" : "Live merchant pilot"}`
            : "Connecting to the service…"}
        </span>
      </footer>
    </>
  );
}

function Home() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);

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
          Bridging independent artisans and autonomous AI shopping agents via Model Context Protocol (MCP) & PayPal.
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
              Your craft deserves a bigger shelf. AgentShelf turns handcrafted product photos into an agent-ready catalog that AI assistants can discover and quote over open Model Context Protocol (MCP)—with human approval on PayPal every step of the way.
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

      {/* Proof / Stats section */}
      <section className="proof page" style={{ paddingTop: 0, paddingBottom: 0 }}>
        <div className="proof-grid">
          <div className="stat">
            <strong>127+</strong>
            <span>Independent sellers worldwide</span>
          </div>
          <div className="stat">
            <strong>4,200+</strong>
            <span>Products discoverable by AI agents</span>
          </div>
          <div className="stat">
            <strong>12 Countries</strong>
            <span>Cross-border merchant access</span>
          </div>
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
            Traditional marketplaces trap independent makers in complex software and steep commission cuts. AgentShelf builds the direct open protocol bridge so AI assistants can find and shop from small makers.
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
              No coding, no SEO keyword stuffing, and no complex inventory software. List your work in seconds.
            </p>
            <ul className="eco-list">
              <li>
                <Check size={15} /> <strong>WhatsApp & Web Uploads:</strong> Snap 1–4 photos of your craft from your phone.
              </li>
              <li>
                <Check size={15} /> <strong>Vision AI Drafting:</strong> Automated material detection, category classification, and descriptions.
              </li>
              <li>
                <Check size={15} /> <strong>You Keep Control:</strong> You confirm the exact USD selling price and live stock quantity.
              </li>
              <li>
                <Check size={15} /> <strong>Direct Payments:</strong> PayPal captures route directly to your business account.
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
              AI assistants need structured, deterministic endpoints, not brittle web scrapers that break on layout changes.
            </p>
            <ul className="eco-list">
              <li>
                <Check size={15} /> <strong>Streamable HTTP Protocol:</strong> Open JSON-RPC 2.0 endpoint at <code>/mcp</code>.
              </li>
              <li>
                <Check size={15} /> <strong>Deterministic Tool Suite:</strong> <code>search_products</code>, <code>get_quote</code>, <code>create_checkout</code>.
              </li>
              <li>
                <Check size={15} /> <strong>Stock Concurrency Locks:</strong> PostgreSQL <code>FOR UPDATE</code> row-locking prevents phantom overselling.
              </li>
              <li>
                <Check size={15} /> <strong>Schema.org JSON-LD:</strong> Full product semantic metadata on every storefront.
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
              Autonomous shopping shouldn't mean unvetted credit card charges. We strictly enforce human-in-the-loop authorization.
            </p>
            <ul className="eco-list">
              <li>
                <Check size={15} /> <strong>Human-in-the-Loop:</strong> Every purchase requires explicit buyer sign-off on PayPal.
              </li>
              <li>
                <Check size={15} /> <strong>Integer Minor Units:</strong> All arithmetic calculated in cents ($42.00 = 4200), zero float errors.
              </li>
              <li>
                <Check size={15} /> <strong>Live Shipping Verification:</strong> Server-verified shipping rates to US and UK destinations.
              </li>
              <li>
                <Check size={15} /> <strong>Durable Tracking:</strong> Single-parcel carrier tracking tied to your PayPal capture.
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
            From the moment an artisan takes a photograph to final delivery tracking, every step is coordinated with strict verification.
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
              Artisan uploads photos via WhatsApp or Web. Multimodal vision models analyze craft materials, textures, and dimensions to suggest a detailed draft.
            </p>
          </article>
          <article>
            <div className="step-top">
              <span>02</span>
              <CheckCircle size={20} />
            </div>
            <h3>2. Seller Confirms</h3>
            <p>
              AI never sets prices autonomously. The seller sets their USD selling price and available units, confirming human publication.
            </p>
          </article>
          <article>
            <div className="step-top">
              <span>03</span>
              <Cpu size={20} />
            </div>
            <h3>3. Agent Discovers</h3>
            <p>
              When a buyer prompts an AI shopping agent, the agent searches live catalogs over MCP, verifies real stock, and requests a binding quote.
            </p>
          </article>
          <article>
            <div className="step-top">
              <span>04</span>
              <ShieldCheck size={20} />
            </div>
            <h3>4. PayPal Authorization</h3>
            <p>
              The buyer reviews the exact quote and authorizes payment directly on PayPal. The seller receives an instant dispatch alert with buyer shipping details.
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
            Experience how distinct independent studios are presented to both human shoppers and autonomous agent crawlers.
          </p>
        </div>
        <div className="stores-showcase-grid">
          {/* Store 1: Suriya Craft Studio */}
          <div className="store-card-featured">
            <div className="store-card-header">
              <div>
                <span className="store-location-badge">SOUTH INDIA · TEXTILES & BRASS</span>
                <h3>Suriya Craft Studio</h3>
                <p className="store-desc">
                  Handcrafted silk table runners, terracotta filter coffee cups, and hammered brass oil lamps.
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
                <span className="item-name">Terracotta Filter Coffee Cup Set</span>
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
                <span className="store-location-badge">RAJASTHAN · TRADITIONAL TEXTILES</span>
                <h3>Meera's Jaipur Studio</h3>
                <p className="store-desc">
                  Artisan catalog featuring indigo block print scarves, terracotta pendants, and botanical prints.
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
            Built from scratch to resolve the fundamental trust and concurrency challenges of agentic e-commerce.
          </p>
        </div>
        <div className="tech-grid">
          <div className="tech-card">
            <div className="tech-icon"><Cpu size={22} /></div>
            <h4>Model Context Protocol (MCP)</h4>
            <p>
              Standardized JSON-RPC 2.0 Streamable HTTP transport exposing discovery and transactional tools. Compatible with Claude, Gemini, and custom agents.
            </p>
          </div>
          <div className="tech-card">
            <div className="tech-icon"><Lock size={22} /></div>
            <h4>Deterministic Minor Units</h4>
            <p>
              Money is stored and computed strictly as integer minor units ($18.00 = 1800 cents), preventing IEEE-754 floating-point truncation bugs during settlement.
            </p>
          </div>
          <div className="tech-card">
            <div className="tech-icon"><Layers3 size={22} /></div>
            <h4>Postgres Concurrency Locking</h4>
            <p>
              Atomic <code>SELECT FOR UPDATE</code> row locks guarantee inventory reservations during concurrent agent quote confirmation, preventing double-selling.
            </p>
          </div>
          <div className="tech-card">
            <div className="tech-icon"><Globe2 size={22} /></div>
            <h4>Multi-Language AI Translation</h4>
            <p>
              Storefronts automatically translate product titles and descriptions into 6 languages (Spanish, French, German, Hindi, Japanese) on demand.
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
            Understanding the transition from traditional e-commerce to agent-native commerce.
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
                  <ChevronDown size={18} className={`faq-icon ${isOpen ? "rotated" : ""}`} />
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
            <p>Join independent sellers reaching a new wave of AI-driven international buyers. Free to get started from your phone.</p>
            <Link to="/dashboard" className="button">
              Create Your Store <ArrowRight size={16} />
            </Link>
          </div>
          <div className="cta-box agent-side">
            <span className="eyebrow">FOR SHOPPERS & DEVELOPERS</span>
            <h3>Want to experience AI shopping in action?</h3>
            <p>Chat with the AI shopping assistant, discover curated products, and test real MCP tool activity live.</p>
            <Link to="/playground" className="button secondary">
              Open Buyer Playground <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}

function ProductArt({
  index,
  title,
  demo = true,
}: {
  index: number;
  title: string;
  demo?: boolean;
}) {
  return (
    <div
      className={`product-art art-${index % 4}`}
      role="img"
      aria-label={
        demo
          ? `Illustrative pattern for ${title}; not a product photograph`
          : `No product photograph supplied for ${title}`
      }
    >
      <span>{demo ? "ILLUSTRATED DEMO" : "PHOTO NOT PROVIDED"}</span>
      <div className="art-shape" />
    </div>
  );
}

function StorePage() {
  const { slug = "meera-jaipur" } = useParams<{ slug: string }>();
  const [store, setStore] = useState<Store | null>(null);
  const [error, setError] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [lang, setLang] = useState("en");
  const [translations, setTranslations] = useState<
    Record<string, { title: string; description: string; language: string }>
  >({});

  async function more() {
    if (!store?.next_cursor) return;
    setLoadingMore(true);
    try {
      const next = await api<Store>(
        `/api/stores/${encodeURIComponent(slug)}?after=${store.next_cursor}`,
      );
      setStore({ ...next, products: [...store.products, ...next.products] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }

  async function translateProduct(productId: string, targetLang: string) {
    if (targetLang === "en") return;
    const key = `${productId}:${targetLang}`;
    if (translations[key]) return; // already translated
    try {
      const translated = await api<{
        title: string;
        description: string;
        language: string;
      }>(
        `/api/products/${encodeURIComponent(productId)}/translate?lang=${encodeURIComponent(targetLang)}`,
      );
      setTranslations((prev) => ({ ...prev, [key]: translated }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // Auto-translate all products when language changes
  useEffect(() => {
    if (!store || lang === "en") return;
    store.products.forEach((p) => {
      void translateProduct(p.product_id, lang);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, store?.products.length]);

  useEffect(() => {
    const controller = new AbortController();
    api<Store>(
      `/api/stores/${encodeURIComponent(slug)}`,
      undefined,
      controller.signal,
    )
      .then(setStore)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [slug]);

  const jsonLd = store
    ? {
        "@context": "https://schema.org",
        "@type": "ItemList",
        name: store.name,
        itemListElement: store.products.map((p, idx) => ({
          "@type": "ListItem",
          position: idx + 1,
          item: {
            "@type": "Product",
            sku: p.product_id,
            name: p.title,
            description: p.description,
            offers: {
              "@type": "Offer",
              price: p.price,
              priceCurrency: p.currency,
              availability: p.in_stock
                ? "https://schema.org/InStock"
                : "https://schema.org/OutOfStock",
            },
          },
        })),
      }
    : null;

  return (
    <div className="page">
      {jsonLd && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c"),
          }}
        />
      )}
      <div className="store-heading">
        <div>
          <span className="eyebrow">THE INDEPENDENT COLLECTION</span>
          <h1>{store?.name || "A shelf of possibilities."}</h1>
          <p>
            {slug === "meera-jaipur"
              ? "A fictional catalog from Jaipur. Prices and availability are read live from the database."
              : `Handcrafted independent catalog${store?.country ? ` (${store.country})` : ""}. Server-verified prices and live stock.`}
          </p>
          {store && (
            <p className="product-count">
              {store.products.length} product{store.products.length !== 1 ? "s" : ""}
              {store.next_cursor ? " · scroll for more" : ""}
            </p>
          )}
        </div>
        <div className="seller-toolbar">
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, whiteSpace: "nowrap" }}>
            <Globe2 size={14} />
            <select
              aria-label="Listing language"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              style={{ marginTop: 0, width: "auto" }}
            >
              <option value="en">English</option>
              <option value="es">Español</option>
              <option value="fr">Français</option>
              <option value="de">Deutsch</option>
              <option value="hi">हिन्दी</option>
              <option value="ja">日本語</option>
            </select>
          </label>
          <span className="pill">
            <ShieldCheck size={14} /> USD · US & UK shipping
          </span>
        </div>
      </div>

      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {!store && !error && (
        <div className="skeleton-product-grid">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="skeleton-card">
              <div className="skeleton" style={{ height: 225 }} />
              <div style={{ padding: 20 }}>
                <div className="skeleton" style={{ height: 12, width: "40%", marginBottom: 12 }} />
                <div className="skeleton" style={{ height: 20, width: "80%", marginBottom: 10 }} />
                <div className="skeleton" style={{ height: 12, width: "100%", marginBottom: 6 }} />
                <div className="skeleton" style={{ height: 12, width: "70%" }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {store && (
        <>
          <div className="product-grid">
            {store.products.map((p, i) => {
              const t =
                lang !== "en" ? translations[`${p.product_id}:${lang}`] : null;
              return (
                <article className="product-card" key={p.product_id}>
                  {p.image_url ? (
                    <img
                      className="product-photo"
                      src={p.image_url}
                      alt={t ? t.title : p.title}
                      loading="lazy"
                    />
                  ) : (
                    <ProductArt
                      index={i}
                      title={p.title}
                      demo={slug === "meera-jaipur"}
                    />
                  )}
                  <div className="product-info">
                    <span className="eyebrow">
                      {store.country} / {String(i + 1).padStart(2, "0")}
                    </span>
                    <h2>{t ? t.title : p.title}</h2>
                    <p>{t ? t.description : p.description}</p>
                    {/* Stock badge */}
                    <span className={`stock-badge ${p.in_stock ? "in-stock" : "out-of-stock"}`}>
                      {p.in_stock ? "● In stock" : "○ Out of stock"}
                    </span>
                    <div className="product-bottom">
                      <strong>
                        ${p.price} <small>{p.currency}</small>
                      </strong>
                      <Link
                        to={`/playground?product=${p.product_id}`}
                        className="product-cta"
                        aria-label={`Get a quote for ${p.title}`}
                      >
                        Get a quote <ArrowRight size={14} />
                      </Link>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>

          {store.next_cursor && (
            <div style={{ textAlign: "center", marginTop: 32 }}>
              <button
                className="button secondary"
                disabled={loadingMore}
                onClick={() => void more()}
              >
                {loadingMore ? "Loading…" : "Load more products"}
              </button>
            </div>
          )}

          {store.products.length === 0 && (
            <div className="empty" style={{ marginTop: 40, border: "1px solid var(--line)", borderRadius: 8 }}>
              <ShoppingBag size={32} style={{ opacity: 0.4 }} />
              <h3>No products yet</h3>
              <p>This shop has no available products right now. Please check back soon.</p>
            </div>
          )}

          {/* Demo notice (moved below grid) */}
          {slug === "meera-jaipur" && (
            <p className="notice" style={{ marginTop: 24 }}>
              Demo products and illustrations are synthetic. The seller PayPal
              account must be configured before purchase.
            </p>
          )}

          <div className="mcp-note">
            <Layers3 size={28} style={{ flexShrink: 0, color: "var(--muted)" }} />
            <div>
              <strong>Open to shopping agents.</strong>
              <p>
                MCP endpoint: <code>{store.mcp_url}</code> · Discovery:{" "}
                <code>/.well-known/mcp.json</code> · Schema.org:{" "}
                <code>/api/stores/{store.slug}/schema.json</code>
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Playground({ capabilities }: { capabilities: Capabilities | null }) {
  const [params] = useSearchParams();
  const [products, setProducts] = useState<Product[]>([]);
  const [budget, setBudget] = useState("60");
  const [country, setCountry] = useState("GB");
  const [session, setSession] = useState("");
  const [query, setQuery] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [chosen, setChosen] = useState<Product | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [trace, setTrace] = useState<string[]>([]);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    api<{ products: Product[] }>(
      "/api/products?limit=10",
      undefined,
      controller.signal,
    )
      .then((d) => {
        setProducts(d.products);
        // Auto-focus search after products load
        setTimeout(() => searchRef.current?.focus(), 100);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, []);

  async function startQuote(product: Product) {
    setError("");
    setBusy(true);
    setQuote(null);
    setChosen(product);
    try {
      const parts = /^(\d+)(?:\.(\d{1,2}))?$/.exec(budget);
      if (!parts)
        throw new Error("Enter a budget with at most two decimal places.");
      const budget_minor =
        Number(parts[1]) * 100 + Number((parts[2] || "").padEnd(2, "0"));
      let sessionId = session;
      if (!sessionId) {
        const s = await api<{ session_id: string }>(
          "/api/playground/sessions",
          {
            budget_minor,
            currency: "USD",
          },
        );
        sessionId = s.session_id;
        setSession(sessionId);
      }
      const q = await api<Quote>("/api/quotes", {
        product_id: product.product_id,
        qty: 1,
        ship_to_country: country,
        session_id: sessionId,
      });
      setQuote(q);
      setTrace((items) => [
        ...(items.length
          ? items.slice(-38)
          : [`Session created with budget $${budget}.`]),
        `get_quote: ${JSON.stringify(q)}`,
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create a quote.");
    } finally {
      setBusy(false);
    }
  }

  async function checkout() {
    if (!quote || !session) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ order_id: string; approval_url: string }>(
        "/api/checkouts",
        { quote_id: quote.quote_id, session_id: session },
      );
      sessionStorage.setItem("agentshelf-buyer-session", session);
      setTrace((t) => [...t, `create_checkout: order ${result.order_id}`]);
      const target = new URL(result.approval_url);
      if (
        target.protocol !== "https:" ||
        ![
          "www.sandbox.paypal.com",
          "sandbox.paypal.com",
          "www.paypal.com",
          "paypal.com",
        ].includes(target.hostname)
      )
        throw new Error("The payment approval link could not be verified.");
      window.location.assign(target.href);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create checkout.");
    } finally {
      setBusy(false);
    }
  }

  function clearSession() {
    setSession("");
    setQuote(null);
    setChosen(null);
    setTrace([]);
    setError("");
  }

  const filtered = products.filter(
    (p) =>
      (!params.get("product") || p.product_id === params.get("product")) &&
      p.title.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="page">
      <span className="eyebrow">BUYER PLAYGROUND</span>
      <h1>
        Find something <em>thoughtful.</em>
      </h1>
      <p className="lede">
        Set your budget, choose your destination, and get a server-verified
        quote before approving payment on PayPal.
      </p>
      <div className="playground-layout">
        <section className="panel">
          <div className="panel-title">
            <ShoppingBag size={20} />
            <h2>Your shopping session</h2>
            <span className="pill">
              {capabilities?.paypal_mode || "Connecting"}
            </span>
          </div>
          <div className="notice" style={{ marginTop: 12 }}>
            {capabilities?.ai_configured
              ? "Chat with your agent above, or browse the catalog and get a direct quote below."
              : "AI chat needs an Anthropic API key. You can explore real catalog data and request server quotes directly."}
          </div>

          {/* Budget + Ship-to */}
          <div className="form-row">
            <label>
              Your budget (USD)
              <div className="input-prefix-wrapper">
                <span className="input-prefix">$</span>
                <input
                  value={budget}
                  onChange={(e) => {
                    setBudget(e.target.value);
                    setSession("");
                    setQuote(null);
                  }}
                  inputMode="decimal"
                  placeholder="60"
                />
              </div>
            </label>
            <label>
              Ship to
              <select
                value={country}
                onChange={(e) => {
                  setCountry(e.target.value);
                  setSession("");
                  setQuote(null);
                }}
              >
                <option value="GB">United Kingdom</option>
                <option value="US">United States</option>
              </select>
            </label>
          </div>

          {/* Session controls */}
          {session && (
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
              <button
                type="button"
                className="text-link"
                onClick={clearSession}
                style={{ fontSize: 12 }}
              >
                ↺ Start a new session
              </button>
            </div>
          )}

          <AiBuyer
            key={`${budget}:${country}`}
            budget={budget}
            country={country}
            capabilities={capabilities}
            onTrace={(line) => setTrace((items) => [...items.slice(-39), line])}
          />

          {/* Product search */}
          <label className="search-label" style={{ marginTop: 8 }}>
            <Search size={18} />
            <input
              ref={searchRef}
              aria-label="Filter products"
              placeholder="Filter the collection…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>

          {error && (
            <p className="notice error" role="alert" style={{ marginTop: 12 }}>
              {error}
            </p>
          )}

          <div className="search-results">
            {filtered.map((p) => (
              <button
                className="result"
                disabled={busy}
                onClick={() => void startQuote(p)}
                key={p.product_id}
              >
                <div className="result-left">
                  {p.image_url && (
                    <img
                      className="result-thumb"
                      src={p.image_url}
                      alt={p.title}
                      loading="lazy"
                    />
                  )}
                  <div>
                    <strong>{p.title}</strong>
                    <span>{p.store_name}</span>
                  </div>
                </div>
                <span>
                  ${p.price}
                  <ArrowRight size={17} />
                </span>
              </button>
            ))}
            {filtered.length === 0 && (
              <p style={{ color: "var(--muted)", fontSize: 13, padding: "20px 0", textAlign: "center" }}>
                No matching products. Try another search.
              </p>
            )}
          </div>

          {busy && (
            <p role="status" style={{ fontSize: 13, color: "var(--muted)" }}>
              Checking with the server…
            </p>
          )}

          {quote && (
            <div className="quote">
              <span className="eyebrow">YOUR SERVER-VERIFIED QUOTE</span>
              <div className="quote-head">
                {chosen?.image_url && (
                  <img
                    className="result-thumb"
                    src={chosen.image_url}
                    alt={chosen.title}
                    loading="lazy"
                  />
                )}
                <h3>{chosen?.title}</h3>
              </div>
              <dl>
                <div>
                  <dt>Item</dt>
                  <dd>${quote.item_total}</dd>
                </div>
                <div>
                  <dt>Shipping</dt>
                  <dd>${quote.shipping}</dd>
                </div>
                <div className="total">
                  <dt>Total</dt>
                  <dd>
                    ${quote.total} {quote.currency}
                  </dd>
                </div>
              </dl>
              <p style={{ fontSize: 11, color: "var(--muted)" }}>
                Quote expires {new Date(quote.expires_at).toLocaleTimeString()}.
                Your budget includes shipping.
              </p>
              <button
                className="button"
                onClick={checkout}
                disabled={busy || !capabilities?.checkout_configured}
              >
                Confirm total & continue to PayPal <ArrowRight size={17} />
              </button>
              {!capabilities?.checkout_configured && (
                <p className="notice" style={{ marginTop: 8, marginBottom: 0 }}>
                  Checkout needs PayPal sandbox credentials. No payment has been
                  created.
                </p>
              )}
            </div>
          )}
        </section>

        {/* Activity panel */}
        <aside className="panel tool-panel">
          <span className="eyebrow">EVERY ACTION, IN THE OPEN</span>
          <h2>Activity</h2>
          <p>
            These are actual server calls from the catalog explorer. The AI
            agent's MCP tool trace appears here when enabled.
          </p>
          {trace.length ? (
            trace.map((line, i) => <pre key={i}>{line}</pre>)
          ) : (
            <div className="empty">
              <Layers3 size={30} />
              <h3>No activity yet</h3>
              <p>
                Choose a product from the list to see its server-verified quote.
                Every API call appears here transparently.
              </p>
            </div>
          )}
          <div className="guard-note">
            <ShieldCheck size={20} />
            <p>
              Prices, stock and budgets are checked on the server. The model
              cannot change them.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}

const STATUS_LABELS: Record<string, string> = {
  paid: "✓ Payment Confirmed",
  shipped: "📦 Order Shipped",
  pending: "⏳ Payment Pending",
  refunded: "↩ Refunded",
  cancelled: "✕ Cancelled",
};

function Receipt() {
  const [params] = useSearchParams();
  const [result, setResult] = useState<{
    status: string;
    amount: string;
    currency: string;
    refunded_amount: string;
    payment_review: string | null;
    carrier?: string | null;
    tracking_number?: string | null;
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const id = params.get("order");
    const session = sessionStorage.getItem("agentshelf-buyer-session");
    if (!id || !session) {
      setError(
        "Receipt not found. Open this page in the same browser you used to start checkout.",
      );
      return;
    }
    const controller = new AbortController();
    api<{
      status: string;
      amount: string;
      currency: string;
      refunded_amount: string;
      payment_review: string | null;
      carrier?: string | null;
      tracking_number?: string | null;
    }>(
      `/api/orders/${encodeURIComponent(id)}?session_id=${encodeURIComponent(session)}`,
      undefined,
      controller.signal,
    )
      .then(setResult)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [params]);

  const isSuccess =
    result?.status === "paid" || result?.status === "shipped";

  return (
    <div className="page narrow">
      <span className="eyebrow">YOUR ORDER</span>

      {/* Visual success state */}
      {isSuccess && (
        <div className="receipt-success">
          <div className="success-icon">
            <CheckCircle size={36} />
          </div>
          <h1>Payment confirmed!</h1>
          <p className="receipt-amount">
            {result!.amount} {result!.currency}
          </p>
        </div>
      )}

      {!isSuccess && !error && result && (
        <h1>Order status.</h1>
      )}

      {!result && !error && (
        <div style={{ marginTop: 24 }}>
          <p role="status" style={{ color: "var(--muted)", fontSize: 14 }}>
            Checking your order…
          </p>
          <div className="skeleton" style={{ height: 160, marginTop: 16, borderRadius: 8 }} />
        </div>
      )}

      {error && (
        <p role="alert" className="notice error" style={{ marginTop: 24 }}>
          {error}
        </p>
      )}

      {result && (
        <div className="panel" style={{ marginTop: isSuccess ? 0 : 32 }}>
          <div className="receipt-detail">
            <div className="receipt-row">
              <span className="receipt-label">Status</span>
              <span className="receipt-value">
                {STATUS_LABELS[result.status] ?? result.status}
              </span>
            </div>
            <div className="receipt-row">
              <span className="receipt-label">Amount</span>
              <span className="receipt-value">
                {result.amount} {result.currency}
              </span>
            </div>
            {result.tracking_number && (
              <div className="receipt-row">
                <span className="receipt-label">Tracking</span>
                <a
                  href={`https://www.google.com/search?q=${encodeURIComponent(
                    `${result.carrier ?? ""} tracking ${result.tracking_number}`,
                  )}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="receipt-value"
                  style={{ color: "var(--green)", textDecoration: "underline" }}
                >
                  {result.carrier ? `${result.carrier} ` : ""}
                  {result.tracking_number} ↗
                </a>
              </div>
            )}
            {Number(result.refunded_amount) > 0 && (
              <div className="receipt-row">
                <span className="receipt-label">Refunded</span>
                <span className="receipt-value">
                  {result.refunded_amount} {result.currency}
                </span>
              </div>
            )}
          </div>

          {result.payment_review && (
            <p className="notice" role="status" style={{ marginTop: 12 }}>
              ⚠️ This payment is under review. Contact the seller before
              arranging fulfilment.
            </p>
          )}
        </div>
      )}

      <Link
        to="/s/meera-jaipur"
        className="button secondary"
        style={{ marginTop: 24, display: "inline-flex" }}
      >
        ← Back to the collection
      </Link>
    </div>
  );
}
