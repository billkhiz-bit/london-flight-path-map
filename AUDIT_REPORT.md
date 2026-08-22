# Audit Report — Sky Score

**Date:** 2026-08-21
**Previous full audit:** 2026-08-12 (`AUDIT_REPORT_2026-08-12.md`)
**Method:** three parallel agents (code quality, security, frontend/a11y), then
**independent verification of every Critical finding against primary sources** —
the live API, the live TfL upstream, `git show` of the relevant commit, or
execution of the code. Agent findings I could not reproduce are recorded in §6
rather than dropped.

---

## Summary

| | Count |
|---|---|
| Critical | 11 — **all 11 closed 2026-08-21**, deployed and verified live |
| Important | 14 |
| Minor | 12 |

**One defect class accounts for 8 of the 11 criticals**, and it is the one this
repo has been recording since June: **an absence rendering as a confident
measurement, guarded by a check that reads the absence as agreement.**
`return []`, `points_within → 0.0`, `.get(band, 0)`, `if new is None: continue`,
a transparent PNG classified as "no risk", `currentCity === 'london' ? … : …`.
Every one sits beside a comment describing the trap.

**The highest-leverage single change is a per-unit floor on every `--check`:
comparing zero fields must be a failure, not a pass.** Three gates currently pass
while comparing nothing, one of them blocking.

---

## 1. Critical — fixed today

**All five are deployed and verified live** (2026-08-21 17:26). `ScoreFunction`
and `TransportFunction` updated via SAM; `index.html` and `api/index.html`
uploaded and CloudFront invalidated. Verification was against the origin, not the
deploy's exit code: both HTML files match source by sha256, `/v1/environment` at
M22 5RX now returns `2.0`, and `/transport` at Oxford Circus returns **6 line
statuses including Victoria "Severe Delays" and Central "Minor Delays"** - the
exact disruptions that had been rendering as "no disruptions".

| # | Issue | File | Verified by |
|---|---|---|---|
| C1 | `/v1/environment` scored every UK coordinate with **London's** geometry | `backend/lambdas/score/app.py` | Live: M22 5RX returned `10.0` vs Manchester's `2.0` |
| C2 | Road Lden had a floor, no ceiling — `+3.4e38` published as decibels | `backend/lambdas/score/app.py:3901` | Executed at HEAD: returned `3.4e+38` |
| C3 | **`/transport` has never returned a line status** | `backend/lambdas/transport/app.py:136` | Live + causation proven against TfL |
| C4 | Ten cities promised `data.police.uk` crime data that no code fetches | `index.html` ×10 | 10 strings, 0 fetches, absent from CSP |
| C5 | `api/index.html` labelled a v3.5 payload "verbatim from the live API" | `api/index.html:254` | `git show`: the API returned **3.5** on 4 Aug |

### C1 — the London-geometry hardcode
Full detail in `AUDIT_REPORT_2026-08-12.md` §A-0812-U1. Headline: **291 of 291
changed postcodes moved louder, zero quieter**, over a 6,000-postcode NSPL
sample. Structural rather than incidental — every term in `calc_postcode_quiet`
is distance-gated, so a geometry lacking your airport cannot over-report.

### C3 — `/transport` line status, dead since it shipped
`fetch_line_status` sent `headers={'Accept': 'application/json'}`.
`fetch_nearby_stations`, **eleven lines above**, has always sent a `User-Agent`.
TfL 403s urllib's default `Python-urllib/3.x`; the 403 is caught and returned as
`[]`; the handler still reports `available: true`.

```
Live, Oxford Circus:      5 stations, lineStatus: 0 entries
TfL /Line/.../Status      {'Accept'}               -> HTTP 403 Forbidden
                          {'Accept','User-Agent'}  -> HTTP 200, 4041 bytes
```

**A suspended Central line renders as "no disruptions."** Third instance of one
header being the entire difference, after the DEFRA host and the mirrored-pair
shape of C2.

**The test could not see it, and my first fix did not make it able to.**
`test_success_response` asserted `"lineStatus" in body` — which `[]` satisfies.
Teaching the mock to raise 403 left the suite green. The assertion is now
`len(body["lineStatus"]) > 0`, proven red by reverting **only** the
`Line/Status` header. *Assert on data, not shape* — the `/sold-prices` lesson,
recurring.

---

## 2. Critical — CLOSED 2026-08-21 (C6, C7, C8) and open (C9-C11)

