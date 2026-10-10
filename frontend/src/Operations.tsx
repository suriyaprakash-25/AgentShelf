import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api";

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

export function Operations() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [csrf, setCsrf] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<Overview>("/api/ops", undefined, controller.signal),
      api<{ csrf_token: string }>("/api/me", undefined, controller.signal),
    ])
      .then(([overview, me]) => {
        setData(overview);
        setCsrf(me.csrf_token);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  async function retry(id: string) {
    if (!window.confirm("Retry this failed job with its existing identifiers?"))
      return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/ops/jobs/${id}/retry`, {}, undefined, { csrf });
      setData(await api<Overview>("/api/ops"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function correlate(orderId: string, providerId: string) {
    if (
      !window.confirm(
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
      setData(await api<Overview>("/api/ops"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <span className="eyebrow">OPERATIONS</span>
      <h1>Review and recover.</h1>
      <Link to="/dashboard">Seller dashboard</Link>
      <p role="alert">{error}</p>
      {data && (
        <>
          <section className="panel">
            <h2>Worker heartbeat</h2>
            {data.workers.length ? (
              data.workers.map((w) => (
                <p key={w.name}>
                  {w.name}: last seen {w.age_seconds}s ago
                  {w.age_seconds > 90 ? " — investigate worker health" : ""}
                </p>
              ))
            ) : (
              <p>No worker heartbeat recorded.</p>
            )}
          </section>
          <h2>Failed jobs ({data.failed_total})</h2>
          <p>
            Showing up to 100 recent failures. Provider delivery may have
            succeeded before an acknowledgement was lost; review before
            retrying.
          </p>
          {data.failed_jobs.map((job) => (
            <section className="panel" key={job.id}>
              <strong>
                {job.kind} · {job.id}
              </strong>
              <p>
                {job.code} · {job.attempts} attempts
              </p>
              <button
                className="button"
                disabled={busy}
                onClick={() => void retry(job.id)}
              >
                Retry job
              </button>
            </section>
          ))}
          <h2>Payment reconciliation</h2>
          <h3>Refunds and disputes</h3>
          {data.adjustments.map((item) => (
            <section className="panel" key={item.resource_id}>
              <strong>
                {item.kind} · {item.resource_id}
              </strong>
              <p>
                Order {item.order_id} · {item.status}
                {item.amount_minor !== null
                  ? ` · $${(item.amount_minor / 100).toFixed(2)} USD`
                  : ""}
              </p>
            </section>
          ))}
          {data.orders.map((order) => (
            <section className="panel" key={order.id}>
              <strong>Order {order.id}</strong>
              <p>
                {order.status} · {order.code}
              </p>
              <p>
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
                  >
                    <label>
                      PayPal order reference found during provider review
                      <input
                        name="provider_id"
                        required
                        maxLength={64}
                        pattern="[A-Za-z0-9-]+"
                        autoComplete="off"
                      />
                    </label>
                    <button className="button secondary" disabled={busy}>
                      Verify reference
                    </button>
                    <p>
                      The server checks the order reference, amount and
                      recipient. Stock remains reserved until payment status is
                      verified.
                    </p>
                  </form>
                )}
            </section>
          ))}
        </>
      )}
    </div>
  );
}
