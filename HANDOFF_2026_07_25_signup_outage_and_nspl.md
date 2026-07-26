# Handoff — 2026-07-25: signup outage, audit re-verification, NSPL postcode independence

> **SUPERSEDED 2026-07-26 — deployed, and the headline diagnosis below is incomplete.**
> The backend is now live and `POST /v1/signup` returns **201**, verified. But §1's cause is only *half*
> the story: there were **two stacked IAM faults**, and `878b09d` fixed only the downstream one, so the
> funnel was still 503'ing after the first deploy. The *first* blocker was a missing tagging grant —
> API Gateway keeps tags at a separate resource path (`/tags/{arn}`), so `create_api_key(tags={...})`
> needs `arn:aws:apigateway:*::/tags/*`, which `dab713d` never added. `CreateApiKey` was therefore denied
> before any key existed, which also means §1's claim that "step 1 worked" is wrong — it had never once
> succeeded in production. Fixed by a second deploy the same day. See `CHANGELOG.md` 2026-07-26 and the
> `project-signup-funnel-outage` memory for the corrected account.
>
> One correction to §1's method: `iam:GetRolePolicy` is **not** granted to `flightmap-dev` (nor is any
> `logs:*` read or `cloudtrail:LookupEvents`), so the deployed role policy cannot in fact be read that way.

**State (as written 2026-07-25):** two commits local and unpushed (`878b09d`, `ebd6abf`), working tree clean,
preflight green (0 ESLint errors, HTML/Prettier/ruff clean, 257 tests, API-URL drift PASS). **Nothing deployed.**

A frontend batch was in flight when this was written — see §6.

---

## 1. The headline

`POST /v1/signup` returned **503 to every visitor from 2026-05-07 (`dab713d`) until today's source fix**.
The whole top of the Free → £499 Professional ladder — the CTA on `/pricing` and `/api/` — was a dead end
for two and a half months, through the exact window Aini/Haatch asked for commercial proof.

**Cause.** One IAM statement granted `apigateway:POST` on *both* `/apikeys` and `/usageplans/*/keys` under a
single `StringEquals: aws:RequestTag/CreatedBy = SignupLambda` condition. `create_api_key` passes that tag,
so step 1 worked. `CreateUsagePlanKey` accepts **no tags at all** — UsagePlanKey is not a taggable resource —
so `aws:RequestTag` is absent, `StringEquals` on an absent key is false, and step 2 hit an implicit deny.
The condition was added deliberately as an audit I-G follow-up: **a security hardening silently broke the
feature it was protecting.**

Verified three ways: the *deployed* role policy read via `iam:GetRolePolicy`; `aws apigateway
create-usage-plan-key --generate-cli-skeleton` having no `tags` member while `create-api-key` does; and
`git log -S 'aws:RequestTag/CreatedBy'` pinning the commit.

**Cost: zero.** Three API keys exist account-wide, all correctly attached; the signups table holds one row
created 2026-05-06, *before* the regression. Failing signups would have left orphaned enabled keys — there
are none, so nobody attempted one. **Do not run an orphan-key cleanup sweep**; an agent's risk list wrongly
claimed one was needed.

**Why it lasted:** there was no 201 happy-path test. The suite covered every error branch and never asserted
that signup *succeeds*. That test now exists.

---

## 2. Deploy runbook

Do these in order. Steps 1 and 2 are prerequisites, not optional.

### Step 1 — Rotate the EPC token (gates everything)
Regenerate from the My account page on `get-energy-performance-data.communities.gov.uk`, update
`EPC_BEARER_TOKEN` in `.env`. Both of 24 Jul's deploys reused the old token.

### Step 2 — Make rollback possible
`flightmap-dev` has `dynamodb:CreateTable` but **not `DeleteTable`**, and the new `PostcodeTable` has no
`DeletionPolicy`, so it defaults to `Delete`. If anything later in this push fails, CloudFormation will try
to delete the just-created table, be denied, and wedge the stack in `UPDATE_ROLLBACK_FAILED` — which
`flightmap-dev` also cannot recover from, lacking `cloudformation:ContinueUpdateRollback`. The live API
would sit broken until someone with admin access intervenes.

