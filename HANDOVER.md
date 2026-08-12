# Handover — resuming on another machine

**Written 2026-08-12.** Read this first if you are picking the repo up on a
laptop, or starting a fresh session on this desktop.

---

## 1. State at handover

Everything is committed, pushed and deployed. Nothing is running.

| | |
|---|---|
| Branch | `master`, level with `origin/master` |
| Deploy drift | **zero** across all 16 public surfaces |
| Score sanity | **PASS, 27 postcodes** |
| Preflight | **PASS** |
| Loaders | all finished — air quality complete, 7 DEFRA aircraft rasters loaded and deployed 19:01:57 |

---

## 2. What a second machine CAN and CANNOT do

Use `git push` / `git pull` as the **only** sync. Never OneDrive — an
interrupted write corrupts `.git/`. Clone to
`C:\Users\<you>\projects\london-flight-path-map`.

### Works immediately after `git clone`

- All code, docs, tests
- `npm install` then ESLint, html-validate, Playwright
- `python -m pytest backend/tests/ tests/` — 258 + 241 tests, no network
- Reading `AUDIT_REPORT_2026-08-12.md` and planning

### Needs setup before it works

| Blocker | What it gates | How to fix |
|---|---|---|
| **`.env`** (gitignored) | score sanity, `/preflight`, any live API call, SAM deploy | Copy `.env.example`, fill `EPC_BEARER_TOKEN` and `SKY_SCORE_API_KEY`. The CI key belongs to the `SkyScoreCiTier` plan — **do not** reuse the public demo key from `score-demo/index.html`; that coupled a blocking gate to a public quota once already. |
| **AWS profile `flightmap`** | every deploy, all loaders | `aws configure --profile flightmap`, region `eu-west-2`. Credentials are for the `flightmap-dev` IAM user. |
| **`data/nspl.csv`** (~806 MB, gitignored) | neighbourhood builder, station builder, all DEFRA loaders, air-quality/raster passes | Download link in `scripts/load_defra_raster.py` header. **This is the big one** — most data scripts are unusable without it. |
| **`data/naptan.csv`** (~101 MB) | `build_city_stations.py`, `build_borough_bands.py` transport | `curl -o data/naptan.csv "https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv"` |
| **`data/defra_*.tif`** (~140 MB) | aircraft/road raster work | Per-airport URLs in `scripts/download_defra_wcs.py`. Needs a browser User-Agent or the host 403s. |
| **`data/pp-2025.csv`** (~155 MB) | neighbourhood prices | Auto-downloads on first `build_city_neighbourhoods.py` run. |

**Practical rule:** a laptop is fine for code, docs, tests and review. Anything
touching `data/` or AWS needs the setup above, and the NSPL download alone is
worth starting before you need it.

---

## 3. What is left, highest value first

All traced with evidence in `AUDIT_REPORT_2026-08-12.md`.

1. **`/v1/score/batch` demo-key bypass** (~20 min + deploy) — the demo key
   printed in `score-demo/index.html` is authorised on the batch route, so one
   metered request returns 100 scores. A 2,000/month plan becomes 200,000
   scores, undercutting the £499 tier. Fix: per-method throttle on
   `ScoreDemoUsagePlan` in `backend/template.yaml`, or a route-scoped plan.
2. **Road-noise plausibility ceiling** (~15 min) — `lden_from_row` gained
   `_RASTER_MAX_PLAUSIBLE_DB` on 2026-08-12; its mirror `road_lden_from_row` did
   not, and both read the same row. A `+3.4e38` sentinel would publish as
   `roadNoiseLdenDb`. Also `_lookup_road_lden` is 60 lines with **zero call
   sites**.
3. **The `excellent` air-quality band can never fire** — *needs your decision.*
   All 86 boroughs exceed the WHO 2021 PM2.5 guideline of 5 µg/m³ (range
   6.3–11.3), so the legend advertises a category no UK borough can occupy.
   Either drop the band or re-anchor it to a reachable standard.
4. **`/v1/environment` hardcodes `'london'` geometry** (`app.py:6136`) for every
   UK coordinate. Confirmed locally: a coordinate by Manchester Airport scores
   **10.0** under London geometry against **0.0** under Manchester's. The
   endpoint is unauthenticated and the public extension renders it.
5. **Mobile legend headings at 1.19:1** — inline `style` beats the stylesheet
   override written to fix it. The hardened a11y gate now scans a phone viewport
   but does not open the collapsed legend, so it does not catch this.

---

## 4. Email / outreach

`EMAIL_AUTH_SETUP.md` has the full sequence. Summary:

- **Sending works today** via Gmail "Send mail as" — it is **not aligned**.
  Gmail signs as `gmail.com` while `From:` says `skyscore.co.uk`.
- **Do first, 2 minutes, zero risk:** publish DMARC at `p=none` in Cloudflare.
  It cannot affect delivery and starts the reports.
- **Then:** Google Workspace (~£5/mo) for real DKIM alignment, SPF update,
  verify with **Show original** that DKIM passes *for skyscore.co.uk*, not for
  `gmail.com`.
- **Warm outreach needs none of this** and is unblocked today.

---

## 5. Habits this repo has paid for

Worth re-reading before changing anything:

- **A gate that reads its expectation from the code under test cannot fail.**
  Six instances. `layer-honesty` and `city-switch` were fixed on 2026-08-12.
- **A passing test asserting old behaviour is worse than no test** — it reads as
  evidence. That is how postcode scoring stayed broken for two days.
- **Absence must never render as a measurement.** The `-0.4` transport penalty,
  `|| 'moderate'` fill layers, and "No stations found within 1.5km" were all the
  same defect wearing different clothes.
- **Any count in an assertion or a label is scheduled staleness.**
- **Verify agent and doc claims against primary sources.** Both produced
  confident, wrong figures this session.
