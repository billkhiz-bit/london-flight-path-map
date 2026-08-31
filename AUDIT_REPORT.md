# Audit Report — Sky Score

**Date:** 2026-08-31
**Scope:** whole codebase — backend Lambdas, the scoring engine, `index.html`,
frontend design and accessibility, the 45 data-derivation scripts, the gate and
test suite, and every customer-facing document.
**Previous:** [`AUDIT_REPORT_2026-08-29.md`](./AUDIT_REPORT_2026-08-29.md), whose
still-open findings are carried forward in §6.

---

## 1. Summary

Seven parallel finders, each told to prove its findings by execution rather than
by reading, and each told that the last audit's verifiers **downgraded 8 of the
first 13 findings and refuted none** — so finders systematically overstate.

| | Count |
|---|---|
| Critical | 6 |
| Important | ~34 |
| Minor / below-the-cut | ~50 |

**Nine findings were independently re-verified by hand**, outside the agent
pipeline, because they are the ones that change a published number or a
contractual claim. Those are marked **RE-VERIFIED** below. Everything else
carries the finder's own evidence and should be re-measured before it is acted
on — a finder's `critical` is a hypothesis, and this repo has a standing lesson
that [a recorded finding can be the inverse of the code](./AUDIT_REPORT_2026-08-29.md).

### What is different about this audit

The last three audits found their richest seam in **gates that cannot fail**.
That seam is not exhausted — this one proved **eight more gates green on
constructed defects** — but the centre of gravity has moved. The single largest
cluster is now **documentation that contradicts the code**, and the most
expensive individual findings are **shape errors in the data derivation**: a
disc standing in for a runway-shaped contour, and a price median computed over
the wrong transaction class.

Three patterns account for most of the report.

1. **A correction applied in one holder and not its mirror.** Twenty-two of the
   documentation findings are this, and in **eight the stale copy sits in the
   same document as its own correction** — §4.6 against §4.5 on the raster
   quarantine, §7.1 against §4.7 on the road band cut, §2 against §2 on which
   cities are planned. Writing a correction as a dated note *beside* the old
   text means the old text survives, and a reader landing on the first of the
   two has no signal the second exists.
2. **A global floor where a per-unit floor was needed.** `compared > 0` is
   satisfied by 104 of 114 bands, by 9 of 10 boroughs, by 1 of 11 cities. Five
   gates were proven to pass while silently checking less than they claim.
3. **A guard whose comment describes a different rule from its code.** Three
   instances, each with the correct reasoning written down beside the wrong
   implementation.

---

## 2. Critical

### C1 — The aircraft near-field floor is a DISC, so two boroughs publish "Quiet skies 10.0/10" over ground DEFRA measures at up to 65.6 dB

| | |
|---|---|
| Location | `scripts/build_aircraft_bands.py:194-199`, applied at `:459-461` |
| Category | published-number-wrong |
| Live today | **Yes** — on the site, `/v1/score`, and two static area pages |

**Failure scenario.** `area/nottingham/rushcliffe/` publishes `Quiet skies
10.0 / 10` and aircraft band `Low`. Measured from DEFRA's own East Midlands
GeoTIFF, Rushcliffe contains **10.43 km² at ≥55 dB Lden with a maximum of
65.6 dB** — the fourth-largest aircraft footprint in the product. North Tyneside
is the same defect at 0.32 km² / 57.1 dB.

**Evidence.** `footprint_for()` returns a scalar *equivalent radius* and compares
it against airport-point-to-borough distance. Round 4 contours are long thin
strips along the runway centreline: East Midlands' is **21.2 × 3.8 km**, while
the disc assumes r = 3.46 km. Rushcliffe misses the disc by **180 m**.

```
nottingham/Rushcliffe    104,316 cells >=55 dB inside the borough = 10.43 km2, max 65.6 dB
tyneandwear/North Tyneside 3,195 cells                            =  0.32 km2, max 57.1 dB
westmidlands/Solihull     92,110 cells                            =  9.21 km2, max 87.2 dB
```

Solihull, at a comparable 9.21 km², is published `moderate-high` — so this is
not a deliberate threshold, it is internally inconsistent. Both finer scoring
tiers disagree with the band: sampling inside Rushcliffe gives DEFRA 64.1 dB,
geometry quiet 0.0 and postcode quiet 1.0 against a borough band of **10.0**.
Score effect: Rushcliffe `balanced` **5.0 → 3.4**, `quietlife` 6.4 → 4.0.

