# ADR-004: Client identity behind proxies, shared quotas and browser headers

Status: ACCEPTED locally (November 9, 2026). Behaviour behind the real hosting proxy
must still be verified on HTTPS staging (DELIVERY_CHECKLIST).

## Problems found

1. The leftmost `X-Forwarded-For` entry was trusted. That entry is client-controlled, so
   every spoofed value minted a fresh quota. This was demonstrated in the evaluation.
2. Uvicorn ran with `--forwarded-allow-ips='*'`.
3. The Playground's MCP traffic comes from the server's own address, so in production
   every buyer would share one 60/min IP bucket.
4. Each quota used three statements and a row lock, and the logic was copied four times.

## Decision

* **Identity** (`rate_limits.client_ip`) is the entry appended by the nearest trusted
  proxy: the `TRUSTED_PROXY_HOPS`-th entry from the right. It defaults to 1 in
  staging/production and 0 locally, where the header is ignored. Uvicorn trusts only
  `FORWARDED_ALLOW_IPS` (default `127.0.0.1`).
* **Signed Playground claim:** the buyer agent sends
  `X-AgentShelf-Playground: <session>.<expiry>.<HMAC-SHA256>` with a 120 s TTL and
  constant-time comparison. Verified MCP traffic is counted per buyer session (120/min,
  itself bounded by 20 chat messages/min). Unsigned callers keep the roadmap's
  60/min per IP. The key is `SERVICE_SIGNING_KEY`, or a purpose-labelled HMAC derivation
  of the shared `DATABASE_URL` secret, so replicas verify each other without new config.
* **One quota primitive:** `rate_limits.consume` is a single atomic
  `INSERT … ON CONFLICT DO UPDATE … RETURNING`. Named `RatePolicy` constants replace
  magic numbers. Raising inside the caller's transaction rolls the count back.
* **Headers:** `Strict-Transport-Security` (deployed only), `Cross-Origin-Opener-Policy`,
  `Permissions-Policy`, and the existing CSP, nosniff and no-referrer.
  `style-src 'unsafe-inline'` remains because React `style` attributes are pervasive.
  Removing it means migrating inline styles to classes; this is tracked, not hidden.
* **Prompt-input hardening:** the translation language must be a bounded language tag,
  which also bounds cache-key cardinality.

## Evidence

| Check | Evidence |
| --- | --- |
| Spoofed leftmost XFF values share one quota | `test_spoofed_forwarded_prefix_cannot_mint_new_quota`: `[202, 202, 202, 429]` |
| Rightmost-hop table, including fewer hops than proxies | `tests/test_rate_limits.py` |
| 40 concurrent attempts admit exactly 10 | `test_concurrent_quota_admits_exactly_the_limit` (real Postgres) |
| Real-socket Playground chat counts against the session bucket, never `127.0.0.1` | `test_agent_uses_real_mcp_and_human_confirmation` |
| Token forgery, expiry stretching and malformed input are rejected | `test_playground_token_round_trip_and_rejections` |
| HSTS only when deployed | `test_deployed_responses_pin_https_and_isolate_the_browsing_context` |