**C6, C7 and C8 are fixed, deployed and verified live.**

- **C6/C7** — `ScoreDemoUsagePlan` now carries a per-method `Throttle` map with
  `RateLimit: 0` on `/v1/chat/POST` and `/v1/score/batch/POST`. Whether API
  Gateway reads 0 as *deny* or as *unlimited* could not be settled from the
  template, so `tests/demo-key-scope.mjs` asks the running API: **red on both
  routes before the deploy, green after** (429/429), with `GET /v1/score` still
  returning a real score. Blocking in preflight, and it spends **no demo quota**
  in the normal case because a throttled request is never metered.
  The status page's batch probe was removed rather than repaired — a public page
  cannot hold a key entitled to batch.
- **C8** — the panel branch is three ways and reads `country` from the registry
  rather than naming cities. UK cities get NaPTAN stations, EPC and sold prices;
  NYC keeps its own copy. The NaPTAN render moved into one holder, which is what
  made the 1,771 stations reachable. **NHS stays London-only deliberately** —
  I3 flags it for no reserved concurrency behind a 45 s timeout against APIGW's
  29 s cap, and widening a faulty route to nine more cities makes the fault
  likelier. `tests/uk-city-panel.mjs` types a real postcode in a non-London city,
  which nothing had ever done; proven red (6 failures with the branch reverted).
  It also closed a defect nobody had listed: nine UK cities rendered the
  sold-prices container from `buildPropertyLinks()` while the fetch was
  London-gated, so they sat on **"Loading from Land Registry..." forever**.

---

## 2a. Critical — ALL CLOSED 2026-08-21

C9, C10 and C11 are fixed, deployed and verified live. Every critical in this
report is now closed. Summary before the detail:

| # | Fixed by | Guard, and how it was proven |
|---|---|---|
| C9 | The aircraft layer joins `markLayerCoverage()`, and the decibel scale is **hidden** rather than relabelled | `layer-honesty.mjs` measures whether an image is present and whether the scale is visible, on **both** sides. It found two bugs in the fix itself, in opposite directions |
| C10 | `points_within()` returns `None` for an EMPTY index; both loaders refuse a zero-row read | `test_empty_source_guards.py`, proven red. A populated index with nothing nearby still returns `0.0` — that distinction is the point |
| C11 | A tile classifying 100% code 0 is retried and never cached | Same file, proven red |

**Why C9's gate mattered more than C9's fix.** The first version of the fix
carried two lifecycle faults: West Midlands inherited New York's `true` because
the flag outlived the city switch — and it is the city selected immediately
after NYC, so every other city passed — and then NYC rendered a hidden scale
over its own painted tiles, because the legend is drawn before
`updateDefraTiles()` runs. A gate reading `aircraftScalePainted` would have
agreed with both bugs perfectly. Measuring the DOM is what separated the check
from a mirror.

**Why C10 is not "treat 0 as None".** A populated index with no station near a
borough is a MEASUREMENT of 0%: that borough really is poorly served and must
still band `poor`. Only an EMPTY index is unknown. Collapsing the two would have
swapped one silent wrong answer for another.

---

## 2b. Critical — the original detail (all now closed)

### C6 — the public demo key authorises `POST /v1/chat`, a Bedrock LLM billed here
`score-demo/index.html:449`, `backend/template.yaml:307, 491-503`

**Root cause verified statically: API Gateway usage plans authorise per STAGE,
not per route.** Both `ApiStages` blocks declare only `ApiId` + `Stage` with no
per-method map, so a key on any plan reaches **every** `ApiKeyRequired: true`
route on `prod`. The template's own comment at :318 — *"An unauthenticated model
endpoint is a free LLM for anyone who finds it, billed to this account"* —
describes a control that does not hold.

`verify_answer()` is not containment: `chat/app.py:143` extracts **numeric
tokens only**, so any digit-free reply passes as `grounded: true`.

Direct spend is small (~£0.50/mo at the 2,000 quota). The durable risk is that
**any future key-gated route is automatically granted to this public key.**

### C7 — the same key returns 100 scores per metered request
`MAX_BATCH_SIZE = 100` (`score/app.py:107`). 2,000 requests/month becomes
**200,000 scores** — 20× the Free tier, without the email address Free requires.
`BATCH_METERING_DECISION.md` cut the free tier 1,000→100 for exactly this reason;
the mitigation never reached the demo key.

**C6 and C7 share one fix.** Ascending robustness:

