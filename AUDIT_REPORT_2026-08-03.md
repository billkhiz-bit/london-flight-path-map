# Sky Score — Full Audit, 2026-08-03

**Method:** 18-agent workflow (`wf_d518b758-495`) — 8 finder dimensions, adversarial
refutation of every finding, a completeness critic, then synthesis. 1,113 tool calls,
2.67M tokens, ~49 minutes. 66 findings survived refutation.

**Not written to `AUDIT_REPORT.md`** — that file holds the 2026-07-24 full audit and the
2026-07-27 targeted pass, and overwriting it without the author present is against the
repo's own safety rule. Merge or supersede deliberately.

---

## Independent verification of the two criticals

Agent findings are not evidence. This project's own record includes eleven agents returning
confident, well-cited crime figures that were wrong, and on 2026-08-03 two defects were
misdiagnosed from eight-postcode samples. Both criticals below were therefore re-derived by
hand against the files before being accepted.

### Finding 1 — native bundle omits `borough-extra.json`: **CONFIRMED**

The whole chain checks out:

1. `mobile/scripts/copy-web.mjs:83` copies `data/` through the filter `(n) => n.endsWith('.png')`.
   Only PNGs are bundled. The comment at line 16 shows why — it was written when `data/` held
   nothing but DEFRA noise tiles, and `borough-extra.json` plus both boundary files were added
   later without revisiting the filter.
2. `mobile/capacitor.config.ts` sets only `server.androidScheme`; there is no remote `url`, so
   the webview serves from the local bundle and the fetch cannot fall through to CloudFront.
3. `index.html:5025` requests the root-relative `/data/borough-extra.json`, which resolves
   inside the bundle and 404s.
4. `index.html:5054` catches it, logs `console.warn('borough-extra hydration failed; using
   empty defaults')`, and leaves `BOROUGH_EXTRA` as `{}` — commented "Non-fatal".

Every downstream lookup (`ex.crimeRate`, `ex.p8`, `ex.transport`, `ex.healthcare`) is then
undefined and falls to its default, flattening liveability. The failure is silent by design:
a `console.warn` nobody reads on a device.

### Finding 2 — Lambda flight-path geometry never trimmed: **CONFIRMED, figure corrected**

Measured directly: the site carries **50** flight-path waypoints, the score Lambda **85**.
The Lambda retains 35 waypoints and two whole corridors (`Approach N`, `Approach S`) that the
site trimmed on 2026-05-07 — a trim METHODOLOGY records as audited against the DEFRA Lden
raster. More waypoints means more proximity hits, so the API scores noisier wherever they
differ.

Across **7,239 live London postcodes** (NSPL, flight-path geometry only, heliports excluded
so the attribution is clean):

- site and API disagree on `quiet` for **2,503 postcodes — 34.6% of London**
- the API is the noisier side in **100%** of disagreements

**The audit reported 41.4%; the correct figure is 34.6%.** The higher number appears to fold
in the heliport term, which is a separate and already-documented divergence. The direction and
the severity stand.

---

# Sky Score — Full Repository Audit

**Date:** 2026-08-03 · **Branch:** `london-corrections-2026-08-02` · **HEAD:** `542e471` (= `origin/master`)
**Method:** 8-dimension sweep + adversarial verification + completeness critic. Every finding below was independently re-derived by a verifier who ran code, executed the shipped functions, queried the live API, and curled the deployed site. Findings that failed refutation were dropped.

---

## 1. Verdict

**The scoring engine is in better shape than the surfaces that describe it — but two live defects put wrong numbers in front of real users, and one of them has been shipping to the App Store since May.** The v3.5 crime and schools re-source landed correctly in `score/app.py` and `borough-extra.json`; the arithmetic is sound and all 96 published offence breakdowns match ONS Table C4 exactly. What has not held is *propagation*. The B2B `/v1/score` API computes noise from flight-path geometry the project itself audited out on 2026-05-07 — the site trimmed 12 corridors to 10, the Lambda never was — so site and API disagree on `quiet` across **41.4% of Greater London**, always with the API noisier, and METHODOLOGY §4.5 explicitly tells readers that divergence cannot exist. Worse, the shipped iOS app omits `data/borough-extra.json` from its bundle entirely, collapsing liveability to a flat 5.0 for **all 38 boroughs across all 8 personas** — a value the code's own docstring calls "below the entire observed range". Beyond those two, there is a broad band of documentation drift: five different published methodology versions against a live 3.5, three retired data suppliers still credited on the README and in METHODOLOGY §7, and a security posture document claiming OIDC and read-only IAM where neither exists. The gates did not catch any of this, and three of them are structurally incapable of doing so. **This is a codebase whose core is honest and whose perimeter is not.**

---

## 2. Findings

