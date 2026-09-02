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

**PWA assets** (one-off after Wave 13.1; rerun on icon/manifest changes):
```bash
# Manifest, MIME type matters — some browsers reject application/json
AWS_PROFILE=flightmap aws s3 cp manifest.webmanifest \
  s3://london-flight-map-frontend/manifest.webmanifest \
  --content-type "application/manifest+json" --region eu-west-2

# Icons (recursive)
AWS_PROFILE=flightmap aws s3 cp icons/ \
  s3://london-flight-map-frontend/icons/ \
  --recursive --content-type "image/svg+xml" --region eu-west-2

# Service worker — CRITICAL: must be no-cache, otherwise SW updates
# never propagate (CloudFront caches the SW itself, then never refreshes)
AWS_PROFILE=flightmap aws s3 cp sw.js \
  s3://london-flight-map-frontend/sw.js \
  --content-type "application/javascript" \
  --cache-control "no-cache, no-store, must-revalidate" \
  --region eu-west-2

# Privacy policy page (referenced by store listings + native app)
AWS_PROFILE=flightmap aws s3 cp privacy.html \
  s3://london-flight-map-frontend/privacy \
  --content-type "text/html" --region eu-west-2

# Deep-link files — DO NOT deploy until placeholders are replaced with
# real values (Apple Team ID, Android keystore SHA-256). See mobile/DEEP_LINKING.md.
AWS_PROFILE=flightmap aws s3 cp .well-known/apple-app-site-association \
  s3://london-flight-map-frontend/.well-known/apple-app-site-association \
  --content-type "application/json" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp .well-known/assetlinks.json \
  s3://london-flight-map-frontend/.well-known/assetlinks.json \
  --content-type "application/json" --region eu-west-2
```

### DONE one-off: demo key moved onto its own usage plan

**Status 2026-07-29: done and verified from the API, in the same session as the
`sam deploy` that cut the free tier.** Kept here as the runbook for any future
key that CloudFormation does not manage — the same unlink-then-link dance
applies. Not an admin action: `flightmap-dev` holds `apigateway:POST` and
`apigateway:DELETE`, so it ran from this machine.

Live plan ids as deployed: `SkyScoreFreeTier` = `sjtyz8` (10,000 req/month
since 2026-08-21, when batch was denied to free keys and the quota was raised
by the same factor so requests and scores became the same unit),
`SkyScoreDemoTier` = `x88go8` (2,000 req/month).

The free tier was cut sharply on 2026-07-29 and restored to 10,000 on
2026-08-21 (the superseded figure is deliberately not restated - this file is
read by the free-tier drift gate, which cannot tell a quoted historical number
from a live claim). The shared public demo
key (`SkyScoreDemoKeyV2`, id `1zy00lrqs5`, embedded in `score-demo/*.html`) was
linked to `ScoreFreeUsagePlan`, so between the deploy and the relink the public
"Try the API" form shared that 100 across every visitor to the page. The quota
is per *key*, not per plan — the problem was that one key is shared by the whole
internet, not that the plan pools its keys. The deploy created
`ScoreDemoUsagePlan` (2,000/month) but **could not move the key** — the key was
created out-of-band in 2026-05, so CloudFormation does not manage it.

**Unlink before linking.** API Gateway refuses to associate a key with two
usage plans that share the same API stage, and both plans here are on
`FlightMapApi`/`prod`. Doing it the other way round fails at the link step.

```bash
# 1. Get both plan ids
AWS_PROFILE=flightmap aws apigateway get-usage-plans --region eu-west-2 \
  --query "items[?name=='SkyScoreFreeTier'||name=='SkyScoreDemoTier'].[name,id]" \
  --output table

# 2 + 3 in ONE shell invocation, chained on && so nothing can land between them.
AWS_PROFILE=flightmap aws apigateway delete-usage-plan-key --region eu-west-2 \
  --usage-plan-id sjtyz8 --key-id 1zy00lrqs5 && \
AWS_PROFILE=flightmap aws apigateway create-usage-plan-key --region eu-west-2 \
  --usage-plan-id x88go8 --key-id 1zy00lrqs5 --key-type API_KEY
```