**Why it matters beyond the two boroughs.** The per-city `quiet` provenance tells
B2B integrators the bands "are PESSIMISTIC rather than optimistic". A sweep of
published band against DEFRA-measured median across the whole product found
**these are the only two boroughs where that sentence is false** — so the claim
is nearly true, and the exceptions are unflagged.

**Why no gate catches it.** `build_aircraft_bands.py --check` is blocking in
preflight and **never opens a raster** — `grep -c 'rasterio|\.tif'` returns 0.
The scale constants are transcribed from a one-off 2026-08-11 measurement, so
`--check` re-runs the same arithmetic against itself. (The constants are exact —
all twelve footprints were re-measured from the GeoTIFFs and match to 3 dp. The
*shape* assumption is the defect, not the numbers.)

**Suggested fix.** Test the borough ring against the ≥55 dB cells in that
airport's own GeoTIFF, which is already on disk and already read by
`probe_aircraft_raster_coverage.py`. That makes the gate cross a source
boundary — the same move `check_flood_georef.py` made for flood on 30 August.

---

### C2 — Neighbourhood medians include HM Land Registry Category B transactions, so 412 of 485 published prices are wrong, by up to 40%

| | |
|---|---|
| Location | `scripts/build_city_neighbourhoods.py:138`, filter `:610-633`, median `:1008` |
| Category | published-number-wrong |
| Live today | **Yes** — every generated neighbourhood row on the site |

**Failure scenario.** Category B is HM Land Registry's *additional* price-paid
class: repossessions, power-of-sale transfers, buy-to-lets identified by
mortgage, transfers to non-private individuals, and everything whose property
type is "Other". **HM Land Registry's own median-price statistics and the UK HPI
use Category A only.** So the borough `avgPrice` — validated against HPI by a
blocking gate — and the neighbourhood `price` in the same product are computed on
**different bases**.

**Evidence.**

```
PPD 2025 category counts: {'A': 779131, 'B': 153547}  -> 16.5% Category B
national median   Cat A £295,000    Cat B £210,000
property type 'O' (Other/non-residential):  A = 0 rows,  B = 45,371 rows

Category-A-only: 412 rise, 40 fall, 33 unchanged;  mean |delta| £9.3k
  TS26 Hartlepool                published 125k -> 175k  (+40.0%)
  WV2  Blakenhall & Ettingshall  published 150k -> 190k  (+26.7%)
  LS2  Woodhouse & Little London published 184k -> 150k  (-18.5%)
```

Rows currently inside published medians include
`£76,000 M9 7EP THE PALLET STORE TELECOMMUNICATIONS MAST SITE` and
`£40,000 S13 9WN`.

**Consequence.** `price` drives `afford`, roughly 31% of the ranked "best value"
list. **TS26 Hartlepool scores 7.84/10 published against 5.88/10 on Category-A
data — a 1.96-point swing.** 352 of 485 entries change rank. The file publishes
`priceBasis: "median sale price per postcode district"`, which Category B is not.

**Why no gate catches it.** There is no neighbourhood-price gate at all.
`preflight.sh:238` claims "a wrong price reds `prices == HM Land Registry`" —
that stage compares **borough** figures and never touches a postcode district.

**Suggested fix.** Filter `row[14] == 'A'` (which also removes every `O` row),
re-run `--write-index`, and add a `--check` with a per-city floor.

---

### C3 — The 99 static area pages credit UK bodies for New York's numbers, and credit ONS for a rate ONS refuses to publish

| | |
|---|---|
| Location | `scripts/build_area_pages.py:139, 142, 148-154` |
| Category | false-published-claim |
| Live today | **Yes** — 5 NYC pages and City of London |

**Failure scenario.** `area/nyc/brooklyn/index.html` prints per-fact notes
reading `HM Land Registry HPI`, `ONS Table C4`, `DEFRA road Lden`,
`Environment Agency RoFRS` and `NaPTAN` — because the note is a hardcoded
literal evaluated for every city. **The same page's** sources paragraph, which is
correctly derived, says *"NYPD CompStat-derived offence rates… Licence note: OGL
v3.0 covers UK Crown copyright and does NOT apply to any data in this
response."* Brooklyn's own record carries `None` for all four of those fields.

Second half: `area/london/city-of-london/` prints `Recorded crime 190
(ONS Table C4)` while the crime gate prints on **every run**: *"City of London:
repo publishes 190, ONS says '[u1]' -> our own figure. Must not be attributed to
ONS."*

