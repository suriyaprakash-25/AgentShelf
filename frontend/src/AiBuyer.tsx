import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, chatEvents, type Capabilities } from "./api";
import { Bot, User } from "lucide-react";

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

type Message = { from: "You" | "Agent"; text: string };

const PROMPT_SUGGESTIONS = [
  "Find me a blue scarf within my budget.",
  "What handmade textiles do you have?",
  "Show me something under $40.",
  "I'm looking for a unique gift.",
];

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
  const [conversation, setConversation] = useState<Message[]>([]);
  const [trace, setTrace] = useState<Record<string, unknown>[]>([]);
  const [quote, setQuote] = useState<Review | null>(null);
  const [approval, setApproval] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const current = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => () => current.current?.abort(), []);

  // Auto-scroll to bottom when conversation updates
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation, busy]);

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
      if (textareaRef.current) textareaRef.current.style.height = "auto";
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

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && capabilities?.ai_configured && message.trim()) {
        void send();
      }
    }
  }

  function handleTextareaChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setMessage(e.target.value);
    // Auto-grow
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
  }

  const aiEnabled = Boolean(capabilities?.ai_configured);

  return (
    <section className="buyer-chat" aria-label="AI shopping chat">
      <div className="panel-title" style={{ marginBottom: 12 }}>
        <Bot size={20} />
        <h2 style={{ margin: 0, fontSize: 18 }}>Shop with your AI agent</h2>
      </div>
      <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 12 }}>
        The agent uses the store's MCP tools. Review the exact quote before
        continuing to PayPal.
      </p>

      {/* Privacy notice */}
      <div
        className="notice"
        style={{ marginTop: 0, display: "flex", gap: 8, alignItems: "flex-start" }}
        role="note"
      >
        <span style={{ fontSize: 14 }}>🔒</span>
        <span>Keep personal details out of chat. The agent only receives your budget and shipping country.</span>
      </div>

      {!aiEnabled && (
        <p className="notice" style={{ borderLeft: "3px solid #c5ab6a" }}>
          ⚠️ AI chat needs an Anthropic API key. Explore the catalog below to
          request server-verified quotes directly.
        </p>
      )}

      {/* Chat transcript */}
      <div
        aria-live="polite"
        aria-label="Chat conversation"
        className="chat-transcript"
        style={{ minHeight: conversation.length ? undefined : 0 }}
      >
        {conversation.length === 0 && aiEnabled && (
          <div style={{ padding: "20px 0", color: "var(--muted)" }}>
            <p style={{ fontSize: 12, margin: "0 0 12px" }}>Try asking:</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {PROMPT_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setMessage(s)}
                  style={{
                    fontSize: 11,
                    padding: "6px 12px",
                    border: "1px solid var(--line)",
                    borderRadius: 20,
                    background: "white",
                    color: "var(--green)",
                    cursor: "pointer",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {conversation.map((item, i) => (
          <div
            key={i}
            className={`chat-bubble-wrapper ${item.from === "You" ? "user" : ""}`}
          >
            <div
              className={`chat-avatar ${item.from === "You" ? "user-avatar" : ""}`}
              aria-hidden="true"
            >
              {item.from === "You" ? (
                <User size={12} />
              ) : (
                <Bot size={12} />
              )}
            </div>
            <div
              className={`chat-bubble ${item.from === "You" ? "user" : "agent"}`}
            >
              {item.text}
            </div>
          </div>
        ))}
        {/* Typing indicator */}
        {busy && (
          <div className="typing-indicator" aria-label="Agent is thinking">
            <span /><span /><span />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Chat input */}
      <form onSubmit={submit} style={{ marginTop: 12 }}>
        <label>
          Your request
          <div className="chat-input-row" style={{ marginTop: 6 }}>
            <textarea
              ref={textareaRef}
              value={message}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              maxLength={600}
              required
              placeholder={
                aiEnabled
                  ? "Ask the agent… (Enter to send, Shift+Enter for new line)"
                  : "AI chat is offline — use the catalog filter below."
              }
              disabled={!aiEnabled || busy}
              rows={1}
              style={{ height: 44 }}
            />
            <button
              type="submit"
              className="button chat-send-btn"
              disabled={busy || !aiEnabled || !message.trim()}
            >
              {busy ? "Shopping…" : "Ask the agent"}
            </button>
          </div>
        </label>
      </form>

      {/* Quote card */}
      {quote && (
        <div className="quote" style={{ marginTop: 16 }}>
          <span className="eyebrow">AGENT FOUND A MATCH</span>
          <h3 style={{ marginTop: 8, marginBottom: 4 }}>
            {quote.title} × {quote.qty}
          </h3>
          <p style={{ marginBottom: 4 }}>
            Total: <strong>${quote.total} {quote.currency}</strong>, including
            ${quote.shipping} shipping to {quote.ship_to_country}.
          </p>
          <p style={{ fontSize: 11, color: "var(--muted)" }}>
            Quote expires at {new Date(quote.expires_at).toLocaleTimeString()}.
          </p>
          <button
            className="button"
            disabled={busy || !capabilities?.checkout_configured}
            onClick={() => void send(true)}
            style={{ width: "100%", marginTop: 12 }}
          >
            Confirm this quote and create checkout
          </button>
          {!capabilities?.checkout_configured && (
            <p className="notice" style={{ marginTop: 8, marginBottom: 0 }}>
              Checkout needs PayPal sandbox credentials.
            </p>
          )}
        </div>
      )}

      {/* PayPal approval link */}
      {approval && (
        <a
          className="button"
          href={approval}
          style={{ width: "100%", marginTop: 12, display: "flex" }}
        >
          Approve payment on PayPal
        </a>
      )}

      {/* Error */}
      {error && (
        <p role="alert" className="notice error" style={{ marginTop: 12 }}>
          {error}
        </p>
      )}

      {/* MCP Tool activity */}
      {trace.length > 0 && (
        <details style={{ marginTop: 16 }}>
          <summary
            style={{ fontSize: 12, color: "var(--muted)", cursor: "pointer" }}
          >
            MCP tool activity ({trace.length})
          </summary>
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
            {trace.map((event, i) => (
              <div key={i} className="tool-event">
                <span className="tool-badge">
                  {event.type === "tool_call" ? "→" : "←"}
                </span>
                <span className="tool-name">
                  {String(event.name ?? (event.type === "tool_result" ? "result" : event.type))}
                </span>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
