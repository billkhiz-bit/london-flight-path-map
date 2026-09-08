# Audit Report — Sky Score

**Date:** 2026-09-07
**Scope:** whole codebase — the 8 backend Lambdas and the scoring engine,
`index.html` and the 8 other public pages, the 99 generated `area/` pages, the
browser extension, the ~45 data-derivation scripts, the gate and test suite,
CI, IAM, and every customer-facing and contractual document.
**Previous:** [`AUDIT_REPORT_2026-08-31.md`](./AUDIT_REPORT_2026-08-31.md).

---

## 1. Summary

Five parallel finders, each scoped to a seam this repo's history says is
productive, and each told that **finders here systematically overstate** — the
31 August audit's verifiers downgraded 8 of the first 13 findings and refuted
none.

| | Count |
|---|---|
| Critical | 8 |
| Important | ~30 |
| Minor | ~35 |

**Seventeen findings were re-verified by hand, in-session, outside the finder
pipeline** — by reading the policy, running the derivation, or calling the live
API. Those carry **VERIFIED** below. Everything else carries only the finder's
own evidence and should be re-measured before it is acted on.

### STATUS, 2026-09-07: 8 of 8 criticals closed, plus 11 importants

**Fixed and verified the same day, in source.** Each carries a gate that was
proven red against the defect it guards, unless noted.

| | Closed | Gate |
|---|---|---|
| **C1** | `/v1/chat` -> Bedrock `us-east-1` now disclosed: SUBPROCESSORS row 18, s5 rewritten to TWO outbound routes, SECURITY.md and METHODOLOGY s15 corrected | `test_data_residency.py`, red on the pre-fix register |
| **C2** | `.is-tabbed .sheet-footer` -> `.is-native`. Mobile web went from **1 visible link to 10**, /privacy and /terms reachable again | `tests/mobile-legal-links.mjs`, red at 4 viewports, and asserts the native sim still hides it |
| **C3** | **NOT applied - deliberately.** Recorded with its verification procedure at `OPERATIONS.md` s3.8 | none; see below |
| **C4** | `area-page-freshness` floor is now DERIVED from `/v1/regions` (99 = 99) | red on an empty `area/` |
| **C5** | Nottingham compared against ONS for the first time - `City of Nottingham` 124.9 **agrees**. 12 cities gated, up from 11 | new city-accounting guard, red both ways |
| **C6** | `score sanity` derives components from the live responses; now checks **5**, including `env` | floor added so a vanishing component reds |
| **C7** | London credits HM Land Registry again | new provenance test, red with the line removed |
| **C8** | METHODOLOGY corrected in 3 places + README; Environment row added to the component table | - |

| Importants closed | |
|---|---|
| **I1** | Retired NaPTAN nodes excluded from the SCORED transport share. **City of Nottingham `good` -> `moderate`, live 5.3 -> 4.5, score 8.3 -> 8.0**, exactly as predicted. 11 fields updated across both holders; two-directional guard added |
| **I3** | `/v1/changes` no longer credits a postcode resolver on a route that resolves nothing |
| **I4** | `/v1/environment` gained a `postcode-uncovered` notice; the payload can no longer assert and deny coverage at once. Regression test asserts the invariant over four coordinates |
| **I5** | `openapi.yaml` prose corrected to five components / 13 cities / 99 boroughs, and `check_openapi_matches_engine.py` now READS `info.description` (21 comparisons, up from 18) |
| **I7** | Area-page attribution cap removed. **90 pages now credit the Environment Agency, up from 0**; gate red on 86 pages with the cap reinstated |
| **I8** | `privacy.html` s2e added for the device token; "almost certainly: nothing", the postcodes.io native-only claim and the stale Last-updated date all corrected |
| **I9** | `?methodology=` removed from the spec and from both pages selling it |
| **I10** | preflight now reports **INCONCLUSIVE** rather than PASS when a gate says it could not verify |
| **I11** | Legend toggle 1.04:1 fixed; **landscape added to both contrast gates**, which had never run at that orientation |
| **I12** | Layers popover opens beside its trigger instead of over it; Escape closes it. 5 viewports verified |
| **I13** | Borough-parity floor derived: was `< 60` against a real **91** |
| **I14** | `panel-caveat`'s not-found sentinel is a failure, not a pass token - red 4/4 when the copy string drifts |
| **I15** | `/badge` path injection closed at `lookup_postcode`; regression test asserts both directions |

**Still open:** C3 (IAM, needs a console session and a verified deploy - see
`OPERATIONS.md` s3.8), I2 (`healthcareWithin1kmPct` names a 500 m radius - a
public field, so renaming is a contract change), and part of the Minor list in
s4 - see the note under it.

**I6 was listed here as open until 2026-09-08 and had been closed the same day
it was written**, by `scripts/check_worked_example.py`, which is blocking in
preflight and reports 16 comparisons agreeing with the engine. `HANDOVER.md`
carried the identical ghost as item 3 of its "THREE ITEMS LEFT OPEN ON
PURPOSE". Both are corrected. *An item closed by a wave has to leave the open
list in the commit that closes it, or it is rediscovered as work.*

