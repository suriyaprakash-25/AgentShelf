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
import { api } from "./api";
import { ListingStudio } from "./ListingStudio";

// Avoid downloading the licensed feature when this build cannot enable it.
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
  price_minor: number;
  stock: number;
  status: string;
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
      <form onSubmit={submit} className="seller-form">
        <label>
          Email
          <input type="email" name="email" autoComplete="email" required />
        </label>
        <button className="button" disabled={busy}>
          {busy ? "Sending…" : "Email a sign-in link"}
        </button>
      </form>
      <p role="status">{message}</p>
      <Link to="/onboarding">Create a store</Link>
    </div>
  );
}

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
  const [copilotSummary, setCopilotSummary] = useState<CopilotSummary | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const productGrid = useRef<AgGridReact<Product>>(null);
  const orderGrid = useRef<AgGridReact<Order>>(null);
  const initial = useRef(false);
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
    // Initial sign-in consumes a single-use token exactly once, including StrictMode.
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
    const form = event.currentTarget;
    const data = new FormData(form);
    await action("/api/me/products", {
      title: data.get("title"),
      description: data.get("description"),
      price_minor: Math.round(Number(data.get("price")) * 100),
      stock: Number(data.get("stock")),
    });
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
  if (!me)
    return (
      <div className="page narrow">
        <span className="eyebrow">SELLER DASHBOARD</span>
        <h1>
          Your shop.
          <br />
          Your control.
        </h1>
        {loading ? (
          <p role="status">Checking your session…</p>
        ) : (
          <>
            <p role="alert">{error}</p>
            <SignInForm />
          </>
        )}
      </div>
    );
  return (
    <div className="page">
      <span className="eyebrow">SELLER DASHBOARD</span>
      <h1>{me.name}</h1>
      <div className="seller-toolbar">
        <Link to={`/s/${me.store_slug}`}>Open public store</Link>
        {me.is_operator && <Link to="/operations">Operations</Link>}
        <button
          className="button secondary"
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
      <p role="alert">{error}</p>
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <button
        className="button secondary"
        onClick={() => setShowAnalytics((v) => !v)}
      >
        {showAnalytics ? "Close shop analytics" : "Open shop analytics"}
      </button>
      {showAnalytics &&
        (AnalyticsStudio ? (
          <Suspense fallback={<p role="status">Loading analytics…</p>}>
            <AnalyticsStudio csrf={me.csrf_token} />
          </Suspense>
        ) : (
          <p>
            Analytics Studio requires a deployment licence. Your catalog and
            orders remain available below.
          </p>
        ))}
      <ListingStudio csrf={me.csrf_token} refresh={() => load()} />
      <div className="panel">
        <h2>Seller Copilot</h2>
        <p>
          Generate a 7-day sales & stock summary or send a PayPal invoice for a
          custom order (also available on WhatsApp via <code>summary</code>,{" "}
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
          <p role="status" className="notice">
            {copilotSummary.summary}
          </p>
        )}
        <form onSubmit={sendCopilotInvoice} className="seller-form">
          <label>
            Buyer email
            <input name="recipient_email" type="email" required />
          </label>
          <label>
            Invoice amount (USD)
            <input
              name="amount"
              type="number"
              min="0.01"
              max="100000"
              step="0.01"
              required
            />
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
            <input
              name="price"
              type="number"
              min="0.01"
              max="1000000"
              step="0.01"
              required
            />
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
          <button className="button" disabled={busy}>
            Save draft
          </button>
        </form>
        <p>Review your price and details before publishing.</p>
      </div>
      <h2>Products</h2>
      <button
        className="button secondary"
        onClick={() =>
          productGrid.current?.api.exportDataAsCsv({
            fileName: "products-current-page.csv",
            processCellCallback: (p) => csv(p.value),
          })
        }
      >
        Export current product page
      </button>
      <div className="seller-grid">
        <AgGridReact<Product>
          ref={productGrid}
          theme={theme}
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
      <div className="seller-actions">
        {products.map((p) => (
          <div className="panel" key={p.id}>
            <strong>{p.title}</strong>
            <span>
              {p.status} · ${(p.price_minor / 100).toFixed(2)} · {p.stock}{" "}
              available
            </span>
            {p.status === "draft" && (
              <button
                className="button"
                disabled={busy}
                onClick={() => {
                  if (
                    window.confirm(
                      `Publish ${p.title} at $${(p.price_minor / 100).toFixed(2)} USD?`,
                    )
                  )
                    void action(`/api/me/products/${p.id}/publish`, {
                      confirm: true,
                    });
                }}
              >
                Confirm and publish
              </button>
            )}
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => {
                const price = window.prompt(
                  "New price in USD",
                  (p.price_minor / 100).toFixed(2),
                );
                if (price !== null && /^\d+(\.\d{1,2})?$/.test(price))
                  void action(
                    `/api/me/products/${p.id}`,
                    { price_minor: Math.round(Number(price) * 100) },
                    "PATCH",
                  );
              }}
            >
              Edit price
            </button>
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => {
                const stock = window.prompt("Available stock", String(p.stock));
                if (stock !== null && /^\d+$/.test(stock))
                  void action(
                    `/api/me/products/${p.id}`,
                    { stock: Number(stock) },
                    "PATCH",
                  );
              }}
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
                onClick={() => {
                  if (window.confirm("Archive this product?"))
                    void action(`/api/me/products/${p.id}/archive`);
                }}
              >
                Archive
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="seller-toolbar">
        <button
          disabled={productPage === 1 || loading}
          onClick={() => void moveProducts(productPage - 1)}
        >
          Previous products
        </button>
        <span>
          Page {productPage} · {total} products
        </span>
        <button
          disabled={
            products.length < 25 || productPage * 25 >= total || loading
          }
          onClick={() => void moveProducts(productPage + 1)}
        >
          Next products
        </button>
      </div>
      <h2>Orders — newest first</h2>
      <button
        className="button secondary"
        onClick={() =>
          orderGrid.current?.api.exportDataAsCsv({
            fileName: "orders-current-page.csv",
            processCellCallback: (p) => csv(p.value),
          })
        }
      >
        Export current order page
      </button>
      <div className="seller-grid">
        <AgGridReact<Order>
          ref={orderGrid}
          theme={theme}
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
      <div className="seller-toolbar">
        <button
          disabled={orderPage === 1 || loading}
          onClick={() => void moveOrders(orderPage - 1)}
        >
          Previous orders
        </button>
        <span>
          Page {orderPage} · {orderTotal} orders
        </span>
        <button
          disabled={
            orders.length < 25 || orderPage * 25 >= orderTotal || loading
          }
          onClick={() => void moveOrders(orderPage + 1)}
        >
          Next orders
        </button>
      </div>
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
    </div>
  );
}

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
    if (
      !window.confirm(
        `Issue a full PayPal refund for order ${order.id.slice(0, 8)}?`,
      )
    )
      return;
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
      <strong>Order {order.id.slice(0, 8)}</strong>
      <span>{order.status}</span>
      <button className="button secondary" onClick={() => void show()}>
        View order and shipping details
      </button>
      {detail && (
        <>
          {detail.payment_review && (
            <p role="status">
              Payment review: {detail.payment_review}. Contact your operator
              before fulfilment.
            </p>
          )}
          <p>
            {detail.title} × {detail.qty}
          </p>
          {address && (
            <address>
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
            <p>
              {detail.carrier}: {detail.tracking_number}
            </p>
          )}
        </>
      )}
      {order.status === "paid" && (
        <form className="seller-form" onSubmit={submit}>
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
          onClick={() => void refundOrder()}
        >
          Refund order on PayPal
        </button>
      )}
      <p role="alert">{error}</p>
    </div>
  );
}

export function SellerOnboarding() {
  const [message, setMessage] = useState("");
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
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page narrow">
      <span className="eyebrow">FOR INDEPENDENT SELLERS</span>
      <h1>Create your store.</h1>
      <div className="panel">
        <form onSubmit={submit} className="seller-form">
          <label>
            Store name
            <input name="name" minLength={2} maxLength={100} required />
          </label>
          <label>
            Country (two-letter code)
            <input
              name="country"
              pattern="[A-Za-z]{2}"
              maxLength={2}
              placeholder="IN"
              required
            />
          </label>
          <label>
            Sign-in email
            <input name="email" type="email" required />
          </label>
          <label>
            PayPal business email
            <input name="paypal_email" type="email" required />
          </label>
          <label className="consent-label">
            <input name="consent" type="checkbox" required />I confirm these
            store details and consent to storing them for seller account access.
          </label>
          <p>
            We’ll verify your sign-in email before creating the store. Merchant
            payment eligibility is checked separately. Initial shipping is to
            the US and UK in USD.
          </p>
          <button className="button" disabled={busy}>
            {busy ? "Sending…" : "Verify email and create store"}
          </button>
        </form>
        <p role="status">{message}</p>
      </div>
    </div>
  );
}
