# Sky Score Outreach Log

> Track every B2B contact, channel, response, and next action across the outreach pipeline. Update on every reply, every send, and every conversation. Future-self uses this to remember where each conversation stands.

**Outreach pipeline reference:** see [`ROADMAP.md`](./ROADMAP.md) §"Outreach pipeline" for tier definitions and approach principles. Cold-email templates are in the chat history of the productisation session (2026-05-05); recreate per-target.

**Status legend:**
- 🟢 Active conversation
- 🟡 Awaiting reply
- 🟠 Stalled (no reply >14 days)
- 🔴 Closed, not interested
- ⚪ Closed, out of scope / wrong person
- 🔵 Customer (signed)

---

## Tier 1, Property data aggregators

One deal puts Sky Score into thousands of conveyancing searches. Long sales cycles (3-9 months). Approach: LinkedIn → cold email; reference Riskview / Plansearch noise gap.

| Date | Contact | Company | Role | Channel | Status | Notes / Next action |
|---|---|---|---|---|---|---|
| _none yet_ | | | | | | |

---

## Tier 2, Islamic finance providers

Aligned-incentive, smaller teams, mission-driven. Approach: LinkedIn (founder-direct for StrideUp / Nester / Yielders); aligned-values angle.

| Date | Contact | Company | Role | Channel | Status | Notes / Next action |
|---|---|---|---|---|---|---|
| _none yet_ | | | | | | |

**Target list (priority):**
- Al Rayan Bank, Head of Mortgages, Head of Risk
- StrideUp, Founder direct
- Gatehouse Bank, Head of Home Finance
- Nester, Founder
- Yielders, Founder

---

## Tier 3, Direct enterprise / aligned segments

B2R operators, conveyancers, surveyors, public bodies. Approach: warm intros only; leverage existing network.

| Date | Contact | Company | Role | Channel | Status | Notes / Next action |
|---|---|---|---|---|---|---|
| _none yet_ | | | | | | |

---

## Warm-intro requests

LinkedIn 1st/2nd-degree connections at target companies. Higher-leverage than any cold email.

| Date | Asked | Their connection | Target | Status |
|---|---|---|---|---|

---

## Outreach principles (reminder)

- One email per company, not a template blast, customise the first paragraph.
- Cadence: send → 7-day follow-up → 14-day re-angled follow-up → stop. Three touches max.
- Channels: LinkedIn DM ≥ LinkedIn InMail ≥ email.
- Don't attach files, link to live API + Postman collection + methodology.
- No CTAs that require commitment ("20 minutes to learn", not "20 minutes to discuss a pilot").
- One specific detail in each opener that wouldn't apply to any other recipient.
- Each cold email should reference at least two of: live API URL, Postman collection link, public methodology URL, sample response JSON.

## Live artefacts to reference in outreach

- Live API: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score`
- Browser demo: `https://d1oe4ftwutjpf.cloudfront.net/score-demo/index.html`
- API reference (Swagger): `https://d1oe4ftwutjpf.cloudfront.net/score-demo/api-docs.html`
- Status page: `https://d1oe4ftwutjpf.cloudfront.net/score-demo/status.html`
- Methodology: `https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md`
- Public repo: `https://github.com/billkhiz-bit/london-flight-path-map`

---

## Cold-email drafts

Each email is tailored to the recipient. Customise the bracketed sections (`[name]`, `[specific reference]`) before sending. Aim to find the right person via LinkedIn (1st/2nd connections preferred); avoid `info@` aliases.

### Al Rayan Bank, Head of Mortgages / Head of Risk

> **Subject:** Property data API for Sharia-compliant home purchase plans
>
> Hi [Name],
>
> Your home purchase plans give Al Rayan partial ownership of the property, which means underwriting cares about asset quality more than it would for a conventional loan, where recovery is the only concern.
>
> I'm building Sky Score, a noise + livability data API for UK property. It's halal-finance-aware (no riba assumptions in the affordability model) and methodologically aligned with the English Indices of Deprivation. Live and free at the postcode level: [methodology link] · [browser demo].
>
> Would 20 minutes be useful to learn how your underwriting team thinks about property risk? I'm in early conversations and your input would shape what I build next. Happy to share the API key for your team to test.
>
> Best,
> Bilal
>
> [Sky Score consumer site] · [methodology v3.1]

### StrideUp, Founder direct (Sakeeb Zaman or Hassan Daher)