| # | Title | Sev | File:line | Impact |
|---|---|---|---|---|
| 1 | Native iOS/Android bundle omits `borough-extra.json` — liveability flatlines at 5.0 | **critical** | `mobile/scripts/copy-web.mjs:83` | Every App Store user sees wrong scores for all 38 boroughs; 26/33 ranks move |
| 2 | Score Lambda's London flight-path geometry never received the 2026-05-07 trim | **critical** | `backend/lambdas/score/app.py:1467` | API `quiet` disagrees with the site across 41.4% of London, always noisier |
| 3 | METHODOLOGY §4.5 asserts a parity that does not hold and forecloses the check that finds #2 | high | `METHODOLOGY.md:407` | Tells integrators the divergence "cannot exist" |
| 4 | Saved-postcode score uses retired 0.40/0.35/0.25 weights, no liveability term | high | `index.html:7531` | 1,033 of 1,064 persona×place cells disagree with the displayed score; persisted server-side |
| 5 | Live site + both store listings promise a per-postcode "exact dB" no code path produces | high | `index.html:2727` | Headline differentiator advertised, undeliverable |
| 6 | Prototype's "AIRPORT INTELLIGENCE" panel shows fabricated dB readings under a live indicator | high | `prototype/index.html:2666` | Invented noise figures at named London locations, no disclaimer |
| 7 | METHODOLOGY + CHANGELOG still claim "the other 29 boroughs already agreed" — 29 of 33 were corrected | high | `METHODOLOGY.md:249` | False factual statement in the audit-facing doc |
| 8 | City of London: `liveResolution: "measured"`, credited to ONS Table C4 + DfE P8, neither of which supplies it | high | `backend/lambdas/score/app.py:2298` | Two national bodies credited for a borough where one suppresses and the other has no value |
| 9 | Consumer site prints a self-contradicting, reassuring crime sentence for City of London | high | `index.html:6144` | "2.2× the median" and "nothing stands out" in one sentence |
| 10 | `/api/` landing page + OpenAPI advertise the DEFRA raster tier, unconditionally bypassed | high | `api/index.html:234` | Sells 10 m resolution the product cannot deliver |
| 11 | METHODOLOGY §20 + CHANGELOG publish a root-cause the code explicitly retracts | high | `METHODOLOGY.md:972` | Sends the next maintainer hunting a CRS bug that does not exist |
| 12 | `SECURITY.md` claims GitHub OIDC and a read-only deploy user; neither is true | high | `SECURITY.md:30` | Procurement-facing false statement about key management |
| 13 | `SUBPROCESSORS.md` says the web app never calls postcodes.io; it calls it on every keystroke | high | `SUBPROCESSORS.md:32` | Undisclosed data flow in an Art. 28(2) register |
| 14 | Airport-quiet invariant vanishes silently if its own probe fails | high | `scripts/check_score_sanity.py:140` | The one data-defect gate can lose its key assertion and still print PASS |
| 15 | Result panel fails WCAG AA contrast on the badges users read the score from | medium | `index.html:1413` | 8–9 of 11 badge elements per borough below 4.5:1 |
| 16 | a11y gate scans initial page state only, so #15 is invisible to it | medium | `tests/e2e/accessibility.spec.js:41` | 13 serious nodes hidden behind one keystroke |
| 17 | Native bundle also omits vendored borough geometry — reverts to 19.2 MB third-party fetch | medium | `mobile/scripts/copy-web.mjs:83` | Next build re-inherits the regression 35cbbba fixed |
| 18 | Nothing guards the native bundle's contents; documented gate is a manual eyeball | medium | `mobile/scripts/copy-web.mjs:57` | Why #1 shipped and survived three months |
| 19 | Store listings' DATA SOURCES omit DfE while Progress 8 drives 35% of liveability | medium | `mobile/fastlane/metadata/ios/en-GB/description.txt:30` | Attribution drift on the slowest-to-correct surface |
| 20 | README credits Home Office, Ofsted, NHS England, Price Paid Data for the wrong things | medium | `README.md:137` | Repo front page contradicts the API's own `sources[]` |
| 21 | METHODOLOGY §7 credits 3 retired suppliers, omits HPI and OpenStreetMap/ODbL | medium | `METHODOLOGY.md:685` | The table a diligence process starts from |
| 22 | METHODOLOGY §13 says schools are *not* intake-adjusted; Progress 8 is, by construction | medium | `METHODOLOGY.md:802` | §13 and §20 of the same doc disagree |
| 23 | Methodology version disagrees across six surfaces; live footer v3.4, API 3.5 | medium | `index.html:2824` | The one version string a visitor sees is stale |
| 24 | `COMPARISON_NOTE` hardcodes "(v3.2)"; rendered as "Honesty note" on /changes | medium | `backend/lambdas/score/app.py:166` | One public page shows v3.2, v3.3 and v3.5 |
| 25 | `?methodology=` version pinning is a §16 contract commitment, implemented nowhere | medium | `METHODOLOGY.md:913` | Unimplemented API-stability term |
| 26 | Frontend renders full scores from all-default liveability on a data-load failure, silently | medium | `index.html:5054` | All 33 scores wrong, 27 ranks move, no disclosure |
| 27 | ONS crime check cannot go red on the one borough it was written to flag | medium | `scripts/refresh_crime_from_ons.py:91` | `--check` prints "in step with ONS" while the City of London figure is unsourced |
| 28 | Import-time vocabulary guard omits `impact`, so a typo in the noise band scores 5.0 | medium | `backend/lambdas/score/app.py:1202` | Latent; would upgrade a severe-noise borough silently |
| 29 | Neighbourhood ranking omits the heliport term the postcode panel applies | medium | `index.html:5115` | Same place, two quiet scores, one click apart |
| 30 | `lden_db_to_quiet` is the only untested function in the score Lambda | medium | `backend/lambdas/score/app.py:2099` | Unguarded exactly where the next change is planned |
| 31 | ESLint enforces zero rules on any `.js`/`.mjs`; `npm run lint` covers 1 of 8 pages | medium | `eslint.config.js:8` | Security rules cover 1 of 26 files |
| 32 | `/v1/score` credits MHCLG for EPC in every response while declaring EPC "planned" | medium | `backend/lambdas/score/app.py:2288` | Payload contradicts itself |
| 33 | Privacy page declares OpenStreetMap and TfL data to be OGL v3.0 | medium | `privacy.html:300` | ODbL mislabelled as permissive Crown copyright |
| 34 | Four upstreams receiving location data absent from the sub-processor register | medium | `SUBPROCESSORS.md:74` | "Never leaves UK AWS infrastructure" is false on 5 routes |
| 35 | 22 of 33 school notes assert Ofsted "Outstanding" beneath a Progress 8 badge | medium | `data/borough-extra.json:7` | Retired vocabulary in live prose, unsourced, undated |
| 36 | Demo-key quota stated as 100 / 1,000 / 2,000 across four files | medium | `score-demo/index.html:395` | Wrong capacity on the page that sells the API |
| 37 | `borough-extra.json` fetched `force-cache` with no `Cache-Control` — SW bump does not evict | medium | `index.html:5025` | The VERSION-bump ritual misses the file it was bumped for |
| 38 | Eleven tracked, publicly-served files have no deploy command anywhere | medium | `Makefile:80` | Incl. `api/index.html`, whose 2026-08-03 correction has no route live |
| 39 | `changes.html` excluded from API-URL drift check and html-validate | medium | `scripts/check_api_url_drift.sh:18` | Gate has a live blind spot on the pending domain cutover |
| 40 | `PROJECT_DOCUMENTATION.md` advertises a 1,000 req/month free tier against a deployed 100 | medium | `PROJECT_DOCUMENTATION.md:103` | 10× wrong ceiling in the architecture reference |
| 41 | `SECURITY.md` describes DynamoDB PITR as planned; the template enables it on all four tables | medium | `SECURITY.md:92` | Understates the actual recovery posture |
| 42 | CLAUDE.md's manual deploy for `sw.js` / `api-base.js` omits load-bearing cache headers | medium | `CLAUDE.md:113` | Two documented deploy paths disagree |
| 43 | METHODOLOGY line 741 says `methodologyVersion` is "currently 3.1" | medium | `METHODOLOGY.md:741` | Stale by four versions in live §16 prose |
| 44 | Live EPC credential (key + account email) committed and pushed to the public repo | medium | `archive/prototype-2026-03/samconfig.toml.march-2026:10` | Service retired 2026-05-30; posture docs claim the opposite |
| 45 | README says 3 endpoints "all API-key gated"; there is a fourth, deliberately public | medium | `README.md:66` | `/v1/changes` omitted from the API surface section |
| 46 | README says 5 personas, OpenAPI enumerates 5 in two schemas; code has 8 | medium | `README.md:126` | A spec-validating client rejects valid requests and responses |
| 47 | README asserts the worked example matches the live API; §6 says it has not since v3.2 | medium | `README.md:139` | Reproducibility claim contradicted by its own target |
| 48 | "London median" for offence ratios includes the Met force-level aggregate row | low | `scripts/refresh_crime_from_ons.py:117` | 12 of 96 ratios shift 0.1; flips one borough's displayed sentence |
| 49 | Neighbourhood band ladder inconsistent with shared `IMPACT_TO_QUIET` vocabulary | low | `index.html:5183` | `moderate-high` unreachable; `severe` means two things |
| 50 | 128 ranking rows, 33 map paths, every saved row are mouse-only | medium | `index.html:8190` | Keyboard users cannot activate them (search is the workaround) |
| 51 | `js/vendor/d3.v7.min.js` precached atomically with no deploy target | low | `sw.js:86` | A d3 upgrade breaks SRI or blocks SW install |
| 52 | Three live B2B pages render "Sky Score API , Live Demo" | low | `score-demo/status.html:158` | Dash-strip artefact in the funnel masthead |
| 53 | Two DOM injection sites interpolate remote data without escaping | low | `index.html:6391` | Defence-in-depth only; not exploitable as data flows today |
| 54 | Status page says "refreshed every 60s"; code is 5 minutes | low | `score-demo/status.html:159` | Freshness promise overstated |
| 55 | Dead `DEFRA_WMS` block keeps four external hosts in the CSP allow-list | low | `index.html:5332` | ~50 lines reading as live provenance, answering nothing |
| 56 | METHODOLOGY / ROADMAP / CHANGELOG cite `index.html:1118-1247` for the Haversine algorithm | low | `METHODOLOGY.md:301` | Those lines are CSS |
| 57 | `SECURITY.md` "Last reviewed" three months older than its own content | low | `SECURITY.md:7` | Also: "five HTML pages" (9), "270 tests" (357) |
| 58 | SECURITY.md and security.txt publish different disclosure addresses | low | `SECURITY.md:13` | Same inbox, inconsistent copy |
| 59 | `html-validate` covers 7 of 8 public pages; `/changes` omitted | low | `package.json:10` | Passes today; a regression would not go red |
| 60 | Loader scripts behind both flagship data defects have no tests | low | `scripts/load_defra_raster.py:398` | Mitigated by `--check` and a downstream Lambda test |
| 61 | `api/index.html` + OpenAPI ship samples pinned to superseded versions | low | `api/index.html:251` | Copy-paste examples disagree with the API |
| 62 | `score-demo/status.html` describes the demo key as on the 1,000/month free plan | low | `score-demo/status.html:197` | Comment-only; quota reasoning anchored to a false budget |