1. Per-method `Throttle` map on `ScoreDemoUsagePlan`, rate 0 for `/v1/chat` and
   `/v1/score/batch`. Cheapest; uses throttling as authorisation.
2. A separate stage (or REST API) for the demo key. Clean; more infrastructure.
3. A Lambda authoriser on the routes that must not be public. Most work.

**This is an architecture decision, so I have not made it.** Note the demo form
only ever issues single `GET /v1/score` calls, so option 1 breaks nothing today.

### C8 — nine UK cities are shown the New York subway
`index.html:9972` — `currentCity === 'london' ? … : …`, **and the else-branch is
NYC's.** An area search in Manchester, Birmingham, Leeds, Sheffield, Liverpool,
Newcastle, Bristol, Leicester or Teesside renders:

> **NEAREST SUBWAY STATIONS**
> NYC subway data coming soon. Check MTA.info for schedules.

Those nine also lose EPC, NHS and sold prices, under a comment reading *"London
only — these APIs are UK-specific"*, which is the reverse of true: EPC, NHS and
HM Land Registry are all UK-wide.

**The aggravating half:** the borough panel invites the user there per city
(*"Want nearest stations & energy ratings? Use the area search above"*), and the
**NaPTAN fallback built on 2026-08-12 to fix exactly this — 1,771 stations across
ten cities — is unreachable.** `nearestStations()` has one call site, inside
`renderTransportData()`, which is called only from the London branch. The data
shipped, the renderer shipped, nothing joined them.

*`feedback-shipped-does-not-mean-reachable`, recurring inside the very feature
that memory was written about.*

### C9 — a five-band decibel legend over an overlay that paints nothing in nine cities
`index.html:3073-3095`, `7714-7754`, `9209-9212`

The aircraft layer is **on by default** and its five swatches (`55-59 dB` …
`75+ dB`) are **static markup**. `updateDefraTiles()` paints `london` and `nyc`
only. The worst instance is South Yorkshire, whose own title reads
`AIRCRAFT NOISE (NO AIRPORT)` above five decibel swatches, while the score panel
says *"ZOOM INTO MAP TO SEE ESTIMATED NOISE CONTOURS"* for contours that exist at
no scale.

**`markLayerCoverage()` is the function written on 2026-08-11 to prevent this.**
Its `rows` array covers `road`, `flood` and `aq` — **the aircraft group was left
out of the fix made for its three siblings.**

### C10 — an empty NaPTAN or GP index publishes a band into *both* score holders
`scripts/build_borough_bands.py:417-443, 476`

`SystemExit` fires only when the **file** is missing. A column rename returns a
happily empty grid, `points_within()` returns `0.0` rather than `None`, and every
borough publishes `transport: 'poor'` / `healthcare: 'moderate'`. `transport` is
**0.25 of liveability**, and `--write-lambda` writes it into the Lambda, so
`test_borough_data_parity.py` stays green — both holders wrong identically.

### C11 — a blank flood render publishes "low risk" and caches it permanently
`scripts/fetch_ea_flood_risk.py:96, 150, 166-170`

`(255,255,255,0) → 0` is a *known* colour meaning "not in any modelled risk
polygon", so a fully transparent tile passes `classify()` without raising, is
`np.save`d, and the 4 MB file defeats the `st_size > 200` re-run guard. A tile
classifying 100% code 0 must fail.

---

## 3. Important

**Ten of the fourteen were closed on 2026-08-22**, each with a guard proven red
before it was trusted. Three of the ten turned out to be larger than recorded
here; the measurements are in the closure notes below the table. What is left is
I1 (a decision, not a defect), the `ReservedConcurrentExecutions` half of I3
(needs an account concurrency figure `flightmap-dev` cannot read), and I6.

