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
| L5 | **Breathe London (GLA)** | Its sensors fill the gap our data admits (roadside air). **Its API data is OGL v3.0** (terms effective 2025-06-23, read 2026-10-01): commercial use, including a paid API, is allowed with the attribution "Contains Breathe London data licensed under the Open Government License v3.0" linked to breathelondon.org, no implied endorsement, within rate limits. Keys are approved at the GLA's discretion and revocable, so never make a paid feature depend on one without a fallback. **The site now names "the new Breathe London team"**, with delivery partners Global Action Plan, CERC, Airly, Vodafone, Scotswolds and Ricardo - not Imperial | Ask L1 for an introduction first (L1 works with Breathe London and has a node on Warwick Road); failing that, apply for the API key (organisation type "Other"), describing BOTH the free map and the paid API in "intended use". Never ask permission to commercialise: the licence answers it, and asking implies it does not. **THERE ARE TWO BREATHE LONDON APIS (read from both pages 2026-10-06).** The above is breathelondon.org/developers (the GLA's network): "All data made available through the API is licensed under the UK Open Government Licence v3.0". The OTHER is **breathelondon-communities.org/developers**, run by Imperial Projects (IPROJ) for the Communities network (Clarity sensors): free for NON-commercial use only; "with prior written approval from IPROJ, exploit the Information for commercial purposes ... by combining it with other Information, or by including it in User's own product or application"; attribution "Powered by Breathe London Communities" hyperlinked. For THAT one, asking permission is not optional: its terms require it, and the free map is part of a commercial company's product | **Introduced by L1, 2026-10-01** (three team members, by email). **2026-10-06: a team member replied ("an amazing site") with the COMMUNITIES API's link** - the one needing written approval. Next: ask which network carries the Earl's Court nodes (Warwick Road); use the GLA's OGL API where it has them, and ask IPROJ's written approval for anything only the Communities network holds |
| L6 | **Imperial College Environmental Research Group** | Ran Breathe London's second phase; since 2025 the network appears to have a new delivery team (L5), so Imperial is no longer the route in. Still a research contact: draft 3B in the research outreach file | Send 3B as a research contact, not as the Breathe London route | After the L1 call (1 Oct) |
| L7 | **The university hosting the survey** (the form runs on City St George's, University of London's survey platform) | Suggests an academic partner analysing the results | Ask L1 who, rather than guessing; offer the dataset for the analysis | After L1 |
| L8 | **Geovation (Ordnance Survey)** | Clinic held 2026-09-30 (cut short; the lead offered a follow-up video call). Its accelerator is run with OS and HM Land Registry, and a 2026 priority theme is "Risk & Resilience" - property-level environmental risk, close to what Sky Score is - with up to GBP 20k equity-free funding and partner introductions (search summaries; confirm on geovation.uk) | **Follow-up video call HELD 2026-10-02** (OUTREACH_LOG): advice was to narrow to the flight-path niche, keep freemium (it sets us apart from Crystal Roof, which is part of Geovation), keep going with community groups; Bill invited to Geovation's Slack. Still to ask: next intake and what makes a strong PropTech application, partner introductions, OS/HMLR data licences | Now: join the Slack, thank-you note |

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

## Search platforms (row 6): how Sky Score could be on them (added 2026-10-06)

Bill asked whether Sky Score could sit on the platforms conveyancers order searches
through, what that needs and what it costs. Researched 2026-10-06; organisations only.

**Who is who.**
- **Ordering platforms**, where a conveyancer clicks "order", inside their case-management
  software: InfoTrack (which bought STL Group in 2014), TM Group (calls itself the largest
  provider of property searches to conveyancers), Search Acumen, and smaller ones (PSG,
  Searchflow). A supplier has ONE account with each, invoiced monthly; the platform bills
  the conveyancers.
- **Report makers** whose products those platforms sell: Groundsure and Landmark
  (environmental reports, close to standard on every purchase).
- **The rules**: the Search Code of Practice (published by CoPSO; register kept by the
  Property Codes Compliance Board). Lenders increasingly require searches from Code
  subscribers.

