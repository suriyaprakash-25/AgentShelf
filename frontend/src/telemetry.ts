import type { ErrorEvent, EventHint } from "@sentry/browser";

const messages = new Set([
  "agentshelf:UI_RENDER_FAILURE",
  "agentshelf:BROWSER_RUNTIME_ERROR",
  "agentshelf:BROWSER_UNHANDLED_REJECTION",
]);
type ErrorCode =
  "UI_RENDER_FAILURE" | "BROWSER_RUNTIME_ERROR" | "BROWSER_UNHANDLED_REJECTION";
const pending = new Set<ErrorCode>();
const lastSent = new Map<ErrorCode, number>();
let capture: ((message: string) => void) | null = null;
let disabled = false;
let sent = 0;
let started = false;
let monitoringEnvironment = "local";

// Replace the event rather than attempting to redact arbitrary customer strings.
export function scrubBrowserEvent(
  event: ErrorEvent,
  hint: EventHint,
): ErrorEvent | null {
  hint.attachments = [];
  if (typeof event.message !== "string" || !messages.has(event.message))
    return null;
  return {
    type: undefined,
    event_id: /^[a-f0-9]{32}$/i.test(event.event_id || "")
      ? event.event_id
      : undefined,
    timestamp:
      typeof event.timestamp === "number" && Number.isFinite(event.timestamp)
        ? event.timestamp
        : undefined,
    level: "error",
    message: event.message,
    platform: "javascript",
    environment: monitoringEnvironment,
  };
}

export function reportBrowserError(code: ErrorCode) {
  if (!messages.has(`agentshelf:${code}`) || disabled || sent >= 10) return;
  if (!capture) {
    pending.add(code);
    return;
  }
  const now = Date.now();
  const previous = lastSent.get(code);
  if (previous !== undefined && now - previous < 60000) return;
  lastSent.set(code, now);
  sent++;
  try {
    capture(`agentshelf:${code}`);
  } catch {
    // Monitoring must never break the storefront or its recovery screen.
  }
}

export async function setupBrowserMonitoring() {
  if (started) return;
  started = true;
  // Never inspect the ErrorEvent, rejection reason or React component stack.
  window.addEventListener("error", () =>
    reportBrowserError("BROWSER_RUNTIME_ERROR"),
  );
  window.addEventListener("unhandledrejection", () =>
    reportBrowserError("BROWSER_UNHANDLED_REJECTION"),
  );
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 3000);
  try {
    const response = await fetch("/api/monitoring-config", {
      credentials: "omit",
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error("Monitoring configuration unavailable");
    const config = (await response.json()) as {
      dsn: string | null;
      environment: string;
    };
    if (!config.dsn) {
      disabled = true;
      pending.clear();
      return;
    }
    if (
      !["local", "test", "staging", "production"].includes(config.environment)
    )
      throw new Error("Invalid monitoring environment");
    monitoringEnvironment = config.environment;
    const sdk = await import("@sentry/browser");
    sdk.init({
      dsn: config.dsn,
      environment: config.environment,
      defaultIntegrations: false,
      dataCollection: {
        userInfo: false,
        cookies: false,
        httpHeaders: false,
        httpBodies: [],
        urlQueryParams: false,
        stackFrameVariables: false,
        frameContextLines: 0,
        databaseQueryData: false,
        queues: false,
        graphQL: { document: false, variables: false },
        genAI: { inputs: false, outputs: false },
      },
      tracesSampleRate: 0,
      maxBreadcrumbs: 0,
      sendClientReports: false,
      beforeSend: scrubBrowserEvent,
    });
    capture = (message) => {
      sdk.captureMessage(message, "error");
    };
    for (const code of pending) reportBrowserError(code);
    pending.clear();
  } catch {
    disabled = true;
    pending.clear();
  } finally {
    window.clearTimeout(timeout);
  }
}