**Two fixes exposed further defects, both now closed.** Un-hiding the mobile
footer (C2) restored its `.sep` separators at **1.97:1** and gave it a
full-width pointer-events band that swallowed taps meant for the layers
trigger at 568x320. *A fix that restores a surface restores its defects with
it.*

---
### What is different about this audit

The last three audits found their richest seam in *gates that cannot fail*, and
the 31 August one moved the centre of gravity to *documentation contradicting
code*. **Both seams produced again, and a third opened: a rule whose
justification expired when the thing it keys on changed meaning.**

Three patterns account for most of what follows.

1. **A fix applied to one of two readers of the same data.** The scored
   transport share still counts retired NaPTAN nodes while the display list
   excludes them; `build_borough_bands.py` still has the pre-fix borough-matching
   pass that `index.html` was corrected away from. In both cases the half that
   got the fix is the half a **user reads**, and the half that missed it is the
   half that **writes a score**. The defect's symptom and its blast radius
   pointed in opposite directions.
2. **A conditional that changed meaning underneath a rule that depended on it.**
   `.is-tabbed` meant "native app" when `.is-tabbed .sheet-footer { display:
   none }` was written. It came to mean "any phone" five days later. Nothing
   re-read the rule.
3. **A gate that reads the right file and the wrong part of it.**
   `check_openapi_matches_engine.py` walks schemas and enums, so it passes while
   the first paragraph of the document it guards still says "four components" —
   the exact defect its own docstring names as its reason for existing.

---

## 2. Critical

### C1 — `/v1/chat` sends customer text to AWS Bedrock in **us-east-1**, and four published documents say no such processing happens — **VERIFIED**

| | |
|---|---|
| Location | `backend/lambdas/chat/app.py:43`, `:205`; `backend/template.yaml:430,469` |
| Category | undisclosed third-country transfer |
| Live today | **Yes** |

```python
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'us-east-1')      # :43
bedrock = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION)  # :205
```

Against that:

| Document | Claim |
|---|---|
| `SUBPROCESSORS.md:113` | "no LLM provider receives any customer data" |
| `SUBPROCESSORS.md:142-146` | "**One** outbound route leaves the UK … intra-EEA … **no Article 46 safeguard is required**" |
| `SECURITY.md:63` | "**All** data processed in AWS eu-west-2 (London) for UK data residency" |
| `SECURITY.md:72` | the Bedrock Lambdas "were **removed entirely** on 2026-05-07" |
| `METHODOLOGY.md:1924` | "AWS is the sole sub-processor of customer data" |

`chat` was restored on 2026-08-06 as a retrieval-only function. The restoration
was correct; **none of these documents was updated**. `METHODOLOGY.md:1924`
survives on a technicality — Bedrock is AWS — but the residency claim does not,
and `SUBPROCESSORS.md` exists precisely to answer a B2B buyer's residency
question. `privacy.html` has no chat feature and no US-compute row at all.

**Harmed:** a regulator (Art. 13 omission, undisclosed transfer) and any buyer
whose procurement requires UK/EEA-only processing.

---

### C2 — The mobile web homepage has exactly **one** visible link; Privacy and Terms are unreachable from every phone — **VERIFIED**

| | |
|---|---|
| Location | `index.html:533-535`, inside the `@media (max-width: 900px)` block at `:500` |
| Category | rule whose justification expired |
| Live today | **Yes** — local `index.html` is md5-identical to what CloudFront serves |

Measured, counting every `a[href]` with a non-zero box and no hidden ancestor:

```
390x844  default     is-tabbed=true   visible links:  1   legal/funnel: NONE
844x390  default     is-tabbed=true   visible links:  1   legal/funnel: NONE
390x844  ?tabbed=0   is-tabbed=false  visible links: 10   legal/funnel: /pricing /privacy /terms
1440x900 desktop     is-tabbed=false  visible links: 13   legal/funnel: /pricing /privacy /terms
```

The one link is the skip link. `@media (max-width: 900px)` hides `.site-footer`
and shows `.sheet-footer` in its place — the A-0724-I6 fix, whose entire purpose
was to keep the legal links reachable on mobile — and then
`.is-tabbed .sheet-footer { display: none }` hides the replacement.

**The rule was correct when written.** It landed in `4d9a803` (2026-08-26) when
`.is-tabbed` was set on **native only**, where the comment at `:495` is right:
the app has its own nav. The tabbed layout became the **web** default at ≤900px
on 2026-08-28. Nothing re-read the rule.

**Consequences that are checkable:** no route to the privacy notice or terms
from the phone homepage; `pricing-footer-click`, `changes-footer-click` and
`appstore-footer-click` cannot fire on mobile, so funnel numbers under-count by
construction; the homepage emits zero internal links to a crawler rendering at
a mobile viewport.

**Why no gate caught it.** `responsive.mjs` asks four questions — overflow,
stranded, covered, clipped-above — every one of which is about a control that
**is rendered**. axe has no rule for "a link that used to be here". Nothing in
`tests/` asserts that a given href is reachable.

---

### C3 — The deploy user can escalate to full account admin in two calls — **VERIFIED**

| | |
|---|---|
| Location | `backend/iam-policy.json`, `Sid: IAMRolesForLambda` |
| Category | privilege escalation |
| Live today | **Yes** as a path; not exercised |

