import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, mediaUrl, uploadPhoto } from "./api";
import { Upload, X, ImagePlus } from "lucide-react";

type Listing = {
  id: string;
  created_at?: string;
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
  const [history, setHistory] = useState<{ id: string; status: string; created_at?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [previewFiles, setPreviewFiles] = useState<{ file: File; preview: string }[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  // Cleanup preview URLs on unmount
  useEffect(() => {
    return () => {
      previewFiles.forEach((p) => URL.revokeObjectURL(p.preview));
    };
  }, [previewFiles]);

  function addFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    const valid = arr.filter(
      (f) =>
        f.size > 0 &&
        f.size <= 5 * 1024 * 1024 &&
        ["image/jpeg", "image/png", "image/webp"].includes(f.type),
    );
    const combined = [...previewFiles, ...valid.map((file) => ({ file, preview: URL.createObjectURL(file) }))].slice(0, 4);
    setPreviewFiles(combined);
  }

  function removePreview(index: number) {
    URL.revokeObjectURL(previewFiles[index].preview);
    setPreviewFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }

  function handleFileInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) addFiles(e.target.files);
    e.target.value = "";
  }

  function clearDraft() {
    setListing(null);
    setSelected("");
    setPreviewFiles([]);
    setError("");
    setUploadProgress(0);
  }

  async function draft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setUploadProgress(0);
    const data = new FormData(event.currentTarget);
    try {
      const files = previewFiles.map((p) => p.file);
      if (files.length < 1 || files.length > 4)
        throw new Error("Choose one to four product photos, each up to 5 MB.");

      const ids: string[] = [];
      for (let i = 0; i < files.length; i++) {
        ids.push((await uploadPhoto(files[i], csrf)).id);
        setUploadProgress(Math.round(((i + 1) / files.length) * 100));
      }
      const result = await api<{ id: string }>(
        "/api/me/listings",
        { media_ids: ids, caption: data.get("caption") },
        undefined,
        { csrf },
      );
      setListing(null);
      setSelected(result.id);
      setHistory((items) => [{ id: result.id, status: "queued" }, ...items]);
      setPreviewFiles([]);
      setUploadProgress(0);
      // Reset form
      (event.target as HTMLFormElement).reset();
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

  function formatHistoryLabel(item: { id: string; status: string; created_at?: string }): string {
    const date = item.created_at
      ? new Date(item.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })
      : item.id.slice(0, 8);
    const statusLabel =
      item.status === "queued"
        ? "⏳ Processing"
        : item.status === "drafted"
          ? "✏️ Draft ready"
          : item.status === "published"
            ? "✓ Published"
            : "⚠️ Failed";
    return `${date} · ${statusLabel}`;
  }

  return (
    <section className="panel" aria-label="Photo listing studio">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div>
          <h2 style={{ marginTop: 0, marginBottom: 6 }}>Turn photos into a listing</h2>
          <p style={{ fontSize: 12, color: "var(--muted)", margin: 0, lineHeight: 1.6 }}>
            Upload product photos — AI drafts the title, description and a
            suggested price. You review everything before publishing.
          </p>
        </div>
        {(selected || listing) && (
          <button
            type="button"
            className="text-link"
            onClick={clearDraft}
            style={{ flexShrink: 0, fontSize: 12 }}
          >
            ↺ Start fresh
          </button>
        )}
      </div>

      {/* Upload form */}
      {!listing && (
        <form className="seller-form" onSubmit={draft} style={{ marginTop: 16 }}>
          {/* Drag-and-drop upload zone */}
          <div
            className={`upload-zone ${dragging ? "dragging" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="upload-zone-icon">
              {previewFiles.length > 0 ? (
                <ImagePlus size={28} />
              ) : (
                <Upload size={28} />
              )}
            </div>
            <h4>
              {previewFiles.length > 0
                ? `${previewFiles.length} photo${previewFiles.length > 1 ? "s" : ""} selected`
                : "Drop photos here or click to browse"}
            </h4>
            <p>JPEG, PNG or WebP · Up to 4 photos · Max 5 MB each</p>
            <label style={{ display: "none" }}>
              Product photos (one to four)
              <input
                ref={fileInputRef}
                type="file"
                name="photos"
                aria-label="Product photos (one to four)"
                accept="image/jpeg,image/png,image/webp"
                multiple
                onChange={handleFileInputChange}
              />
            </label>
          </div>

          {/* Photo previews */}
          {previewFiles.length > 0 && (
            <div className="upload-preview-grid">
              {previewFiles.map((p, i) => (
                <div key={i} className="upload-preview-item">
                  <img src={p.preview} alt={`Preview ${i + 1}`} />
                  <button
                    type="button"
                    className="upload-preview-remove"
                    onClick={(e) => { e.stopPropagation(); removePreview(i); }}
                    aria-label={`Remove photo ${i + 1}`}
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Upload progress */}
          {busy && uploadProgress > 0 && uploadProgress < 100 && (
            <div>
              <div className="upload-progress">
                <div className="upload-progress-bar" style={{ width: `${uploadProgress}%` }} />
              </div>
              <span style={{ fontSize: 11, color: "var(--muted)" }}>
                Uploading… {uploadProgress}%
              </span>
            </div>
          )}

          {/* Product notes */}
          <label>
            Product notes (optional)
            <textarea
              name="caption"
              maxLength={600}
              placeholder="Size, colour, condition — anything that helps the AI write a better listing. Leave out personal details."
            />
          </label>

          <button
            className="button"
            disabled={busy || previewFiles.length === 0}
            style={{ marginTop: 4 }}
          >
            {busy ? "Working…" : "Generate a draft"}
          </button>
        </form>
      )}

      {/* Draft history select */}
      {history.length > 0 && !listing && (
        <label style={{ marginTop: 16, display: "grid", gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 600 }}>Review a recent draft</span>
          <select
            value={selected}
            onChange={(e) => {
              setListing(null);
              setSelected(e.target.value);
              setError("");
            }}
          >
            <option value="">Choose a draft…</option>
            {history.map((item) => (
              <option key={item.id} value={item.id}>
                {formatHistoryLabel(item)}
              </option>
            ))}
          </select>
        </label>
      )}

      {/* Status messages */}
      {listing?.status === "queued" && (
        <div className="notice" role="status">
          <strong>⏳ AI is generating your draft…</strong>
          <p style={{ margin: "4px 0 0", fontSize: 11 }}>
            This usually takes 15–30 seconds. You can leave and come back — your draft will be waiting.
          </p>
        </div>
      )}
      {listing?.status === "failed" && (
        <div className="notice error" role="status">
          <strong>⚠️ Draft could not be generated.</strong>
          <p style={{ margin: "4px 0 0", fontSize: 11 }}>
            Try uploading clearer product-only photos. You can also create a
            product manually using the form below.
          </p>
        </div>
      )}
      {listing?.status === "published" && (
        <div
          className="notice success"
          role="status"
          style={{ display: "flex", alignItems: "flex-start", gap: 10 }}
        >
          <span style={{ fontSize: 18 }}>✓</span>
          <div>
            <strong>Published!</strong>
            <p style={{ margin: "2px 0 0", fontSize: 11 }}>
              Your product is now live in your public store.
            </p>
          </div>
        </div>
      )}

      {/* Draft review & publish form */}
      {listing?.status === "drafted" && listing.draft && (
        <form key={listing.id} className="seller-form" onSubmit={publish} style={{ marginTop: 20 }}>
          {/* Photo review */}
          {listing.media_urls.length > 0 && (
            <div>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 8 }}>
                Your photos
              </span>
              <div className="listing-photos">
                {listing.media_urls.map((url) => (
                  <img
                    key={url}
                    src={mediaUrl(url)}
                    alt="Uploaded product photo"
                    width="120"
                    height="120"
                    style={{ objectFit: "cover", borderRadius: 8, border: "1px solid var(--line)" }}
                  />
                ))}
              </div>
            </div>
          )}

          {/* AI-generated suggested price notice */}
          <div className="notice" style={{ marginBottom: 8 }}>
            <strong>Suggested price:</strong> $
            {(listing.draft.suggested_price_minor / 100).toFixed(2)} USD
            {listing.draft.price_rationale && (
              <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--muted)" }}>
                {listing.draft.price_rationale}
              </p>
            )}
          </div>

          {/* AI questions as callout cards */}
          {listing.draft.questions?.length > 0 && (
            <div>
              <span style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6, color: "var(--muted)" }}>
                AI has some questions — consider them when editing:
              </span>
              {listing.draft.questions.map((q) => (
                <div key={q} className="ai-question">
                  💡 {q}
                </div>
              ))}
            </div>
          )}

          <label>
            Listing title
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
          <label>
            Your selling price in USD
            <div className="input-prefix-wrapper">
              <span className="input-prefix">$</span>
              <input
                name="price"
                type="number"
                min="0.01"
                max="1000000"
                step="0.01"
                required
                defaultValue={(listing.draft.suggested_price_minor / 100).toFixed(2)}
              />
            </div>
          </label>
          <label>
            Available stock
            <input
              name="stock"
              type="number"
              min="0"
              max="1000000"
              step="1"
              defaultValue="1"
              required
            />
          </label>
          <label className="consent-label seller-form">
            <input type="checkbox" name="confirm" required />
            I reviewed these details and confirm my price and stock.
          </label>
          <button className="button" disabled={busy}>
            {busy ? "Publishing…" : "Confirm and publish listing"}
          </button>
        </form>
      )}

      {error && (
        <p role="alert" className="notice error" style={{ marginTop: 12 }}>
          {error}
        </p>
      )}
    </section>
  );
}