> **Subject:** Sky Score for halal home buyers
>
> Hi [Name],
>
> I built Sky Score (sky-score data API for UK property, quiet, livability, affordability). Same problem you're working on from a different angle: surfacing what listings sites won't show, so buyers (and the platforms financing them) can make informed calls.
>
> The interesting thing for StrideUp specifically: my methodology is openly halal-aware, the affordability calculation doesn't assume conventional mortgages, and the data refreshes match your refresh cycle (Land Registry HPI, DEFRA noise, postcodes.io). Live API: [link]. Methodology: [link].
>
> Would a 20-min call make sense? Curious how StrideUp customers experience property due-diligence today and where the gaps are.
>
> Best,
> Bilal · [Sky Score]

### Gatehouse Bank, Head of Home Finance

> **Subject:** Property due-diligence data layer for Sharia home finance
>
> Hi [Name],
>
> Sharia home finance customers tend to be more deliberate buyers, research-heavy, willing to pay a slight premium for quality. The data they wish they had ahead of a viewing is, ironically, the data UK listings sites have a structural reason not to show (noise impact, school quality, neighbourhood factors).
>
> Sky Score is a data API for that gap. Postcode-level, methodologically open, OGL-aligned. Free tier live now: [link].
>
> Would 20 minutes be useful to discuss whether this fits inside your home finance application or pre-approval flow? I'm happy to share an API key for your team to evaluate.
>
> Best,
> Bilal

### Landmark Information Group, Data Partnerships / Head of Product

> **Subject:** Per-postcode noise and livability layer, fits Riskview pattern
>
> Hi [Name],
>
> I noticed Landmark's Riskview includes flood, contamination, energy, and environmental risk data, but no integrated noise or composite livability layer. Has there been a deliberate decision to leave that to specialist providers, or is it on a future roadmap?
>
> Sky Score is a noise + livability data API positioned exactly there. Per-postcode resolution (DEFRA noise + Haversine flight-path geometry today, full DEFRA raster tier scaffolded), composite 0-10 score with components, OGL-licensed, methodology fully published.
>
> Live: [browser demo] · [methodology] · [Swagger UI]. Sample response for SW11 1AA: <https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score?postcode=SW11+1AA> (with key, happy to share).
>
> Would 20 minutes be useful to explore whether this complements Riskview or sits parallel?
>
> Best,
> Bilal

### TM Group, Data Partnerships

> **Subject:** Adding a noise + livability layer to your conveyancing data products
>
> Hi [Name],
>
> Conveyancing search products integrate flood, contamination, energy, and a few specialist risks. Buyers increasingly ask "what's it like to live there?", and that's a different question than "is the title clean?". Sky Score fills that gap with a postcode-level data layer.
>
> Live and free at postcode resolution: [browser demo]. Methodology open: [link]. Aligned with EU Environmental Noise Directive 2002/49/EC and HM Land Registry HPI.
>
> Worth 20 minutes to learn what your team is hearing from the conveyancing side of the market?
>
> Best,
> Bilal

### Climate X, Founder / Product