**Why no gate catches it.** `test_non_uk_city_never_credits_uk_bodies` guards the
API's `sources` array and never sees these pages. `tests/area-pages.mjs` asserts
a fact floor and title uniqueness, not what a note says. **The one surface that
renders provenance per fact is the one nothing checks.**

---

### C4 — A slow or failed `/nhs` or `/transport` leaves a loading placeholder up permanently, and it fires on the live London path today

| | |
|---|---|
| Location | `index.html:9827`, `:9831`, `:9617`, `:9837`; placeholders `:11361`, `:11369` |
| Category | absence-as-measurement |
| Live today | **Yes** — measured against the production endpoint |

**Failure scenario.** A London postcode search. `/transport` or `/nhs` answers
non-2xx, or exceeds `PANEL_TIMEOUT_MS = 8000`. The fetcher returns `null`; both
renderers open with `if (!el || !data) return;` and paint nothing. The user is
left on **"Loading from TfL API…"** and **"Loading from NHS API…"** for the rest
of the session.

**Evidence — live latency, measured now:**

```
/transport run1 http=200 time=0.558s
/transport run2 http=200 time=1.825s
/transport run4 http=200 time=10.775s   <-- past the 8000 ms deadline
(earlier sample: 7.609s)
```

2 of 16 samples were at or past the deadline. Warm it is 0.4s; a cold Lambda
blows through it. **The fallback needs no network at all** — 708 London NaPTAN
stations are already in memory.

**Why no gate catches it.** `tests/failure-path.mjs:214-224` stubs `/transport`
with a hardcoded `status: 200` and never varies it, and never routes `/nhs` at
all. Its polling loop returns the raw text after 40 tries without asserting the
loading text is gone.

**The fix already exists eleven lines away and was not mirrored.**
`fetchEpcData` opens with: *"Always resolve to an object, never null. Returning
null used to make renderEpcData early-return, which left the 'Loading from EPC
register…' placeholder on screen permanently."* That lesson was applied to EPC
only.

---

### C5 — A `/transport` 5xx is turned into `available: true`, so an outage renders as a clean network

| | |
|---|---|
| Location | `index.html:9459` |
| Category | absence-as-measurement |
| Live today | **Yes** |

`if (!resp.ok) return { available: true, stations: [], _lat: lat, _lon: lon };`

The Lambda says `available: False` when TfL is unreachable and sets
`lineStatusAvailable` only when it answered. The frontend **fabricates the
success shape** for a 500/429 and omits `lineStatusAvailable`, so
`data.lineStatusAvailable !== false` evaluates `undefined !== false` → true, and
the 2026-08-27 "line status could not be checked" notice **can never fire**.

```
=== healthy (200) ===        hasLineStatusHeading: true   saysCouldNotBeChecked: false
=== tflStatus403 (200) ===   hasLineStatusHeading: true   saysCouldNotBeChecked: true
=== http500 ===              hasLineStatusHeading: false  saysCouldNotBeChecked: false
=== http429 ===              hasLineStatusHeading: false  saysCouldNotBeChecked: false
```

On a 500 the panel lists four stations and the line-status section **disappears
entirely** — the state the code's own comment says "was already being read as
*no disruptions*". The endpoint being wholly down produces a **less** honest
panel than TfL's status leg alone being down. **Fix:** `return { available: false };`
— the branch at `:9621` already renders the right message.

---

### C6 — METHODOLOGY §5 publishes a scoring formula that omits `env`, so a customer reproducing any score gets the wrong number — **RE-VERIFIED**

| | |
|---|---|
| Location | `METHODOLOGY.md` §5 |
| Category | false-published-claim |
| Status | **FIXED 2026-08-31** |

§5 read *"The **five** components are combined with persona weights"* followed by
a formula summing **four**:

```
score = w.quiet × quiet + w.afford × afford + w.growth × growth + w.live × live
```

`calc_score` (`app.py:5943-5959`) builds `parts` including `env` and sums
`parts[k] * effective[k]`. `env` is 0.14 of six personas and 0.18 of `family`
and `laterlife`. §5.1, **eight lines below**, already printed
`balanced = { …, env: 0.14 }` — so the document contradicted itself, and the
half a customer executes was the wrong half.

README:93 calls METHODOLOGY "the document that closes B2B audits", and §5 is the
reproduction procedure a pilot's evidence report rests on.

