import { useEffect, useState, type FormEvent } from "react";
import { api, mediaUrl, uploadPhoto } from "./api";

type Listing = {
  id: string;
  status: "queued" | "drafted" | "failed" | "published";
  media_urls: string[];
  draft: {
    title: string;
    description: string;
    suggested_price_minor: number;
    price_rationale: string;
    questions: string[];
  } | null;
};

export function ListingStudio({
  csrf,
  refresh,
}: {
  csrf: string;
  refresh: () => Promise<void>;
}) {
  const [selected, setSelected] = useState("");
  const [listing, setListing] = useState<Listing | null>(null);
  const [history, setHistory] = useState<{ id: string; status: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<{ items: typeof history }>(
      "/api/me/listings",
      undefined,
      controller.signal,
    )
      .then((data) => setHistory(data.items))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const data = await api<Listing>(
          `/api/me/listings/${selected}`,
          undefined,
          controller.signal,
        );
        setListing(data);
        if (data.status === "queued")
          timer = setTimeout(() => void poll(), 2000);
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [selected]);
  async function draft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const files = data.getAll("photos") as File[];
      if (
        files.length < 1 ||
        files.length > 4 ||
        files.some((f) => !f.size || f.size > 5 * 1024 * 1024)
      )
        throw new Error("Choose one to four product photos, each up to 5 MB.");
      const ids: string[] = [];
      for (const file of files) ids.push((await uploadPhoto(file, csrf)).id);
      const result = await api<{ id: string }>(
        "/api/me/listings",
        { media_ids: ids, caption: data.get("caption") },
        undefined,
        { csrf },
      );
      setListing(null);
      setSelected(result.id);
      setHistory((items) => [{ id: result.id, status: "queued" }, ...items]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!listing) return;
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await api(
        `/api/me/listings/${listing.id}/publish`,
        {
          confirm: data.get("confirm") === "on",
          title: data.get("title"),
          description: data.get("description"),
          price_minor: Math.round(Number(data.get("price")) * 100),
          stock: Number(data.get("stock")),
        },
        undefined,
        { csrf },
      );
      setListing({ ...listing, status: "published" });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel" aria-label="Photo listing studio">
      <h2>Turn product photos into a draft</h2>
      <p>
        Use product-only photos without people, addresses or contact details.
        You review the description and set the final selling price.
      </p>
      <form className="seller-form" onSubmit={draft}>
        <label>
          Product photos (one to four)
          <input
            type="file"
            name="photos"
            accept="image/jpeg,image/png,image/webp"
            multiple
            required
          />
        </label>
        <label>
          Product notes
          <textarea
            name="caption"
            maxLength={600}
            placeholder="Size, colour and condition. Leave personal details out."
          />
        </label>
        <button className="button" disabled={busy}>
          {busy ? "Working…" : "Generate a draft"}
        </button>
      </form>
      {history.length > 0 && (
        <label>
          Review a recent draft
          <select
            value={selected}
            onChange={(e) => {
              setListing(null);
              setSelected(e.target.value);
              setError("");
            }}
          >
            <option value="">Choose a draft</option>
            {history.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id.slice(0, 8)} · {item.status}
              </option>
            ))}
          </select>
        </label>
      )}
      {listing?.status === "queued" && (
        <p role="status">
          Your draft is queued. You can return to review it later.
        </p>
      )}
      {listing?.status === "failed" && (
        <p role="status">
          The draft could not be generated. Use the manual product form below.
        </p>
      )}
      {listing?.status === "published" && (
        <p role="status">
          Published. Your product is now in your public store.
        </p>
      )}
      {listing?.status === "drafted" && listing.draft && (
        <form key={listing.id} className="seller-form" onSubmit={publish}>
          <div className="listing-photos">
            {listing.media_urls.map((url) => (
              <img
                key={url}
                src={mediaUrl(url)}
                alt="Uploaded product photo"
                width="160"
                height="160"
              />
            ))}
          </div>
          <label>
            Title
            <input
              name="title"
              defaultValue={listing.draft.title}
              maxLength={80}
              required
            />
          </label>
          <label>
            Description
            <textarea
              name="description"
              defaultValue={listing.draft.description}
              maxLength={600}
              required
            />
          </label>
          <p>
            Suggested price: $
            {(listing.draft.suggested_price_minor / 100).toFixed(2)} USD.{" "}
            {listing.draft.price_rationale}
          </p>
          {listing.draft.questions?.map((q) => (
            <p key={q}>{q}</p>
          ))}
          <label>
            Your selling price in USD
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
          <label className="consent-label">
            <input type="checkbox" name="confirm" required />I reviewed these
            details and confirm my price and stock.
          </label>
          <button className="button" disabled={busy}>
            Confirm and publish listing
          </button>
        </form>
      )}
      <p role="alert">{error}</p>
    </section>
  );
}
