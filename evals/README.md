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

## Twenty-search MCP latency evaluation

`backend/evaluate_search.py` measures actual `search_products` calls through the MCP
SDK and deployed HTTP transport. It makes no model calls, checkout or catalog writes.
Before and after timing it enumerates `/api/products` with normal cursor pagination:
at least 1,000 searchable products, at most 10,000, no duplicates or cursor loops.
Complete public-record hashes must match across both snapshots. This detects changes
visible at those snapshots; isolate the catalog from writes during the run. It is not
a transactional snapshot and cannot prove that a product never changed temporarily.

1. Seed an isolated evaluation database with at least 1,000 eligible live, in-stock
   products owned by consenting active sellers. Apply migrations, including the GIN
   full-text index. Verify the index and query plan separately using database access;
   the public evaluator cannot prove index installation or use.
2. Copy `templates/search-tasks.example.json` to ignored `private/search-tasks.json`.
   Fill all twenty cases with queries and the exact ordered expected product UUIDs
   (1–10 per case) from the frozen seeded manifest. Use at least five distinct queries,
   covering representative selective and broad searches. Empty placeholders are invalid.
   Establish expected matches independently of the timed run, rather than accepting
   whatever the endpoint happens to return. This protocol measures successful searches;
   separate correctness tests cover empty results and invalid inputs.
3. From `backend`, run against quiet HTTPS staging:

   ```powershell
   uv run python evaluate_search.py --origin https://YOUR-STAGING-HOST --dataset ../evals/private/search-tasks.json --output ../evals/results/search-001.json
   ```

   Explicit `--allow-loopback` permits local HTTP for engineering verification. Origins
   cannot contain credentials, paths, queries or fragments. Catalog HTTP redirects are
   disabled. Catalog scans have a two-minute deadline checked between requests, each
   HTTP request a ten-second socket timeout. Each tool call is bounded to ten seconds;
   the MCP lifecycle to four minutes.
   Twenty calls stay within the existing quota on an otherwise quiet endpoint. Rate
   limits remain enabled; a failure leaves evaluation incomplete, with no success report.
4. Review the report and retain dataset/catalog hashes with deployment and index evidence.
   The nearest-rank p95 is the nineteenth sorted sample and must be strictly below 1 s.
   Timing includes the MCP tool request, transport and database work, excludes initial
   MCP connection setup, catalog enumeration and local correctness validation. No warmup
   searches are discarded. SDK response caching is explicitly disabled so repeated
   queries still reach the endpoint. Reports contain durations, hashes and counts, no product
   records, queries or endpoint URL. Existing files cannot be overwritten. Exit codes:
   0 target met, 1 measured target unmet, 2 invalid/incomplete run.

`gate_approval` and `postgres_index_verified` remain false. A local result does not establish
hosted latency, concurrent load capacity, real-provider acceptance or a roadmap gate.

## Other required evaluations remain open

The normal development and packaged browser suites now include axe-core WCAG 2.1
A/AA scans with no excluded elements or disabled rules. Public screens are scanned at
375 px: home, seeded store, playground, onboarding, signed-out dashboard/operations,
receipt recovery and not-found. Controlled populated seller grids/fulfilment forms and
operator screens are scanned at 1,280 and 375 px; controlled quote confirmation and
listing review are also scanned. An independent keyboard check activates the skip link
and verifies that main content receives focus. These controlled responses exist only in
Playwright, not in production authentication or provider adapters.

Reports retain both violations and incomplete checks under frontend/test-results;
CI retains packaged accessibility reports for seven days, including successful scans.
Review incomplete results manually. Zero automated violations is not full WCAG
conformance, a Lighthouse score, screen-reader acceptance or proof that every state of
every screen is accessible. Actual licensed Studio/provider/payment states and real
content still require hosted and human checks. Use the roadmap's separate Lighthouse
score >=90, 375 px layout and keyboard/screen-reader requirements as acceptance gates.
Playwright's [accessibility guidance](https://playwright.dev/docs/accessibility-testing)
also explains why automated scans require manual assessment.

- Fifteen real-model buyer tasks: 14/15 successes, zero over-budget checkout and zero
  prices not from tools. The runner is implemented; real outcomes remain unmeasured.
- Twenty hosted searches over 1,000 products: p95 <1 second.
- Hosted end-to-end draft latency, image-instruction/PII tests and all mobile/accessibility
  screens. Independent purchase under five minutes and real money-path browser flow.
- Real nightly PayPal create/capture/tracking/refund, signatures and outage acceptance.

These require their own runtime evidence; listing summaries never mark them complete.
See docs/IMPLEMENTATION_PLAN.md, docs/DELIVERY_CHECKLIST.md and docs/OWNER_HANDOFF.md.