Between the two the demo key belongs to no plan and `/v1/score` will reject it
— seconds, but do not stop halfway, and do not run this while demoing to
anyone. Chain them in a single shell command rather than running them as two
separate steps, so a pause between them is impossible.

**Verify from the API, not the console** — two structural checks and one
functional one. Structure: the demo key appears under `SkyScoreDemoTier` and is
absent from `SkyScoreFreeTier`.

```bash
AWS_PROFILE=flightmap aws apigateway get-usage-plan-keys --region eu-west-2 \
  --usage-plan-id x88go8 --query 'items[].[id,name]' --output table
AWS_PROFILE=flightmap aws apigateway get-usage-plan-keys --region eu-west-2 \
  --usage-plan-id sjtyz8 --query 'items[].[id,name]' --output table
```

Function: score something with the embedded key and expect 200. **`/v1/score`
is a GET with query params**, not a POST with a JSON body — a POST returns
`403 {"message":"Missing Authentication Token"}`, which is API Gateway's
unmatched-route error and reads exactly like a rejected key. Do not diagnose a
relink from it.

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  "https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score?postcode=SW1A%201AA&persona=balanced" \
  -H "X-Api-Key: <demo key from score-demo/index.html>"
```

**Native iOS / Android binaries** (Wave 13.2+):
- Web changes propagate to native apps **only** when a Codemagic build is triggered + reviewed by Apple/Google. Plan binary releases every 2-4 weeks.
- Full pre-release runbook: `mobile/RELEASE_CHECKLIST.md` (9 steps including version bump, asset regen, smoke test, store promotion).
- Codemagic auto-publishes to TestFlight (iOS) + Play Console internal track (Android); manual promotion to public release via the respective consoles.

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

### 3.7 — Migrate CI from static keys to GitHub OIDC — **OPEN, prepared 2026-08-04**

**Status:** the outstanding security remediation from audit finding A-0803-12.
`SECURITY.md` once claimed CI already used OIDC; it does not. Both deploy
workflows authenticate with `secrets.AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY`, which are long-lived credentials sitting in GitHub.

**Do the AWS side FIRST. Do not edit the workflows before the role exists** —
they would fail on the next `workflow_dispatch` with an opaque credentials
error. Both are manual-dispatch only, so nothing breaks on a push, but a
broken deploy path discovered mid-incident is the worst time to find out.

**Step 1 — create the OIDC identity provider** (IAM → Identity providers →
Add provider → OpenID Connect):

- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

One provider serves every repo in the account; skip if it already exists.

**Step 2 — create the role.** Name it `flightmap-github-deploy`. Trust policy,
scoped to this repo *and* the `production` environment so a fork or an
unrelated branch cannot assume it:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::072674217857:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:billkhiz-bit/london-flight-path-map:environment:production"
      }
    }
  }]
}
```

**The `sub` condition is the whole security value.** With `StringLike` and a
`*`, any branch or PR from a fork can assume the role. Use `StringEquals`
against the exact `environment:production` subject, matching the `environment:
production` already declared in both workflow files.

**Step 3 — attach permissions.** Simplest correct move is to attach the same
`FlightMapDeployPolicy` the user carries today, so the migration changes *how*
CI authenticates without changing *what* it can do. Tightening the policy is a
separate change and should not ride along with this one.

**Step 4 — edit both workflows** (`.github/workflows/deploy-frontend.yml` and
`deploy-backend.yml`). Add the `permissions` block at job level and swap the
credential inputs:

```yaml
    permissions:
      id-token: write     # required to mint the OIDC token
      contents: read      # default is dropped once permissions is declared
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::072674217857:role/flightmap-github-deploy
          aws-region: eu-west-2
```

Delete the `aws-access-key-id` and `aws-secret-access-key` lines. **`contents:
read` is not optional** — declaring `permissions` at all replaces the default
set, so omitting it breaks `actions/checkout`.

**Step 5 — verify before deleting anything.** Dispatch *Deploy Frontend*
manually and confirm it succeeds. Only then delete the `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` repository secrets and deactivate the access key in
IAM.

**Rollback:** the access key stays valid until explicitly deactivated, so
reverting the two workflow files restores the previous path. This is why
Step 5 deletes the secrets last rather than first.

