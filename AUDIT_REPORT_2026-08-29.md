# Audit Report — Sky Score

**Date:** 2026-08-29
**Previous full audit:** 2026-08-21 (`AUDIT_REPORT_2026-08-21.md`)
**Method:** a ten-agent survey (nine dimension finders plus a completeness
critic) across the whole tree, then an adversarial verification pass in which
each finding was handed to verifiers *briefed to refute it* — three
perspective-diverse lenses per Critical (reproduce it / trace the code path /
who is harmed and does a gate already catch it), one per Important. Survey:
851 tool uses, 2.5M tokens, 0 agent failures. Findings the finders could not
evidence were dropped by the finders themselves before reporting.

> **Read the verification column before acting on anything here.** This repo
> has a documented history of confidently-worded findings that were the
> INVERSE of the code — seven instances by the last count. A finding marked
> UNVERIFIED has been through one agent and nothing else; treat it as a lead,
> not a fact, and re-measure before writing a fix. **A fix written from a wrong
> diagnosis is wrong too.**

---

## Summary

| | Count |
|---|---|
| Critical | 9 |
| Important | 21 |
| Minor | 15 |
| **Total** | **45** |

### Status, 2026-08-31

**Eleven findings closed, one partial.** F1, F5, F24, F25, F30, F39 and F41 on 30 August;
**F14, F15, F31, F34, F35 and F43 on 31 August, with F33 partial** — the whole "gates that
cannot fail" cluster, which the shape-of-this-audit note below calls the most
productive dimension three audits running.

Every 31 August fix was **proven able to go red** before being accepted, and two
of the proofs mattered more than the fixes:

- **F34 was worse than recorded.** `FAIL_MODERATE` was not merely filtered out by
  impact — axe never RAN those four rules, because all four are tagged
  `best-practice` only while the builder asked for WCAG tags alone. The set was
  dead code from the day it was written. Proven at the taxonomy level rather
  than against today's pages, which shows it could never have fired on ANY page.
  It was hiding missing `<main>` landmarks on **privacy.html and terms.html —
  the two legal pages — and all 100 pages under `area/`**.
- **F43's first red-proof passed, and the harness was at fault, not the gate.**
  MSYS rewrote the `/fonts/...` path argument (this repo's own documented Git
  Bash gotcha, in a new place), so nothing was actually broken. *A harness that
  disagrees with the real thing is evidence about the harness first.*

**F33 is PARTIAL, not closed, and the follow-up audit caught me claiming
otherwise.** The fix does what the finding asked — the city list is now
cross-checked against the Lambda's own `<CITY>_BOROUGHS` blocks, so dropping a
city from `AIRPORTS` fails loudly (proven red: before, that scenario printed
"Compared 104 band(s) … 0 disagreement(s)" and exited 0), and there is a
per-city floor. But `london` and `nyc` are named `DERIVATION_EXEMPT` rather than
covered, so **London's 33 and NYC's 5 published `impact` bands — 38 of 99,
including every `severe` band and the entire Heathrow set the ladder is
calibrated on — are still compared against nothing.** Naming them means a
twelfth city cannot silently join them, which is the improvement; it is not the
same as checking them. Covering London needs the gate to read the DEFRA GeoTIFFs
already on disk, which would also close finding 1 of the 31 August data-scripts
audit.

**A new instance of the same class was created and caught during the fix**: a
collapsed `\b` in a Bash heredoc became a literal `\x08` in the new
viewport-exemption regex, so a guard written that minute to close F34 could
never match — a check that cannot fail, made while removing checks that cannot
fail. `grep` renders it as though the backslash were there and `node --check`
accepts it. See [[feedback-gitbash-shell-gotchas]].

| Verification | Count |
|---|---|
| CONFIRMED (survived adversarial refutation) | 5 |
| REFUTED (verifiers broke it) | 0 |
| UNVERIFIED (pass did not reach it) | 40 |

**Two findings were also confirmed independently by hand, outside the agent
pipeline**, because they are the highest-stakes ones: the EA flood mosaic
mis-georeferencing (F24 / F39) and the `envCaveat()` regression (F25). The
notes under each say what was checked and how.

### The shape of this audit

Three clusters account for most of it.

1. **Geometry and georeferencing, not absence.** The single worst finding is a
   raster mosaic that pastes clipped edge tiles as though they were full ones,
   so published flood figures are wrong in 10 of 11 cities. The `--check` gate
   beside it cannot see this, because it re-derives from the same mosaic: the
   two things it compares are the file and itself.
2. **Echo-work left undone by the v4.0 wave shipped hours earlier.** Five
   findings are customer-facing surfaces still describing a four-component
   score, or quoting counts that the code contradicts. One of them is an error
   introduced by the wave itself.
3. **Gates that cannot fail** — still the most productive dimension, three
   audits running. Two gates are in no runner at all; one cannot fail while a
   shared quota is exhausted, and it is exhausted.

---

## 1. Critical

### F1 — [FIXED 2026-08-30]  The scored `environment` component is credited to nobody: no `sourceBreakdown` entry, no `sources` line, and the guard test hardcodes the pre-v3.9 four-key set

| | |
|---|---|
| **Verification** | **CONFIRMED** — 3 of 3 verifiers could not refute it |
| Location | `backend/lambdas/score/app.py:4683` |
| Category | provenance-and-attribution |
| Found by | Published claims that do not match |

**Failure scenario.** A B2B integrator scores any London postcode, takes the returned `sources` array, and republishes it to their own users exactly as terms.html §6 obliges them to. The array they carry forward credits DfT, NHS, ONS, DfE and DEFRA-aviation but omits DEFRA's background pollution maps, DEFRA's road Lden surface and the Environment Agency's RoFRS — the sole basis for 14-18% of the number they are republishing. Both the integrator and Sky Score are then distributing OGL v3.0 data with no attribution, while METHODOLOGY §18 tells the integrator's auditor the array is complete. A conveyancer auditing `sourceBreakdown` for the `env` value in `components` finds no key for it at all, and METHODOLOGY §18 says that state means the component has no source — which is false; it has three.

**Evidence.** `build_source_breakdown()` returns exactly `prov['breakdown']`. I dumped it for every city: python -c "...; [print(c, sorted(p['breakdown'])) for c,p in m.CITY_PROVENANCE.items()]" london ['afford', 'growth', 'live', 'quiet'] (identical for all 13 cities) `build_sources()` (app.py:4938) likewise names no environment source. London's array resolves to: NaPTAN, NHS ODS, postcodes.io/NSPL, borough metadata (ONS + DfE), "Aviation noise context: DEFRA strategic noise mapping". No DEFRA background pollution maps, no DEFRA road Lden, no Environment Agency RoFRS — the three datasets that are the ENTIRE `environment` component (`_ENV_WEIGHTS` app.py:5276, `aq_to_score`/`road_to_score`/`flood_to_score` app.py:5349/5375/5360), which carries 0.14 of six personas and 0.18 of `family` and `laterlife` (app.py:252-265). The published claims this contradicts: - terms.html:292 (contractual): "Every API response includes a `sources` array naming the datasets used to produce it. If you display or redistribute Sky Score data, you must carry that attribution through to your own users." - METHODOLOGY.md:1892 (§18): "Every `/v1/score` response carries a `sources` array and a `sourceBreakdown` object naming the origin of **each scored component**." - METHODOLOGY.md:1896: "Where a component has no source, the response is required to say so rather than publish a silent default." The code applies exactly 

**Why no gate catches it.** `test_every_city_has_its_own_provenance` is the only gate over provenance completeness and it asserts a hardcoded literal `{'quiet','afford','growth','live'}` under a message claiming it covers every scored component. It passed unchanged through v3.9 (2026-08-26) and v4.0 (2026-08-29), and it would go RED on the fix — adding an `env` breakdown key fails the assertEqual. Every other preflight stage (32 of them) checks lint, markup, a11y, responsiveness, data-vs-publisher parity or site-vs-Lambda score parity; none reads the `sources`/`sourceBreakdown` contract. `test_non_uk_city_never_credits_uk_bodies` only checks that NYC does NOT name UK bodies, never that a UK city names the right ones.

**Suggested fix.** Add an `env` key to every city's `breakdown` naming DEFRA background pollution maps (PCM), DEFRA Round 4 road Lden and EA RoFRS with the weight each carries, plus `sources` lines for the three (and the NYC/Cardiff 'component declined' case). Then replace the hardcoded set in test_score.py:1243 with one derived from the components the engine can actually emit — e.g. assert the breakdown keys equal the keys `score_borough()` can put in `components` — so the gate cannot go stale on the next component.

**Verifier notes.**

