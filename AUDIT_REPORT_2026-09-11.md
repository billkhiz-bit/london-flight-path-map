# Audit Report — Sky Score

**Date:** 2026-09-11
**Scope:** full codebase — backend Lambdas + scripts, frontend, and a dedicated
docs-vs-code drift pass.
**Method:** three parallel agents, every finding then re-verified in-session
before it was written down. Verification status is marked on every row; nothing
here is a suspicion.

> **This file does not replace `AUDIT_REPORT.md`.** The 2026-09-07 report is
> still the live list and was not overwritten — Bill was away, and overwriting a
> generated report without confirmation is what the global safety rule forbids.
> Rotate on return if you want: copy `AUDIT_REPORT.md` to
> `AUDIT_REPORT_2026-09-07.md` and promote this one, matching the convention
> already used for the 08-21 and 08-29 archives.

---

## Verification key

- **[V]** — verified by me, in this session, by reading the code or running it.
- **[A]** — the finding agent reported verifying it by execution; I did not
  independently re-run it. Strong, but not confirmed.
- **[U]** — reported, not verified by anyone. Listed so it is not lost.

---

## FIXED IN THIS SESSION (2026-09-11)

| # | What | Proof |
|---|---|---|
| **F1** | **53 of 91 boroughs rendered the literal word `undefined` in the borough detail panel**, including `UNDEFINED` in the *worst* rating colour under CRIME | Gate proven red on the pre-fix tree, green after |
| **F2** | `tests/panel-caveat.mjs` rendered the whole panel and asserted `undefined` against **one row** of it | Widened to the whole panel; red-proven |
| **F3** | `build_progress8.py --check` could print `RESULT: PASS` having compared **zero** values against DfE | Red-proven: now `Compared 0 / FAIL / exit 1` |
| **F4** | `scripts/score_bulk.py` omitted `env`, so Enterprise CSV rows could not reproduce their own `score` | Worked example closes from 4.3 to 5.0 against a published 5.0 |

### F1 — the panel printed `undefined` on every borough outside London and NYC **[V]**

`index.html:11770, :11780, :11790, :11800`. Four unguarded interpolations in
`updateSidebar()`: `data.note`, `data.property`, `extra.crime`,
`extra.schoolNote`. Their siblings in the same block (`extra.crimeRate`,
`extra.name`, `crimeNote()`, `schoolBadge().text`) all go through
`escapeHtml()`; these four did not.

**Measured independently of the agent:** `crime` and `schoolNote` exist on
exactly **38 of 91** borough records — London's 33 plus NYC's 5 — so **53**
boroughs rendered the literal word. `ratingBadgeClass(undefined)` lowercases to
`''`, matches neither branch, and returns **`rating-high`**, so the CRIME badge
read `UNDEFINED` in the same ink the app uses for the worst crime, directly above
a correct rate.

**This is the 2026-08-11 defect, in the four siblings that fix did not reach.**
`buildOptionalSections()` was made fully conditional that day and carries a
comment explaining exactly this failure mode; the four fields 1,800 lines below
were never revisited. Mirror drift, one function apart.

**Fixed** with the same idiom the repaired sibling uses — omit the element rather
than print a placeholder — plus `escapeHtml()` on all four.

### F2 — the gate that exists for this rendered it every run and never looked **[V]**

`tests/panel-caveat.mjs` calls `updateSidebar(d)`, so the whole panel has been in
the DOM on every run since the file was written. It then narrowed to
`row.textContent` of the single `.score-explain` row matching the Environment
copy string, and tested `undefined` against **that**. The word was present four
times elsewhere in the same rendered panel, on the Teesside borough the file
already uses as a subject.

**Rendering a surface is not asserting it.** The caveat checks stay scoped to the
row; `undefined` is now asked of `#sidebar-content` entire. Proven red on the
pre-fix tree (Middlesbrough `undefined=true` twice) and green after.

### F3 — the Progress 8 gate could pass having compared nothing **[V]**

