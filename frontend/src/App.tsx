import { lazy, Suspense, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { ArrowRight, Layers3 } from "lucide-react";
import { api, type Capabilities } from "./api";
import { Home } from "./pages/Home";
import "./styles.css";

const StorePage = lazy(() =>
  import("./pages/StorePage").then((m) => ({ default: m.StorePage })),
);
const Playground = lazy(() =>
  import("./pages/Playground").then((m) => ({ default: m.Playground })),
);
const Receipt = lazy(() =>
  import("./pages/Receipt").then((m) => ({ default: m.Receipt })),
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
                  <Link
                    className="button"
                    to="/"
                    style={{ marginTop: 16, display: "inline-flex" }}
                  >
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
