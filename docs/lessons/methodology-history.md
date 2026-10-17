# Methodology decisions, v5.0 to v5.2

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> Structural price-led notice, rounding, ranking separability, national affordability, growth pool and real terms, applied weights.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 1921-1987 (2026-10-16) -->
**THE PRICE-LED DISCLOSURE IS STRUCTURAL SINCE 2026-09-09, not a correlation.**
`priceLed` was a rank-to-price correlation tested against **0.60**, a constant
whose own comment recorded it going arbitrary - it was chosen because "nothing
sat between -0.23 and 0.67", and London then drifted to **+0.55**, inside that
gap and 0.05 from flipping the notice on 128 neighbourhoods. A city is now
price-led iff its neighbourhood detail carries **no non-zero sub-borough crime
modifier**: without one, a generated district differs from its neighbours only
by price and aircraft quiet, because it inherits its borough's liveability and
crime is not published at postcode-district geography. **The code now matches
the sentence it prints**, which already described exactly that condition.

- **It reproduced the correlation exactly** the day it replaced it: London 71
  non-zero modifiers, NYC 88 (not price-led), all nine generated cities 0
  (price-led) - the same split as +0.55 / -0.06 / 0.65-0.89. No disclosure moved.
  **London has been price-led since 2026-10-11**: its 71 modifiers were hand-assigned,
  and went when its neighbourhoods became generated. Only New York is not.
- **`priceDominance` and `rankPrice` are DELETED**, not left dangling; nothing
  else read them. Do not reintroduce a correlation.
- Gated by the second pass in `tests/ranking-separability.mjs`, computed from
  the DATA HOLDER rather than the flag the fix sets, proven red by forcing the
  flag on.

**SCORING FROM ROUNDED COMPONENTS: DECIDED WON'T-CHANGE (2026-09-09), and the
published bound is GATED.** `score` keeps being computed from full-precision
components and rounded once; rounding twice would make reproduction exact and
the score less accurate, and would move 43 of 792 published scores by 0.1. What
the decision left behind was a published number with no check - METHODOLOGY s6
and the `AppliedWeights` schema both state a worst-case residual.
`test_the_published_residual_figure_does_not_understate_reality` fails if either
claim drops **below** the measured worst. Asserted as "must not understate",
never as equality - pinning it would be the magic-number trap. Measuring for it
corrected the figure: against the weights **as published** (6dp) the worst is
**0.0674**, not the 0.069 computed from unrounded ones, so both documents now
say "under 0.07".

**THE BOROUGH RANKING DISCLOSES WHEN ITS SCORES CANNOT BE RANKED (2026-09-09,
after v5.0).** v5.0's national anchor removed spread that within-city min-max
had MANUFACTURED, and composite spread fell in **twelve of thirteen cities**:
South Yorkshire 2.3 -> **0.1**, three of four boroughs sharing a published
score. `renderBoroughRanking()` now says so, and the threshold is **DERIVED**
- if the mean gap between adjacent boroughs is under the 0.1 the scores are
printed at, their order is an artefact of rounding. Do not replace it with a
chosen constant; the `priceLed` 0.60 beside it is a standing warning and has
already expired once. Measured at render time, so a city that gains a
differentiating input drops the notice by itself. Fires for South Yorkshire
alone today. Gated by `tests/ranking-separability.mjs`, proven red BOTH ways.

- **REWEIGHTING DOES NOT FIX IT - measured, do not reach for it.** `quiet`
  varies MOST within a city (5.0-10.0) and `live`/`env` LEAST (0.8-2.7,
  0.0-1.4), so shifting weight toward liveability **reduced** spread in twelve
  of thirteen cities. South Yorkshire's `quiet` spread is **0.0** - Doncaster
  Sheffield closed to commercial flights in 2022 - so no weighting recovers a
  ranking there. Its ceiling under any weighting is 3.0, and only with all
  weight on growth, which `balanced` zeroes.
- **THE GATE'S TWO TRAPS, both of which read as "the page is broken" and are
  not.** The score cell renders `<span aria-hidden>GLYPH</span> 7.9`, so a
  bare `parseFloat(td.textContent)` is NaN on every row - take the TRAILING
  number. And a poll on "more than one score cell exists" is satisfied by the
  PREVIOUS city's table, so every reading comes back one city stale; comparing
  counts too still aliases (Merseyside and Tyne and Wear both have five), so
  wait until the rendered `data-rank-name`s ARE the target city's borough set.
  **Poll for the state you want, never one already true.**
