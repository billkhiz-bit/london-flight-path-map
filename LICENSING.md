# Sky Score data-source licensing audit

Every external data source used by Sky Score, with the licence terms,
our use case (consumer site / B2B API / both), required attribution,
and any obligations or restrictions. This is the canonical reference
for "are we allowed to use this commercially" questions.

**TL;DR:** every UK government source is **OGL v3.0** (commercial use OK
with attribution), TfL is similar,
**OpenStreetMap is ODbL and is NOT "similar"** — see the note below,
MHCLG EPC needs attribution + bearer token, Bedrock is a paid AWS
service (and the consumer-side AI features that used it were removed
end-to-end; their Lambda code + template entries live in git history
only, verified 2026-07-23).

> **ODbL is share-alike, not just attribution — corrected 2026-08-05.**
> This TL;DR previously grouped OpenStreetMap with OGL and TfL as
> "similar". It is not. OGL and the TfL licence permit commercial reuse
> on attribution alone; **ODbL 1.0 additionally requires that a
> *Derivative Database* be offered under ODbL**, which for a paid B2B
> product is a materially different obligation. `privacy.html` §5 has
> described it correctly as "share-alike rather than permissive" since
> 2026-08-03, so the two documents disagreed, and the more permissive
> reading was the one sitting in the licensing file.
>
> **Why our current use is very likely outside the share-alike trigger,
> stated so it can be re-checked rather than assumed:**
> 1. ~~OSM is reached through Overpass **per request, as a transient
>    passthrough** for the `/nhs` nearby-facilities panel. Nothing is
>    stored, so there is no database of ours for the term to attach to.~~
>    **NO LONGER TRUE, corrected 2026-08-12.** `backend/lambdas/nhs/london_healthcare.json`
>    is a **stored 3,224-element OSM extract (458 KB) bundled inside the
>    deployed Lambda** and read on the hot path (`nhs/app.py:112`), built by
>    `scripts/fetch_london_healthcare.py`. The re-open trigger below ("if OSM
>    output is ever cached, stored") fired when that snapshot landed and was
>    not actioned. **This is a stored extract of an ODbL database**, so the
>    share-alike question is live and needs an actual answer rather than the
>    assumption above. Point 2 still holds and is what limits the exposure.
> 2. **The healthcare component of the liveability score does not come
>    from OSM**, and that is the load-bearing separation. It comes from
>    `data/borough-extra.json`, derived from the **NHS Organisation Data
>    Service** register since methodology v3.7 (`scripts/fetch_nhs_gp_practices.py`)
>    — OGL, not ODbL. (This file used to describe that field as our own
>    editorial work; see the corrected row in the table below.)
> 3. Attribution is emitted in the `/nhs` response, which ODbL requires
>    regardless.
>
> **Re-open this if any of those three stop being true** — in particular
> if OSM output is ever cached, stored, or fed into a scored component.
> At that point the question becomes whether `/v1/score` output is a
> Produced Work or a Derivative Database, and that is a question for a
> solicitor, not for this file.
**OpenSky was removed entirely on 2026-05-07** — see "Removed sources"
below. We're clean for both consumer + B2B.

---

## Sources used by the B2B API (`/v1/score`)

These appear in the `sources` array of every `/v1/score` response.

| Source | Licence | Use | Attribution | Status |
|---|---|---|---|---|
| **DEFRA Strategic Noise Mapping — road Lden** (Round 4, 2022, England) | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | Borough `roadNoise` band and `roadNoiseLdenMedian` (display-only), and — **SCORED since methodology v4.0 (2026-08-29)** — `roadNoiseAboveWhoPct`, the share of a borough's postcodes at or above WHO 2018's 53 dB road guideline, which is **0.35** of the `environment` component. Also returned per postcode by `/v1/environment` as `roadNoiseLdenDb` - or, where DEFRA surveyed the ground and found it under the lowest level its map records (40 dB, 2.0% of covered postcodes), as the BOUND `roadNoiseBelowDb`, never as a decibel figure. **Every English city since 2026-09-10**; it was London-only before that. **England only** — the coverage is England's, so Cardiff is excluded by name (`NO_ROAD_COVERAGE`) and New York carries none. **This row did not exist until 2026-08-31**: the surface was licensed and attributed under the aircraft row below, which describes a different coverage and does not mention scoring, so the one environmental dataset carrying the largest scored share after air quality had no licensing entry of its own. | "Contains public sector information licensed under the Open Government Licence v3.0" | ✅ Commercial use OK |
| **DEFRA Strategic Noise Mapping** (Round 4, 2022) | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | (a) Quiet score (Lden bands per borough; raster sample at postcode centroid in v3.1). (b) Consumer-site overlay PNG cached on our origin (refreshed via `scripts/refresh_aircraft_noise.sh` when DEFRA publishes a new round, ~5-year cadence). | "Contains public sector information licensed under the Open Government Licence v3.0" | ✅ Commercial use OK |
| **HM Land Registry House Price Index (HPI)** | OGL v3.0 | Affordability + Growth scores (cohort-relative price + trend). Credited in every UK `/v1/score` response - London's line was missing from 2026-08-25 to 2026-09-07, see the note below this table. | **Not "same OGL boilerplate"** (corrected 2026-09-07). HMLR requires its own notice: *"Contains HM Land Registry data (c) Crown copyright and database right YYYY. This data is licensed under the Open Government Licence v3.0."* The project already holds that wording, in the docstring of `scripts/build_city_neighbourhoods.py` - the very script that derives the 481 published medians - and it does not reach any output. | ✅ Commercial use OK |
| **HM Land Registry Price Paid Data** | OGL v3.0 | Recent sold-price comparables (`/sold_prices`) | Same OGL boilerplate | ✅ Commercial use OK |
| **MHCLG Energy Performance of Buildings Register** (`/epc`) | OGL v3.0 + bearer-token T&Cs | EPC band lookup per address | "EPC data: MHCLG, Open Government Licence v3.0" + comply with new bearer-token terms | ✅ Commercial use OK with token rotation hygiene |
| **ONS National Statistics Postcode Lookup (NSPL)** — *live resolver since 2026-07-25* | OGL v3.0 | **Primary** postcode → borough + lat/lon resolution, served from our own DynamoDB table (`london-flight-map-postcodes`, loaded by `scripts/load_nspl.py`). Also still the input to the DEFRA raster sampler — see the offline table below. | "Postcode resolution: ONS National Statistics Postcode Lookup (Open Government Licence v3.0), with postcodes.io (Open Government Licence v3.0) as fallback" — emitted only once the local tier has actually served a lookup, so the credit is never claimed while the table is empty | ✅ Commercial use OK |
| **postcodes.io** (api.postcodes.io) | OGL v3.0 (data) + MIT (the service) | Postcode → admin_district resolution. **Demoted to fallback 2026-07-25**: used when the local NSPL table misses, is unloaded, or errors. The move was made partly for licence hygiene — routing a customer's 100k-address backfill through a free community service is not fair use, whatever the data licence permits. | "Postcode resolution: postcodes.io (Open Government Licence v3.0)" — still the sole credit whenever the local tier has not served | ✅ Commercial use OK |
| **ONS** (population, deprivation, recorded crime) | OGL v3.0 | Liveability composite + crime score normalisation. **Primary crime rate since 2026-08-02**: *Crime in England and Wales*, Police Force Area data tables, year ending March 2026, **Table C4**, offences per 1,000 residents on mid-2024 population. | OGL boilerplate | ✅ Commercial use OK |
| **Department for Education** (Key Stage 4 Progress 8) | OGL v3.0 | Liveability "schools" sub-score. **Re-sourced 2026-08-02** (methodology v3.5): was Ofsted overall-effectiveness grades, which Ofsted abolished in September 2024 and which never reproduced from the published distribution anyway. Now Progress 8, **2023/24, local-authority level (rolled 2026-08-27 from 2022/23)** — and 2023/24 IS the last edition until 2026/27 publishes, because the 2024/25 and 2025/26 cohorts lost their KS2 baseline to the cancelled 2020/2021 test windows. The earlier claim that *2022/23* was terminal was wrong by one year: the cancelled sittings were 2020 and 2021, so 2023/24's cohort (KS2 in 2018/19) has a baseline, and DfE published it on 2025-02-27. | OGL boilerplate | ✅ Commercial use OK |
| **Home Office** (recorded crime statistics) | OGL v3.0 | **Superseded 2026-08-02** — the crime sub-score now reads ONS *Crime in England and Wales* Table C4 (row above). Listed here because scores published before that date used it. | OGL boilerplate | ✅ Commercial use OK |
| **NaPTAN** (DfT National Public Transport Access Nodes) | OGL v3.0 | Two uses, deliberately separate. (a) Liveability **`transport`** sub-score for every borough since methodology v3.6 — share of a borough's postcodes within 800 m of a rail/metro/tram node, a **scored input at 0.25 of liveability**. (b) Since 2026-08-12, the **1,415 stations listed in the detail panel's nearest-stations section** (`scripts/build_city_stations.py`) — **display only**, and deliberately not scored, because scoring them too would count (a) twice. This said "drawn on the map's transport layer" until 2026-09-01; that layer was **deleted on 2026-08-12**, the same day the data landed. The count fell from 1,651 on 2026-09-01 (audit I19: one tram stop was being published as up to five "stations", and 806 retired NaPTAN nodes shipped as current). | OGL boilerplate | ✅ Commercial use OK |
| **NHS Organisation Data Service** (ODS) | OGL v3.0 | Liveability **`healthcare`** sub-score since methodology v3.7 — share of postcodes within 500 m of a GP practice (role RO76). **Scored input at 0.10 of liveability.** Deliberately NOT OpenStreetMap: that choice is what keeps the score clear of ODbL share-alike. | OGL boilerplate | ✅ Commercial use OK |
| **Environment Agency** — Risk of Flooding from Rivers and Sea (RoFRS/NAFRA2) | OGL v3.0 | Borough `flood` band, via the published WMS (no WCS/WFS exists). **SCORED since methodology v3.9 (2026-08-26)**: `floodMediumOrHighPct` is **0.20** of the `environment` component (0.35 until methodology v4.0, 2026-08-29, when road noise became the third scored input; corrected here 2026-08-31). The three-band summary beside it remains display-only. England only — Natural Resources Wales publishes Wales's own, so Cardiff carries air quality without flood. | OGL boilerplate | ✅ Commercial use OK |
| **DEFRA background air-quality maps** (modelled annual mean NO₂ / PM2.5, PCM 1 km grid) | OGL v3.0 | Borough `airQuality` band, the per-postcode NO₂/PM2.5 figures returned by `/v1/environment`, and — **SCORED since methodology v3.9 (2026-08-26)** — `airQualityWhoRatio`, which is **0.45** of the `environment` component (0.65 until methodology v4.0, 2026-08-29; corrected here 2026-08-31). Whole-UK coverage including Wales, so all 13 cities carry it; New York does not, DEFRA being a UK source. | OGL boilerplate | ✅ Commercial use OK |
| **US DOT NTAD** (`geo.dot.gov`) | US federal public domain | Aviation and road noise map layers on the **New York** view (`index.html`). Requested by the visitor's browser, so the layer host receives their IP and map bbox. Display only; nothing here is scored. **Added 2026-09-07** - in live use and absent from this file. | None required; credited on the page | OK |
| **FEMA National Flood Hazard Layer** (`hazards.fema.gov`) | US federal public domain | New York flood layer, browser-requested. Display only. The Environment Agency row above is England only, which is why New York has a separate source and no `environment` score. **Added 2026-09-07.** | None required; credited on the page | OK |
| **US EPA** (`gispub.epa.gov`) | US federal public domain | Air-quality non-attainment areas on the New York view, browser-requested. Display only. **Added 2026-09-07.** | None required; credited on the page | OK |
| **New York borough inputs** (curated) | Compiled by Sky Score from public NYC sources | **SCORED.** NYPD CompStat-derived offence rates per 1,000, curated borough median sale prices (USD), and JFK/LaGuardia approach-geometry aircraft bands - `CITIES['nyc']` in the score Lambda. **Added 2026-09-07**, and this was the largest gap in this file: five boroughs of a commercial API scored from inputs with no licensing position recorded anywhere. They are DERIVED figures, not a redistributed dataset, and `/v1/score` states so - every NYC response carries *"OGL v3.0 covers UK Crown copyright and does NOT apply to any data in this response."* | Sky Score is the source; no third-party notice required | Own work |
| **OurAirports** | Public domain (CC0 dedication) | Runway coordinates and geometry behind every non-London `impact` band (`scripts/build_aircraft_bands.py`). | None required; credited anyway | ✅ Commercial use OK |
| **TfL Open Data** (`/transport`) | [TfL Open Data licence](https://tfl.gov.uk/info-for/open-data-users/our-open-data) | **Line status only, London only, display only.** Corrected 2026-09-07: this row claimed the liveability **`transport` sub-score** and the nearby stations. Both moved to **NaPTAN** - the sub-score at methodology v3.6 (2026-08-11) and the station list on 2026-08-12 - and the NaPTAN row two above has said so since. `backend/lambdas/score/app.py` contains no TfL call at all; the only caller is `backend/lambdas/transport/app.py`, which the detail panel uses for disruption. So this row credited TfL for a scored input it does not supply, in the file whose purpose is to say who supplies what. | "Powered by TfL Open Data. Contains OS data © Crown copyright and database rights..." | ✅ Commercial use OK |

**Conclusion for the B2B API**: every data source is commercial-use-OK
under OGL v3.0 or equivalent open licence. Attribution is enforced via
the `sources` array in every API response. We are **clean to charge for
the API** (per-query, subscription, or usage-tier).

---

## Sources used by the consumer site (`https://skyscore.co.uk`) only

These are visible to consumer-site visitors but NOT exposed via the B2B API.

| Source | Licence | Use | Attribution | Status |
|---|---|---|---|---|
| **OpenStreetMap** (via Overpass API) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/) | Nearby NHS services in `/nhs` (replaced the deprecated NHS Service Search public key) | "OpenStreetMap contributors (ODbL)" — must include in response + visible attribution on the page | ✅ Commercial use OK; **attribution is mandatory** |
| **Office for National Statistics** (NSPL via Geoportal — offline uses) | OGL v3.0 | Postcode lat/lon for the v3.1 raster sampler, **and** the source loaded by `scripts/load_nspl.py` into the live resolver table (see the primary table above). The same on-disk `data/nspl.csv` now feeds both. | OGL boilerplate | ✅ Commercial use OK |
| **DEFRA GeoTIFF (Round 4, 2022)** | OGL v3.0 | Sampled offline by `scripts/load_defra_raster.py`. v2 (with below-threshold sentinel) shipped 2026-05-06; loader running 2026-05-07 against the full ~2.5M NSPL postcode list. Same source as the live noise mapping. | Same OGL boilerplate | ✅ Commercial use OK |
| **House of Commons Library MSOA Names v2.1** (2021 MSOAs) | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | **Verification only, never displayed and never scored.** `scripts/build_city_neighbourhoods.py --check-names` corroborates each of the 281 curated postcode-district labels against that district's own published MSOA names, so a label cannot claim a place no source puts there. The derived join lives in `data/district-msoa-names.json`; the 663 KB source CSV stays local. | OGL boilerplate; not surfaced to users because nothing derived from it reaches a page | ✅ Commercial use OK |
| **`data/borough-extra.json`** — **mostly third-party derived since 2026-08-11, not editorial** | Third-party, all OGL v3.0 (see the five rows added above); the residual `crime`/`schools` PROSE tiers on 38 boroughs remain own editorial work | Borough-level air-quality, flood-risk, schools, crime, transport and healthcare ratings + prose notes shown in the detail panel; also drive the air-quality and flood map fills (the map layers colour boroughs from this file, not from live DEFRA/EA/EPA/FEMA services) | UI badges label these "borough-level rating (curated)" since 2026-07-23 | ✅ No third-party licence involved; must never be presented as official agency data |

---

## Removed sources

| Source | Used for | When removed | Why |
|---|---|---|---|
| **OpenSky Network** (`/api/states/all`) | Live aircraft positions on the consumer-site map and the 3D radar prototype's "live mode" | 2026-05-07 (commit `6f6ce7d`) | Re-reading [their terms](https://opensky-network.org/about/terms-of-use) confirmed a written agreement is required for any operational use, including consumer surfaces. Lambda + UI both removed end-to-end pending a licensing reply. Email enquiry sent — see `OPENSKY_LICENSING_EMAIL.md`. Restoring is `git revert 6f6ce7d` + add OpenSky params back to `.env` + redeploy. |

---

## Backend infrastructure (paid services)

Not "data sources" but listed for completeness.

| Service | Type | Notes |
|---|---|---|
| **AWS Bedrock — Amazon Nova 2 Lite + Nova Pro** | Paid AWS service | Per-token billing; commercial use is the intended use |
| **AWS Lambda / API Gateway / S3 / CloudFront / DynamoDB / ACM** | Paid AWS services | Standard commercial AWS terms |
| **Cloudflare DNS / Cloudflare Registrar** | Free / at-cost | Standard Cloudflare ToS |

---

## Attribution surfacing — where the OGL boilerplate appears

| Surface | How attribution is shown |
|---|---|
| `/v1/score` response | `sources` array (always returned) + `sourceBreakdown` per-component |
| `/v1/score/batch` response | Same `sources` array on the wrapper |
| `/epc`, `/sold_prices`, `/transport`, `/nhs` responses | Each has its own `sources` array |
| Consumer site | Footer link: "Methodology v5.0" → links to the methodology document which lists every source with full attribution + licence |
| Methodology document (`METHODOLOGY.md`) | Section 11 enumerates every source + licence reference |
| `/v1/regions` discovery endpoint | Includes `methodologyVersion` + `methodologyUrl` so integrators can audit licensing |
| **Bulk scoring export** (`scripts/score_bulk.py`) | **Two places, deliberately.** A `sources` column on **every** row naming the sources and OGL v3.0, plus a companion `<output>.sources.txt` carrying the full attribution, the OGL link, and the ONS/OS/Royal Mail copyright notices |

Attribution requirements are **structurally satisfied on the scoring path**,
and there are three exceptions. Corrected 2026-09-07: this read "there is no
code path in the API that returns data without the source array", which was
an absolute claim that three live endpoints falsify.

- **`/badge`** returns an SVG whose entire text content is the score, the
  band and the postcode. No attribution at all, and it is the surface
  designed to render on third-party listing pages, so it is the one where
  the obligation travels furthest from us.
- **`/v1/environment`** returns DEFRA road Lden and DEFRA PCM NO2/PM2.5
  with no `sources` key. The browser extension renders only what that
  response carries, so its Environment section shows no OGL line while its
  EPC, sold-price and NHS siblings do.
- **`/v1/regions`** returns ONS-derived borough lists with the same gap.

`/v1/score`, `/v1/score/batch` and `/v1/changes` all carry it. Recorded
rather than quietly softened, because a licensing file that overstates
compliance is worse than one that admits a gap: the gap is fixable and the
false assurance is what stops anyone fixing it.

### Derived exports — the obligation travels

The bulk scoring CSV is a **derived work**: every row carries an ONS NSPL
centroid and a DEFRA-derived quiet score. OGL v3.0 attribution therefore
survives into it, and shipping the file bare would put the *customer* in
breach as well as us.

It is attributed in two places on purpose. The companion file holds the full
notices, but a customer will inevitably email the CSV on its own — so the
per-row `sources` column is the copy that cannot be separated from the data.

Both are generated from the API's own `build_sources()`, so the export and the
live responses cannot drift apart; and the companion file is written **after**
the run, because `build_sources()` only credits ONS once the local NSPL tier
has genuinely served a lookup. A file that claimed ONS provenance for a run
that had actually fallen back to postcodes.io would be a false claim in a
customer-facing document.

Pinned by `tests/test_score_bulk.py::TestAttribution` rather than left to a
code comment.

**Gap found and closed 2026-07-27.** The export shipped initially with **no
attribution at all** — despite `scripts/load_nspl.py`'s own docstring warning
that "the attribution obligation SURVIVES INTO ANY DERIVED EXPORT. The
Enterprise 'score your whole city' CSV is such an export." The warning was
written before the exporter existed and was not consulted when it was built.

---

## Obligations we're meeting

- ✅ OGL v3.0: attribution included on every response that uses OGL data
- ✅ TfL Open Data: full attribution string in `/transport` responses + methodology
- ✅ OpenStreetMap ODbL: attribution in `/nhs` responses + methodology
- ✅ MHCLG EPC: bearer token rotated per their guidance; attribution in responses
- ✅ Postcodes.io: attribution + we don't redistribute the raw dataset

## Obligations to keep in mind

- 📌 **OpenSky** — only consumer-site, low-risk, but worth a courtesy email to confirm "free public site with attribution + OAuth2 free tier" is OK with them
- 📌 **MHCLG EPC bearer token** — rotate periodically (the production token shouldn't appear in chat logs, terminal scrollback, or any unencrypted persistence per CLAUDE.md note)
- 📌 **NSPL — now a live serving source, not just an offline input (changed 2026-07-25).** The `london-flight-map-postcodes` table is OGL-derived, and `/v1/score` responses carry NSPL-derived `location.postcode`, `latitude`, `longitude` and `borough` directly. OGL v3.0 permits this commercially; the obligation is attribution, which the response `sources` array now carries. Two consequences worth holding:
  - **The planned Enterprise "score your whole city" CSV is a bulk export of NSPL-derived data.** That is allowed under OGL, but the attribution must travel *with the file* — a licence notice in the CSV header or an accompanying README, not merely in the API response the customer never sees. Decide the exact form before the first pilot deliverable ships.
  - We still must not redistribute the raw NSPL dataset itself, as distinct from scores derived from it.

---

## What's NOT in our stack (yet) and would need licensing review

If we add any of these later, **check terms first**:

- Flightradar24 / FlightAware (paid)
- Zoopla / Rightmove listings APIs (commercial-only, expensive)
- Gov.uk Crime API beyond ONS aggregates (mostly OK but check rate limits)
- ADS-B Exchange (would replace OpenSky; their commercial terms differ)
- Any PAID dataset (we currently use only free / open data)

---

## Action items from this audit

| Priority | Action |
|---|---|
| 🟢 None blocking | All current B2B API sources are commercial-use-OK with attribution we're already shipping |
| 🟡 Hygiene | Email OpenSky to confirm consumer-site usage is OK with attribution + free OAuth2 tier |
| 🟡 Hygiene | Rotate MHCLG EPC bearer token (already noted in CLAUDE.md) |
| 🟢 None | DEFRA + ONS + Land Registry + TfL all OGL v3.0; nothing to do |

This document gets refreshed whenever we add or change a data source.
Last reviewed: 2026-09-07 (**five datasets in live use added** - US DOT NTAD, FEMA NFHL, US EPA and the curated New York scored inputs; the **TfL row corrected**, which had credited TfL for the liveability `transport` sub-score that NaPTAN has supplied since v3.6; HMLR's required notice recorded as its own rather than "same OGL boilerplate"; and the absolute attribution claim corrected against three endpoints that falsify it. Found by the 2026-09-07 audit.) — Previous review 2026-07-25 (**ONS NSPL promoted from an offline input to a primary live serving source**, postcodes.io demoted to fallback; response attribution is now conditional on the local tier having actually served, so ONS is never credited while the table is empty. Flagged: the Enterprise city-scale CSV will be a bulk export of NSPL-derived data — allowed under OGL, but the attribution must travel with the file, and that form needs deciding before the first pilot deliverable). — Previous review 2026-05-07 (OpenSky removal end-to-end; AI-powered consumer features removed earlier the same day; loader still running against the full NSPL postcode list).