**Verification the migration actually landed:**

```bash
grep -rn "AWS_SECRET_ACCESS_KEY\|role-to-assume" .github/workflows/
```

Expected afterwards: `role-to-assume` in both files, `AWS_SECRET_ACCESS_KEY`
in neither. `SECURITY.md`'s CI bullet must be updated in the same commit —
that bullet describing a state that did not exist is what the finding was.

---

## 4. Disaster Recovery

| Scenario | RTO | RPO | Procedure |
|---|---|---|---|
| Lambda code breaks | <5 min | 0 | `git revert` last commit, re-deploy backend |
| Frontend regression | <2 min | 0 | `git checkout HEAD~1 index.html`, S3 cp + invalidate |
| DDB row corruption | <30 min | <5 min | PITR restore to point-in-time (after Section 3.1 enabled) |
| Stack drift / accidental delete | <1 hour | 0 | `sam deploy` from current `master` re-creates everything **except the DynamoDB tables, which are now `Retain`** — see below |
| Failed update wedges the stack | see note | 0 | **Mitigated 2026-07-26.** `flightmap-dev` has no `dynamodb:DeleteTable` and no `cloudformation:ContinueUpdateRollback`, so a rollback needing to delete a table would be denied and strand the stack in `UPDATE_ROLLBACK_FAILED` with no self-recovery. All four tables now carry `DeletionPolicy: Retain` + `UpdateReplacePolicy: Retain`, so CFN never attempts the delete |
| AWS region outage | manual | unknown | No multi-region failover; eu-west-2 is single point |
| Secret leaked | <30 min | n/a | Rotate per **Section 3.6 (Token Rotation)**. Note the deploy user cannot read CloudWatch or CloudTrail, so misuse auditing must be done from the console |

**The four DynamoDB tables and how recoverable each is:**

| Table | Contents | Recoverable? |
|---|---|---|
| `london-flight-map-signups` | Customer signup audit log + API keyIds | **PITR/backup only** — irreplaceable, these are real customers |
| `london-flight-map-favourites` | User-saved properties, keyed to device tokens | **PITR/backup only** — device tokens cannot be reissued |
| `london-flight-map-noise-raster` | 423,481 DEFRA Lden samples | Rebuildable from the source GeoTIFF, ~6 hours |
| `london-flight-map-postcodes` | ~2.7M ONS NSPL rows | Rebuildable from `data/nspl.csv`. **5.80 h measured** on the per-item path; since 2026-07-27 the loader uses `BatchWriteItem` and should be far faster — **but only once `dynamodb:BatchWriteItem` is applied to the live `flightmap-dev` policy** (it is in `backend/iam-policy.json`, not yet applied). It falls back automatically, so **a ~6 h run means the grant never landed**. Next full load is unmeasured; do not quote a figure until one produces it. |

All four are `Retain`, so a stack-level failure will not destroy them. That
protects the two irreplaceable tables and saves ~13 hours of reload on the
other two.

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

**Alarms, created 2026-09-02 (CLI, `flightmap-dev`):**

| Alarm | Metric | Fires when |
|---|---|---|
| `london-flight-map-lambda-errors` | `AWS/Lambda` `Errors`, Sum, no dimension | any error across all 8 functions, >0 in 5 min |
| `london-flight-map-lambda-duration` | `AWS/Lambda` `Duration`, Maximum | >25 s, i.e. approaching the **29 s API Gateway integration cap**, before requests start 504-ing |
| `london-flight-map-api-5xx` | `AWS/ApiGateway` `5XXError`, Sum, `ApiName=london-flight-map` | any 5xx, >0 in 5 min |

All three notify **`arn:aws:sns:eu-west-2:072674217857:sky-score-alerts`** (email
to Bill) on BOTH `ALARM` and `OK`, and all three use
`--treat-missing-data notBreaching` so a quiet API does not page anyone.

**The `london-flight-map-` prefix is load-bearing.** The `FlightMapObservability`
policy scopes `PutMetricAlarm` / `DeleteAlarms` / `SetAlarmState` to
`alarm:london-flight-map-*`, deliberately EXCLUDING the `sky-score-*` billing
alarms - so a leaked deploy key cannot delete the controls that notice a runaway
spend. **A new alarm named anything else cannot be managed by the deploy user.**