- **Two states must be reached first**: `#tab-ranking` ships `display:none`,
  and `rankingView` defaults to `neighbourhood`, whose scores use WITHIN-city
  neighbourhood prices and are untouched by the national anchor - so a gate
  stopping at the tab measures the one view this does not apply to.

<!-- CLAUDE.md lines 2006-2072 (2026-10-16) -->
**AFFORDABILITY IS NATIONAL AND LOG-SCALED SINCE METHODOLOGY v5.0
(2026-09-09), not min-max within each city.** `afford` is now
`clamp((ln(p95) - ln(price)) / (ln(p95) - ln(p5)), 0, 1) x 10` against the
5th-95th percentile of borough medians across the whole **currency** pool.
Barking and Dagenham **10.0 -> 4.4** at GBP 371,030, Stockton-on-Tees
**0.0 -> 9.5** at GBP 170,923; all **1,619 of 4,371 inverted cross-city pairs**
are gone. **737 of 792 composite scores move**: London falls a mean 1.55,
Teesside rises 1.28. **DEPLOYED AND VERIFIED LIVE 2026-09-09**: backend via SAM
first (the site computes v5.0 locally, so a frontend-first deploy would put the
site ahead of the API on every borough), then 104 web uploads and 4 CloudFront
invalidations, all Completed. Verified from the ORIGIN, never from an exit code:
drift **133 of 133**, `area pages match the live API` **99 of 99**,
`site == /v1/score` agreeing on every component of 6 postcodes, `score sanity`
**28 postcodes**. SW11 1AA serves **5.0 with afford 0.4**, which is METHODOLOGY
s6's worked example exactly.

- **LOG, and the linear p10/p90 that ROADMAP recommended was measured and
  REJECTED.** UK borough medians are right-skewed, so a linear scale flattened
  **four of thirteen cities** to under a point of internal spread (Teesside to
  exactly 0.0) and pinned 22 of 99 boroughs at a rail. Log p5/p95 flattens one.
  Do not "simplify" it back to linear; the comparison table is METHODOLOGY s4.2.
- **A compressed city cohort is the honest answer, not a defect.** Teesside
  really is 171k-200k. Same argument the repo already accepted when it widened
  Leicester's cohort: *min-max over a narrow cohort manufactures spread it has
  not measured.*
- **The within-city signal is published, not deleted**:
  `context.priceRankInCity` = `{rank, of}`, cheapest first, ONE nested object so
  the pair cannot drift.
- **Pools are per CURRENCY.** The USD pool is New York's five boroughs, so US
  and UK scores are NOT comparable with each other; the provenance says so.
  Never pool currencies to "widen" the cohort.
- **THE SITE NEEDS `BACKEND_ONLY_PRICES` AND IT IS EASY TO LOSE.** `/v1/score`
  covers 13 cities, the site renders 11, so the site pooled **86** sterling
  boroughs against the Lambda's **94** - moving p5/p95 and disagreeing on four
  boroughs by 0.1. index.html carries a prices-only block for Cardiff and
  Nottingham between `BACKEND-ONLY-PRICES` markers, **maintained by
  `build_hpi_prices.py --write`** (which reads `BACKEND_ONLY_CITIES` from its
  single holder, `tests/test_borough_data_parity.py`, by AST rather than
  copying it). A national anchor makes every score depend on every other
  borough's price, so **input parity is not enough** - only
  `tests/borough-score-parity.mjs`, which compares OUTPUT, could see this.
- **`check_worked_example.py` HAD NEVER COMPARED AFFORDABILITY.** It read
  `app.calc_afford(...) if hasattr(app, 'calc_afford') else None` and there is
  no `calc_afford` - the guard was permanently False and the loop skips a None,
  while the stage printed "every input, bound, component, weight and the final
  arithmetic agree". **Second `hasattr()`-on-a-nonexistent-name in this repo**;
  the first dropped seven fields from all 99 area pages. 17 comparisons now.
- **The provenance line is DERIVED**, replacing THIRTEEN hand-written strings
  whose whole point was an incomparability caveat that v5.0 makes false in
  thirteen places at once. `SNAPSHOT_VINTAGE_LABEL` is the one holder for
  the month label ("June 2026" then; "July 2026" since the 2026-09-16 roll),
  which those thirteen also each hardcoded. **The twelve `Prices: HM Land
  Registry ... vintage` SOURCE lines were the same shape and were derived on
  2026-09-16** (`_hpi_source_line`); `build_hpi_prices.py --check` asserts
  what `build_sources()` emits per city, since there is no literal to count.
