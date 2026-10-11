# Roadmap evaluation tools

No product-quality or real-provider evaluation has been completed. Unit fixtures are
synthetic protocol tests, never results to submit. Gate approval is always separate.

## Listing quality and local draft-call benchmark

Collect the roadmap's **20 real team-photographed products**: five jewellery, five
textiles, five crafts and five prints. Label category and observed attributes before
running the model. Use de-identified photos with no buyer/address/credential content;
preprocessing strips metadata but does not remove text visible in a photograph.
Finish the roadmap's five-photo provider/model spike before the full evaluation.

1. Copy `templates/listing-dataset.example.json` to ignored
   `evals/private/dataset.json`. Put photographs below the same private directory.
   Replace every empty images list with one to four relative filenames, enter verified
   captions/attributes and retain the 20 distinct IDs and category balance. Empty
   placeholders are intentionally invalid. The tool does not invent products/photos.
2. Configure actual Anthropic access and the selected model in the ignored root `.env`.
   Run from `backend`:

   ```powershell
   uv run --env-file ../.env python evaluate_listings.py run --dataset ../evals/private/dataset.json --output ../evals/private/run-001.json
   ```

   This invokes the application's actual image preprocessing, caption guard and listing
   provider/schema pipeline. All images/captions are preflighted before a model call.
   Missing credentials fail explicitly. Individual failures are recorded for every case
   and cannot be excluded from scoring. Each product includes one to four images;
   repeated processed images are rejected. Nothing is published or priced for sale.
3. Copy `templates/listing-reviews.example.json` into the private directory. Set
   run_sha256 to the hash printed by the runner and reviewer_id to an anonymous team
   identifier. A human reviews all 20 originals, hand labels and drafts. Fill every
   rating with an integer 1–5 and invented_claim with an explicit boolean. Check brands,
   certifications, materials, provenance and every unsupported claim. Null placeholders
   never count as a passing review. Do not use a model as the human rater.
4. Score from `backend`:

   ```powershell
   uv run python evaluate_listings.py score --dataset ../evals/private/dataset.json --run-file ../evals/private/run-001.json --reviews ../evals/private/reviews-001.json --output ../evals/results/listing-001.json
   ```

The summary requires 18/20 correct categories, average human rating >=4/5, zero
invented claims and local draft-call p95 <20 seconds. Nearest-rank p95 uses the 19th
of 20 sorted observations, compares the unrounded value and includes schema/provider
retries. It excludes hosted queue/storage/upload time. Measure the separate hosted
photo-to-draft workflow for staging latency acceptance; this benchmark cannot prove it.
Ground-truth changes, missing/duplicate records, provider failures or unbound reviews
produce incomplete. Complete results below a target produce targets_not_met.

Exit 0 means recorded successful drafts or computed targets_met, exit 1 means failed
cases/incomplete/unmet targets, exit 2 means invalid input/provider setup/output path.
Previous artifacts are never overwritten. Use a new numbered filename for each run.
Private artifacts contain untrusted model text and photographs; keep them in ignored
evals/private. Only reviewed aggregate summaries belong in evals/results. Summaries
contain hashes, anonymous reviewer ID and metrics, never captions, photo paths or draft
text. Preserve private source evidence securely for independent review. A file's source
declaration and human scores are owner-supplied evidence, not independent verification.

## Other required evaluations remain open

- Fifteen real-model buyer tasks: 14/15 successes, zero over-budget checkout and zero
  prices not from tools. Include out-of-stock, ambiguous and adversarial requests.
- Twenty hosted searches over 1,000 products: p95 <1 second.
- Hosted end-to-end draft latency, image-instruction/PII tests and all mobile/accessibility
  screens. Independent purchase under five minutes and real money-path browser flow.
- Real nightly PayPal create/capture/tracking/refund, signatures and outage acceptance.

These require their own runtime evidence; listing summaries never mark them complete.
See docs/IMPLEMENTATION_PLAN.md, docs/DELIVERY_CHECKLIST.md and docs/OWNER_HANDOFF.md.
