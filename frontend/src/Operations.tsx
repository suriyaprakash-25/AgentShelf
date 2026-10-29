import { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import { api } from "./api";
import { RefreshCw, Server, AlertTriangle, GitMerge } from "lucide-react";

type Overview = {
  adjustments: {
    order_id: string;
    resource_id: string;
    kind: string;
    status: string;
    amount_minor: number | null;
  }[];
  failed_total: number;
  failed_jobs: { id: string; kind: string; attempts: number; code: string }[];
  orders: {
    id: string;
    status: string;
    paypal_order_id: string | null;
    code: string;
  }[];
  workers: { name: string; age_seconds: number }[];
};

function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s ago`;
  }
  return `${Math.floor(seconds / 3600)}h ago`;
}

function workerStatus(age: number): "ok" | "warning" | "error" {
  if (age < 60) return "ok";
  if (age < 90) return "warning";
  return "error";
}

const STATUS_LABEL: Record<string, string> = {
  paid: "Paid",
  shipped: "Shipped",
  pending: "Pending",
  checkout_created: "Checkout Created",
  refunded: "Refunded",
  failed: "Failed",
  queued: "Queued",
};

function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase().replace(/\s+/g, "_");
  const label = STATUS_LABEL[normalized] ?? value;
  const cls =
    normalized === "paid" || normalized === "shipped"
      ? "badge paid"
      : normalized === "failed"
        ? "badge failed"
        : normalized === "queued"
          ? "badge queued"
          : normalized === "checkout_created"
            ? "badge pending"
            : "badge archived";
  return <span className={cls}>{label}</span>;
}

export function Operations() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [csrf, setCsrf] = useState("");
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function load(signal?: AbortSignal) {
    const [overview, me] = await Promise.all([
      api<Overview>("/api/ops", undefined, signal),
      api<{ csrf_token: string }>("/api/me", undefined, signal),
    ]);
    setData(overview);
    setCsrf(me.csrf_token);
    setLastRefresh(new Date());
  }

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch((e: Error) => {
      if (e.name !== "AbortError") setError(e.message);
    });
    // Auto-refresh every 30 seconds
    intervalRef.current = setInterval(() => {
      load().catch(() => {});
    }, 30_000);
    return () => {
      controller.abort();
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  async function retry(id: string) {
    if (!confirm("Retry this failed job with its existing identifiers?")) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/ops/jobs/${id}/retry`, {}, undefined, { csrf });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function correlate(orderId: string, providerId: string) {
    if (
      !confirm(
        "Verify and attach this PayPal order reference? This does not approve or capture payment.",
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await api(
        `/api/ops/orders/${orderId}/correlate`,
        { paypal_order_id: providerId.trim(), confirmed: true },
        undefined,
        { csrf },
      );
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function manualRefresh() {
    setBusy(true);
    try {
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      {/* Page header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
        <div>
          <span className="eyebrow">OPERATIONS DASHBOARD</span>
          <h1 style={{ marginBottom: 8 }}>Review and recover.</h1>
          <Link to="/dashboard" className="text-link" style={{ marginTop: 0 }}>
            ← Seller dashboard
          </Link>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
          <button
            className="button secondary small"
            disabled={busy}
            onClick={() => void manualRefresh()}
            style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
          >
            <RefreshCw size={14} />
            Refresh
          </button>
          {lastRefresh && (
            <span className="ops-refresh">
              Last updated: {lastRefresh.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {busy && (
        <p role="status" className="notice">
          Verifying your recovery action…
        </p>
      )}
      {!data && !error && (
        <p role="status" className="notice">
          Loading operations…
        </p>
      )}

      {data && (
        <>
          {/* Summary header cards */}
          <div className="ops-header">
            <div className={`ops-stat ${data.failed_total > 0 ? "error" : "ok"}`}>
              <AlertTriangle size={18} style={{ marginBottom: 6, opacity: 0.7 }} />
              <strong>{data.failed_total}</strong>
              <span>Failed Jobs</span>
            </div>
            <div className={`ops-stat ${data.workers.length === 0 ? "error" : "ok"}`}>
              <Server size={18} style={{ marginBottom: 6, opacity: 0.7 }} />
              <strong>{data.workers.length}</strong>
              <span>Active Workers</span>
            </div>
            <div className={`ops-stat ${data.adjustments.length > 0 ? "warning" : "ok"}`}>
              <GitMerge size={18} style={{ marginBottom: 6, opacity: 0.7 }} />
              <strong>{data.adjustments.length}</strong>
              <span>Pending Adjustments</span>
            </div>
          </div>

          {/* Worker heartbeat */}
          <section>
            <h2 style={{ marginTop: 0 }}>Worker heartbeat</h2>
            {data.workers.length ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {data.workers.map((w) => {
                  const s = workerStatus(w.age_seconds);
                  return (
                    <div key={w.name} className={`worker-badge ${s}`}>
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          background:
                            s === "ok"
                              ? "#2e7d32"
                              : s === "warning"
                                ? "#e65100"
                                : "#c62828",
                          display: "inline-block",
                          flexShrink: 0,
                        }}
                      />
                      <strong>{w.name}</strong>
                      <span style={{ opacity: 0.8 }}>
                        {formatAge(w.age_seconds)}
                        {w.age_seconds > 90
                          ? " — investigate worker health"
                          : s === "warning"
                            ? " — check soon"
                            : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="notice error">
                No worker heartbeat recorded. Worker process may be down.
              </p>
            )}
          </section>

          {/* Failed jobs */}
          <section style={{ marginTop: 32 }}>
            <h2>Failed jobs ({data.failed_total})</h2>
            <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 16, lineHeight: 1.6 }}>
              Showing up to 100 recent failures. Provider delivery may have
              succeeded before an acknowledgement was lost — review before
              retrying.
            </p>
            {!data.failed_jobs.length ? (
              <p
                className="notice"
                style={{ background: "var(--color-success-bg)", color: "var(--color-success-text)", borderLeft: "3px solid var(--color-success-border)" }}
              >
                No failed jobs to review.
              </p>
            ) : (
              <div style={{ display: "grid", gap: 12 }}>
                {data.failed_jobs.map((job) => (
                  <section className="panel" key={job.id} style={{ display: "grid", gap: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                      <div>
                        <strong style={{ fontSize: 14, fontFamily: "Manrope, sans-serif" }}>
                          {job.kind}
                        </strong>
                        <span className="badge failed" style={{ marginLeft: 10 }}>
                          Failed
                        </span>
                      </div>
                      <button
                        className="button small"
                        disabled={busy}
                        onClick={() => void retry(job.id)}
                      >
                        Retry job
                      </button>
                    </div>
                    <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 12, color: "var(--muted)" }}>
                      <span>
                        <strong>Code:</strong> {job.code}
                      </span>
                      <span>
                        <strong>Attempts:</strong> {job.attempts}
                      </span>
                      <span
                        title={job.id}
                        style={{ fontFamily: "monospace", fontSize: 11, background: "#eff1e6", padding: "2px 6px", borderRadius: 4 }}
                      >
                        {job.id.slice(0, 16)}…
                      </span>
                    </div>
                  </section>
                ))}
              </div>
            )}
          </section>

          {/* Payment reconciliation */}
          <section style={{ marginTop: 32 }}>
            <h2>Payment reconciliation</h2>
            <h3>Refunds and disputes</h3>
            {!data.adjustments.length ? (
              <p
                className="notice"
                style={{ background: "var(--color-success-bg)", color: "var(--color-success-text)" }}
              >
                No refunds or disputes recorded.
              </p>
            ) : (
              <div style={{ display: "grid", gap: 12 }}>
                {data.adjustments.map((item) => (
                  <section className="panel" key={item.resource_id}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                      <strong style={{ fontFamily: "Manrope, sans-serif", fontSize: 14 }}>
                        {item.kind}
                      </strong>
                      <StatusBadge value={item.status} />
                    </div>
                    <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                      Order {item.order_id.slice(0, 8)}
                      {item.amount_minor !== null
                        ? ` · $${(item.amount_minor / 100).toFixed(2)} USD`
                        : ""}
                    </div>
                    <div
                      style={{ fontFamily: "monospace", fontSize: 11, background: "#eff1e6", padding: "3px 8px", borderRadius: 4, width: "fit-content", color: "var(--muted)" }}
                    >
                      {item.resource_id}
                    </div>
                  </section>
                ))}
              </div>
            )}

            <h3 style={{ marginTop: 24 }}>Payment orders awaiting review</h3>
            {!data.orders.length ? (
              <p
                className="notice"
                style={{ background: "var(--color-success-bg)", color: "var(--color-success-text)" }}
              >
                No payment orders awaiting review.
              </p>
            ) : (
              <div style={{ display: "grid", gap: 12 }}>
                {data.orders.map((order) => (
                  <section className="panel" key={order.id}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                      <strong style={{ fontFamily: "Manrope, sans-serif", fontSize: 14 }}>
                        Order {order.id.slice(0, 8)}
                      </strong>
                      <StatusBadge value={order.status} />
                    </div>
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: "4px 0" }}>
                      Error code: {order.code}
                    </p>
                    <p style={{ fontSize: 12, margin: "4px 0" }}>
                      PayPal reference:{" "}
                      {order.paypal_order_id || "Create response uncertain"}
                    </p>
                    {!order.paypal_order_id &&
                      order.status === "checkout_created" && (
                        <form
                          onSubmit={(event) => {
                            event.preventDefault();
                            const form = new FormData(event.currentTarget);
                            void correlate(
                              order.id,
                              String(form.get("provider_id") || ""),
                            );
                          }}
                          style={{ marginTop: 12, padding: 16, background: "#fafaf5", borderRadius: 8, border: "1px solid var(--line)" }}
                        >
                          <p
                            className="notice"
                            style={{ marginTop: 0, fontSize: 11 }}
                          >
                            The server checks the order reference, amount and
                            recipient. Stock remains reserved until payment status is
                            verified.
                          </p>
                          <label>
                            PayPal order reference found during provider review
                            <input
                              name="provider_id"
                              required
                              maxLength={64}
                              pattern="[A-Za-z0-9-]+"
                              autoComplete="off"
                              placeholder="e.g. 5O190127TN364715T"
                            />
                          </label>
                          <button
                            className="button secondary"
                            disabled={busy}
                            style={{ marginTop: 12 }}
                          >
                            Verify reference
                          </button>
                        </form>
                      )}
                  </section>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
