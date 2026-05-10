# Apple App Review Notes

## What this file is

Documentation and rejection-counter-arguments for App Store reviewer interactions. The single most important piece of copy in the whole submission process — Apple reviewers spend ~2 minutes per app, and proactively answering their objections moves you from a likely rejection to a likely first-pass approval.

---

## Canonical text lives in fastlane metadata

As of Wave 13.8.5, the verbatim review-notes text lives at:

```
mobile/fastlane/metadata/ios/review_information/notes.txt
```

That file is auto-pushed to App Store Connect by `bundle exec fastlane ios metadata_only` and `submit_for_review`. You no longer need to copy-paste manually before submission.

To update the text: edit `notes.txt`, then run `bundle exec fastlane ios metadata_only` from `mobile/`. The rejection-counter-argument section below remains here as Markdown documentation because it's never sent to Apple — it's runbook content for *you* when reading a rejection email.

---

## Copy (mirror of the auto-pushed file, kept for context)

```
Hi Apple Review Team,

Thanks for taking the time to review Sky Score. A few notes that might help:

1. WHAT THE APP DOES

Sky Score is a UK property data tool that gives postcode-level scores on aircraft noise, affordability, growth, and overall livability. The data is sourced from public datasets (DEFRA Strategic Noise Maps, HM Land Registry, EPC certificates, NHS/TfL, Ministry of Housing data) under the Open Government Licence v3.0.

The user value is letting people see noise and livability data that listings sites have a structural reason to hide — the data is public but it's not surfaced anywhere consumer-friendly.

2. SECTION 4.2 — MINIMUM FUNCTIONALITY

Sky Score is more than a website wrapper. The native app provides a feature that the web version cannot deliver as effectively:

   • "Score where I am" button — uses the device's GPS via CoreLocation
     (through @capacitor/geolocation) to identify the user's current
     UK postcode and return an instant noise+livability score for their
     exact location. This is meaningfully different from typing a
     postcode into the web form, because users frequently want a
     score for "here, right now" — for example when viewing a flat
     in person, walking through a neighbourhood, or visiting a
     property. The native GPS path makes that one tap; the web path
     requires the user to know their postcode first.

   • Native splash screen, status bar styling, and standalone display —
     gives the experience native ergonomics rather than browser chrome.

   • Native share sheet integration via @capacitor/share — users can
     share a score using the OS share sheet rather than copy-paste.

3. NO LOGIN REQUIRED

The app does not require an account. All features are immediately
accessible. Demo credentials are not needed — please tap any feature
freely.

4. LOCATION PERMISSION

The "Score where I am" feature requests "When in Use" location access.
The location is sent to api.postcodes.io (a free UK government postcode
lookup service operated under the Open Government Licence) to identify
the nearest postcode, then discarded. We do not store, log, or share
location data anywhere. If the user denies the permission, the rest of
the app continues to function normally — they can still search for
postcodes manually.

5. DATA + PRIVACY

The full privacy policy is at https://skyscore.co.uk/privacy. Key points:
- No accounts, no email collection, no tracking IDs
- Anonymous analytics via GoatCounter (privacy-respecting, no cookies)
- All API calls go to skyscore.co.uk's own AWS API Gateway, plus
  api.postcodes.io for postcode lookups
- No third-party SDKs for advertising, analytics, or tracking

6. AGE RATING

The app contains no age-restricted content. We've completed the
questionnaire as 4+ / suitable for all ages.

7. CONTACT

If you have any questions or need clarification:
- Email: support@skyscore.co.uk
- Web: https://skyscore.co.uk/

Thanks again for the review.

— Bilal Khizar
   Sky Score
```

---

## If Apple rejects

The most common Section 4.2 rejection language is:

> *"Your app provides a limited user experience as it is not sufficiently different from a mobile browsing experience..."*

Standard counter-arguments to escalate, in order of strength:

1. **GPS is native-only** — Web Geolocation API is permissioned per-origin per-session, requires HTTPS, and is significantly less reliable than the native CoreLocation API. Specifically, Safari on iOS requires the user to grant permission per Safari origin, every time. The native app remembers the permission and uses true CoreLocation accuracy. Cite specific use cases where native GPS matters: viewing flats in person, evaluating a neighbourhood mid-walk.

2. **Standalone window experience** — Without native, the user can install as PWA but the install rate is materially lower (Apple's own data on PWA installs vs App Store apps). App Store presence makes the tool discoverable to users who would never type a URL into Safari.

3. **OS-level integrations not available to PWAs** — Native share sheet, status bar theming, splash screen branding. These are all explicit native-API integrations.

4. **User-confirmed value** — If you have any user feedback / install metrics from the PWA showing demand, attach screenshots. "100 users have installed the PWA already" is more persuasive than design arguments.

5. **Updates from competitors** — Apple has approved comparable property/data apps that wrap web functionality (Sprift, Hometrack consumer apps, etc.). Reference these by name as evidence the category is acceptable.

If still rejected, ask for an Apple Developer call. They often reverse decisions when explained with the user-value framing.

---

## Don't include in the review notes

- Apologies (sounds defensive, weakens position)
- Long history of why the app was built
- Mentions of other rejected apps (don't put yourself in that bucket)
- Hackathon context (Apple reviewers are looking for shippable products, not student projects)
- Promises of future features (review based on what's there *now*, not what might come)
