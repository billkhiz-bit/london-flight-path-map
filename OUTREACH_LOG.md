# Sky Score Outreach Log

> Track every B2B contact, channel, response, and next action across the outreach pipeline. Update on every reply, every send, and every conversation. Future-self uses this to remember where each conversation stands.

**Outreach pipeline reference:** see [`ROADMAP.md`](./ROADMAP.md) §"Outreach pipeline" for tier definitions and approach principles. Cold-email templates are in the chat history of the productisation session (2026-05-05); recreate per-target.

**Status legend:**
- 🟢 Active conversation
- 🟡 Awaiting reply
- 🟠 Stalled (no reply >14 days)
- 🔴 Closed — not interested
- ⚪ Closed — out of scope / wrong person
- 🔵 Customer (signed)

---

## Tier 1 — Property data aggregators

One deal puts Sky Score into thousands of conveyancing searches. Long sales cycles (3–9 months). Approach: LinkedIn → cold email; reference Riskview / Plansearch noise gap.

| Date | Contact | Company | Role | Channel | Status | Notes / Next action |
|---|---|---|---|---|---|---|
| _none yet_ |   |   |   |   |   |   |

---

## Tier 2 — Islamic finance providers

Aligned-incentive, smaller teams, mission-driven. Approach: LinkedIn (founder-direct for StrideUp / Nester / Yielders); aligned-values angle.

| Date | Contact | Company | Role | Channel | Status | Notes / Next action |
|---|---|---|---|---|---|---|
| _none yet_ |   |   |   |   |   |   |

**Target list (priority):**
- Al Rayan Bank — Head of Mortgages, Head of Risk
- StrideUp — Founder direct
- Gatehouse Bank — Head of Home Finance
- Nester — Founder
- Yielders — Founder

---

## Tier 3 — Direct enterprise / aligned segments

B2R operators, conveyancers, surveyors, public bodies. Approach: warm intros only; leverage existing network.

| Date | Contact | Company | Role | Channel | Status | Notes / Next action |
|---|---|---|---|---|---|---|
| _none yet_ |   |   |   |   |   |   |

---

## Warm-intro requests

LinkedIn 1st/2nd-degree connections at target companies. Higher-leverage than any cold email.

| Date | Asked | Their connection | Target | Status |
|---|---|---|---|---|

---

## Outreach principles (reminder)

- One email per company, not a template blast — customise the first paragraph.
- Cadence: send → 7-day follow-up → 14-day re-angled follow-up → stop. Three touches max.
- Channels: LinkedIn DM ≥ LinkedIn InMail ≥ email.
- Don't attach files — link to live API + Postman collection + methodology.
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

### Al Rayan Bank — Head of Mortgages / Head of Risk

> **Subject:** Property data API for Sharia-compliant home purchase plans
>
> Hi [Name],
>
> Your home purchase plans give Al Rayan partial ownership of the property — which means underwriting cares about asset quality more than it would for a conventional loan, where recovery is the only concern.
>
> I'm building Sky Score, a noise + livability data API for UK property. It's halal-finance-aware (no riba assumptions in the affordability model) and methodologically aligned with the English Indices of Deprivation. Live and free at the postcode level: [methodology link] · [browser demo].
>
> Would 20 minutes be useful to learn how your underwriting team thinks about property risk? I'm in early conversations and your input would shape what I build next. Happy to share the API key for your team to test.
>
> Best,
> Bilal
>
> [Sky Score consumer site] · [methodology v3.1]

### StrideUp — Founder direct (Sakeeb Zaman or Hassan Daher)

> **Subject:** Sky Score for halal home buyers
>
> Hi [Name],
>
> I built Sky Score (sky-score data API for UK property — quiet, livability, affordability). Same problem you're working on from a different angle: surfacing what listings sites won't show, so buyers (and the platforms financing them) can make informed calls.
>
> The interesting thing for StrideUp specifically: my methodology is openly halal-aware, the affordability calculation doesn't assume conventional mortgages, and the data refreshes match your refresh cycle (Land Registry HPI, DEFRA noise, postcodes.io). Live API: [link]. Methodology: [link].
>
> Would a 20-min call make sense? Curious how StrideUp customers experience property due-diligence today and where the gaps are.
>
> Best,
> Bilal · [Sky Score]

### Gatehouse Bank — Head of Home Finance

> **Subject:** Property due-diligence data layer for Sharia home finance
>
> Hi [Name],
>
> Sharia home finance customers tend to be more deliberate buyers — research-heavy, willing to pay a slight premium for quality. The data they wish they had ahead of a viewing is, ironically, the data UK listings sites have a structural reason not to show (noise impact, school quality, neighbourhood factors).
>
> Sky Score is a data API for that gap. Postcode-level, methodologically open, OGL-aligned. Free tier live now: [link].
>
> Would 20 minutes be useful to discuss whether this fits inside your home finance application or pre-approval flow? I'm happy to share an API key for your team to evaluate.
>
> Best,
> Bilal

### Landmark Information Group — Data Partnerships / Head of Product

> **Subject:** Per-postcode noise and livability layer — fits Riskview pattern
>
> Hi [Name],
>
> I noticed Landmark's Riskview includes flood, contamination, energy, and environmental risk data — but no integrated noise or composite livability layer. Has there been a deliberate decision to leave that to specialist providers, or is it on a future roadmap?
>
> Sky Score is a noise + livability data API positioned exactly there. Per-postcode resolution (DEFRA noise + Haversine flight-path geometry today, full DEFRA raster tier scaffolded), composite 0-10 score with components, OGL-licensed, methodology fully published.
>
> Live: [browser demo] · [methodology] · [Swagger UI]. Sample response for SW11 1AA: <https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score?postcode=SW11+1AA> (with key — happy to share).
>
> Would 20 minutes be useful to explore whether this complements Riskview or sits parallel?
>
> Best,
> Bilal

### TM Group — Data Partnerships

> **Subject:** Adding a noise + livability layer to your conveyancing data products
>
> Hi [Name],
>
> Conveyancing search products integrate flood, contamination, energy, and a few specialist risks. Buyers increasingly ask "what's it like to live there?" — and that's a different question than "is the title clean?". Sky Score fills that gap with a postcode-level data layer.
>
> Live and free at postcode resolution: [browser demo]. Methodology open: [link]. Aligned with EU Environmental Noise Directive 2002/49/EC and HM Land Registry HPI.
>
> Worth 20 minutes to learn what your team is hearing from the conveyancing side of the market?
>
> Best,
> Bilal

### Climate X — Founder / Product

> **Subject:** Sky Score and Climate X — possible partnership angle
>
> Hi [Name],
>
> Climate X covers physical climate risk for UK property and finance — flood, heat, subsidence. Sky Score covers an adjacent gap: aviation + road noise, livability composite, halal-finance-aware framing. Different domain, similar shape (B2B, OGL-anchored, postcode resolution).
>
> Two possible angles worth a 20-minute call:
> 1. Bundle (your customers ask for noise too, our customers ask for flood — joint sales motion).
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
- **Send 2** (7 days): one-line check-in. "Hi [Name], any thoughts on the below? Happy to send the API key for your team to evaluate. — Bilal"
- **Send 3** (14 days, different angle): change the hook. Try an industry observation, a recent event, or a different artefact (Postman link instead of methodology link)
- **Stop after 3 touches.** Move on. Track in the table above.
