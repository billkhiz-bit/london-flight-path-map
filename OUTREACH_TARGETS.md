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

## Local and London air-quality contacts (added 2026-09-29)

Found through a residents' group message about an air-quality survey in Earls Court,
where Bill lives. Being a resident is the introduction, so these go **now**: they are
about the data, not the brand. Order matters - each one's reply makes the next easier.

| # | Who | Why they would care | How | When |
|---|---|---|---|---|
| L1 | **Earls Court Society, Environmental Group** | Preparing a Mayor's Air Quality Fund bid with the council and Breathe London; the one-pager gives them the official baseline | Resident email + one-page summary (drafted, `OneDrive/Desktop/earls-court-society-email-2026-09-29.txt`) | Now |
| L2 | **The residents' association network that forwarded it** | Their members asked to answer the survey; the same summary answers "how bad is it here" | Only after L1 replies, and only if L1 is happy for it to be shared | After L1 |
| L3 | **Neighbouring amenity societies** (Kensington, Chelsea, and Hammersmith and Fulham groups near Earls Court) | Same question for their own streets; a per-area summary is an hour's work each | Offer a free summary for their area | After L1 |
| L4 | **RBKC environment / air-quality team** | Already working with L1 | Through L1, never cold; offer data and ask for corrections (councils: no pitch) | Via L1 |
| L5 | **Breathe London (GLA)** | Its sensors fill the gap our data admits (roadside air) | Ask L1 for an introduction first (L1 works with Breathe London and has a node on Warwick Road); failing that, apply for the API key, where the "intended use" answer is the introduction | After the L1 call (1 Oct) |
| L6 | **Imperial College Environmental Research Group** | Involved in Breathe London; already draft 3B in the research outreach file | Send 3B, mentioning Breathe London (and the L1 introduction, if there is one) | After the L1 call (1 Oct) |
| L7 | **The university hosting the survey** (the form runs on City St George's, University of London's survey platform) | Suggests an academic partner analysing the results | Ask L1 who, rather than guessing; offer the dataset for the analysis | After L1 |
| L8 | **Geovation (Ordnance Survey)** | Clinic held 2026-09-30 (cut short; the lead offered a follow-up video call). Its accelerator is run with OS and HM Land Registry, and a 2026 priority theme is "Risk & Resilience" - property-level environmental risk, close to what Sky Score is - with up to GBP 20k equity-free funding and partner introductions (search summaries; confirm on geovation.uk) | Video call: next intake and what makes a strong PropTech application, partner introductions, OS/HMLR data licences. Draft in `OneDrive/Desktop/outreach-drafts-2026-09-30.txt` | Now (warm) |

**Clean-air campaign groups:** usable, carefully. Unlike Heathrow expansion, "cleaner air"
has no opposing side, so neutrality is not at stake the same way - but keep to supplying
data, never co-signing a campaign position.

**The Earls Court regeneration developer** is a potential COMMERCIAL contact (site
context for a large development) and so waits for the rename like rows 5-10.

## Community plan (agreed 2026-09-29)

**Goal: be the trusted local source for "what is it like to live here", so B2B
conversations can say "as used by".** A residents' group citing Sky Score in a
funding bid is worth more to a lender than any advert.

Three strands feeding one loop:

1. **Local groups (the engine).** Free one-page area summaries for residents'
   associations, amenity societies and neighbourhood forums - the evidence they
   need for bids, objections and council meetings. `scripts/area_summary.mjs`
   generates one from a postcode list in about a minute.
2. **Findings (the megaphone).** One real finding a month on LinkedIn under
   Bill's own name (survives the rename); helpful answers on r/HousingUK and
   city subreddits, linking only when it adds something (about 90/10); the
   occasional data chart. A LinkedIn newsletter grows out of the posts. A site
   email newsletter waits: it needs its own PECR consent, a privacy.html change,
   unsubscribe handling, the ICO fee and SPF/DMARC. The score-update list is
   NOT a newsletter list.
3. **Listening (the retention).** "Spotted something wrong? Tell us" on every
   result panel (since 2026-09-29); "you asked, we fixed" follow-ups with the
   reporter's permission; a hand-kept list of 10-20 **insiders** emailed
   personally before each monthly data update.

**Start narrow: local groups, in London, from Earls Court** (rows L1-L7 above).
Bill is a resident, the chain already exists, and one group actually USING a
summary is the first case study. Do not spread across cities until one works.

**Weekly rhythm, time-boxed at about 3 hours:** one group offer or follow-up;
three or four helpful Reddit answers; one LinkedIn post; five minutes on Friday
updating the tracker.

**End-of-October measures:** 5 groups offered a summary; 2 used or forwarded
it; **1 permission to say "as used by"**; 10 insiders; community referrals
trending up in GoatCounter. If none of five used it, change the offer before
doing more of it.

**Not now:** a forum (empty forums read as abandoned, and a user-to-user
service brings Online Safety Act duties), Discord/Slack, giveaways, paid ads.

The working tracker is Bill's spreadsheet (Desktop, not the repo, because it
holds contact details): Contacts, Community and Insiders tabs.

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
| Aircraft-noise estimate error vs DEFRA: **MAE 1.32** on 35,441 London postcodes near airports (1.879 before v5.3), bias -0.15, reading slightly louder than DEFRA (pessimistic). Near airports only - never a global accuracy figure | `scripts/check_quiet_estimate_error.py` (re-run) | 2026-09-30 |
| A runway-shaped airport term would cut that error by roughly a quarter to a third on DEFRA's noise strip and by about 40% in the quieter ground around it. **Measured, NOT live**: say "isn't live yet". **Quote the fractions, not the decimals**: the exact figures depend on which (k, w) pair ships, which is still open (held-out test half: 1.43 -> 1.11 / 1.23 -> 0.72 at k = 4, w = 0.45; 1.43 -> 0.98 / 1.23 -> 0.71 at k = 6, w = 0.50) | `scripts/fit_airport_shape.py` (re-runs it, about 20 s) | 2026-10-01 |

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

**The downloadable dataset is LIVE since 2026-09-28**: `https://skyscore.co.uk/open-data/`
(one CSV, 97 UK areas, every column documented and sourced). Link it in every
journalist, researcher and public-health email. Licence: CC BY-NC 4.0 plus an
explicit grant for journalism and academic research; bulk resale or product use
needs written permission (Bill's call: no competitor reselling). Regenerated by
`scripts/build_area_pages.py --write` with the area pages after every data roll.
