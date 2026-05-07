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

### 3.1 — Enable DynamoDB Point-in-Time Recovery (PITR)

**Why:** 35-day continuous backups for the three production tables. Cost is
rounding-error money for the table sizes we run; recovery posture is
meaningfully better.

**Steps:**

1. Sign in to the AWS console as the root account (or an IAM admin with
   `iam:PutUserPolicy` on `flightmap-dev`).
2. Update the `FlightMapDeployPolicy` (attached to user `flightmap-dev`) so
   the `DynamoDB` statement includes:
   - `dynamodb:UpdateContinuousBackups`
   - `dynamodb:DescribeContinuousBackups`
   - `dynamodb:UpdateTable`
   The full updated policy lives in `backend/iam-policy.json`. Copy/paste
   that file's `DynamoDB` Sid block over the existing one.
3. Re-run the standard backend deploy (Section 2). The next CloudFormation
   changeset will enable PITR on `london-flight-map-signups`,
   `london-flight-map-noise-raster`, and `london-flight-map-favourites`.

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

### 3.5 — Token Rotation

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
