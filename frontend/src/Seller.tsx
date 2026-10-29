import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link } from "react-router-dom";
import { AgGridReact } from "ag-grid-react";
import {
  ClientSideRowModelModule,
  CsvExportModule,
  TextFilterModule,
  NumberFilterModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
} from "ag-grid-community";
import { api, uploadPhoto } from "./api";
import { ListingStudio } from "./ListingStudio";
import { CheckCircle, X, ChevronLeft, ChevronRight } from "lucide-react";

const AnalyticsStudio =
  import.meta.env.DEV || import.meta.env.VITE_AG_STUDIO_LICENSE_KEY
    ? lazy(() => import("./AnalyticsStudio"))
    : null;

ModuleRegistry.registerModules([
  ClientSideRowModelModule,
  CsvExportModule,
  TextFilterModule,
  NumberFilterModule,
]);
const theme = themeQuartz.withParams({
  accentColor: "#45533b",
  backgroundColor: "#faf8f3",
  foregroundColor: "#252b22",
  borderColor: "#deded1",
});
type Me = {
  name: string;
  store_slug: string;
  csrf_token: string;
  is_operator: boolean;
};
type Product = {
  id: string;
  title: string;
  description?: string;
  price_minor: number;
  stock: number;
  status: string;
  images?: string[];
};
type Order = {
  id: string;
  status: string;
  amount_minor: number;
  currency: string;
  created_at: string;
};
type CopilotSummary = {
  summary: string;
  paid_or_shipped_orders: number;
  gross_paid_minor: number;
  refunded_orders: number;
  refunded_minor: number;
};
const productColumns: ColDef<Product>[] = [
  { field: "title", flex: 2 },
  {
    field: "price_minor",
    headerName: "Price (USD)",
    valueFormatter: (p) => ((p.value || 0) / 100).toFixed(2),
  },
  { field: "stock", headerName: "Available stock" },
  { field: "status" },
];
const orderColumns: ColDef<Order>[] = [
  { field: "id", headerName: "Order", flex: 2 },
  { field: "status" },
  {
    field: "amount_minor",
    headerName: "Total (USD)",
    valueFormatter: (p) => ((p.value || 0) / 100).toFixed(2),
  },
  { field: "created_at", headerName: "Created", flex: 2 },
];

/* ============================================================
   CONFIRM DIALOG
   ============================================================ */
function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  danger = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="dialog-overlay" onClick={onCancel}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="dialog-actions">
          <button className="button secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            className={`button ${danger ? "danger" : ""}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   INLINE EDIT DIALOG
   ============================================================ */
function InlineEditDialog({
  title,
  label,
  initialValue,
  inputType = "text",
  onSave,
  onCancel,
}: {
  title: string;
  label: string;
  initialValue: string;
  inputType?: string;
  onSave: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initialValue);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);
  return (
    <div className="dialog-overlay" onClick={onCancel}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button
            className="text-link"
            onClick={onCancel}
            style={{ padding: 0, minHeight: "auto" }}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>
        <div className="dialog-input-wrapper">
          <label>{label}</label>
          <input
            ref={inputRef}
            type={inputType}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSave(value);
              if (e.key === "Escape") onCancel();
            }}
          />
        </div>
        <div className="dialog-actions">
          <button className="button secondary" onClick={onCancel}>
            Cancel
          </button>
          <button className="button" onClick={() => onSave(value)}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   STATUS BADGE
   ============================================================ */
function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  return <span className={`badge ${normalized}`}>{status}</span>;
}

/* ============================================================
   DASHBOARD SKELETON
   ============================================================ */