**Fixed**, along with the rescaling rule a reproduction also needs: a missing
component is **dropped and the survivors rescaled**, not treated as 0.0 — which
matters for New York (no `env`) and Cardiff (below the two-input floor).

---

## 3. Important — a selection

The full finder output is long; these are the ones that change a number, a
contractual claim, or a gate's meaning.

| # | Issue | Location | Note |
|---|---|---|---|
| I1 | **RE-VERIFIED, FIXED.** METHODOLOGY §7.1 published the road-noise band rule as *median Lden vs 53/48 dB*. `road_band()` takes the **share over 53 dB** at 66.7%/50% cuts. The old rule reproduces the published band for **11 of 86** boroughs; the corrected rule reproduces **86 of 86**. Hounslow's median is 54.8 dB → doc said `high`, product publishes `moderate` | `METHODOLOGY.md` §7.1 | 87% of boroughs mis-described |
| I2 | **RE-VERIFIED.** 11 provenance strings say `"May 2026 vintage"` while the Lambda serves **June** figures — Sandwell `avgPrice 205743 / trend 0.6` is HPI 2026-06 (May was 208920 / 2.7). `terms.html` obliges integrators to pass `sources` through | `backend/lambdas/score/app.py:4707`+ | `prices == HM Land Registry` compares numbers only |
| I3 | DEFRA road `0.0` means "surveyed, below 40 dB" and both consumers treat it as missing, **in opposite directions**. The loader drops it, so `/v1/environment` says "not measured" for 2,610 London postcodes DEFRA did measure — and **only the good-news readings are dropped**. The band builder drops it from the share's *denominator*, inflating `roadNoiseAboveWhoPct` by up to 5.5 points. **Band flip: London's Sutton 50.2 → 49.7, `moderate` → `low`** | `load_defra_raster.py:161`, `build_borough_bands.py:307,608` | Its flood sibling explains why it deliberately does NOT drop 0 |
| I4 | **RE-VERIFIED.** When `data/borough-extra.json` fails to load, 31 of 33 London boroughs change score and **20 move UP** — Barking reaches a perfect **10/10 because its data went missing** — under a notice claiming the total "falls back to a neutral 5.0". `combineWeighted`'s own comment says the `?? 5` placeholder was deliberately removed because it "penalised a borough for being unmeasured"; the code rescales. The notice never mentions Environment | `index.html:7839` | The fix reached the code and not the notice |
| I5 | Barking and Dagenham's area page silently drops road noise, air quality and flood: the Lambda keys `Barking and Dagenham`, `borough-extra.json` keys `Barking`, and `build_area_pages.py` does a raw `.get`. **The alias is declared in four other places**, only one pair drift-guarded | `build_area_pages.py:125` | Cardiff/Nottingham pages under-report for the mirror reason |
| I6 | **RE-VERIFIED, FIXED.** CI's `test-backend` job has been RED on every push: it installs `pytest pytest-mock boto3`, and the root suite imports `numpy`/`PIL` inside test bodies with no `importorskip`. **254 pass locally, 8 fail under CI's dependency set.** This is one step beyond F30 — that fix stopped the job being *skipped*, only for it to fail on imports | `.github/workflows/ci.yml:52` | CI still produced no correctness signal |
| I7 | `check_flood_georef.py` — **a mosaic with every flood polygon erased PASSES.** A class with no eroded interior sets `results[label] = None` and `main()` skips it, so the medium-or-high direction is silently dropped and the city passes on the not-MoH direction alone. Its own docstring says both directions are checked *because* asserting one "would pass a mosaic that had lost its flood polygons entirely" | `check_flood_georef.py:245,342` | Proven: 1.2M MoH pixels zeroed, exit 0 |
| I8 | `check_flood_georef.py --all` — **10 of 11 cities silently skipped.** `data/*.tif` is gitignored, so "never fetched" is the normal state on any machine but Bill's. Printed *"verified against the EA service for 1 cities"*, exit 0 | `check_flood_georef.py:222,338` | Global floor, not per-city |
| I9 | `build_borough_bands.py --check` prints *"agrees with DEFRA on every derived field"* **having compared zero**. It is the only source-crossing gate for road noise (0.35 of env), air quality (0.45), transport (0.25 of live) and healthcare (0.10) — and it is advisory | `build_borough_bands.py:723,750` | Missing data is indistinguishable from agreement |
| I10 | `tests/area-pages.mjs` runs its two most important assertions on `pages[0]` **only**. 98 of 99 pages given `<script src="https://evil.example/...">` and their score text removed: **all three checks PASS** | `tests/area-pages.mjs:134-136` | Header calls the no-script property "the entire point" |
| I11 | `tests/map-fit.mjs` **never measures New York**, at any viewport — it enumerates `.city-btn`, and the app renders chips for the active country only. NYC is the one city with a different projection origin and boundary source. Its floor is 18 against a real 90 | `tests/map-fit.mjs:143` | 10 city labels measured, not 11 |
| I12 | `check_api_url_drift.sh` — 7 of 8 surfaces rewritten to `https://DELETED.example`, leaving only `js/api-base.js`: **PASS**. It detects drift *between* execute-api ids, never drift *away from* execute-api | `check_api_url_drift.sh:29` | |
| I13 | `check_no_em_dash.sh` — zero files scanned is a PASS, and a renamed page is silently skipped. The 100 deployed `area/` pages are outside its list entirely | `check_no_em_dash.sh:30` | |
| I14 | `refresh_crime_from_ons.py` (blocking) passes with a borough 25 per 1,000 adrift — the floor is per city, not per borough. Its own comment at `:322` predicts exactly this and does not act on it | `refresh_crime_from_ons.py:283,398` | Constructed red |
| I15 | The ONS crime workbook is cached under a name that **omits the edition**, so a quarterly roll re-checks the old release and reports "in step with ONS". Its HPI sibling does check the vintage | `refresh_crime_from_ons.py:44,49` | |
| I16 | `chat`'s boto3 clients have **no timeout config** — botocore defaults are 60s connect + 60s read with up to 5 retries, against a 28s function budget. Both degraded-response branches are unreachable for a Bedrock throttle, so the caller gets a raw 502 with no CORS headers instead of the 503 the code exists to give | `chat/app.py:109-118` | Same class as audit I3, one level in |
| I17 | `POST /favourites` is unauthenticated (the device token is self-asserted and unregistered), **unthrottled** (no per-method entry, so 50 RPS), and writes permanently into a PITR-backed, TTL-less, `Retain` table. 4.32M writes/day at the ceiling | `favourites/app.py:97`, `template.yaml:52` | The file's own comment states the exposure and bounds only item size |
| I18 | `score_bulk.py` — **the Enterprise deliverable has crashed on every run for nine days** (`_LOCAL_POSTCODE_SERVED` became thread-local on 22 Aug). The silent half is worse: attribution is thread-local, scoring runs in workers, and `write_sources_file` runs on the main thread — so the OGL file that "MUST accompany the CSV" credits postcodes.io for lookups ONS served | `score_bulk.py:548,377` | |
| I19 | Station lists de-duplicate by exact cleaned name, so **24.5% of "nearest four stations" panels show fewer than four places** and 14 show one place four times (Attercliffe appears as five "stations"). Nine explicitly closed stations and two heritage-railway halts ship as current — NaPTAN `Status` is never read | `build_city_stations.py:117,202` | `uk-city-panel.mjs` asserts `length > 0` |
| I20 | **RE-VERIFIED, FIXED.** README said "Six endpoints. Four are API-key gated. Two are deliberately public" against its own table of **seven** rows with **three** marked Public. Live: 3 gated (`/v1/score`, `/v1/score/batch`, `/v1/chat`), 4 public | `README.md:119` | Wrong in all three numbers |
| I21 | **RE-VERIFIED, FIXED.** LICENSING recorded the **v3.9** environment weights (air 0.65 / flood 0.35) against the live 0.45/0.35/0.20, and had **no row at all** for DEFRA road Lden — the dataset carrying the second-largest scored environmental share | `LICENSING.md:75-76` | Integrator licensing review surface |
| I22 | **RE-VERIFIED, FIXED.** METHODOLOGY §2 published Greater Manchester as resting on "2 of the 4" liveability inputs with "no Greater Manchester source" for road noise, flood or air quality. All ten boroughs carry **4 of 4 and 3 of 3**; §7.1–§7.3 of the same document already said so | `METHODOLOGY.md` §2 | |
| I23 | **RE-VERIFIED, FIXED.** METHODOLOGY listed eight already-live cities as "Planned", 61 lines after listing them as supported. Only Edinburgh, Glasgow and Belfast remain | `METHODOLOGY.md` §2 | |
| I24 | **RE-VERIFIED, FIXED.** Four statements that `/v1/score` "does not implement" the heliport term. `HELIPORTS_LONDON` has been wired into `calc_postcode_quiet` since 2026-08-03, kept identical to the site by `test_heliports_match_the_site`. The document advertised a live site/API divergence over 14.1% of London for four weeks after it closed | `METHODOLOGY.md` §4.5, §11 | |
| I25 | METHODOLOGY §16's free-tier block has **every figure wrong** (100 requests/month, 1/s sustained, a usable batch multiplier) against 10,000/month, 2/s, and batch **denied**. `template.yaml` names five mirrors of these numbers and **METHODOLOGY is not one of them**, so `FreeTierQuotaDriftTests` cannot see it | `METHODOLOGY.md` §16 | "A list of mirrors that omits a mirror", recurring |
| I26 | `?compare=previous` explains every score under the **balanced** persona, so an `investor` request gets an explanation contradicting its own `scoreChange` | `score/app.py:398` | Carried forward as F8; still open |
| I27 | `sourceBreakdown.live` credits DfE for boroughs with **no Progress 8** — 7 of Leicester's 8 today — contradicting `liveResolution` and `sources` in the same response. Verbatim the 2026-08-24 defect; the fix reached `_live_sources_line` and not its sibling `_live_breakdown_line` | `score/app.py:4647` | |
| I28 | City of London's crime rate is Sky Score's **own estimate**, scored at full weight and counted as "measured" — 0.9 points of a live headline score. `live_resolution`'s own docstring names this exact case as fixed; only the schools half was | `score/app.py:1267,5779` | `crimeEstimated` is read by nothing |
| I29 | A caller **cannot opt into `env` weights**: a five-key set fails `parse_weights`' set-equality check and falls back to `balanced` silently, with no error field. A legal four-key set drops `env` to weight 0 while the response still publishes `env: 4.4` as `measured` and credits three datasets | `score/app.py:6427` | A passing test asserts the defect — 5th instance |
| I30 | The postcode LRU defeats NSPL attribution: only the **first** request for a postcode in a warm container credits ONS; requests 2..N credit postcodes.io, which was never called. Two identical postcodes in one batch get different provenance | `score/app.py:6372` | One-line fix; `_resolver` is already cached |
| I31 | `epc` publishes "no certificates on record" for **every postcode in the country** if MHCLG renames its response envelope, and discards the `pagination.totalRecords` in its own payload that would prove otherwise | `epc/app.py:130-143` | Verbatim the `sold_prices` scar |
| I32 | `transport` reports `lineStatusAvailable: true` on responses where the status feed was **never contacted** — live in Manchester and Sheffield. A passing test locks the wrong answer in, under reasoning true for London and false for a tram-only centre | `transport/app.py:69` | 4th instance of "a passing test reads as evidence" |
| I33 | Favourites: an API failure renders as **"No saved locations yet"** — the one message that could persuade a user their saved locations were lost. And every non-London UK favourite is filed under a heading reading **"London"** (a two-city binary that survived the expansion to eleven) | `index.html:11557,11621` | Nothing renders this list in any test |
| I34 | The score explainer says "four components" and the ranking header lists weights summing to **82–86%**, on a page that renders five rows and ranks with `env` included | `index.html:6556,12473` | |