- **Quarter-over-quarter affordability now mixes two movements.** Wandsworth's
  price ROSE 660,000 -> 680,105 and its affordability ALSO rose 0.3 -> 0.4,
  because the national p95 rose faster. That is what "affordable relative to the
  country" means; `marketContext` on `/v1/changes` exists to make it visible.
  (July 2026: 686,076 and 0.3 in both vintages at 1dp - the raw figure moved
  0.027 and did not cross a rounding boundary.)
- **The NEIGHBOURHOOD ranking is still within-city min-max, deliberately.** It
  is site-only, no endpoint publishes it, and changing it would move the data
  under the still-open price-led-threshold decision. Both transforms are
  monotonic in price, so the order inside a city is identical either way. If it
  is ever unified, call `affordScore()` - do not write a third formula.

<!-- CLAUDE.md lines 2089-2191 (2026-10-16) -->
**GROWTH IS ANCHORED ON THE CURRENCY POOL SINCE METHODOLOGY v5.2 (2026-09-16),
not the city cohort.** `national_trend_bounds()` beside `national_price_bounds()`,
`nationalTrendBounds()` beside `nationalPriceBounds()` on the site; the two
API-only cities enter the site's pool through **`BACKEND_ONLY_TRENDS`**, written
by `build_hpi_prices.py --write` in the same block as their prices. New
`context.growthRankInCity` `{rank, of}`. **Why:** the city cohort put one borough
per city on EACH RAIL every month by construction (22 of 94), so a 4-5 borough
cohort's leader changing hands was a 10-point flip - the July roll did exactly
that to Hartlepool (0.0 -> 10.0) and Newport (8.5 -> 0.0). **Measured, not
argued:** `scripts/cost_growth_anchor.py` replays 24 months under four designs;
the pool halves the churn (1.44 -> 0.76 mean month-on-month, 8.2% -> 0.2%
moving 5+) and takes cross-city inversions from 651 of 4,371 pairs to 0.
Smoothing the input was measured and REJECTED - the rails stay, and it would
publish a trend that no longer equals HMLR's `Annual_Change`. `balanced` cannot
move on it (growth weight 0.00); `investor` moved on 56 of 99, max 1.8. **A
yardstick outside the borough's city is labelled with it** - the London
`/v1/changes` names "Trafford (Greater Manchester)" as the fastest riser - and
`benchmarks()` takes the city so it can assemble the pool with a previous
vintage's slice standing in. **Two tests borrowed London's fastest riser as
"the" benchmark and now construct their cohorts**: nationally that role belongs
to a city with no previous vintage, so live data can no longer reach the branch
(`feedback-borrowed-edge-cases-expire`). The published reproduction residual
moved 0.0674 -> 0.0721; both documents say "under 0.08" - the openapi gate's
regex needs `under 0.08.` followed by a full stop, so a parenthetical after the
number must be its own sentence. **Same afternoon, `panel contrast, area (AA)`
went red on a node it had never measured before**: the `/nhs` "none within
1.5 km" link, brand orange as TEXT at 2.60:1, rendered only when Overpass
happened to answer that way for the probed area - green in the morning, red in
the afternoon, nothing changed between. Fixed (inherit + underline;
`--orange-ink` is 4.35:1 on the `--cream` mobile panel and is NOT enough, now
recorded on the token) and **the gate now REACHES that state on purpose**: a
third state, `area panel, nhs none-nearby`, fulfils `/nhs` with the Lambda's
own `none_nearby()` shape and asserts the three links rendered before
measuring (`reached`), proven red at 3 nodes per viewport on the old colour.
*A state reached by chance is a state not gated.* **DEPLOYED 2026-09-16 with the July roll and verified from the origin** (drift 133/133, freshness 99/99, sanity 28, parity 6); `deploy_hpi_roll.sh` does not run `demo-deploy`, so a methodology change that touches `openapi.yaml` needs that target too.