Pick one:
- Add `dynamodb:DeleteTable` on `arn:aws:dynamodb:eu-west-2:*:table/london-flight-map-*` to
  `FlightMapDeployPolicy` (`backend/iam-policy.json` is **not** deployed by SAM — needs a manual
  `aws iam put-user-policy`), **or**
- Set `DeletionPolicy: Retain` on `PostcodeTable` in `backend/template.yaml`.

### Step 3 — Deploy
```bash
set -a && source ../.env && set +a && \
  cd backend && rm -rf .aws-sam && \
  AWS_PROFILE=flightmap sam build && \
  AWS_PROFILE=flightmap sam deploy --parameter-overrides \
    EpcBearerToken="$EPC_BEARER_TOKEN"
```
This one deploy carries: the signup IAM fix, the `/epc` throttle, the `MethodSettings` de-duplication, the
new (empty) `PostcodeTable`, the score-Lambda NSPL tier, favourites validation, and 24 Jul's source-only
backend fixes. **It cannot be split** — `template.yaml` carries both the security fixes and the table.

### Step 4 — Verify (this is the step that settles the open question)
```bash
# 1. Signup must return 201, not 503. Burns the address permanently (no re-issue path) — use a throwaway.
curl -s -X POST https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/signup \
  -H 'Content-Type: application/json' -d '{"email":"throwaway+skyscore@example.com"}' | head -c 400

# 2. Throttles must match the template — epc/GET 3/6, v1/score/GET 40/80, batch 10/20.
AWS_PROFILE=flightmap aws apigateway get-stage \
  --rest-api-id 2gjfdzg20c --stage-name prod --region eu-west-2 \
  --query 'methodSettings'
```
**If signup still 503s:** the remaining fault is the `aws:RequestTag` condition on `/apikeys`, which has
never once been satisfied in production. The fix is to close audit I-G a different way — **NOT** to merge
the two statements back together.

Note step 2 will also *raise* `POST /v1/score/batch` from its live 5/10 to 10/20 — that is 24 Jul's intended
soak fix, which never actually took effect (see §3).

### Step 5 — Load the postcode table
Only after the deploy, since the table must exist. The Lambda upgrades silently as rows land; **no second
deploy.**
```bash
python scripts/load_nspl.py --self-test          # ~1s, no AWS calls
python scripts/load_nspl.py --dry-run --limit 100 # ~2s, proves credentials + mapping
AWS_PROFILE=flightmap python scripts/load_nspl.py # ~40 min, ~£1.50, resumable
```

---

## 3. The near-miss worth knowing about

`MethodSettings` declared `GET /v1/score` **twice** — 24 Jul's soak fix at 40/80, and an older "audit I-D"
pair at 5/10 sitting *below* it. CloudFormation renders `MethodSettings` into **ordered** UpdateStage patch
operations, so the later entry wins: the template's effective desired state was still 5/10, identical to the
pre-soak deployment. That is why CFN emitted no patch on the 2026-07-24 21:41Z update, and why the live
40 rps existed **only as console drift** from that session's "fixed live" step.

Adding the `/epc` entry would have re-emitted the collection and cut the primary paid route eightfold,
silently, as a side effect of an unrelated security fix. Duplicates are now removed and the I-D rationale is
folded into the surviving comment.

The same add-above-instead-of-edit pattern appeared **twice in one day** — the other in `index.html`, where
commit `f1abcad` fixed a 9px `.search-hint` accessibility problem by adding an 11px rule above the old one,
so the fix has never rendered on the website for a single day. Worth a `/preflight` addition: a duplicate
same-key check for `MethodSettings` and duplicate same-specificity CSS selectors.

---

## 4. Open decision — batch metering (yours, not Claude's)