---

## 3b. Frontend design and accessibility

Measured, not eyeballed: `getBoundingClientRect`, `elementFromPoint`,
`getComputedStyle` and real `mouse.click` across 15 viewports including three
landscape sizes, in both `prefers-color-scheme` states.

**This finder audited its own instrument first, and it is worth recording.** Its
first contrast checker returned `NaN` for every ratio, so `ratio < 4.5` was false
everywhere and it reported the whole site clean; its second reported
`.btn-primary` at 1:1, a false positive caused by `background: linear-gradient`
leaving `backgroundColor` transparent. Only the third — red-proofed at 2.85 and
1.62, green at 18.88 and 14.49 — produced the numbers below. It also **discarded
four focus-indicator findings** after byte-comparing focused and unfocused
screenshots proved all ten controls do paint an indicator, despite
`getComputedStyle` reporting `outline: 0px`.

| # | Issue | Severity | Measurement |
|---|---|---|---|
| D1 | **All 99 area pages link to a borough the app ignores** — **RE-VERIFIED**. Every page carries `<a href="/?city=london&borough=Camden">Open Camden on the Sky Score map</a>`, and `bootFromQuery()` reads `city` and `postcode` **only**. The link lands on the empty state: *"Search by area… or click the map"* | **HIGH** | `selectedBorough: null`, `anyPanel: false` at 390 and 1366 |
| D2 | **The result-close `×` is invisible and unclickable at every width ≤900px.** `.search-box` is `position: sticky; z-index: 3` and opaque; `.result-close` is `z-index: 2` inside `#tab-analysis`, which has `z-index: auto` and so creates no stacking context — the inner 2 loses to the outer 3 directly. A screenshot crop shows **no × at all**. `Escape` does nothing | **HIGH** | **33% hit-testable**, identical at 320/360/375/390/414/844/900. A real click at the centre does not dismiss |
| D3 | **Landscape phone: the legend and layer toggles are unusable.** `max-height: calc(100dvh - …)` has no floor, and the expand chip is gated on `max-width: 480px` while the failing dimension is **height** | **CRITICAL** | 568×320: legend **17.6px** for 192px of content, **91% hidden**, no expand toggle. Layer toggles **6 of 6 blocked at centre**, 4 at 0% of their area |
| D4 | **Desktop 901–1366px: up to 6 of 10 city chips cannot be reached with a mouse.** The strip is `overflow-x: auto` with the scrollbar hidden (`offsetHeight - clientHeight = 0`), vertical wheel gives `scrollLeft = 0`, and there is no drag handler. **1366×768 is the most common laptop resolution** | **HIGH** | 901px: 652px of 1109px hidden. 1366px: Greater Manchester entirely off-strip. `city-switch.mjs` runs at 1440 and 390, straddling the band |
| D5 | "Change profile" — the control that changes the entire scoring persona — fails AA | MED-HIGH | **2.22:1** on phones, 2.6:1 on desktop. The area pages already use an accessible `#c2410c` (5.18:1) for the same role |
| D6 | 13 controls stay in the tab order behind the full-screen mobile panel — `inert: false`, `aria-hidden: false`, all confirmed occluded | MEDIUM | Tab stops 16–28 all `occluded: true` |
| D7 | `.score-explain` misses AA by 0.03 across the whole borough panel | MEDIUM | **4.47:1**, needs 4.5. `#5f5f5f` clears it |
| D8 | The borough panel **never names the borough** in a heading: six `<h3>`s, none the subject, `<h1>` stays "Sky Score" and `document.title` never changes | MEDIUM | `h1` → `h3` with no `h2` |
| D9 | Four visual systems across nine page types — four font families, four `h1` sizes, four link colours, **two opposite background polarities**, three accent oranges | MEDIUM | area→home→pricing crosses three products |
| D10 | Country tabs are **14px tall** (UK 24×14, USA 28×14); ten city chips 22px — under the WCAG 2.5.8 24×24 minimum, on the primary navigation | LOW-MED | `responsive.mjs` builds a tap-target list but keeps it advisory |
| D11 | Dark mode exists on the **area pages only** and declares no `color-scheme`, so UA scrollbars render light on `#141414` and an area→map journey flashes full white | LOW | 0 `prefers-color-scheme` hits in the other 9 pages |

