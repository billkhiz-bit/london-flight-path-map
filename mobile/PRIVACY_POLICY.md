# Sky Score — Privacy Policy

**Last updated**: 2026-05-09
**Effective**: 2026-05-09

This is a draft. Before submission to App Store / Play Store, host this at `https://skyscore.co.uk/privacy` (the URL referenced in `STORE_LISTINGS.md`). Update the date whenever you change the substance.

---

## TL;DR

- We don't collect personal data, accounts, or tracking IDs
- We don't sell anything to anyone
- Your location stays on your device unless you tap "Score where I am" — then it's used once to find your postcode and discarded
- Anonymous analytics tell us how many people use the app (no cookies, no profiles)

---

## 1. Who we are

**Sky Score** is operated by Bilal Khizar, an independent developer based in the United Kingdom.

- Website: https://skyscore.co.uk
- Contact: support@skyscore.co.uk

For data protection purposes, we act as the **data controller** for the limited data described below.

---

## 2. What data we collect

### 2a. Data you actively give us

**None.** Sky Score does not require an account, email address, name, phone number, or any other identifying information. There are no sign-up forms, no payment forms, and no surveys.

### 2b. Data the app uses temporarily, on your device only

When you tap **"Score where I am"** (native iOS or Android app only):

- Your device's GPS coordinates (latitude + longitude) are read by the app
- The app sends those coordinates to **api.postcodes.io** (a free UK government postcode lookup service, operated under the Open Government Licence)
- The response (your nearest UK postcode) is shown to you and used to fetch a Sky Score
- The coordinates are **not** stored, logged, profiled, or shared anywhere else

If you deny the location permission, the rest of the app works normally — you just have to type a postcode manually.

### 2c. Anonymous usage analytics

We use **GoatCounter** ([goatcounter.com](https://www.goatcounter.com)) for privacy-respecting analytics. GoatCounter:

- Sets **no cookies**
- Records no IP addresses (IPs are hashed and discarded server-side)
- Does **not track users across sites**
- Stores aggregate counts only — page views, referrers, screen sizes
- Is hosted in the EU (Berlin)

This is comparable to a server-side log of HTTP requests, with personal data scrubbed.

### 2d. Server logs (AWS)

Sky Score's backend runs on AWS Lambda + API Gateway in the eu-west-2 region (London). API Gateway logs include:

- Request timestamp
- Request path (e.g. `/v1/score`)
- Response status code
- Source IP address
- User agent

These logs are retained for **7 days** then automatically deleted. We use them solely for debugging and to investigate suspected abuse. We do not link logs to identities.

---

## 3. What data we do NOT collect

To be unambiguous:

- We do not track you across other apps or websites
- We do not build advertising profiles
- We do not sell, rent, or license any data to third parties
- We do not use third-party analytics that profile users (no Google Analytics, no Facebook Pixel, no Mixpanel, no Segment)
- We do not use cross-app identifiers (no IDFA, no ADID, no device fingerprinting)
- We do not use the contents of your messages, photos, contacts, or calendar
- We do not record audio or video
- We do not access your microphone or camera

---

## 4. Subprocessors

The third parties below process limited data on our behalf:

| Subprocessor | Purpose | Data | Region |
|---|---|---|---|
| Amazon Web Services (AWS) | Backend compute, API Gateway, DynamoDB | Anonymous request logs (7-day retention) | eu-west-2 (London) |
| Cloudflare / Amazon S3 + CloudFront | Static asset delivery | Standard CDN logs | Multi-region |
| api.postcodes.io | Postcode lookup from coordinates | Lat/lon (transient) | UK |
| GoatCounter | Anonymous analytics | Aggregate counts | EU (Berlin) |
| Codemagic | Building the iOS / Android binaries | Source code only — no user data | EU |
| Apple App Store / Google Play Store | App distribution + crash reports if you opt in | Standard store telemetry | Various |

If you'd like the full list with their respective privacy policies, see [SUBPROCESSORS.md](https://github.com/billkhiz-bit/london-flight-path-map/blob/master/SUBPROCESSORS.md) in our public repo.

---

## 5. Data we receive from public sources

Sky Score's *content* (the underlying scores) is computed from open public data:

- DEFRA Strategic Noise Maps (Round 4, 2022)
- HM Land Registry Price Paid Data
- Energy Performance Certificate (EPC) data via the MHCLG register
- ONS National Statistics Postcode Lookup
- Office for National Statistics neighbourhood statistics
- NHS facility location data (via OpenStreetMap)
- TfL Open Data

All under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). When you ask for a postcode score, we look up the relevant pre-computed values for that postcode. We don't request data about you from any of these sources.

---

## 6. Your rights (UK GDPR)

Even though we hold very little data about you, your UK GDPR rights still apply. You can:

- **Ask what data we hold about you** (almost certainly: nothing)
- **Ask us to delete any data we do hold** (we'll do it within 30 days)
- **Withdraw consent** to anything we're processing under consent (e.g., uninstalling the app revokes location consent)
- **Lodge a complaint** with the Information Commissioner's Office: [ico.org.uk](https://ico.org.uk)

To exercise these rights, email `support@skyscore.co.uk`.

---

## 7. Children

Sky Score has no minimum age requirement and does not knowingly collect data from anyone, including children. The app is rated 4+ on App Store and PEGI 3 / Everyone on Play Store.

---

## 8. Cookies (web only)

The Sky Score website (skyscore.co.uk) does **not** use cookies. The native iOS and Android apps do not use cookies either.

---

## 9. International data transfers

If you use the app outside the UK or EU, your usage data may transit through AWS edge locations in your region before reaching the UK / EU origin. AWS edge transfers are encrypted in flight and do not constitute a data transfer for GDPR purposes (no controller-controller relationship).

---

## 10. Security

- All API calls use HTTPS (TLS 1.2+)
- AWS infrastructure is hosted in eu-west-2 (London) with standard AWS security controls
- API rate limiting is in place to prevent abuse
- The full security posture is documented at [github.com/billkhiz-bit/london-flight-path-map/blob/master/SECURITY.md](https://github.com/billkhiz-bit/london-flight-path-map/blob/master/SECURITY.md)

If you find a security issue, please email `support@skyscore.co.uk` rather than disclosing publicly. We commit to acknowledging within 48 hours.

---

## 11. Changes to this policy

If we make material changes (e.g. adding a new subprocessor or a new data type), we'll update the "Last updated" date and surface a notice in the app on next launch. Non-material changes (typos, formatting) won't trigger a notice.

---

## 12. Contact

For any privacy-related question:

**Email**: support@skyscore.co.uk
**Postal**: Available on request

We aim to reply within 5 working days.
