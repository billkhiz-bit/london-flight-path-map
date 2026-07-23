# Support & Status

How to reach Sky Score and where to check service health.

---

## Getting in touch

| Reason | Where to send it |
|---|---|
| Security vulnerability disclosure | `support@skyscore.co.uk` (also listed in `/.well-known/security.txt`) |
| API support, billing, account issues | `support@skyscore.co.uk` |
| GDPR data-subject access request (SAR) | `support@skyscore.co.uk` with subject line beginning `[GDPR SAR]` |
| Bug report (non-security) | GitHub issue at <https://github.com/billkhiz-bit/london-flight-path-map/issues> |
| Press / partnership / pilots | `support@skyscore.co.uk` |

`support@skyscore.co.uk` has been live since 2026-05-21 (Cloudflare Email
Routing on the `skyscore.co.uk` zone; see `EMAIL_SETUP.md`).

Response targets (best-effort, single-founder operation):

- Security: acknowledged within 24 hours, triaged within 72 hours.
- API support: same business day during UK working hours, next business
  day otherwise.
- SAR: within 30 days as required by UK GDPR Art. 12(3).

---

## Service status

The live status page is at <https://skyscore.co.uk/score-demo/status.html>
(endpoint-by-endpoint probes, browser-side). Additional checks:

1. The consumer site itself — `https://skyscore.co.uk`. If the home page
   is up, CloudFront and S3 are healthy.
2. The API liveness probe — `curl https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/regions`
   should return a small JSON list of supported regions.
3. AWS health dashboard for `eu-west-2` (London) — that's the only region
   we run in. <https://health.aws.amazon.com/health/status>

---

## Planned (Wave 9 deferred)

- ~~**`support@skyscore.co.uk` mailbox.**~~ **Done 2026-05-21** via
  Cloudflare Email Routing (`support@`, `info@`, `bilalkhizar@` all
  forward; outbound "Send mail as" configured in Gmail). See
  `EMAIL_SETUP.md` for the full setup + DKIM caveat.
- **`status.skyscore.co.uk` subdomain.** Recommended stack: a free
  StatusGator / Better Stack page CNAMEd to `status.skyscore.co.uk`. The
  page would surface (a) home-page check (b) `/v1/regions` API probe
  (c) AWS eu-west-2 region status. ~30 min one-time setup.

Both are tracked in `AUDIT_REPORT.md` under Wave-9 deferred items.

---

## Change history

| Date | Change |
|---|---|
| 2026-07-23 | Contact addresses switched to `support@skyscore.co.uk` (live since 2026-05-21); status-page pointer updated to `/score-demo/status.html`. |
| 2026-05-07 | Initial SUPPORT.md created as part of Wave 9 enterprise readiness. |
