# Sky Score outreach drafts

Templates for the outreach pipeline in `ROADMAP.md` §"Outreach pipeline". Adapt per target. Log every send in `OUTREACH_LOG.md`.

**Cadence (per ROADMAP):**
- 2 warm-intro asks per week to LinkedIn 1st/2nd connections at Tier-1/2 targets — first batch due **2026-05-08**.
- 2 cold emails per week using the templates below — starting week of **2026-05-12**.
- Chase Emergent Ventures if no reply by **2026-05-12** (form promised "within ~1 week").

---

## Warm-intro ask (LinkedIn DM)

Use for 1st-degree connections who work at, or recently worked at, a Tier-1/2 target. Goal: a 2-line forwarded intro email, not a meeting.

> Hi [first name] — hope you're well.
>
> I'm building **Sky Score** (skyscore.co.uk), a UK property noise + livability data API. Free consumer site + B2B endpoint for property aggregators and Sharia-compliant home-finance providers. Methodology fully published, every threshold anchored to DEFRA / Ofsted / ONS.
>
> I noticed you're connected to [name] at [Company]. Would you mind a quick forwarded intro? Happy to draft the intro email — you literally just paste and forward. If they're not the right person, no worries; if you'd rather not, also no worries.
>
> Sky Score in 30 sec: [https://skyscore.co.uk/score-demo/](https://skyscore.co.uk/score-demo/) — try `N1 7SX` or `TW3 4DX`.
>
> Thanks,
> Bilal

**Forward-ready intro email** (paste this into the warm-intro reply if they say yes):

> Hi [target name] — meet Bilal Khizar, an independent UK developer who's built Sky Score, a property noise + livability data API. I think his work is directly relevant to [Company]'s [aggregator stack / underwriting workflow] and worth a 15-minute look. I'll let you both take it from here.
>
> Bilal — [target] is [role] at [Company].

---

## Tier 1 cold email — aggregators (Landmark, TM Group, OneSearch Direct)

Use when no warm intro is available. Subject is everything.

**Subject:** Noise + livability data for [Company]'s [conveyancing / underwriting] reports

> Hi [first name],
>
> I run **Sky Score** (skyscore.co.uk), a UK property noise + livability data API. We score any UK postcode 0-10 across four components — quiet, affordability, growth, liveability — anchored to DEFRA Strategic Noise Mapping, Ofsted, ONS, Land Registry HPI. Methodology published; OpenAPI 3.0 spec live.
>
> [Company]'s conveyancing search reports include flood, planning, environmental — but as far as I can tell, no honest aircraft / road noise component (the kind that materially affects a buyer's quality of life and rarely shows up before exchange). Sky Score plugs that gap as a single `/v1/score` call per property.
>
> Concrete next step that costs you nothing: try the free demo with one of your live conveyancing search postcodes — `https://skyscore.co.uk/score-demo/index.html` — and tell me whether the output would have been useful.
>
> If yes, I'd love a 20-minute call to discuss integration patterns and pricing for [Company]'s volume.
>
> Sky Score is independent, sole-developer, 1,000 req/month free tier, paid tiers above. Methodology, licensing, status all public:
> - [METHODOLOGY.md](https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md)
> - [LICENSING.md](https://github.com/billkhiz-bit/london-flight-path-map/blob/master/LICENSING.md)
> - [Status page](https://skyscore.co.uk/score-demo/status.html)
>
> Thanks,
> Bilal Khizar
> billkhiz@gmail.com · LinkedIn: [billkhiz-bit](https://www.linkedin.com/in/billkhiz)

### Specific tweaks per Tier-1 target

- **Landmark Information**: their RiskView product is the natural integration point. Reference: "your RiskView API ingests planning and environmental layers — Sky Score is a similarly-scoped noise + livability layer."
- **TM Group**: their PlainSearch reports cover planning, drainage, environmental. Reference: "PlainSearch covers structural risk; Sky Score covers experiential risk (noise, school catchment, transport access)."
- **OneSearch Direct**: emphasise time-to-integration (hours, not weeks) and OGL data attribution already shipped.

---

## Tier 2 cold email — Islamic finance (Al Rayan, StrideUp, Gatehouse, Nester, Yielders)

Different tone — aligned-values angle matters more than feature differentiation.

**Subject:** Halal-aware property data API for [Company] underwriting

> As-salamu alaykum [first name],
>
> I'm building **Sky Score** (skyscore.co.uk), a UK property noise + livability data API explicitly built with Sharia-compliant home-finance integrators in mind. The B2B endpoint surfaces the structural property data — aircraft noise, road noise, schools, crime, transport — that affects whether a property is genuinely a good buy for a [Company] customer.
>
> Why this matters for [Company] specifically:
>
> - **Maqasid al-Shariah alignment** — protecting buyers from harm (noise, poor schools, environmental risks) maps directly to Hifz an-Nasl (preservation of progeny / family) and Hifz al-Mal (preservation of wealth). Listings sites have a structural incentive to obscure this; Sky Score doesn't.
> - **Riba-free targeting** — Sky Score's customer focus is explicitly halal-finance providers, conveyancers, B2R operators, public bodies. Not conventional banks or insurers. (My memory note on this is one of the reasons I built it.)
> - **No AI hallucination layer** — every score is deterministic, anchored to DEFRA / Ofsted / ONS published thresholds. Methodology fully public for audit.
>
> Try the demo at `https://skyscore.co.uk/score-demo/` — `N1 7SX` or `TW3 4DX`. If [Company]'s underwriting team would find the per-postcode data useful, I'd value a 20-minute conversation.
>
> Methodology: [https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md](https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md)
>
> JazakAllahu khairan,
> Bilal Khizar
> billkhiz@gmail.com

### Specific tweaks per Tier-2 target

- **Al Rayan Bank**: largest UK Islamic bank; primary halal-finance partner in the buildathon plan. Mention Buildathon participation if applying.
- **StrideUp**: founder-direct outreach (Sakeeb Zaman). Digital-native angle — they'll appreciate the OpenAPI spec.
- **Gatehouse Bank**: more institutional; lead with "audit-defensible methodology" rather than founder-velocity language.
- **Nester / Yielders**: smaller teams, founder-direct; emphasise integration ease (1 endpoint, 1 API key, 5-minute setup).

---

## Subject-line A/B options (for when the first attempt doesn't reply)

If first email gets no reply within 7 days, send a second with a different subject:

- **Question subject**: "Quick question about [Company]'s noise data sourcing"
- **Specific-postcode subject**: "Why is `TW3 4DX` scoring 0/10 quiet on Sky Score?"
- **Industry-news subject**: "Re: [recent industry news re property data / disclosures]"

Avoid subject lines that look automated: anything with "[Company]" placeholder left in, anything starting "Following up", anything with "circling back".

---

## After sending — log it

Add a row to the relevant tier table in `OUTREACH_LOG.md`:

| Date | Contact | Company | Role | Channel | Status | Notes / Next action |
|---|---|---|---|---|---|---|
| YYYY-MM-DD | Name | Company | Role | Email / LinkedIn / Warm intro | 🟡 Awaiting reply | Sent X. Chase if no reply by YYYY-MM-DD (7 days). |

Reply states (per OUTREACH_LOG.md legend):
- 🟢 Active conversation
- 🟡 Awaiting reply (default after send)
- 🟠 Stalled (no reply >14 days)
- 🔴 Closed, not interested
- ⚪ Closed, out of scope / wrong person
- 🔵 Customer (signed)
