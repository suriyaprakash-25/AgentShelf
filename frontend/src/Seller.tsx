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
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const productGrid = useRef<AgGridReact<Product>>(null);
  const orderGrid = useRef<AgGridReact<Order>>(null);
  const initial = useRef(false);
  async function load(currentPage = page) {
    const owner = await api<Me>("/api/me");
    setMe(owner);
    const [catalog, purchases] = await Promise.all([
      api<{ items: Product[]; total: number }>(
        `/api/me/products?page=${currentPage}`,
      ),
      api<{ items: Order[] }>(`/api/me/orders?page=${currentPage}`),
    ]);
    setProducts(catalog.items);
    setTotal(catalog.total);
    setOrders(purchases.items);
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
        await load(1);
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
  async function move(next: number) {
    setLoading(true);
    try {
      await load(next);
      setPage(next);
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
          disabled={page === 1 || loading}
          onClick={() => void move(page - 1)}
        >
          Previous page
        </button>
        <span>
          Page {page} · {total} products
        </span>
        <button
          disabled={(products.length < 25 && orders.length < 25) || loading}
          onClick={() => void move(page + 1)}
        >
          Next page
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