`scripts/build_progress8.py`. `compared += len(with_p8)` counted **registry**
rows, before `for_city()` ran. `diffs` is filtered by `if n in got`, and `absent`
— boroughs we publish a p8 for that DfE does not list — was printed and **never
added to `bad`**. So a DfE side resolving nothing gave `diffs=[]`, `bad=0`,
`compared=79`, `RESULT: PASS`, exit 0.

That is precisely the schema drift this repo hit **twice in September** (DfE
`gender` → `sex`; NSPL `lad25cd` → `lad26cd`). p8 is 0.35 of `live` on 79
boroughs and this is its only cross-source check. The stage is `advise`, which
sends all output to `/dev/null`, so the exit code is the only signal and it did
not carry this.

**Fixed:** `compared` counts actual matches; an uncorroborated published value
counts as a failure. Measured first — `absent` is **0 across all 11 cities**
today, so this cannot fire on current data. Red-proven with `for_city()` stubbed:
`Compared 0 / FAIL / exit 1`.

### F4 — the Enterprise bulk CSV could not reproduce its own score column **[V]**

`scripts/score_bulk.py`. `OUTPUT_COLUMNS` published `quiet/afford/growth/live`
under a comment calling them "the four components calc_score actually returns" —
true when written, false since methodology **v3.9** (2026-08-26). Every `env`
match in the file was `os.environ`.

A customer summing published components against published weights missed the
published `score`. On METHODOLOGY §6's own worked example (SW11 1AA): with `env`,
`6.4(.32) + 0.4(.27) + 7.8(.27) + 5.6(.14)` = 5.046 → **5.0**, matching. Without
it, 4.262 → **4.3** against a published **5.0**.

The file's own docstring states the consequence: *"A bulk CSV whose scores differ
from the API's, even slightly, is worse than no CSV."* **Fourth holder of this
drift** — `openapi.yaml` and `api/index.html` were fixed as F2/F3 on 2026-09-03,
the consumer site as I34 on 2026-09-01. This one was missed because nothing gates
it. `env` is written as an **empty cell**, never `0`, for the 9 boroughs below
the two-input floor — 0 is a real score on this scale.

---

## CRITICAL — open

### C0 — the public B2B demo has been returning `429` to prospects since 9 September, and our own gates drained it **[V]**

**Found by running the post-deploy verification, not by the audit agents.**

`GET /v1/score` with the demo key embedded in `score-demo/index.html` returns
**`429 Limit Exceeded`** (measured live 2026-09-11). `ScoreDemoUsagePlan` is
capped at **2,000/month** and API Gateway's own usage data shows it hit exactly
2,000 and stopped:

```
1 Sep 511 | 2 Sep 146 | 3 Sep 195 | 4 Sep 142 | 5-6 Sep  0 (weekend)
7 Sep 627 | 8 Sep 251 | 9 Sep 128 -> 0 remaining
```

**The cause is us.** `score-demo/status.html` probes `/v1/score` **twice on
load** (`runAllChecks()` at `:439`, plus a `setInterval` at `:443`) with that
demo key, and both `tests/a11y-source.mjs` and `tests/responsive.mjs` scan that
page — a11y at 3 viewports, responsive at 5. Measured after stubbing:
**responsive 10 requests per run, a11y 6**, about 16 per preflight run. At ~30
runs on a wave day that is ~480, matching the 511 and 627 spikes. Visitor
traffic does not take weekends off and does not spike on the days the gates ran
most.

**Third instance of `memory/feedback-gate-blocked-by-shared-quota.md`**, and
the worst of the three, because the first two turned a gate red and were noticed
within hours. This one left every gate green and broke only the thing no one
monitors: a B2B prospect opening the API tester.

**Fixed** (`tests/stub-live-api.mjs`): a `page.route()` URL predicate scoped to
`/v1/score` alone, with a hit counter asserted at the end of each run, because a
stub cannot report its own absence. Narrowed after a first version intercepted
the whole API host and answered `/v1/changes` with a score-shaped payload —
`changes.html` builds its entire body from that endpoint, so it rendered a
different page and `responsive` went red on a 2px overflow. *Answer too little
and you audit an error state; answer the wrong shape and you audit a wrong
state.*

