# Sky Score outreach drafts

Templates for the outreach pipeline in `ROADMAP.md` §"Outreach pipeline". Adapt per target. Log every send in `OUTREACH_LOG.md`.

**Cadence (per ROADMAP):**
- 2 warm-intro asks per week to LinkedIn 1st/2nd connections at Tier-1/2 targets — first batch due **2026-05-08**.
- 2 cold emails per week using the templates below — starting week of **2026-05-12**.
- Chase Emergent Ventures if no reply by **2026-05-12** (form promised "within ~1 week").

**⚠ Send gate (2026-07-24):** no cold email goes out from the skyscore.co.uk domain until Migadu/DKIM is set up (ROADMAP open item) — unauthenticated domain mail lands in spam and burns the target. LinkedIn DMs and warm intros are not gated.

---

## Pilot-first variants (2026-07-24) — USE THESE FIRST

Post-Haatch reframe: the ask is no longer "a 20-minute call to discuss" — it is the **90-day £2,500 pilot** (live at [skyscore.co.uk/pricing](https://skyscore.co.uk/pricing)), with the call as the scoping step. A signed pilot or LOI plus outcome evidence is the current commercial-proof goal; the LOI template lives at `Desktop/SKY_SCORE_LOI_TEMPLATE.md` (kept out of this public repo), alongside `Desktop/SKY_SCORE_PILOT_ONE_PAGER.md`.

### Tier 1 — aggregators, pilot-first

**Subject:** A 90-day noise-data pilot for [Company]'s reports

> Hi [first name],
>
> I run **Sky Score** (skyscore.co.uk) — an environmental and livability data API for UK property: aircraft and road noise, air quality, schools, crime, transport, each anchored to published government sources (DEFRA, Ofsted, ONS) with an open, versioned methodology.
>
> [Company]'s [reports / search products] cover flood, planning and environmental risk — but no defensible noise layer, the gap the DMCC material-information rules make expensive to ignore.
>
> Rather than a long procurement conversation, I run a fixed-scope 90-day pilot: **£2,500 + VAT**, one success metric agreed at day 0, review at day 45, written evidence report at day 90 — and the fee is credited in full against a licence if you continue. Terms: [skyscore.co.uk/pricing](https://skyscore.co.uk/pricing?utm_source=outreach-{SLUG}&utm_medium=email&utm_campaign={YYYY-MM})
>
> Worth a 20-minute call to scope the metric?
>
> Bilal Khizar
> support@skyscore.co.uk · skyscore.co.uk

### Tier 2 — Islamic finance, pilot-first

**Subject:** A measured pilot: property-harm data for [Company] customers

> As-salamu alaykum [first name],
>
> I'm Bilal Khizar, founder of **Sky Score** (skyscore.co.uk) — a UK property data API surfacing the structural harms listings sites are incentivised to hide: aircraft and road noise, air quality, crime, school quality. Protecting buyers from hidden harm is the point — the Maqasid alignment (Hifz al-Mal, Hifz an-Nasl) is why the customer focus is halal-finance providers, not conventional lenders.
>
> Every score is deterministic and anchored to published DEFRA / Ofsted / ONS thresholds — no AI layer, methodology fully public for Sharia-board or audit scrutiny.
>
> The concrete proposal: a **90-day pilot, £2,500 + VAT**, one metric your team already cares about (e.g. environmental-harm flags per postcode vs manual review), agreed at day 0, written evidence report at day 90, fee credited against a licence if you continue. Terms: [skyscore.co.uk/pricing](https://skyscore.co.uk/pricing?utm_source=outreach-{SLUG}&utm_medium=email&utm_campaign={YYYY-MM})
>
> Would a 20-minute scoping call be worthwhile?
>
> JazakAllahu khairan,
> Bilal Khizar
> support@skyscore.co.uk · skyscore.co.uk

### LinkedIn DM — pilot-first (short)

> Hi [first name] — I run Sky Score (skyscore.co.uk), a noise + livability data API for UK property, methodology anchored to DEFRA/Ofsted/ONS and fully published.
>
> I'm running fixed-scope 90-day pilots (£2,500, one agreed metric, written evidence report at day 90, fee credited against a licence). Given [Company]'s [product], is that worth a 20-minute scoping call?

### If they bite — the close sequence

1. Scoping call → agree the **one metric** (day-0 definition, from the one-pager's examples).
2. Send the one-pager PDF + LOI (`Desktop/SKY_SCORE_LOI_TEMPLATE.md` → PDF) same day.
3. Signed LOI → log in `OUTREACH_LOG.md` (🟢), tell Haatch thread.
4. Kickoff invoice (entity gate: incorporate first — see one-pager internal notes).

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

## UTM convention (so you can see in analytics who clicked)

Every link to `https://skyscore.co.uk/api/` (or any other Sky Score URL) sent in cold email or DM **must** carry a UTM tag identifying the recipient. GoatCounter logs the full referrer URL including query string, so the tag flows through automatically — no extra setup needed beyond using the right URL when you send.

**Format:** `https://skyscore.co.uk/api/?utm_source=outreach-{slug}&utm_medium={channel}&utm_campaign={month}`

- `slug` — short lower-case company / contact identifier. Examples below.
- `channel` — `email` / `linkedin-dm` / `warm-intro` / `event-followup`
- `campaign` — `2026-05` / `2026-06` etc. (year-month). Lets you slice GoatCounter by campaign.

**Per-target slugs (use these consistently — analytics gets noisy if you spell the same target two ways):**

| Target | Slug |
|---|---|
| Landmark Information Group | `landmark` |
| TM Group | `tmgroup` |
| OneSearch Direct | `onesearch` |
| Geodesys | `geodesys` |
| Searches UK | `searchesuk` |
| Al Rayan Bank | `alrayan` |
| StrideUp | `strideup` |
| Gatehouse Bank | `gatehouse` |
| Nester | `nester` |
| Yielders | `yielders` |
| (Generic warm intro from a known contact) | `intro-{contact-firstname}` |

**Examples:**

```
https://skyscore.co.uk/api/?utm_source=outreach-landmark&utm_medium=email&utm_campaign=2026-05
https://skyscore.co.uk/api/?utm_source=outreach-strideup&utm_medium=linkedin-dm&utm_campaign=2026-05
https://skyscore.co.uk/api/?utm_source=intro-david&utm_medium=warm-intro&utm_campaign=2026-05
```

**Where to look in GoatCounter:** dashboard → *Referrers* tab. Sort by visits, filter by `outreach-` prefix to isolate cold-email traffic. Click any row to see the full URL (campaign + medium).

**Funnel events (auto-fire on click):** `api-methodology-click` (real diligence), `api-demo-click` (intent to try), `api-spec-click` (intent to integrate), `signup-attempted`, `signup-issued`. Visible under *Pages* with the `event/` prefix.

**Quick-paste snippet for a Tier 1 email link:**

```
the spec + live methodology is here:
https://skyscore.co.uk/api/?utm_source=outreach-{SLUG}&utm_medium=email&utm_campaign={YYYY-MM}
```

Replace `{SLUG}` and `{YYYY-MM}` per the table + current month.

---

## Organic social — Twitter / X

For broadcast launches, not 1:1 outreach. Two-tweet thread targeting two distinct audiences (renters/buyers in the lead post, builders/devs in the reply). Each tweet's UTM lets GoatCounter split clicks per audience.

### Tweet 1 — consumer hook (the lead post)

Sharper-hook version. Lead with the missing-information problem before naming the product:

> Property listings tell you bedrooms and price. They don't tell you flight noise, air quality, or flood risk.
>
> Sky Score does. UK or NYC postcode → all of it, from open gov data.
>
> Free, no signup. Built for the Nova hackathon, kept going.
>
> https://skyscore.co.uk/?utm_source=twitter&utm_medium=organic&utm_campaign=2026-05

**Char count:** ~263 (under 280, Twitter shortens URLs to 23 chars regardless of length). Hashtags omitted — builder-voice on X reads stronger without them.

#### Alternative — conversational variant

If the listings-vs-Sky-Score parallel feels too neat, this version leads with a more lived-in pain point (digging through forums to find out about noise):

> You can find a flat's bedrooms and price in 5 seconds. Knowing whether you'll wake up to plane noise or live next to flood risk takes hours of digging.
>
> Sky Score does it instantly. UK or NYC postcode, free, open gov data only.
>
> https://skyscore.co.uk/?utm_source=twitter&utm_medium=organic&utm_campaign=2026-05

Same UTM. Drops the hackathon origin — punchier but loses the credibility signal.

### Tweet 2 — API hook (reply to tweet 1)

> If you build with property data: there's a free /v1/score API too.
>
> GET ?postcode=N1+7SX → score + components + methodology in the JSON. POST /v1/score/batch for up to 100 in one call.
>
> 1000 reqs/month free, no card.
>
> https://skyscore.co.uk/api/?utm_source=twitter&utm_medium=organic&utm_campaign=2026-05

**Char count:** ~240. The "no card" line is the unblock — most "free tier" tweets fail because devs assume there's a credit-card paywall behind the signup.

### Practical notes

- **Attach a screenshot to tweet 1.** Image-tweets get materially more reach than text-only on X. Capture the consumer site showing a score for a recognisable London or NYC postcode (e.g. `N1 7SX`, `SW11 1AA`, `10001`) so people can visually verify the claim before clicking. The Wave 12.10 deploy is fully live, so the screenshot reflects current production.
- **Best posting time:** UK afternoon (~3-5pm GMT). Catches both UK property crowd and US dev Twitter coming online. Tuesday-Thursday strongest.
- **Hashtags:** skip. `#buildinpublic` is the only plausibly useful one but cheapens the tone.
- **UTM convention:** matches the email outreach format (`utm_source` differs by channel, `utm_campaign={YYYY-MM}`). GoatCounter funnel events from Wave 12.7 will report these clicks.

### After posting — log it

Add a row to the appropriate section in `OUTREACH_LOG.md` (consider adding an "Organic / social" tier table if one doesn't exist yet). Include the tweet URL so you can come back to engagement metrics, and the funnel events that fired.

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