**Clean, and worth not re-auditing:** all 100 area pages at 320 and 414 in both
schemes — **0 overflow, 0 contrast failures, 0 table scroll**. They are the
best-built surface in the repo. `changes.html`'s `#table-wrap` is exemplary
(`overflow-x: auto`, a real scrollbar, `tabIndex=0`) and is the pattern
`.city-selector` is missing.

**The pattern behind D2, D3 and D6 is one shape**: a fixed or sticky layer
painting over a control that still has layout, focus and hit-testing. The
codebase already documents that exact mechanism twice in comments — including
for the city chips at `index.html:3246`, *"an inner z-index of 4 cannot lift a
child out of a parent stacking context that loses"* — while three more instances
ship.

**Gate gaps behind these:** `responsive.mjs` runs **no landscape viewport and no
dark mode**, and covers neither `area/**` nor `api-docs.html`. `a11y-source.mjs`
scans the app's **landing state only**, so the borough panel — where D5, D6, D7
and D8 all live — has never been scanned by anything.

---

## 4. What I fixed in this pass

Nine findings, each verified before and after. The gate work is recorded in
`AUDIT_REPORT_2026-08-29.md` §Status; the documentation work is here.

| Finding | Fix | Verification |
|---|---|---|
| C6 | `env` added to the §5 formula, plus the drop-and-rescale rule | Read against `calc_score` |
| I1 | §7.1 road band rule rewritten to the share, with the real cuts | Corrected rule reproduces **86 of 86** published bands (was 11) |
| I20 | README API surface: routes **named**, not counted | Verified live: 403 vs 200 per route |
| I21 | LICENSING weights corrected; a DEFRA road Lden row added | Against `_ENV_WEIGHTS` |
| I22 | §2 Greater Manchester corrected to 4-of-4 and 3-of-3 | Against `borough-extra.json` |
| I23 | §2 "Planned" reduced to Edinburgh, Glasgow, Belfast | Against `CITY_DATA` |
| I24 | Four heliport statements corrected | Against `HELIPORTS_LONDON` |
| I6 | `numpy pillow` added to CI | Proven: 254 pass local, 8 fail stubbed |
| D1 | `bootFromQuery()` now reads `borough`, awaiting the async `switchCity` first | 6 deep-link cases, proven red 5 of 6 by reverting the fix |
| I10 | `area-pages.mjs`'s three per-page checks now loop over all 99, not `pages[0]` | Each proven red on a page that is not `pages[0]` |
| — | `city-switch.mjs` gained a city-count floor; `renderBoroughs()` now compares borough names canonically, as its sibling handler already did | Floor: an empty list used to print "All 0 cities switch" and exit 0 |

