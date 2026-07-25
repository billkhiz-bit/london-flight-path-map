# Sky Score data-source licensing audit

Every external data source used by Sky Score, with the licence terms,
our use case (consumer site / B2B API / both), required attribution,
and any obligations or restrictions. This is the canonical reference
for "are we allowed to use this commercially" questions.

**TL;DR:** every UK government source is **OGL v3.0** (commercial use OK
with attribution), TfL is similar, OpenStreetMap is ODbL (similar),
MHCLG EPC needs attribution + bearer token, Bedrock is a paid AWS
service (and the consumer-side AI features that used it were removed
end-to-end; their Lambda code + template entries live in git history
only, verified 2026-07-23).
**OpenSky was removed entirely on 2026-05-07** — see "Removed sources"
below. We're clean for both consumer + B2B.

---

## Sources used by the B2B API (`/v1/score`)

These appear in the `sources` array of every `/v1/score` response.

| Source | Licence | Use | Attribution | Status |
|---|---|---|---|---|
| **DEFRA Strategic Noise Mapping** (Round 4, 2022) | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | (a) Quiet score (Lden bands per borough; raster sample at postcode centroid in v3.1). (b) Consumer-site overlay PNG cached on our origin (refreshed via `scripts/refresh_aircraft_noise.sh` when DEFRA publishes a new round, ~5-year cadence). | "Contains public sector information licensed under the Open Government Licence v3.0" | ✅ Commercial use OK |
| **HM Land Registry House Price Index (HPI)** | OGL v3.0 | Affordability + Growth scores (cohort-relative price + trend) | Same OGL boilerplate | ✅ Commercial use OK |
| **HM Land Registry Price Paid Data** | OGL v3.0 | Recent sold-price comparables (`/sold_prices`) | Same OGL boilerplate | ✅ Commercial use OK |
| **MHCLG Energy Performance of Buildings Register** (`/epc`) | OGL v3.0 + bearer-token T&Cs | EPC band lookup per address | "EPC data: MHCLG, Open Government Licence v3.0" + comply with new bearer-token terms | ✅ Commercial use OK with token rotation hygiene |
| **ONS National Statistics Postcode Lookup (NSPL)** — *live resolver since 2026-07-25* | OGL v3.0 | **Primary** postcode → borough + lat/lon resolution, served from our own DynamoDB table (`london-flight-map-postcodes`, loaded by `scripts/load_nspl.py`). Also still the input to the DEFRA raster sampler — see the offline table below. | "Postcode resolution: ONS National Statistics Postcode Lookup (Open Government Licence v3.0), with postcodes.io (Open Government Licence v3.0) as fallback" — emitted only once the local tier has actually served a lookup, so the credit is never claimed while the table is empty | ✅ Commercial use OK |
| **postcodes.io** (api.postcodes.io) | OGL v3.0 (data) + MIT (the service) | Postcode → admin_district resolution. **Demoted to fallback 2026-07-25**: used when the local NSPL table misses, is unloaded, or errors. The move was made partly for licence hygiene — routing a customer's 100k-address backfill through a free community service is not fair use, whatever the data licence permits. | "Postcode resolution: postcodes.io (Open Government Licence v3.0)" — still the sole credit whenever the local tier has not served | ✅ Commercial use OK |
| **ONS** (population, crime denominators, deprivation) | OGL v3.0 | Liveability composite + crime score normalisation | OGL boilerplate | ✅ Commercial use OK |
| **Department for Education** (Ofsted school ratings) | OGL v3.0 | Liveability "schools" sub-score | OGL boilerplate | ✅ Commercial use OK |
| **Home Office** (recorded crime statistics) | OGL v3.0 | Liveability "crime" sub-score | OGL boilerplate | ✅ Commercial use OK |
| **TfL Open Data** (`/transport`) | [TfL Open Data licence](https://tfl.gov.uk/info-for/open-data-users/our-open-data) | Liveability "transport" sub-score; nearby stations | "Powered by TfL Open Data. Contains OS data © Crown copyright and database rights..." | ✅ Commercial use OK |

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
| **Curated borough classifications** (`data/borough-extra.json`) | Own editorial work (informed by public sources) | Borough-level air-quality, flood-risk, schools, crime, transport and healthcare ratings + prose notes shown in the detail panel; also drive the air-quality and flood map fills (the map layers colour boroughs from this file, not from live DEFRA/EA/EPA/FEMA services) | UI badges label these "borough-level rating (curated)" since 2026-07-23 | ✅ No third-party licence involved; must never be presented as official agency data |

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
| Consumer site | Footer link: "Methodology v3.1" → links to the methodology document which lists every source with full attribution + licence |
| Methodology document (`METHODOLOGY.md`) | Section 11 enumerates every source + licence reference |
| `/v1/regions` discovery endpoint | Includes `methodologyVersion` + `methodologyUrl` so integrators can audit licensing |

Attribution requirements are **structurally satisfied** — there is no
code path in the API that returns data without the source array.

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
Last reviewed: 2026-07-25 (**ONS NSPL promoted from an offline input to a primary live serving source**, postcodes.io demoted to fallback; response attribution is now conditional on the local tier having actually served, so ONS is never credited while the table is empty. Flagged: the Enterprise city-scale CSV will be a bulk export of NSPL-derived data — allowed under OGL, but the attribution must travel with the file, and that form needs deciding before the first pilot deliverable). — Previous review 2026-05-07 (OpenSky removal end-to-end; AI-powered consumer features removed earlier the same day; loader still running against the full NSPL postcode list).
