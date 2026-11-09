import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle } from "lucide-react";
import { api } from "../api";

const STATUS_LABELS: Record<string, string> = {
  paid: "✓ Payment Confirmed",
  shipped: "📦 Order Shipped",
  pending: "⏳ Payment Pending",
  refunded: "↩ Refunded",
  cancelled: "✕ Cancelled",
};

export function Receipt() {
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

  const isSuccess = result?.status === "paid" || result?.status === "shipped";

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

      {/* Every state has exactly one page heading for screen-reader navigation. */}
      {!isSuccess && (
        <h1>
          {error
            ? "Receipt unavailable."
            : result
              ? "Order status."
              : "Checking your order…"}
        </h1>
      )}

      {!result && !error && (
        <div style={{ marginTop: 24 }}>
          <p role="status" style={{ color: "var(--muted)", fontSize: 14 }}>
            Checking your order…
          </p>
          <div
            className="skeleton"
            style={{ height: 160, marginTop: 16, borderRadius: 8 }}
          />
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