```
Actions:   iam:CreateRole, iam:PassRole, iam:AttachRolePolicy, iam:PutRolePolicy, ...
Resource:  arn:aws:iam::<acct>:role/london-flight-map-*
Condition: NONE
```

The resource constrains the **role**, not the **policy being attached**, and
there is no permissions boundary. So: attach `AdministratorAccess` to
`london-flight-map-ScoreFunctionRole-*`, then `lambda:UpdateFunctionCode`
(granted) and invoke. The same credential is in `.env` on the laptop **and in
GitHub Actions secrets on a repository confirmed public** (`visibility: PUBLIC`,
anonymous API returns 200).

**Fix:** a `Condition` on `iam:PolicyARN` restricting attachable policies to
what SAM needs, plus an `iam:PermissionsBoundary` condition on `CreateRole`.

**Related, same file — `apigateway:GET` on `arn:aws:apigateway:eu-west-2::*`
with no condition** covers `GET /apikeys?includeValues=true`, so the deploy
credential can read every customer API key in plaintext. Add an explicit `Deny`
on `/apikeys*`; the deploy path does not need key values.

---

### C4 — A blocking gate prints "OK: all 0 area pages match the live API" and exits 0 — **VERIFIED**

| | |
|---|---|
| Location | `tests/area-page-freshness.mjs:159,172`; wired at `scripts/preflight.sh:474` |
| Category | gate that cannot fail |
| Live today | **Yes** (the gate; the pages are currently in sync) |

`pages` is built by walking `area/`; the only guard is `existsSync(areaRoot)`.
**`pages.length` is never asserted.** Its sibling `tests/area-pages.mjs:64`
carries `pages.length > 50`.

```
Area page freshness
  0 pages to check, in 0 batch request(s)
OK: all 0 area pages match the live API
EXIT=0
```

Zero HTTP requests made. The gate exists because area pages **bake** their
scores; a partial loss — one city's directory — is equally silent and would
still clear the sibling's floor of 50.

---

### C5 — Three data gates enumerate cities from a hand-written list inside the gate, and one city's crime rate has never been compared — **VERIFIED**

| | |
|---|---|
| Location | `scripts/refresh_crime_from_ons.py:78` (`CITY_PFA`), `scripts/build_hpi_prices.py:69`, `scripts/build_progress8.py:115` |
| Category | global floor where a per-unit floor was needed |
| Live today | **Yes** |

```
engine cities   : 13
gate CITY_PFA   : 11
UNGATED         : ['nottingham', 'nyc']
```

NYC is legitimate — ONS is a UK source. **Nottingham is not**: `City of
Nottingham` publishes `crimeRate: 124.9`, and the **blocking** `crime == ONS
Table C4` stage has never compared it. A city present in the engine and absent
from the gate's own dict is dropped from `--all` silently; the only floor is
`if not cities`.

The finder proved the same shape on `build_hpi_prices.py` by construction: a
14th city with `trend: -99.9` added to the engine produced
`Checked 12 city/cities … RESULT: PASS`.

---

### C6 — The only gate that reads the live API does not check the `env` component — **VERIFIED**

| | |
|---|---|
| Location | `scripts/check_score_sanity.py:131` |
| Category | gate that cannot fail |
| Live today | **Yes** |

```
COMPONENTS = ('quiet', 'afford', 'growth', 'live')
engine balanced persona: ['afford', 'env', 'growth', 'live', 'quiet']
```

`env` is 0.14 of six personas and 0.18 of `family`/`laterlife`. The gate's
§2 check — "every component must discriminate", written after three separate
incidents of a component collapsing onto one value — runs over four of five.
There is no `environmentResolution` sibling to its §4 contradiction check.
CLAUDE.md calls this "the only stage that can catch a DATA defect".

---

### C7 — London's `/v1/score` credits **no price source at all** — **VERIFIED**

| | |
|---|---|
| Location | `backend/lambdas/score/app.py:4694-4714` |
| Category | licence attribution failure |
| Live today | **Yes** |

```
sources[0]              : Transport access: DfT NaPTAN, Open Government Licence v3.0
any HM Land Registry line? False
sourceBreakdown.afford  : HM Land Registry House Price Index (HPI), borough cohort min-max scaling
```

All eleven other UK cities carry `"Prices: HM Land Registry UK House Price
Index …"` as `sources[0]`. `afford` is 0.27 of the balanced score and
`context.avgPriceGbp` is HPI data.

**The mechanism is four lines above the gap.** On 2026-08-25 `'Sold prices: HM
Land Registry'` was deliberately removed, reasoning that HMLR backs `/epc` and
`/sold-prices` "not this response". That was right about *sold prices* and wrong
about *avgPrice and trend*, which are HPI — a different HMLR product feeding the
same response. **Eighth instance of the stale copy living in the same document
as its own correction.**

`terms.html:294` obliges integrators to carry the `sources` array through to
their own users, so an integrator who follows the terms exactly republishes
HMLR data with no HMLR attribution, and believes they are compliant.

---

### C8 — `METHODOLOGY.md` says in four places that road noise does not score. It is **0.35 of `environment`** — **VERIFIED**

| | |
|---|---|
| Location | `METHODOLOGY.md:159-160, :171-172, :1299, :1573`; `README.md:219` |
| Category | false published claim |
| Live today | **Yes** |