- *? lens* (high confidence, severity called `important`): Line references, all minor and all off-by-one or off-by-two: - `build_sources` is at app.py:**4939**, not 4938. - The `assertEqual` in the guard opens at test_score.py:**1242**; the hardcoded literal `{'quiet','afford','growth','live'}` is at **1244**. The finding cites 1243, which is the `set(app.build_source_breakdown(city))` argument line. - app.py:4683 (the finding's anchor) is correct: it is 
- *? lens* (high confidence, severity called `important`): 1. LINE NUMBERS. `build_source_breakdown()` is at app.py:4979, not 4683 — line 4683 is the `quiet` string inside London's `breakdown` dict (CITY_PROVENANCE starts at 4661). `build_sources()` is at 4939, not 4938. `_ENV_WEIGHTS` 5276, `aq_to_score` 5349, `flood_to_score` 5360, `road_to_score` 5375, test_score.py:1243, terms.html:291-293 are all correct. 2. TWO OF THE THREE ARE PARTIALLY CREDITED, i
- *? lens* (high confidence, severity called `important`): 1) LINE REFERENCE: `build_source_breakdown()` is at app.py:4979 and `build_sources()` at app.py:4939, not 4683. Line 4683 is the london `'breakdown'` dict literal — a fine anchor for where the `env` key must be ADDED, but the evidence prose describes the function, which is 300 lines further down. Both numbers the evidence cites for the weights (252-265) and `_ENV_WEIGHTS` (5276) / `aq_to_score` (5

---

### F8 — ?compare=previous explains every score under the balanced persona, so a non-balanced request gets an explanation that contradicts its own scoreChange

| | |
|---|---|
| **Verification** | **CONFIRMED** — 3 of 3 verifiers could not refute it |
| Location | `backend/lambdas/score/app.py:398` |
| Category | false-published-claim |
| Found by | Scoring engine — backend/lambdas/s |

**Failure scenario.** GET /v1/score?borough=Barking%20and%20Dagenham&city=london&persona=investor&compare=previous returns score 8.8, comparison.previousScore 7.1 and comparison.scoreChange 1.7, and in the same object comparison.explanation reads "Score unchanged at 8.8, even though the market moved." followed by "Growth moved from 5.0 to 10.0 out of 10, but it carries no weight in this view, so it did not change the score" and "it is weighted only for the investor persona" - served to a caller who asked for the investor persona, where growth carries 0.34 and drove the whole +1.7. comparison.attribution is an empty array, so the decomposition whose stated purpose is "the parts must add up to the whole, and a caller can check it" cites no driver at all. For family/quietlife/renter/commuter/firsttime/laterlife and for any accepted custom weight set the array is non-empty but carries balanced's weights and contributions, and the residual caveat actively denies the real cause ("rounding in the per-factor values, not a missing driver") when the missing driver is a real weighted component.

**Evidence.** build_comparison() hardcodes the balanced weight set for both the decomposition and the prose, while resolve_query() scored the borough with the caller's weights: app.py:386 current, previous, city, PERSONAS['balanced'], name, cur_bm, prev_bm, cur_ranks, prev_ranks app.py:398 'attribution': build_attribution(current, previous, PERSONAS['balanced']), build_attribution then does `for key, weight in weights.items(): ... if weight == 0: continue` (app.py:429-440) and build_why puts every zero-weight component into `unweighted` with the note "it carries no weight in this view" (app.py:634-651). Ran: python -c "...; body,_ = app.resolve_query({'borough':'Barking and Dagenham','city':'london','persona':'investor','compare':'previous'})" Output (verbatim): weights {'quiet':0.09,'afford':0.26,'growth':0.34,'live':0.17,'env':0.14} score 8.8 previousScore 7.1 scoreChange 1.7 attribution [] why.headline: 'Score unchanged at 8.8, even though the market moved.' why.unweighted[0].note: 'Growth moved from 5.0 to 10.0 out of 10, but it carries no weight in this view, so it did not change the score.' why.caveats[0]: 'Growth moved this quarter but is not counted in this view - it is weighted only for the investor persona...' Same effect with weights that merely differ from balanced. For Camden with persona=family the attribution publishes `weight: 0.27` for afford while the response's own `weight

**Why no gate catches it.** No test in the repo ever passes a persona alongside compare - verified by `grep -rn "'compare'" backend/tests/*.py tests/*.py`, which returns 7 hits, every one of them using the default (balanced) persona. test_compare_previous_includes_attribution (backend/tests/test_score.py:544) calls resolve_query({'borough':'Ealing','compare':'previous'}) with no persona, and test_attribution_contributions_reconcile_to_score_change (test_score.py:222) checks /v1/changes, which is balanced-only by construction (app.py:6858 `bal = PERSONAS['balanced']`). So the reconciliation gate only ever samples the one persona where the hardcode happens to be correct - an expectation that agrees with the code under test. scripts/check_score_sanity.py sends neither `persona` nor `compare` (grep returns no match for either). The frontend never calls compare, so tests/borough-score-parity.mjs and tests/site-api-parity.mjs cannot see it.

**Suggested fix.** Thread the caller's weight set through: give build_comparison a `weights` parameter and pass the same `weights` object resolve_query used for calc_score (app.py:6656-6663) into both build_attribution and build_why. handle_changes keeps passing PERSONAS['balanced'] explicitly because it genuinely is a balanced-only surface. Add a test that runs resolve_query for each of the eight personas with compare=previous and asserts abs(scoreChange - sum(contribution)) stays inside roundingResidual, and that build_why's `unweighted` list is empty whenever the requested persona weights that component.

**Verifier notes.**

- *? lens* (high confidence, severity called `important`): The finding is accurate on mechanism, line numbers and quoted output. Three corrections, all narrowing rather than widening: 1. **The loud failure is investor-only (plus growth-weighted custom sets), not "family/quietlife/renter/commuter/firsttime/laterlife" equally.** Measured across 33 London boroughs x 8 personas against the repo's own <0.2 reconciliation tolerance: investor 15/33 violations, w
- *? lens* (high confidence, severity called `critical`): The mechanism, the two line references (386, 398) and both worked examples are exact - I reproduced them verbatim, including against the live API. Four refinements a fix should carry: 1. **`roundingResidual` does not exist in the `comparison` block.** The suggested test asserts `abs(scoreChange - sum(contribution)) stays inside roundingResidual`, but that field is only emitted by `/v1/changes` (ap
- *? lens* (high confidence, severity called `critical`): Mechanism, line references and severity stand. Five corrections/additions: 1. LINE REFS: the `build_attribution` loop is app.py:427-441 (finding says 429-440) — a two-line drift, immaterial. 386, 398, 634-651, openapi 376 and 410 are all exact. 2. THE FINDING OVERSTATES ONE SUB-CASE: "for family/quietlife/renter/commuter/firsttime/laterlife ... the array is non-empty" is not reliably true. The arr

---

### F24 — [FIXED 2026-08-30] EA flood mosaic is mis-georeferenced: every partial edge tile is a stretched render pasted as if 10 m/px, so flood risk is read from up to 9 km away

| | |
|---|---|
| **Verification** | **UNVERIFIED** — verification did not complete for this finding |
| Location | `scripts/fetch_ea_flood_risk.py:156` |
| Category | data-derivation |
| Found by | Absence rendered as a confident me |

> **RESOLVED 2026-08-30.** `tile_px()` requests each tile at its real extent, so
> every tile is genuinely 10 m/px and the mosaic's existing assumption becomes
> true; the tile cache key gained the extent, without which the stale 2000x2000
> renders would have been served forever. Re-fetched, re-derived, area pages
> rebuilt. **37 of 81 boroughs moved, 13 changed band**: Sefton 31.39 -> **0.27**
> `high -> low`, within 0.01 of the 0.28 this finding predicted by hand; South
> Tyneside 10.94 -> **0.11**; Doncaster 24.38 -> **6.39**. **Teesside gained
> flood for the first time** (81 -> 86 boroughs) because a partial mosaic is now
> legal. Two further defects surfaced in the same file: Bristol's edge tile was
> cached ALL-ZERO from before the blank-render guard existed, and the mosaic
> initialised to `np.zeros` where 0 means "surveyed, no risk" - it is 255
> (Unavailable) now. Gated by `scripts/check_flood_georef.py`, which queries the
> EA's own GetFeatureInfo rather than re-deriving from the same mosaic. **Its
> first version passed the known-bad file 9 of 9**; the six interior tile blocks
> were byte-identical, so only periphery-first sampling can see this.


**Failure scenario.** A user opens the Sefton borough panel (or the public SEO page `area/merseyside/sefton/index.html`, which currently renders `Flood risk: High` with the note `Environment Agency RoFRS, risk after defences`). The panel prints `31.39% of this borough's postcodes sit at Medium or High risk, meaning a 1% or greater chance of flooding from rivers or the sea in any year`. The correct figure from the same EA tiles is 0.28%: the mosaic filled Sefton's rows with a vertically stretched copy of the Ribble/Southport coastal strip 20 km north. Since v3.9/v4.0 this is not just a map colour - `flood_to_score(31.39)` clamps to 0.0 where `flood_to_score(0.28)` is 9.72, so running the live Lambda's `get_env_score()` over the borough record gives environment 5.40 as shipped against 7.30 corrected. Same direction for South Tyneside (5.20 -> 7.10), Bury (5.60 -> 7.10), Doncaster (6.20 -> 7.00). At env's 0.14 balanced weight that is ~0.27 on the headline score, and it moves the `flood` map band from `high` to `low`. Rochdale and Tower Hamlets are wrong in the opposite direction - real risk understated.

**Evidence.** `fetch_tile` always requests 2000x2000 pixels regardless of the tile's ground extent: scripts/fetch_ea_flood_risk.py:156 raw = fetch_bytes(getmap_url(bbox, TILE_PX, TILE_PX)) but `fetch_city` builds the last tile of each row and column as a PARTIAL one (`e2, n2 = min(e + TILE_M, bbox[2]), min(n + TILE_M, bbox[3])`, line 219) and then pastes every tile assuming exactly 10 m/px: scripts/fetch_ea_flood_risk.py:236 mosaic = np.zeros((height, width), dtype='uint8') scripts/fetch_ea_flood_risk.py:243 mosaic[row : row + h, col : col + w] = codes[: height - row, : width - col] `city_bbox` rounds to 1 km, never 20 km (`fetch_defra_road_noise.py:126-129`), so a partial edge tile is the norm. Measured: `city_bbox('london')` = (501000,153000,565000,204000), so w%20000=4000 and h%20000=11000. VERIFIED THE TILES ARE STRETCHED, not padded. The top tile's LAST row and the tile below's FIRST row depict the same ground line (n=193000). Agreement, top-tile-last-row vs below-tile-first-row, against the naive-placement row and a baseline row: london spans 11000 m stretched-join 98.7% naive 93.2% baseline 94.5% merseyside spans 11000 m stretched-join 91.5% naive 66.0% baseline 66.5% southyorkshire spans 5000 m stretched-join 92.7% naive 69.4% baseline 74.6% tyneandwear spans 17000 m stretched-join 98.0% naive 84.9% baseline 95.5% manchester spans 5000 m stretched-join 99.2% naive 95.8% baseline 92.3

**Why no gate catches it.** `build_borough_bands.py --check` is the only gate that touches this field and it is (a) ADVISORY only (`scripts/preflight.sh:487 advise "borough bands == sources"`) and (b) re-derives from the same corrupt `data/ea_flood_risk_*.tif`, so it agrees with itself. `tests/test_borough_data_parity.py` compares the two holders - both carry the same wrong number. `tests/borough-score-parity.mjs` and `tests/area-page-freshness.mjs` compare site against Lambda - again the same number on both sides. `tests/layer-honesty.mjs` only asks whether a painted band has a legend row, never whether the band is right. `fetch_ea_flood_risk.py --verify` re-checks the colour-to-band mapping, which is correct; the defect is in the geometry after classification. Nothing in the repo compares any flood figure against the EA.

**Suggested fix.** Request each tile at its true pixel size - `w_px = (bbox[2]-bbox[0])//RES`, `h_px = (bbox[3]-bbox[1])//RES` - rather than the constant `TILE_PX`, and delete the whole `data/flood_risk_tiles/` cache before re-running (the cached partial tiles are unrecoverable at 10 m/px). Alternatively keep the fixed request size and resample on paste using each tile's declared extent. Two hardening points while in there: the tile filename `flood_{e}_{n}.npy` keys on the ORIGIN only, so two cities whose grids share an origin but not an extent would silently reuse the wrong tile (no clash today - I checked all 104 origins across 11 cities - but it is one bbox change away); and `mosaic = np.zeros(...)` makes an unwritten cell read as code 0, `not in any modelled risk polygon`, where `FLOOD_UNAVAILABLE` (255) is the honest initial value. Finally, add a re-derivation gate that can actually disagree - spot-check a handful of postcodes against the live RoFRS `risk_band` attribute the way `--verify` already does for colours.

---

### F25 — [FIXED 2026-08-29, ce0bf49] Every UK borough panel renders "undefined only here" under Environment — envCaveat() is passed the scored record, which never holds the three continuous fields it tests

| | |
|---|---|
| **Verification** | **CONFIRMED** — 5 of 5 verifiers could not refute it |
| Location | `index.html:11013` |
| Category | renders-a-value-it-did-not-verify |
| Found by | Absence rendered as a confident me, Frontend JavaScript correctness in (corroborated by 2 independent finders) |

**Failure scenario.** A user clicks any of the 86 UK boroughs on the live site (all 11 UK city-regions; NYC is unaffected). Under the Environment row, which shows a correctly-computed fully-measured score of e.g. 4.4/10, they read: "Air quality, road noise and flood risk. Weight: 14% · undefined only here, so not comparable with a fully-measured borough". The sentence is doubly false — the borough HAS all three inputs, and the input it names is the string "undefined". This is the same visible failure as the "FLOOD RISK UNDEFINED" metric cards fixed on 2026-08-11, in the row added three days ago to disclose partial coverage.

**Evidence.** Line 11013: `<div class="score-explain">Air quality, road noise and flood risk. Weight: <strong>${Math.round(pw.env * 100)}%</strong>${envCaveat(data, ev)}</div>`. `data` is the SCORED borough record — `updateSidebar({ name: selectedBorough, ...data })` at lines 7783/7808/12164/12331/12598, where the record is `{...d}` spread from `<CITY>_BOROUGH_DATA_RAW` (avg_price, trend, impact, note) plus scores. But envCaveat() at 7429 calls `envComponentScores(ex)` (7385), which reads `ex.airQualityWhoRatio` / `ex.roadNoiseAboveWhoPct` / `ex.floodMediumOrHighPct` — fields that exist ONLY in borough-extra.json, reachable via `cityOf(city).boroughExtra()` / `getExtraData()`. `grep -n 'airQualityWhoRatio\\|roadNoiseAboveWhoPct\\|floodMediumOrHighPct' index.html` returns lines 7389-7394 and 9336 only: never a raw-data literal. So `have = []`, the `have.length >= 3` early return never fires, `names = []`, and `list = names[0]` is `undefined`. I drove the real page (source tree served on localhost, Playwright, waited on `_boroughExtraHydrated === true`) and called the real `updateSidebar`. Camden's Environment row renders verbatim: "Air quality, road noise and flood risk. Weight: 14% · undefined only here, so not comparable with a fully-measured borough" Same for Leicester. Passing the CORRECT object returns `''` (`caveatWithExtra: ""`), which confirms the diagnosis and the fix. I then swept a

**Why no gate catches it.** `site == Lambda (91 boroughs)` (tests/borough-score-parity.mjs) reads `CITY_DATA[c].boroughData()[name].score` out of the registry — it never opens the sidebar, so it cannot see any rendered copy. `layers paint only real data` inverts SVG `fill` attributes. `responsive`, `map fits its box` and `WCAG source scan` ask about geometry, position and contrast, not text. `every city switches` counts outlines. Nothing in tests/ or tests/e2e/ contains the strings `score-explain`, `only here` or `not comparable` (`grep -rn 'score-explain\\|only here\\|not comparable' tests/` → no matches), so no gate has ever read this row. The full preflight was reported PASS on the commit that shipped it.

**Suggested fix.** DONE. envCaveat() now takes a borough name + city and resolves the record itself, as getEnvScore() does; an empty measured-input list exits early instead of naming itself. Guarded by tests/panel-caveat.mjs (blocking), proven red against the pre-fix tree. ORIGINAL SUGGESTION: Pass the borough-extra record, not the scored record: at line 11013 use the `extra` that updateSidebar already resolves for the metric cards (`getExtraData(data.name)`), i.e. `envCaveat(getExtraData(data.name), ev)`. Independently, make envCaveat() incapable of printing `undefined`: `if (!have.length) return '';` before building `names` — a caveat that cannot name a single input has nothing to disclose. Add an assertion to tests/borough-score-parity.mjs (it already opens the page and iterates every borough) that the rendered `.score-explain` text contains no `undefined`.

**Verifier notes.**

- *? lens* (high confidence, severity called `critical`): Four corrections, none of which weakens the finding, but the first changes the fix: 1. "The borough HAS all three inputs" is true for 81 of the 86, NOT all 86. Teesside's five (Hartlepool, Middlesbrough, Redcar and Cleveland, Stockton-on-Tees, Darlington) genuinely carry only two — `airQualityWhoRatio` and `roadNoiseAboveWhoPct`, no `floodMediumOrHighPct`. Measured with the suggested fix applied i
- *? lens* (high confidence, severity called `critical`): Three corrections, none of which weakens the finding: 1. "all 11 UK city-regions" is wrong by one. The site carries 10 UK city-regions plus NYC = 11 cities. The 86 affected boroughs span TEN UK cities (measured: london 33, manchester 10, leicester 8, westmidlands 7, westyorkshire 5, merseyside 5, tyneandwear 5, teesside 5, southyorkshire 4, bristol 4). NYC's 5 are suppressed by the `ev === null` g
- *? lens* (high confidence, severity called `critical`): Three corrections, none of which weaken the finding: 1. THE SUGGESTED FIX NAMES A BINDING THAT IS NOT IN SCOPE. "use the `extra` that updateSidebar already resolves for the metric cards" is wrong: `const extra = getExtraData(data.name)` at index.html:11035 lives inside an IIFE embedded LATER in the same template literal that line 11013 is part of, so it cannot be referenced at 11013. The concrete 
- *? lens* (high confidence, severity called `critical`): Three corrections, none of which weaken the finding: 1. THE SUGGESTED FIX AS WRITTEN WOULD THROW. It says to "use the `extra` that updateSidebar already resolves for the metric cards". `extra` is NOT in scope at line 11013: it is `const extra = getExtraData(data.name)` declared at line 11033, inside a later arrow-function IIFE (`${(() => { ... })()}`) embedded in the same template literal, several
- *? lens* (high confidence, severity called `critical`): Four corrections, none of which weaken the finding: 1. IT IS LIVE, not source-only. The finding describes the source tree. I fetched the deployed CloudFront copy — it is byte-identical to `index.html` at HEAD, and clicking Camden on https://d1oe4ftwutjpf.cloudfront.net renders the broken row today. This is a production defect, not a pre-deploy one. 2. THE FIX IS NOT PURE SUPPRESSION — it restores 

---

### F26 — London's aircraft raster is declared painted from an href attribute, and `layer-honesty.mjs` reads the same attribute - a 404 on the PNG renders a confident five-band decibel legend over nothing and the gate passes

| | |
|---|---|
| **Verification** | **CONFIRMED** — 4 of 4 verifiers could not refute it |
| Location | `index.html:8825` |
| Category | absence-as-measurement |
| Found by | Absence rendered as a confident me, Can any gate report success while  (corroborated by 2 independent finders) |

**Failure scenario.** `/data/aircraft-noise-london-lden.png` goes missing at the CloudFront origin - a web-only deploy that skips `data-deploy`, an S3 lifecycle rule, a rename, or a Round 5 refresh that writes a new filename. Every London visitor who turns on the aircraft layer sees the legend title "DEFRA AIRCRAFT NOISE (dB Lden)" above five confident colour bands (55-59, 60-64 ... dB) with no contours on the map. The legend does not append "(NO DATA)" because `markLayerCoverage()` is told the raster painted. `layers paint only real data` reports PASS on every run thereafter, because both sides of its comparison agree that a surface is present. This is the same failure the same commit fixed for NYC, where it was measured live: "tile count 2 at ~200 ms, 0 from 400 ms onward... with the scale shown throughout."

**Evidence.** index.html:8815-8827 sets the image href and then, unconditionally, the coverage flag: d3.select('#defra-aircraft-img').attr('xlink:href', url).attr('href', url)... aircraftRasterLoadedFor = 'london'; aircraftScalePainted = true; There is no `onload`/`onerror` on `#defra-aircraft-img`; line 8797 sets the same flag true again on a repeat call. `tests/layer-honesty.mjs`:360-368 measures the same thing: const hasRaster = Boolean( (img && (img.getAttribute('href') \|\| img.getAttribute('xlink:href'))) \|\| (tiles && tiles.querySelectorAll('image[data-loaded]').length > 0) ); The NYC half was fixed today (commit 4b2429e, 19:59) with a comment in that very file reading "image[data-loaded], not image. A tile element whose href has not come back paints NOTHING, so counting elements reports a surface that is not on the map - which is the very thing this check exists to catch, made by the checker." The London half is still `getAttribute('href')`. PROVEN by a read-only harness that serves the unmodified working tree and answers 404 for exactly one path, then evaluates the gate's own expression. Baseline (PNG served 200) and broken (PNG served 404) produce byte-identical readings: {"hasRaster":true,"scaleShown":true,"saysNoData":false,"title":"DEFRA AIRCRAFT NOISE (dB Lden)","href":"/data/aircraft-noise-london-lden.png"} layer-honesty aircraft assertions: WOULD PASS (scaleShown!==hasRaster

**Why no gate catches it.** `layer-honesty.mjs` is the only gate that looks at the aircraft layer at all, and its London branch takes its evidence from the presence of an attribute rather than from a load event - the exact substitution its own NYC branch was rewritten to avoid twenty minutes earlier. Its two integrity floors (`totalExpected === 0` and `totalBandRows === 0`) cover the three borough fill layers and the legend rows; there is no equivalent floor asserting that any city ever painted an aircraft surface, so London and NYC both collapsing to zero would also pass. `check_deploy_drift.sh` compares 16 surfaces and none is under `data/`. `map-fit.mjs` measures borough paths, `city-switch.mjs` counts outlines, `responsive.mjs` asks about controls - a raster image is none of those. `a11y-source.mjs` does not evaluate whether an image resolved.

**Suggested fix.** Give `#defra-aircraft-img` the same `onload`/`onerror` treatment the NYC tiles now have: set `aircraftScalePainted` from the load event (and a deadline), and stamp `data-loaded` on success. Then change `tests/layer-honesty.mjs`:360 to require `img.getAttribute('data-loaded')` rather than an href, and add a floor asserting that at least one city painted an aircraft surface, so both sides cannot collapse to zero together.

**Verifier notes.**

- *? lens* (high confidence, severity called `important`): Severity: important, not critical. No user or API caller is affected today — `/data/aircraft-noise-london-lden.png` returns 200 with 45,659 bytes (matching the tracked file) at both `d1oe4ftwutjpf.cloudfront.net` and `skyscore.co.uk`. The raster is display-only and is not a scoring input, so no published number, score or API response can move; the harm is a legend claiming a dB scale over an empty
- *? lens* (high confidence, severity called `important`): Severity: downgraded critical -> important. Nothing is broken for any user today, and the auditor's own evidence shows it: the baseline and broken readings are identical because the baseline is healthy. `/data/aircraft-noise-london-lden.png` is git-TRACKED (not gitignored), CloudFront serves it 200 at 45,659 bytes (verified live), and `mobile/scripts/copy-web.mjs` lists it in `REQUIRED_DATA` and `
- *? lens* (high confidence, severity called `important`): 1. SEVERITY: important, not critical. No user or API caller is affected today. The live PNG is 200/45,659 bytes at CloudFront, identical to the tracked copy; it is in git, in `make data-deploy` (Makefile:263) which `web-deploy-all` (Makefile:391) runs, and in the native bundle's REQUIRED_DATA allow-list (mobile/scripts/copy-web.mjs:106) behind a FATAL missing-file check. The NYC half was critical 
- *? lens* (high confidence, severity called `important`): Severity: `critical` -> `important`. The defect and the gate blindness are both proven, but the origin copy is live and healthy (200, 45,659 bytes, identical to the tracked file on both CloudFront and skyscore.co.uk), so nothing is being mis-rendered today and no scored value is affected in any scenario — the failure needs a deploy/lifecycle mistake or a per-user fetch failure to fire. Mechanism, 

---

### F30 — [FIXED 2026-08-30]  CI has executed neither test suite since 24 July: both test jobs are skipped because their `needs` lint jobs fail on formatting checks that can never go green

| | |
|---|---|
| **Verification** | **CONFIRMED** — 3 of 3 verifiers could not refute it |
| Location | `.github/workflows/ci.yml:35` |
| Category | check-that-cannot-fail |
| Found by | Can any gate report success while  |

**Failure scenario.** Push any commit to master. `lint-frontend` and `lint-backend` fail on formatting; `test-backend` and `test-e2e` are skipped. `backend/tests/test_score.py` (182 KB, including today's 18 new EnvironmentComponentTests), `backend/tests/test_liveability.py`, the 167-test root `tests/` suite and the whole Playwright e2e never execute. A commit that breaks `calc_score` outright, or that deletes a Lambda handler's CORS headers, is merged to master with a CI status that looks exactly the same as every other commit for the last five weeks - red for the formatting reason everyone has learned to ignore. The repo is public, so this is also the only signal an outside contributor gets, and it tells them the tests ran and something failed.

**Evidence.** ci.yml declares four jobs. `lint-frontend` (line 20) runs `npm run format:check` = `prettier --check index.html`; `lint-backend` (line 31) runs `ruff format --check backend/lambdas/`. `test-backend` has `needs: lint-backend` (line 35) and `test-e2e` has `needs: [lint-frontend, lint-backend]` (line 57). GitHub Actions SKIPS a job whose `needs` job failed. I ran both formatting commands on the current tree: `python -m ruff format --check backend/lambdas/` -> "5 files would be reformatted, 3 files already formatted", exit 1; `npx prettier --check index.html` -> "Code style issues found", exit 1. preflight.sh:447-453 documents the prettier state as permanent and deliberate: "every HTML/JS file in the repo deviates... Reporting it as blocking would make the gate permanently red". Live CI confirms the consequence: `gh run list --workflow=ci.yml --limit 100` returns 93 failures / 7 successes, the last success 2026-07-24T21:25Z. `gh run view 33269686898 --json jobs` (the run for today's v4.0 wave) returns exactly: lint-backend\tfailure lint-frontend\tfailure test-backend\tskipped test-e2e\tskipped Note also that `ruff format --check` is in NO preflight stage - preflight only runs `ruff check` - so the backend half of this is invisible from the local gate as well.

**Why no gate catches it.** preflight.sh is the local gate and is unaware of CI: it runs `ruff check` but not `ruff format --check`, and it classifies prettier as advisory precisely so a permanent deviation does not block. Nothing in the repo asserts that CI's job graph can reach its test jobs. The CI run is red, so it does not read as a false green - it reads as the known-and-tolerated formatting noise, which is worse: the red carries no information about whether the tests ran. This is the mirror of the documented `feedback-a-gate-that-cannot-go-green` lesson ("check whether a red gate RAN at all"), applied to a whole workflow rather than one harness.

**Suggested fix.** Break the dependency between formatting and testing. Either drop `needs:` from `test-backend`/`test-e2e` so they run regardless, or move `npm run format:check` and `ruff format --check` into their own non-blocking job (`continue-on-error: true`), matching preflight's own advisory classification. Then confirm with `gh run view <id> --json jobs` that `test-backend` and `test-e2e` report a conclusion other than `skipped`.

**Verifier notes.**

- *? lens* (high confidence, severity called `important`): 1. THE SUGGESTED FIX IS INCOMPLETE AND WOULD PRODUCE A NEW RED, NOT A GREEN. Dropping `needs:` from `test-backend` is necessary but not sufficient: CI installs only `pytest pytest-mock boto3` (ci.yml line 41), and the root `tests/` suite has since acquired unguarded third-party imports. Reproduced by simulating that dependency set — `tests/test_empty_source_guards.py` (added 2026-08-21, i.e. AFTER
- *? lens* (high confidence, severity called `important`): Four corrections; none changes the conclusion, but a fix written from the uncorrected version would misattribute the blocker. 1. SEVERITY: critical -> important. The failure_scenario's "is merged to master with a CI status that looks exactly the same as every other commit" is true of CI but omits that `scripts/preflight.sh` - mandated before every commit by CLAUDE.md - runs both pytest suites (lin
- *? lens* (high confidence, severity called `important`): 1. TEST COUNT IS STALE. The finding says "the 167-test root `tests/` suite". Collected today: root `tests/` = 254 tests, `backend/tests/` = 358. The 167 figure predates roughly a year of additions and should not be quoted in the fix. 2. "CAN NEVER GO GREEN" IS A POLICY CLAIM, NOT A TECHNICAL ONE, AND ONLY FOR HALF OF IT. The prettier half is genuinely a standing decision (preflight.sh:447-452: a 1

---

### F38 — Every borough band is weighted by RETIRED postcodes: 39.2% of the sample no longer exists, and the guard that looks like it excludes them removes only 1.25% of them

| | |
|---|---|
| **Verification** | **UNVERIFIED** — verification did not complete for this finding |
| Location | `scripts/build_borough_bands.py:266` |
| Category | absence-rendered-as-measurement |
| Found by | The 44 data-derivation scripts und |

> **STILL OPEN - and the note that used to sit here belonged to F24.** A copy of
> the flood-mosaic resolution (`tile_px()`, Sefton 31.39 -> 0.27) was pasted
> under this finding on 2026-08-30, stamping the report's most valuable open
> item "RESOLVED". That text describes `fetch_ea_flood_risk.py`; **F38 is about
> `build_borough_bands.py` never reading NSPL's `doterm`** - an unrelated file
> and an unrelated defect. Corrected 2026-08-31. The surviving copy under F24
> is the correct one.
>
> **Re-confirmed by direct measurement 2026-08-31**, outside the agent pipeline
> that left it UNVERIFIED. `grep -n doterm scripts/build_borough_bands.py`
> still returns nothing, while `build_aircraft_quiet_dataset.py`,
> `build_city_neighbourhoods.py`, `load_nspl.py` and
> `probe_aircraft_raster_coverage.py` all filter on it. A full pass over
> `data/nspl.csv` reproduces every figure below **exactly**: 2,723,596 rows,
> **915,867 terminated**, of which only **11,414 (1.25%)** sit at `lat > 90`
> and **904,453 pass straight through** into every derived band. The 12,789
> live-but-parked rows are what the filter is actually for.


**Failure scenario.** Leicester's `transportWithin800mPct` is published as 26.7% and banded `moderate`; over live postcodes only it is 12.0% and bands `poor`. Hinckley and Bosworth 22.5% -> 10.5%. Bath and North East Somerset 25.8% -> 16.9% (`moderate` -> `poor`). Transport is 0.25 of the liveability component in BOTH holders, so the wrong band is served by /v1/score and rendered by the site identically. Feeding the corrected bands through `resolve_query` moves published headline scores: Ealing `live` 8.3 -> 7.6 and score 5.7 -> 5.5; Richmond upon Thames 5.0 -> 4.8; Bexley 8.6 -> 8.4; Enfield 8.4 -> 8.2. On the v4.0 environment inputs: Islington's `roadNoiseAboveWhoPct` 75.3 -> 65.1 (band `high` -> `moderate`), Redbridge 72.1 -> 62.0, Richmond 68.6 -> 56.7, and Kingston upon Thames's `floodMediumOrHighPct` 20.02 -> 5.69 (band `high` -> `medium`). The bias is not random: retired postcodes cluster in redeveloped inner-urban blocks near stations (and duplicate a single coordinate many times, as the two EC1A rows show), so transport access is systematically over-stated where churn is highest.

**Evidence.** `collect_postcodes()` is the single NSPL pass behind transport, healthcare, road noise, flood and air quality for all 91 boroughs. It never reads NSPL's `doterm` column (date of termination) - `grep -n doterm scripts/build_borough_bands.py` returns nothing. Its only filter is lines 266-268: # NSPL parks terminated/unlocatable postcodes at (99.999, 0.0). if lat > 90 or lat < -90: continue That comment is the defect: it reads as "terminated postcodes are excluded" and the test excludes only UNLOCATABLE ones. Measured over the whole 2,723,596-row data/nspl.csv: 915,867 rows are terminated, of which only 11,414 (1.25%) sit at lat>90; **904,453 terminated postcodes carry real coordinates and pass straight through**. (12,789 LIVE postcodes are also parked at lat>90, which is what the parking rule is actually about.) Sampled rows confirm it - E09000019 (Islington) contains `EC1A 1TD doterm=201812 lat 51.524567 lon -0.112017` and `EC1A 1XA doterm=201812` at the identical coordinate. Across the twelve cities the script derives, 373,642 of 952,582 sampled postcodes (39.2%) are terminated - London 45.5%, Cardiff 58.2%, Leicester 35.1%. The repo already knows what "live" means and disagrees with itself: backend/lambdas/score/app.py:4263 records "180,983 live London postcode centroids", and my live-only London count is **exactly 180,983** while build_borough_bands.py uses 332,308. Two sibli

**Why no gate catches it.** `build_borough_bands.py --check` (the advisory `borough bands == sources` stage) re-derives from the same NSPL with the same inclusion rule, so it compares the file against itself and prints "borough-extra.json agrees with DEFRA on every derived field" - I ran it and it passed. `tests/test_borough_data_parity.py` compares borough-extra.json against the Lambda's CITIES, and `--write-lambda`/`--sync-lambda` copy the same number into both, so both holders hold the same wrong value and the parity gate is green by construction. `tests/borough-score-parity.mjs` compares the score the SITE renders against the Lambda's - both computed from that same input. `tests/layer-honesty.mjs` asserts only that a borough with a reading is painted and one without is not; a wrong reading is still a reading. `scripts/check_score_sanity.py` asserts discrimination and range, never whether a share is correct. Nothing in the 32 stages ever compares a live-postcode count with an all-postcode count.

**Suggested fix.** Read `doterm` in `collect_postcodes()` and skip any row where it is non-empty, exactly as build_city_neighbourhoods.py:669 and build_aircraft_quiet_dataset.py:152 already do; correct the comment at line 266, which describes locatability and not termination. Then re-run `--write --write-lambda` and re-run build_area_pages.py --write, since 55 band values across 91 boroughs move. Consider extracting the one NSPL row filter into a shared helper so the three scripts cannot disagree about what a postcode is again.

---

### F39 — [FIXED 2026-08-30, with F24] The EA flood mosaic misregisters every city's edge tiles: partial tiles are rendered at 2000x2000 px whatever their extent, then placed as if they were 10 m/px, stretching real flood polygons by up to 5x

| | |
|---|---|
| **Verification** | **UNVERIFIED** — verification did not complete for this finding |
| Location | `scripts/fetch_ea_flood_risk.py:156` |
| Category | unit-projection-error |
| Found by | The 44 data-derivation scripts und |

**Failure scenario.** Sefton (Merseyside) publishes `floodMediumOrHighPct: 31.39` and `flood: "high"` - the highest flood figure in the whole dataset. Correctly georeferenced it is 0.28%, i.e. `low`. South Tyneside publishes 10.94 (`high`); correct value 0.09 (`low`). Doncaster 24.38 (`high`) vs 6.38 (`medium`). Bury 8.51 (`medium`) vs 0.78 (`low`). Also wrong-banded: South Gloucestershire, Melton, Enfield, Hackney, Hillingdon, Newham, Redbridge, Barnsley, Gateshead. Two consequences, both live: the map paints those boroughs in the wrong flood colour under a legend that says the data is measured, and since v3.9/v4.0 `floodMediumOrHighPct` is a scored input (0.20 of `environment`) held in BOTH score holders. Running the corrected values through the Lambda's own `get_env_score`/`resolve_query`: Sefton environment 5.40 -> 7.30 and headline 5.5 -> 5.8; South Tyneside 5.20 -> 7.10 and 7.3 -> 7.6; Bury 5.60 -> 7.10 and 7.5 -> 7.7; South Gloucestershire 6.90 -> 7.90 and 7.4 -> 7.6.

**Evidence.** `fetch_tile()` always asks the WMS for a fixed-size image regardless of how big the bbox is - line 156: `raw = fetch_bytes(getmap_url(bbox, TILE_PX, TILE_PX))` with TILE_PX = 2000. The tile grid at lines 216-222 clamps the last row and column: `e2, n2 = min(e + TILE_M, bbox[2]), min(n + TILE_M, bbox[3])`, so edge tiles cover less than 20 km but are still rendered into 2000 px. The mosaic at lines 234-243 then assumes a uniform `res = TILE_M // TILE_PX` = 10 m/px for every tile. Every city has partial edge tiles - `city_bbox()` rounds to 1 km, not 20 km. Measured spans: London 64000x51000 (remainder 4000x11000), Leicester 69000x71000 (9000x11000), Merseyside 49000x51000 (9000x11000), Tyne and Wear 38000x37000 (18000x17000). All 103 cached .npy tiles are 4,000,128 bytes = 2000x2000 + header, confirming edge tiles are the same pixel size as full ones. Proved three independent ways, entirely offline: 1. Placement: for London, `mosaic[0:2000, 0:2000]` is byte-identical to flood_501000_193000.npy (a tile covering only N 193000-204000, 11 km) while the mosaic transform claims those rows span N 184000-204000, 20 km; `mosaic[2000:3100]` equals `mid[900:2000]`, i.e. the correctly-placed mid tile was partly overwritten by the stretched top tile. 2. Anisotropy: mean vertical/horizontal run-length of risk pixels is 0.95-1.07 in the four full 20x20 km tiles (isotropic, as expected), 1.49-1.6

**Why no gate catches it.** `build_borough_bands.py --check` samples data/ea_flood_risk_<city>.tif - the same mosaic - so it re-derives the identical wrong number and reports agreement; I ran it and it printed "borough-extra.json agrees with DEFRA on every derived field". Both score holders carry that number, so `tests/test_borough_data_parity.py` and `tests/borough-score-parity.mjs` compare two copies of it. `tests/layer-honesty.mjs` only checks that a borough with a reading gets painted. The script's own `--verify` mode checks the colour-to-band mapping at a single 8 km sample near Ipswich and never looks at the tiling geometry at all, and it needs the network so it is in no preflight stage. The `nz == 0` guard added at line 185 catches a wholly blank tile but a stretched tile is full of real classified pixels. Nothing in the repo has ever compared the mosaic back to the EA service's own `risk_band`.

**Suggested fix.** Request each tile at its true size - `getmap_url(bbox, (e2-e)//res, (n2-n)//res)` - or, better, pad the bbox in `city_bbox()` up to a whole multiple of TILE_M so every tile is full-size, and assert `codes.shape == ((n2-n)//res, (e2-e)//res)` before writing it into the mosaic so a mismatch fails loudly. Delete the affected cached tiles, refetch, then re-run `build_borough_bands.py --write --write-lambda` and `build_area_pages.py --write`. Worth adding a preflight-able check that samples a handful of postcodes from the mosaic and compares against the WMS GetFeatureInfo `risk_band`, which is the only thing that can catch a geometry fault in a decoded image.

---

### F41 — [FIXED 2026-08-30]  The native bundle's data allow-list is still the four files it had on 3 August, so a Capacitor build ships without 9 of 11 cities' boundaries and every font in the atomic precache set

| | |
|---|---|
| **Verification** | **UNVERIFIED** — verification did not complete for this finding |
| Location | `mobile/scripts/copy-web.mjs:102` |
| Category | stale-mirror-fails-open |
| Found by | completeness critic — subsystems a |

**Failure scenario.** Codemagic's ios-workflow runs `npm run build:web` (codemagic.yaml:67). copy-web.mjs finds all four of its listed files, prints `done`, exits 0, and the build proceeds. In the resulting app: (1) a user taps the Greater Manchester chip and gets "Greater Manchester borough outlines could not be loaded" — the same for West Midlands, West Yorkshire, South Yorkshire, Merseyside, Tyne and Wear, Bristol, Leicester and Teesside, i.e. 9 of the 11 cities on the switcher; (2) `cache.addAll` rejects on the first missing entry, so the service worker never installs and the app has no offline shell at all — the exact atomic-failure mode the file's own comment cites for nyc-boroughs.json; (3) /data/aircraft-quiet-london.json and /data/aircraft-quiet-regions.json 404 inside the bundle, so every postcode result scores aircraft quiet from flight-path geometry while /v1/score answers the same postcode from the DEFRA raster — the site/API divergence the Makefile's data-deploy comment calls "LOAD-BEARING FOR CORRECTNESS", reopened for 42,691 measured postcodes, with a console.warn on a phone as the only signal.

**Evidence.** copy-web.mjs:102 declares the complete data allow-list: const REQUIRED_DATA = [ 'borough-extra.json', 'london-boroughs.json', 'nyc-boroughs.json', 'aircraft-noise-london-lden.png', ]; and the only directories copied are icons/, js/ and prototype/ (lines 74-84). fonts/ is copied nowhere. I reproduced the copier's rules against sw.js's SHELL_ASSETS with node (read-only): SHELL_ASSETS entries: 20 NOT copied into mobile/www by copy-web.mjs: 12 /data/manchester-boroughs.json, /data/westmidlands-boroughs.json, /data/westyorkshire-boroughs.json, /data/southyorkshire-boroughs.json, /data/merseyside-boroughs.json, /data/tyneandwear-boroughs.json, /data/bristol-boroughs.json, /data/leicester-boroughs.json, /data/teesside-boroughs.json, /fonts/fonts.css, /fonts/inter.woff2, /fonts/jetbrains-mono.woff2 The last-built bundle on disk confirms it, not just my model of it: `ls mobile/www` shows no fonts/ directory at all, and `ls mobile/www/data` shows exactly aircraft-noise-london-lden.png, borough-extra.json, london-boroughs.json, nyc-boroughs.json. Dates (git log): the allow-list landed 2026-08-03 (3b31ca9). Fonts joined SHELL_ASSETS 2026-08-06 (daa7270), Manchester 2026-08-09 (1d8c67e), six regions 2026-08-10, Leicester and Teesside 2026-08-11 (601d89e). Every entry it misses was added after it was written. sw.js:290 is `cache.addAll(SHELL_ASSETS)` — atomic. index.html:8175 loadCityBoundar

**Why no gate catches it.** Nothing runs copy-web.mjs outside the cloud build. I grepped preflight.sh, package.json, Makefile, .github/workflows and codemagic.yaml for copy-web / REQUIRED_DATA / build:web: the only hits are codemagic.yaml:67 and mobile/package.json:7. None of preflight's 32 stages touches the mobile bundle, and no test compares REQUIRED_DATA against SHELL_ASSETS or against index.html's /data/ fetches. The allow-list was introduced precisely to replace an extension filter that "fails open: add a file, get no error, ship without it" — but a STATIC allow-list fails closed only for the files already on it; adding a twelfth boundary file still produces a green build.

**Suggested fix.** Derive the copy set instead of listing it: parse SHELL_ASSETS out of sw.js and the /data/ literals out of index.html at build time, copy exactly that union (fonts/ included), and fail the build if any SHELL_ASSETS entry is absent under www/ after the copy. That makes the mobile bundle re-derive itself whenever a city is added, which is the event that broke it three times over.

---

## 2. Important

| # | Verified | Issue | Location | Failure scenario |
|---|---|---|---|---|
| F2 | UNVERIFIED | The live OpenAPI spec declares `enum: [london, nyc]` in four places, so a spec-validating client rejects 11 of the 13 cities the API serves | `score-demo/openapi.yaml:374` | An integrator generates a client from the published spec (which is the stated purpose — README lists it as "OpenAPI 3.0 spec" and it is rendered at /score-demo/api-docs.html). The generated `City` type has two members. `GET /v1/score?postcode=M1 1AE` returns `location.city: "manchester"`, which fails deserialisation or response validation |
| F3 | UNVERIFIED | Every public B2B surface still describes a four-component score three days after `env` shipped: the OpenAPI schemas, the API landing page and the live | `api/index.html:224` | A prospect runs the browser demo on a London postcode. They see Quiet 32%, Affordability 27%, Growth 0%, Liveability 27% — 86% — and a headline score they cannot reproduce from the bars shown, because 14% of it (the environment component, which just moved the median environment score by more than a point) is invisible. They then read api/ |
| F4 | UNVERIFIED | METHODOLOGY.md tells B2B auditors in three places that road noise does not score, including a block edited today for v4.0 | `METHODOLOGY.md:1508` | A conveyancer or lender doing the methodology audit this document exists for reads §3 and §7.1, concludes Sky Score's number contains no road-noise term, and either (a) buys a separate road-noise product believing there is no overlap, or (b) signs off the score as road-noise-free for a decision where double-counting matters. Meanwhile the |
| F5 | **FIXED 2026-08-30** | README's v4.0 headline says 90 of 99 boroughs are "fully measured" for environment; the code says 85, and README's own three numbers sum to 104 | `README.md:18` | README is the first page of the source-available repo the methodology audit is run against, and its first screen is the v4.0 summary. A reader takes "90 of 99 fully measured" as the coverage figure and cites it, when 5 of those 90 are Teesside boroughs scored on two inputs of three with no flood data at all — the exact boroughs the v4.0 f |
| F9 | UNVERIFIED | A DynamoDB read failure makes /v1/environment and /v1/score assert that DEFRA has no contour at a postcode DEFRA has measured | `backend/lambdas/score/app.py:4090` | DynamoDB throttles or the client cannot be built (a region/config change, a PAY_PER_REQUEST ramp under the loader's write workers - the case _DDB_TIMEOUT_CONFIG's comment anticipates). A request to the unauthenticated GET /v1/environment?lat=51.47&lon=-0.4543 - the endpoint the public browser extension renders on Rightmove listings - retu |
| F14 | **FIXED 2026-08-31** | The demo-key scope gate cannot fail while the demo key is out of monthly quota - and it is out of quota right now | `tests/demo-key-scope.mjs:34` | Someone edits `backend/template.yaml` and drops the `/v1/chat/POST` and `/v1/score/batch/POST` Throttle entries from `ScoreDemoUsagePlan` (lines 615-623), or API Gateway changes how it reads RateLimit 0. Because the demo key's 2,000/month quota is currently exhausted, every request with that key returns 429 regardless, so both assertions  |
| F15 | **FIXED 2026-08-31** | The free-tier deny assertions - the ones the code calls load-bearing - have never run, because their env var exists nowhere in the repo | `tests/demo-key-scope.mjs:172` | The `ScoreFreeUsagePlan` per-method denies (backend/template.yaml lines 540-547) stop working - removed in an edit, or lost to the CloudFormation MethodSettings/Throttle ordering trap the same file documents twice. Free-tier keys are minted by `/v1/signup`, which is UNAUTHENTICATED and needs only an unverified email address, so anyone can |
| F16 | UNVERIFIED | /v1/signup writes an unverified third party onto the score-update list, and that write permanently locks the real owner out of self-service API signup | `backend/lambdas/signup/app.py:432` | An attacker scripts POST /v1/signup with `source: consumer` against a list of addresses at the per-route ceiling of 1 RPS (backend/template.yaml:71-74) = 86,400/day. Three effects, all verified above: (a) every unknown address is written into `london-flight-map-signups` as a consented subscriber, kept under 35-day PITR, on a list whose ow |
| F17 | UNVERIFIED | /nhs is unauthenticated, holds a Lambda for up to 26 seconds per request, and is the one route with no per-method throttle | `backend/template.yaml:52` | An attacker sends 50 RPS of `GET /nhs?lat=56.5&lon=-4.2` (any coordinate outside the London snapshot bbox, so `in_bundle_area` is false and every request reaches Overpass). Two consequences, neither needing a key: (1) the stage-wide 50 RPS bucket is fully consumed by /nhs, so paying customers' `GET /v1/score` requests are rejected at the  |
| F19 | UNVERIFIED | chat's grounding control whitelists exactly the 0-10 range every Sky Score number lives in, so a hallucinated score passes as grounded | `backend/lambdas/chat/app.py:138` | A caller POSTs `{"postcode":"SE1 7PB","question":"how quiet is it?"}` to /v1/chat for a borough whose real payload is `score: 4.1, components.quiet: 2.0`. Nova Lite (temperature 0.2, and reachable by prompt injection through the free-text `question` field, which is interpolated into the user message at line 176 with no separation from the |
| F20 | UNVERIFIED | transport silently drops line statuses at big interchanges, in a non-deterministic subset, while reporting lineStatusAvailable: true | `backend/lambdas/transport/app.py:69` | A user searches N1C 4AG (King's Cross) while the Piccadilly line is suspended. The Lambda gathers 14 line ids, `list(line_ids)[:10]` happens to drop 'piccadilly' (it did in two of my four sample orderings), TfL is asked about the other ten and answers 'Good Service' for all of them. The response is `lineStatusAvailable: true` with ten Goo |
| F21 | UNVERIFIED | A failed or slow /nhs or /transport call leaves the panel's "Loading..." placeholder up permanently, so both Lambdas' honest degraded responses are un | `index.html:9807` | A London postcode whose bundled snapshot has no service within 1500 m (measured below: 8.4% of Greater London's area) falls through to live Overpass. Overpass from Lambda competes for AWS's shared-IP budget — the documented, measured reason the bundle exists — and takes 12s. At 8s the browser aborts with TimeoutError, fetchNhsData returns |
| F27 | UNVERIFIED | fetchTransportData turns any non-2xx /transport response into `available: true`, so a Lambda 5xx renders as "stations found, no line disruptions" | `index.html:9442` | `/transport` returns 500 (the Lambda's own final guard at `transport/app.py:88-89`), or API Gateway returns 502/504 on a Lambda timeout, or the key/route is throttled. A London user searching SW1A 1AA sees four stations with distances under `NEAREST STATIONS (LIVE TfL DATA)` and no line-status section at all. Per the codebase's own reason |
| F28 | UNVERIFIED | When borough-extra.json fails to load, every borough score silently INFLATES and the notice explaining it describes arithmetic the code does not do | `index.html:7826` | A CloudFront blip, a corporate proxy, or an S3 permissions error makes /data/borough-extra.json 403 or time out twice. Every borough on the site now scores ~1.0 point HIGHER than /v1/score returns for the same borough (Camden 7.6 vs 6.6), because dropping liveability and environment removes the two components London boroughs score worst o |
| F31 | **FIXED 2026-08-31** | The two gates that assert the web/native layout split are wired into no runner, and two of the three contexts inside one of them assert nothing at all | `tests/native-sim-render.mjs:130` | The tabbed layout became the web default at <=900px on 2026-08-27 (index.html:4096-4121, `applyTabbedLayout()`), with `?tabbed=0` as the documented opt-out. If a later CSS or JS edit breaks the `?tabbed=0` classic path - `#sheet-handle` never shown, `is-tabbed` not removed - nothing in the repo notices: the only assertion of that path liv |
| F32 | UNVERIFIED | All 99 area pages publish a component breakdown that omits `environment` - 14% of every score - while including `growth`, which carries 0% weight; the | `scripts/build_area_pages.py:137` | A visitor or a search crawler lands on /area/london/camden/. The page states "6.6 Sky Score out of 10" and then a table of Quiet skies 10.0, Affordability 4.7, Growth 3.6, Liveability 5.5. Those four cannot produce 6.6 under any published weighting - they produce 6.92 - and the row that reconciles them (Environment 4.4, the component that |
| F34 | **FIXED 2026-08-31** | The a11y gate's FAIL_MODERATE set can never fire - all four rules are excluded by the tag filter directly above it, and two of them are violated today | `tests/a11y-source.mjs:172` | privacy.html and terms.html - the legal pages - ship with no `<main>` landmark and 38 and 46 content nodes respectively outside any landmark. A screen-reader user pressing the 'jump to main content' shortcut on either page lands nowhere and has to traverse the whole document. The gate that exists to stop exactly this prints OK for both an |
| F35 | **FIXED 2026-08-31** | The 100 pages under area/ are in no accessibility or responsive gate at all, and every one of them ships without a main landmark | `tests/a11y-source.mjs:53` | A screen-reader user landing on any of the 99 borough pages from search - which is the entire reason the pages exist - gets a document with no main landmark and all of its content, including the score headline and the 15-row measurement table, outside any landmark. More importantly the whole surface is ungated: scripts/build_area_pages.py |
| F36 | UNVERIFIED | On every phone width the result card's close button is 69% covered by the sticky search card - live in production, on the default mobile layout | `index.html:3151` | A visitor on a phone (tabbed layout is the web default at <=900px since 2026-08-27, index.html:4119) searches a postcode or taps a borough. The result card opens over the map. The `×` that returns them to the map is painted under the floating white search card - visually a stray mark, and a tap at its centre hits the search input instead. |
| F42 | UNVERIFIED | /v1/environment and /badge publish DEFRA measurements with no sources array, so the extension panel's own attribution footer credits everyone except D | `backend/lambdas/score/app.py:7088` | A reader opens a Rightmove listing in a postcode with no EPC certificates on record and no Land Registry sales (a new-build, or any of the postcodes where /sold-prices returns an empty array). The only section that resolves is Environment. renderSources() collects zero strings across all payloads, hits `if (!seen.size) return null`, and t |
| F43 | **FIXED 2026-08-31** | The only gate that compares deployed state to source covers 3 of the 20 assets whose atomic precache decides whether the PWA installs, and prints "all | `scripts/check_deploy_drift.sh:119` | `make web-deploy-all` runs. fonts-deploy uploads fonts.css and inter.woff2 but the recursive .woff2 copy is interrupted, or the run hits the documented Git-Bash MSYS invalidation failure that bit on 2026-08-26 *after* the uploads — leaving jetbrains-mono.woff2 absent from the origin. Every later target succeeds. `sh scripts/check_deploy_d |

## 3. Minor

| # | Verified | Issue | Location | Failure scenario |
|---|---|---|---|---|
| F6 | UNVERIFIED | LICENSING.md still records the v3.9 environment weights (air 0.65 / flood 0.35) and never records DEFRA road Lden as a score input | `LICENSING.md:76` | An integrator's licensing review follows terms.html §6 to LICENSING.md to work out which third-party licences pass through to them and in what proportion. They record that the EA's flood data drives 0.35 of the environment component and that DEFRA's road surface is display-only — both wrong — and build their own attribution page and their |
| F7 | UNVERIFIED | README says "Six endpoints ... Four are API-key gated. Two are deliberately public"; its own table lists seven, and the live API gates three and leave | `README.md:117` | An integrator planning a public-facing embed reads "Four are API-key gated. Two are deliberately public" and the table's unmarked /v1/regions row, concludes /v1/regions needs a key, and either builds a server-side proxy for a discovery call that needs none, or — reading the prose count of six against a table of seven — cannot tell whether |
| F10 | UNVERIFIED | The liveability-unavailable coverage notice has never been emitted: build_coverage compares against a bare 'unavailable' that live_resolution has neve | `backend/lambdas/score/app.py:5650` | A borough drops below two liveability inputs - the code path the design explicitly supports (live_weights_for's docstring: a city "can now be sourced one field at a time"; Nottingham's Broxtowe/Gedling/Rushcliffe already sit at exactly 2/4 with crimeRate and p8 both None, so one ONS or NaPTAN refresh takes them to 1/4). /v1/score then omi |
| F11 | UNVERIFIED | City of London's sources array claims schools 'falls back to a curated band' while the same response says the input was dropped and its weight redistr | `backend/lambdas/score/app.py:4934` | A B2B integrator auditing provenance calls GET /v1/score?borough=City of London&city=london and is told in the machine-readable `sources` array that the schools input came from a curated band. No schools input was used: live_component_scores dropped it and live_weights_for redistributed its 0.35 across crime, transport and healthcare, whi |
| F12 | UNVERIFIED | /v1/changes freezes the postcode-resolution attribution of whichever request warmed the container into a body cached for its whole lifetime | `backend/lambdas/score/app.py:6947` | A warm container serves GET /v1/score?postcode=SW11+1AA (NSPL answers, setting the thread-local flag), then GET /v1/changes. The unauthenticated /v1/changes body credits 'ONS National Statistics Postcode Lookup (Open Government Licence v3.0)' as a source for a borough-level payload that performed no postcode lookup, and every subsequent / |
| F13 | UNVERIFIED | liveResolution counts City of London's in-house crime estimate as a measured input, the half of the defect its own comment says was fixed | `backend/lambdas/score/app.py:5687` | GET /v1/score?borough=City of London&city=london returns context.liveResolution and coverage.live.basis both reading 'partial - 3/4 inputs measured', and the sentence goes on to say the absent inputs 'are not estimated'. Two of those three inputs are third-party measurements; the third is an in-house estimate, and it is the highest-weight |
| F18 | UNVERIFIED | OPTIONS /v1/environment requires an API key, so CORS preflight fails 403 with no CORS headers on the route built for public browser callers | `backend/template.yaml:451` | Any browser client that triggers a CORS preflight on this route - i.e. any caller sending a non-safelisted request header, which is the normal shape for a third-party integration and the reason the Api-level `Cors` block sets `AllowOrigin: '*'` - gets a 403 on the preflight with no `Access-Control-Allow-Origin`, so the browser blocks the  |
| F22 | UNVERIFIED | signup leaks an API key with no orphan-alarm log when the DynamoDB write fails with a non-ClientError, the exact case the mirrored rollback 265 lines  | `backend/lambdas/signup/app.py:481` | A DynamoDB connection failure or read timeout on the PutItem in record_signup (SignupFunction has `Timeout: 10`, so a slow DDB call is entirely plausible). The user has already had an APIGW key created, enabled and linked to SkyScoreFreeTier. They receive HTTP 500 'Internal server error.' with no key. CloudWatch shows only the generic 'un |
| F23 | UNVERIFIED | The recorded rationale for the /nhs bbox fall-through is the inverse of the data: the snapshot covers the whole bounding box, so the fall-through make | `backend/lambdas/nhs/app.py:318` | A user searches a postcode in outer London where the nearest OSM-tagged GP, pharmacy and hospital are all beyond 1500 m — the green-belt fringes of Havering, Bromley, Enfield or Hillingdon, 8.4% of Greater London's area. The snapshot already knows the correct answer (nothing within 1.5 km) but `any(buckets.values())` is false, so the requ |
| F29 | UNVERIFIED | The Saved list files every UK city's favourites under a "LONDON" heading | `index.html:11604` | A user in Greater Manchester saves M1 1AE, then Bradford (West Yorkshire) and Middlesbrough (Teesside). Opening Saved, all three appear under a heading reading "LONDON", beside their real borough names ("Manchester", "Bradford", "Middlesbrough") — a heading that contradicts the rows underneath it. Clicking one still opens the correct city |
| F33 | **PARTIAL 2026-08-31** | `aircraft bands == geometry` reads its city list from the same dict it checks and has no coverage floor, so it omits London's 33 and NYC's 5 boroughs  | `scripts/build_aircraft_bands.py:507` | A merge, a rebase, or a refactor drops or renames one entry in `AIRPORTS` - say `manchester`, whose docstring comment at lines 78-82 records that its ten bands "were hand-assigned against a Heathrow-calibrated ladder and were the only site city whose aircraft input no script could reproduce". The blocking preflight stage then prints "Comp |
| F37 | UNVERIFIED | The homepage footer renders "Methodology v3.7" while the live API, METHODOLOGY.md and the 99 area pages all say 4.0 | `index.html:3757` | A visitor (or a pilot prospect doing diligence) reads "Methodology v3.7" in the footer, clicks it, and lands on a document headed "Version 4.0" describing a scored environment component the footer says does not exist yet. Any score they then pull from /v1/score comes back stamped 4.0. Three surfaces give three different answers to "which  |
| F40 | UNVERIFIED | roadNoiseAboveWhoPct is a share of the postcodes DEFRA mapped, not of the borough's addresses, but is published and scored as the latter - the quiet c | `scripts/build_borough_bands.py:608` | Solihull publishes `roadNoiseAboveWhoPct: 45.7` with `roadNoiseCoverage: 88.0`; the share of its addresses over the WHO guideline is 40.2%. Every one of the 86 boroughs with road data is biased in the same direction - louder, i.e. worse - by 0 to 5.5 points. One published map band is wrong as a result: London's Sutton is banded `moderate` |
| F44 | UNVERIFIED | The prototype's meta, og and twitter descriptions advertise "live aircraft tracking" on a page whose own live mode is disabled pending OpenSky licensi | `prototype/index.html:16` | Someone shares the prototype URL on LinkedIn or X, or it surfaces in a search result. The card and the snippet read "3D terrain visualisation of London airspace with live aircraft tracking" — a capability the page deliberately does not have, and cannot have until OpenSky's written licensing agreement lands (OPENSKY_LICENSING_EMAIL.md, Tic |
| F45 | UNVERIFIED | apple-touch-icon points at an SVG, which iOS Safari does not accept, so Add to Home Screen on the documented iOS PWA path produces a page screenshot i | `index.html:80` | A visitor on iPhone follows the install path CLAUDE.md documents as one of three ("iOS Safari uses Share -> Add to Home Screen"). Safari cannot decode /icons/icon.svg for the touch icon and falls back to a screenshot of whatever the page was showing at that moment — typically the map mid-render or the search sheet — so the home-screen til |

---

## 4. Explicitly out of scope

Carried from the 2026-08-21 audit and deliberately NOT re-raised:

- **I1** — `/v1/regions` and `/v1/changes` unauthenticated. An open decision,
  not a defect.
- **I3 (part)** — no function sets `ReservedConcurrentExecutions`. Blocked on
  an account concurrency figure `flightmap-dev` is denied.
- **Teesside's missing flood raster** — one near-all-sea tile renders blank and
  the fetcher correctly refuses to cache it. Known and deliberate.
- **Prettier deviations** — advisory, repo-wide, long-standing.

## 5. Finishing the verification

18 of the 48 planned verifications completed. The rest died when the session
hit its spend limit, which is the failure mode the audit skill documents; the
survey had been checkpointed to disk first, so no FINDING was lost - only the
adversarial pass over them.

**Workflow resume is same-session only.** A later session cannot replay the
completed verifiers from cache, so finishing this means re-running the
verification workflow from scratch against the ids still marked UNVERIFIED.
The findings themselves are in
`<session>/scratchpad/audit_findings.json` and, permanently, in the survey
journal named below.

Until then: **an UNVERIFIED row is a lead, not a fact.** The verifiers that DID
run downgraded 8 of their first 13 findings while refuting none, so expect the
same of the rest - severity here is the finder's opinion, not a measurement.

## 6. Provenance of this report

Survey findings live in the workflow journal at
`subagents/workflows/wf_1cad9887-8a4/journal.jsonl`; verdicts at
`wf_81b6b296-934/journal.jsonl`. Both survive this session. If a finding here
reads oddly, the agent transcript that produced it is recoverable.
