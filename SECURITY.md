# Sky Score, security one-pager

A pre-emptive answer to the "are you SOC 2 / ISO 27001" question that almost every B2B procurement team asks. **Sky Score does not yet hold a third-party security attestation** (SOC 2 Type I/II, ISO 27001, Cyber Essentials Plus). Those are 6-12 month exercises with substantial fixed cost, sized for serving a customer base that justifies them. Sky Score is pre-revenue; the attestation track will start once the first paying enterprise customer specifically requires it.

In the meantime, this document lists the controls that **are** in place today and the procedures that handle the questions a security questionnaire would raise. It is updated alongside the codebase; the canonical source is the linked AUDIT_REPORT.md, LICENSING.md, and METHODOLOGY.md.

**Last reviewed:** 2026-08-03 (previously stamped 2026-05-07 while the content had moved on three months)

---

## Reporting a vulnerability

If you've found a security issue (XSS, IDOR, IAM gap, secret leak, abuse vector, anything you'd want to disclose privately), reach out at **`support@skyscore.co.uk`** - the same address published in [`/.well-known/security.txt`](https://skyscore.co.uk/.well-known/security.txt) under RFC 9116. (This page named a personal Gmail until 2026-08-03, so the two disclosure routes gave different addresses; a reporter checking both had no way to know they reached the same inbox.) See also the contact in [`/.well-known/security.txt`](https://skyscore.co.uk/.well-known/security.txt) (RFC 9116 format).

Sole-developer, independent project. Reply timeline best-effort but typically within a working day for things that look real.

---

## Controls in place

### Scope of this document

Sky Score has three deployment surfaces sharing one codebase: web (skyscore.co.uk), PWA (browser-installable), and native iOS / Android (Capacitor wrap, Codemagic-built, App Store + Play Store distribution). The controls below apply to all three unless flagged otherwise. The native wrap adds two surfaces with their own security stories: the `capacitor://` (iOS) / `https://localhost` (Android) WebView origin is locked down by the same CSP as the web origin; the Codemagic build pipeline accesses source code only (no user data). Full sub-processor list including Apple App Store + Google Play in [`SUBPROCESSORS.md`](./SUBPROCESSORS.md).

### Access control + least-privilege

- **Per-Lambda IAM policies** (no shared catch-all role). Each Lambda gets only the permissions it needs; the SAM template at [`backend/template.yaml`](./backend/template.yaml) enumerates them inline.
- **Tag-condition scoped IAM** on the signup Lambda's `apigateway:DELETE` and `apigateway:GET` for `/apikeys/*` — keys are tagged `CreatedBy=SignupLambda` at creation time (with a matching `aws:RequestTag` condition on POST) and only deletable by the same Lambda that created them. Audit ID: N-Code-1.
- **MFA required** on the AWS account root and admin IAM user (account-level setting; not in code).
- **No AWS access keys in source or git history.** Verified by `git log --all -S` across the
  full history for both `AKIA` and the EPC token: zero hits. `.env` and `backend/samconfig.toml`
  are gitignored and have never been committed.
- **CI uses long-lived static access keys, not OIDC** (corrected 2026-08-03; this section
  previously claimed "CI / deploy uses GitHub OIDC where applicable" and that `flightmap-dev`
  had "read-only operational scope" — all three clauses were untrue). `.github/workflows/`
  authenticates via `aws-actions/configure-aws-credentials@v4` with
  `aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}`; there is no `id-token` permission or
  `role-to-assume` anywhere in the repo. **Migrating to OIDC is the outstanding remediation.**
  **Prepared 2026-08-04:** the full procedure is now `OPERATIONS.md` §3.7 — identity provider,
  role trust policy scoped with `StringEquals` on
  `repo:billkhiz-bit/london-flight-path-map:environment:production`, the workflow diff,
  verification and rollback. **Not performed:** it needs IAM write, which `flightmap-dev` is
  deliberately denied, so it is a console action. The workflows are intentionally left on static
  keys until the role exists, because flipping them first breaks the next manual deploy. This
  bullet will be updated when the migration is verified from the workflows, not when it is
  scheduled.
- **`flightmap-dev` is a deploy user, not a read-only one, and is not the Lambda runtime
  identity.** `backend/iam-policy.json` grants `cloudformation:DeleteStack`, `s3:DeleteBucket`,
  `lambda:DeleteFunction`, `iam:CreateRole`, `iam:PutRolePolicy` and `iam:PassRole`. A leaked
  Actions secret would therefore reach the full production stack. The Lambdas run under
  per-function roles SAM generates from the `Policies:` blocks in `backend/template.yaml`;
  no explicit `Role:` is declared.

### Authentication + authorisation on the API

- **API key required** on every `/v1/score*` endpoint (API Gateway Usage Plan; 10,000 requests/month free tier; per-key throttling at 2 req/s sustained, 5 burst). Requests and scores are the **same unit**: `/v1/score/batch` is denied to the free plan per-method (`RateLimit: 0`, answered as 429), so a request cannot carry more than one query. This corrects a line that survived until 2026-09-01 describing the quota and the ×100 batch multiplier as they stood before 2026-08-21.
- **Per-route APIGW throttle** of 1 RPS / 5 burst on `/v1/signup` to gate self-service abuse (audit ID: N-Code-2).
- **Self-service signup hardened**: CORS allow-listed to `https://skyscore.co.uk` and the legacy CloudFront URL only (no wildcard), one-key-per-email idempotency with consistent-read DDB, race-recovered orphan-key cleanup, structured `[SIGNUP_ORPHAN_KEY]` log prefix for CloudWatch alarming.
- **Favourites endpoint** uses an opaque `X-Device-Token` UUID header (audit C3 mitigation; capability-based, not identity-based — anyone learning a token can use it). Documented limitation; identity-based auth is on the roadmap if PII expands.

### Encryption + data residency

- **All data processed in AWS eu-west-2 (London)** for UK data residency.
- **TLS 1.2+** end-to-end (CloudFront, API Gateway, Lambda, S3 all default-on; HTTPS-only).
- **DynamoDB encryption at rest** via AWS-managed KMS (default; customer-managed KMS available on Enterprise tier when required).
- **No card data, no special-category PII**. Sole PII processed is the email address provided to `/v1/signup` for API-key issuance.

### Application-layer defences

- **XSS sweep**: every `innerHTML` interpolation that touches third-party data (OSM, TfL, Land Registry, NHS, postcodes.io, autocomplete user input, borough/postcode strings) wrapped in `escapeHtml`. URL allow-list `safeUrl` for `href` from community sources. Audit IDs: N-Sec-1, N-Sec-2, N-Sec-3.
- **Content Security Policy** enforcing on all **nine** deployed HTML pages (consumer site, prototype, score-demo + api-docs + status, /api, /pricing, /privacy, /changes). This said "five" until 2026-08-03, which *understated* the coverage - the four B2B funnel pages were protected and uncredited. Per-page allow-lists; no `'unsafe-eval'`; `frame-ancestors 'none'`; `base-uri 'self'`; `form-action 'self'`. Plus `X-Content-Type-Options: nosniff` and `Referrer-Policy: strict-origin-when-cross-origin` on every page.
- **Bedrock cost-abuse prevention**: the Bedrock-using Lambdas (chat, multi_agent, analyze_image, analyze_document, report) and their API Gateway routes were removed entirely on 2026-05-07 after a smoke test discovered they were anonymously invokable. Restoration is a `git revert` away if AI features come back as user-triggered constrained variants.
- **Live aircraft feature removed** pending OpenSky Network licensing (Ticket #835285 with OpenSky open since 2026-05-07).
- **`AllowedPattern '^.+$'`** on every `NoEcho` SAM parameter (currently `EpcBearerToken`); empty / missing token at deploy time fails CloudFormation parameter validation before the changeset runs. Audit ID: I-A-equivalent.
- **Zero third-party code ships to the browser from npm.** `package.json` has an *empty* `dependencies` block — every npm package is a `devDependency` (ESLint, Prettier, stylelint, html-validate, Playwright), and the site is a single hand-written `index.html` with no build step, so nothing from `node_modules` reaches production. Verified 2026-07-27: `npm audit --omit=dev` reports **0 vulnerabilities**, while the full dev tree reports 4 high-severity advisories in the linting toolchain (`postcss`, `js-yaml`, `fast-uri`). Those affect developer machines only and are reported as advisory by `/preflight`. An earlier version of this line claimed a flat "`npm audit` clean (0 vulnerabilities)", which stopped being true as the dev tree aged.

### Operational visibility

- **CloudWatch logs** on every Lambda invocation. Structured `[SIGNUP_ORPHAN_KEY]` prefix on the orphan-key path for metric filter / alarm setup.
- **Log retention is 30 days — REMEDIATION PERFORMED AND VERIFIED 2026-08-07.** This section once claimed "default 90-day retention"; that was wrong (corrected 2026-07-26), and the truth was that log groups created implicitly by Lambda have **no** retention policy at all, so every group read `retentionInDays: none`, i.e. *Never Expire*, for the life of the project. **Now done, and verified by re-reading the AWS API rather than by trusting the console:** the widened deploy policy in `backend/iam-policy.json` was applied, **7 groups were deleted** and **30-day retention set on the 7 that remain** (`Score`, `Favourites`, `Epc`, `SoldPrices`, `Transport`, `Nhs`, `Chat`). An earlier attempt on 2026-07-26 was reported done and was found unchanged, which is why the verification here is a fresh `describe-log-groups` read and not a dashboard glance.
  - **The count was 14, not the 13 recorded here for weeks.** Restoring `chat` on 2026-08-06 added an eighth active function and left its predecessor's group behind, so there were two `ChatFunction` groups differing only in CloudFormation suffix. The dead one (`wzeXuMdafiCz`) was deleted and the live one (`LuxoNSLxJMva`) kept.
  - **Scope of the personal-data exposure, now cleared:** the signup Lambda logged raw email addresses between 2026-06-26 and 2026-07-23, when the code path was fixed. Those entries sat in the `SignupFunction` log group. **That group was deleted outright rather than aged out** — under GDPR storage limitation those are different remedies, and only deletion actually removes the data.
  - **Enforced, not just done.** `scripts/check_log_retention.sh` runs as a blocking preflight stage and asserts that AWS matches whatever `privacy.html` §2d claims, in both directions. It derives the expected function set from `backend/template.yaml`, so a restored or removed Lambda updates the check automatically.
  - **One residual gap, stated rather than hidden:** Lambda recreates a deleted log group on the next invocation **with no retention policy**. The `SignupFunction` group will therefore reappear at *Never Expire* the first time somebody signs up, and stays that way until retention is set on it again. The preflight check will catch it and go red; nothing silently regresses, but it is a manual step each time, and the durable fix is to declare retention in `template.yaml` rather than applying it by hand.
- **Public status page** at <https://skyscore.co.uk/score-demo/status.html> ping-checks all live endpoints every 60s.
- **Self-performed audits** quarterly via the 3-agent + manual process documented in [`AUDIT_REPORT.md`](./AUDIT_REPORT.md). External penetration test deferred until first paying enterprise customer.
- **Billing alarm setup runbook** in [`AWS_BILLING_ALARM_SETUP.md`](./AWS_BILLING_ALARM_SETUP.md). Threshold $20 USD; would have caught today's "AI Lambda routes left open" defect within hours.

### Supply chain + sub-processors

- **AWS** is the primary sub-processor of customer data (eu-west-2). **Corrected 2026-08-03:**
  this line previously said AWS was the *sole* sub-processor. It is not — a user-typed postcode
  reaches **api.postcodes.io** from the web app, the native app and the score Lambda's Tier-2
  resolver, and this register defines that postcode as customer data. See
  [`SUBPROCESSORS.md`](./SUBPROCESSORS.md) row 4 for the full list; see
  [`LICENSING.md`](./LICENSING.md) for data-source licensing.
- **Cloudflare** provides DNS and domain-registration only (no access to API requests, responses, or customer data).
- **GoatCounter** provides consumer-site analytics on the marketing surface only (no API traffic, no PII, EU-hosted).
- **The Lambdas have no third-party Python dependencies at all** — every handler imports only the standard library plus the `boto3`/`botocore` provided by the AWS runtime. There are no per-Lambda `requirements.txt` files (an earlier version of this line claimed there were), so the backend has no PyPI supply-chain surface to audit. Frontend/tooling dependencies are tracked in `package.json` and `npm audit` runs as part of the [`/preflight`](./.claude/skills/preflight/SKILL.md) check before every commit.

### Code + change discipline

- **Pre-commit `/preflight`** runs ESLint, Prettier, html-validate, ruff (Python), and the Python test suite (**362 tests** across backend and root: 171 backend + 191 root, counted 2026-08-03). Blocking on any new error.
- **Commit hygiene**: per-feature atomic commits, full SHA citations in CHANGELOG, audit-finding IDs referenced inline.
- **Public CHANGELOG** at [`CHANGELOG.md`](./CHANGELOG.md) with the security-relevant items grouped by release.

---

## Procedures

### Incident response

For a confirmed security incident affecting customer data or the production API:

1. **Triage** within 4 hours of report: confirm impact, identify affected accounts/keys.
2. **Containment**: rotate any compromised secrets immediately (API keys via APIGW console; EPC bearer via the MHCLG dashboard; AWS access keys via IAM); revoke API keys with `apigateway:DELETE` (Lambda or console); isolate Lambdas via API Gateway throttle to 0 RPS if needed.
3. **Notification**: any customer whose data is at risk gets a same-day notification.
4. **Post-mortem**: written in the relevant audit report (`AUDIT_REPORT.md`) within 72 hours; published in CHANGELOG with the fix commits cited.

### Disaster recovery

- **RTO**: 24 hours from confirmed loss to restored service.
- **RPO**: 1 hour for customer-facing state (signup table, favourites table). **Met.** DynamoDB Point-in-Time Recovery is enabled on **all four tables** in [`backend/template.yaml`](./backend/template.yaml), not merely planned - this section described it as a pending 1-click console action until 2026-08-03, understating the actual recovery posture.
- **Source code**: GitHub remote at <https://github.com/billkhiz-bit/london-flight-path-map>; mirrored locally at the canonical `C:\Users\bilal\projects\` clone. Recovery is `git clone` + `sam deploy` (~15 min wall-clock).
- **Single-region deployment** (eu-west-2). Multi-region failover available on Enterprise tier when contractually required; not built ahead of demand.

### Data subject requests (GDPR)

PII processed: email (and optionally name) for API key issuance, stored in the `london-flight-map-signups` DynamoDB table; CloudWatch logs containing the email for audit traceability.

For an SAR / delete-my-data / data-export request, email `support@skyscore.co.uk` - the address privacy.html and SUBPROCESSORS.md both already publish. This page named a personal Gmail until 2026-08-03, so a data subject following the privacy notice and one following this document were told to write to different places. Manual workflow:

1. **SAR (Subject Access Request)**: query the SignupsTable by email; export the row as JSON; redact internal log identifiers; reply within 30 days per Article 12.
2. **Delete**: `apigateway:DELETE` the issued key; `dynamodb:DeleteItem` the SignupsTable row; scrub matching CloudWatch log events using a CloudWatch Logs Insights query and `delete-log-event` (best-effort; CloudWatch retains aggregate metrics that can't be deleted per-event).
3. **Data portability**: same as SAR, formatted as JSON.

Lawful basis for processing the email: **Article 6(1)(f) legitimate interest** (issuing and managing access credentials for the API the user signed up to). LIA on file; available on request.

### Vulnerability disclosure

Per `/.well-known/security.txt`. We commit to:

- Acknowledge receipt within 1 working day.
- Provide an initial triage assessment within 5 working days.
- Credit the reporter publicly (with consent) once the issue is fixed.
- Not pursue legal action against good-faith research that follows responsible-disclosure norms (no destructive testing on prod, no targeting of other users' data).

---

## What we do *not* yet have

To be transparent (procurement teams catch overstated claims):

| Control | Status | When |
|---|---|---|
| SOC 2 Type I / II | 🔴 Not yet | Multi-year track; starts once first enterprise customer requires it (~£8-15k/yr Drata/Vanta) |
| ISO 27001 | 🔴 Not yet | Same |
| Cyber Essentials Plus | 🔴 Not yet | Lower bar (~£1.5k); will add when first UK enterprise customer asks |
| Independent penetration test | 🔴 Not yet | ~£3-5k for a 3-day external test; commission once revenue justifies it |
| DPA template | 🔴 Not yet | CommonPaper / PandaDoc UK template; 2-3 hr legal review when first asked |
| MSA template | 🔴 Not yet | CommonPaper SaaS MSA + Sky Score schedule; 1-day legal effort |
| Professional indemnity / cyber liability insurance | 🔴 Not yet | Hiscox / Markel quote ~£400-800/yr for solo dev pre-revenue; purchase when a contract specifically requires it |
| Customer-managed KMS encryption | 🟡 Available on request | Default is AWS-managed KMS |
| Multi-region failover | 🟡 Available on Enterprise tier | Default is single-region eu-west-2 |
| 99.9%+ uptime SLA | 🟡 Best-effort, not contractual | Will offer 99.5% on Professional / 99.9% on Enterprise once first customer commits |

If a procurement questionnaire requires any of the above as a hard pre-condition, please ask explicitly so we can quote the cost + timeline.