---

## 3. Critical and high findings in detail

### 1 · Native bundle omits `borough-extra.json` — liveability flatlines at 5.0 (critical)

**What it is.** `mobile/scripts/copy-web.mjs:83` copies only `data/*.png` into the Capacitor bundle:

```js
await copyDir(join(ROOT,'data'), join(WWW,'data'), (n) => n.endsWith('.png'));
```

`index.html:5025` fetches `/data/borough-extra.json` as an absolute path on the WebView's own origin. `capacitor.config.ts:23` sets `webDir: 'www'` with **no `server.url`**, so that path resolves to the local bundle and 404s. The catch block at `index.html:5054-5057` only `console.warn`s, leaving `BOROUGH_EXTRA` as `{}`, and `getLiveScore` (`index.html:4929`) returns the `5` fallback for every borough.

**Evidence.** The on-disk bundle confirms it: `ls mobile/www/data/` returns exactly one file, `aircraft-noise-london-lden.png`. This is **shipped, not hypothetical** — `git show 4af9bc5:mobile/scripts/copy-web.mjs` already had the `.png` filter at line 83, and `git show 4af9bc5:index.html` already fetched the JSON; `4af9bc5` is the commit CLAUDE.md records as the source of iOS **v1.0.21, live on the GB App Store**. Impact was *measured*, not estimated: extracting the site's real scoring functions into a node vm and running both ways gives **264/264 London cells (33 boroughs × 8 personas) and 40/40 NYC cells differ**; distinct liveability values collapse from 21 to 1 (London) and 5 to 1 (NYC); **26 of 33 balanced-persona ranks move**. Largest deltas: `family`/Ealing 6.7→4.8, `family`/Manhattan 6.0→3.9.

