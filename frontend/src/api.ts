export type Product = {
  product_id: string;
  store_name: string;
  title: string;
  description: string;
  price: string;
  currency: string;
  in_stock: boolean;
  image_url: string | null;
  product_url: string;
};
export type Store = {
  next_cursor: string | null;
  name: string;
  slug: string;
  country: string;
  currency: string;
  mcp_url: string;
  products: Product[];
};
export type Capabilities = {
  paypal_mode: string;
  checkout_configured: boolean;
  ai_configured: boolean;
  whatsapp_configured: boolean;
  seller_login_configured: boolean;
  live_checkout_enabled: boolean;
  supported_currencies: string[];
  shipping_destinations: string[];
};
export type Quote = {
  quote_id: string;
  item_total: string;
  shipping: string;
  total: string;
  currency: string;
  expires_at: string;
};

const base = import.meta.env.VITE_API_URL || "";
export function mediaUrl(path: string) {
  return base + path;
}
export async function chatEvents(
  body: unknown,
  receive: (event: Record<string, unknown>) => void,
  signal: AbortSignal,
) {
  const response = await fetch(base + "/api/playground/chat", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.error?.message || "Chat is unavailable.");
  }
  if (!response.body)
    throw new Error("Streaming is unavailable in this browser.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      let end: number;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice(6))
          .join("\n");
        if (data) receive(JSON.parse(data));
      }
      if (chunk.done) break;
    }
  } finally {
    reader.releaseLock();
  }
}
export async function uploadPhoto(
  file: File,
  csrf: string,
): Promise<{ id: string }> {
  const response = await fetch(base + "/api/me/media", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": file.type, "X-CSRF-Token": csrf },
    body: file,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error?.message || "Photo upload failed.");
  return data;
}
export async function api<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
  options?: { method?: string; csrf?: string },
): Promise<T> {
  const response = await fetch(base + path, {
    signal,
    credentials: "include",
    ...(body !== undefined
      ? {
          method: options?.method || "POST",
          headers: {
            "Content-Type": "application/json",
            ...(options?.csrf ? { "X-CSRF-Token": options.csrf } : {}),
          },
          body: JSON.stringify(body),
        }
      : {}),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.error?.message || "The service is unavailable. Please try again.",
    );
  return data as T;
}
