import { lazy, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Layers3,
  Search,
  ShieldCheck,
  ShoppingBag,
} from "lucide-react";
import { api, type Capabilities, type Product, type Quote } from "../api";
import { resolveProductImage } from "../productImages";

const AiBuyer = lazy(() =>
  import("../AiBuyer").then((m) => ({ default: m.AiBuyer })),
);

export function Playground({
  capabilities,
}: {
  capabilities: Capabilities | null;
}) {
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
              : "AI chat needs a configured AI provider. You can explore real catalog data and request server quotes directly."}
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
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                marginBottom: 8,
              }}
            >
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
            {filtered.map((p) => {
              const thumbImg = resolveProductImage(p.title, p.image_url);
              return (
                <button
                  className="result"
                  disabled={busy}
                  onClick={() => void startQuote(p)}
                  key={p.product_id}
                >
                  <div className="result-left">
                    {thumbImg && (
                      <img
                        className="result-thumb"
                        src={thumbImg}
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
              );
            })}
            {filtered.length === 0 && (
              <p
                style={{
                  color: "var(--muted)",
                  fontSize: 13,
                  padding: "20px 0",
                  textAlign: "center",
                }}
              >
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
                {resolveProductImage(chosen?.title, chosen?.image_url) && (
                  <img
                    className="result-thumb"
                    src={resolveProductImage(chosen?.title, chosen?.image_url)!}
                    alt={chosen?.title}
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
