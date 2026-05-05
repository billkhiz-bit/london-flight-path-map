# Sky Score Buildathon Plan

**Status:** Awaiting eligibility reply from Shared Futures Foundation (email sent 2026-05-05). Application deadline 2026-05-15. Event 2026-06-07.

---

## Competition

- **Shared Futures Foundation Buildathon London 2026**
- Application deadline: **2026-05-15** (10 days from save date)
- Event: Sunday 7 June 2026, 08:00–22:30, central London
- Effective build time: ~9.5h (build 09:30 → freeze 19:00). Demos 5min + 3min Q&A.
- Track: **Interchange (open)** — "products in categories dominated by a top-100 company lacking ethical alternatives"
- Solo applicant
- Prize: £10k build grant + 90-day incubation (top 4–6) + angel syndicate access (top 2). No equity taken.
- Judging weights: Problem Clarity 20 / Working Product 25 / Ethical Integrity 25 / Adoption Potential 15 / Continuation Viability 15
- One panellist explicitly **Ethical Finance** — direct match for halal home-buying angle.
- Partners: Replit (credits for every team), Ummah.com (API + sandbox), boycat, Muslim Tech Fest. 2M+ combined reach.

## Positioning

**Sky Score for Halal Home Buyers** — ethical alternative to Rightmove/Zoopla for property due-diligence, focused on Sharia-compliant home-buying.

- **Top-100 incumbents to displace**: Rightmove (FTSE 250, £4.5bn cap) and Zoopla (£2bn+ revenue). Neither offers honest noise/livability data; both incentivised to keep buyers under-informed (estate-agent revenue model).
- **Ethical angle**: riba-aware, health-aware, Maqasid al-Shariah aligned. Designed for buyers using Islamic home purchase plans (Murabaha / Ijara / Diminishing Musharakah).

## Lead partners (named in application)

- **Al Rayan Bank** (UK's largest Islamic bank, £2bn+ assets) — primary halal-finance partner
- **StrideUp** (digital-native Islamic home purchase plans) — secondary halal-finance partner
- **Ummah.com** (Buildathon partner — API access for every team) — distribution + integration target

## Fork plan

Separate repo + deployment from the original Sky Score (mirrors the Siraj → Siraj Noor pattern). Original stays as the consumer site + API exploration; fork is the buildathon variant.

- **Repo name (proposed)**: `sky-score-halal`
- **Deployment**: Cloudflare Pages or Replit (Replit is a Buildathon partner — bonus integration signal)
- **Backend**: shared. New `/v1/score` Lambda extracted from existing scoring logic (also serves the standalone B2B API roadmap)

### Pre-work (before 7 June, only if Foundation confirms eligibility)

- Create new GitHub repo
- Stand up new deployment
- Extract `/v1/score` to a Lambda from existing frontend logic
- Clean noise/livability data into Lambda-served JSON

### On-day build (9.5h, 09:30 → 19:00 on 7 June)

- Ummah.com OAuth integration
- Halal-finance partner UI (Al Rayan + StrideUp panels with Sharia-compliant home-purchase explainer)
- Halal-aware affordability score (no implicit-mortgage assumptions; show purchase-plan structure)
- Demo polish (5-min walkthrough script)

### 5-min demo flow

1. Sign in with Ummah.com (partner API in action)
2. Search a London property
3. Sky Score loads from `/v1/score`
4. Halal-aware affordability: "with a 20% deposit, Al Rayan / StrideUp / Gatehouse offer..."
5. Cross-device save to Ummah.com profile

## Eligibility check (pending)

Email sent 2026-05-05 to buildathon@sharedfuturesfoundation.org.uk asking whether extending an existing product (Sky Score, Amazon Nova hackathon entry) with a halal-finance variant built on the day is acceptable for the Interchange.

- **If yes**: apply with the framing below; do pre-work this/next week; build the halal variant on the day.
- **If no / restrictive**: restructure — build a smaller standalone halal-property tool from scratch during the day, treat Sky Score as inspiration only.

## Application framing (draft, ready when eligibility confirmed)

> Sky Score's noise + livability core was built for the Amazon Nova AI Hackathon (March 2026, won AWS credits). The Buildathon delivers Sky Score Halal — a focused fork (separate repo, separate deployment) — built on the day: Ummah.com OAuth, Al Rayan + StrideUp halal-finance integration, halal-aware affordability scoring, served from a shared `/v1/score` API endpoint.

## Cross-references

- Memory: `project_buildathon_focus.md` (Sky Score memory dir)
- Memory: `project_api_target_customers.md` (B2B target customer strategy)
- Memory: `feedback_no_riba_customers.md` (riba constraint)
- Sister project: Siraj Noor at `C:\Users\bilal\projects\siraj-noor` (QF hackathon entry, deadline 2026-05-20, separate competition, no cross-pollination)

## Decision queue

1. Foundation eligibility reply — when received, decide framing
2. If yes: produce 1-page Interchange application by 2026-05-12 (3-day buffer before 2026-05-15 deadline)
3. Pre-work week of 2026-05-26 (extract `/v1/score`, fork repo, set up deployment)
4. Event day rehearsal (week of 2026-06-01): walk through 5-min demo
