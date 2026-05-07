# AviationStack — fallback live-aircraft provider spike

Reference doc for **if/when OpenSky says no** (Ticket #835285) or never replies. AviationStack is the most commercially-friendly off-the-shelf alternative; this captures what we'd need to swap in.

**Status:** spike, not committed. Account not created. Implementation deferred until OpenSky reply lands or chase date (2026-06-04) passes.

## Why AviationStack vs the alternatives

| Provider | Free tier | Commercial use | Pricing for our scale | Verdict |
|---|---|---|---|---|
| **OpenSky** (current) | Free OAuth (4000 credits/day) | **Requires written agreement** for any operational use; reply pending | Unknown | Blocked on licensing |
| **AviationStack** | 500 req/month, no card | "Commercial use" gated to paid plans; clear pricing | ~$50/mo Basic (10k req) → ~$500/mo Business (250k req) | **Best option** if OpenSky says no |
| **FlightAware AeroAPI** | None / very limited | Enterprise sales conversation; pricing on request | "$$$" — typically $1k+/mo | Overkill at our scale |
| **ADSBHub / OpenADSB** | Free / community | Same-pattern community licensing as OpenSky | Same risk as OpenSky | No improvement |
| **Self-host ADS-B receiver** | Hardware + setup | OK (the data you collect is yours) | Hardware ~£100 one-off + hosting | Most work; no licensing concern |

AviationStack wins on: clear pricing, explicit commercial-friendly licensing, 30-60s data freshness (close to OpenSky's real-time), no separate licensing negotiation.

## Integration shape

**API:** `https://api.aviationstack.com/v1/flights?access_key=YOUR_KEY` (REST). Same general shape as OpenSky `/api/states/all`.

**Bbox / geographic filtering:** AviationStack filters by airport (ICAO/IATA) rather than by lat/lon bounding box. For Sky Score, that means querying per airport (LHR, LGW, LCY, JFK, LGA, EWR, etc.) and merging client-side, instead of one bbox query covering all flights in a region. ~5 queries per refresh per city.

**Rate vs cost trade-off:**
- 500 req/month free: 1 query per ~88 minutes — too slow for live tracking
- 10k req/month at $50: ~14 queries/hour. Cache per Lambda for 4 minutes per airport → 5 airports × 15 = 75 queries/hour ÷ 5 = 15/hour upper-bound. Fits.
- 50k req/month at ~$150: comfortable headroom for 1 city
- 250k req/month at ~$500: covers London + NYC + buffer

**At our scale today (low single-digit visitors):** the **free tier (500/mo) might actually be enough** if we cache aggressively. 1 update per minute × 60 min × 24 hr × 30 days = 43,200 — way over. But 1 update per 10 min × 5 airports = 21,600/mo. Still over.
At 1 update per 30 min × 5 airports = 7,200/mo. Still over the free 500.
**Realistic minimum**: 500/mo cap = ~1 query per 90 min, which is too slow for "live" tracking. Free tier is for evaluation, not production.

→ **Conclusion: $50/mo Basic plan is the realistic minimum for production live tracking.**

## What we'd need to change

### Backend
- New Lambda: `backend/lambdas/live_flights/app.py` (mirror the previously-removed one but call AviationStack)
- Per-airport queries instead of bbox; merge results before returning
- Cache more aggressively (currently 12s; AviationStack pricing implies 60-300s caching)
- Env vars: `AVIATIONSTACK_API_KEY` (NoEcho param + AllowedPattern '^.+$' as we did for EpcBearerToken)
- Restore the API Gateway route + the Lambda block in template.yaml

### Frontend
- Restore the live-aircraft toggle on `index.html` (revert the relevant chunk of commit `6f6ce7d`)
- Re-enable prototype's live mode (`liveLicensed = true` in `prototype/index.html`)
- Update normalisation: AviationStack response shape differs from OpenSky's positional array; map their `flight.live.latitude/longitude/altitude/direction/speed_horizontal` to the same client-side schema.

### Docs
- `LICENSING.md`: move OpenSky from "Removed sources" to "Removed (replaced by AviationStack)"; add AviationStack row with their commercial-use terms link
- `ROADMAP.md`: close the OpenSky open decision; new line item for AviationStack subscription cost as a real OpEx
- `CLAUDE.md`: update env-var setup + token rotation hygiene for the new key
- `OPENSKY_LICENSING_EMAIL.md`: archive (chase date passed; alternative shipped)

### One-time admin
- Sign up at <https://aviationstack.com/signup/free> with `billkhiz@gmail.com`
- Verify the free tier works for the integration spike
- Upgrade to Basic ($50/mo) before going to production; add card

## Estimated effort if we pull the trigger

- Sign up + smoke test free tier: ~30 min
- Lambda + template.yaml + .env wiring: ~1 hour
- Frontend revert + normalisation: ~45 min
- Docs sweep: ~30 min
- Smoke test the deployed integration: ~15 min

**Total: ~3 hours from "OpenSky said no" to "live aircraft back on the consumer site, billed differently."**

## When to pull the trigger

Only when one of the following:
1. OpenSky replies "no" to Ticket #835285
2. **2026-06-04 (4-week chase date) passes with no human reply** from OpenSky
3. A paying B2B customer asks for live aviation data before either of the above (rare; the B2B `/v1/score` API doesn't use OpenSky)

**Default until trigger:** the live-aircraft feature stays removed. Spec the integration; don't build it.

Sources:
- [AviationStack Pricing](https://aviationstack.com/pricing)
- [AviationStack FAQ](https://aviationstack.com/faq)
- [Best Flight Data APIs in 2026 — Geekflare comparison](https://geekflare.com/dev/flight-data-api/)