Severity rests on the repo's own docstring at `backend/lambdas/score/app.py:2408-2412`: *"**5.0 is not neutral**. London's computed live scores span 5.5-8.8, so the fallback sits below the entire observed range."*

**This is known defect class #1 (DEFRA nodata → "perfectly quiet"), one level up:** missing data silently becoming a plausible value — except here an entire *file* is missing, not a cell.

**Fix.** Change the filter to copy the whole `data/` directory (or at minimum `.png` + `.json`), then add a `MISSING` assertion for `data/borough-extra.json`, `data/london-boroughs.json` and `data/nyc-boroughs.json` alongside the existing three at `copy-web.mjs:57`. Rebuild and resubmit both stores. Separately, make `hydrateBoroughExtra`'s failure path *visible* — the `_boroughExtraHydrated` flag at `index.html:5030` is already written and never read (finding 26); gate the score render on it.

---

### 2 · Score Lambda's London flight-path geometry never received the 2026-05-07 trim (critical)

**What it is.** `FLIGHT_PATHS_LONDON` (`backend/lambdas/score/app.py:1467-1683`) holds **12 corridors / 82 waypoints**. `index.html:4370-4516` holds **10 corridors / 47 waypoints** — the shape the project's own DEFRA audit produced on 2026-05-07. The Lambda's set is a strict superset: all 47 site waypoints plus 35 extras, including the two whole corridors (LGW `Approach N`, LTN `Approach S`) that `index.html:4501-4515` documents as deliberately removed. Because `calc_postcode_quiet` scores by distance to the *nearest* waypoint of *any* corridor (`app.py:2169-2183`), those 35 extras can only **add** noise.

**Evidence.** Both geometries extracted programmatically and diffed corridor-by-corridor, waypoint-by-waypoint: `py-only corridors: ['Approach N', 'Approach S']`, `lambda-only waypoints: 35`, `site-only: 0`. Proof it is the geometry and nothing else: monkeypatching `app.CITY_GEOMETRY['london']['paths']` to the site's 10-corridor set drops mismatches from **1539 → 0** over 3,875 test points. Measured over an 8,152-point in-London grid (0.005° lattice, point-in-polygon against all 33 features of `data/london-boroughs.json`), with the heliport term removed from both sides: **3,375 disagreements = 41.4%**, API noisier at 3,375, quieter at **0**, 27 boroughs touched. Max quiet gap 3.0 (Purley: site 10.0, API 7.0); at headline score, 68 of 134 neighbourhoods disagree by up to 1.1.

The tier is live: `RASTER_TIER_QUARANTINED = True` (`app.py:2008`) makes `_lookup_lden_raster` return `None` unconditionally (`app.py:2031`), so **every** postcode resolves on this Haversine tier. Git confirms the cause: `git show --stat abbae36` and `5c167db` (both 2026-05-07) touch only `FLIGHT_PATHS_AUDIT.md`, `index.html`, `scripts/audit_flight_paths.py` — `app.py` is in neither. `git log -S"'Approach N'" -- backend/lambdas/score/app.py` returns exactly one commit, `2654e2a` (2026-05-05, the v3.0 port). `scripts/audit_flight_paths.py` — a third copy — matches the site byte-for-byte, so the Lambda is the sole outlier. No test compares the two.

Commit `3f9e833`'s own comment (`app.py:1993-1994`) asserts the Haversine tier *"is what the consumer site has computed all along, so this also closes the site/API divergence"* — this refutes that.

**Fix.** Replace `FLIGHT_PATHS_LONDON` with the trimmed 10-corridor set from `index.html:4370-4516` (or, better, load both from a single shared JSON in `data/`). Then add a parity test that asserts the Lambda's corridor names and waypoint coordinates equal the site's — there is currently none, and `scripts/audit_flight_paths.py` already holds a correct mirror to test against.

---

### 3 · METHODOLOGY §4.5 asserts a parity that does not hold, and forecloses the check that finds #2 (high)

`METHODOLOGY.md:407-409`: *"The formulas are otherwise identical… The term touches **14.1% of Greater London's land area**; outside that, site and API agree exactly."* Line 432: *"This accounts for **every** observed site-versus-API difference on quiet."*

Both are false by 41.4% of London. The heliport figure itself checks out (1,142 of 8,152 grid points lie within 5 km of a heliport = 14.0%), which is what makes the surrounding claim so effective at stopping anyone looking further. The document is also internally inconsistent: `METHODOLOGY.md:336` correctly describes the API as carrying *"12 corridors for London (… LGW approach, LTN approach)"*, while `:979` says those same polylines were trimmed. `CHANGELOG.md:836` compounds it, recording *"Score Lambda's Haversine fallback now also more accurate for outer-London postcodes"* for a commit whose `--stat` does not include `app.py`.

**Fix.** After fixing #2, rewrite §4.5's parity claim to state what is actually true and add the parity test as the evidence it cites. Correct `CHANGELOG.md:836` and reconcile `METHODOLOGY.md:336` with `:979`.

---

### 4 · Saved-postcode score uses retired weights with no liveability term (high)