**Yes, Sky Score could be on them, by two routes.**
- **B, lead with this: our data inside an existing environmental report**, under an API
  licence. The section is in every report, so there is no take-up problem, at a small fee
  per address. What we add that the open DEFRA maps do not: the published flight routes
  near the address, the aircraft's height there, an estimate where DEFRA has no reading,
  and the 2021 understatement. Read their sample reports first: DEFRA's noise maps are
  open data, so they may already show noise bands, and the pitch is the part they lack.
- **A: our report as a line in a platform's catalogue**, paid wholesale per report.
  Selling it as a search probably means subscribing to the Search Code ourselves.

**Volume, measured** (see "Facts safe to quote"): 779,131 standard home sales in England
and Wales in 2025; we cover 34.6% of sales, about 270,000 to 320,000 a year. But only
**14,532 (1.87%)** of 2025's sales in the cities we cover were at postcodes on DEFRA's
aircraft-noise map: an OPTIONAL aircraft report has a small natural audience, which is
why route B leads.

**What it needs, in order, and what it costs** (estimates marked; quotes before
committing):

| # | What | Why | Cost | Who |
|---|---|---|---|---|
| 1 | Written confirmation from NATS's aeronautical information service that facts derived from the UK AIP may be resold inside a paid product | A platform's lawyers will ask. The AIP terms (5.4) acknowledge commercial data services built on it, "with or without charge"; NATS's corporate site terms leave doubt (LICENSING.md) | Free | Bill sends; Claude drafts |
| 2 | ~~Professional indemnity insurance~~ **NOT BOUGHT (Bill, 2026-10-06): no conventional insurance, for the same reason as no conventional lenders.** See "Without conventional insurance" below | Conveyancers rely on these reports; Groundsure's carry GBP 10M | GBP 0 (was estimated GBP 300 to 1,500 a year) | - |
| 3 | Cyber Essentials | Platforms' and councils' security questionnaires | About GBP 384 a year (VAT paid in full: not VAT-registered) | Bill |
| 4 | England-wide coverage | At 34.6% of sales, two orders in three would say "not covered" | GBP 0 in data (every English source is national and open); build time; AWS a few pounds a month | Claude |
| 5 | The rename: the register check, domains, an attorney's opinion, a UK filing in classes 9 and 42 | Gate for cold outreach, and a platform contracts with a brand | About GBP 30 + GBP 150 to 300 + GBP 265 (UK IPO since April 2026: GBP 205 + GBP 60 a class) | Bill and an attorney |
| 6 | The ICO fee | Legal obligation, open since August | GBP 52 a year | Bill |
| 7 | A data-supply or reseller contract reviewed by a solicitor | Liability cap, warranties, licences passed through | **Rough estimate GBP 500 to 1,500**, one-off; ask for a fixed fee | Bill |
| 8 | Search Code subscription (route A only) | Lenders require Code-compliant searches | Not published in what was found; ask the PCCB | Bill |
| 9 | Evidence: 5 to 10 reports sold by hand to buying agents and surveyors | Proof of demand and a quote or two make the pitch | GBP 0 | Bill, with Claude |
| 10 | A warm introduction: Geovation (run with OS and HM Land Registry) offered partner introductions, and OS lists InfoTrack and TM Group as OS business partners | A warm first contact beats a cold one | GBP 0 | Bill |

**Total without insurance: roughly GBP 1,400 to 2,600 in the first year, then about
GBP 450 a year** (ICO fee, Cyber Essentials, domains). Most of it is needed whatever the
channel: Cyber Essentials for councils too, the rename and the ICO fee regardless.

**Without conventional insurance (Bill, 2026-10-06).** The options, in the order they
matter:
1. **Be a data SUPPLIER, not a search seller: route B and the API become the plan.** The
   report maker (Groundsure, Landmark) issues the report under its own Search Code
   membership and its own cover; our contract is a data licence with a liability cap
   (typically the fees paid in the last 12 months), a warranty limited to faithful
   reproduction of the named official sources, and no reliance by anyone but the report
   maker. Some partners will still ask for cover: a negotiation, not a given. **Route A
   (our report sold as a search) is probably closed without cover**: the platforms work to
   the Search Code (TM Group says it subscribes), and the GeoSmart precedent below almost
   certainly held cover.
