# Sky Score, security one-pager

A pre-emptive answer to the "are you SOC 2 / ISO 27001" question that almost every B2B procurement team asks. **Sky Score does not yet hold a third-party security attestation** (SOC 2 Type I/II, ISO 27001, Cyber Essentials Plus). Those are 6-12 month exercises with substantial fixed cost, sized for serving a customer base that justifies them. Sky Score is pre-revenue; the attestation track will start once the first paying enterprise customer specifically requires it.

In the meantime, this document lists the controls that **are** in place today and the procedures that handle the questions a security questionnaire would raise. It is updated alongside the codebase; the canonical source is the linked AUDIT_REPORT.md, LICENSING.md, and METHODOLOGY.md.

**Last reviewed:** 2026-05-07

---

## Reporting a vulnerability

If you've found a security issue (XSS, IDOR, IAM gap, secret leak, abuse vector, anything you'd want to disclose privately), reach out at **`billkhiz@gmail.com`** or via the contact in [`/.well-known/security.txt`](https://skyscore.co.uk/.well-known/security.txt) (RFC 9116 format).

Sole-developer, independent project. Reply timeline best-effort but typically within a working day for things that look real.

---

## Controls in place

### Scope of this document

Sky Score has three deployment surfaces sharing one codebase: web (skyscore.co.uk), PWA (browser-installable), and native iOS / Android (Capacitor wrap, Codemagic-built, App Store + Play Store distribution). The controls below apply to all three unless flagged otherwise. The native wrap adds two surfaces with their own security stories: the `capacitor://` (iOS) / `https://localhost` (Android) WebView origin is locked down by the same CSP as the web origin; the Codemagic build pipeline accesses source code only (no user data). Full sub-processor list including Apple App Store + Google Play in [`SUBPROCESSORS.md`](./SUBPROCESSORS.md).

### Access control + least-privilege

- **Per-Lambda IAM policies** (no shared catch-all role). Each Lambda gets only the permissions it needs; the SAM template at [`backend/template.yaml`](./backend/template.yaml) enumerates them inline.
- **Tag-condition scoped IAM** on the signup Lambda's `apigateway:DELETE` and `apigateway:GET` for `/apikeys/*` — keys are tagged `CreatedBy=SignupLambda` at creation time (with a matching `aws:RequestTag` condition on POST) and only deletable by the same Lambda that created them. Audit ID: N-Code-1.
- **MFA required** on the AWS account root and admin IAM user (account-level setting; not in code).
- **No long-lived AWS access keys** in source. CI / deploy uses GitHub OIDC where applicable; `flightmap-dev` is the runtime API user with read-only operational scope.

### Authentication + authorisation on the API

- **API key required** on every `/v1/score*` endpoint (API Gateway Usage Plan; 1000 req/month free tier; per-key throttling).
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
- **Content Security Policy** enforcing on all five HTML pages (consumer site, prototype, score-demo + api-docs + status). Per-page allow-lists; no `'unsafe-eval'`; `frame-ancestors 'none'`; `base-uri 'self'`; `form-action 'self'`. Plus `X-Content-Type-Options: nosniff` and `Referrer-Policy: strict-origin-when-cross-origin` on every page.
- **Bedrock cost-abuse prevention**: the Bedrock-using Lambdas (chat, multi_agent, analyze_image, analyze_document, report) and their API Gateway routes were removed entirely on 2026-05-07 after a smoke test discovered they were anonymously invokable. Restoration is a `git revert` away if AI features come back as user-triggered constrained variants.
- **Live aircraft feature removed** pending OpenSky Network licensing (Ticket #835285 with OpenSky open since 2026-05-07).
- **`AllowedPattern '^.+$'`** on every `NoEcho` SAM parameter (currently `EpcBearerToken`); empty / missing token at deploy time fails CloudFormation parameter validation before the changeset runs. Audit ID: I-A-equivalent.
- **`npm audit` clean** (0 vulnerabilities, verified 2026-05-07).

### Operational visibility

- **CloudWatch logs** on every Lambda invocation; default 90-day retention. Structured `[SIGNUP_ORPHAN_KEY]` prefix on the orphan-key path for metric filter / alarm setup.
- **Public status page** at <https://skyscore.co.uk/score-demo/status.html> ping-checks all live endpoints every 60s.
- **Self-performed audits** quarterly via the 3-agent + manual process documented in [`AUDIT_REPORT.md`](./AUDIT_REPORT.md). External penetration test deferred until first paying enterprise customer.
- **Billing alarm setup runbook** in [`AWS_BILLING_ALARM_SETUP.md`](./AWS_BILLING_ALARM_SETUP.md). Threshold $20 USD; would have caught today's "AI Lambda routes left open" defect within hours.

### Supply chain + sub-processors

- **AWS** is the sole sub-processor of customer data (eu-west-2). See [`LICENSING.md`](./LICENSING.md) for full data-source licensing.
- **Cloudflare** provides DNS and domain-registration only (no access to API requests, responses, or customer data).
- **GoatCounter** provides consumer-site analytics on the marketing surface only (no API traffic, no PII, EU-hosted).
- All non-trivial dependencies tracked in `package.json` / per-Lambda `requirements.txt`. `npm audit` is part of the [`/preflight`](./.claude/skills/preflight/SKILL.md) check before every commit.

### Code + change discipline

- **Pre-commit `/preflight`** runs ESLint, Prettier, html-validate, ruff (Python), and the unittest suite (60 tests). Blocking on any new error.
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
- **RPO**: 1 hour for customer-facing state (signup table, favourites table). Achievable by enabling DynamoDB Point-in-Time Recovery (PITR) on both tables (1-click in AWS console; documented in [`backend/template.yaml`](./backend/template.yaml) as a planned addition).
- **Source code**: GitHub remote at <https://github.com/billkhiz-bit/london-flight-path-map>; mirrored locally at the canonical `C:\Users\bilal\projects\` clone. Recovery is `git clone` + `sam deploy` (~15 min wall-clock).
- **Single-region deployment** (eu-west-2). Multi-region failover available on Enterprise tier when contractually required; not built ahead of demand.

### Data subject requests (GDPR)

PII processed: email (and optionally name) for API key issuance, stored in the `london-flight-map-signups` DynamoDB table; CloudWatch logs containing the email for audit traceability.

For an SAR / delete-my-data / data-export request, email `billkhiz@gmail.com`. Manual workflow:

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