| # | Issue | File | Note |
|---|---|---|---|
| I1 | **`/v1/regions` and `/v1/changes` are unauthenticated** while `template.yaml`, the `score/app.py` docstring and `CLAUDE.md` all say gated | `template.yaml:376` | Verified live: HTTP 200, 4.9 KB and 116 KB, no key. **CLAUDE.md corrected today** |
| I2 | `/v1/changes` is uncached and recomputes 33 boroughs per call at 116 KB | `score/app.py:6061` | Cost amplification on an open route. **CLOSED 2026-08-22** - memoised per container + `Cache-Control`; `generatedAt` deliberately NOT cached. |
| I3 | `/nhs` has `Timeout: 45` against APIGW's 29 s cap, no per-method throttle, and **no function sets `ReservedConcurrentExecutions`** | `template.yaml:213` | Verified: 0 occurrences repo-wide. Can starve the paid `/v1/score` path. **TIMEOUTS CLOSED 2026-08-22** - 45/60/30 all to 28. Concurrency half OPEN: `flightmap-dev` is denied `lambda:GetAccountSettings`, so the reserve cannot be sized from here. |
| I4 | `tests/api.test.mjs` passes on **any** 4xx; 2 of its 5 endpoints have only ever asserted a 400 | `tests/api.test.mjs:48` | It is the pre-release gate. **CLOSED 2026-08-22** - asserts payload contents; `/transport` and `/nhs` were live-proven to be returning 400 and passing. |
| I5 | `build_aircraft_bands.py --check` — **a blocking preflight stage** — exits 0 having compared nothing | `scripts/build_aircraft_bands.py:488` | `if have is None: continue`, then `return 1 if bad else 0`. **CLOSED 2026-08-22** - and in two sibling gates that had the same hole, one of them also blocking. |
| I6 | Leicester 0/8 and Teesside 0/5 carry **no** road-noise or flood band; three defences pass green | `data/borough-extra.json` | Verified. The map is honest; **CLAUDE.md was over-claiming, corrected today** |
| I7 | Mobile legend headings at **1.22:1**; the a11y gate never opens the collapsed legend | `index.html:3117, 3141, 3161` | Inline `style` beats the override written to fix it. **CLOSED 2026-08-22** - measured at **1.00:1**, not 1.22; gate now opens the legend. |
| I8 | `privacy.html` overflows to **469px** at 320 and 375 — and `responsive.mjs` has only ever loaded the homepage | `privacy.html:250`, `tests/responsive.mjs:18` | The legal notice scrolls sideways on every phone. **CLOSED 2026-08-22** - THREE pages were broken, not one; the audit covers 8 pages now. |
| I9 | EPC: an unrecognised band publishes `rating: 0` / `averageBand: 'G'` | `epc/app.py:175` | `.get(band, 0)` beside a guarded `[band]` ten lines up. **CLOSED 2026-08-22** - unknown band publishes null; no recognised band gives `averageBand: N/A`. |
| I10 | `/nhs` bundled path renders a confident empty result where the sibling path renders fallback links | `nhs/app.py:311-330` | Corners of the bbox report no GP, pharmacy or hospital. **CLOSED 2026-08-22** - **35.4%** of the bbox was affected, measured on a 24x24 grid. |
| I11 | `_LOCAL_POSTCODE_SERVED` is a sticky global — one NSPL hit credits ONS for every later postcodes.io answer | `score/app.py:3453` | B2B customers audit that `sources` array. **CLOSED 2026-08-22** - now `threading.local()`, reset per query. |
| I12 | The extension deletes its own aircraft-coverage caveat whenever a basis string exists | `extension/content/panel.js:790` | The flag tests "something is there", not "the notice is there". **CLOSED 2026-08-22** - suppression keyed on the notice itself, not on "some text exists". |
| I13 | The extension prints *"Live data unavailable"* and *"None found nearby"* one line apart | `extension/content/panel.js:576, 610` | Fourth instance of the class. **CLOSED 2026-08-22** - the two messages are now mutually exclusive. |
| I14 | The extension's Chrome-visible description still sells the transport section removed 2026-08-06 | `extension/manifest.json:5` | Grep for the NAME, not the function. **CLOSED 2026-08-22** - `extension/README.md` carried the same stale claim in its opening line. |

---

## 3a. Closure notes, 2026-08-22

Three findings were **larger than this report recorded**, and one recorded number
was wrong in the direction that matters. All four were found by measuring rather
than by reading the finding.

**I5 was three gates, not one.** The report named
`build_aircraft_bands.py --check`. The same hole - a missing holder is
`continue`, so comparing nothing returns 0 - was also in
`build_hpi_prices.py --check` (**also blocking**; an empty registry printed
`0/0 agree` and passed, and `--all` over an empty city list is `sum(())` = 0 =
PASS) and in `build_progress8.py --check`. All three now print what they
compared and fail on zero. The floor is **per-unit**: renaming one city's marker
leaves 104 of 114 bands still comparing, which a global `compared > 0` check
would wave through.