`index.html:7463` renders the postcode score with the active persona's weights. Sixty-eight lines later, `index.html:7531` writes `data-fav-score` from a fixed `quiet*0.40 + afford*0.35 + growth*0.25` — **no `live` term at all**, and a 0.25 growth weight when 7 of the 8 personas weight growth at 0.00 (verified across all 8 entries at `index.html:4798-4846`; `balanced` is `{0.38, 0.31, 0.00, 0.31}`). The value flows `data-fav-score` → `toggleFavourite` (8323) → `saveFavourite` (7703) → `buyerScore`, is persisted to DynamoDB, and is re-rendered as `Score: X/10` at `index.html:7776`.

Reimplementing both expressions in node against the real data: across **134 neighbourhoods × 8 personas = 1,064 cells, 1,033 disagree**, max gap 2.6 (`firsttime`/Canary Wharf: displayed 7.3, saved 4.7), median 0.7. Across all 33 boroughs under `balanced`, 32 of 33 diverge, 11 by ≥1.0. The borough card's save button at `index.html:7314` correctly stores `data.score`, so **the two save buttons on the same page disagree with each other**. `git log -L 7531,7531` shows it is a pre-persona artefact carried through four commits with no rationale comment.

**Fix.** Replace the expression at `index.html:7531` with the already-computed `pcScore` variable from line 7463. Consider a one-off backfill or invalidation of stored `buyerScore` values, since the wrong number survives reload.

---

### 5 · Live site and both store listings promise an "exact dB" no code path produces (high)

`index.html:2727` — confirmed live by curl against skyscore.co.uk — reads *"Click any postcode for the exact dB at that spot."* `mobile/fastlane/metadata/ios/en-GB/description.txt` repeats it: *"Tap any postcode for the precise dB at that spot."*

The only source of a per-postcode Lden figure is the DEFRA raster tier, and `app.py:2008/2031` bypasses it before any DynamoDB call. The only place a dB reaches a response is `ldenDb` at `app.py:2057/2075`, inside that bypassed function. **Grepping `index.html` for `ldenDb` returns zero hits** — the frontend has no code that consumes a dB from the API at all; its 30 `dB` occurrences are all static legend band labels.

**Fix.** Reword the legend to describe what the site actually shows (a 0–10 quiet score plus a banded overlay) until the raster tier is un-quarantined. Store copy needs a metadata submission and, for iOS, a review cycle — worth batching with #1 and #19.

---

### 6 · Prototype's "AIRPORT INTELLIGENCE" panel shows fabricated dB readings under a live indicator (high)

The publicly deployed Sky Score Radar renders an *"AIRPORT INTELLIGENCE, EGLL"* panel with a flight count, peak movements, a ticking METAR age, runway utilisation, full METAR weather, and — most damagingly for a noise-data product — four named dB readings: **Hounslow (2.1km) 72.4 dB, Richmond (8.3km) 63.1 dB, Putney (14.7km) 57.8 dB, Westminster (21km) 48.2 dB** (`prototype/index.html:776-793`, static HTML, no ids, never updated).

The animated values are invented in code:
```js
$('flights-today').textContent = (1247 + Math.floor(Math.sin(t*0.1)*20)).toLocaleString();  // :2666
$('peak-mvts').textContent = 87 + Math.floor(Math.random()*5-2);                            // :2667
```

The panel header (`:771`) uses the unmodified `.status-dot` class — green, glowing, `animation: pulse-dot 2s infinite` (`:190-196`). The authors demonstrably knew how to signal "not live": the sibling flight panel deliberately switches to amber and appends `(SIM)` at `:2659-2660`. A case-insensitive grep of the whole file for disclaimer vocabulary (*illustrative, not real, demo only, synthetic, placeholder, indicative, sample data*) returns three hits, all JS comments, none user-facing.

The live-flight feed itself **is** correctly gated (`const liveLicensed = false` at `:1777` with a throw guard) — that part is handled well.

**This is known defect class #1 again:** a figure with no measurement behind it presented as a measurement.

**Fix.** Either remove the panel or add a visible "ILLUSTRATIVE — not measured data" label and switch the status dot to the amber `(SIM)` treatment already used 200 lines away. The four dB rows should go regardless; the product's credibility rests on not inventing decibels.

---

### 7 · METHODOLOGY and CHANGELOG still claim "the other 29 boroughs already agreed" (high)

`METHODOLOGY.md:248-250` — live prose in the crime section, not a changelog entry — reads: *"The other 29 boroughs already agreed with the release within 10 per 1,000 and were left untouched, so v3.5 is a tail correction rather than a vintage roll."* Identical text at `METHODOLOGY.md:974`, `CHANGELOG.md:67`, and a fourth site inside the file the commit *did* edit: `backend/lambdas/score/app.py:84-86`.

Diffing `git show 542e471^:data/borough-extra.json` against the working copy across **all 33 boroughs**: **29 `crimeRate` values changed**; only Camden, Kensington and Chelsea, Westminster and City of London are unchanged; **7 moved by more than 10 per 1,000** (Barking 105→84.2, Hillingdon 72→91.6, Croydon 98→80.4, Tower Hamlets 120→106.6, Hammersmith and Fulham 96→107.0, Merton 70→59.3, Harrow 70→59.5). `sw.js:47-49` already says *"29 of 33 boroughs corrected"* — the repo contradicts itself. `app.py:76` points `methodologyUrl` at this exact document.

**This is known defect class #3 (METHODOLOGY §11 claimed SCHOOL_SCORE was "anchored to the Ofsted distribution"; it was not) recurring verbatim.**

**Fix.** Rewrite all four sites to state 29 of 33 corrected, and cite the diff. Note the claim also *understates* the last correction's size, which is the opposite of the usual drift direction and worth flagging in the changelog.

---

### 8 · City of London reports `liveResolution: "measured"` and credits two bodies that supply nothing (high)