### D1's residual, measured and left open

The fix makes the panel correct everywhere and the map selection correct on
desktop. **On a phone, a deep link that also switches city renders the panel
correctly and then loses the map highlight.** Measured on 390x844:
`?city=manchester&borough=Salford` sets the fill *synchronously* — reading it in
the same tick gives 1 dark outline — and something repaints it to the default
within ~1.2s, stably, at every sample out to 8 seconds.

It is specific to that one path, which is what makes it worth recording rather
than guessing at: **Camden with no city switch keeps its highlight on the same
phone, a normal borough click keeps it, and a plain resize after either keeps
it.** So it is not the generic repaint-on-resize case, and it is not something
the deep-link fix introduced.

`renderBoroughs()` was found comparing `getName(d) === selectedBorough` — the
raw feature name — while the mouseout handler eleven lines below already
resolved through `matchBorough()`. That is a real inconsistency of the
two-copies-of-one-rule kind and is fixed, but it was **not** the cause; the
mobile behaviour is unchanged by it. The late repainter has not been
identified. The gate asserts the panel at both viewports and the highlight only
where it is guaranteed, rather than reddening on a defect the fix does not own.
| F34/F35/F31/F43/F14/F15 (29 Aug) | See the previous report's Status section | All proven red |

---

## 5. Method, and what to distrust