**I7 was 1.00:1, not 1.22:1.** Measured on the rendered DOM at 390x844: three
legend headings were `var(--dark)` #141414 on a `rgba(20,20,20,0.92)` pill - the
*same colour as their background*. Not low contrast, invisible. Now 17.64:1.
Hardening the a11y gate to open the collapsed legend then found a **second**
defect nothing had ever scanned: `.sheet-footer .for-devs` at 2.60:1, fixed by
applying `--orange-text`, a token created for this exact purpose on 2026-08-12
and never applied here.

**I8 was three pages, not one.** `privacy.html` overflowed 149px at 320. But
`changes.html` was worse - it scrolled the WINDOW **402px** at five viewports -
and `score-demo/status.html` overflowed at 320. `changes.html` is the
interesting one: it already had `overflow-x: auto` on a wrapper that measured a
correct 272px box, every over-wide element had a clipping ancestor, and the page
still scrolled. The cause is `position: sticky` on `th`: a stuck element is not
clipped by its scroll container when the document scrollable region is
computed. `contain: paint` was the only one of five candidate fixes that worked,
and it keeps the sticky header rather than trading the feature for the fix.

**I10 affects 35.4% of the bounding box.** `in_bundle_area()` tests a rectangle
spanning 51.25..51.72 by -0.55..0.35, well into Surrey, Kent, Essex and Herts.
Sampled on a 24x24 grid, 204 of 576 points had no bundled service within 1500 m
and were published as `available: true` with three empty lists. The report said
"corners of the bbox".

**A finding not in this report, found by the I8 gate widening.**
`score-demo/index.html` still advertised the pre-2026-08-21 free tier - "100
requests / month, 5 burst, 1 sustained" plus a working batch multiplier - on the
page a prospect uses to try the API. 100x under the real quota, and selling an
entitlement the usage plan now answers with 429. `FreeTierQuotaDriftTests` opens
by saying the numbers live in five places and only one is enforced, and then
asserted exactly one of the other four; `template.yaml`'s own list of mirrors
omitted this file. Both are fixed, and the pages are now asserted against the
plan.

---

## 4. Minor

`crimeRate` labelled `(EST.)` over an ONS attribution on one path and not the
other (`index.html:9698` vs `9956`) · the status page reports "All systems
operational" from probes where **403 scores as up** (`status.html:281`) · three
different quotas published for one key (100 / 1000 / 2000), the customer-facing
one 20× low · the extension's `LONDON_BOUNDS` is a **bounding box** deciding
whether the coverage caveat shows, so it hides for Watford and Dartford — *"a
bounding box is not containment"*, recurring · the extension drops focus to
`<body>` on every open and close, with no `.focus()` anywhere in `panel.js`
(WCAG 2.4.3) · EPC band swatches B 2.72:1 and F 2.70:1, licence attribution
2.97:1, focus ring 2.75:1 against the 3:1 WCAG 1.4.11 requires · `Avg Price`
column header over a **median** (`index.html:10889`) · `privacy.html` §5 omits
NaPTAN, EA RoFRS and NHS ODS from the stated score sources · `pricing.html` says
13 city-regions, `api/index.html` says 12 · `score_bulk.py` tells Enterprise
customers "the 33 supported London boroughs" for a 94-borough API ·
`d3.v7.min.js` 280 KB in `<head>` with no `defer` · `/v1/changes` ships
`explanation` byte-identical to `why.summary`, **21.7% of a 116 KB payload**.

**Second pass, 2026-08-22:** the extension now hands focus to the panel on open
and back to the badge on close (it had no `.focus()` call at all, so both actions
dropped a keyboard user to `<body>` - on a Rightmove listing that means tabbing
from the top of the page; both directions are asserted in the e2e and proven
red) · the panel focus ring 2.75 -> **4.51:1**, the OGL/ODbL licence attribution
2.97 -> **5.67:1** (that line is a condition of using the data and was the least
legible thing on the panel) and the debug row 1.90 -> **4.19:1** · `crimeRate`
now names the borough on BOTH paths instead of claiming `(EST.)` on one - ONS
Table C4 is a published figure, not an estimate, and the `(EST.)` sat directly
above an ONS attribution · the status page distinguishes **"Up (no key
required)"** from "Up (auth enforced)", which had rendered identically, so a
route silently losing its gate looked exactly like a gate holding.

**Examined and deliberately NOT changed:**