**GROWTH IS SCORED ON THE REAL-TERMS TREND SINCE METHODOLOGY v5.1 (2026-09-15).**
The nominal HPI 12-month change is deflated by ONS CPIH for the SAME month -
`real_trend_pct()`, `CPIH_12M_PCT` (one entry PER VINTAGE KEY, holding the CURRENT
month's rate: 2026-Q3 = July 2026 3.1 since the 16 Sep roll, was June 2.8; 2026-Q2 = May
2026 3.0), `with_real_trends()` attaching `trendReal` to every sterling record
IN PLACE at import, `scored_trend()` read by `calc_score`, `benchmarks`,
`growth_ranks`. `trend` stays nominal; `context.priceTrendRealPct`,
`inflationPct`, `growthBasis` are new. **New York stays nominal** - no US
series - and `scored_trend()` falls back by construction. **Read before the
July HPI roll:** the roll must ADD the new month's CPIH to `CPIH_12M_PCT`
(`build_hpi_prices.py --check` reds without it and compares the value to ONS
L55O); the site holds ONE deflator, `SNAPSHOT_CPIH_PCT` in index.html, which
rolls with it - `tests/borough-score-parity.mjs` now compares `investor` as
well as `balanced` because balanced weights growth at 0.00 and could not see a
stale site deflator (proven: 52 investor rows red, 0 balanced). The previous
vintage is deflated by ITS month (`previous_dataset()` re-derives after the
overlay). `market_context` stays NOMINAL deliberately (it describes prices);
the comparison's step 3 works in real terms and says so. Rounding is
`math.floor(x*10+0.5)/10`, the engine's `round_1dp` rule, NOT Python's
`round` - the two differ on a .x5 tie and the value has a JS holder. The
growth provenance line is DERIVED (`_growth_breakdown_line`), replacing 13
literals; a constructed test cohort must set `trendReal` too, or the engine
reads the copied record's real figure and the stub changes nothing.
Measured: 25 of 77 'rising' boroughs fall in real terms, 78 of 99 investor
scores move (mean -0.53), no other persona can. Worked example growth
4.0 -> 3.6. **DEPLOYED 2026-09-15 and verified from the origin: SAM modified ScoreFunction, SignupFunction (+ role) and the API (pending table ACTIVE, confirm route answering HTML, flag off); web + demo + area + meta targets run from the Makefile's own recipes, four invalidations completed; drift 133 of 133; score sanity PASS on 28 postcodes at matching versions; area pages 99 of 99; site == /v1/score on every component of 6 postcodes; demo-key scope 3 PASS; live index.html serves v5.1 with SNAPSHOT_CPIH_PCT 2.8; Cardiff investor 4.1 live, as measured.**

**`weights` IS THE APPLIED TABLE SINCE 2026-09-09, not the persona's nominal
row.** `sum(components * weights)` now reaches `score` on every borough -
Brooklyn **4.4826 -> 4.5** (was 3.9 against 4.5), Cardiff **6.2953 -> 6.3**.
The engine had always dropped an uncomputable component and rescaled the
survivors; only the RESPONSE published the un-rescaled row, and the whole
response-side fix was **deleting one line** - `'weights': weights` sat after the
`**score_data` spread and overrode the applied set `calc_score` returns.
Deliberately **not** a second `weightsApplied` field: that is the
`lineStatusAvailable` shape, where an optional correct field leaves the naive
computation wrong for everyone who does not know to switch.

- **No score moved, and no weight on the 720 complete combinations** - applied
  values are rounded to **6dp** so a complete set republishes the declared
  `0.32`, not the `0.32000000000000006` that dividing by a total of
  0.9999999999999999 produces. Only the 72 absent-component ones change.
- **The spec now carries TWO schemas** because they are two objects: `Weights`
  is what a caller may SEND, `AppliedWeights` what a response returns. Callers
  using the old divide-by-the-present-weights workaround need change nothing -
  that denominator is now 1.0.
- **Two gates, both proven red, and BOTH had been blind to this.**
  `check_openapi_matches_engine.py` divided by the present weights, and **that
  division cannot tell the two tables apart** - it recovers the same score
  either way, so it sat green for the whole period. It asserts the published
  total is 1.0 now. And the first five engine-level unit tests I wrote went
  green against the live defect, because they read `calc_score`, which was
  always right; **the guarding test goes through `resolve_query`**. Same lesson
  as "measure the DOM, not the flag", in the backend.
- **REPRODUCTION IS EXACT TO THE LAST PUBLISHED DIGIT, NOT TO THE BIT, and that
  is a separate open decision.** Components are published at 1dp while the
  engine weights them unrounded, so the sum can sit up to **0.1** from `score`
  (0.05 + 0.05; worst observed **0.069**). This predates the weights work and
  is unrelated to it: **37 of the 720 COMPLETE sets already did not reproduce**.
  Making it exact means scoring from the ROUNDED components, which moves **43
  of 792 published scores by 0.1** and rounds twice where the engine rounds
  once - so it is a decision, and the recommendation is *don't*, publish the
  bound instead (done: METHODOLOGY s6 and the `AppliedWeights` schema). Same
  honesty `roundingResidual` already applies to `attribution`.
- **The gate's tolerance is DERIVED (0.10), never the measured 0.069** - an
  observed worst case asserted as a constant is the `0.60 threshold` trap.