**THE PATH IS TESTED, NOT ASSUMED.** Forced to `ALARM` with `set-alarm-state` and
back to `OK`; both emails delivered. Re-test after any change to the topic or its
subscription:

```
export MSYS_NO_PATHCONV=1
AWS_PROFILE=flightmap aws cloudwatch set-alarm-state --region eu-west-2   --alarm-name london-flight-map-lambda-errors --state-value ALARM   --state-reason "path test, not a real fault"
# ...then set it back to OK
```

**Why testing it was not optional.** The subscription sat at
`PendingConfirmation` for its first hour, and EVERY surface said the setup
worked: the topic existed, all three alarms pointed at it, and `Publish message`
returned a MessageId and a green success banner. SNS accepts publishes to a topic
with zero confirmed subscribers, because that is a legal state. The only field
that disagreed was the subscription ARN, which literally reads
`PendingConfirmation` instead of an ARN, on a tab nobody visits. **Alerting is
the one system where no-error and working are furthest apart** - confirm the
subscription and force a transition, or the alarms are decorative.

**Gaps (deferred, see `AUDIT_REPORT.md`):**
- No centralised dashboard.
- No latency / error-rate SLO tracking.
- No external uptime checker (`status.skyscore.co.uk` subdomain
  recommended; not yet provisioned).
- ~~No DLQ on async Lambdas (audit item I6).~~ **Closed 2026-07-24 as moot** —
  all 7 Lambdas are APIGW-synchronous, so there is no async invocation for a
  DLQ to catch.
- ~~**No log read for the deploy user** (added 2026-07-26).~~ **NOT TRUE as of
  2026-09-02** — re-measured against a real log group and proven by reading
  production output. `/aws-debug` works. The old entry had been recording a
  stale log-group NAME as a permissions wall; see Section 6.
- ~~**No metrics or alarms for the deploy user**~~ **CLOSED 2026-09-02.** The
  `FlightMapObservability` managed policy is created and attached to
  `flightmap-dev`; CloudWatch metrics, alarms and `lambda:ListFunctions` all
  work, and the three alarms above exist. Kept as a SEPARATE managed policy
  rather than merged into `FlightMapDeployPolicy`: AWS unions permissions across
  attached policies, so a mistake here cannot break deploys, and it detaches
  cleanly. **`apigateway:GET` is still denied** - read API dimension values from
  `cloudwatch list-metrics` instead, which is the authoritative source anyway.

---

## 6. Common Debugging Recipes

> **✅ CORRECTED 2026-09-02 — `flightmap-dev` CAN read logs, and could not on
> 2026-07-26.** Re-measured against a REAL log group and proven by reading
> production output: `logs:FilterLogEvents`, `logs:GetLogEvents` and
> `logs:DescribeLogStreams` are **ALLOWED**. **`/aws-debug` works**; steps 1-3
> below are runnable as written.
>
> **Why the old claim survived, and the trap to avoid repeating.** The probe
> that "verified" the denial used the log-group name written down in
> `CLAUDE.md` — `.../ScoreFunction-LuxoNSLxJMva`. **A Lambda's log-group suffix
> changes whenever CloudFormation REPLACES the function rather than updating
> it**, and that name no longer exists; the live one is
> `.../ScoreFunction-AQH1Sxwg3LaF`. Querying a non-existent group returns
> `ResourceNotFoundException`, and a probe that treats any non-zero exit as
> "denied" records it as a permissions wall. **Resolve the name from
> `describe-log-groups` first; never hardcode a log-group suffix.**
>
> **What IS still denied** (re-measured the same day, distinguishing
> `AccessDenied` from every other error): `cloudwatch:DescribeAlarms`,
> `cloudwatch:ListMetrics` / `GetMetricData`, and `lambda:ListFunctions`. So
> logs are readable but **metrics and alarms are not** — the `Observability`
> statement in `backend/iam-policy.json` covers exactly these and needs
> applying in the console.
>
> The general lesson this repo already records for the log-retention work
> applies here too: **re-measure a recorded blocker before working around it.**
> This one cost the product a documented "we cannot support customers" gap that
> had stopped being true.
>
> Git Bash also mangles the leading slash in `/aws/lambda/...` arguments;
> prefix any such command with `export MSYS_NO_PATHCONV=1` or it fails with a
> misleading regex-validation error.

