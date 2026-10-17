# Audit waves and what they left behind

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> The 22 Aug, 30 Aug and 7 Sep waves, known issues, F2/F3, the website audit, the current audit.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 837-990 (2026-10-16) -->
## The 2026-09-07 audit wave - 8 criticals and 11 importants closed

Full detail in `AUDIT_REPORT.md`. The things a future session must not undo:

- **`.is-native .sheet-footer`, NOT `.is-tabbed`.** For ten days the mobile web
  homepage rendered **exactly ONE visible link** - the skip link - so /privacy
  and /terms were unreachable from every phone. The rule was correct when
  written: `.is-tabbed` meant "native app", which has its own nav. It came to
  mean "any phone" two days later and nothing re-read it. **A rule keyed on a
  class whose meaning changes is a rule that expires silently.**
  `tests/mobile-legal-links.mjs` asserts REACHABILITY, which nothing did -
  `responsive.mjs`'s four detectors are all about a control that IS rendered.
- **Un-hiding that footer exposed two more defects**, both fixed: its `.sep`
  separators measured **1.97:1** (any alpha under 1 on `--mid` fails AA), and
  its full-width pointer-events band swallowed taps meant for `#layers-trigger`
  at 568x320. *A fix that restores a surface restores its defects with it.*
- **Retired NaPTAN nodes no longer count in the SCORED transport share.** The
  2026-09-01 fix reached `build_city_stations.py` (the list a user READS) and
  not `build_borough_bands.py` (the field that SCORES, 0.25 of liveability, in
  both holders). **City of Nottingham `good` -> `moderate`, live 5.3 -> 4.5,
  score 8.3 -> 8.0.** The reader now hard-fails on an absent `Status` column
  AND on a scan that kept nodes while finding no inactive ones.
- **London credits HM Land Registry again.** The 2026-08-25 edit removed
  'Sold prices: HM Land Registry' reasoning that HMLR backs `/epc` and
  `/sold-prices` "not this response" - right about sold prices, wrong about
  `avgPrice` and `trend`, which are HPI. The flagship city credited no price
  source at all while `sourceBreakdown.afford` named HMLR four lines away.
  APPENDED, never inserted: the postcode line is index 2 by contract.
- **`/v1/chat` calls Bedrock in `us-east-1`** and four documents said that could
  not be happening. Now SUBPROCESSORS row 18 and a rewritten s5 (TWO outbound
  routes, one leaving the EEA). `backend/tests/test_data_residency.py` compares
  the CODE's regions against the REGISTER, so a new region reds on the day it
  lands.
- **Nottingham crime is gated for the first time.** It sat outside `CITY_PFA`
  under a comment whose reason covered only THREE of its four boroughs;
  `City of Nottingham` published 124.9 under a blocking gate that had never
  looked at it. Now compared (it agrees). `NO_ONS_COMPARISON` makes any future
  omission declared rather than silent.
- **Three blocking gates were checking less than they claimed**, all now
  derived: `area-page-freshness` passed on **zero pages**, `score sanity` never
  checked `env`, and borough parity floored at **60 against a real 91**.