`app.py:5434` `_ENV_WEIGHTS = {'airQuality': 0.45, 'roadNoise': 0.35, 'flood':
0.20}`, and the live API says so itself — `sourceBreakdown.env` returns
*"Air quality (0.45), Road noise (0.35), Flood risk (0.20)"*. §4.7 and the v4.0
changelog **in the same document** describe it correctly.

The first of the false statements is itself a boxed *"Correction, 2026-08-04"* —
a correction that has become the false claim.

**Harmed:** a buyer comparing Sky Score against a road-noise product (§14 names
Landmark Riskview as sharing the source) is told the road data does not enter
the number they are buying.

---

## 3. Important — a selection

The full finder output is long; these change a number, a contract, or a
published score.

### I1 — The scored transport share counts **retired** NaPTAN nodes — **VERIFIED**

```
scripts/build_borough_bands.py   Status refs: 0     <- writes the SCORED field
scripts/build_city_stations.py   Status refs: 7     <- hard-fails without the column
```

Same dataset, same repo. The 2026-09-01 fix that excluded **806 inactive nodes
of 11,163** reached the display list and not the scored share, which is 0.25 of
liveability and lives in **both** score holders. Finder-measured effect: share
inflated by ≤1.02 pp, 12 boroughs affected, **one band change** — `City of
Nottingham` `good → moderate`, `live 5.3 → 4.5`, published score **8.3 → 8.0**.

### I2 — `healthcareWithin1kmPct` is a **500 m** share — **VERIFIED**

`GP_RADIUS_M = 500.0` (`build_borough_bands.py:195`) written into
`rec['healthcareWithin1kmPct']` (`:684`); the log line even prints `% <1km`.
86 published values, in `borough-extra.json`, a **deployed public asset**, so
the key name is public. The values are right; the name claims twice the radius.

### I3 — `/v1/changes` credits a postcode resolver on a route that resolves nothing, and freezes it — **VERIFIED**

Live, 3 of 3 requests:
`"Postcode resolution: ONS National Statistics Postcode Lookup (OGL v3.0), with postcodes.io…"`

`handle_changes` resolves no postcode, never calls
`reset_postcode_attribution()`, and caches the whole body in a module global —
so whatever the `threading.local()` flag happened to be on first call is baked
in for the container's life. Same root cause reaches `/v1/score/batch`, where
`build_batch_sources` runs on the main thread and never sees any worker's flag:
the finder proved it wrong in **both** directions (under- and over-crediting ONS).

### I4 — `/v1/environment` contradicts itself in one payload — **VERIFIED**

At TR1 1DT (Truro, uncovered):

```
basis  : "the nearest airports we hold, not measured - this postcode is outside every city Sky Score covers"
notice : "…DEFRA publishes contours for part of this area and this postcode falls outside them."
```

`app.py:7343` selects the notice by `'postcode-nyc' if city == 'nyc' else 'postcode'`,
ignoring the `city is None` case it has already established two lines above. The
file's own comment measures that population at **68% of live UK postcodes**, and
this is the surface the public browser extension renders. A previous fix removed
the *city name* from this string and kept the *coverage claim*.

### I5 — `openapi.yaml`'s opening description still says four components and London-plus-NYC — **VERIFIED**

```yaml
… computed from four components: Quiet …, Affordability …, Growth …, and Liveability …
**Coverage.** 33 London boroughs … 5 NYC boroughs …
```

Live: five components since v3.9, **13 cities, 99 boroughs**. The Coverage block
under-claims by eleven cities and sixty-one boroughs.

**`scripts/check_openapi_matches_engine.py` is blocking and passes** — it walks
schemas and enums, and never reads `info.description`. Its own docstring names
"described a FOUR-component score" as the defect it exists to prevent. Every
one of the 99 area pages links to this file rendered in Swagger UI.

### I6 — `METHODOLOGY.md` §6, the worked example that is the document's stated proof of reproducibility, does not reproduce — **VERIFIED**

```
document : "The live API returns quiet: 5.0 and a balanced total of 6.4" (:1195)
live     :  score 6.7,  quiet 6.4
```

The two figures are transposed. Every borough input in Step 2 is also stale
(`trend 2.1%` vs `-5.2`, sign flipped; `crimeRate 82` vs `76.4`; `transport
'excellent'` vs `'good'`), Step 2 scores schools off the **retired Ofsted band**,
and Step 3's airport term ignores `AIRPORT_NOISE_SCALE`. Two of the Step 3
errors cancel, which is why the total still lands near the truth.

**The engine is reproducible** — every live component recomputes exactly from
the code. §6 is the section an auditor executes, and it is the part that is not.

### I7 — The 99 `area/` pages truncate attribution to six lines, dropping the Environment Agency on all 90 pages that publish its flood band

`scripts/build_area_pages.py:392` — `data['sources'][:6]`. Dropped: EA RoFRS
(90 pages), DEFRA road Lden (43), DEFRA PCM air quality (10). Each affected page
prints the row it just dropped the credit for and bakes it into the Environment
score above it. Verified on the deployed page:
`grep -c 'Environment Agency Risk of Flooding'` on
`/area/london/wandsworth/` → **0**. All 99 are in `sitemap.xml`.

### I8 — `privacy.html` says browsing collects no tracking IDs; the site mints a persistent device identifier and stores a location list server-side with no TTL

