# Operations Runbook — Sky Score

Operational procedures for running, monitoring, recovering, and debugging the
production Sky Score stack. Audience: future-you, an SRE-shaped reviewer
during enterprise due-diligence, anyone covering for the founder.

Companion to:
- `SECURITY.md` — security posture, incident response, GDPR / SAR procedure
- `AUDIT_REPORT.md` — open audit items + triage
- `LICENSING.md` — data sources + sub-processors
- `AWS_BILLING_ALARM_SETUP.md` — one-time billing-alarm setup runbook
- `backend/template.yaml` — SAM/CloudFormation source of truth

---

## 1. Production Topology

| Layer | Resource | Region |
|---|---|---|
| CDN | CloudFront `EGSSPJKLFL33M` | global |
| Static origin | S3 `london-flight-map-frontend` | eu-west-2 |
| API edge | API Gateway `2gjfdzg20c` | eu-west-2 |
| Compute | 7 Lambdas (`score`, `signup`, `favourites`, `epc`, `sold_prices`, `transport`, `nhs`) | eu-west-2 |
| State | 3 DynamoDB tables (signups, noise-raster, favourites), all on-demand | eu-west-2 |
| Secrets | `EPC_BEARER_TOKEN` via SAM `NoEcho` parameter; `.env` locally | local + CFN |
| Custom domain | `skyscore.co.uk` → CloudFront | DNS at registrar |

API Gateway endpoint: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
CloudFront URL: `https://d1oe4ftwutjpf.cloudfront.net` (canonical: `https://skyscore.co.uk`)

---

## 2. Routine Deploys

**Frontend** (single HTML page):
```bash
AWS_PROFILE=flightmap aws s3 cp index.html \
  s3://london-flight-map-frontend/index.html \
  --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation \
  --distribution-id EGSSPJKLFL33M --paths '/*'
```

**Backend** (Lambdas + APIGW + DDB):
```bash
set -a && source ../.env && set +a
cd backend && rm -rf .aws-sam
AWS_PROFILE=flightmap sam build
AWS_PROFILE=flightmap sam deploy \
  --stack-name london-flight-map \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --region eu-west-2 \
  --no-confirm-changeset \
  --parameter-overrides EpcBearerToken="$EPC_BEARER_TOKEN"
```

Always `rm -rf .aws-sam` first — stale build dirs will silently deploy old
code if a Lambda's `requirements.txt` hasn't changed but the source has.

**Pre-flight before deploy**: `/preflight` (linting, security scan, tests).
Blocking: ESLint errors, html-validate errors, failing pytest.

---

## 3. One-Time Admin Actions (require root / IAM admin)

These cannot be performed by `flightmap-dev` because they touch IAM, billing,
or backup configuration that the deploy user is intentionally locked out of.

### 3.1 — Enable DynamoDB Point-in-Time Recovery (PITR) — **DONE 2026-05-08**

**Status:** ENABLED on all three tables (`london-flight-map-favourites`,
`london-flight-map-signups`, `london-flight-map-noise-raster`) via the
Wave 12.10 deploy after `dynamodb:UpdateContinuousBackups` +
`DescribeContinuousBackups` were granted to `flightmap-dev` via inline
policy `flightmap-dev-pitr-grant`. The first attempt on 2026-05-07 rolled
back because the IAM grant hadn't landed; the May-8 attempt succeeded
once the policy was in place.

**Why:** 35-day continuous backups for the three production tables. Cost is
rounding-error money for the table sizes we run; recovery posture is
meaningfully better.

**If PITR ever needs re-enabling on a future table** (e.g. a new
DynamoDB resource added to `template.yaml`), the IAM grant covers all
`london-flight-map-*` tables via wildcard, so no further admin action is
required as long as the new table follows the naming convention.

**Verification:**
```bash
AWS_PROFILE=flightmap aws dynamodb describe-continuous-backups \
  --table-name london-flight-map-signups --region eu-west-2
```
Look for `"PointInTimeRecoveryStatus": "ENABLED"`.

### 3.2 — CloudFront Response-Headers Policy (HSTS + Permissions-Policy)