`data/ons_pfa_tables.xlsx`, sheet `Table C4`, row 35: PFA `City of London[note 8]`, total `'[u1]'`. Sheet `Notes - CSP` row 11, verbatim: *"Rates per 1,000 population are not presented for City of London owing to its small resident population."* `data/borough-extra.json:1011-1013` publishes `"crimeRate": 190` — and a script over all 33 boroughs confirms it is the **only** one lacking `crimeVintage`, `crimeTop` *and* `p8`.

Live `GET /v1/score?postcode=EC2V+6AA` returns `"liveResolution": "measured"` and `sources[3] = "Borough metadata: ONS (Crime in England and Wales, Police Force Area data tables, Table C4) and Department for Education (Key Stage 4 Progress 8), Open Government Licence v3.0"`. The schools slot silently falls back to `SCHOOL_SCORE['good']=6` (`app.py:2422`), the retired Ofsted band. `live_resolution()` (`app.py:2440`) counts the slot as measured when `p8` **or** the legacy band is present — so `measured` is per its documented contract, but the contract is wrong for this case, since `METHODOLOGY.md:974` point 7 says the field exists *"so a defaulted component cannot read as a measurement"*.

`?include=score,components` strips `context` entirely, so the `liveResolution` disclosure is opt-out-able while the false source line stays in the always-kept `sources` array.

The estimate itself **is** disclosed at `METHODOLOGY.md:253-259`, which is why this is high rather than critical — the defect is the attribution surface, not an undisclosed number.

**This is known defect class #4 (the API credited the Home Office for a figure that had moved to ONS) at borough rather than city granularity — the exact fault `CITY_PROVENANCE` was built to prevent (`app.py:2281`).**

**Fix.** Make the borough-metadata source line conditional on what actually answered, mirroring the `CITY_PROVENANCE` pattern: when `crimeVintage` is absent, credit "Sky Score estimate (ONS publishes no rate for this area)"; when `p8` is absent, drop the DfE credit. Change `live_resolution` to treat a legacy-band schools fallback as *defaulted*, not present.

---

### 9 · Consumer site prints a self-contradicting, reassuring crime sentence for the City of London (high)

Executing the shipped `crimeNote()` (`index.html:6095-6148`) verbatim in node against the real `data/borough-extra.json`, the City of London output is:

> "190 recorded offences per 1,000 residents — **2.2x the London median of 87.4**. **No single offence type stands out — every major category is close to the London median.** Source: **ONS Table C4**, on mid-2024 population."

Three defects in one sentence. The ratio and the reassurance contradict each other. The reassurance is manufactured purely by the absence of `crimeTop` (the else-branch at `:6143-6145`). The source line comes from the fallback at `:6147` — `extra.crimeVintage || 'ONS Table C4'` — crediting ONS for a figure `METHODOLOGY.md:255-259` says ONS suppresses. Enumerated across all 33 boroughs: 16 take the else-branch, but the other 15 have populated `crimeTop` arrays where the statement is true; City of London is the sole borough where it is manufactured from absence, and the sole one taking the vintage fallback. Rendered at `index.html:7382` and `:7573`. The deployed HTML is byte-identical to local.

**Same class as the DEFRA nodata defect:** not-measured rendered as a reassuring measurement.

**Fix.** Guard both branches on presence: when `crimeTop` is empty, say "Offence breakdown not published for this area"; when `crimeVintage` is absent, say "Sky Score estimate — ONS publishes no rate for this area" rather than defaulting to a source string.

---

### 10 · `/api/` landing and OpenAPI advertise the bypassed DEFRA raster tier (high)

`api/index.html:234` — fetched live from skyscore.co.uk/api/, HTTP 200, byte-identical to local — sells *"v3.1 samples the DEFRA Lden raster at the exact postcode centroid (~10 m grid), with Haversine flight-path proximity as a fallback."* Haversine is not a fallback; since `RASTER_TIER_QUARANTINED = True` it is the only tier that answers. Live `GET /v1/score?postcode=TW6+1AP` → `quietResolution: "postcode"`.

The same over-claim is in the payload itself (`sourceBreakdown.quiet`, `app.py:2302`), in `PROJECT_DOCUMENTATION.md:12`, and in `score-demo/openapi.yaml:736-746`, which keeps `raster` in the `quietResolution` enum and tells integrators they can *"filter for higher-precision results"* with an unreachable value. `METHODOLOGY.md:358` already states *"While the quarantine holds, `'raster'` is never returned"* — the internal doc is right; the customer-facing ones are not.

**Fix.** Add a quarantine banner to `api/index.html` and `sourceBreakdown.quiet`, and mark the `raster` enum value as currently unreturned in the OpenAPI description. Revert when the tier is restored.

---

### 11 · METHODOLOGY §20 and CHANGELOG publish a root cause the code explicitly retracts (high)

`METHODOLOGY.md:972` still reads *"the loaded sample table was invalid"* and *"(6) **Root cause outstanding:** `scripts/load_defra_raster.py` is unfixed. Suspects: a CRS mismatch (British National Grid vs WGS84)…"*. `CHANGELOG.md:38-40` repeats it.

`backend/lambdas/score/app.py:1969-1982` retracts precisely that: *"READ THIS BEFORE HUNTING FOR A LOADER BUG. There isn't one… That was wrong, and it was concluded from a sample of eight postcodes… sampling it at correctly projected coordinates returns 58.2 for TW61AP, identical to the stored value… The defect is COVERAGE, not correctness."* `scripts/load_defra_raster.py:398-424` shows the fix applied. Commit `3f9e833` rewrote only §4.5's warning box; §20 and CHANGELOG were never touched.

**METHODOLOGY.md now contradicts itself within one file**: §4.5 line 360 says in bold *"The raster is not faulty and neither is the loader"*, while §20 six hundred lines later asserts the retracted diagnosis. `METHODOLOGY.md:466/469` (§4.6) carries a third version, *"contents invalid, tier bypassed"*.

