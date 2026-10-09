# ADR-001: PayPal merchant payee feasibility

Status: PROPOSED; sandbox spike not executed, no credentials available.

The source guide requires this evidence before approving the checkout architecture.
Official PayPal documentation describes setting `purchase_units[].payee`, but that
is not proof of capture, tracking, event delivery, refunds or India account behavior.

| Check | Status | Evidence |
| --- | --- | --- |
| Capture to another seller using platform app | Not run | Needs sandbox app/seller/buyer |
| Tracking using platform credentials | Not run | Needs captured order |
| Capture webhook reaches platform app and verifies | Not run | Needs public HTTPS webhook |
| Refund permissions | Not run | Needs captured order |
| India sandbox seller receives USD | Not run | Needs India sandbox account |

The code currently implements the candidate direct-payee path. It is experimental
until these checks pass. Platform/Payouts fallback is not implemented or approved.
Live pilot must use the verified merchant's own account/app; independent live merchants
require a separate onboarding/permission design. Never infer live support from sandbox.

Reference: https://developer.paypal.com/v5/checkout/pay-another-account
