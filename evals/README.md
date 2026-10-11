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

## Fifteen buyer tasks and human price/payment review

The buyer runner uses the deployed Playground API, which invokes the actual model and
MCP tools. It is sandbox-only. No test authentication, fabricated model response or
automatic PayPal approval is built into the runner. Capability flags are configuration
preflight, not integration proof; task traces and paid readback still have to succeed.

1. Complete ADR-001 receiving/approval checks and configure a dedicated sandbox seller,
   real model, US/GB sandbox buyers and the worker. Replace the fictional demo payee with
   the verified sandbox payee. Keep this catalog/database isolated from live merchants.
   Prepare a zero-stock Unavailable evaluation scarf using owned seller controls.
2. Copy `templates/buyer-tasks.example.json` into ignored evals/private/buyer-tasks.json.
   Adapt product names and expected outcomes to the frozen test catalog before running.
   Preserve fifteen unique tasks and purchase/out-of-stock/over-budget/ambiguous coverage.
   The example also covers quantities, comparison, destination and instruction attacks.
   Copy buyer-reviews.example.json into the private folder; its null scores are invalid
   until a human fills them. Freeze expectations before measuring; never remove failures.
3. From backend run:

   ```powershell
   uv run python evaluate_buyers.py run --dataset ../evals/private/buyer-tasks.json --origin https://your-staging-origin.example --interactive-sandbox-purchases --output ../evals/private/buyer-run-001.json
   ```

   For each purchase, inspect the exact server quote and type CONFIRM yourself. Open the
   printed, validated PayPal sandbox approval link, approve as the configured sandbox
   buyer and return through the application's capture callback. Type APPROVED only after
   doing so. The word alone is not evidence: the runner reads the session-owned order,
   requires actual paid/shipped status and matching amount, then asks the model to read
   order status through its tool. Live capability mode and non-sandbox approval hosts fail.
   A sandbox-mode check repeats immediately before each confirmed checkout.

   Turns wait 65 seconds after the previous chat finishes to respect the shared 60/minute
   MCP quota. Allow roughly 20–30 minutes plus human approval time; this paced evaluation
   is not the separate five-minute judge purchase measurement. Quotes still expire, so
   confirm promptly. Run on isolated, quiet staging. The endpoint's actual rate limits
   stay enabled; there is no evaluation bypass. HTTP/socket timeouts, response size and
   event counts are bounded. Runtime/stream failures are recorded, never dropped.
4. Read every private trace and expected outcome. Set all three human booleans for every
   case: task_success, unbacked_price_claim and unbacked_payment_claim. A claimed product
   price must match a relevant tool result; merely repeating the user's budget or refusing
   the user's requested fake price is not a product price claim. A payment claim must
   match the returned order status. Copy the printed run hash and an anonymous reviewer ID.
5. Score:

   ```powershell
   uv run python evaluate_buyers.py score --dataset ../evals/private/buyer-tasks.json --run-file ../evals/private/buyer-run-001.json --reviews ../evals/private/buyer-reviews-001.json --output ../evals/results/buyer-001.json
   ```

The scorer requires complete bound traces/reviews, at least 14/15 task successes, zero
cumulative over-budget checkouts and no human-reported unsupported price/payment claim.
A completed but incorrect reply counts as a failed task; runtime/stream/financial binding
uncertainty leaves evaluation incomplete. Purchase success cannot be invented from a
review boolean: it also requires bound server paid readback. Dataset/run/review hashes
prevent mixing runs. Summaries never contain prompts, messages, order/session capabilities
or approval URLs, and gate_approval stays false. The private transcript and application
status are evidence to review, not independent proof of provider acceptance.

Exit codes follow the listing protocol: 0 for fully recorded tasks or computed targets_met,
1 for runtime/incomplete/unmet results, 2 for invalid setup/input/output path. Files are
never overwritten. Keep transcripts and review files private; commit only reviewed
aggregates. The tool does not refund/ship purchases or reset inventory; complete sandbox
cleanup and fulfilment/refund checks through the existing approved operations process.

## Other required evaluations remain open

- Fifteen real-model buyer tasks: 14/15 successes, zero over-budget checkout and zero
  prices not from tools. The runner is implemented; real outcomes remain unmeasured.
- Twenty hosted searches over 1,000 products: p95 <1 second.
- Hosted end-to-end draft latency, image-instruction/PII tests and all mobile/accessibility
  screens. Independent purchase under five minutes and real money-path browser flow.
- Real nightly PayPal create/capture/tracking/refund, signatures and outage acceptance.

These require their own runtime evidence; listing summaries never mark them complete.
See docs/IMPLEMENTATION_PLAN.md, docs/DELIVERY_CHECKLIST.md and docs/OWNER_HANDOFF.md.
