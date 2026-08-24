# Sky Score Buildathon Plan

**Status (2026-05-07):** Awaiting eligibility reply from Shared Futures Foundation (email sent 2026-05-05, 2 days silent). Application deadline **2026-05-15** (8 days). Event 2026-06-07.

**Action this week:**
- **Chase Foundation by 2026-05-10** if no reply (need ≥5 days to draft + submit application before deadline).
- Most pre-work below is already done as part of the productisation track — the buildathon-specific work narrows to: separate repo, halal-aware affordability variant, Ummah.com OAuth, demo flow.

---

## Competition

- **Shared Futures Foundation Buildathon London 2026**
- Application deadline: **2026-05-15** (10 days from save date)
- Event: Sunday 7 June 2026, 08:00-22:30, central London
- Effective build time: ~9.5h (build 09:30 → freeze 19:00). Demos 5min + 3min Q&A.
- Track: **Interchange (open)**, "products in categories dominated by a top-100 company lacking ethical alternatives"
- Solo applicant
- Prize: £10k build grant + 90-day incubation (top 4-6) + angel syndicate access (top 2). No equity taken.
- Judging weights: Problem Clarity 20 / Working Product 25 / Ethical Integrity 25 / Adoption Potential 15 / Continuation Viability 15
- One panellist explicitly **Ethical Finance**, direct match for halal home-buying angle.
- Partners: Replit (credits for every team), Ummah.com (API + sandbox), boycat, Muslim Tech Fest. 2M+ combined reach.

## Positioning

**Sky Score for Halal Home Buyers**, ethical alternative to Rightmove/Zoopla for property due-diligence, focused on Sharia-compliant home-buying.

- **Top-100 incumbents to displace**: Rightmove (FTSE 250, £4.5bn cap) and Zoopla (£2bn+ revenue). Neither offers honest noise/livability data; both incentivised to keep buyers under-informed (estate-agent revenue model).
- **Ethical angle**: riba-aware, health-aware, Maqasid al-Shariah aligned. Designed for buyers using Islamic home purchase plans (Murabaha / Ijara / Diminishing Musharakah).

## Lead partners (named in application)

- **Al Rayan Bank** (UK's largest Islamic bank, £2bn+ assets), primary halal-finance partner
- **StrideUp** (digital-native Islamic home purchase plans), secondary halal-finance partner
- **Ummah.com** (Buildathon partner, API access for every team), distribution + integration target

## Fork plan

Separate repo + deployment from the original Sky Score (mirrors the Siraj → Siraj Noor pattern). Original stays as the consumer site + API exploration; fork is the buildathon variant.

- **Repo name (proposed)**: `sky-score-halal`
- **Deployment**: Cloudflare Pages or Replit (Replit is a Buildathon partner, bonus integration signal)
- **Backend**: shared. New `/v1/score` Lambda extracted from existing scoring logic (also serves the standalone B2B API roadmap)

### Pre-work status (2026-05-07)

What's already done as part of the main productisation track (no extra buildathon work needed):
- ✅ **`/v1/score` Lambda extracted, hardened, deployed** — shipped 2026-05-05; today's session added per-route throttle, IAM tag-conditions on signup, XSS hardening across the consumer site, and 9 unit tests for the live_flights Lambda before that was removed for OpenSky-licensing reasons. Score Lambda has 70/70 backend tests passing (61 currently after live_flights tests removed).
- ✅ **Noise/livability data cleaned into Lambda-served JSON** — DEFRA Round 4 (2022) Lden raster sampled at every UK postcode centroid, written to DynamoDB. v3.1 raster path is live and resolving most central-London postcodes (~2.3M of ~2.5M NSPL rows loaded as of 2026-05-07).
- ✅ **Methodology defensibility positioning** strengthened — AI features removed from consumer UI 2026-05-07, narrative is now "deterministic data, not AI summaries". Aligns with Maqasid al-Shariah (no harm from misleading data) which is the *exact* judging panel angle.

What's still buildathon-specific (do once Foundation confirms eligibility):
- Create new GitHub repo (`sky-score-halal`)
- Stand up new deployment (Cloudflare Pages or Replit — Replit is a Buildathon partner, bonus integration signal)
- Halal-aware affordability variant: replace conventional-mortgage assumption with Murabaha / Ijara / Diminishing Musharakah cost calc

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
- **If no / restrictive**: restructure, build a smaller standalone halal-property tool from scratch during the day, treat Sky Score as inspiration only.

## Application framing (draft, ready when eligibility confirmed)

> Sky Score's noise + livability core was built for the Amazon Nova AI Hackathon (March 2026, won AWS credits). The Buildathon delivers Sky Score Halal, a focused fork (separate repo, separate deployment), built on the day: Ummah.com OAuth, Al Rayan + StrideUp halal-finance integration, halal-aware affordability scoring, served from a shared `/v1/score` API endpoint.

## Cross-references

- Memory: `project_buildathon_focus.md` (Sky Score memory dir)
- Memory: `project_api_target_customers.md` (B2B target customer strategy)
- Memory: `feedback_no_riba_customers.md` (riba constraint)
- Sister project: Siraj Noor at `C:\Users\bilal\projects\siraj-noor` (QF hackathon entry, deadline 2026-05-20, separate competition, no cross-pollination)

## Decision queue

1. **2026-05-10**: chase Foundation if still no reply (5-day deadline buffer)
2. **When reply lands**: decide framing (extend Sky Score vs build standalone halal property tool from scratch on the day)
3. **2026-05-12 hard deadline**: produce 1-page Interchange application (3-day buffer before 2026-05-15 close). Section drafts to write: Problem Clarity (the listings-site information asymmetry + halal-finance gap), Working Product (Sky Score + the halal variant), Ethical Integrity (Maqasid al-Shariah + riba-free targeting + DEFRA-anchored deterministic scoring), Adoption Potential (Al Rayan / StrideUp / Gatehouse / Ummah.com network), Continuation Viability (B2B API monetisation already chosen — see ROADMAP §"Monetisation strategy").
4. **Week of 2026-05-26**: buildathon-specific pre-work — fork repo, stand up new deployment. (Skip the `/v1/score` extraction step — that's already shipped.)
5. **Week of 2026-06-01**: rehearse 5-min demo + Q&A.

## Strategic alignment notes (added 2026-05-07)

The data-first pivot done this session strengthens the buildathon angle in concrete ways worth surfacing in the application:

- **Ethical Integrity (25% of judging)**: removing AI summaries on top of deterministic scores eliminates the hallucination risk that would have weakened a Maqasid-al-Shariah pitch (no harm from misleading data). The story is now "every threshold anchored to a published source; no AI vibes layered on top."
- **Working Product (25%)**: per-postcode quiet via DEFRA raster (v3.1) is gold-standard; the audit script `scripts/audit_flight_paths.py` validates the visualisation against the underlying noise data. Makes the "working" claim defensible under judge questioning.
- **Continuation Viability (15%)**: monetisation strategy resolved (convenience-tier B2B API); per-Lambda auth + throttling + signup hardening done; OpenAPI spec public. Not a hackathon toy — a productised service.