**This is known defect class #3 in its purest form,** and it is compounded by class #5's lesson: the retracted diagnosis came from an eight-postcode sample.

**Fix.** Add a dated correction entry to §20 rather than editing history silently, and reconcile §4.6 with §4.5. Mark the loader remediation as done.

---

### 12 · `SECURITY.md` claims GitHub OIDC and a read-only deploy user (high)

`SECURITY.md:30`: *"CI / deploy uses GitHub OIDC where applicable; `flightmap-dev` is the runtime API user with read-only operational scope."*

All three clauses fail. `.github/workflows/deploy-backend.yml:16-20` and `deploy-frontend.yml:12-16` both use `aws-actions/configure-aws-credentials@v4` with `aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}`; `grep -rn 'id-token|role-to-assume|OIDC' .github/` returns **nothing**. `backend/iam-policy.json` grants `cloudformation:DeleteStack` (10), `s3:DeleteBucket` (50), `lambda:DeleteFunction` (64), `iam:CreateRole`/`PutRolePolicy`/`PassRole` (97-104) — not read-only. And `flightmap-dev` is not the runtime user: `grep -n 'Role:' backend/template.yaml` returns zero explicit roles, only `Policies:` blocks at 234/283/437, so SAM generates a per-Lambda role.

This is the paragraph a procurement questionnaire reads. A leaked Actions secret gives an attacker the full production stack, and the document says it would not. `SECURITY.md` itself warns that *"procurement teams catch overstated claims"*.

**Fix.** Rewrite the bullet to describe static keys and the actual policy scope, or implement OIDC and then make the claim true. The former is a five-minute edit; the latter is the better answer.

---

### 13 · `SUBPROCESSORS.md` says the web app never calls postcodes.io (high)

Register row 4 (`SUBPROCESSORS.md:32`) says api.postcodes.io is *"Used only by the native iOS/Android app's 'Score where I am' feature; web app does not call this endpoint"* and receives only *"Lat/lon"*.

`index.html:5805` and `:5811` sit inside `lookupPostcode()`, called from the main search flow at `:6822` and `:6784` — neither native-gated. `index.html:6583` is `fetchAutocomplete()`, fired from a debounced `input` listener at `:8631`. `index.html:15` allow-lists the host in CSP `connect-src`, so the calls are live. Server-side, `backend/lambdas/score/app.py:2679` builds the same URL from `lookup_postcode()` as Tier 2 whenever the NSPL table defers — and `SUBPROCESSORS.md:19-21` defines exactly that postcode as customer data.

So the register misstates both the caller and the data category, in an Art. 28(2) document. `SECURITY.md:65` compounds it: *"AWS is the sole sub-processor of customer data."*

**Fix.** Correct row 4 to state web + native + server-side, data category "postcode (user-typed) and lat/lon". Fold in the four omitted upstreams from finding 34 (Overpass, TfL, Land Registry, MHCLG EPC) and correct §5's residency sentence.

---

### 14 · The airport-quiet invariant vanishes if its own probe fails (high)

`scripts/check_score_sanity.py:139-144` scopes the only airport assertion inside a `for` loop that `continue`s past every non-`TW6 1AP` row, so `check()` is never reached when that probe is absent. Driving `main()` offline with `css.fetch` monkeypatched to 429 only TW6 1AP and leave the other 15 healthy: output is `transport failures: ! TW6 1AP (Heathrow Airport)`, then **eight** PASS lines with **no line at all** for the airport assertion, then `RESULT: PASS (15 postcodes)`, exit 0. The dropout guard at line 125 is `len(rows) < len(PROBES) * 0.9` — 16 probes → threshold 14.4 → 15 survivors clears it. `fetch()` converts every failure into a skip.

This is structurally unique: invariants 2–6 all use comprehensions or unconditional `check()` calls. Invariant 1 is the only one whose assertion is conditional on a probe surviving — and the file's own docstring names it as *"the exact assertion the raster defect violated, at 7.5/10"*, `scripts/preflight.sh:96-100` calls it *"the only check here that can catch a DATA defect"*, and `app.py:2005-2006` explicitly relies on it before lifting the quarantine. TW6 1AP is the first probe, so it is the request most likely to hit a cold Lambda.

**This is the "checks that cannot fail" pattern already in this project's memory, on the single most important assertion in the gate.**

**Fix.** Hoist the airport check out of the loop: look up the row by key and `check(row is not None, 'airport probe returned')` first, so a missing probe fails rather than disappears. Make an omitted assertion print `SKIP` rather than nothing.

---

## 4. Checked and clean

The sweep verified a substantial amount as sound. Recording it so the reader knows the breadth.

**Data correctness (exhaustive, not sampled).**
- All 33 London borough crime rates compared against `data/ons_pfa_tables.xlsx` Table C4 by script: **32 match within 0.06** (Barking aliases correctly at 84.2 vs 84.177); City of London is the only one with no source row.
- All **96** `crimeTop` entries across 32 boroughs: `ratePer1000`, `shareOfTotal` and `vsLondonMedian` all match Table C4 exactly — **0 arithmetic mismatches**. The only issue is the cohort definition (finding 48), which shifts 12 values by 0.1.
- All 33 GeoJSON features in `data/london-boroughs.json` resolve to an `extra` record (0 misses, 1 alias); 0 records missing `flood` or `airQuality`.
- `impact` enumerated across all 38 boroughs in both cities — every value is in `IMPACT_TO_QUIET`; nothing is wrong live.
- `IMPACT_TO_QUIET` is byte-identical between `index.html:4943-4950` and `app.py:106-113`.
- The live `getLiveScore` composite at `index.html:4940` matches `app.py:2426` exactly.