**STILL OPEN and Bill's call: the quota resets on 1 October.** Until then the
public demo is down. Whether 2,000/month suits a public B2B tester is a product
and cost decision, not a defect — raising it is a `template.yaml` change and a
SAM deploy.


### C1 — `openapi.yaml` declares `/v1/regions` key-gated; production serves it open **[V]**

`score-demo/openapi.yaml`. The global default at `:55` is
`security: - ApiKeyAuth: []`. `/v1/signup` (`:66`) and `/v1/changes` (`:275`)
both override with `security: []`. **`/v1/regions` (`:208`) has no override**, so
the spec says it needs a key, and it declares a `403`.

**Measured live, 2026-09-11: `GET /v1/regions` returns HTTP 200 with no key.**
`backend/template.yaml` carries exactly four `ApiKeyRequired: true` entries —
`/v1/chat` POST (`:476`), `/v1/score` GET (`:525`), `/v1/score/batch` POST
(`:533`), `/v1/environment` OPTIONS (`:584`). `/v1/regions` is not among them.

This is the **last surviving copy** of a falsehood `CLAUDE.md` records being
corrected elsewhere on 2026-08-21 ("`template.yaml` and the `handle_regions`
docstring were corrected while THIS one was not"). The spec is the artefact
integrators generate clients from.

The blocking gate `check_openapi_matches_engine.py` **passes** — it compares
components, weights, context keys, sources, cities and personas, never auth.

**Fix:** add `security: []` to `/v1/regions`, drop its `403`, change "Two do not"
to three. **Then gate it** — see the recommendation at the end.

### C2 — the methodology version reads 3.7 / 4.0 / 5.0 across five surfaces **[V]**

Engine: `backend/lambdas/score/app.py:106` → `METHODOLOGY_VERSION = '5.0'`, and
every response carries `"methodologyVersion": "5.0"` (verified live).

| Surface | Says | Where |
|---|---|---|
| Consumer site footer | **"Methodology v3.7"** | `index.html:4204` |
| METHODOLOGY.md header | **"Version 4.0"** | `METHODOLOGY.md:3` |
| METHODOLOGY.md §12 | *"currently `4.0`"* | `METHODOLOGY.md:1897` |
| README badge | **"Methodology v4.0"** | `README.md:7` |
| LICENSING, describing the footer | **"Methodology v3.1"** | `LICENSING.md:133` |

The documents contradict *themselves*: `README.md:211` prints `"5.0"` in its
sample response, and METHODOLOGY §4.2 and Step 4 are both labelled v5.0 under a
header saying 4.0. The 99 area pages and `api/index.html:292` are correct.

METHODOLOGY.md is the document §16 names as the B2B contract reference and the
one the site footer links to. **An auditor lands on a page headed "Version 4.0"
describing an API that returns 5.0.** `sw.js` v1.0.9 records this exact footer
defect being fixed once before; nothing asserts the string, so it drifted again.

**Correct value: 5.0 on all five.**

### C3 — README says road noise is not scored, 29 lines after saying it is **[V]**

`README.md:43`: *"**Road noise remains reported and not scored**; it is scheduled
for the v4.0 noise composite."* `backend/lambdas/score/app.py:5571` →
`'roadNoise': 0.35` of `environment`, scored since v4.0 (2026-08-29) from
`roadNoiseAboveWhoPct`. `README.md:9`, in the **same blockquote**, says *"Air
quality, road noise and flood risk are all SCORED."* **Delete the sentence.**

### C4 — README claims a coverage figure is derived and "cannot disagree"; it is hardcoded and disagrees **[V]**

`README.md:56, :315`: *"all four are measured for **84 of 99** boroughs"*, with
`:319` asserting *"That figure is **counted through the Lambda's own
`live_resolution()`**, not recomputed here, **so it cannot disagree**"*.

**I ran `app.live_resolution()` over all 99 records:**

```
measured      79
partial       20   (16 at 3/4, 4 at 2/4)
unavailable    0
```

The 20 partials are every borough without Progress 8 — City of London, **all five
NYC boroughs**, Leicester's 7 county districts, Cardiff's 4, Nottingham's 3.
README's arithmetic (`:324`, "78 + 6 = 84") counts NYC's five as fully measured;
`live_resolution()` returns `partial — 3/4` for each, because `p8` is `None`.
README's two supporting counts are right (`p8` absent for exactly 20).

**Correct: 79 measured, 20 partial, 0 unavailable.** Worth singling out: *a claim
of derivation that is not one is the most expensive kind of stale number, because
it tells the next reader not to check.*

### C5 — OPERATIONS.md records the NSPL reload as ~6 h and blocked on an ungranted IAM action **[V]**

`OPERATIONS.md:587`: *"only once `dynamodb:BatchWriteItem` is applied to the live
policy (it is in `backend/iam-policy.json`, **not yet applied**) … **a ~6 h run
means the grant never landed**."*

**Reality:** `scripts/load_nspl.py:306` → `NSPL_VINTAGE = '2026-08'`; 2,704,825
rows loaded **2026-09-09 in 58 minutes** on the batch path.
`check_aws_permissions.py` reports 18 granted, 0 denied.

This is an operational runbook. Anyone planning the **November NSPL roll** from
it budgets six hours and a blocked prerequisite for an hour-long job with no
prerequisite. `OPERATIONS.md:590` compounds it ("saves ~13 hours").

---

## IMPORTANT — open

### I1 — Six deployed HTML pages ship with no `Cache-Control` header **[A]**

`/privacy`, `/terms`, `/pricing`, `/changes`, `/api/`, `/score-demo/index.html`.
`Makefile:117-126` added `--cache-control "no-cache"` to `index.html` on
2026-09-08, with a comment explaining that a bare header means heuristic
freshness and that **neither a CloudFront invalidation nor an `sw.js` bump can
reach the browser's HTTP cache**. The six `aws s3 cp` lines immediately below it
**in the same target** were not changed.

`/terms` and `/privacy` are the legal documents: a reader can be pinned to a
superseded version with no way for a deploy to dislodge it.

### I2 — `?weights=` serves a caveat that is false about affordability **[V]**

`backend/lambdas/score/app.py:683-686`. `build_why` builds `unweighted`
generically over **every** zero-weight component, then emits one hardcoded
sentence: *"… it is weighted only for the investor persona, because past price
growth describes the market rather than the property."*

Set `weights=afford:0.0` — a documented feature sold on `pricing.html` and
`api/index.html` — and Affordability gets that sentence. Both clauses are false
of it. With two zero-weight components the grammar also breaks: *"Affordability
and Growth moved … but **is** not counted"*.

### I3 — Saved-location rows: nested interactive, and Remove is unreachable by keyboard **[A]**

`index.html:12517` applies `makeKeyActivatable` (setting `role="button"`,
`tabindex="0"`) to `.fav-item`, which already contains a real
`<button class="fav-remove">`. axe reports `nested-interactive`. The container's
keydown handler calls `preventDefault()` and handles Enter/Space, both of which
bubble from the inner button — so pressing Enter on the × **switches city and
re-runs the search** instead of deleting. There is no keyboard route to delete a
saved location. Mouse is unaffected.

No gate ever renders a populated favourites list, so axe has never seen it.

### I4 — The score tooltip can never render, and the text screen readers get is wrong **[A]**

`index.html:294-296` uses the sibling combinator `~`, but trigger and tip do not
share a parent, so `:hover` / `:focus` can never match. `cursor: help`, a
`tabindex="0"` tab stop (the **first** inside the panel) and an Escape handler all
serve a popover that cannot appear.

The text is still delivered via `aria-describedby`, and it says **"five
components"** while listing four (Environment absent), and describes affordability
as *"cohort-relative (cheapest = 10)"* — the scale v5.0 deliberately deleted, 72
lines away. **A screen-reader user is the only audience for this text and is the
only one given the retired scale.**

### I5 — "Offence breakdown not published for this area" is false for 53 boroughs **[A]**

`index.html:9876` fires whenever `extra.crimeTop` is empty, which is every borough
outside London. ONS Table C4 **does** publish the breakdown for those rows —
`refresh_crime_from_ons.py:363` already reads those columns for every city to
compute medians; only `--write` is London-gated. The derivation is missing, not
the publication. This is the repo's own "absence must never render as a
measurement" rule, in a branch whose comment three lines above makes that
argument.

**Latent, same path:** if anyone runs `--write` for a non-London city,
`vsLondonMedian` is computed from *that city's* medians while `index.html:9863`
prints "x the London median".

### I6 — OPERATIONS.md's resource inventory omits a Lambda and a table **[V]**

`OPERATIONS.md:23` says **7 Lambdas** and omits `chat`; `:24` says **3 DynamoDB
tables** and omits `postcodes`. Measured: `backend/lambdas/` holds **8**
directories, `template.yaml` holds **8** `AWS::Serverless::Function` blocks and
**4** `AWS::DynamoDB::Table` blocks. Repeated at `:654`, `:760`, `:762`. The same
file already says "the four DynamoDB tables" at `:580`; the top-of-file inventory
— the first thing an operator reads — is the outlier.

### I7 — The 403-diagnosis runbook lists 5 of 14 throttles, omitting the three tightest **[A]**

`OPERATIONS.md:727-731` gives the stage ceiling plus four routes, "updated
2026-07-26". `template.yaml` declares **14** per-route entries; the nine added on
2026-09-07 are missing, including the three tightest limits in the API (`/nhs`
2/5, `/transport` 2/5, `/sold-prices` 3/6). This is the section headed "API
returning 403 unexpectedly", so the one lookup it exists for fails on the routes
most likely to trip.

### I8 — `env` is missing from the `coverage` object entirely **[A]**

`backend/lambdas/score/app.py:5974-5984` returns `quiet` and `live` only. `env` is
dropped for 9 of 99 boroughs and carries 0.14–0.18 of the score. A Cardiff
response publishes `context.environmentResolution: "unavailable — 1/3 inputs"`
while `coverage` says nothing. `coverage` is the one surface `filter_response`
refuses to let a caller strip, and `terms.html:294` obliges integrators to carry
it through.

### I9 — The liveability-unavailable notice can never fire, and its text is wrong **[A]**

`app.py:5971` tests `live_source == 'unavailable'` by exact equality, but
`live_resolution` has returned a full sentence since 2026-08-09. Across all 99
boroughs it fires **0 times**. Its text also still says the component *"is a
neutral placeholder rather than a measurement"* — false since v3.8, which omits
it. **Two tests pin the dead branch**: `test_score.py:2945-2956` calls
`build_coverage('raster', 'unavailable')` with the bare literal, so both pass
green on a branch production cannot enter.

### I10 — Counts that have drifted, all measured **[V]**

| Claim | Where | Measured |
|---|---|---|
| "485 postcode districts" | `METHODOLOGY.md:58,102`, `README.md:311`, `CLAUDE.md:372` | **481** (generated headers: 91+83+43+54+40+37+23+26+84) |
| "285 curated area labels" | `CLAUDE.md:505`, `METHODOLOGY.md:102`, `README.md:311`, `LICENSING.md:101` | **281** — the gate prints it: `OK: all 281 curated names corroborated` |
| `env` coverage "85 measured, 5 partial (Teesside)" | `CLAUDE.md:197` | **90 measured, 0 partial, 9 unavailable** — the `partial` tier is unreachable; CLAUDE.md says so itself 260 lines later |
| "HPI 2026-05" | `CLAUDE.md:103` | **2026-06** (`build_hpi_prices.py:58`; `SNAPSHOT_VINTAGE_LABEL = 'June 2026'`) |
| "roll to the August 2026 edition when it ships" | `CLAUDE.md:1199` | Done 2026-09-09; the block ~10 lines below is headed "THE 2026-08 ROLL IS COMPLETE" |
| "35,352 London postcodes DEFRA measured" | `api/index.html:258` (**B2B-facing**), `README.md:54` | **35,441** (`data/aircraft-quiet-london.json`, rebuilt `42f864d`) |
| "27 probes" | `CLAUDE.md:849` | **28** |
| "two viewports" in the a11y scan | `CLAUDE.md:849`, `a11y-source.mjs:150` comment | **three** — landscape added 2026-09-07 |
| "DEFRA full-UK extension … Outstanding" | `ROADMAP.md:553-554` | Shipped 2026-08-10/12 |
| README per-city table: aircraft "runway geometry only, not DEFRA" | `README.md:291` | Contradicted by `README.md:312`, 21 lines later |

---

## MINOR — open

Agent-reported, not individually re-verified **[A]** unless marked.

**Backend / scripts**

- `sold_prices/app.py:122` — `item.get('pricePaid', 0)` publishes a missing price
  as **£0**, two lines below a sibling that returns `''` "rather than a
  placeholder".
- `fetch_nhs_gp_practices.py:118` — `expected = int(headers.get('x-total-count')
  or 0)` makes the truncation floor a no-op if the header is renamed; feeds
  `healthcareWithin500mPct`, 0.10 of liveability. Under-fetching flatters the
  data.
- `check_openapi_matches_engine.py:103` — `require()` increments `checks` before
  computing the diff, so an empty expectation passes unconditionally while
  keeping the floor satisfied. Blocking gate.
- `load_defra_raster.py:644` — the checkpoint comment describes a fix the code
  does not implement (four `continue`s still bypass it); `:645` writes the
  checkpoint with up to 24 rows still buffered, where `load_nspl.py:1277` guards
  exactly this.
- `load_nspl.py:1176` — the 2026-09-10 connection-pool fix reached two of three
  loaders; this one still uses boto3's default pool of 10 against up to 20
  threads.
- `build_borough_bands.py:784` — air quality is the only derived band with no
  coverage gate; `sample_aq` computes `counts` for that purpose and it is never
  read. 0.45 of `environment`.
- `build_aircraft_bands.py:511` — `hits.get(name, 0.0)` turns a borough absent
  from the measurement file into a measured zero, skipping the near-field floor:
  the Rushcliffe defect re-entering through a `.get` default. Latent (48/48
  resolve today).
- `build_hpi_prices.py:550` — a non-London price roll prints a follow-up command
  that returns early for every city already in `index.html`, so no script updates
  the site's prices. Under v5.0's national pool a stale site price moves every
  borough.
- `chat/app.py:259` — upstream-outage errors returned as **400**, blaming the
  caller for a server-side failure.
- `signup/app.py:157` — `except ClientError: return None` with no log line, so a
  GetItem permission or throttle regression is invisible.
- `transport/app.py:132` — `stops[:8]` truncates **before** sorting by distance;
  `:133` renders a coordinate-less stop as ~5,500 km away.
- `check_worked_example.py:157` — `if real is None: continue` three lines below a
  comment condemning that opt-out; 17 checks against a floor of 15, so two can
  drop silently.
- `build_area_pages.py:485` — `--check` fails only on `if not pages`; a page below
  `MIN_FACTS` is collected and fails nothing.
- Several loaders lack the `--limit 0`, `written > 0` and renamed-`doterm` guards
  that `load_nspl.py` carries.

**Frontend**

- `score-demo/openapi.yaml:117-148` — free-tier schema still shows
  `monthlyQuota: 100`, `sustainedRateLimit: 1`, `batchMultiplier: 100`. Live:
  10,000 / 2 / none. `FreeTierQuotaDriftTests` lists this file but matches prose
  patterns only, so bare YAML `example:` scalars slip past — 13 tests pass
  against it.
- `score-demo/status.html:214` — comment says the demo key is on
  `SkyScoreFreeTier` at 1000/month; it is `ScoreDemoUsagePlan` at 2,000, which the
  same file states correctly at `:425`.
- `api/index.html:14, :21, :56-61` — the `<head>` still sells a four-component
  score and asserts "GDPR-compliant UK data residency (eu-west-2)" in JSON-LD,
  against `chat/app.py:43` `BEDROCK_REGION = 'us-east-1'`. The 2026-09-07 C1 fix
  enumerated five documents; this one was not among them.
- `privacy.html:431` — tells a data subject their browser "loads fonts … from
  US-hosted services". Fonts have been self-hosted since 2026-08-05 and the CSP is
  `font-src 'self'`; the paragraph points at a subprocessor row that no longer
  exists.
- `terms.html:303` — "Every API response includes a `sources` array".
  `/v1/environment` does not (it carries per-field source strings instead), and
  `/badge` returns SVG.
- `index.html:9017` — `renderSearchFailure()` writes `#sidebar-title` directly
  instead of via `setPanelSubject()`, so `document.title` keeps the previous
  subject after a failed lookup.
- `index.html:11086` — the `matchBorough()`-miss fallback passes
  `{impact:'unknown', avg_price:0, score:0}` and renders a 20%-wide **green**
  noise bar beside "UNKNOWN". Unreachable today; one renamed boundary away.

---

## Categories reported CLEAN

- **Service worker / `SHELL_ASSETS`** — all 20 precached paths 200 at the origin,
  every one has a Makefile target, and the atomic-`addAll` ordering
  (`fonts` → `data` → `pwa`) is respected. `/data/` and `/js/` are network-first
  with `cache: 'no-cache'`.
- **Dead code** — every module-level function in all 8 Lambdas and 36 scripts has
  a call site (AST extraction plus a repo-wide reference count).
- **Secrets in source** — none. `.env` gitignored, EPC token is a `NoEcho` SAM
  parameter.
- **Injection / `shell=True`** — none. `lookup_postcode`'s `[A-Z0-9]{1,8}` gate is
  the single funnel; `/nhs`, `/transport` and `/v1/environment` range-check
  coordinates.
- **Unauthenticated routes lacking throttles** — all twelve carry per-method
  `MethodSettings`.
- **a11y beyond the existing gates** — axe run over five previously-uncovered
  states (expanded metric details, score-tip focused, autocomplete open, layers
  popover open, ranking tab) returned **0 critical/serious** in all five.

---

## The pattern, and what to do about it

**Four of the five open criticals are one mechanism:** a version or scope bumped
in the code, with one of its mirrors left behind. `/v1/regions` auth (fixed in
`template.yaml` 2026-08-21, never in the spec), the methodology version (bumped
four times, three surfaces frozen), road noise scored at v4.0 (README's summary
frozen), the BatchWriteItem grant (applied 2026-09-04, OPERATIONS frozen). All
four fixes made this session were the same shape.

Two are cheaply gateable, and both gates exist in adjacent form already:

1. **`check_openapi_matches_engine.py` should compare auth**, not just shape. It
   already derives personas, cities, components and weights from the engine. One
   assertion — *every path whose SAM event lacks `ApiKeyRequired: true` must carry
   `security: []`* — closes C1 permanently.
2. **`METHODOLOGY_VERSION` should be asserted against the strings that quote
   it** — `METHODOLOGY.md:3`, `METHODOLOGY.md:1897`, `README.md:7`,
   `index.html:4204`. The pattern is proven by
   `test_the_published_residual_figure_does_not_understate_reality`, which already
   reads two documents and fails on drift.

**States with zero gate coverage**, ranked by surface carried: the persona
selector (8 buttons, nothing clicks one), `#tab-favourites` contents (I3 lives
there), `toggleMetricDetail()` expanded, `renderScoreTip()` (I4 lives there),
`wireNotifyForm()`, `boroughDataNotice()`, the NOT FOUND search branch, and web
`data-mview` switching. Four `.mjs` files are in no runner at all (`loadtest`,
`rehearse`, `api.test`, `store-screenshots`).

---

## Summary

- **Fixed this session: 5** (1 critical live user-visible, 2 gate-integrity, 1 B2B deliverable, and the demo-quota drain in C0)
- **Critical open: 5** — plus C0, whose CAUSE is fixed but whose quota does not reset until 1 October
- **Important open: 10**
- **Minor open: ~21**

None of the open items needs a deploy to be made safe; all are source or document
changes. The two gate recommendations above are the highest-leverage work, and
both close a class rather than an instance.