**API returning 5xx unexpectedly:**
1. Console → CloudWatch Logs for the Lambda (region eu-west-2). From the CLI
   you can at least resolve the log-group name:
   `export MSYS_NO_PATHCONV=1; AWS_PROFILE=flightmap aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/london-flight-map" --region eu-west-2`
2. **When logs are unavailable, diagnose by side-effect elimination instead.**
   Identify the state a handler commits *between* its external calls, then
   query that state to bracket where it stopped. This is how the 2026-07-26
   signup `AccessDenied` was located without a single log line: a failed
   signup left no API key and no orphaned key, which places the denial before
   key creation and rules out the downstream call entirely.

**API returning 403 unexpectedly:**
- Per-route APIGW throttle. Current declared values (`template.yaml`
  `MethodSettings`, updated 2026-07-26): stage-wide `*/*` **50 RPS / 100
  burst**, `GET /v1/score` **40/80**, `POST /v1/score/batch` **10/20**,
  `POST /v1/signup` **1/5**, `GET /epc` **3/6**. A burst test will trip these.
  Read the live values with
  `aws apigateway get-stage --rest-api-id 2gjfdzg20c --stage-name prod --query 'methodSettings'`
  — and note that `MethodSettings` is **last-wins** on duplicates, so never
  add a second declaration above an old one.
- Missing/expired API key on `/v1/score*` paths.

**CORS errors in browser:**
- `Globals.Function.Environment.CORS_ORIGIN` is `'*'` since 2026-07-24 (audit
  A-0724-C1: it had been pinned to the legacy CloudFront URL, silently
  breaking all five consumer data panels on skyscore.co.uk for ~2 months).
- `signup` is the exception and keeps its own stricter in-code allow-list in
  `_origin_for_request`; `score` overrides to `'*'`. Check the specific
  Lambda before assuming which rule applies.

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

## Log-group retention is NOT declared in the template (found 2026-08-21)

A Lambda log group is created by AWS on the function's FIRST INVOCATION, with
no retention policy. `privacy.html` promises 30 days and
`scripts/check_log_retention.sh` is a blocking gate, so the sequence is:

1. deploy a function, or redeploy one whose group had been cleaned up
2. invoke it once - even a smoke test counts
3. the next preflight goes RED on that group

That happened on 2026-08-21: verifying the new consumer signup path by calling
the live endpoint created `/aws/lambda/london-flight-map-SignupFunction-vLApmPCZyQTD`
and the gate caught it immediately, which is the gate working.

Manual fix (flightmap-dev DOES hold `logs:PutRetentionPolicy`, unlike the
delete permissions it lacks):

```bash
export MSYS_NO_PATHCONV=1   # or Git Bash mangles the /aws/lambda path
AWS_PROFILE=flightmap aws logs put-retention-policy \
  --log-group-name "/aws/lambda/<function-log-group>" \
  --retention-in-days 30 --region eu-west-2
```

**Audited 2026-08-21:** the account holds **8 log groups, one per live Lambda,
every one at 30-day retention, and zero orphans**. The 6 orphaned groups recorded
in `CLAUDE.md` and `DRAFT_security_retention_passage.md` - including the signup
one said to hold raw emails from June and July - no longer exist. Re-measure a
recorded blocker before planning work around it.

To re-audit:

```bash
export MSYS_NO_PATHCONV=1
AWS_PROFILE=flightmap aws logs describe-log-groups --region eu-west-2   --query 'logGroups[].[logGroupName,retentionInDays]' --output text
```

Any row whose second column is `None` needs the command above.

**Durable fix, not yet done:** declare each group as an `AWS::Logs::LogGroup`
with `RetentionInDays: 30` in `backend/template.yaml`. Deliberately not done
blind - CloudFormation refuses to CREATE a log group that already exists, so
the existing groups would need importing into the stack first. Worth doing on a
session where the stack can be watched, not as a side effect of another change.