- **EPC band swatches.** B at 2.72:1 and F at 2.70:1 are the OFFICIAL EPC ramp,
  which a user matches against their real certificate - WCAG 1.4.11 exempts a
  presentation that is essential to the information. And the finding's premise
  (a CSS comment saying "a column carries no text") is wrong about the chart:
  every column carries its band letter and its count, so band identity is not
  conveyed by colour alone. Changing these would break the match to the
  certificate to fix a rule that is already satisfied another way.
- **`d3.v7.min.js` without `defer`.** 280 KB render-blocking in `<head>` is a
  real cost, but the inline script spans most of `<body>` and deferred scripts
  run *after* it. Proving no top-level d3 call exists across ~8,000 lines needs
  more than a grep, and the failure mode is a blank map on the live consumer
  site. Left for a session where the change can be watched. Moving the tag to
  the end of `<body>` is the lower-risk form of the same win.

**Closed 2026-08-22:** `Avg Price` over a median (the header now follows the
view - median for neighbourhoods, average for boroughs) · `privacy.html` §5
(five datasets added: DEFRA background maps, Price Paid, NaPTAN, NHS ODS, EA
RoFRS) · the 13-vs-12 city-region contradiction (both pages now count 12 UK
regions plus New York; every per-city borough count was verified against the
Lambda and all twelve were already correct) · `score_bulk.py`'s "33 supported
London boroughs", which now names no count at all and points at `/v1/regions` ·
and the three-published-quotas item, which was worse than recorded - see §3a.

---

## 5. Corrections to previously recorded findings

**The `excellent` air-quality band is NOT unreachable.** `HANDOVER.md` recorded
it as a category "no UK borough can occupy" and proposed dropping it or
re-anchoring it. Measured against DEFRA PCM 2022, 254,904 1 km cells:

| | |
|---|---|
| Cells clearing **both** WHO guidelines | **150,839 — 59.2%** |
| PM2.5 min / median | 1.72 / **4.43** against a guideline of 5.0 |
| NO₂ min / median | 0.42 / 3.33 against 10.0 |

The band is reachable; our **coverage** is 86 urban boroughs. Both proposed
remedies would therefore be wrong, and dropping it means re-adding it as soon as
coverage leaves the city cores — which `EXPANSION.md` says is the plan. **The
right fix is the `markLayerCoverage()` pattern**: hide bands with zero rendered
boroughs, so it corrects itself.

**`privacy.html` §2d carries Version A ("30 days"), not Version B.**
`check_log_retention.sh` exits 0 against it. `CLAUDE.md` described Version B for
some time after the page had moved on — **corrected today**. The gate is the
authority, not the prose.

---

## 6. Raised by agents, NOT reproduced

- **`.map-legend` clipping at 320×568** — flagged UNVERIFIED by the reporting
  agent; needs a render. Not counted in the totals above.
- The chat-endpoint exploit was executed by the security agent, not by me. I
  verified its **root cause** statically (stage-scoped usage plans) and did not
  re-run the live call, which would spend quota and Bedrock credit to re-prove a
  mechanism the template already demonstrates.

---

## 7. What no gate watches

1. **Any `--check` that skips a missing field and then reports agreement.**
   Three found: `build_aircraft_bands` (blocking), `build_progress8`,
   `refresh_crime_from_ons`. A per-unit floor fixes all three.
2. **`responsive.mjs` and the a11y scan load one URL each** — the homepage, in
   its default state. Neither has ever loaded `privacy`, `pricing`, `terms`,
   `changes` or a demo page, and neither opens a collapsed disclosure.
3. **No gate exercises the non-London area-search path**, which is how C8
   survived: the score-parity check compares boroughs, never the panel.
4. **`tests/api.test.mjs` cannot fail on a 4xx**, so it guards nothing it claims.

**Closed 2026-08-21 (evening):** point 3 - the non-London area-search path now
has `tests/uk-city-panel.mjs`. And a gap CREATED the same day was closed with
it: the 99 generated area pages bake their scores at build time, so a data
vintage would have put them silently out of step with `/v1/score` while
`deployed == source` kept passing (after a roll the repo and the CDN are both
stale, so they agree). `tests/area-page-freshness.mjs` compares the baked
number against the live API for all 99 in a SINGLE batch request - 1 quota unit
rather than 99, because a blocking gate that spends a consumable is how
`score sanity` once blocked every commit in the repo. Proven red three ways:
a stale score, a template change that breaks the parse, and a missing API key
(which fails rather than skips - a silent skip is how a stale page survives).