- Seven finders ran in parallel, each with a scoped brief and an explicit
  instruction that the last audit's verifiers downgraded 8 of 13 findings.
- **No adversarial verification pass ran on this audit.** The 29 August audit's
  verification died at 13 of 48 on the session limit; rather than repeat that,
  the finders were told to prove by execution and **nine of the highest-stakes
  findings were re-verified by hand instead**. Anything not marked
  **RE-VERIFIED** should be re-measured before a fix is written from it — a fix
  written from a wrong diagnosis is wrong too.
- **Findings deliberately narrowed by their own finder** are worth noting as a
  quality signal: the `/nhs` per-category fallback was nearly filed as important
  and was downgraded after the bundle was checked at eleven fringe towns and
  found genuinely complete; the finder wrote *"I nearly filed this as important
  and it does not deserve it."*
- Baselines that came back **clean**, which narrow the search: a full
  re-derivation of all 91 borough band records reproduced `borough-extra.json`
  with **0 disagreements**; all 485 neighbourhood medians reproduce; every
  postcode of every city falls inside its own road and flood raster (0 of
  952,582 outside); all 11 flood mosaics are geometrically exact after the
  30 August fix; DEFRA AQ grid coverage is 100.00% in all 99 boroughs. **No
  derivation drift exists today** — C1 and C2 are shape errors, not drift.

---

## 6. Carried forward from 29 August, still open

`F8` (persona-blind comparison explanations), `F26` (London's aircraft raster
declared painted from an href), `F38` (**every borough band weighted by retired
postcodes — 904,453 of them; re-verified by hand on 31 August and still open**),
and the Important/Minor rows not marked FIXED in
[`AUDIT_REPORT_2026-08-29.md`](./AUDIT_REPORT_2026-08-29.md).

**F38 is the largest single open item in either report.** It moves published
bands across all 91 boroughs and both score holders, and it is a one-line read
of NSPL's `doterm` column that four sibling scripts already perform.
