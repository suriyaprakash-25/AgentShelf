# AgentShelf delivery plan and working checklist

Started October 10, 2026. This expands the completion audit into implementation
work; the supplied roadmap and its review gates remain authoritative.
Check an implementation box only after focused tests pass. Staging acceptance and
live release require their own evidence even after code is implemented.

## 1. Foundations and provider feasibility — Sprint 0

- [x] Preserve source guide, implementation plan and full 113-checkbox audit.
- [x] Database/MCP/quote foundation with recorded local tests.
- [ ] Configure PayPal sandbox accounts and record every ADR-001 experiment.
- [ ] Configure Anthropic, run five-photo spike and select measured model.
- [ ] Configure Meta test recipients and verify actual staging echo.
- [ ] Establish funded HTTPS staging, real CI and required AG Studio licence.

## 2. Walking skeleton — Gate 1

- [x] Secure email magic links and server-side seller sessions (local/provider-mock evidence).
- [x] Web onboarding with consent and isolated merchant eligibility (local browser fixture).
- [ ] WhatsApp onboarding to public store/MCP URLs.
- [ ] Real MCP buyer agent, budget-bound session and human quote confirmation.
- [ ] Real sandbox approval/capture, signed webhook and complete audit trail.
- [ ] Gate 1 review evidence, tag and reviewer signoff.

## 3. Complete all Must workflows

- [x] Seller-owned draft/create/price/stock/archive, confirmation and paginated lists (local evidence).
- [ ] AG Studio product/order dashboard, filters/sorting and CSV export.
- [ ] Durable processed media, listing drafts, price confirmation and YES publication.
- [ ] WhatsApp image/listing/edit commands and paid notifications.
- [ ] Tracking command/API pushed to PayPal with ownership checks.
  Local dashboard/API implementation is tested with controlled provider responses;
  WhatsApp command and real sandbox tracker acceptance remain open.
- [ ] Streaming Playground with MCP tool results and server-controlled checkout approval.
- [ ] Safe reservation expiry and uncertain-payment reconciliation.
- [ ] Full partial-refund/reversal/dispute handling with visible operational states.

## 4. Production checks — Gate 2

- [ ] Shared prescribed quotas, CSRF, all seller ownership and prompt/log privacy tests.
- [ ] Minimize stored webhook PII and prove buyer-address storage policy.
- [ ] Admin failures/retry UI, order correlation, Sentry and external alerting.
- [ ] Real backup/restore, safe sandbox demo-reset and clean-machine startup.
- [ ] Complete red-team suite, 20 real products, 15 buyer tasks and latency evidence.
- [ ] 1,000-product search benchmark, Lighthouse performance/accessibility and all layouts.
- [ ] Full money-path browser coverage and resolve Windows Chrome teardown.
- [ ] All M1–M12 and 14 stories pass on staging; Gate 2 review/signoff.

## 5. Release, submission and live pilot — Gate 3

- [ ] Should items only after Gate 2, in guide order.
- [ ] Final README, judge credentials, verified public links and runbook drills.
- [ ] Real demo video, team evaluations, Devpost draft and Gate 3 review/signoff.
- [ ] Separately verified live merchant account, permissions, policies and isolation.
- [ ] Funded operations through judging; merchant-approved controlled live transaction.
- [ ] User/team performs submission and independent link verification.

External credentials belong in ignored local env files or managed deployment secrets.
No secrets are requested in chat. Missing credentials do not prevent code work;
they do prevent claiming provider acceptance or live readiness.