> **Subject:** Sky Score and Climate X, possible partnership angle
>
> Hi [Name],
>
> Climate X covers physical climate risk for UK property and finance, flood, heat, subsidence. Sky Score covers an adjacent gap: aviation + road noise, livability composite, halal-finance-aware framing. Different domain, similar shape (B2B, OGL-anchored, postcode resolution).
>
> Two possible angles worth a 20-minute call:
> 1. Bundle (your customers ask for noise too, our customers ask for flood, joint sales motion).
> 2. Cross-reference (Sky Score's `plannedComponents` includes flood; we could integrate Climate X data rather than building from scratch).
>
> Live API + methodology open at [links]. No competitive overlap; mostly complementary.
>
> Would a call make sense?
>
> Best,
> Bilal · [Sky Score]

### Generic conveyancer / B2R operator outreach (template)

> **Subject:** Property quality data for [their product]
>
> Hi [Name],
>
> [One-sentence specific observation about their product or recent launch].
>
> I'm building Sky Score, a property data API focused on the things listings sites underweight (aircraft noise, road noise, livability). Postcode-level for UK, free tier live for evaluation.
>
> Would 20 minutes be useful to show you what an integration could look like? Happy to share an API key for your team.
>
> Best,
> Bilal · [browser demo] · [methodology]

---

## Email-cadence quick reference

- **Send 1**: tailored opener, one specific link, 20-min ask
- **Send 2** (7 days): one-line check-in. "Hi [Name], any thoughts on the below? Happy to send the API key for your team to evaluate., Bilal"
- **Send 3** (14 days, different angle): change the hook. Try an industry observation, a recent event, or a different artefact (Postman link instead of methodology link)
- **Stop after 3 touches.** Move on. Track in the table above.

---

## Public-launch drafts (consumer-side publicity)

These are the public-facing launch drafts. Different audience, different tone from the B2B drafts above. The B2B drafts are commercial (sell into a workflow); these are civic / community / tech-audience (build awareness, drive consumer-site traffic, validate demand).

**Status:**

| Channel | Target | Status | Send / launch date |
|---|---|---|---|
| HACAN East | London City aircraft noise charity | 🟡 draft ready | TBC |
| HACAN West (Heathrow) | Heathrow aircraft noise charity | 🟡 draft ready | TBC |
| Twitter/X thread | General public, property buyers | 🟡 draft ready | TBC, pair with HN launch day |
| Hacker News Show HN | Tech audience, hobbyist devs | 🟡 draft ready | TBC, Tue/Wed morning EST |

### HACAN East, community outreach

> **Subject:** Free postcode-level aircraft noise scoring tool, useful for HACAN East members?
>
> Hi [Name],
>
> I'm a London-based developer and I've built a free public tool that scores any UK postcode for noise exposure (aircraft, road), livability factors (schools, crime, transport, healthcare) and a few other data points. I'm reaching out because HACAN East has been the most credible voice on London City aircraft noise for years, and your members are exactly the people the tool is built for: people deciding where to rent or buy who want to know what they're walking into before they sign.
>
> Some specifics that may matter:
>
> - **Open methodology, not a black box.** Every threshold and weight is anchored to a published source (DEFRA Strategic Noise Mapping, WHO night-noise guidelines, ONS, TfL PTAL). Full document at [methodology link]. Anyone can audit how a score was built.
> - **Free to use.** No sign-up, no paywall, no advertising. The site itself is public. There's a B2B API behind it that I plan to charge for, but the consumer site stays free.
> - **OGL-attributed throughout.** All UK government data is sourced under Open Government Licence v3.0 with attribution.
> - **No commercial agenda toward your membership.** I'm not asking for anything from HACAN East. Just sharing in case you think the tool would be useful for members researching neighbourhoods to move to (or to flag to friends and family who don't know the story behind specific flight paths).
>
> Live tool: [https://d1oe4ftwutjpf.cloudfront.net/](https://d1oe4ftwutjpf.cloudfront.net/), try a postcode you know well; the score should match your intuition.
>
> If it's useful for HACAN East to share with members in a newsletter or blog post, I'd be glad to. If not, no follow-up needed, I'd rather not waste your time.
>
> Best,
> Bilal Khizar

### HACAN West (Heathrow), community outreach

> Same opener as HACAN East, replacing "London City aircraft noise" with "Heathrow aircraft noise" and adding a Heathrow-specific data point:
>
> *"Sky Score uses the actual Heathrow flight-path geometry, Lambourne Stack, Biggin Stack, Ockham Stack, etc, when computing per-postcode quiet scores, not just borough-level Lden bands. So the within-Hounslow variation that members already know about (TW1 Twickenham = quiet, TW6 Heathrow village = severe) is reflected in the score."*

### Twitter/X thread, surprising-data launch

7 tweets, posted as a thread. Best paired with HN launch day for maximum convergent traffic.

**Tweet 1, hook:**

> Listings sites have a structural reason not to tell you about aircraft noise.
>
> Within a single London borough, the difference between two postcodes 6 miles apart can be 17 dB, the difference between a peaceful suburb and the inside of a vacuum cleaner.
>
> So I built a free public tool. 🧵

**Tweet 2, the within-borough variation problem:**

> "Hounslow is noisy" is the kind of pub-knowledge that's both true and useless if you're shopping for a flat there.
>
> TW1 (Twickenham) clocks ~62 dB Lden.
> TW6 (Heathrow village) clocks 75+ dB.
>
> A renter walks into one of those, signs a tenancy, and finds out at 6am.

**Tweet 3, Richmond example:**

> Same story in Richmond upon Thames.
>
> Hampton + Teddington (west): 70+ dB.
> Richmond town centre + Sheen (east): ~62 dB.
>
> Listings sites show you "Richmond" + a price. They don't show you the postcode-level Lden differential. Sky Score does.

**Tweet 4, Wandsworth example:**

> Or Wandsworth, usually bracketed as "moderate" (60-65 dB Lden).
>
> Battersea Heliport area: ~68 dB.
> Tooting Bec: ~55 dB.
>
> Same borough. Same average price band. Different sleep quality. Different long-term cardiovascular outcome (WHO 2018).

**Tweet 5, what it actually does:**

> Sky Score takes any UK postcode and returns:
>
> - 0-10 quiet score (DEFRA noise + flight-path geometry)
> - Affordability (cohort price scaling)
> - Growth (HM Land Registry HPI trend)
> - Liveability (schools / crime / transport / healthcare)
>
> Composite + components. NYC ZIPs work too.

**Tweet 6, methodology:**

> Every threshold is anchored to a published source.
>
> DEFRA Lden bands. WHO night-noise guidelines. Ofsted. ONS crime medians. TfL PTAL. Land Registry HPI.
>
> Full methodology at [link]. Anyone can audit how their score was built. No black box.

**Tweet 7, close:**

> Free, public, no sign-up: [https://d1oe4ftwutjpf.cloudfront.net/](https://d1oe4ftwutjpf.cloudfront.net/)
>
> If you're a renter or buyer, try the postcode you live in or are about to move to. If the score doesn't match your gut, tell me, that's how it gets better.
>
> /end

### Hacker News, Show HN

> **Title:** Show HN: Sky Score, postcode-level noise + livability scoring for UK and NYC property
>
> **Text body:**
>
> Hi HN,
>
> I built Sky Score because the structural information asymmetry in UK property bothered me. Listings sites earn commission when sales close, so they're not incentivised to surface the things that might cause a buyer to walk away, aircraft noise being the obvious one. So I built the data layer they won't.
>
> What it does: take any UK postcode (or NYC ZIP) and return a 0-10 score across four components, Quiet, Affordability, Growth, Liveability, plus the underlying data lineage. Free consumer site, separate B2B API for integrators.
>
> A few things that might be technically interesting:
>
> - **Per-postcode quiet score.** Most "noise score" tools you've seen use borough-level averages. Within a borough, Lden can vary 10-15 dB. Sky Score uses Haversine distances to actual flight-path geometry (Heathrow stacks, JFK approaches) at the postcode centroid for a much finer signal. v3.1 also reads from a DEFRA raster table when populated.
> - **Methodology fully published.** Every threshold and weight points back to a public source: DEFRA Lden bands, WHO night-noise guidelines, Ofsted, ONS crime medians, TfL PTAL, Land Registry HPI. The methodology doc has a worked example for SW11 1AA you can reproduce by hand.
> - **OpenAPI 3.0 + Swagger UI.** Real B2B endpoint with API-key auth. Free tier 1000 req/month. Anyone can poke at the schema.
> - **Halal-finance-aware affordability model.** No riba assumptions in the affordability calculation, because some target customers (Sharia-compliant home-finance providers) operate without conventional mortgages.
>
> Stack: vanilla JS + D3 frontend, AWS Lambda + API Gateway + DynamoDB backend (SAM-deployed), Amazon Bedrock for the AI chat / multi-agent property reports. All inputs OGL v3.0 attributed.
>
> Live: [https://d1oe4ftwutjpf.cloudfront.net/](https://d1oe4ftwutjpf.cloudfront.net/)
> Methodology: [https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md](https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md)
> API docs: [https://d1oe4ftwutjpf.cloudfront.net/score-demo/api-docs.html](https://d1oe4ftwutjpf.cloudfront.net/score-demo/api-docs.html)
>
> Happy to answer technical questions. Strongest feedback I'm looking for: anywhere the score doesn't match your intuition, that's a methodology bug I want to know about.

#### Show HN posting checklist

Before posting, do all of these:

- [ ] Tuesday or Wednesday, between **15:00-17:00 UTC** (10am-noon EST). HN front page is most attainable then; weekends/evenings get drowned by stronger threads.
- [ ] Title under 80 chars. Current draft is 75. ✓
- [ ] No emojis. No "[Show HN]" tag (HN adds it from the URL). Just "Show HN: ".
- [ ] First comment from your own account, posted within 5 minutes of submission, expanding on one technical decision (e.g., "I went vanilla JS instead of React because…").
- [ ] No karma-farming. If it doesn't trend in the first 60 minutes, don't repost, let it die. Reposting burns the only Show HN slot you get.
- [ ] CloudFront caching is warm before posting (hit the URL from 2-3 different IPs ahead of time so the first wave doesn't all get cold edges).
- [ ] Status page (`/score-demo/status.html`) reachable; "live" badge truthful.
- [ ] Twitter thread queued for the same hour to amplify (separate channels, convergent timing).
- [ ] If front-paged: respond to comments within an hour. HN audience punishes silence.
