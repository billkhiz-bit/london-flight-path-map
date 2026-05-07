# Draft email — OpenSky Network licensing enquiry

**To:** `contact@opensky-network.org`
**From:** `billkhiz@gmail.com`
**Subject:** Licensing enquiry — Sky Score (UK property data tool)
**Status:** Draft, ready to send.

---

Hi,

I'd like to enquire about licensing for using OpenSky's `/api/states/all` endpoint in **Sky Score** (<https://skyscore.co.uk>), a UK property noise + livability data tool.

We had a "live aircraft" toggle on the consumer site and a 3D radar prototype, both backed by a server-side proxy using our OAuth2 client credentials. Each request only asked for aircraft inside a small box around London or NYC (about 78 × 70 km and 56 × 60 km respectively, never the unbounded global feed); responses were cached at our Lambda for 12 seconds per city to keep upstream load minimal; an OpenSky attribution string was surfaced in every API response. I removed both surfaces this week after re-reading your terms — they require a written agreement for operational use, including consumer surfaces.

A few specifics:
- Independent project, sole developer; consumer site is free, B2B API is the product
- Traffic: low single-digit concurrent visitors today; growth expected but not forecast
- Geographic scope: small windows around London and NYC only — nothing global
- Already on OAuth2 client credentials per the March 2026 change; happy to surface OpenSky branding visibly on any consumer surface

Could you let me know what licensing options fit our profile? Specifically: does the existing free OAuth tier (4000 credits/day) extend to operational use of the kind described above, or is that tier only for non-operational / hobbyist access? If it does cover us, brilliant — we'd just turn the proxy back on. If a paid agreement is the route, a rough sense of pricing for our traffic level would help me decide whether to pursue now or hold until revenue justifies it.

Thanks,
Bilal Khizar
Sky Score · <https://skyscore.co.uk>
<billkhiz@gmail.com>

---

## After sending

Add to `OUTREACH_LOG.md` under a new `## Vendor / data licensing` section:

| Date | Contact | Company | Role | Channel | Status | Notes / Next action |
|---|---|---|---|---|---|---|
| YYYY-MM-DD | `contact@opensky-network.org` | OpenSky Network | Licensing | Email | 🟡 Awaiting reply | Sent licensing enquiry; chase if no reply by YYYY-MM-DD (4 weeks) |