**Why:** `Strict-Transport-Security` and `Permissions-Policy` cannot be set
via `<meta>` tags — browsers ignore them when not delivered as real HTTP
headers. CloudFront's "response-headers policy" feature adds them at the
edge without changing origin S3 objects.

**Steps:**

1. CloudFront console → Policies → Response headers policies → Create.
2. Name: `SkyScoreSecurityHeaders`.
3. Strict-Transport-Security: `max-age=63072000; includeSubDomains; preload`
   (2 years, the value that gets you eligible for the
   [HSTS preload list](https://hstspreload.org/)).
4. X-Content-Type-Options: `nosniff` (also already in `<meta>` — belt &
   braces; the header version takes precedence).
5. Referrer-Policy: `strict-origin-when-cross-origin`.
6. Custom header — Permissions-Policy:
   `geolocation=(), microphone=(), camera=(), payment=(), usb=(), interest-cohort=()`
   (we use none of these — explicit deny stops third-party libraries from
   silently asking for them).
7. Attach the policy to the `EGSSPJKLFL33M` distribution's default cache
   behaviour. CloudFront will invalidate and serve new headers within
   ~5 minutes.

**Verification:**
```bash
curl -sI https://skyscore.co.uk | grep -iE 'strict-transport|permissions-policy|referrer|content-type-options'
```

If you ever want to apply for HSTS preload: only do that *after* the
header has been live for 6+ months without issue and you're certain
every subdomain (incl. future `status.skyscore.co.uk`, `api.skyscore.co.uk`)
will always be HTTPS-only.

### 3.3 — CSP Report-URI Endpoint

**Why:** Today CSP is enforcing across all 5 HTML pages but violations
log only to the user's browser DevTools console — invisible to us.
Adding a `report-uri` directive routes violation reports to a collector.

**Cheapest path:** [report-uri.com](https://report-uri.com) free tier
(10k reports/month, sufficient for our scale). Sign up, copy the unique
endpoint URL, then update CSP on each HTML page:

```html
<meta http-equiv="Content-Security-Policy" content="…existing rules…; report-uri https://YOUR-ID.report-uri.com/r/d/csp/enforce;">
```

Each of the 5 HTML files needs the same `report-uri` token added. Re-deploy
to S3 + invalidate. Reports start flowing within minutes.

**Alternative path:** A tiny Lambda + API Gateway endpoint that accepts
the JSON POST and dumps it to CloudWatch Logs. ~30 min build, but adds
a moving piece to maintain.

### 3.4 — Billing Alarm

See `AWS_BILLING_ALARM_SETUP.md` (must be created in `us-east-1`, requires
billing-data alarm permissions).

### 3.5 — Refresh DEFRA Aircraft Noise PNG (every ~5 years)

**Why:** The aircraft-noise overlay on the consumer map is served from
`/data/aircraft-noise-london-lden.png`, a one-shot capture of DEFRA's
WMS render at the bbox covering LHR + LCY + LGW. We self-host because
DEFRA's GeoServer takes ~8-9 seconds to render this size of request.

DEFRA publishes new strategic noise maps approximately every 5 years
under the EU Environmental Noise Directive (UK still complies post-Brexit):

| Round | Data year | WMS layer suffix | Status |
|---|---|---|---|
| Round 3 | 2017 | `…round-3` | Superseded |
| Round 4 | 2022 | `…round-4` | **Current** (used today) |
| Round 5 | 2027 (expected) | `…round-5` | Future |

**Steps when Round 5 lands:**

1. Update the WMS URL in `index.html` (`DEFRA_WMS.aircraft.all.url`) and
   in `scripts/refresh_aircraft_noise.sh` (`WMS_URL` const) to point at
   the new round's endpoint.
2. Run `bash scripts/refresh_aircraft_noise.sh`. This fetches the PNG
   at the bbox/resolution that match `LONDON_AIRCRAFT_BBOX` +
   `AIRCRAFT_RASTER_PX` in `index.html`.
3. Visually inspect `data/aircraft-noise-london-lden.png` in any image
   viewer to confirm the contours haven't suddenly shifted (LHR moved,
   new airport added, etc.).
4. Deploy + invalidate (the script prints the exact commands).
5. Commit the new PNG + reference the round version in the commit message.
6. Update `METHODOLOGY.md` §11 with the new data year.

### 3.6 — Token Rotation

When `EPC_BEARER_TOKEN` has touched a chat log / scrollback / unencrypted
storage:

1. Regenerate at <https://get-energy-performance-data.communities.gov.uk>
   (My account page).
2. Update local `.env`.
3. Re-run the backend deploy in Section 2.

Old tokens are not explicitly revoked by the rotation — MHCLG's UI just
issues a new one and silently expires the old one.

---

## 4. Disaster Recovery

| Scenario | RTO | RPO | Procedure |
|---|---|---|---|
| Lambda code breaks | <5 min | 0 | `git revert` last commit, re-deploy backend |
| Frontend regression | <2 min | 0 | `git checkout HEAD~1 index.html`, S3 cp + invalidate |
| DDB row corruption | <30 min | <5 min | PITR restore to point-in-time (after Section 3.1 enabled) |
| Stack drift / accidental delete | <1 hour | 0 | `sam deploy` from current `master` re-creates everything |
| AWS region outage | manual | unknown | No multi-region failover; eu-west-2 is single point |
| Secret leaked | <30 min | n/a | Rotate per Section 3.3, audit CloudWatch for misuse |

The DDB tables hold (a) signup audit log and (b) DEFRA noise samples and
(c) user favourites. (b) is reproducible from the source GeoTIFF in ~6 hours;
(a) and (c) are only recoverable from PITR or backup.

---

## 5. Monitoring & Alarming

**What's instrumented today:**
- CloudWatch Logs on every Lambda (default retention).
- `[SIGNUP_ORPHAN_KEY]` structured log prefix on signup race rollback.
  Recommended metric filter:
  ```
  filter @message like /\[SIGNUP_ORPHAN_KEY\]/
  ```
  Alarm: `> 0` over 1 hour.
- API Gateway access logs disabled (cost reasons); enable via the APIGW
  console if investigating an abuse case.
- Billing alarm: see `AWS_BILLING_ALARM_SETUP.md`.

**Gaps (deferred, see `AUDIT_REPORT.md`):**
- No centralised dashboard.
- No latency / error-rate SLO tracking.
- No external uptime checker (`status.skyscore.co.uk` subdomain
  recommended; not yet provisioned).
- No DLQ on async Lambdas (audit item I6).

---

## 6. Common Debugging Recipes

**API returning 5xx unexpectedly:**
1. CloudWatch Logs for the Lambda (region eu-west-2).
2. `AWS_PROFILE=flightmap aws logs tail /aws/lambda/<FunctionName> --follow --region eu-west-2`
3. Run `/aws-debug` skill for project-specific Lambda + APIGW recipes.

**API returning 403 unexpectedly:**
- Per-route APIGW throttle — `score` is 5 RPS / 10 burst, `signup` is
  1 RPS / 5 burst. A burst test will trip these.
- Missing/expired API key on `/v1/score*` paths.

**CORS errors in browser:**
- Verify origin is on the allow-list in the relevant Lambda's
  `_origin_for_request` (`signup/app.py`, `score/app.py`).
- Wildcards are deliberately not used; allow-list lives in code.

**CloudFront serving stale content:**
- Always invalidate after S3 upload: `--paths '/*'`.
- TTL on the distribution is set to default; explicit invalidation is the
  contract.

---

## 7. Cost Profile (steady-state)

Approximate monthly cost at near-zero traffic, all on AWS hackathon credits
through April 2027:

| Resource | Cost |
|---|---|
| Lambda (on-demand, 7 fns) | <$0.10 |
| API Gateway | <$0.10 |
| DynamoDB on-demand (3 tables, tiny) | <$0.25 |
| S3 (single 300 KB index.html, ~5 GB raster GeoTIFF as data only locally) | ~$0.05 |
| CloudFront (low-egress) | <$0.50 |
| **Total** | **<$1/month at zero traffic** |

Billing alarm is set at $20 USD as a tripwire.

---

## 8. Change History

This file tracks the meta-rules; routine changes go in `CHANGELOG.md`.

| Date | Change |
|---|---|
| 2026-05-07 | Initial OPERATIONS.md created as part of Wave 9 enterprise readiness. PITR documented as one-time admin action pending IAM policy update. |
