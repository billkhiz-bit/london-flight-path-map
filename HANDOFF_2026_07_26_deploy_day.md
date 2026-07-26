# Handoff — 2026-07-26: backend deployed, signup funnel actually fixed, NSPL live

**State at close:** 11 commits local and **unpushed**, working tree clean, 125 backend + 140 root
tests green. Backend and frontend both deployed and verified. **One item outstanding and it is
console-only — see §6.**

---

## 1. The headline

**The signup funnel is open again.** `POST /v1/signup` returns `201` with a working
usage-plan-attached key, verified live. It had returned `503` to every visitor since 2026-05-07.

**The 25 July diagnosis was half right, and that mattered.** There were **two stacked IAM faults**;
`878b09d` fixed only the downstream one, so the funnel was *still dead* after the first deploy of
the day.

- **Fault 2 (fixed 25 Jul).** `CreateUsagePlanKey` sat under a `aws:RequestTag/CreatedBy` condition
  it can never satisfy, because UsagePlanKey is not taggable. Correctly fixed by splitting the
  statement.
- **Fault 1 (fixed 26 Jul, the actual first blocker).** In API Gateway, **tags live at a separate
  resource path** — `/tags/{arn}`, TagResource is `PUT /tags/{arn}`. So `create_api_key(tags={...})`
  needs a grant on `arn:aws:apigateway:*::/tags/*`, which the audit I-G hardening never added.
  `CreateApiKey` was denied *before any key existed*, meaning the `/apikeys` half of that condition
  had **never once succeeded in production** — exactly as the 25 July handoff warned it might.

**Generalisable lesson: granting a tag *condition* is not the same as granting the *tagging*.**
A condition constrains a permission you already hold; it never confers one. That is why the
hardening looked complete and passed review — the statement it added was correct, just insufficient.

The condition was **kept** on the new statement. Dropping it would let the Lambda write arbitrary
tags onto any API Gateway resource in the account, a wider hole than I-G ever closed.

---

## 2. How it was diagnosed without logs

CloudWatch was unreadable (`flightmap-dev` has no `logs:*` read, no `cloudtrail:LookupEvents`, no
`iam:` read — so **`/aws-debug` cannot function on this account**). The failing call was instead
found by **side-effect elimination**:

> `create_api_key()` commits observable state between its three calls, so `get-api-keys`
> distinguishes them. A failed signup left **no key and no orphan**, which places the denial
> *before* key creation and rules out `CreateUsagePlanKey` entirely.

Reusable pattern: find the state transition the code commits before the failure point, and the
account itself becomes the log.

---

## 3. Everything that shipped

| Item | Status |
|---|---|
| Signup `/tags/*` IAM grant | Deployed, live `201` verified |
| NSPL `PostcodeTable` created + **fully loaded** | 2,699,393 rows, 332,308 London, 5.80h |
| `DeletionPolicy: Retain` on **all four** DynamoDB tables | Deployed in place, no data disturbed |
| EPC `403` handling | Deployed, 3 tests added |
| Frontend batch (was committed but **never deployed**) | Deployed + gates green |
| Stage throttles | `/epc` 3/6 new, batch 5/10 → 10/20, score 40/80 now **declared in source** |
| Doc corrections | 3 statements that were *wrong*, not merely stale |

**The frontend catch is worth noting**: `index.html`, `sw.js`, `js/api-base.js` and
`score-demo/index.html` had all drifted from S3. The search-flow race — one postcode's EPC and
sold-price data rendered under a *different* postcode's heading, a terminal state that never
self-corrects — was live on skyscore.co.uk the entire time the fix sat committed.

---

## 4. NSPL load — verified, with a vintage debt

`2,699,393` written · `24,203` skipped · `904,453` terminated · `332,308` London · `0` mismatches ·
**5.80 hours at ~129 rows/s**.

**Verified by `get-item`, never `ItemCount`** — the latter refreshes ~6-hourly and read `0`
throughout; anyone checking that way would conclude the load had failed. Ten probes correct,
including the boundary cases the loader itself nominates: `E1 6AN` → **City of London**,
`BR1 1HB` → Bromley with the predicted `dt=198412, q=8`. Controls confirm non-London rows carry
**no** `b`, which keeps the "borough not supported" 404 byte-identical.

**postcodes.io is now the fallback, not the primary.** The fair-use exposure that made a customer's
100k-address backfill indefensible is closed.

**Two debts:**
1. **Vintage.** The table holds the **February 2026** edition, confirmed from the data
   (`max(dointr) = 202601`), not from the hardcoded `NSPL_VINTAGE` constant. May already existed;
   August is due within weeks. Harmless — post-Feb postcodes miss and fall back — but roll it.
