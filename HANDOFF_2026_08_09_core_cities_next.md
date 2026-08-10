# Handoff, 2026-08-09 late night — Core Cities is next, and most of the data is already here

Read this before picking up city four. It exists so the next session starts
from the measurements below rather than re-deriving them.

## State at handoff

Everything below is **committed and deployed and verified in production**.
Working tree clean. Branch `manchester-frontend-preview`, **51 commits ahead of
`origin/master` and unpushed** — git is local-only on this project by choice.

| Shipped this session | Verified how |
|---|---|
| Greater Manchester on `/v1/score` + `/v1/regions` | `/v1/regions` returns 3 cities; Trafford scores 4.1 |
| Greater Manchester on the consumer site | all 10 boroughs agree site vs API, 3.6 to 8.5 |
| 85 GM neighbourhoods in the ranking | 85 rows live, provenance note renders |
| Country tier (UK / USA) + locator inset | `tests/locator-verify.mjs`, `tests/selector-widths.mjs` |
| Docs propagated | README, CLAUDE.md, ROADMAP, CHANGELOG, METHODOLOGY |

Preflight is **18 blocking stages** and green.

## The three things that are yours, not the code's

1. **Rotate the EPC token.** It was printed into a chat transcript this session
   (reading `backend/samconfig.toml` to check for interactive prompts). The repo
   itself is clean — verified the token is **not** in git history and
   `samconfig.toml` is gitignored — but the project's own rotation policy covers
   chat-log exposure. Regenerate on
   `get-energy-performance-data.communities.gov.uk`, update `.env` and
   `backend/samconfig.toml`, redeploy.
2. **Simulator check on the native city chip.** The country tier changed the
   native segmented control (`.app[data-mview='search']`). The caps and the
   `search-box` margin were updated and are marked **NOT VERIFIED** in
   `index.html`, because `data-mview` is never set on the website and no gate
   here loads the native shell.
3. **Merge `manchester-frontend-preview`.** Production is running an unmerged
   branch.

## Core Cities: what is already solved

**Prices are effectively solved for all eight remaining regions.** Measured
against `data/pp-2025.csv` (HM Land Registry bulk Price Paid, 155 MB, already
on disk, gitignored):

| Region | 2025 sales | Median | Districts matched |
|---|---|---|---|
| West Midlands | 35,236 | £230k | 7/7 |
| West Yorkshire | 36,297 | £205k | 5/5 |
| South Yorkshire | 21,101 | £182k | 4/4 |
| Merseyside | 19,494 | £190k | 4/5 |
| Bristol | 19,167 | £340k | 4/4 |
| Tyne and Wear | 17,917 | £168k | 5/5 |
| Nottingham | 10,474 | £238k | 4/4 |
| Cardiff | 10,488 | £235k | 3/4 |

**The two misses are spelling, not absent data**: `ST. HELENS` and
`VALE OF GLAMORGAN` did not match the district strings I used. Fix the name
list, do not conclude the data is missing.

Also already national and reusable:
- **Crime** — ONS Table C4. `scripts/refresh_crime_from_ons.py` already takes
  `--city`. Watch for extra Community Safety Partnership rows: Greater
  Manchester publishes **eleven** because `Manchester Airport` is its own
  partnership.
- **Schools** — DfE Key Stage 4 Progress 8 by local authority, **2022/23 is the
  terminal vintage** until 2026/27 publishes.
- **Neighbourhoods** — `scripts/build_manchester_neighbourhoods.py` generalises:
  it is parameterised by a borough-name map and already streams the England &
  Wales CSV. Rename and pass a different region.

## What each new city still needs

1. **Boundaries GeoJSON** at `data/<city>-boroughs.json`, **plus a
   `!data/<city>-boroughs.json` line in `.gitignore`** — `data/*` is ignored and
   un-ignored file by file, so a new city's boundaries are invisible to git by
   default. This nearly shipped broken for Manchester: the map rendered, every
   local gate passed, and the file was never in git.
2. **Airport + runway geometry** for the aircraft bands. GM's are runway
   geometry, **not DEFRA**, and its legend says so — a regulator's name on a
   city it does not cover is a false provenance claim.
3. **Registry entries in BOTH holders**: `CITIES` in
   `backend/lambdas/score/app.py` and `CITY_DATA` in `index.html`. Adding a
   registry field means adding it to **every** city — `tests/smoke-local.mjs`
   asserts key parity.
4. **`data/borough-extra.json`** entry, and the three places that still
   enumerate cities by name: `hydrateBoroughExtra()`, `recalcAllScores()` and
   that file. Missing one makes the site score from an empty object while the
   API scores properly — all ten GM boroughs disagreed by up to 1.5 points that
   way, with nothing erroring and the map looking correct.
5. **`SHELL_ASSETS` in `sw.js` + a `make data-deploy` line.** `cache.addAll()`
   is atomic: a precached file missing at the origin stops the service worker
   installing for **every** city.
6. **`LOCATOR_TO_CITY` in `index.html`** — otherwise the city stays a "planned"
   light disc on the inset and the caption keeps saying `2 of 10`.

## Suggested order

**West Midlands (Birmingham) first** — most transactions of the eight, and
Birmingham is the obvious flagship for outreach. Then West Yorkshire (Leeds),
then Merseyside (Liverpool).

## Traps confirmed this session

- **Search `--all` before concluding something was never built.** The country
  tier and locator existed on `worktree-core-cities-spike-2026-07-31` in six
  commits; a search of one file on one branch missed them and a worse version
  was built and discarded. That branch is **kept** precisely because it holds
  work that exists nowhere else.
- **HM Land Registry's linked-data API cannot do district queries**:
  `propertyAddress.postcode=M20` returns **HTTP 200 with an empty list**,
  indistinguishable from "no sales". Use the bulk CSV.
- **CloudFront invalidation needs `export MSYS_NO_PATHCONV=1`** in Git Bash or
  the leading-slash paths are rewritten to Windows paths and the call fails with
  `InvalidArgument`.
- **Read a red proof's output, not just its exit code.** `locator-verify` exited
  1 when its data was removed — but because its own static server crashed with
  `ERR_HTTP_HEADERS_SENT`, not because the assertion failed. Both ported
  harnesses had that bug.
- **"live" in older notes meant MERGED, not SERVED.** Three documents said
  Greater Manchester was live on the API while production answered
  `{"error": "Unsupported city: manchester"}`. Check the endpoint.
