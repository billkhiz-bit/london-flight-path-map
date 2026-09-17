# Audit Report — Sky Score

**Date:** 2026-09-13 (two days after the previous audit, run early because
that day's wave changed the score engine's provenance, the crime writer, the
favourites rows, the drift gate, the Makefile and the SAM template, and a
second pair of eyes on a day's work is cheapest the same day).
**Files scanned:** 8 Lambda handlers (10,494 lines), `backend/template.yaml`,
`backend/iam-policy.json`, 45 `scripts/*.py`, 10 `scripts/*.sh`, `Makefile`,
14 test files, `index.html` (14,489 lines) driven through 11 page-states at up
to 9 viewports, 10 static pages, 100 area pages (5 sampled for content), the
browser extension, `sw.js`, both GitHub workflows, `SECURITY.md`,
`OPERATIONS.md`, `METHODOLOGY.md`. Three parallel passes (backend/scripts code
review, security, frontend), ~250 tool calls, ~60 read-only live requests.
**Not done:** any write to AWS, any call with the public demo key, any
privilege path, `preflight.sh` (already green on this tree).

## Verification key

- **[V]** — verified by me, in this session, by running it or by reading both
  sides of a contradiction. Every Critical and every headline Important below
  was re-run by me after the agent reported it.
- **[A]** — the finding agent verified it by execution; I did not re-run it.
- **[U]** — reasoned from code by the agent, not executed. Listed so it is not
  lost.

---

## Critical Issues

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| C1 | The POSTCODE result panel prints the literal `undefined` and an empty "worst" crime badge on 53 of 91 boroughs — F1 of 11 Sep, in the sibling function that fix did not reach | `index.html:12033, :12095, :12109` | Frontend |
| C2 | `sources` says "NOT a DEFRA sample at this address" on the ~7,300 postcodes in 8 cities where the score IS a DEFRA sample | `backend/lambdas/score/app.py:4899-5080, :5240` | Backend / provenance |

### C1 — the postcode panel prints `undefined` on every borough outside London and NYC **[V]**

`updateSidebarPostcode()` interpolates `${boroughData.property}` unguarded
(`:12033`), calls `ratingBadgeClass(extra.crime)` on a field 53 of 91 records
do not carry — which returns `rating-high`, the worst-crime colour, wrapping
an EMPTY badge (`:12095`) — and emits an empty `<p class="info-note">` under
SCHOOLS (`:12109`). This is **F1 of the 11 Sep report in its sibling**: that
fix guarded `updateSidebar()` (the borough-click panel, `:11735-11765`) and
not `updateSidebarPostcode()` 300 lines below, which is the flow the search
box's own placeholder invites ("Type a postcode").

**Reproduced live 2026-09-13**, three postcodes on the deployed site:

```
M1 1AE   title=M1 1AE   undefined=1  empty rating badges=1
TS1 1AA  title=TS1 1AA  undefined=1  empty rating badges=1
SW11 1AA title=SW11 1AA undefined=0  empty rating badges=0
```

**Why no gate saw it:** `tests/panel-caveat.mjs` (widened on 11 Sep to the
whole panel) renders `updateSidebar()` only; `tests/uk-city-panel.mjs`
renders EXACTLY this panel for non-London cities on every run and asserts
station names, never the word. *When you fix a fabricating default, grep the
whole function family* — the 11 Sep memory said so, and the grep stopped one
function short.

### C2 — the aviation `sources` line denies the DEFRA sample it was scored from **[V]**

Eight cities' `CITY_PROVENANCE` carry a static "Aviation noise context:
ESTIMATED from <airport> runway geometry ...; NOT a DEFRA sample at this
address" line, and `build_sources(city, bd)` has no `quiet_source` argument,
so the array cannot know which tier answered. `data/aircraft-quiet-regions.json`
holds 7,332 postcodes in those cities that the raster tier measures.

**Reproduced live**: `GET /v1/score?postcode=M22+0AD` returns
`context.quietResolution: "raster"`, `coverage.quiet.measuredAtLocation: true`,
`quiet: 1.1` — and in the same body `sources[1]` ends "NOT a DEFRA sample at
this address". No test ties the aviation line to the tier. An integrator
obeying `terms.html` republishes a denial of the dataset that answered, and
that OGL dataset is credited nowhere. Same class as C7 of 7 Sep (London
credited no price source), one field over.

---

## Important Issues

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| ~~I1~~ **FIXED 2026-09-13** | Layers popover on every LANDSCAPE phone opens over the sheet-footer links: tapping "Flight paths" navigates to `/privacy` (844x390, 896x414), opens the App Store (667x375) | `index.html:3556-3585` vs `:2883`, `:487-497` | Frontend |
| ~~I2~~ **FIXED 2026-09-13** | Every AREA search sends the display label (`Chelsea (SW3 5RZ)`) as the postcode to `/epc`, `/sold-prices` and `/badge`; the panel shows a "Not covered" badge and an EPC outage for an area it just scored, and the embed snippet copies the broken badge | `index.html:10905-10907, :12169-12176, :12257-12264` | Frontend |
| ~~I3~~ **FIXED 2026-09-13** | `coverage.notices` says "DEFRA publishes contours for part of this area" for Teesside and Cardiff, whose airports DEFRA does not map; `/v1/environment` says "estimated" for South Yorkshire, where nothing was | `score/app.py:5848-5851, :6009, :7775` | Backend / provenance |
| ~~I4~~ **FIXED 2026-09-13** | Postcode-resolution provenance (ONS NSPL, postcodes.io) is credited by London alone; 12 of 13 cities' `sources` never name the two OGL datasets that resolved the query | `score/app.py:4847` | Backend / provenance |
| ~~I5~~ **FIXED 2026-09-13** | METHODOLOGY s5.4/s6 say internals are unrounded and rounded once; `live` and `env` are rounded to 1dp BEFORE weighting, and 65 of 792 published scores depend on it | `score/app.py:5521, :5765, :6395`; `METHODOLOGY.md:1222` | Backend / docs |
| ~~I6~~ **FIXED 2026-09-13** | The blocking `prices == HM Land Registry` gate cannot see `SNAPSHOT_VINTAGE_LABEL`; the July roll can go green with every UK `afford` lineage naming the wrong month | `scripts/build_hpi_prices.py:300-333`; `score/app.py:282, :4806` | Gate |
| ~~I7~~ **FIXED 2026-09-13** | `build_hpi_prices.py --write` for a non-London city prints a site step that is a no-op, so the documented roll leaves 58 site boroughs on the old vintage | `build_hpi_prices.py:516-553`; `build_city_frontend_block.py:112-114` | Gate / runbook |
| ~~I8~~ **FIXED 2026-09-13** | `advise()` in preflight prints `ok` for a stage that printed INCONCLUSIVE — the 7 Sep fix reached `check()` only; `aws perms` and `quiet estimate` both run under `advise` | `scripts/preflight.sh:141-150, :756, :773` | Gate |
| ~~I9~~ **FIXED 2026-09-13** | `score_bulk.py` writes London's provenance into every customer's licence file (`build_sources()` with no city); the test pins the literal | `scripts/score_bulk.py:397`; `tests/test_score_bulk.py:229` | Backend / B2B |
| ~~I10~~ **FIXED 2026-09-13** | `check_openapi_matches_engine.py` (blocking) exits 0 having resolved zero response samples — the half that caught the 9 Sep weights defect vanishes silently | `scripts/check_openapi_matches_engine.py:93-112, :200-225, :288` | Gate |
| ~~I11~~ **FIXED 2026-09-13** | `chat.verify_answer()` passes any integer 0-10 and any figure whose stripped zeros match a payload number (`330,000` passes via `of: 33`) | `chat/app.py:168, :196` | Backend |
| ~~I12~~ **FIXED 2026-09-13** | `POST /v1/chat` with a valid-JSON non-object body raises out of the handler: raw 502, no CORS; chat is the only Lambda with no final guard | `chat/app.py:244` | Backend |
| ~~I13~~ **FIXED 2026-09-13** | An upstream envelope rename collapses to "no data" with HTTP 200 in `sold_prices` and `transport` — the epc I31 fix never reached its siblings | `sold_prices/app.py:116`; `transport/app.py:129` | Backend |
| ~~I14~~ **FIXED 2026-09-13** | `signup` and `favourites` build boto3 clients on botocore defaults (60s connect/read) inside 10s and 28s functions; the inner budget exceeds the outer, the /nhs 22 Aug class | `signup/app.py:104-105`; `favourites/app.py:44` | Backend |
| ~~I15~~ **FIXED 2026-09-13** | Three Makefile targets' CloudFront invalidations fail under Git Bash (`'/index.html'`, `'/sw.js'`, `'/robots.txt'` are path-mangled); no `MSYS_NO_PATHCONV` in the file that CLAUDE.md says to prefer | `Makefile:176-177, :315-317, :440-442` | Runbook |
| I16 | `load_nspl.py` still runs 20 threads on boto3's default 10-connection pool; CLAUDE.md says every bulk load was fixed on 10 Sep and `ddb_write.py` says both loaders import it | `scripts/load_nspl.py:1176-1180, :866-871` | Scripts |
| I17 (**DECISION, in ROADMAP**) | `/v1/signup` lets anyone subscribe, lock out or enumerate any email address, unauthenticated — F16 of 29 Aug, dropped from every report since | `signup/app.py:321-391, :434` | Security |
| ~~I18~~ **FIXED 2026-09-13** | SECURITY.md and OPERATIONS s3.7/s3.8 say the deploy credential sits in GitHub Actions secrets on the public repo; the repo holds ZERO secrets and both deploy workflows have never run — and would deploy `index.html` with no `Cache-Control` | `SECURITY.md:33-49`; `.github/workflows/deploy-*.yml` | Security / docs |
| ~~I19~~ **FIXED 2026-09-13** | Changing persona while a postcode result is open silently replaces it with the borough panel; the postcode panel's own copy sends the user to that action | `index.html:13273-13276` | Frontend |
| ~~I20~~ **FIXED 2026-09-13** | The site prints the persona's NOMINAL weights beside "no data" rows, so the displayed weights do not reproduce the displayed score (Brooklyn: 14% beside "Environment no data", headline 4.0 not 3.5) — the `weights`-is-applied defect the API fixed 9 Sep, live on the site | `index.html:11685-11729` | Frontend |
| ~~I21~~ **FIXED 2026-09-13** | Hover text at 2.60:1 / 2.38:1 on every ranking row and on today's saved-location buttons; the palette block records `--orange` as failing and provides `--orange-text` for this | `index.html:1285, :2349, :2366` | Frontend / a11y |
| ~~I22~~ **FIXED 2026-09-13** | The postcode result is never announced to screen readers; `#result-status` stays empty or names the previous borough | `index.html:11881` vs `:11632, :10962` | Frontend / a11y |
| ~~I23~~ **FIXED 2026-09-13** | The borough-extra failure notice describes a "neutral 5.0" fallback that no longer exists (measured: quiet+afford rescaled, 5.4) and omits Environment — I9 of 11 Sep, on the site | `index.html:8329-8331` | Frontend |
| ~~I24~~ **FIXED 2026-09-13** | 57 area pages caption the aircraft band "DEFRA Strategic Noise Mapping Round 4" while their own sources paragraph calls it an estimate that is "NOT a DEFRA sample" — the C3 (31 Aug) mechanism one row over | `scripts/build_area_pages.py:239-240` | Provenance |

### Notes on the Importants re-run in this session

- **I1 [V]** — live at 844x390 with the popover open, `elementFromPoint` at the
  centre of the "Flight paths" toggle (y 153, h 44) returns `a href=/privacy`.
  Mechanism per the agent: the sheet-footer flows at y 146-227 in landscape,
  `.sidebar` (z 2) stacks over `#map-container` (z 1) so the popover's z 11
  cannot win — the same trap the city-selector comment at `:3610` documents.
  The two 7 Sep fixes collided: I11 reserved the trigger column for the
  footer links, I12 moved the popover left, into the links. `responsive.mjs`
  has no popover-open state, so its COVERED detector has never seen it.
- **I2 [V]** — live, after typing `Chelsea` + Enter: requests captured
  `/sold-prices?postcode=Chelsea%20(SW3%205RZ)`, `/epc?postcode=...`,
  `/badge?postcode=...`; the rendered badge `<img>` carries the same value.
  Live responses for that value vs `SW3 5RZ`: badge `Not covered` vs `4.4/10`;
  EPC upstream 400 vs `available: true`. Applies to all 128 London areas and
  481 generated districts. `uk-city-panel.mjs` accepts an error message as
  "not Loading…", so it cannot see this.
- **I3 [V]** — `data/aircraft-footprint.json` `unmapped` names teesside (MME),
  cardiff (CWL) and southyorkshire (no airport); live `TS1 2PP` carries the
  "DEFRA publishes contours for part of this area" notice.
- **I5 [V]** — `get_live_score` and `get_env_score` both `return round_1dp(sum(...))`;
  `calc_score` weights those and rounds again at `:6395`. METHODOLOGY s5.4:
  "Internal computation uses unrounded floating-point values". The agent
  re-ran all 792 combinations unrounded: 65 headline scores differ by 0.1. The
  site does the same, so parity holds — only the document is wrong, and the
  9 Sep "won't-change" decision rests on the premise the engine rounds once.
- **I6 [V]** — nothing under `backend/tests`, `tests` or `scripts` reads
  `SNAPSHOT_VINTAGE_LABEL`; `check_vintage_words` scans source text for
  `<Month> 20xx vintage`, and `:4806` builds that phrase from the constant at
  runtime, so the regex sees the 23 literals and never the derived one. The
  agent set the label to `May 2026` in a scratch copy: the gate printed
  `24 strings say 'June 2026 vintage'`, exit 0.
- **I8 [V]** — `advise()` maps exit 0 to `ok` and discards output;
  `check_aws_permissions.py --profile no-such-profile-xyz` prints
  `INCONCLUSIVE ...`, exit 0. CLAUDE.md: "preflight distinguishes
  INCONCLUSIVE from PASS" — for `check()` stages only.
- **I15 [V]** — I ran all three affected targets today ONLY because the
  expander I used exported `MSYS_NO_PATHCONV=1` first; pasted from the file
  as CLAUDE.md prescribes, `'/index.html'` reaches the API as
  `C:/Program Files/Git/index.html`, the 2026-08-26 incident.
- **I17 [V]** — `AUDIT_REPORT_2026-08-29.md:357` carries F16 UNVERIFIED; it
  appears in no later report and not in ROADMAP. The route is reachable with
  no key and no verification step; the stage throttle is 1 rps.
- **I18 [V]** — `gh api .../actions/secrets` → `total_count: 0`; environments
  = `github-pages` only; `deploy-backend.yml` and `deploy-frontend.yml` runs
  = 0 each (`ci.yml` = 293). `deploy-frontend.yml:17` uploads `index.html`
  with no `Cache-Control`; `deploy-backend.yml:21` runs `sam deploy` with no
  `EpcBearerToken` override and no `samconfig.toml`, so it cannot deploy.
  The record is inverted in the SAFE direction, but SECURITY.md tells a
  procurement reader the credential is in GitHub, and s3.7's OIDC remediation
  addresses an exposure that does not exist.
- **I19, I20, I21, I22, I23 [A]** — agent-measured in the browser with the
  keystrokes and numbers quoted in the table; not re-run by me.
- **I4, I7, I9, I10, I11, I12, I13, I14, I16, I24 [A]** — agent-verified by
  running the handler, the script, or a scratch copy; evidence quoted in the
  table.

---

## Minor Issues

Agent-reported, marked [A] where executed and [U] where reasoned from code.

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| ~~M1~~ **CLAIM CORRECTED 2026-09-14, fix is a DECISION - both template comments now say the 24h max-age caches in the browser only (`X-Cache: Miss` measured on every call); three options in ROADMAP Open decisions, A (a cached `/badge*` behaviour on the site distribution) recommended** | `/badge`'s stated cost control ("CloudFront holds a rendered badge for 24h") does not exist: `cacheClusterEnabled: false`, three identical GETs all `X-Cache: Miss`; the 5 RPS throttle is the only bound, and a busy portal page → 429 → broken image | `template.yaml:112, :562` | Security [A] |
| ~~M2~~ **FIXED 2026-09-14 - BotoCoreError handled at both AWS calls (create: 503; record: the key is returned and the orphan row logged by keyId); the AWS error code goes to the log, never the body. The test that asserted the code IN the body was inverted** | Signup can orphan an ENABLED free-tier key on a `BotoCoreError` (only `ClientError` is caught after `create_api_key`), and echoes AWS error codes to anonymous callers — F22 of 29 Aug, also dropped | `signup/app.py:467-474, :480-506` | Security [A] |
| ~~M3~~ **FIXED 2026-09-14 - batch `[]` and favourites DELETE with a non-object body or non-string postcode answer 400; the chat half was already closed by I12 on 13 Sep** | Malformed JSON shapes → 5xx: chat `[]`/typed fields → 502 no CORS; batch `[]` → 500; `DELETE /favourites` with a non-string postcode → 503 "Storage backend temporarily unavailable" | `chat/app.py:242-262`; `score/app.py:8016`; `favourites/app.py:244-246` | Security [A] |
| ~~M4~~ **FIXED 2026-09-14 - both WebView origins allow-listed; test DERIVES them from capacitor.config.ts** | The signup CORS allow-list excludes both native WebView origins (`capacitor://localhost`, `https://localhost`), so the notify form (added 21 Aug) fails in the NEXT native release | `signup/app.py:59-63` | Security [A] |
| ~~M5~~ **FIXED 2026-09-14 - AWS-owned key (re-measured on all four tables), key name + description inventoried as email holders, chat question logging disclosed, erasure step reaches all of them** | SECURITY.md claims DynamoDB uses AWS-managed KMS (it is the AWS-owned key: `SSEDescription: null` on all four) and that signup logs the email (it logs `keyId` only); a third email holder — the API key NAME — is not inventoried; chat logs the question text at WARNING | `SECURITY.md:65, :131, :172`; `signup/app.py:190-191`; `chat/app.py:272` | Security / docs [A] |
| ~~M6~~ **RECORDED 2026-09-14 - SECURITY.md now names `/score-demo/` in the analytics scope and the trade; removing GoatCounter from the key-minting page is a decision row in ROADMAP** | GoatCounter's rolling `count.js` (no SRI possible) executes on the page that mints and displays API keys; SECURITY.md scopes analytics to "the marketing surface only" | `score-demo/index.html:731` | Security [A] |
| ~~M7~~ **CLOSED 2026-09-16.** 14 Sep: SECURITY.md and the preflight skill no longer state a fixed advisory count; `ci.yml` gains `permissions: contents: read`. 15 Sep: Dependabot alerts + security updates ON, all nine `uses:` pinned to SHAs, `dependabot.yml` for the actions ecosystem. 16 Sep: `master` PROTECTED (`.github/branch-protection.master.json`, verified by GET) and all nine Dependabot PRs merged with master CI green; root `npm audit` 5 -> 1 moderate | `npm audit`: 5 advisories (2 high), all dev-only, all `fixAvailable`; SECURITY.md says "4 high". Dependabot security updates disabled; `master` unprotected; `ci.yml` has no `permissions:`; actions pinned by tag | `package.json`; repo settings | Security [A] |
| ~~M8~~ **FIXED 2026-09-14 - docstring now states the approximation and the latent case** | `national_price_bounds` docstring claims substituting one city's slice reproduces the previous pool; false since the June roll moved 54 of 61 non-London prices — measured effect today zero (p5/p95 land on unmoved boroughs), latent | `score/app.py:6173-6190` | Backend [A] |
| ~~M9~~ **FIXED 2026-09-14** | `benchmarks()` docstring and `/v1/changes` "yardsticks" still describe within-city cheapest/dearest affordability (v5.0 is national) | `score/app.py:556-561` | Backend / docs [A] |
| ~~M10~~ **FIXED 2026-09-14 - derived** | Hand-written `'on a 94-borough national pool'` in the NYC branch three lines below the branch that derives `{pool}` | `score/app.py:4830` | Backend [A] |
| ~~M11~~ **FIXED 2026-09-14 - all eight; the stale nhs pair was DELETED, it sat above a correct comment** | Stale numbers in comments: "10s Lambda timeout" (28), "Road Lden is reported, not scored" (0.35 of env since v4.0), "(chat, multi_agent) protected by throttling", "global 10 RPS" (50), "free tier 5 burst / 1 sustained" (2), nhs "45s Timeout" (28), transport "within 1km" (1500), "the 9 Lambdas" (8) | `score/app.py:8043, :5921`; `template.yaml:30, :60, :65`; `nhs/app.py:181`; `transport/app.py:39`; `test_handlers.py:1` | Docs [A] |
| ~~M12~~ **FIXED 2026-09-14 - `_road_absence_notice(city)`, derived from the borough records; four tests** | `/v1/environment` for Cardiff says road noise "has not been measured for this postcode, or is still being loaded" — Cardiff is excluded by name (`NO_ROAD_COVERAGE`); the load will never happen | `score/app.py`; `build_borough_bands.py:231` | Backend [A] |
| ~~M13~~ **FIXED 2026-09-14 - a failed GetItem raises `SignupLookupError`, is logged as `[SIGNUP_LOOKUP_FAILED]`, and the handler answers 503 rather than proceeding as if no row existed** | `signup` `except ClientError: return None` with no log: with GetItem denied a KEY HOLDER on the consumer form gets 200 "already-subscribed" | `signup/app.py:157-158` | Backend [A] |
| ~~M14~~ **FIXED 2026-09-13 (sold_prices, transport) and 2026-09-15 (chat: a crash, 5xx, unreadable or unreachable ScoreFunction is a 502 naming the scoring service; `ChatUpstreamFailureTests`, 3 of 5 red on HEAD)** | `sold_prices` publishes a missing price as `0`; `transport` slices `stops[:8]` before sorting (a coordinate-less stop → `distance: 5728222`); chat reports a ScoreFunction crash as "That location could not be resolved" (400) | `sold_prices/app.py:122`; `transport/app.py:132`; `chat/app.py:259-261` | Backend [A] |
| ~~M15~~ **FIXED 2026-09-14 - `_lambda_client()` / `_bedrock_client()` build once per container, lazily** | chat's comment says the clients were hoisted; only `_BOTO_CONFIG` was — `boto3.client()` runs per request twice | `chat/app.py:78-80, :139, :205` | Backend [A] |
| ~~M16~~ **FIXED 2026-09-14 - `none_nearby()` is the happy-path row (`noneNearby: true`, `fallback: false`, wording names the 1.5 km); both renderers key on `link: true`. `backend/tests/test_error_paths.py` holds all five, 9 of 9 red on the committed Lambdas** | `nhs` happy path publishes a `fallback: true` row for any empty bucket under `available: true`, so "no GP within 1.5 km" and an outage share a row shape | `nhs/app.py:274-277` | Backend [A] |
| ~~M17~~ **FIXED 2026-09-14 - the unreachable OPTIONS branch refuses explicitly (405) and the test says why; `city` and `buyerScore` no longer default to London and 0 for non-site callers** | `favourites` OPTIONS branch unreachable (no event); live OPTIONS answers from the API MOCK with different headers; a test exercises the dead branch; `city` defaults to London and `buyerScore` to `'0'` for any non-site caller | `favourites/app.py:189-190, :228-231` | Backend [A] |
| ~~M18~~ **FIXED 2026-09-14 - row 18 + s5 name the inference profile; `test_cross_region_inference_profiles_are_disclosed_as_such`** | `chat` uses the `us.` cross-region inference profile; `SUBPROCESSORS.md:92` says `us-east-1`; `test_data_residency.py`'s regex cannot see the prefix. Country-level claim holds | `chat/app.py:44` | Docs [U] |
| ~~M19~~ **FIXED 2026-09-14 - Cache-Control on all three objects (sw.js matches the Makefile), the wait reads checkpoint AGE and refuses a STOPPED loader, the invalidation is awaited and every object is hash-verified from the origin** | `load_aircraft_rasters.sh` re-uploads `index.html` and `sw.js` with NO `Cache-Control`, reverting the 8 Sep header; the same runbook waits on checkpoint EXISTENCE (the misreading `load_status.sh` was rewritten to avoid) and deploys on exit code alone | `scripts/load_aircraft_rasters.sh:49-53, :66, :94-101` | Runbook [A] |
| ~~M20~~ **FIXED 2026-09-14 - both loaders: schema checked once and hard (`require_columns`), a full run that wrote nothing fails (`require_wrote_something`), the checkpoint moved to the top of the loop body and flushes first (it sat behind six / four `continue`s - the case its comment claimed fixed), `--limit 0` refused (measured doing a FULL 2,704,817-row dry pass before the fix), help text rewritten; the AQ loader imports the two helpers rather than mirroring them** | Both DEFRA loaders: checkpoint comment describes a fix six `continue`s bypass; schema drift is silent (`KeyError → continue`, `Wrote: 0`, exit 0); `--limit 0` is a full run (nspl refuses it); help text contradicts the code | `load_defra_raster.py:264, :525-645`; `load_defra_air_quality.py:229` | Scripts [A] |
| ~~M21~~ **FIXED 2026-09-14 - warning removed, IAM claim corrected** | `check_log_retention.sh` prints on every run that the Signup group "contains raw email addresses from 26 Jun - 23 Jul 2026" directly after verifying 30-day retention on all 8 groups; `:38-41` says flightmap-dev cannot call `PutRetentionPolicy` (it can) | `scripts/check_log_retention.sh:38-41, :346-354` | Gate [A] |
| ~~M22~~ **FIXED 2026-09-14 - a None from the engine is a failure; the count is DERIVED (17) and asserted as equality both ways; red-proven with env patched to None** | `check_worked_example.py` `if real is None: continue` under a comment condemning it; floor 15 of a maximum 17 — proven: with the two composites patched to `None`, "comparisons made 15", OK, exit 0 | `scripts/check_worked_example.py:157-159` | Gate [A] |
| ~~M23~~ **FIXED 2026-09-15 - the qualifier is split off LAST and restored only when every node carries it (`split_name` / `display_name`); 1,415 -> 1,390, 19 duplicates gone, `Kensington (Olympia)` and `Hayes (Kent)` kept; both stale '18 hand-picked' claims corrected; `test_no_place_is_listed_twice_under_a_qualifier` red on the old arrays** | `build_city_stations.py` still publishes one station twice under a parenthetical (`Abbey Wood` / `Abbey Wood (London)` 28 m apart; ≥15 such pairs) — the I19 shape, a different suffix; and it and CLAUDE.md say London's `STATIONS` is "18 hand-picked interchanges" (693 NaPTAN rows) | `scripts/build_city_stations.py:21-25, :132-138` | Scripts [A] |
| ~~M24~~ **FIXED 2026-09-14 - `--check` fails on a thin page; `airQualityCoverage` derived and written (86 boroughs, all 100.0); an unmatched borough in the aircraft floor is a SystemExit, not a measured zero** | `build_area_pages.py --check` fails only `if not pages`, not on a page under `MIN_FACTS` as its header says; `build_borough_bands.py` has no `airQualityCoverage` (road and flood do); `build_aircraft_bands.py` `hits.get(name, 0.0)` publishes a measured zero for an unmatched borough (48/48 resolve today) | `build_area_pages.py:484-489`; `build_borough_bands.py:784`; `build_aircraft_bands.py:511` | Gates [A] |
| ~~M25~~ **FIXED 2026-09-14 - the KEY was wrong, not the value: now a fingerprint DERIVED from the Lambda ramp; builder imports the ramp; `tests/test_aircraft_quiet_dataset.py`; both files regenerated, 0 of 42,773 values moved** | `build_aircraft_quiet_dataset.py` and `index.html:8095` claim to mirror `METHODOLOGY_VERSION` and hold `'3.6'` against the Lambda's `'5.0'`; no test compares the script's ramp to `app.lden_db_to_quiet` | `scripts/build_aircraft_quiet_dataset.py:76-80` | Scripts [A] |
| ~~M26~~ **FIXED 2026-09-14 - floor derived from `app.PERSONAS`, compared only at matching methodologyVersion (INCONCLUSIVE otherwise); HPI cache keyed by vintage and `--check` probes for the next month** | `check_score_sanity.py` `KNOWN_COMPONENTS` omits `env`, so a vanishing `env` is not caught by the floor the comment describes; `build_hpi_prices.py fetch()` returns early on a cached CSV not keyed by vintage, so "drift is the signal" cannot fire | `scripts/check_score_sanity.py:135`; `scripts/build_hpi_prices.py:237-239` | Gates [U] |
| ~~M27~~ **FIXED 2026-09-14 - `tests/test_script_mirrors.py` holds the three pairs equal (red-proven); the bulk-scorer fixture is five-component and the env column is asserted present AND empty-for-absent; `audit_flight_paths.py` reads the corridors from the Lambda instead of a May hand copy (21 waypoints on Lambourne, not 5)** | Unguarded mirrored sets (`NO_ROAD_COVERAGE`/`WELSH`, `NO_FLOOD_COVERAGE`/`NO_COVERAGE`, `NAPTAN_RAIL_TYPES`/`RAIL_TYPES`) agree today with no drift test; `test_score_bulk.py` fixture is four-component so the `env` column is untested; `audit_flight_paths.py` mirror has 4-7 waypoints against 11-23 live | various | Scripts [A] |
| ~~M28~~ **FIXED 2026-09-14 - OUT_PATH deleted, total_differ printed, SKIP labelled as the record it is, the orphan CSS deleted, `.defra_load_failures_*` ignored. `_in_registry` is USED (main:751) - that part of the finding was wrong** | Dead/decorative: `build_city_neighbourhoods.py:566 OUT_PATH`, `:1111 total_differ`; `update_canonical_url.py:50-61 SKIP`; `build_hpi_prices.py:216-220 _in_registry`; `.borough-list-item` CSS with no markup; `.gitignore` ignores `.defra_load_failures_air_quality*` but not the road/aircraft siblings | various | Housekeeping [A] |
| ~~M29~~ **FIXED 2026-09-14 - all six** | Stale runbook numbers: `load_nspl.py` "~6-7 hours" (59 min), names `lad25cd`; `load_defra_raster.py` "BatchWriteItem 25 per request" (per-item), verifies with `ItemCount` (which `:679` forbids); `load_status.sh` `NSPL_ROWS=2723596` (2,729,090); `Makefile` help omits five targets; `preflight.sh:775` "all 14 publicly-served files" (133); CLAUDE.md's target table omits `deeplinks-deploy` | various | Docs [A] |
| ~~M30~~ **FIXED 2026-09-14 - focus moves to the row that took the removed one's place (or the list), #favourites-status announces it, the open button is named by its content; five checks added to `favourites-keyboard.mjs`, all red on the 13 Sep page** | After a keyboard Remove in Saved, focus lands on `<body>` and nothing is announced; the `fav-open` `aria-label` replaces the row's visible data in the accessible name | `index.html:12380` | Frontend / a11y [A] |
| ~~M31~~ **FIXED 2026-09-14 - `role="img"`, label says the map is mouse-only and names the keyboard routes** | `#map-svg` is `role="application"` with no focusable descendants and no key handlers; `role="img"` is the honest description, by the 8 Sep locator reasoning | `index.html:4144` | Frontend / a11y [A] |
| ~~M32~~ **FIXED 2026-09-14 - the phone title is visually hidden, not display:none; `page-has-heading-one` promoted into FAIL_MODERATE (red at 844x390 on the pre-fix page). Whether a VISIBLE wordmark belongs on the phone landing state is left as a design judgement for Bill** | Phones have no visible heading on the landing state (the only `<h1>` is `display:none` in the search view); axe `page-has-heading-one` at 844x390 | `index.html:3596` | Frontend [A] |
| ~~M33~~ **FIXED 2026-09-14 - it was every DESKTOP width too (301px table in a 291px sidebar box): 3px cell padding fits it at 291; `#borough-ranking` gets its own overflow-x scroller for phones; `responsive.mjs` gains a ranking-open state and a table-respects-its-gutter detector, red at 320, 901 and 1280 on the pre-fix page** | Neighbourhood ranking table overflows its gutter by 1px at 320x568 with no x-scroller; `responsive.mjs` does not audit the ranking view | `index.html:1236` | Frontend [A] |
| ~~M34~~ **FIXED 2026-09-14 - two muted-text tokens (5.30:1 / 4.87:1) replace #6b7c93 (8 rules), #8a97a8 (5 text rules the audit did not count) and the debug row's #727d8a (4.19:1 under a comment calling it fixed); `<header>` -> `<div>`. Axe over the rendered panel: 8 contrast + 1 nested-banner before, 0 after** | Extension panel: `#6b7c93` on white = 4.26:1 at 11-12px in eight rules (axe `color-contrast` ×10); `<header>` computes to a nested banner | `extension/content/panel.css:200-562`; `panel.js:1240` | Extension / a11y [A] |
| ~~M35~~ **FIXED 2026-09-13** | NOT FOUND leaves `document.title` naming the previous result — the 11 Sep `renderSearchFailure()` item, also at the `!result` branch | `index.html:10961` | Frontend [A] |
| ~~M36~~ **FIXED 2026-09-14 - both footers separate Areas from Privacy; the stations heading is source-neutral and each renderer names its source (TfL / NaPTAN); score-demo inputs have a visible focus ring. `prototype/index.html` is still in no gate - a design decision (it is a Three.js canvas with its own a11y story)** | Copy: both footers omit the separator between "Areas" and "Privacy"; the London postcode panel heading says "(LIVE TfL DATA)" when the NaPTAN fallback renders under it; `score-demo` inputs `outline:none` with border-only focus; `prototype/index.html` is in no gate (no landmarks/headings) | `index.html:4189, :12116`; `score-demo/index.html:126` | Frontend [A]/[U] |
| ~~M37~~ **FIXED 2026-09-14 - the entry says the breakdown is on the consumer site today and planned for THIS response** | `plannedComponents.crimeBreakdown: "planned"` while today's wave derived `crimeTop` for 85 of 91 boroughs into the site holder — planned for the API, so not a contradiction, but the next reader will "close" it | `score/app.py:7421-7431` | Docs [A] |

---

## Categories reported CLEAN

- **Auth gates and denies (live)** — without a key: `/v1/score` 403,
  `/v1/score/batch` 403, `/v1/chat` 403; open by design and 200: `/v1/regions`,
  `/v1/changes`, `/v1/environment`, `/badge`, `/epc`, `/sold-prices`,
  `/transport`, `/nhs`; `/favourites` 401 without token; key in header only.
  All 13 OPTIONS answer 2xx (today's `EnvironmentOptions` un-gating
  confirmed). Free-tier key: batch 429, chat 429, score 200. Live stage
  `methodSettings` = exactly the template's 14 routes + `*/*`.
- **Injection / SSRF / XSS** — every outbound URL read; `lookup_postcode`'s
  `[A-Z0-9]{1,8}` gate holds against traversal; `/badge` fully entity-escapes;
  the extension is `textContent` throughout; no `shell=True`, `eval`,
  `verify=False` anywhere.
- **Secrets** — none in tracked source or in 640 commits across all branches;
  `.env` and `samconfig.toml` ignored; no script prints a credential.
- **IAM on Lambda roles** — least-privilege per function as the template
  declares; nothing widens the known s3.8 path.
- **Origin / CDN / CSP / service worker / extension manifest / security.txt** —
  as declared; `no-cache` verified on all 9 HTML pages + `openapi.yaml`.
- **Today's wave, fresh eyes** — `refresh_crime_from_ons.py --write --all`
  accumulates per city correctly with London medians as one cached holder;
  `demo-key-scope.mjs`'s body discrimination is sound and conservative;
  `check_deploy_drift.sh`'s page pass is derived from `SURFACES` with a floor;
  `cost_real_growth.py` uses `growth_score` exactly as `calc_score` does;
  `crimeNote()`'s new sentences derive from `crimeTop` correctly; the
  favourites rows are two real sibling buttons with no nested-interactive.
- **Dead code** — AST + reference count over 53 files: 0 unreferenced
  module-level functions; ruff F401/F841/F811/F821 clean.
- **Gates run green** — `check_openapi_matches_engine.py` (22),
  `check_worked_example.py` (17), `build_aircraft_bands.py --check` (114/0),
  `build_hpi_prices.py --check --all` (12 cities), `build_progress8.py --check`
  (79), `build_area_pages.py --check` (99), `--check-names` (281/281),
  `check_aws_permissions.py` (18/0), `check_deploy_drift.sh` (133/133).
- **Rounding residual** — worst published `sum(components×weights) − score`
  0.0674; "under 0.07" holds. `LAD_TO_BOROUGH` vs `CITY_LADS` 94/94 identical;
  `AIRPORT_NOISE_SCALE` / `FOOTPRINT_RADIUS_KM` reproduce from the 12
  GeoTIFFs.
- **Axe, every tag incl. wcag22aa + best-practice** — landing, borough panel,
  metric detail, postcode result, ranking (both views), persona selected,
  favourites populated, autocomplete open, NOT FOUND, layers popover, legend
  expanded, at 1440x900 / 375x667 / 844x390: 0 violations except I21 and M32.
- **Focus / tab order / accessible names** — 54 desktop and 32 phone stops
  after a result, every one named, in view, with a measurable focus style; no
  stop leads nowhere (the tooltip stop removed today left nothing dangling).
- **Autocomplete, layers popover in portrait, tap targets in driven states,
  area-page content uniqueness, static-page landmarks and counts** — clean.
- **Performance** — index.html 920 KB, inline script 734 KB (24% comments);
  `#app` visible 120-254 ms, boroughs drawn ≤260 ms; at 4× CPU throttle 521 ms.
  Nothing worth reporting.

---

## The pattern, and what to do about it

**Both Criticals are a fix that stopped one function short of the family.**
F1 of 11 Sep guarded `updateSidebar()` and not `updateSidebarPostcode()`;
C7 of 7 Sep credited London's price source and not the other twelve cities'
aviation line. I3, I4, I9, I13, I14, I23 and I24 are the same shape: a
correction applied to the instance the audit named, with siblings left as
they were. The gate to write is not a seventh panel test; it is a test that
enumerates the *family* — every function that renders a borough record,
every city's provenance block, every Lambda's client config — and asserts the
property across all of them. `test_every_city_has_its_own_provenance` is the
model: it derives the expected set from the engine rather than naming it.

**Three gates cannot go red on the thing they are for** (I6, I8, I10) and two
findings were dropped from the record rather than closed (I17, M2). The
"recorded findings vanish" pattern now has a second instance in one report;
the fix is a carried-forward table in `AUDIT_REPORT.md` that lists every
UNVERIFIED/open item from every prior report until it is closed BY NAME.

---

## Summary

- **Critical: 2** — C1 (postcode panel `undefined`, live, primary flow),
  C2 (sources deny the DEFRA sample, live, 8 cities). Both verified in-session.
- **Important: 24 found; 23 closed the same night, 1 (I17) is a decision in ROADMAP.**
- **Minor: 37** — agent-reported.
- **Categories clean:** 14, listed above with what was checked and how.

**Fixed in this session (both Criticals), each proven red before and green after:**

- **C1 — `updateSidebarPostcode()` guarded** exactly as `updateSidebar()` was
  on 11 Sep (`property`, `crime` badge, `schoolNote`; `:12033`, `:12095`,
  `:12109`). **Gated**: `tests/uk-city-panel.mjs` — the file that had rendered
  this panel every run — now asserts the WHOLE panel prints no `undefined`
  and carries no empty rating badge, for every city including London and NYC.
  Run against the still-deployed page: **6 FAIL** (Manchester, West Midlands,
  West Yorkshire: one occurrence and one empty badge each); against the tree:
  all PASS.
- **C2 — `build_sources()` takes `quiet_source`** (the response's own
  `context.quietResolution`) and, when the DEFRA raster answered, replaces
  the regional geometry line with one crediting "DEFRA Round 4 strategic
  noise mapping, Lden sampled at this postcode (OGL v3.0)". The eight
  estimate strings are unchanged data; the substitution keys on a prefix
  constant. **Gated**: `AviationSourceLineMatchesTierTests` drives
  `resolve_query` on a Manchester postcode with a stubbed noise row - both
  tiers asserted (raster credits DEFRA and denies nothing; geometry keeps the
  estimate line) plus a registry-wide check that every estimate line still
  carries the marker. Against the committed engine: **11 failed**; fixed:
  3 passed.

****Tier 4 of the backlog (backend robustness + security) closed the same night; deployed:**

- **I11** — `verify_answer()` tells a 0-10 integer beside a SCORE CUE
  ("score", "rated", "out of 10", "/10") from a bare count in prose: the
  former must be in the payload, the latter stays trivial, and the "10" of
  "out of 10" is exempted as the scale. The `priceRankInCity` pair is
  removed from the grounding haystack. The audit's three passes ("the quiet
  score is 9", "330,000" via `of: 33`, "120,000" via `rank: 12`) now fail;
  "3 things worth noting" still passes.
- **I12** — a valid-JSON non-object body, or a mistyped field, is a 400 with
  the CORS headers; and `handler()` wraps `_handle()` in the final guard the
  other six Lambdas carry, so nothing escapes as a raw 502.
- **I13** — `sold_prices` answers 502 "unexpected shape" when `result.items`
  is not a list (an empty list is still a measurement), and drops a sale
  with no numeric price rather than publishing `0` (M14); `transport`
  returns `None` - the outage signal its caller already handles - when
  `stopPoints` is not a list, and sorts ALL stops by distance before taking
  the nearest, skipping any without a coordinate (M14).
- **I14** — `signup` and `favourites` gained a `_BOTO_CONFIG`; `chat` drops
  to one attempt; each module declares `_SEQUENTIAL_HOPS` and
  `InnerClientBudgetTests` asserts hops x budget < the function's Timeout
  for all three (it had asserted chat alone, one-hop). `SignupFunction`
  Timeout 10 -> 28: four sequential calls cannot fit in ten seconds at any
  honest per-call budget.
- **I18** — `SECURITY.md` and `OPERATIONS.md` §3.7/§3.8 now say what
  `gh api` measured: zero repository secrets, no `production` environment,
  the two deploy workflows never run. Both workflow files are deleted (one
  could not have deployed, the other would have reverted the Cache-Control
  fix); §3.7 is kept as the OIDC design for CI deploys if they are ever
  wanted.
- **I17** — not coded: it needs a product decision (verification email, or
  two lesser options). Written into ROADMAP's open-decisions table with the
  trade-offs.

Every guard was red on the committed Lambdas (18 failures) and green on the
fix (419 backend tests).

**Tier 3 of the backlog (user-facing frontend) closed the same night; deployed:**

- **I1** — the sheet footer yields (`display: none`) while the layers popover
  is open, via a `layers-open` class on `<html>` set by one `setLayersOpen()`
  beside `aria-expanded` - the idiom the legend already uses. In the GENERAL
  phone block, not the landscape one: the first version was landscape-only
  and left 320x568 covered (the Methodology link under "Aircraft noise").
  `tests/responsive.mjs` gained a `layers open` state scoped to the trigger's
  own media rule (71 -> 78 combinations); it was red against the still-
  deployed page (`Flight paths covered by a[href=/privacy]` at 844x390) and
  clean on the source at every phone viewport.
- **I2** — the area search keeps the REAL postcode in `postcode` and carries
  the display name in a new `label`; the panel title and heading read the
  label, every fetch, the badge, the embed snippet and the favourite read the
  postcode. Measured: `/epc`, `/sold-prices` and `/badge` now receive
  `SW3 5RZ` for a "Chelsea" search.
- **I19** — the sidebar records what it is showing (`panelSubject`); a
  persona change re-renders a postcode result AS a postcode result, with the
  borough record recalculated, and stays on the tab the user was on. Measured:
  title stays `CHELSEA (SW3 5RZ)`, LOCATION section present, ranking tab kept.
- **I21** — hover text uses `--orange-text` (5.65:1) instead of `--orange`
  (2.60:1 / 2.38:1) on the ranking rows and the saved-location buttons.
- **I22** — `updateSidebarPostcode()` announces `Results loaded for <label>`
  through the same live region the borough panel uses.
- **M35** (with it) — both not-found paths set `document.title` and clear the
  panel subject, so a persona change cannot resurrect a lost result.

**Tier 2 of the backlog (live false statements) closed the same night; deployed - see the deploy note below:**

- **I3** — `_defra_contour_status(city)` derives mapped / unmapped / none from
  the geometry registry against `AIRPORT_NOISE_SCALE`; `build_coverage` and
  `handle_environment` choose the estimate notice through one helper. Teesside
  and Cardiff now say DEFRA publishes no contours for their airport; South
  Yorkshire says no commercial airport operates and no estimate is made.
  Guarded through `resolve_query` and `handle_environment`; 14 failures on the
  committed engine.
- **I4** — the postcode-resolution line is injected into every UK city's
  `sources` in the same loop as the environment lines (appended, so no index
  moves; London keeps its index-2 copy; NYC gets none). Guarded per city.
- **I5** — METHODOLOGY §5.4 now says which components enter the sum rounded
  (`live` and `env`, at their published 1dp) and which unrounded; §6's
  contrast corrected to match.
- **I9** — `score_bulk.py` records the cities it scored and writes the
  companion file through `app.build_batch_sources(cities)`; the test that
  pinned the literal `build_sources()` now asserts a Manchester export carries
  Manchester Airport and not Heathrow or the Met, and a two-city export
  prefixes each line.
- **I20** — the borough panel prints the APPLIED weights, rescaled over the
  components present exactly as `combineWeighted()` scores them: Brooklyn
  reads 37/31/0/31/0 and those weights reproduce its 4.0; Camden unchanged.
- **I23** — the borough-extra failure notice describes omission and
  re-weighting, names Environment, and drops the "neutral 5.0" that v3.8
  retired.
- **I24** — the area-page aircraft caption is derived from the same contour
  status: 82 pages "estimated from airport geometry, ladder scaled by the
  DEFRA Round 4 footprint", 9 "DEFRA Round 4 does not map this airport",
  4 "no commercial airport"; New York none. All 99 rebuilt.

**Tier 1 of the backlog (roll safety) closed the same night, no deploy needed:**

- **I6** — `check_vintage_words` now also asserts `SNAPSHOT_VINTAGE_LABEL`
  equals the vintage month. Red with the constant set to `May 2026` while all
  24 literals still said June; green after.
- **I7** — `--write` rewrites the site block for EVERY city that has one
  (marker `const <CITY>_BOROUGH_DATA_RAW = {`) and fails loudly for a
  non-backend-only city with none. Proven by perturbing Salford in both
  holders and letting `--write --city manchester` put both back (no diff).
- **I8** — `advise()` captures output and prints `INCONCLUSIVE (advisory)`,
  naming the stage in the summary, exactly as `check()` does. Proven on the
  permissions probe with a broken profile (INCONCLUSIVE) and the real one (ok).
- **I10** — the OpenAPI gate counts resolved samples and fails unless ALL
  resolve; a renamed borough in `SAMPLES` now fails (`4 of 5`) where it
  passed with 17 comparisons.
- **I15** — every `create-invalidation` recipe carries `MSYS_NO_PATHCONV=1` on
  the command, so it survives being pasted into Git Bash; demonstrated on the
  same mangling with `sts get-caller-identity --query '/index.html'`.

Both deployed the same evening and verified from the origin**: `web-deploy`
+ invalidation, then `uk-city-panel.mjs` pointed at CloudFront - the run that
was 6 FAIL an hour earlier is all PASS; SAM deploy (changeset: ScoreFunction,
FlightMapApi, and the chat function that references the score ARN), then
live `M22 0AD` returns `quietResolution: raster` beside "DEFRA Round 4
strategic noise mapping, Lden sampled at this postcode" and `M1 1AE`
(`postcode` tier) keeps the estimate line. `check_deploy_drift.sh` 133 of 133.
