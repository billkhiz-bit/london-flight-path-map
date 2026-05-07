# Draft email — OpenSky Network licensing enquiry

**To:** `contact@opensky-network.org`
**From:** `billkhiz@gmail.com`
**Subject:** Licensing enquiry — Sky Score (UK property data tool)
**Status:** Draft, ready to send. Update if anything below has changed before you hit send.

---

Hi OpenSky team,

I'm writing to enquire about licensing options for using OpenSky Network's `/api/states/all` endpoint in **Sky Score**, a UK property noise + livability data tool.

## About Sky Score

Sky Score is a free consumer site at <https://skyscore.co.uk> and a B2B API at `/v1/score`. The consumer site shows aircraft and road noise scores for any UK postcode or NYC ZIP, sourced from DEFRA Strategic Noise Mapping (Round 4, 2022) and equivalent FAA / BTS data; the B2B API surfaces the same scores to property aggregators, conveyancers, and Sharia-compliant home-finance providers. Coverage today is 33 London boroughs + the five NYC boroughs (~182 residential ZIPs). Independent project, sole developer.

## The use case

We had a "live aircraft" toggle on the consumer-site map and a 3D radar prototype (`/prototype/`) that visualised current aircraft positions over London / NYC using your `/api/states/all` endpoint. Calls were made server-side via an AWS Lambda proxy authenticated with our OAuth2 client credentials, bbox-restricted to one city at a time, response cached for 12 seconds per city to keep upstream load minimal.

I removed both surfaces this week (May 2026) after re-reading your terms of use, which require a written agreement for any operational / commercial use, including consumer-facing live surfaces. I'd like to understand what licensing options exist for our profile before deciding whether to re-enable, replace with a paid alternative, or skip the feature entirely.

## Specifics that might affect a quote

- **Traffic:** low today (single-digit concurrent visitors typical); early-stage with growth expected, but no precise forecast.
- **Cache:** 12-second per-city cache at our Lambda so concurrent visitors share one upstream call.
- **Geographic scope:** London + NYC only, two ~0.5° × 0.5° bounding boxes.
- **Attribution:** every API response we serve already includes an OpenSky attribution string in a `sources` field. Happy to surface OpenSky branding visibly on any consumer surface using the data.
- **Authentication:** we already migrated to OAuth2 client credentials per the March 2026 change.

If a non-commercial / community licence covers our profile, that would be ideal. If a paid agreement is the right path, I'd appreciate a sense of pricing so I can decide whether to pursue it now or hold until our revenue justifies it.

Happy to provide any further information you need.

Best regards,

Bilal Khizar
Sky Score · <https://skyscore.co.uk>
<billkhiz@gmail.com>
GitHub: <https://github.com/billkhiz-bit>

---

## After sending — log the date in OUTREACH_LOG.md

Add a row to a new `## Vendor / data licensing` section in `OUTREACH_LOG.md`:

| Date | Contact | Company | Role | Channel | Status | Notes / Next action |
|---|---|---|---|---|---|---|
| YYYY-MM-DD | `contact@opensky-network.org` | OpenSky Network | Licensing | Email | 🟡 Awaiting reply | Sent licensing enquiry; chase if no reply by YYYY-MM-DD (4 weeks) |