**Provenance that is correct.** `LICENSING.md` is the strongest document in the repo: `:32` records the Ofsted→Progress 8 re-source, `:33` marks the Home Office superseded on 2026-08-02, `:49` correctly gives OpenStreetMap as ODbL 1.0. The `nhs` Lambda emits the mandatory ODbL attribution at runtime (`backend/lambdas/nhs/app.py:37-38`). NYC provenance is correctly disclaimed by `CITY_PROVENANCE['nyc']` — resolving Manhattan returns a breakdown explicitly stating *"NOT ONS, Home Office, DfE, TfL or NHS"*.

**Geometry parity elsewhere.** All 5 London airports and all 4 NYC airports match exactly between site and Lambda. NYC flight paths match exactly (8/8 corridors, 0 waypoint diffs) — **London is the only divergent city**. `scripts/audit_flight_paths.py` matches the site byte-for-byte across all 10 corridors.

**Secrets.** Every tracked non-binary file under 3 MB scanned with 6 patterns (hex40, hex32, AKIA/ASIA, bearer, PEM, `key|secret|token = "..."`): **12 hits, all opened individually**. Ten are test UUIDs, an AOSP commit hash, an ONS dataset id, and an `openssl genrsa` how-to. Only one is a credential (finding 44), and it targets a service retired 2026-05-30. `.env` was never committed — `git log --all -S <EPC_BEARER_TOKEN>` and `git grep` both return 0. `git log --all -S"AKIA"` → 0.

**Escaping discipline.** Of 56 HTML-bearing template literals in `index.html`, **54 are correctly escaped**. `renderNhs` uses `escapeHtml` + `safeUrl`; `renderSoldPrices` uses `escapeHtml` + `encodeURIComponent`; autocomplete uses `escapeHtmlAttr` on `data-value`; favourites, ranking rows and transport all escape. `changes.html`, `score-demo/index.html` and `score-demo/status.html` are clean. No `outerHTML`, `insertAdjacentHTML` or `document.write` anywhere.

**Infrastructure.** PITR is enabled on all four DynamoDB tables (verified by mapping every `PointInTimeRecoveryEnabled` to its enclosing `TableName`). All 9 deployed HTML pages carry a CSP meta (SECURITY.md's "five pages" *understates* coverage). All 8 SHELL_ASSETS return HTTP 200 live. The `js/vendor/d3.v7.min.js` SRI hash matches the checked-in bytes exactly. The prototype's live-flight feed is correctly gated behind `liveLicensed = false` with a throw guard. `/v1/changes` being public is deliberate and documented in the template.

**Test suites.** 357 tests collect and pass (166 backend + 191 root). `test_legacy_nodata_fill_is_treated_as_a_miss` genuinely goes red when its guard is removed. Only **1 of 47** top-level functions in the score Lambda has zero coverage (finding 30). `refresh_crime_from_ons.py --check` compares every London row against the published workbook and exits 1 on drift — a stronger guarantee than a unit test for that failure mode.

---

## 5. Not covered

Honest gaps, from the completeness critic and the individual dimensions.

- **No AWS API calls were made.** Deployed S3 object state, CloudFront distribution config, live IAM policy attachments, actual usage-plan bindings and CloudWatch data were not inspected. Findings that say "live" rest on public HTTPS GETs against skyscore.co.uk / the CloudFront domain and the production API Gateway URL — nothing privileged.
- **The shipped `.ipa` / `.aab` were not downloaded or decompiled.** Finding 1's shipped status is established from the build commit (`4af9bc5`), the build script at that commit, `codemagic.yaml`'s build step, the on-disk `mobile/www/` bundle, and CLAUDE.md's record that v1.0.21 came from that commit. That chain is strong but it is inference, not artefact inspection.
- **The service worker was not executed.** Finding 17 states only that two precache entries are absent from the native bundle; it deliberately does not assert what `cache.addAll` does with a missing entry.
- **No external fact was verified against any publisher.** Not one crime rate, Progress 8 value, dB threshold, METAR reading or noise measurement was checked against a primary release *outside* the repo. Where a figure was checked, it was checked against `data/ons_pfa_tables.xlsx` — a primary source *in* the repo. Finding 6 says the prototype's figures are generated in code and carry no source; it does **not** claim any is factually wrong. Finding 19 says DfE is uncredited, not that any `p8` value is incorrect.
- **`mobile/android/`, `mobile/www/` beyond `data/`, and `store-screenshots/` are unaudited.** So are `archive/` (beyond the credential scan) and the PNG assets.
- **The native `.is-native` UI path was never exercised.** The mobile-redesign CSS and `setMobileView()` are gated behind a class only Capacitor adds; no dimension could run it.
- **Finding 53's exhaustiveness claim is partly unverified.** The "exactly two unescaped sites" figure comes from a template-literal lexer the verifier did not re-run. Both cited sites are confirmed; the *completeness* of the enumeration is not independently checked.
- **Finding 15's severity is contested.** The headline "every borough" overstates — green badges on the white sidebar pass at 5.20, and the runtime data shows 8–9 of 11 elements failing, not 11 of 11.
- **Finding 42's blast radius is unconfirmed.** The CloudFront default TTL and live object headers for `sw.js` were not checked; only the divergence between the two documented deploy paths is established.

---

### Recommended order of work

1. **#2** (flight-path parity) — one data change, closes the largest live divergence and unblocks a truthful §4.5.
2. **#1 + #17 + #18** (native bundle) — one filter change plus three `MISSING` assertions; then rebuild and resubmit.
3. **#4** (saved score) — one-line fix, `pcScore` is already in scope.
4. **#14** (sanity-check hoist) — before anything else lands, so the gate can actually go red.
5. **#8 + #9** (City of London) — conditional attribution on both surfaces.
6. **#5 + #6** (fabricated/undeliverable measurements) — copy edits, but they are the credibility ones.
7. The documentation sweep (#3, #7, #11, #12, #13, #20–#25, #43) — a single echo-work pass while the context is hot, per the project's own discipline.