# Store Listings — Paste-Ready Copy

Both Apple and Google reject submissions for tone/quality reasons surprisingly often. This file is the source of truth — paste these strings into the listing forms exactly. Update here first, then propagate to the stores.

---

## App Store Connect

### App Information

| Field | Value |
|---|---|
| App Name | `Sky Score` |
| Subtitle (30 char max) | `Postcode noise & livability` |
| Bundle ID | `uk.co.skyscore.app` |
| SKU | `skyscore-001` |
| Primary Language | English (UK) |
| Primary Category | Reference |
| Secondary Category | Utilities |
| Content Rights | Does not contain third-party content (you own the data presentations) |

### Keywords (100 char limit, comma-separated, no spaces)

```
postcode,noise,property,livability,uk,london,flight,aircraft,affordability,score,buyer,renter
```

### Promotional Text (170 char, can update without re-review)

```
Find out how noisy and liveable any UK postcode is. Tap your location for an instant Sky Score: noise, affordability, growth, and liveability — all on the map.
```

### Description (4,000 char max)

```
Sky Score is the property data tool listings sites have a structural reason not to show you. Search any UK postcode, area, or borough — or tap your current location — and get an honest, independent score on the four things that actually shape life in a property: how quiet the skies are, how affordable it is, whether prices are growing, and how livable the area is overall.

WHY USE SKY SCORE

Estate agents and listings sites earn from completed transactions. Showing you that a flat is on a Heathrow descent path doesn't help close the deal, so they don't show it. Sky Score is built outside that incentive. The data is public — DEFRA Strategic Noise Maps, HM Land Registry Price Paid Data, EPC certificates, NHS/TfL — and our job is to combine it into a postcode-level score you can trust.

WHAT YOU GET

• Score from 1–10 based on quiet skies, affordability, growth and liveability
• Personalised by buyer profile (family, first-time buyer, later-life downsizer, etc.)
• Aircraft noise overlay from DEFRA's Strategic Noise Map (Round 4, 2022 data)
• Road noise, flood risk, air quality, transport, and labels as toggleable layers
• Tap any postcode for the precise dB at that spot
• 'Score where I am' button uses your phone's GPS for instant feedback on your current location

INDEPENDENT, OPEN, REPRODUCIBLE

We don't sell ads, push leads, or tilt scores toward sponsors. The methodology is published openly and the underlying data sources are cited at every step. If you doubt a score, you can read exactly how it was computed.

UK COVERAGE

Greater London plus expanding national coverage. Heathrow, Gatwick, London City, Stansted, Luton, and minor aerodromes. New York metro is included as a comparison surface.

PRIVACY

We don't track you across the web, build advertising profiles, or sell your data. Your location, when you use the 'Score where I am' button, is sent to api.postcodes.io to find the nearest postcode, then discarded. See our privacy policy for the full breakdown.

DATA SOURCES

DEFRA · Office for National Statistics · HM Land Registry · Department for Energy Security and Net Zero · Ministry of Housing, Communities & Local Government · Transport for London · NHS · Open Government Licence v3.0
```

### Support URL

```
https://skyscore.co.uk/
```

### Marketing URL (optional)

```
https://skyscore.co.uk/
```

### Privacy Policy URL

```
https://skyscore.co.uk/privacy
```

### Copyright (one-line)

```
© 2026 Bilal Khizar
```

### Age Rating Questionnaire

All "No" / "None" — Sky Score has no age-restricted content (no profanity, no realistic violence, no drugs, no horror, no sexual content, no gambling, no tobacco/alcohol, no controversial themes). Result: **4+**.

### What's New in This Version (release notes — first version)

```
First release of Sky Score for iOS. Features:
• Live noise + livability scores for any UK postcode
• Tap-to-score map with aircraft, road, and air-quality overlays
• Personalised buyer profiles (family, first-time, later-life, etc.)
• Use your current location to score where you are right now
• Independent, open methodology — no listings-site tilt
```

---

## Google Play Console

### App Information

| Field | Value |
|---|---|
| App Name (50 char) | `Sky Score: postcode noise data` |
| Short Description (80 char) | `Independent UK postcode noise + livability data. Score where you are.` |
| Default Language | English (United Kingdom) |
| Application Type | Application |
| Category | Tools |
| Tags | Reference, Lifestyle, Productivity |

### Full Description (4,000 char)

Use the same copy as the App Store description above (Google accepts the same length).

### Content Rating Questionnaire

Answer "No" to every restricted-content question. Result: **PEGI 3 / Everyone**.

### Pricing & Distribution

| Field | Value |
|---|---|
| Price | Free |
| Countries | All countries |
| Contains ads | **No** |
| In-app purchases | **No** |
| Designed for Families | **No** |
| Government / Official app | **No** |

### Data Safety form (Play Console)

Sky Score collects:
- **Approximate location** — to suggest the nearest postcode when the user taps "Score where I am"
- **Precise location** — same purpose, optional, requires user consent at run time
- **App activity** — anonymous interactions (button taps, searches) for service improvement (handled by GoatCounter, no cookies, no tracking IDs)

Sky Score does **NOT**:
- Track users across other apps or websites
- Share data with third parties for advertising
- Sell any data
- Collect personally identifiable information (no email, name, account, phone)

Each data type must be marked as: **Collected**, **Optional**, **Not shared**.

### Store Listing — graphic assets needed

| Asset | Specs |
|---|---|
| App icon | 512×512 PNG, no alpha (Capacitor-assets generates this) |
| Feature graphic | 1024×500 PNG, no alpha — TODO |
| Phone screenshots | 1080×1920 (or 9:16), min 2 / max 8 — TODO |
| Tablet screenshots (optional) | 1200×1920 — skip for first release |

---

## Common metadata for both stores

### Contact info

- Support email: `support@skyscore.co.uk` (set up an alias before submission)
- Public-facing contact name: `Bilal Khizar`
- Privacy policy URL: `https://skyscore.co.uk/privacy`

### Subprocessors disclosed in privacy policy

- AWS (data processing, eu-west-2)
- Cloudflare / S3 / CloudFront (static asset hosting)
- GoatCounter (privacy-respecting analytics, EU-hosted)
- Codemagic (build artefact pipeline, no user data)
- Apple App Store / Google Play Store (distribution)
- api.postcodes.io (postcode lookup; covered under Open Government Licence)

---

## Pre-submission checklist

Before tapping "Submit for review":

### App Store
- [ ] Demo account credentials filled in (n/a — no auth required)
- [ ] App preview video (optional, skip for first release)
- [ ] All screenshots uploaded for required device sizes
- [ ] Privacy policy URL is live and reachable
- [ ] Contact email actually receives mail
- [ ] App Review notes paste from `APPLE_REVIEW_NOTES.md`
- [ ] Build uploaded via TestFlight, internally tested

### Play Console
- [ ] Internal testing track tested by at least 1 reviewer
- [ ] Data safety form completed
- [ ] Content rating questionnaire completed
- [ ] Target audience + content questionnaire completed
- [ ] App access (whether parts of the app are gated by login — answer: No)
- [ ] Ads questionnaire — answer: No, this app does not contain ads

---

## Naming notes

**Always use "Sky Score" — never "London Flight Path Map"** in any consumer-facing surface. The latter is the legacy GitHub project name; the consumer brand is Sky Score.

The "Sky Score Radar" prototype (3D view) is currently a sister product but planned to merge into the main app long-term. Don't list Radar as a separate app.
