# Outreach targets

Who would value Sky Score's data, especially in **aggregated** form (borough and
district scores, rankings, change over time, and the joined dataset itself), and
how to write to each. Drafted 2026-09-28. Use this to start any outreach email;
log every send and reply in `OUTREACH_LOG.md`.

**This repository is public.** Organisations only, never named individuals or
contact details. Look contacts up at the time of sending; do not guess addresses.

## Before any email goes out

1. **ICO fee paid** (Cubitt33 Ltd, GBP 52). Open since August.
2. **DKIM passes** on the sending domain: send a test to a personal address and
   check the headers. A first email in spam is the most expensive one.
3. **Rename gate.** The rename decision says COLD commercial outreach waits for the
   new name. Data publishers, journalists, researchers and public-health bodies
   are about the data, not the brand, and can go now. Rows marked "after rename"
   wait.
4. **Every number checked** against the "Facts safe to quote" list below. If a
   figure is not there, measure it before sending it.

## The shortlist

| # | Who | What they would do with it | When |
|---|---|---|---|
| 1 | **Data journalists** (BBC Shared Data Unit, FT, Guardian, Reach regional titles) | Rankings and findings are stories: quietest affordable boroughs, where the 2021 noise map is most out of date | Now |
| 2 | **Public health** (UKHSA noise and air teams, council Directors of Public Health, Asthma + Lung UK) | Noise and air exposure by area as a health-inequalities input they currently assemble by hand | Now |
| 3 | **Academic groups** (UCL CASA, Imperial Environmental Research Group, urban-analytics centres) | A joined, documented dataset saves months; a validation paper is worth more than any advert | Now |
| 4 | **Data publishers** (DEFRA noise team, ONS, Environment Agency, HM Land Registry, London Datastore) | Reuse case studies; DEFRA gets the measured 2021 gap | Now (drafts: `OneDrive/Desktop/outreach-data-publishers-2026-09-28.txt`) |
| 5 | **Mortgage lenders' climate-risk teams**, Islamic lenders first (StrideUp, Al Rayan, Gatehouse) | Portfolio-level flood and environmental exposure; riba-free affordability angle | After rename |
| 6 | **Property data aggregators / search providers** (Landmark, TM Group, Search Acumen) | Resell the joined layer inside conveyancing and environmental searches | After rename |
| 7 | **Real-estate ESG and research** (Savills, Knight Frank, JLL, CBRE research; build-to-rent investors) | Noise and air as ESG factors in site selection and reporting | After rename |
| 8 | **Councils** (environmental health / noise, planning, housing) | Noise-complaint triage, site context | After rename |
| 9 | **Housing associations** (asset / sustainability teams) | Site choice; advising tenants | After rename |
| 10 | **Airport community bodies** (Heathrow Community Engagement Board, noise forums) | Neutral data for residents' questions | After rename, carefully |

**Start with 1-4.** No rename, no procurement, and each produces something public
(an article, a citation, a listing) that makes 5-10 easier: "as used by" is the
credibility a small supplier lacks.

**Avoid for now: campaign groups** (e.g. anti-expansion groups). A natural audience,
but being seen on one side of Heathrow expansion costs the neutrality that councils,
lenders and journalists are buying.

**Councils cannot usually endorse or buy from a small supplier without
procurement.** Never pitch; offer a free tool and ask for corrections.

## Facts safe to quote

Each is measured and in the repo. Re-check the source before quoting if the date is old.

| Fact | Source in repo | As of |
|---|---|---|
| Heathrow 55 dB Lden contour: DEFRA 2021 **75.6 km2** vs CAA 2024 **148.4 km2** (ERCD 2501 Table 12), about half | `scripts/measure_covid_understatement.py --check` (blocking) | 2026-09-26 |
| 62% of DEFRA's mapped Heathrow area (124.2 of 199.8 km2) is below 55 dB | ROADMAP, Option C | 2026-09-26 |
| Site covers 11 city regions, 91 boroughs; the API covers 14 cities | CLAUDE.md "Project" | 2026-09-27 |
| Every input is open government data under the Open Government Licence | LICENSING.md | current |
| Crime checked against ONS Table C4; prices against HM Land Registry HPI; flood against the EA's own map service, before every release | blocking preflight stages | current |
| Neighbourhood prices use HM Land Registry Category A sales only, as HMLR's own statistics do | `build_city_neighbourhoods.py --check` | 2026-09-01 |
| Aircraft-noise estimate error vs DEFRA: MAE 1.879 on 35,352 London postcodes near airports, reading louder than DEFRA (pessimistic) | `scripts/check_quiet_estimate_error.py` | 2026-09-02 |

## Never say

- **"How often planes fly over."** Sky Score scores LOUDNESS (Lden, an average).
  Frequency is N65, which is not measured.
- **Any accuracy figure as national.** The 1.879 error describes postcodes near
  airports, the only places DEFRA published a comparison.
- **"AI-powered."** The product is data-first; the consumer site uses no AI.
- **That anyone uses the API.** As of 2026-09-28 no outside developer had.

## Templates

Replace everything in [brackets]. Keep them short: one finding, one ask.

### Journalists (1)

> Subject: [one finding, e.g. "The official aircraft noise map shows Heathrow at half its size"]
>
> [One-sentence finding with the number.] It comes from comparing DEFRA's official
> 2021 noise map, drawn during lockdown, with the CAA's 2024 figures.
>
> I built Sky Score (skyscore.co.uk), a free map joining open government data on
> noise, air, flood, crime, schools and prices for [N] city regions. I can share
> the borough-level table and the method behind the finding. Everything is open
> data under the Open Government Licence.
>
> [Name], Cubitt33 Ltd

### Public health and researchers (2, 3)

> Subject: Joined open data on noise, air and flood by area - free for research
>
> Sky Score (skyscore.co.uk) joins DEFRA noise and air-quality maps, Environment
> Agency flood risk and ONS, DfE and HM Land Registry data on one geography for
> [N] UK city regions, with the method published and each figure checked against
> its source before release.
>
> If it would help your work on [their topic], I am happy to share the
> borough-level dataset and methodology, and I would welcome an independent check
> of it.
>
> [Name], Cubitt33 Ltd

### Data publishers (4)

Full drafts in `OneDrive/Desktop/outreach-data-publishers-2026-09-28.txt`.

### Commercial (5-10, after rename)

Use the pilot pack (`memory/project-pilot-outreach-pack.md`, `OUTREACH_LOG.md`
send gates). Lead with one measured fact relevant to their risk, not the product.

## What would make every row easier

**A downloadable dataset**: one CSV of borough scores and components with sources
and licence on a `/data` page, so a journalist or researcher can use it in five
minutes without the API. About a day of work; not built yet.