`privacy.html:195` "no personal data, accounts, or **tracking IDs**"; `:428`
"almost certainly: nothing". Code: `index.html:12037-12044` mints and persists
`flightmap_device_token`; `favourites/app.py:14-16` — "**the header is the
partition key**"; the table has **no TTL**. `SECURITY.md:129`'s deletion
workflow covers signups, the APIGW key and CloudWatch — **not favourites**.

### I9 — `?methodology=` is documented as a stability guarantee and **sold as an Enterprise feature**; the parameter does not exist

`openapi.yaml:426-438` promises 14-day version pinning; `pricing.html:254` and
`api/index.html:339` sell it. Live: `?methodology=3.9`, `3.8`, `3.2` and the
nonsense `9.9` all return `methodologyVersion 4.0`. `METHODOLOGY.md:1945`
already retracted this on 2026-08-04 — the spec cites §16 as its authority for
a claim §16 was rewritten to withdraw.

### I10 — Preflight's runner converts "I could not check" into PASS

`scripts/preflight.sh:71-83` — `check()` shows output only on failure, so three
gates that deliberately distinguish unverified from verified are erased:
`check_openapi_matches_engine.py` returns **0** when PyYAML is absent (proven:
prints `PASS`); `tests/demo-key-scope.mjs` exits 0 whenever `unproven` is
non-empty, and `SKY_SCORE_FREE_TIER_KEY` is unset locally, so **the deny the
file itself calls load-bearing has never executed**; `check_quiet_estimate_error.py`
returns 0 on INCONCLUSIVE into `advise()`, which discards stdout.

### I11 — The legend's disclosure control renders at **1.04:1** at every landscape phone size, and is the only thing visible in the legend there

`.legend-toggle { color: var(--dark) }` (`index.html:585`) against the dark pill
set in `@media (max-width: 900px) and (max-height: 500px)` (`:2848`). The
`color: var(--white)` correction lives in `@media (max-width: 480px)` (`:2713`),
which landscape phones do not match. `rgb(20,20,20)` on `rgb(25,25,25)`, 11px.

**No contrast measurement has ever run at a landscape viewport** —
`a11y-source.mjs` and `panel-contrast.mjs` both run 1440×900 and 390×844 only.
`responsive.mjs` gained the landscape viewports on 2026-08-31 but measures
geometry. Fourth instance of a mobile rule keyed on width where height is the
failing dimension.

### I12 — The layers popover covers its own trigger at every landscape phone size, and Escape does not close it

`elementFromPoint` at the trigger centre returns `button.layer-toggle` at
568×320, 667×375, 844×390 and 896×414; a second click does not close it and
`Escape` does not either. The only exit is a click on the map, which selects a
borough as a side effect. Keyboard users are unaffected. `responsive.mjs`'s
`covered` detector is correct and has simply never been pointed at this state —
its `prepare: 'legend'` clicks `[data-layer]` in JS and never opens the popover.

### I13 — `site == Lambda (91 boroughs)` passes on 61

`tests/borough-score-parity.mjs:143` — `if (compared < 60)`. There is no floor
on `shared.length`, so Manchester (10) + West Midlands (7) + Leicester (8) +
Teesside (5) could all vanish from `CITY_DATA` and it would still print
"PASS: the site and the Lambda agree on every borough" — the one-way-door
guarantee.

### I14 — `panel-caveat.mjs`'s not-found sentinel is a pass token

`tests/panel-caveat.mjs:83-98` — when the row is not found, `text = '(no
environment row)'`, which yields `hasUndef=false, hasCaveat=false, named=true`.
Three of the four checks go green having rendered nothing. The row is located by
the literal copy string `/Air quality, road noise and flood risk/`; reword that
sentence and the only gate that has ever opened the borough panel stops checking.

### I15 — An unauthenticated 500 on `/badge` via path injection, defeating the badge's own documented contract — **VERIFIED**

```
postcode=../outcodes/SW11  -> 500   Content-Type: application/json
postcode=../outcodes/M1    -> 500
postcode=A/B               -> 404      (so it is not "any slash")
postcode=SW1A1AA           -> 200
```

`quote()` defaults to `safe='/'`, so `..` and `/` survive into a **path segment**
on postcodes.io (`app.py:6226`), reaching an outcode endpoint whose payload has a
different shape and crashing on an unhashable key. `handle_badge`'s docstring
says an unresolvable postcode must return a **badge**, never an error, "because a
404 renders as exactly that broken image" on a customer's page. Bounded SSRF —
host-locked, no scheme or host control. **Fix:** validate against `^[A-Z0-9]{5,7}$`
before the value reaches a URL.

### I16 — `build_borough_bands.py` writes one borough's values into another's record

`:806-815` uses a single substring pass whose comment claims it is "the SAME
containment rule the frontend's `getExtraData()` uses". It is not:
`index.html:9481-9487` was fixed to exact-match-first **because**
`'north west leicestershire'.includes('leicester')` served the wrong record live.
The builder still has the pre-fix version, and the builder is the half that
**writes**. Finder-proven on a scratchpad copy: two scored fields on Leicester
overwritten, reported under a different borough's name. Latent today.

### I17 — Further gate gaps (finder-evidenced, not re-verified here)