- **preflight distinguishes INCONCLUSIVE from PASS.** Three gates deliberately
  exit 0 when they cannot verify, and the runner printed PASS and discarded the
  reason. **And CRASHED from "deviates" since 2026-10-12**: `advise()` printed
  any non-zero exit as "deviates", so `fit_airport_shape.py --check` dying on a
  tuple unpack read as a measured deviation in a PASSing run.
  `advisory_verdict()` keys on lines only a crash prints (Python's `Traceback
  (most recent call last):`, Node's closing `Node.js v<version>`) and reports
  the stage as could-not-verify with its last line;
  `tests/test_preflight_advise.py` runs the real functions, proven red.
- **`lookup_postcode` rejects anything but `[A-Z0-9]{1,8}`.** `quote()` defaults
  to `safe='/'`, so `../outcodes/SW11` traversed into the postcodes.io PATH and
  returned a **500 with a JSON body** from `/badge` - the one thing that
  endpoint's docstring says must never happen, because it renders in an <img>
  on a customer page.
- **Both contrast gates now run a landscape viewport.** No contrast measurement
  had ever run at one; a control at **1.04:1** was living there.

**Still open and deliberately not done:** the IAM privilege-escalation path
(`OPERATIONS.md` s3.8 - it needs a console session and a REAL deploy to verify,
and an untested IAM edit is what caused the 3 Sep outage). **That is the ONLY
item left in this paragraph.**

~~METHODOLOGY s6, whose worked example transposes `quiet` and the total~~ -
**that was audit I6 and it was closed on 2026-09-07, the day it was written**,
by `scripts/check_worked_example.py`, which is BLOCKING in preflight and green.
Verified against the live API 2026-09-11: SW11 1AA returns `score 5.0`,
`quiet 6.4`, `afford 0.4`, `live 7.8`, `env 5.6`, `methodologyVersion 5.0` -
exactly what s6 documents, nothing transposed. **`AUDIT_REPORT.md` records this
same ghost outliving its own fix once already** ("I6 was listed here as open
until 2026-09-08 and had been closed the same day it was written"); this file
was the surviving copy, and `ROADMAP.md`'s closed-items table had it right
("rebuilt at v4.0 and **gated**") the whole time. **Tenth instance of
`memory/feedback-recorded-findings-can-be-inverted.md`** - three documents, one
fact, and the one sessions actually read was the stale one.

**The `healthcareWithin1kmPct` rename is DONE (2026-09-11): the field is
`healthcareWithin500mPct`.** It was never a contract change - it lives in
`data/borough-extra.json` alone, is in `DERIVED_KEYS` and deliberately NOT in
`LAMBDA_FIELDS`, and no endpoint, spec or page emits or reads it. **Doing it
exposed a real gap**: `--write` assigns only keys IN `DERIVED_KEYS` and
`--check` compares only keys IN `DERIVED_KEYS`, so a key that LEAVES the tuple
stops being written and stops being compared in the same edit - the documented
procedure would have published the old key frozen beside the new one on all 86
boroughs, invisibly. `FOREIGN_KEYS` + an orphaned-key check close it, proven red.
**Do not rename a derived field by editing `DERIVED_KEYS` and running `--write`**
- rename it in the holder too, then `--check`.
## Absence must never render as a measurement — the 2026-08-22 sweep

**Shipped and verified live the same day.** Four Lambdas via SAM, six public
surfaces via S3 + a completed CloudFront invalidation. The live responsive audit
went from 10 failing page/viewport combinations to 0, and `/nhs` at an uncovered
bbox point now answers with NHS search links instead of three empty lists.

Ten audit-Important findings closed in one pass, and **most were one defect
wearing different clothes**. Read this before adding any fallback value.

- **`/nhs` asserted absence over 35.4% of its own bounding box.**
  `in_bundle_area()` tests a RECTANGLE (51.25..51.72 by -0.55..0.35) that reaches
  into Surrey, Kent, Essex and Herts. Measured on a 24x24 grid: 204 of 576 points
  had no bundled service within 1500 m and were published as `available: true`
  with three empty lists - "we checked, there is no GP near you". The Overpass
  branch beside it, facing the same gap, returns fallback links and
  `available: false`. One branch admitted ignorance, the other asserted absence,
  for identical missing data. It now falls through. **"A bounding box is not
  containment", fourth instance.**
- **EPC published an unparsed band as the WORST possible property.**
  `BAND_MIDPOINT[band]` inside `if band in bands` was guarded; `.get(band, 0)`
  **ten lines below** was not. 0 is not "unknown" on a 1-100 scale, it is below
  every real certificate - and `rating_to_band(0)` is `'G'`, so a postcode whose
  bands we could not read reported itself as worse than any genuine G. Mirrored
  code, eleven lines apart, **third instance**.
- **A gate that compares nothing was three gates, one of them extra-blocking.**
  `build_aircraft_bands.py`, `build_hpi_prices.py` (also blocking - an empty
  registry printed `0/0 agree`, and `--all` over an empty city list is
  `sum(())` = 0 = PASS) and `build_progress8.py`. All three now print what they
  compared and fail on zero. **The floor is PER-UNIT**: renaming one city's
  marker leaves 104 of 114 bands comparing, which a global `compared > 0` waves
  through.
- **Attribution was per-CONTAINER, not per-request.** `_LOCAL_POSTCODE_SERVED`
  was set True on the first NSPL hit and never reset, so one local hit credited
  ONS in the `sources` array of every later response from that container. The
  comment reasoned about the write race under the batch pool and called it
  "idempotent" - true, and beside the point: the defect is one thread READING
  another's True. Now `threading.local()`, reset in `resolve_query`.
- **The extension deleted its own caveat whenever a basis string existed.** The
  suppression flag tested "the row has some text", but the row carries the
  short per-row basis when `aircraftQuietBasis` is present and only falls back
  to the coverage notice when it is absent - so in the common case the notice
  was filtered out of the disclosure having never been inlined anywhere. Keyed
  on the notice itself now.
- **The pre-release API gate passed on any 4xx.** `res.status < 500`. Measured
  live: `/transport` and `/nhs` were BOTH returning 400 and reported PASS - they
  take `lat`/`lon` and the file had always sent `postcode`. Two of five
  endpoints had never once been exercised. It asserts payload contents now, and
  probes were re-chosen for postcodes that HAVE data: SW11 1AA has no recorded
  sales, so even the endpoint that answered 200 was proved by an empty array.

**Every Lambda timeout was above what API Gateway will wait for**, including the
Globals default (30 against a 29s integration cap). The cost was the smaller
half: at `Timeout: 45`, `/nhs` could not reach its own fallback branch inside
the caller's window, so a slow Overpass produced a raw 504 instead of the
degraded answer the code exists to give. **Raising a timeout past the cap
silently disables the fallback beneath it.** Guarded by
`ApiGatewayTimeoutCapTests`.

**`score-demo/index.html` advertised the free tier at 100 requests/month against
a plan enforcing 10,000**, and sold a batch multiplier the gateway answers with
429. `FreeTierQuotaDriftTests` opens by saying the numbers live in five places
and only one is enforced - and then asserted exactly one of the other four,
the signup Lambda. `template.yaml`'s own list of mirrors omitted this file.
**A list of mirrors that omits a mirror is worse than no list, because it reads
as complete.** The pages are now asserted against the plan.

<!-- CLAUDE.md lines 1116-1153 (2026-10-16) -->
## Audit follow-ups closed 2026-08-30

- **F30 - CI had run neither test suite since 24 July.** `test-backend` and
  `test-e2e` were `needs:` the lint jobs, and the lint jobs failed on FORMATTING
  alone (`ruff format --check` exit 1, `npm run format:check` exit 1) while the
  real checks passed (`ruff check` 0, `npm run lint` 0). A skipped job reports
  neither pass nor fail, so CI looked healthy running nothing. **Formatting is
  now advisory in CI, as it has always been in preflight**, and the test jobs no
  longer `needs:` lint at all - style must never be able to withhold the
  correctness signal.
- **F41 - a Capacitor build shipped 2 of 13 cities' geometry.**
  `mobile/scripts/copy-web.mjs` held a hand-written four-file `REQUIRED_DATA`
  frozen on 3 August. Worse than missing outlines: `sw.js` precaches ELEVEN
  borough files through `cache.addAll()`, which is **atomic**, so the service
  worker would have failed to install at all in the native app. The requirement
  is now **derived** from the `/data/` references in `sw.js` and `index.html`
  (their union, **18 files since `data/stations.json` joined on 2026-09-18**;
  17 before) with a floor of 10, because a regex that matches nothing must not
  produce an empty requirement. Verified by running it: 4 -> 17, and every
  sw.js-precached file present. **Re-measured 2026-09-19: sw.js 11, index.html
  18, union 18** - the derivation picked `stations.json` up with no edit, which
  is the whole point of deriving it.
- **F1 - the scored `environment` component was credited to nobody.** No
  `sourceBreakdown` key and no `sources` line, while `terms.html` obliges
  integrators to carry the sources array through to their own users and
  METHODOLOGY §18 tells their auditor it is complete. The component is 0.14 of
  six personas and 0.18 of `family`/`laterlife`, entirely from three OGL v3.0
  datasets. Both the lineage line and the three source lines are now **derived
  from the borough records per city**, injected into all 13 provenance entries
  rather than written into each, so a city that gains or loses a dataset
  re-describes itself. `build_sources` drops a `None` line, which is how New
  York credits **zero** UK bodies while still SAYING the component is not scored
  there. Cardiff states it is below the two-input floor. **The guard was the
  real problem**: `test_every_city_has_its_own_provenance` asserted the literal
  `{'quiet','afford','growth','live'}` and so passed unchanged through v3.9 and
  v4.0. It now derives the expected set from the components London actually
  emits, and is proven red.

<!-- CLAUDE.md lines 1860-1920 (2026-10-16) -->
## Known Issues

> ## ~~OPEN 2026-09-29: API GATEWAY ERROR RESPONSES LACK HSTS + NOSNIFF~~ DEPLOYED 2026-09-30
> 
> Every Lambda response sends both since `7df6d4e`, and
> `backend/tests/test_security_headers.py` fails any new response path that
> does not - **eight Lambdas each build their own headers, so the test is the
> only thing keeping them in step**. A path with NO route is answered by API
> Gateway itself, so `GatewayResponses` DEFAULT_4XX/5XX in
> `backend/template.yaml` carry both too. **The body template is PINNED to API
> Gateway's own default** (`{"message":$context.error.messageString}`, read off
> the live API before the deploy) - this note said "headers only, never add a
> ResponseTemplate" until then, which was the risky option: SAM's
> `generate_swagger()` writes `responseTemplates: {}` whenever none is given,
> and THROTTLED / QUOTA_EXCEEDED inherit from DEFAULT_4XX, while
> `tests/demo-key-scope.mjs` reads the 429 `messageString` to tell a method
> throttle from a quota. The test reds on the template dropped OR customised
> (both proven). **Verified from the origin:** the reviewed changeset touched
> `FlightMapApi.Body`, a new deployment and the stage's `DeploymentId` only (no
> Lambda, and `MethodSettings` unchanged); `get-gateway-responses` shows
> THROTTLED, QUOTA_EXCEEDED and MISSING_AUTHENTICATION_TOKEN inheriting both
> headers AND the default template; eight unrouted paths answer 403 with HSTS +
> nosniff and an unchanged `{"message":"Missing Authentication Token"}`; and
> `demo-key-scope.mjs` is 6 of 6 PASS on "Too Many Requests" bodies.
> 
> Same day, also shipped: Swagger UI 5.33.0 (5.17.14 bundled a vulnerable
> DOMPurify; 5.33 renders its title as `<h1>`, so the page gives it
> `aria-level="2"` after render or heading-order fails); London borough panels
> show DEFRA NO2/PM2.5 before the curated `aqNote` (it used to REPLACE them);
> the open-data CSV gains `no2_ugm3`/`pm25_ugm3`; "+ VAT" removed - **Cubitt33
> is not VAT-registered, never quote "+ VAT"**. `node scripts/area_summary.mjs`
> makes the free community one-pager from the live API (see OUTREACH_TARGETS
> "Community plan").

> ## ~~THE 11-13 SEP WAVE IS COMMITTED AND NOT DEPLOYED~~ DEPLOYED 2026-09-13
>
> All five surfaces went out on 13 Sep and were verified FROM THE ORIGIN, not
> from exit codes: `check_deploy_drift.sh` **133 of 133** and its new pass
> **`cache-control: 11 of 11 pages revalidate`** (it read 1 of 11 that
> morning); the live `index.html` hash equals source, so the borough panel no
> longer prints `undefined` on 53 boroughs; `/privacy` and `/terms` answer
> `no-cache`; the SAM deploy modified the REST API, its deployment and the
> stage and NO Lambda - which is how the claim that the 11 Sep backend had
> already deployed was confirmed a second way; and a real CORS preflight to
> `/v1/environment` answers **200** with the full CORS header set (was 403).
> `demo-key-scope.mjs` reports what it did on 11 Sep - two checks UNPROVEN
> behind the spent demo quota (audit C0, resets 1 Oct), CI-key batch PASS.
>
> **Two things from the deploy worth keeping.** `make` is on no PATH here, so
> the targets were run by EXPANDING the Makefile's own recipes into `sh`
> (`scratchpad/make_expand.py`) rather than retyping them - retyping is how
> `OPERATIONS.md` s2 came to upload `privacy.html` to a dead key. The expander
> was wrong twice before it was right: its variable regex excluded digits, so
> `$(S3_BUCKET)` survived unexpanded and the check for leftovers, written with
> the SAME regex, reported clean; and it did not strip make's `@` prefix, so
> `data-deploy` died on line 3 under `set -e` with nothing uploaded. Neither
> reached S3. *A check that shares the defect of the thing it checks passes.*
> And the OPTIONS verification in this file and ROADMAP said "-> 204": the
> score handler returns **200**, as `/v1/signup` does; only `/v1/chat` is 204.
> A browser accepts any 2xx for a preflight, so nothing was wrong but the note.

<!-- CLAUDE.md lines 2192-2298 (2026-10-16) -->
**F2 and F3 are CLOSED (2026-09-03), and the gate is the part that matters.**
Every public B2B surface had described a FOUR-component score since v3.9
shipped `env` on 2026-08-26. `score-demo/openapi.yaml` - the artefact
integrators generate clients from - contained the string `env` **zero times**
across `Components`, `Weights` and `sourceBreakdown`, so a strict client
flagged an undocumented field on every UK response outside Cardiff and NYC
and a lenient one dropped 0.14-0.18 of the score; its `quiet` description
denied that road noise is scored (false at v4.0, where road is 0.35 of
`env`); and `enum: [london, nyc]` appeared in **four** places against
THIRTEEN served cities. `api/index.html` said "four components" and its
sample carried pre-v3.9 weights and `methodologyVersion 3.8` under a caption
promising "field names as the live API emits them". The demo drew four bars
summing to **0.86**, so a prospect saw a headline they could not reproduce.

**The consumer half was closed as I34 on 1 September and the B2B half was
not** - mirror drift, the largest cluster in the 31 Aug audit.
`scripts/check_openapi_matches_engine.py` is now **blocking** and derives its
expectation from `app.PERSONAS` / `app.CITIES` / `app.METHODOLOGY_VERSION`
plus the keys `resolve_query` emits, so the spec cannot describe an engine
that does not exist. **It finds enums by RECURSIVE WALK keyed on contents,
never by known path** - the spec's own comment records that "three enums in
this spec listed personas and only one was complete" - and that paid on its
first run by catching a **fourth** city enum (`BatchRequest`) the hand fix
had missed. It also distinguishes REQUEST from RESPONSE persona enums, which
was the gate's own first defect: `custom` is a response value only, and
`persona=custom` measurably returns 200 while silently scoring `balanced`,
so advertising it as an input would document a parameter that does something
else. Proven red five ways including one-enum-short-with-three-complete.
**The area-page half is CLOSED too (2026-09-03).** `build_area_pages.py`
adds `Environment` and all 99 pages are rebuilt: **90 carry it, and the 9
that do not are exactly Cardiff (4) and New York (5)** - matching the
recorded `env` coverage without the builder being told to expect that.
`area pages match the live API` stays **99 of 99**, because a row is not
a score. ~~**Undeployed**: the deploy is blocked on the AWS policy.~~
**DEPLOYED.** That blocker was the 3 Sep IAM outage, resolved 2026-09-04; this
line outlived it by five days and several deploys. A blocker note that does not
name what retires it is a note that expires silently - the same failure this
file records twice more on 2026-09-09.

**A WEBSITE CONTENT AUDIT RAN ON 2026-10-06: `AUDIT_REPORT_2026-10-06-website.md`** (what the
site SAYS, page by page, as four visitors; statuses live in that file). Rules it set:
- **Never call the whole product "open government data" / "OGL".** The UK flight routes (and so the
  quiet estimate) come from the UK AIP (NATS): public, NOT openly licensed. Say "official public
  data" and credit "UK AIP (NATS)" wherever routes are shown. **The FAA's routes need the FAA's
  "as is, without warranty" disclaimer wherever shown** - `/bay-area/` and the full map's legends
  have it, and the front page's footer since 2026-10-07 (`.route-credit`, with the NATS credit,
  checked in `tests/front-page.mjs`).
- **Region names are the API's** (`app.CITIES[key]['name']`): `build_area_pages.py` derives
  `CITY_LABEL` since 2026-10-07 (M3). Its own list had said "Nottinghamshire" for four of the
  county's eight authorities and "Leicestershire" where everything else says Leicester.
  (`refresh_crime_from_ons.py`'s Leicestershire/Nottinghamshire are POLICE FORCES: correct.)
- **Every page carries the site bar** (M1, 2026-10-07: privacy, terms, changes, talks, the API
  reference and status joined): INSIDE each page's own `<header>`, so there is never a second
  banner landmark, in `currentColor` because three of them are dark. 16c checks all twelve.
- **The front page counts engagement** (ROADMAP 3b, 2026-10-07): `front-engaged` once per view
  at a PERSON's first action, then `front-search/example/city/explore/map` once each. Never
  from `search()`: a deep link searches at boot (proven red). The measure is engaged events over
  views of `/`. privacy s2c lists "page views, referrers, screen sizes"; naming action counts
  there is legal wording for Bill (batch 2).
- **`/pricing` is the ONLY page with prices**; `/api/` states none and links `/pricing#platforms`
  (it had kept its own copy, which drifted). `tests/front-page.mjs` 16b fails on a price there.
- **An area page describes itself from its own rows** (`topics()` in `build_area_pages.py`): 22 of
  102 promised "schools" they did not show.

**THE CURRENT AUDIT IS `AUDIT_REPORT_2026-10-16.md`** (0 Critical, 5 Important, 19 Minor; statuses live in
that file). Before it, **`AUDIT_REPORT_2026-10-09.md`** (0 Critical, 8 Important,
17 Minor, read-only). One lesson from it to keep: **the
CloudFront 404 -> `/404.html` mapping is DISTRIBUTION-WIDE and replaced the badge's
"not covered" SVG (a 404 by design) with HTML** - before changing an error response,
check every path that answers 4xx with a body on purpose (I-2). The previous audit,
**`AUDIT_REPORT_2026-10-05.md`** (1 Critical, 8 Important, 20 Minor), still applies;
what a future session must not undo from it:

- **The phone footer is "Privacy · Terms · More" (M-20, closed 2026-10-08, Bill's
  choice).** With no result it flows up under the search card, and its nine links
  ran in three rows across the map's airport labels. The other seven sit in an
  inline `<details class="sheet-more">`, on a search-card-style card when open.
  **Closed, its content is `display: none` on purpose**: Chrome hides a closed
  `<details>` with `content-visibility`, which KEEPS layout boxes, so
  `tests/responsive.mjs` hit-tested all eight hidden links as "covered by the map"
  at every phone width. `tests/mobile-legal-links.mjs` hit-tests both states.

- **`.no-result-yet`, NOT `.empty-state`, marks "nothing searched yet".** The
  tabbed (<=900px) layout hid `.empty-state` and the whole `#tab-analysis`
  card behind it, and every search OUTCOME (not covered, not on the map, not
  found, connection issue) is wrapped in `.empty-state` too - so on a phone a
  search that did not succeed showed NOTHING, for five weeks, while the live
  region announced it. The two placeholders (boot markup, `switchCity()`'s
  reset) carry `.no-result-yet` and the five hide/reveal rules key on that, so
  a message that forgets a class is shown. Same shape as `.is-tabbed
  .sheet-footer` (7 Sep): a rule keyed on a marker whose meaning changed.
- **`innerText` of an element that is not rendered returns its text anyway.**
  `tests/outside-coverage.mjs` read `#sidebar-content.innerText` and passed
  "phone Exeter says not covered" on a `display: none` panel. It hit-tests the
  message's first line box now (`getClientRects()[0]`, because a wrapped
  link's bounding-box centre is on neither line), plus the title, the
  scorecard link and the retry button, at desktop, phone and LANDSCAPE.
- **An outcome card is CAPPED, not floored**: `max-height: calc(100% - 201px)`
  with `flex-shrink: 0`. With `min-height: 0` alone the footer squeezed it to a
  52px sliver at 844x390 with the close button clipped out.
- **The front page (`js/home-engine.mjs`, was `/preview/`) has its own copy of the district-to-city lookup** and it
  misses `Barking and Dagenham` (I-1); the 86-spelling fixture runs against
  `index.html` only. Open findings on the trial page are I-1, I-2, I-4 to I-7.

See `AUDIT_REPORT_2026-09-13.md` (**the last full audit before the 25 Sep and 5 Oct ones, 2026-09-13**; `AUDIT_REPORT.md` is a pointer plus the carried-forward table, and the 09-11 and 08-31 reports sit beside it) for the live list. **Every Critical from every audit to date is closed and deployed as of 13 Sep, and 23 of the 13 Sep report's 24 Importants were closed and deployed the same night** (four tiers, each preflighted, each red-proven, each verified from the origin; the two dead deploy workflows are deleted). **The one open Important is I17** - `/v1/signup` writes any address unverified - and it is a DECISION, with three options in ROADMAP's open-decisions table, not a fix waiting to be typed. **On 2026-09-14, 36 of the report's 37 Minors were closed or converted to decisions across five preflighted commits, all deployed and verified from the origin.** That sentence said "only M14's chat-400 remainder is a fix still to type" and was wrong by one: **M23 was the 37th, never struck in the table, and the 14 Sep brief omitted it** - the list-that-omits-a-member trap, in the list of remaining work. **Both were closed on 2026-09-15** (chat 502 via `retrieve_context`'s third return value; station qualifiers via `split_name`/`display_name`, 1,415 -> 1,390), committed and **DEPLOYED 2026-09-15 and verified from the origin**: SAM modified `ChatFunction` alone; `index.html` uploaded `no-cache` and invalidated (completed); live hash == source; 1,390 stations served with 0 duplicates; `check_deploy_drift.sh` 133 of 133; live `/v1/chat` answers 400 with the score API's wording for a bad postcode and 200 for SW11 1AA. **Next session starts at ROADMAP -> Open decisions -> "What each open decision entails"** and its closing paragraph "Where this stands after 17 Sep": the badge edge cache is APPLIED, verified and repointed (17 Sep, audit M1 closed); the I17 pages are PREPARED on branch `i17-flip-verification-on` with a gate that keeps them red until the TTL lands (OPERATIONS s3.9 step 4); what remains is I17 steps 1-3 (SES, sandbox exit, two IAM verbs - Bill's), the EPC token rotation, and the AWS Marketplace row (after the rebrand). **Those two wrong numbers are FIXED AND DEPLOYED (2026-09-02).** The aircraft near-field floor was a DISC compared against runway-shaped contours (Rushcliffe published `Quiet skies 10.0/10` over 10.43 km2 at >=55 dB; it now publishes **3.4 / `Quiet skies 5.0` / `Moderate`**, verified live), and the neighbourhood medians included HM Land Registry **Category B** transactions, which HMLR's own statistics exclude - 412 of 485 published prices were wrong, so the product carried two price bases. **Both were SHAPE errors, not drift**, which is why a full re-derivation reproduced `borough-extra.json` with 0 disagreements and every gate stayed green throughout - the lesson to keep, since the next one will also be invisible to a consistency check. The long-standing trio closed 2026-07-24: I4 (borough metadata duplication — resolved by removal, `score/app.py` is the single holder), I6 (DLQ on async Lambdas — moot, all 7 functions are APIGW-synchronous), I14 (`PROJECT_DOCUMENTATION.md` — fully refreshed).

Most of the May-6 critical findings have shipped fixes — see `AUDIT_REPORT.md` for the triage column.
