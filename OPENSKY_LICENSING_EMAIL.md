# Draft email — OpenSky Network licensing enquiry

**To:** `contact@opensky-network.org`
**From:** `billkhiz@gmail.com`
**Subject:** Licensing enquiry — Sky Score (UK property data tool)
**Status:** Draft, ready to send.

---

Hi,

I'd like to enquire about licensing for using OpenSky's `/api/states/all` endpoint in **Sky Score** (<https://skyscore.co.uk>), a UK property noise + livability data tool.

We had a "live aircraft" toggle on the consumer site and a 3D radar prototype, both backed by a server-side proxy with our OAuth client credentials, bbox-restricted to London or NYC, response cached 12 s per city, OpenSky attribution surfaced in every API response. I removed both surfaces this week after re-reading your terms — they require a written agreement for operational use, including consumer surfaces.

A few specifics:
- Independent project, sole developer; consumer site is free, B2B API is the product
- Traffic: low single-digit concurrent visitors today; growth expected but not forecast
- Geographic scope: London + NYC bboxes only (~0.5° × 0.5° each)
- Already on OAuth2 client credentials per the March 2026 change; happy to surface OpenSky branding visibly on any consumer surface

Could you let me know what licensing options fit our profile? If a community licence covers us, ideal — if a paid agreement is the route, a rough sense of pricing for our traffic level would help me decide whether to pursue now or hold until revenue justifies it.

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