API Gateway usage plans meter **requests**, not payload items, and `MAX_BATCH_SIZE = 100`. So:

| Tier | Advertised | Actually delivers |
|---|---|---|
| Free | 1,000 requests/month | **100,000 scores/month** |
| Professional £499/mo | 100,000 requests/month | **10,000,000 scores/month** |

The free tier is numerically equal to Professional's entire allowance, extractable in ~9 minutes at the
plan's 2 rps, repeatable per email address. **£0 has actually leaked** — no paying customers, and nobody
could sign up anyway (§1).

Two options: keep per-call metering (customer-generous, simple story, no code) or move to per-score metering
(protects the ladder; APIGW cannot count this natively, so it needs Lambda-side usage recording keyed on
`requestContext.identity.apiKeyId`). **Decide before Professional launches.**

Whichever way it goes, the "1,000 requests" figure appears on **five** surfaces and they must change
together: `pricing.html:244`, `api/index.html:291`, `README.md:74`, `score-demo/index.html:372`,
`METHODOLOGY.md:733`.

Already fixed: `pricing.html` no longer sells the batch endpoint as an Enterprise differentiator while the
deployed API serves it to every free key.

---

## 5. Audit re-verification — 18 of 19 confirmed

The leads stranded when the spend limit killed the verifiers on 24 Jul were re-checked with the verifiers
instructed to be adversarial and default to *refuted*. Result: 13 confirmed, 5 partially real, 1 fully
refuted. **None** overlapped with 24 Jul's fix wave.

Useful pattern: **finders got the mechanism right and the consequence wrong.** Every "partially real"
verdict was a real defect whose claimed harm dissolved under test — the favourites "crash" is a clean 503,
the `escapeHtml` duplicates are byte-identical rather than an XSS gap, the orphan key is a dead credential
rather than an auth bypass. Five cited line numbers had already drifted. One was materially *under*-rated:
"orphan key leak" was actually the dead funnel in §1.

Full triage, with failure scenarios and fix sketches, is in `AUDIT_REPORT.md` §2026-07-25.

---

## 6. Frontend batch (deploys independently via CloudFront)

In flight at the time of writing. Ranked:

1. **Search-flow request sequencing** — the only finding where users see *wrong data*. Live-reproduced:
   search SW11 1AA then TW3 1AA and the page settles on "TW3 1AA — Hounslow Central" showing SW11's 411 EPC
   certificates and a £875,000 Battersea Park Road sale. Terminal state, no error, no loading indicator.
2. **`sw.js` cache-first strands installed PWAs on a stale `js/api-base.js`** — harmless today, irreversible
   the moment the `api.skyscore.co.uk` CNAME swap happens, because that means editing `api-base.js`, which
   has no reason to touch `sw.js`. **Must land BEFORE that DNS change.** Recovery needs a byte change to
   `sw.js`; CloudFront invalidation does not do it.
3. `switchCity` re-entrancy, resize debounce + D3 transition interrupt, verdict colour contrast (1.16:1
   against a 4.5:1 requirement, on the product's headline output), `.search-hint` duplicate, score-demo
   sequencing.

---

## 7. Still open, all user-side

- EPC token rotation — gates every backend change (§2 step 1)
- `dynamodb:DeleteTable` grant or `DeletionPolicy: Retain` (§2 step 2)
- Live `POST /v1/signup` check after deploy (§2 step 4)
- Batch-metering decision (§4)
- Cloudflare `CNAME api → d1pr4crjutz9z8.cloudfront.net` (DNS only / grey cloud) — **do the `sw.js` fix first**
- Signup log-retention console click, Gmail `/mcp` re-auth, Migadu/DKIM before cold outreach
- `git push` — two commits are local only, per the never-push-without-asking convention

## 8. Not built

The **offline city-scale bulk scorer** — the second consumer the NSPL table was designed for, and the actual
Enterprise "score your whole book / whole city" deliverable plus the managed-first-load pilot motion. The
table now exists in source to serve it; the scorer itself is the next real build.
