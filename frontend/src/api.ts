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
export async function api<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(base + path, {
    signal,
    credentials: "include",
    ...(body !== undefined
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
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
