import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, chatEvents, type Capabilities } from "./api";

type Review = {
  quote_id: string;
  title: string;
  qty: number;
  total: string;
  shipping: string;
  currency: string;
  expires_at: string;
  ship_to_country: string;
};

export function AiBuyer({
  budget,
  country,
  capabilities,
  onTrace,
}: {
  budget: string;
  country: string;
  capabilities: Capabilities | null;
  onTrace?: (line: string) => void;
}) {
  const [session, setSession] = useState("");
  const [message, setMessage] = useState("");
  const [conversation, setConversation] = useState<
    { from: string; text: string }[]
  >([]);
  const [trace, setTrace] = useState<Record<string, unknown>[]>([]);
  const [quote, setQuote] = useState<Review | null>(null);
  const [approval, setApproval] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const current = useRef<AbortController | null>(null);
  useEffect(() => () => current.current?.abort(), []);
  async function send(confirm = false) {
    setBusy(true);
    setError("");
    setApproval("");
    const controller = new AbortController();
    current.current = controller;
    try {
      let buyer = session;
      if (!buyer) {
        if (!/^\d+(\.\d{1,2})?$/.test(budget))
          throw new Error("Enter a budget with at most two decimal places.");
        const created = await api<{ session_id: string }>(
          "/api/playground/sessions",
          { budget_minor: Math.round(Number(budget) * 100), currency: "USD" },
          controller.signal,
        );
        buyer = created.session_id;
        setSession(buyer);
      }
      sessionStorage.setItem("agentshelf-buyer-session", buyer);
      setConversation((items) => [
        ...items,
        {
          from: "You",
          text: confirm ? "I confirm the displayed quote." : message,
        },
      ]);
      const confirmed = confirm ? quote?.quote_id : null;
      if (!confirm) setQuote(null);
      await chatEvents(
        {
          session_id: buyer,
          message: confirm ? "" : message,
          ship_to_country: country,
          confirmed_quote_id: confirmed,
        },
        (event) => {
          if (event.type === "message")
            setConversation((items) => [
              ...items,
              { from: "Agent", text: String(event.text) },
            ]);
          if (event.type === "tool_call" || event.type === "tool_result") {
            setTrace((items) => [...items.slice(-39), event]);
            onTrace?.(
              `${event.type}: ${String(event.name ?? "")} ${JSON.stringify(
                event.arguments ?? event.result ?? {},
              )}`,
            );
          }
          if (event.type === "quote") setQuote(event as unknown as Review);
          if (event.type === "error")
            setError((event.error as { message: string }).message);
          if (event.type === "checkout") {
            const url = new URL(String(event.approval_url));
            if (
              url.protocol !== "https:" ||
              ![
                "www.sandbox.paypal.com",
                "sandbox.paypal.com",
                "www.paypal.com",
                "paypal.com",
              ].includes(url.hostname) ||
              url.username ||
              url.password
            )
              throw new Error(
                "The PayPal approval link could not be verified.",
              );
            setApproval(String(event.approval_url));
            setQuote(null);
          }
        },
        controller.signal,
      );
      setMessage("");
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void send();
  }
  return (
    <section className="buyer-chat" aria-label="AI shopping chat">
      <h2>Shop with your AI agent</h2>
      <p>
        The agent uses the store’s MCP tools. Review the exact quote before
        continuing to PayPal. Keep personal details out of chat.
      </p>
      {!capabilities?.ai_configured && (
        <p className="notice">
          AI chat needs an Anthropic key. The catalog explorer below is
          available now.
        </p>
      )}
      <div aria-live="polite" className="chat-transcript">
        {conversation.map((item, i) => (
          <p key={i}>
            <strong>{item.from}: </strong>
            {item.text}
          </p>
        ))}
      </div>
      <form className="seller-form" onSubmit={submit}>
        <label>
          Your request
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={600}
            required
            placeholder="Find a blue scarf within my budget."
          />
        </label>
        <button
          className="button"
          disabled={busy || !capabilities?.ai_configured}
        >
          {busy ? "Shopping…" : "Ask the agent"}
        </button>
      </form>
      {quote && (
        <div className="quote">
          <h3>
            {quote.title} × {quote.qty}
          </h3>
          <p>
            Total: ${quote.total} {quote.currency}, including ${quote.shipping}{" "}
            shipping to {quote.ship_to_country}.
          </p>
          <p>Expires {new Date(quote.expires_at).toLocaleTimeString()}.</p>
          <button
            className="button"
            disabled={busy || !capabilities?.checkout_configured}
            onClick={() => void send(true)}
          >
            Confirm this quote and create checkout
          </button>
        </div>
      )}
      {approval && (
        <a className="button" href={approval}>
          Approve payment on PayPal
        </a>
      )}
      <p role="alert">{error}</p>
      <details>
        <summary>MCP tool activity ({trace.length})</summary>
        {trace.map((event, i) => (
          <pre key={i}>{JSON.stringify(event, null, 2)}</pre>
        ))}
      </details>
    </section>
  );
}