- **`--check` in the bands builder never iterates the holder**, so NYC's 5
  borough records are compared by nothing, permanently; `holder_only` is counted,
  printed, and never appended to `diffs`.
- **`roadNoiseCoverage` cannot report under-coverage** — all 86 published values
  are exactly `100.0`; `surveyed` is derived from a rectangle index test and the
  declared nodata never occurs in the file.
- **The published estimator accuracy is guarded by a bound, not the figure**:
  `api/index.html` publishes MAE 1.879 / median 1.5 / p90 4.2; preflight asserts
  only `MAE ≤ 2.2` on a 3,000 sample, never median or p90.
- **Orphaned gates:** `tests/changes-why.mjs` is in no runner; `tests/pwa-check.mjs`
  is referenced only from the Makefile, and `make` is not on PATH here.
- **`--check --write-lambda` writes `app.py`** while nominally read-only
  (`build_borough_bands.py:1081`).

### I18 — Further published-claim drift (finder-evidenced)

- `?weights=` invalid input is documented as a silent fallback in two places;
  the API returns **400**. The one documented behaviour that breaks a client.
- The `coverage` object — which carries every measurement caveat — is
  documented nowhere in the spec.
- The spec and `METHODOLOGY.md` §4.6 both say the DEFRA raster tier is
  **quarantined and not returned**; `RASTER_TIER_QUARANTINED = False` and
  SW11 1AA returns `quietResolution: "raster"`.
- `environmentSingleInput`'s mandated mitigation **can never fire** — with
  `_ENV_MIN_FIELDS = 2`, one input means `env` is omitted entirely.
- `/v1/regions` is documented as key-gated with a 403; it answers **200 with no
  key**, and `status.html` renders it as "no key required" — two Sky Score
  surfaces telling one prospect opposite things.
- `/v1/chat` is denied to **every** self-service key (`RateLimit: 0` on
  `ScoreFreeUsagePlan`, proven live) while `README.md:120` advertises it as one
  of the three key-gated routes a customer can reach.
- `LICENSING.md` omits five datasets in live use (US DOT NTAD, FEMA NFHL, US EPA,
  NYPD-derived crime, curated NYC prices), still credits **TfL** for the
  transport sub-score two rows below the NaPTAN row that replaced it, and never
  emits HMLR's or NSPL's required wording — which the project already holds, in
  the docstring of the script that generates the medians.
- `privacy.html` says postcodes.io is a native-app-only lookup; it is called on
  every web search and every autocomplete keystroke. `SUBPROCESSORS.md` recorded
  this exact correction on 2026-08-03; the notice a data subject reads was not
  updated.
- `PROJECT_DOCUMENTATION.md` describes `/v1/chat` as removed, and is stale on
  every headline fact (33 boroughs, v3.1, 7 functions, four factors, TfL PTAL).

---

## 4. Minor — a selection

- **`index.html` ships 894,230 bytes and 30% of it is comments** (271,682 B).
  First borough path at **7.7 s** on a throttled 1.6 Mbps connection. It is
  served with **no `Cache-Control` header at all**. CLAUDE.md says "~8,200
  lines"; it is **14,120**.
- **Four public pages are permanently dark and never declare `color-scheme`**
  (`pricing`, `changes`, `api/`, `score-demo/*`). The 99 area pages do. The
  lesson reached the generated pages and not the hand-written ones.
- **The extension panel is branded "cubitt33"** — one visible title and three
  accessible names — against the project rule of "always Sky Score in
  public-facing UI text". It renders on Rightmove.
- **`#country-selector` is a `role="tablist"` with no tab panels** and no
  arrow-key navigation, while the sibling `.tab-bar` in the same file implements
  the pattern correctly.
- **Ten locator-inset markers are focusable at 5×5 CSS px**, occupying tab stops
  14-23 of 51 on desktop.
- **`status.html` reports `/v1/score` "Up" on a 403** from five minutes after
  load, and renders its own two data rows as a bare `", "`.
- **`changes.html:441`** hard-codes "growth was responsible for 87% of last
  quarter's movement" beside a table in which growth carries weight 0.0.
- **`.well-known/security.txt:13`** points `Policy:` at `LICENSING.md` — RFC 9116
  `Policy` is the vulnerability-disclosure policy, which lives in `SECURITY.md`.
- **`npm audit`: 3 advisories**, all transitive dev-only; nothing from
  `node_modules` ships.
- **A live-format EPC key and account email remain in public git history** at
  `7eb1984`. The legacy host now 301s so the key is very likely dead; the repo
  is confirmed public.
- **`Math.random()` fallback** for the device token, the only authorisation the
  favourites table has (`index.html:12043`). `crypto.getRandomValues` is a
  one-line swap.

### Minor list re-measured 2026-09-08 — most of it was already closed

**Read this before working any item above.** The list was written on 7 Sep and
several entries were closed by the second wave later the same day, so it has
been describing finished work as outstanding. Each line below was checked
against the code, not against a changelog.

