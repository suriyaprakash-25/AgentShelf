import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowRight,
  Globe2,
  Layers3,
  ShieldCheck,
  ShoppingBag,
} from "lucide-react";
import { api, type Store } from "../api";
import { resolveProductImage } from "../productImages";

export function ProductArt({
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

export function StorePage() {
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
              {store.products.length} product
              {store.products.length !== 1 ? "s" : ""}
              {store.next_cursor ? " · scroll for more" : ""}
            </p>
          )}
        </div>
        <div className="seller-toolbar">
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 12,
              whiteSpace: "nowrap",
            }}
          >
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
                <div
                  className="skeleton"
                  style={{ height: 12, width: "40%", marginBottom: 12 }}
                />
                <div
                  className="skeleton"
                  style={{ height: 20, width: "80%", marginBottom: 10 }}
                />
                <div
                  className="skeleton"
                  style={{ height: 12, width: "100%", marginBottom: 6 }}
                />
                <div
                  className="skeleton"
                  style={{ height: 12, width: "70%" }}
                />
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
              const productImg = resolveProductImage(p.title, p.image_url);
              return (
                <article className="product-card" key={p.product_id}>
                  {productImg ? (
                    <img
                      className="product-photo"
                      src={productImg}
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
                    <span
                      className={`stock-badge ${p.in_stock ? "in-stock" : "out-of-stock"}`}
                    >
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
            <div
              className="empty"
              style={{
                marginTop: 40,
                border: "1px solid var(--line)",
                borderRadius: 8,
              }}
            >
              <ShoppingBag size={32} style={{ opacity: 0.4 }} />
              <h3>No products yet</h3>
              <p>
                This shop has no available products right now. Please check back
                soon.
              </p>
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
            <Layers3
              size={28}
              style={{ flexShrink: 0, color: "var(--muted)" }}
            />
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