2. **Takaful**, the Sharia-compliant alternative: thin in the UK (an industry article calls
   it "nothing of significance"), with specialist brokers (GNL Insurance) and a
   Sharia-compliant Lloyd's syndicate (Creechurch, Syndicate 3786). An enquiry is free;
   whether a product meets Bill's standard is a question for his scholar.
3. **Self-cover**: Cubitt33 Ltd holds a reserve equal to its liability cap; the limited
   company and capped contracts bound what a claim can reach.
4. **Design that keeps the risk low**, most of it already live: information not advice,
   "not a search or a survey", every figure with its source and date, the free report on
   screen only and for personal use, warranty disclaimers in the terms. A solicitor adds a
   clear liability cap (item 7).
5. **Direct buyers (councils, firms)**: "no professional indemnity cover held; liability
   capped at the contract value". Some will accept for small purchases; ask early.

**Precedent for route A**: TM Group added GeoSmart's drainage report (SuDSmart) to its
ordering system, tmConvey, which offers "over 400 property searches". Catalogues, opened
2026-10-06: InfoTrack `infotrack.co.uk/solutions/conveyancing/property-searches/`, TM Group
`tmgroup.co.uk/residential/searches-property-data/`.

**The channel wall (ROADMAP "Constraints").** The free per-address report on the site
could look like undercutting a platform selling the same report. Expect a reseller to ask.
The on-screen-only, personal-use design helps; decide before signing whether the free
version stays as it is.

**Is it the right path?** (Written before the no-insurance ruling, which narrows it to
route B and the API.) Yes, as the main business channel for per-address reports, and
inside the constraints (aggregators and conveyancers, no riba issue). Not first in time:
it is slow (months of due diligence), wholesale margins are thin, and a platform could
build basic noise from the same open DEFRA maps, so the edge has to be the flight routes,
the heights and the checks. **Order: prove demand by hand (9); do the prerequisites
(1 to 7) as they come due; then the Geovation introduction (10), with route B as the
pitch.** The tracks that need no rename (journalists, researchers, the twice-yearly
report) build the "as used by" credibility in the meantime.