| Item | State |
|---|---|
| `security.txt` `Policy:` → LICENSING | **Closed** — points at `SECURITY.md` |
| `Math.random()` device token | **Closed** — `crypto.getRandomValues` |
| `changes.html` hard-coded 87% | **Closed** — reframed as a historical measurement |
| `status.html` reports "Up" on a 403 | **Closed**, both halves — reports UNVERIFIED, and the bare `", "` is gone: `methodologyVersion`/`apiVersion` render `'not reported'`, guarded on the FIELD rather than the response, because a keyless 403 body carries neither. (This row said the second half "was NOT reproduced and needs re-checking"; it was re-checked on 8 Sep and is closed.) |
| Extension branded "cubitt33" | **Closed** — every visible string and accessible name reads "Sky Score"; what remains is internal DOM ids (`cubitt33-panel`) and code comments, which are not public-facing UI text |
| `#country-selector` tablist with no panels | **Closed 2026-09-08** — now `role="group"` + `aria-pressed`, matching the city chips. Gated by `tablist-has-panels` in `a11y-source.mjs`, proven red |
| Ten locator markers focusable at 5×5 px | **Closed 2026-09-08** — click-only, out of the tab order. Gated by `locator-verify.mjs`, proven red at `focusable=10` |
| `npm audit`: 3 advisories | **Corrected** — `npm audit --omit=dev` reports **0 vulnerabilities**. The 3 are dev-only, which the entry itself said; the headline number was the production-facing read |
| Four pages never declare `color-scheme` | **Closed 2026-09-08.** Five pages already declared it; `score-demo/api-docs.html` did not, and was missed because **the finding said "four pages" when it was five** — the count, not the fix, was the thing that was wrong |
| `index.html` size and headers | **Header closed 2026-09-08**, payload still open. Verified live that the origin returned `Content-Type` and **no `Cache-Control` at all**, so browsers applied heuristic freshness and could pin the whole app shell — unreachable by a CloudFront invalidation *or* an `sw.js` bump, which is the `borough-extra.json` defect on the shell. Now `no-cache` (revalidate, not "don't store"), guarded at the ORIGIN by `check_deploy_drift.sh`, which a hash comparison could never see. The "~8,200 lines" claim is corrected to a measured **14,390 lines / 926 KB**; the 30%-comment payload is genuinely open |
| EPC key in public git history at `7eb1984` | **Open, and unfixable in place** — history is immutable without a rewrite of a public repo. The legacy host 301s, so the key is very likely dead; the decision is whether to rotate-and-document or rewrite |

*Two of these were closed by the commit that published the list naming them.
The pattern is the one recorded at the top of §1: an item has to leave the open
list in the commit that closes it, or it is rediscovered as work.*

#### NEW, 2026-09-08: a blocking gate's fixed clock had drifted under the real latency

**`UK cities get UK panel content` went red on a defect-free tree**, reporting
`transport panel reads "Loading from TfL API..."` — which reads as a broken
panel rather than a slow one, and sends the reader hunting inside the panel.

`tests/uk-city-panel.mjs` waited `waitForTimeout(6000)` under a comment reading
*"6s is what the slowest of those needs from a cold container"*. Measured that
day: **`/transport` alone answered HTTP 200 in 6.16 s** — it makes **two** TfL
calls, **unregistered**, behind a cold Lambda. The comment was true when
written and nothing could show it stale.

**Fifth instance of a blocking gate riding on a live third party's latency**,
and simultaneously an instance of a justifying number expiring. Fixed the way
`panel-contrast.mjs` was on 2026-09-01: a short settle so the fetches start and
paint their spinners, then **poll for the terminal state**, bounded at 25 s.
Terminal means "no longer fetching", not "succeeded", so an error state still
reaches the assertions and fails there with its own message. **Proven red**: with
the poll given no time, all four cities still fail on the loading panel, so the
bound cannot mask what the stage exists to catch.

#### NEW, 2026-09-08: a live-pointed gate reported PASS on a tree it contradicts

**`Playwright e2e` runs against the LIVE site, so it green-lit a source tree
whose contract its own assertions denied.** When `#country-selector` moved from
`aria-selected` to `aria-pressed` in source, `tests/e2e/city-switch.spec.js`
kept passing - it was still reading the previously-deployed `index.html`. A
full preflight reported **43 of 43** on that tree. The stage only went red
after the deploy made the site match the source, at which point the *test* was
the stale artefact.

This is the documented live-vs-source hazard **running backwards**. The known
direction - a live-pointed gate going red on a tree that has already fixed the
defect - is why `responsive` and `a11y` were each split into a blocking
source-pointed half and an advisory live one. The inverse is worse, because a
false red is investigated and a false green is not.

`tests/city-switch.mjs` is the source-pointed sibling and passed legitimately:
it asserts rendering and outline counts, not ARIA, so it could not have caught
this either. **No gate reads the working tree's ARIA contract for the
switcher.** Recorded rather than fixed - giving this spec a source-pointed twin
duplicates a suite, and the cheaper habit is the one now written at the top of
the spec: when changing an attribute the frontend publishes, grep
`tests/e2e/` as well as `tests/*.mjs`.

#### NEW, and it needs a decision: `AXE_TAGS` has no `wcag22aa`

**Nothing in this repo has ever run a WCAG 2.2 rule.** `AXE_TAGS` in
`tests/a11y-source.mjs` is `['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa',
'best-practice']`, and axe tags `target-size` — the rule for the locator defect
above — as **`wcag22aa`**. So the gate did not weigh those ten 5.2 px targets
and pass them; it never evaluated them. That is the identical mechanism the
same file already documents for `FAIL_MODERATE`: *"a rule that does not run
cannot fail"*, one tag along.

