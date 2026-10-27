import { lazy, Suspense, useEffect, useState } from "react";
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
  Check,
  Globe2,
  Layers3,
  Search,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
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
                  <h1>Page not found</h1>
                  <Link to="/">Back to AgentShelf</Link>
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
  return (
    <>
      <section className="hero page">
        <div className="eyebrow">
          <span className="dot" /> A NEW WAY FOR SMALL SHOPS TO BE FOUND
        </div>
        <div className="hero-grid">
          <div>
            <h1>
              Made by you.
              <br />
              Found by <em>AI.</em>
            </h1>
            <p className="lede">
              Your craft deserves a bigger shelf. Turn product photos into a
              shop that AI shopping agents can discover—with you in control,
              every step of the way.
            </p>
            <div className="actions">
              <Link className="button" to="/s/meera-jaipur">
                Explore the demo collection <ArrowRight size={18} />
              </Link>
              <Link className="text-link" to="/playground">
                Try the buyer playground <ArrowRight size={16} />
              </Link>
            </div>
            <div className="trust">
              <ShieldCheck size={17} /> Human-approved PayPal checkout{" "}
              <span>·</span>
              <Globe2 size={17} /> Built for cross-border discovery
            </div>
          </div>
          <div
            className="hero-art"
            aria-label="Illustration of an artisan scarf and a product listing"
          >
            <div className="art-note">FROM A PHOTO TO A POSSIBILITY</div>
            <div className="fabric">
              <span className="fabric-label">
                JAIPUR STUDIO
                <br />
                01 / TEXTILES
              </span>
            </div>
            <div className="listing-card">
              <div className="card-icon">
                <Sparkles size={19} />
              </div>
              <span className="eyebrow">YOUR NEXT CHAPTER</span>
              <h3>An agent-ready shop.</h3>
              <p>Photos → your listing → your approval.</p>
              <div className="listing-bottom">
                <span>
                  <Check size={13} /> Your price. Your products.
                </span>
                <ArrowRight size={20} />
              </div>
            </div>
            <span className="art-caption">
              An illustrated preview. Explore the real seeded catalog below.
            </span>
          </div>
        </div>
      </section>
      <section className="strip">
        <span>SELLER FIRST.</span>
        <span>SERVER-VERIFIED PRICES.</span>
        <span>HUMAN APPROVAL.</span>
        <span>PAYPAL CHECKOUT.</span>
      </section>
      <section className="page steps">
        <div>
          <span className="eyebrow">A LITTLE LESS FRICTION</span>
          <h2>Your shop, on a new shelf.</h2>
        </div>
        <div className="steps-grid">
          {[
            {
              n: "01",
              title: "Show what you make",
              text: "Start with photos. AI drafts the details, and you confirm what goes live.",
              icon: <Sparkles />,
            },
            {
              n: "02",
              title: "Be discovered",
              text: "A public storefront and MCP tools give shopping agents a way to find your products.",
              icon: <Search />,
            },
            {
              n: "03",
              title: "Keep the final say",
              text: "The server checks price, stock and budget. The buyer approves payment on PayPal.",
              icon: <ShieldCheck />,
            },
          ].map((step) => (
            <article key={step.n}>
              <div className="step-top">
                <span>{step.n}</span>
                {step.icon}
              </div>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </article>
          ))}
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
    try {
      const translated = await api<{
        title: string;
        description: string;
        language: string;
      }>(
        `/api/products/${encodeURIComponent(productId)}/translate?lang=${encodeURIComponent(targetLang)}`,
      );
      setTranslations((prev) => ({
        ...prev,
        [`${productId}:${targetLang}`]: translated,
      }));
    } catch (e) {
      setError((e as Error).message);
    }
  }
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
              ? "Discover a fictional catalog from Jaipur. Prices and availability are read from the database."
              : `Handcrafted independent catalog${store?.country ? ` (${store.country})` : ""}. Server-verified prices and live stock availability.`}
          </p>
        </div>
        <div className="seller-toolbar">
          <label>
            Language{" "}
            <select
              aria-label="Listing language"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
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
            <Globe2 size={15} /> USD · shipping to US & UK
          </span>
        </div>
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {!store && !error && <p role="status">Loading the collection…</p>}
      {store && (
        <>
          {slug === "meera-jaipur" && (
            <p className="notice">
              Demo products and illustrations are synthetic. The seller PayPal
              account must be configured before purchase.
            </p>
          )}
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
                    {lang !== "en" && !t && (
                      <button
                        type="button"
                        className="text-link"
                        onClick={() =>
                          void translateProduct(p.product_id, lang)
                        }
                      >
                        Translate copy ({lang.toUpperCase()})
                      </button>
                    )}
                    <div className="product-bottom">
                      <strong>
                        ${p.price} <small>{p.currency}</small>
                      </strong>
                      <Link
                        to={`/playground?product=${p.product_id}`}
                        aria-label={`Get a quote for ${p.title}`}
                      >
                        <ArrowRight size={21} />
                      </Link>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
          {store.next_cursor && (
            <button
              className="button secondary"
              disabled={loadingMore}
              onClick={() => void more()}
            >
              {loadingMore ? "Loading…" : "More products"}
            </button>
          )}
          {store.products.length === 0 && (
            <p className="notice">
              This shop has no available products right now. Please check back.
            </p>
          )}
          <div className="mcp-note">
            <Layers3 />
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
  useEffect(() => {
    const controller = new AbortController();
    api<{ products: Product[] }>(
      "/api/products?limit=10",
      undefined,
      controller.signal,
    )
      .then((d) => setProducts(d.products))
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
        Explore the catalog, see the exact total, and approve your purchase on
        PayPal.
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
          <div className="notice">
            {capabilities?.ai_configured
              ? "Chat with your agent, or browse the catalog directly below."
              : "AI chat needs an Anthropic API key. You can explore real catalog data and request server quotes here."}
          </div>
          <div className="form-row">
            <label>
              Your budget (USD)
              <input
                value={budget}
                onChange={(e) => {
                  setBudget(e.target.value);
                  setSession("");
                  setQuote(null);
                }}
                inputMode="decimal"
              />
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
          <AiBuyer
            key={`${budget}:${country}`}
            budget={budget}
            country={country}
            capabilities={capabilities}
            onTrace={(line) => setTrace((items) => [...items.slice(-39), line])}
          />
          <label className="search-label">
            <Search size={18} />
            <input
              aria-label="Filter products"
              placeholder="Filter the collection…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          <div className="search-results">
            {filtered.map((p) => (
              <button
                className="result"
                disabled={busy}
                onClick={() => startQuote(p)}
                key={p.product_id}
              >
                <div>
                  <strong>{p.title}</strong>
                  <span>{p.store_name}</span>
                </div>
                <span>
                  ${p.price}
                  <ArrowRight size={17} />
                </span>
              </button>
            ))}
            {filtered.length === 0 && (
              <p>No matching products. Try another search.</p>
            )}
          </div>
          {busy && <p role="status">Checking with the server…</p>}
          {quote && (
            <div className="quote">
              <span className="eyebrow">YOUR SERVER-VERIFIED QUOTE</span>
              <h3>{chosen?.title}</h3>
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
              <p>
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
                <p className="notice">
                  Checkout needs PayPal sandbox credentials. No payment has been
                  created.
                </p>
              )}
            </div>
          )}
        </section>
        <aside className="panel tool-panel">
          <span className="eyebrow">EVERY ACTION, IN THE OPEN</span>
          <h2>Activity</h2>
          <p>
            These are actual server calls from the catalog explorer. The AI
            agent's MCP tool trace will appear here when enabled.
          </p>
          {trace.length ? (
            trace.map((line, i) => <pre key={i}>{line}</pre>)
          ) : (
            <div className="empty">
              <Layers3 size={30} />
              <p>Choose a product to see its server-verified quote.</p>
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
      setError("Open this receipt in the browser used to start checkout.");
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
  return (
    <div className="page narrow">
      <span className="eyebrow">YOUR ORDER</span>
      <h1>
        {result?.status === "paid" || result?.status === "shipped"
          ? "Payment confirmed."
          : "Order status."}
      </h1>
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {result ? (
        <div className="panel">
          <p>
            Status: <strong>{result.status}</strong>
          </p>
          <p>
            Amount: {result.amount} {result.currency}
          </p>
          {result.tracking_number && (
            <p>
              Tracking: {result.carrier ? `${result.carrier} ` : ""}
              {result.tracking_number}
            </p>
          )}
          {Number(result.refunded_amount) > 0 && (
            <p>
              Confirmed refunds: {result.refunded_amount} {result.currency}
            </p>
          )}
          {result.payment_review && (
            <p role="status">
              This payment needs review. Contact the seller before arranging
              fulfilment.
            </p>
          )}
        </div>
      ) : (
        !error && <p role="status">Checking your order…</p>
      )}
      <Link to="/s/meera-jaipur" className="text-link">
        Back to the collection
      </Link>
    </div>
  );
}