Sources, read 2026-10-06: ordnancesurvey.co.uk business partner pages for InfoTrack and
TM Group; todaysconveyancer.co.uk (InfoTrack's acquisition of STL); legalfutures.co.uk
(Search Acumen; the PCCB); gov.uk (IPO fees from April 2026); getindemnity.co.uk and
simplybusiness.co.uk (PI premium ranges).

## Facts safe to quote

Each is measured and in the repo. Re-check the source before quoting if the date is old.

| Fact | Source in repo | As of |
|---|---|---|
| Heathrow 55 dB Lden contour: DEFRA 2021 **75.6 km2** vs CAA 2024 **148.4 km2** (ERCD 2501 Table 12), about half | `scripts/measure_covid_understatement.py --check` (blocking) | 2026-09-26 |
| 62% of DEFRA's mapped Heathrow area (124.2 of 199.8 km2) is below 55 dB | ROADMAP, Option C | 2026-09-26 |
| Site covers 11 city regions, 91 boroughs; the API covers 14 cities | CLAUDE.md "Project" | 2026-09-27 |
| Every input is official public data. DEFRA, the Environment Agency, ONS and HM Land Registry publish under the Open Government Licence; **the UK flight routes come from the UK AIP (NATS), which is public but NOT openly licensed** - never say "all open data" (corrected 2026-10-06; it read "every input is open government data") | LICENSING.md | 2026-10-06 |
| Crime checked against ONS Table C4; prices against HM Land Registry HPI; flood against the EA's own map service, before every release | blocking preflight stages | current |
| Neighbourhood prices use HM Land Registry Category A sales only, as HMLR's own statistics do | `build_city_neighbourhoods.py --check` | 2026-09-01 |
| Aircraft-noise estimate error vs DEFRA: **MAE 1.03** on 35,441 London postcodes near airports (1.879 before v5.3, 1.32 before v5.5), bias -0.29, reading louder than DEFRA (pessimistic). Near airports only - never a global accuracy figure. Live since 2026-10-01 (v5.5) | `scripts/check_quiet_estimate_error.py` (re-run) | 2026-10-01 |
| v5.5 makes the airport term follow the runway instead of a circle: held-out error against DEFRA falls by a fifth on its noise strip (1.43 -> 1.14) and by over a third in the quieter ground beside it (1.23 -> 0.77), in every city, and **no city reads quieter than DEFRA measured** (that is a rule of the fit, checked city by city). Live since 2026-10-01 | `scripts/fit_airport_shape.py` (about 20 s) | 2026-10-01 |
| **779,131** standard (Category A) home sales in England and Wales in 2025; **14,532 (1.87%)** were at postcodes on DEFRA's aircraft-noise map in the cities we cover, **2,488** of them at about 55 dB Lden or louder. A FLOOR: the map is 2021, the surroundings of Gatwick, Stansted and Luton are outside it, and lettings are not counted | `scripts/measure_aircraft_market.py` (needs the gitignored `data/pp-2025.csv`, downloaded 2026-08-09) | 2026-10-02 |
| Crystal Roof's consumer prices: GBP 7.99 a week, 12.99 a month, 29.99 for three months, with postcode-level data limited on its free plan | its pricing page, read 2026-10-02 (NOT in the repo: re-read before quoting) | 2026-10-02 |
| Government backed a third Heathrow runway (29 Jan 2025), approved Luton's expansion (Apr 2025) and Gatwick's northern runway (21 Sep 2025), and is redesigning UK airspace through a new Airspace Design Service (announced June 2025) | gov.uk and press, searched 2026-10-02 (NOT in the repo: re-read before quoting) | 2026-10-02 |
| **Hounslow, its five AQAP focus areas** (one postcode on each named road: W4 1RG, W4 2DY, TW5 0TA, TW5 0AA, TW3 1QJ): every point above the WHO guideline for both NO2 (17.8-19.5 vs 10 ug/m3) and PM2.5 (8.6-9.1 vs 5), DEFRA PCM 2024; road noise **67.7-77.8 dB Lden** against WHO's 53; **Vicarage Farm Rd (TW5 0AA) is 0.1 km from Heathrow's 27R approach line, landing aircraft at about 600 ft**, DEFRA aircraft noise 64.7 dB Lden there | `node scripts/area_summary.mjs --area "Hounslow" --aircraft --point ...` (live `/v1/environment` + the AIP record); the sheet is on Bill's Desktop | 2026-10-08 |
| Hounslow: **63%** of its postcodes above the WHO road-noise guideline; **13th-highest NO2** of London's 33 boroughs | `data/borough-extra.json`, via the same script | 2026-10-08 |
| **Mayor's Air Quality Fund Round 5 is open to London boroughs: GBP 6m, closing 5pm Friday 13 November 2026.** Boroughs apply, not community groups | london.gov.uk MAQF page, read 2026-10-08 (NOT in the repo: re-read before quoting) | 2026-10-08 |
| **DEFRA's Air Quality Grant has had no round since 2023-24**, whose ~GBP 6m was withheld after councils had been told they had won (LocalGov, 16 Apr 2024); the grant's own page says "nearly GBP 92 million" since 1997 | gov.uk Air Quality Grant collection page + LocalGov, read 2026-10-08 (NOT in the repo) | 2026-10-08 |
| Aircraft noise cannot be a statutory nuisance (Environmental Protection Act 1990 s.79(6)), and boroughs do not write noise action plans (DEFRA and airport operators do): a council's aircraft-noise lever is planning and advocacy, not enforcement | legislation.gov.uk, read 2026-10-08 | 2026-10-08 |

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
> I built Sky Score (skyscore.co.uk), a free map joining official public data on
> noise, air, flood, crime, schools and prices for [N] city regions. I can share
> the borough-level table and the method behind the finding. The government
> datasets are under the Open Government Licence; the flight routes come from the
> UK AIP (NATS), which is public but not openly licensed.
>
> [Name], Cubitt33 Ltd

### Public health and researchers (2, 3)

> Subject: Joined official data on noise, air and flood by area - free for research
>
> Sky Score (skyscore.co.uk) joins DEFRA noise and air-quality maps, Environment
> Agency flood risk and ONS, DfE and HM Land Registry data on one geography for
> [N] UK city regions, with the method published, and the crime, price and flood
> figures checked against their publishers before every release.
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