2. **Speed.** The loader is ~10× slower than its own docstring claimed. It is **client-CPU-bound**
   on 2.7M separate TLS + SigV4 handshakes, because it issues one `PutItem` per row — and it does
   *that* only because `dynamodb:BatchWriteItem` is not granted. **Grant it and switch
   `_flush_batch` before the August roll.** More workers will not help.

---

## 5. Docs that were wrong, not stale

Checked against the live account rather than re-read:

- **`SECURITY.md` claimed "default 90-day" CloudWatch retention. It is UNLIMITED.** All 13 groups
  read `retentionInDays: none`. This is a customer-facing document, and the signup Lambda logged
  **raw email addresses until 2026-07-23** — personal data retained indefinitely while published as
  expiring. A GDPR storage-limitation gap, not a typo.
- **`SECURITY.md` claimed per-Lambda `requirements.txt`.** None exist; every handler is stdlib plus
  the runtime's boto3, so the backend has **no PyPI supply-chain surface**. This also makes the
  preflight skill's `pip-audit` step a no-op that reads as a green tick.
- **`OPERATIONS.md` §6's debugging recipe was entirely unrunnable** — it said to tail CloudWatch and
  run `/aws-debug`, both denied. Its throttle figures were two deploys stale, its CORS note
  contradicted the 24 Jul `CORS_ORIGIN: '*'` fix, §4 listed 3 DynamoDB tables (there are 4) and the
  leaked-secret row cross-referenced the wrong section.

---

## 6. OUTSTANDING — console-only, blocks the push

**The CloudWatch log-group work has NOT been done.** It was reported as done on 26 Jul but verified
unchanged: all 13 groups present, all `retentionInDays: none`, and the Signup group's
`creationTime` still `2026-05-06 13:23` — which proves the delete never happened, independently of
any caching question.

**Delete these 7** (6 dead Lambdas + the signup group; deleting the signup group *is* the GDPR fix,
because 30-day retention would preserve the raw-email entries from 26 Jun–23 Jul):

```
/aws/lambda/london-flight-map-AnalyzeDocumentFunction-WGYkSBln0Rii
/aws/lambda/london-flight-map-AnalyzeImageFunction-BYNUmNi4Lxbq
/aws/lambda/london-flight-map-ChatFunction-wzeXuMdafiCz
/aws/lambda/london-flight-map-LiveFlightsFunction-inXEwZXJB5hG
/aws/lambda/london-flight-map-MultiAgentFunction-0BaKRcMkZzE6
/aws/lambda/london-flight-map-ReportFunction-bnFAI9UXiDBI
/aws/lambda/london-flight-map-SignupFunction-vLApmPCZyQTD
```

**Set 30-day retention on these 6:** Score, Favourites, Transport, Epc, SoldPrices, Nhs.

**This must be done in the AWS console as root/admin.** There are no working admin credentials on
this machine: `default` is dead (`InvalidClientTokenId`) and `flightmap` is deploy-scoped and cannot
even read its own IAM user. Region **eu-west-2**, account **072674217857**. The likeliest silent
failure is retention — *Edit retention setting* opens a modal whose dropdown does nothing until
**Save**, and closing it loses the change with no warning.

### Why this blocks the push

**The repo is PUBLIC** (`github.com/billkhiz-bit/london-flight-path-map`). `SECURITY.md` currently
describes the retention gap as **open**, so pushing now publishes a written admission of a live
GDPR exposure on a repo shown to investors and pilot customers. Bill chose "fix it first, then the
docs describe a closed gap" — that precondition has not been met, so **the 11 commits were
deliberately not pushed.**

Once the console work is done: rewrite the `SECURITY.md` passage as closed, then push.
Note `npm run trigger:ios` *is* `git push origin master`, so the push also starts a Codemagic build.

---

## 7. Also outstanding

- **Task #4** — verify ONS now appears in `/v1/score` `sources`. The Lambda gates ONS credit on
  `_LOCAL_POSTCODE_SERVED` so it never makes a false provenance claim while the table is empty; the
  table is now full, so it should be crediting. OGL v3.0 attribution compliance. Needs an API key.
- **IAM grants** on `FlightMapDeployPolicy`, all scoped `london-flight-map-*`: `logs:FilterLogEvents`
  / `GetLogEvents` / `DescribeLogStreams` (makes `/aws-debug` work), `logs:PutRetentionPolicy` /
  `DeleteLogGroup` (retires this console trip), `dynamodb:BatchWriteItem` (NSPL speedup).
- **Batch metering decision** — still blocks the Professional launch. Free tier is really 100k
  scores/month.
- Cloudflare `CNAME api → d1pr4crjutz9z8.cloudfront.net` — **now safe**, the `sw.js` unstranding fix
  is live. Order: CNAME first, repoint `api-base.js` only after.
- Migadu/DKIM before cold outreach; Android Play Console flow.