`target-size` is not the only 2.2 rule, and the level-AA additions in 2.2 are
the kind that fire on real UI (target size, focus appearance, dragging
movements). **Deliberately NOT added here as a side effect of this fix** — the
comment beside `AXE_TAGS` warns in terms against exactly that, and promoting an
unknown number of new rules to blocking across 109 pages is a scope change that
should be chosen rather than inherited.

**The decision is whether Sky Score claims WCAG 2.2 AA or 2.1 AA.** The public
pages make no version claim today, so either is defensible.

**SIZED 2026-09-08.** `wcag22aa` is now in `AXE_TAGS` (rules run) and not in
`WCAG_TAGS` (nothing 2.2-only blocks). Across all 134 scanned page-states the
whole backlog is **1 rule, 16 nodes, 1 state**: `target-size`, every node on
**`/score-demo/api-docs.html`** — the vendored Swagger UI. Nothing else in 2.2
fires anywhere, including the 99 area pages and the borough panel. So the
question is not "audit the product for 2.2" but "override vendored Swagger UI
CSS, or scope the claim to exclude the embedded API reference". See ROADMAP,
"Open decisions".

---

## 5. Method, and what to distrust

Each finder was told to prove by execution, to state plainly where it could not,
and that finders here overstate. All five did mark unexercised claims.

**Re-verified by hand in-session (17):** C1-C8 above, plus I1, I2, I3, I4, I5,
I6, I15, the `apigateway:GET` half of C3, and the public-repository claim.
Verification was by reading the policy JSON, running the derivation, driving the
page with Playwright, or calling the live API — never by reading a document.

**Not verified here:** everything in §3 marked finder-evidenced, and all of §4.
Two specific cautions:

- The **Nottingham transport band change** (I1, `live 5.3 → 4.5`) is a finder
  measurement over a full NSPL scan. It is the single claim in this report that
  changes a published score, and it should be re-derived before it is acted on.
- The **IAM escalation (C3) was deliberately not exercised.** It is a path read
  off the policy document, confirmed to be the live policy by a prefix-scope
  probe, not a demonstrated compromise.

**One question the frontend finder could not settle by measurement:** the map's
`path.borough` elements carry no `role`, `tabindex` or `aria-label`, so borough
selection is mouse-only. Whether that is a WCAG 2.1.1 failure turns on whether
the search box is an equivalent route to every borough. It appears to be, so it
is not raised as a finding.

---

## 6. Checked and found sound

Recorded so this ground is not re-audited.

**Security.** `/badge` XSS escaping is correct (`<script>` renders as
`&lt;SCRIPT&gt;` in both `aria-label` and `<title>`). Every third-party renderer
in `index.html` routes through `escapeHtml`/`safeUrl`, which rejects
`javascript:`. `/nhs` and `/transport` range-check `lat`/`lon` before URL
construction; `/epc` and `/sold-prices` use query-position quoting. The
favourites IDOR is genuinely closed — the device token *is* the partition key.
`.env` and `backend/samconfig.toml` were never committed. No `eval`,
`os.system` or `shell=True` anywhere. The extension carries no `innerHTML` sink.

**Contracts.** Free-tier quota (10,000/month, batch denied) agrees across all
ten stating surfaces and live AWS, and the per-method `RateLimit: 0` deny was
proven live for both the free and demo keys. Batch cap 100 agreed everywhere and
proven. No duplicate `MethodSettings`; the live stage is byte-identical to the
template across 15 entries. All Lambda timeouts ≤28 s, under the 29 s cap. All
four city enums and all three persona enums in `openapi.yaml` are complete. NYC
area pages carry no UK Crown-copyright credits. All 99 baked area-page scores
match the live API. Nine live B2B pages are byte-identical to source.

**Frontend.** The 99 `area/` pages are in no responsive gate — run here across
**495 page/viewport combinations, 0 failing**. The 8 non-homepage public pages
get only 5 portrait widths in `responsive.mjs` — run here at 6 more each,
**54 combinations, 0 failing**. The borough panel at four viewports
`panel-contrast.mjs` never uses: **0 nodes below AA**. Tab-order walks at three
viewports: no unnamed control, no keyboard trap, no missing focus ring.
`.tab-bar` implements the tablist pattern correctly. Map legend titles track the
city correctly on a UK→USA switch.

**Data.** `build_city_neighbourhoods.py --check` crosses the source boundary
with a per-city 95% share floor — 481 of 481 medians reproduce, 9 of 9 cities at
100%. The PPD cache is clean (932,678 rows, all `record_status: A`, zero
duplicate transaction ids). `measure_aircraft_footprint.py --verify` is green
over 48 boroughs. `AIRPORT_NOISE_SCALE` was independently re-derived from the
on-disk GeoTIFFs and all 12 values are exactly `sqrt(area≥55 dB / Heathrow's)` —
correct, but re-derived by no script, so a Round 5 roll would leave them stale.
`check_no_em_dash.sh` and `check_api_url_drift.sh` both carry real per-file
floors. `backend/tests`: 374 passed, 152 subtests.