function DashboardSkeleton() {
  return (
    <div className="page">
      <div
        style={{
          marginBottom: 24,
          paddingBottom: 24,
          borderBottom: "1px solid var(--line)",
        }}
      >
        <div
          className="skeleton"
          style={{ height: 14, width: 140, marginBottom: 12 }}
        />
        <div className="skeleton" style={{ height: 48, width: 260 }} />
      </div>
      <div className="seller-workspace-grid">
        {[1, 2, 3].map((i) => (
          <div key={i} className="panel">
            <div
              className="skeleton"
              style={{ height: 22, width: "55%", marginBottom: 16 }}
            />
            <div
              className="skeleton"
              style={{ height: 12, width: "80%", marginBottom: 8 }}
            />
            <div
              className="skeleton"
              style={{ height: 12, width: "65%", marginBottom: 24 }}
            />
            <div className="skeleton" style={{ height: 44, borderRadius: 7 }} />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ============================================================
   SIGN IN FORM
   ============================================================ */
function SignInForm() {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const email = new FormData(event.currentTarget).get("email");
    try {
      const result = await api<{ message: string }>("/api/auth/request-link", {
        email,
      });
      setMessage(result.message);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="panel">
      <h2>Sign in to your store</h2>
      <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 20 }}>
        Enter your email and we'll send you a magic sign-in link. No password
        needed.
      </p>
      <form onSubmit={submit} className="seller-form">
        <label>
          Email address
          <input
            type="email"
            name="email"
            autoComplete="email"
            required
            placeholder="you@example.com"
          />
        </label>
        <button className="button" disabled={busy}>
          {busy ? "Sending…" : "Email a sign-in link"}
        </button>
      </form>
      {message && (
        <p role="status" className="notice" style={{ marginTop: 12 }}>
          {message}
        </p>
      )}
      <p style={{ marginTop: 16, fontSize: 12, color: "var(--muted)" }}>
        Don't have a store?{" "}
        <Link
          to="/onboarding"
          style={{ color: "var(--green)", fontWeight: 600 }}
        >
          Create one →
        </Link>
      </p>
    </div>
  );
}

/* ============================================================
   SELLER DASHBOARD
   ============================================================ */
export function SellerDashboard() {
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [productPage, setProductPage] = useState(1);
  const [orderPage, setOrderPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [orderTotal, setOrderTotal] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copilotSummary, setCopilotSummary] =
    useState<CopilotSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const productGrid = useRef<AgGridReact<Product>>(null);
  const orderGrid = useRef<AgGridReact<Order>>(null);
  const initial = useRef(false);

  // Dialog states
  const [priceDialog, setPriceDialog] = useState<Product | null>(null);
  const [stockDialog, setStockDialog] = useState<Product | null>(null);
  const [archiveDialog, setArchiveDialog] = useState<Product | null>(null);
  const [publishDialog, setPublishDialog] = useState<Product | null>(null);

  async function load(
    currentProductPage = productPage,
    currentOrderPage = orderPage,
  ) {
    const owner = await api<Me>("/api/me");
    setMe(owner);
    const [catalog, purchases] = await Promise.all([
      api<{ items: Product[]; total: number }>(
        `/api/me/products?page=${currentProductPage}`,
      ),
      api<{ items: Order[]; total?: number }>(
        `/api/me/orders?page=${currentOrderPage}`,
      ),
    ]);
    setProducts(catalog.items);
    setTotal(catalog.total);
    setOrders(purchases.items);
    setOrderTotal(purchases.total ?? purchases.items.length);
  }

  useEffect(() => {
    if (initial.current) return;
    initial.current = true;
    const token = new URLSearchParams(window.location.hash.slice(1)).get(
      "sign-in",
    );
    if (token) window.history.replaceState(null, "", window.location.pathname);
    (async () => {
      try {
        if (token) await api("/api/auth/redeem", { token });
        await load(1, 1);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function action(path: string, body: unknown = {}, method = "POST") {
    if (!me) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(path, body, undefined, { method, csrf: me.csrf_token });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!me) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const photoFile = data.get("photo");
    let media_id: string | undefined;
    if (photoFile instanceof File && photoFile.size > 0) {
      setBusy(true);
      setError("");
      try {
        const uploaded = await uploadPhoto(photoFile, me.csrf_token);
        media_id = uploaded.id;
      } catch (e) {
        setError((e as Error).message);
        setBusy(false);
        return;
      }
    }
    await action("/api/me/products", {
      title: data.get("title"),
      description: data.get("description"),
      price_minor: Math.round(Number(data.get("price")) * 100),
      stock: Number(data.get("stock")),
      ...(media_id ? { media_id } : {}),
    });
    form.reset();
  }

  async function loadCopilotSummary() {
    setBusy(true);
    setError("");
    try {
      setCopilotSummary(await api<CopilotSummary>("/api/me/copilot/summary"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function sendCopilotInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!me) return;
    setBusy(true);
    setError("");
    setNotice("");
    const data = new FormData(event.currentTarget);
    try {
      const result = await api<{
        invoice_id: string;
        amount: string;
        currency: string;
      }>(
        "/api/me/copilot/invoices",
        {
          recipient_email: data.get("recipient_email"),
          amount_minor: Math.round(Number(data.get("amount")) * 100),
          note: data.get("note"),
          confirm: true,
        },
        undefined,
        { csrf: me.csrf_token },
      );
      setNotice(
        `PayPal invoice ${result.invoice_id} sent (${result.amount} ${result.currency}).`,
      );
      event.currentTarget.reset();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function moveProducts(next: number) {
    setLoading(true);
    try {
      await load(next, orderPage);
      setProductPage(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function moveOrders(next: number) {
    setLoading(true);
    try {
      await load(productPage, next);
      setOrderPage(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function csv(value: unknown) {
    const text = String(value ?? "");
    return /^[=+@\-\t\r\n]/.test(text.trimStart()) ? "'" + text : text;
  }

  if (loading) return <DashboardSkeleton />;

  if (!me)
    return (
      <div className="page narrow">
        <span className="eyebrow">SELLER DASHBOARD</span>
        <h1>
          Your shop.
          <br />
          Your control.
        </h1>
        {error && (
          <p role="alert" className="notice error">
            {error}
          </p>
        )}
        <SignInForm />
      </div>
    );

  const totalProductPages = Math.max(1, Math.ceil(total / 25));
  const totalOrderPages = Math.max(1, Math.ceil(orderTotal / 25));

  return (
    <div className="page">
      {/* Confirm dialogs */}
      {archiveDialog && (
        <ConfirmDialog
          title="Archive product"
          message={`Archive "${archiveDialog.title}"? It will be hidden from your store.`}
          confirmLabel="Archive"
          danger
          onConfirm={() => {
            void action(`/api/me/products/${archiveDialog.id}/archive`);
            setArchiveDialog(null);
          }}
          onCancel={() => setArchiveDialog(null)}
        />
      )}
      {publishDialog && (
        <ConfirmDialog
          title="Publish product"
          message={`Publish "${publishDialog.title}" at $${(publishDialog.price_minor / 100).toFixed(2)} USD? Buyers will be able to purchase it.`}
          confirmLabel="Publish"
          onConfirm={() => {
            void action(`/api/me/products/${publishDialog.id}/publish`, {
              confirm: true,
            });
            setPublishDialog(null);
          }}
          onCancel={() => setPublishDialog(null)}
        />
      )}
      {priceDialog && (
        <InlineEditDialog
          title="Edit price"
          label="New price in USD"
          initialValue={(priceDialog.price_minor / 100).toFixed(2)}
          inputType="number"
          onSave={(val) => {
            if (/^\d+(\.\d{1,2})?$/.test(val)) {
              void action(
                `/api/me/products/${priceDialog.id}`,
                { price_minor: Math.round(Number(val) * 100) },
                "PATCH",
              );
            }
            setPriceDialog(null);
          }}
          onCancel={() => setPriceDialog(null)}
        />
      )}
      {stockDialog && (
        <InlineEditDialog
          title="Edit stock"
          label="Available stock"
          initialValue={String(stockDialog.stock)}
          inputType="number"
          onSave={(val) => {
            if (/^\d+$/.test(val)) {
              void action(
                `/api/me/products/${stockDialog.id}`,
                { stock: Number(val) },
                "PATCH",
              );
            }
            setStockDialog(null);
          }}
          onCancel={() => setStockDialog(null)}
        />
      )}

      <div className="seller-header-bar">
        <div>
          <span className="eyebrow">SELLER DASHBOARD</span>
          <h1>{me.name}</h1>
        </div>
        <div className="seller-toolbar">
          <Link className="button secondary small" to={`/s/${me.store_slug}`}>
            Open public store
          </Link>
          <button
            className="button secondary small"
            onClick={() => setShowAnalytics((v) => !v)}
          >
            {showAnalytics ? "Close shop analytics" : "Open shop analytics"}
          </button>
          {me.is_operator && (
            <Link className="button secondary small" to="/operations">
              Operations
            </Link>
          )}
          <button
            className="button secondary small"
            disabled={busy}
            onClick={async () => {
              try {
                await api("/api/auth/logout", {}, undefined, {
                  csrf: me.csrf_token,
                });
                setMe(null);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Sign out
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {notice && (
        <p
          role="status"
          className="notice success"
          style={{ display: "flex", alignItems: "center", gap: 8 }}
        >
          <CheckCircle size={16} /> {notice}
        </p>
      )}

      {showAnalytics &&
        (AnalyticsStudio ? (
          <Suspense fallback={<p role="status">Loading analytics…</p>}>
            <AnalyticsStudio csrf={me.csrf_token} />
          </Suspense>
        ) : (
          <p className="notice">
            Analytics Studio requires a deployment licence. Your catalog and
            orders remain available below.
          </p>
        ))}

      <div className="seller-workspace-grid">
        <ListingStudio csrf={me.csrf_token} refresh={() => load()} />

        {/* Seller Copilot */}
        <div className="panel">
          <h2>Seller Copilot</h2>
          <p>
            Generate a 7-day sales & stock summary or send a PayPal invoice for
            a custom order (also available on WhatsApp via <code>summary</code>,{" "}
            <code>invoice</code> and <code>refund #order confirm</code>).
          </p>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => void loadCopilotSummary()}
          >
            Generate 7-day summary
          </button>
          {copilotSummary && (
            <p role="status" className="notice" style={{ marginTop: 12 }}>
              {copilotSummary.summary}
            </p>
          )}
          <form
            onSubmit={sendCopilotInvoice}
            className="seller-form"
            style={{ marginTop: 16 }}
          >
            <label>
              Buyer email
              <input
                name="recipient_email"
                type="email"
                required
                placeholder="buyer@example.com"
              />
            </label>
            <label>
              Invoice amount (USD)
              <div className="input-prefix-wrapper">
                <span className="input-prefix">$</span>
                <input
                  name="amount"
                  type="number"
                  min="0.01"
                  max="100000"
                  step="0.01"
                  required
                />
              </div>
            </label>
            <label>
              Custom order description
              <input name="note" maxLength={240} required />
            </label>
            <button className="button" disabled={busy}>
              Send PayPal invoice
            </button>
          </form>
        </div>

        {/* Create product draft */}
        <div className="panel">
          <h2>Create a product draft</h2>
          <form onSubmit={create} className="seller-form">
            <label>
              Title
              <input name="title" maxLength={80} required />
            </label>
            <label>
              Description
              <textarea name="description" maxLength={600} required />
            </label>
            <label>
              Price in USD
              <div className="input-prefix-wrapper">
                <span className="input-prefix">$</span>
                <input
                  name="price"
                  type="number"
                  min="0.01"
                  max="1000000"
                  step="0.01"
                  required
                />
              </div>
            </label>
            <label>
              Available stock
              <input
                name="stock"
                type="number"
                min="0"
                max="1000000"
                step="1"
                required
              />
            </label>
            <label>
              Product photo (optional)
              <input
                name="photo"
                type="file"
                accept="image/jpeg,image/png,image/webp"
              />
            </label>
            <button className="button" disabled={busy}>
              Save draft
            </button>
          </form>
          <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>
            Review your price and details before publishing.
          </p>
        </div>
      </div>

      {/* Products section */}
      <div className="section-header">
        <h2>Products</h2>
        <button
          className="button secondary small"
          onClick={() =>
            productGrid.current?.api.exportDataAsCsv({
              fileName: "products-current-page.csv",
              processCellCallback: (p) => csv(p.value),
            })
          }
        >
          Export CSV
        </button>
      </div>

      {products.length === 0 && !loading ? (
        <div
          className="empty"
          style={{
            border: "1px solid var(--line)",
            borderRadius: 8,
            marginTop: 16,
          }}
        >
          <h3>No products yet</h3>
          <p>
            Use the Listing Studio above to upload photos, or create a product
            manually.
          </p>
        </div>
      ) : (
        <div className="seller-grid">
          <AgGridReact<Product>
            ref={productGrid}
            theme={theme}
            domLayout="autoHeight"
            rowData={products}
            columnDefs={productColumns}
            defaultColDef={{
              sortable: true,
              filter: true,
              resizable: true,
              minWidth: 130,
            }}
            getRowId={(p) => p.data.id}
          />
        </div>
      )}

      {/* Product action cards */}
      <div className="seller-actions">
        {products.map((p) => (
          <div className="panel" key={p.id}>
            {p.images?.[0] && (
              <img
                className="seller-card-photo"
                src={p.images[0]}
                alt={p.title}
                loading="lazy"
              />
            )}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 8,
              }}
            >
              <strong>{p.title}</strong>
              <StatusBadge status={p.status} />
            </div>
            {p.description && (
              <p className="seller-card-desc">{p.description}</p>
            )}
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "var(--green)",
              }}
            >
              ${(p.price_minor / 100).toFixed(2)} USD · {p.stock} in stock
            </div>
            {p.status === "draft" && (
              <button
                className="button"
                disabled={busy}
                onClick={() => setPublishDialog(p)}
              >
                Confirm and publish
              </button>
            )}
            <label
              className="button secondary"
              style={{ cursor: "pointer", textAlign: "center" }}
            >
              {p.images?.[0] ? "Change photo" : "Upload photo"}
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                hidden
                disabled={busy}
                onChange={async (e) => {
                  const file = e.currentTarget.files?.[0];
                  e.currentTarget.value = "";
                  if (!file || !me) return;
                  setBusy(true);
                  setError("");
                  try {
                    const uploaded = await uploadPhoto(file, me.csrf_token);
                    await action(
                      `/api/me/products/${p.id}`,
                      { media_id: uploaded.id },
                      "PATCH",
                    );
                  } catch (err) {
                    setError((err as Error).message);
                    setBusy(false);
                  }
                }}
              />
            </label>
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => setPriceDialog(p)}
            >
              Edit price
            </button>
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => setStockDialog(p)}
            >
              Edit stock
            </button>
            {p.status === "live" && (
              <button
                className="button secondary"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  setNotice("");
                  try {
                    const synced = await api<{ paypal_product_id: string }>(
                      `/api/me/products/${p.id}/paypal-catalog`,
                      {},
                      undefined,
                      { csrf: me.csrf_token },
                    );
                    setNotice(
                      `Mirrored to PayPal Catalog (${synced.paypal_product_id}).`,
                    );
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Mirror to PayPal Catalog
              </button>
            )}
            {p.status !== "archived" && (
              <button
                className="text-link"
                disabled={busy}
                onClick={() => setArchiveDialog(p)}
                style={{ color: "#c62828" }}
              >
                Archive product
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Product pagination */}
      <div className="pagination">
        <button
          className="pagination-btn"
          disabled={productPage === 1 || loading}
          onClick={() => void moveProducts(productPage - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="pagination-info">
          Page {productPage} of {totalProductPages} · {total} products
        </span>
        <button
          className="pagination-btn"
          disabled={
            products.length < 25 || productPage * 25 >= total || loading
          }
          onClick={() => void moveProducts(productPage + 1)}
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {/* Orders section */}
      <div className="section-header">
        <h2>Orders — newest first</h2>
        <button
          className="button secondary small"
          onClick={() =>
            orderGrid.current?.api.exportDataAsCsv({
              fileName: "orders-current-page.csv",
              processCellCallback: (p) => csv(p.value),
            })
          }
        >
          Export CSV
        </button>
      </div>

      <div className="seller-grid">
        <AgGridReact<Order>
          ref={orderGrid}
          theme={theme}
          domLayout="autoHeight"
          rowData={orders}
          columnDefs={orderColumns}
          defaultColDef={{
            sortable: true,
            filter: true,
            resizable: true,
            minWidth: 130,
          }}
          getRowId={(p) => p.data.id}
        />
      </div>

      {/* Order action cards */}
      <div className="seller-actions">
        {orders.map((order) => (
          <Fulfilment
            key={order.id}
            order={order}
            csrf={me.csrf_token}
            refresh={() => load()}
          />
        ))}
      </div>

      {/* Orders pagination */}
      <div className="pagination">
        <button
          className="pagination-btn"
          disabled={orderPage === 1 || loading}
          onClick={() => void moveOrders(orderPage - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="pagination-info">
          Page {orderPage} of {totalOrderPages} · {orderTotal} orders
        </span>
        <button
          className="pagination-btn"
          disabled={
            orders.length < 25 || orderPage * 25 >= orderTotal || loading
          }
          onClick={() => void moveOrders(orderPage + 1)}
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

/* ============================================================
   FULFILMENT
   ============================================================ */
type Detail = {
  payment_review: string | null;
  title: string;
  qty: number;
  carrier: string | null;
  tracking_number: string | null;
  ship_to: {
    name?: { full_name?: string };
    address?: Record<string, string>;
  } | null;
};

function Fulfilment({
  order,
  csrf,
  refresh,
}: {
  order: Order;
  csrf: string;
  refresh: () => Promise<void>;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showRefundConfirm, setShowRefundConfirm] = useState(false);
  const path = `/api/me/orders/${order.id}`;

  async function show() {
    try {
      setDetail(await api<Detail>(path));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await api(
        path + "/tracking",
        {
          carrier: data.get("carrier"),
          tracking_number: data.get("tracking_number"),
        },
        undefined,
        { csrf },
      );
      await show();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function refundOrder() {
    setBusy(true);
    setError("");
    try {
      await api(path + "/refund", { confirm: true }, undefined, { csrf });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const address = detail?.ship_to?.address;

  return (
    <div className="panel">
      {showRefundConfirm && (
        <ConfirmDialog
          title="Issue refund"
          message={`Issue a full PayPal refund for order ${order.id.slice(0, 8)}? This cannot be undone.`}
          confirmLabel="Refund"
          danger
          onConfirm={() => {
            setShowRefundConfirm(false);
            void refundOrder();
          }}
          onCancel={() => setShowRefundConfirm(false)}
        />
      )}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
        }}
      >
        <strong>Order {order.id.slice(0, 8)}</strong>
        <StatusBadge status={order.status} />
      </div>

      <button
        className="button secondary small"
        onClick={() => void show()}
        style={{ marginTop: 8 }}
      >
        View shipping details
      </button>

      {detail && (
        <>
          {detail.payment_review && (
            <p className="notice" role="status">
              ⚠️ Payment review: {detail.payment_review}. Contact your operator
              before fulfilment.
            </p>
          )}
          <p style={{ fontSize: 13 }}>
            {detail.title} × {detail.qty}
          </p>
          {address && (
            <address
              style={{
                fontSize: 12,
                color: "var(--muted)",
                fontStyle: "normal",
                lineHeight: 1.6,
              }}
            >
              {detail.ship_to?.name?.full_name}
              <br />
              {[
                address.address_line_1,
                address.address_line_2,
                address.admin_area_2,
                address.admin_area_1,
                address.postal_code,
                address.country_code,
              ]
                .filter(Boolean)
                .join(", ")}
            </address>
          )}
          {detail.tracking_number && (
            <p style={{ fontSize: 12 }}>
              <strong>{detail.carrier}:</strong> {detail.tracking_number}
            </p>
          )}
        </>
      )}

      {order.status === "paid" && (
        <form
          className="seller-form"
          onSubmit={submit}
          style={{ marginTop: 12 }}
        >
          <label>
            Carrier
            <input name="carrier" placeholder="DHL" maxLength={64} required />
          </label>
          <label>
            Tracking number
            <input
              name="tracking_number"
              pattern="[A-Za-z0-9-]+"
              maxLength={64}
              required
            />
          </label>
          <button className="button" disabled={busy}>
            {busy ? "Verifying tracking…" : "Send tracking to PayPal"}
          </button>
        </form>
      )}

      {(order.status === "paid" || order.status === "shipped") && (
        <button
          type="button"
          className="text-link"
          disabled={busy}
          onClick={() => setShowRefundConfirm(true)}
          style={{ color: "#c62828", marginTop: 8 }}
        >
          Refund order on PayPal
        </button>
      )}

      {error && (
        <p role="alert" className="notice error" style={{ marginTop: 8 }}>
          {error}
        </p>
      )}
    </div>
  );
}

/* ============================================================
   SELLER ONBOARDING
   ============================================================ */

const COUNTRIES = [
  { code: "IN", name: "India 🇮🇳" },
  { code: "US", name: "United States 🇺🇸" },
  { code: "GB", name: "United Kingdom 🇬🇧" },
  { code: "AU", name: "Australia 🇦🇺" },
  { code: "CA", name: "Canada 🇨🇦" },
  { code: "DE", name: "Germany 🇩🇪" },
  { code: "FR", name: "France 🇫🇷" },
  { code: "JP", name: "Japan 🇯🇵" },
  { code: "SG", name: "Singapore 🇸🇬" },
  { code: "AE", name: "UAE 🇦🇪" },
  { code: "MX", name: "Mexico 🇲🇽" },
  { code: "BR", name: "Brazil 🇧🇷" },
  { code: "NG", name: "Nigeria 🇳🇬" },
  { code: "ZA", name: "South Africa 🇿🇦" },
  { code: "PH", name: "Philippines 🇵🇭" },
  { code: "TH", name: "Thailand 🇹🇭" },
  { code: "ID", name: "Indonesia 🇮🇩" },
  { code: "NL", name: "Netherlands 🇳🇱" },
  { code: "IT", name: "Italy 🇮🇹" },
  { code: "ES", name: "Spain 🇪🇸" },
];

export function SellerOnboarding() {
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const data = new FormData(event.currentTarget);
    try {
      const result = await api<{ message: string }>("/api/onboarding", {
        name: data.get("name"),
        country: String(data.get("country")).toUpperCase(),
        email: data.get("email"),
        paypal_email: data.get("paypal_email"),
        consent: data.get("consent") === "on",
      });
      setMessage(result.message);
      setSuccess(true);
    } catch (e) {
      setMessage((e as Error).message);
      setSuccess(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page narrow">
      <span className="eyebrow">FOR INDEPENDENT SELLERS</span>
      <h1>Create your store.</h1>

      {/* Step progress indicator */}
      <div className="step-progress">
        <div className={`step-progress-item ${!success ? "active" : "done"}`}>
          <div className="step-num">
            {success ? <CheckCircle size={12} /> : "1"}
          </div>
          Store details
        </div>
        <div className="step-connector" />
        <div className={`step-progress-item ${success ? "active" : ""}`}>
          <div className="step-num">2</div>
          Email verification
        </div>
      </div>

      <div className="panel">
        {success ? (
          <div className="success-state">
            <div className="success-icon">
              <CheckCircle size={36} />
            </div>
            <h2>Almost there!</h2>
            <p>{message}</p>
            <p>
              Check your inbox for a sign-in link to access your seller dashboard
              and start listing products.
            </p>
            <Link
              to="/dashboard"
              className="button"
              style={{ marginTop: 20, display: "inline-flex" }}
            >
              Go to dashboard →
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="seller-form">
            <label>
              Store name
              <input
                name="name"
                minLength={2}
                maxLength={100}
                required
                placeholder="Jaipur Textiles Studio"
                autoComplete="organization"
              />
            </label>
            <label>
              Country
              <select name="country" required>
                <option value="">Select your country…</option>
                {COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Sign-in email
              <input
                name="email"
                type="email"
                required
                placeholder="you@example.com"
                autoComplete="email"
              />
              <span className="field-hint">
                We'll send a magic link here — no password needed.
              </span>
            </label>
            <label>
              PayPal business email
              <input
                name="paypal_email"
                type="email"
                required
                placeholder="business@paypal.com"
                autoComplete="email"
              />
              <span className="field-hint">
                The email registered with your PayPal business account. Buyers pay
                to this address. Must be a verified PayPal account.
              </span>
            </label>
            <label className="consent-label">
              <input name="consent" type="checkbox" required />I confirm these
              store details and consent to storing them for seller account access.
            </label>
            <div className="notice" style={{ margin: 0, fontSize: 11 }}>
              We'll verify your sign-in email before creating the store. Initial
              shipping is to the US and UK in USD. Merchant payment eligibility
              is checked separately.
            </div>
            <button className="button" disabled={busy}>
              {busy ? "Sending…" : "Verify email and create store →"}
            </button>
            {message && !success && (
              <p role="alert" className="notice error">
                {message}
              </p>
            )}
          </form>
        )}

        <p
          style={{
            marginTop: 20,
            fontSize: 12,
            color: "var(--muted)",
            textAlign: "center",
          }}
        >
          Already have a store?{" "}
          <Link
            to="/dashboard"
            style={{ color: "var(--green)", fontWeight: 600 }}
          >
            Sign in →
          </Link>
        </p>
      </div>
    </div>
  );
}
