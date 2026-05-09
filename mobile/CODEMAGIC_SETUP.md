# Codemagic setup for Sky Score (iOS only)

The `codemagic.yaml` at the repo root defines a single workflow (`ios-workflow`). Codemagic only handles iOS for Sky Score, mirroring the Noor pattern: cloud Mac is essential because there's no local Mac, but Android builds locally on Windows via Android Studio (see [`ANDROID_BUILD.md`](./ANDROID_BUILD.md)).

This guide covers the **dashboard tasks** — the secrets and integrations Codemagic needs that can't live in the yaml file. Do these once; subsequent iOS builds just push code and tap "Start new build" in the Codemagic UI.

---

## 1. Connect the repo

1. Sign in at [codemagic.io](https://codemagic.io)
2. **Add application** → choose GitHub → pick `billkhiz-bit/london-flight-path-map`
3. Codemagic auto-detects `codemagic.yaml` at root. You should see `ios-workflow` listed in the left sidebar.

---

## 2. App Store Connect integration

This lets Codemagic auto-sign builds and upload to TestFlight.

1. Codemagic dashboard → **Teams** → **Integrations** → **App Store Connect**
2. **Generate API key** in App Store Connect → Users and Access → Keys → `+` (Codemagic walks you through it)
3. Upload the `.p8` private key to Codemagic, paste the Key ID and Issuer ID
4. Name the integration `codemagic_asc` (matches the yaml's `integrations: app_store_connect: codemagic_asc`)
5. Select your team

After this, the iOS workflow's `ios_signing` block automatically fetches certs and provisioning profiles for `uk.co.skyscore.app`. Codemagic creates them if they don't exist yet.

---

## 3. Asset generation (icons + splash)

The icon and splash sources live as SVGs at `mobile/assets/`:
- `logo.svg` (full-bleed icon, 1024×1024)
- `icon-foreground.svg` + `icon-background.svg` (Android adaptive icon — used for the local Android build)
- `splash.svg` + `splash-dark.svg` (light + dark splash, 2732×2732)

These are passed to `@capacitor/assets`, which generates 130+ platform-specific PNG variants (every iOS size, Android density variants, PWA icons, light + dark splash for landscape and portrait). The `ios-workflow` runs this as a build step automatically; locally:

```bash
cd mobile
npm run build:assets   # generates icons + splash for all platforms
```

To **change the icon design**, edit the SVGs in `mobile/assets/` and rerun `npm run build:assets`. Keep the inner safe zone (60% of canvas) for the airplane silhouette so Android's adaptive shape masks don't clip it.

---

## 4. First iOS build

1. In Codemagic dashboard, click `ios-workflow` → **Start new build** → master branch
2. Watch the log. First build takes ~12 min.
3. Output: an `.ipa` artefact downloadable from the build page, automatically uploaded to TestFlight if the App Store Connect integration succeeded.
4. From TestFlight, install on your iPhone for smoke testing before submitting for App Store review.

---

## 5. Android (separate workflow, local)

Android does NOT use Codemagic. See [`ANDROID_BUILD.md`](./ANDROID_BUILD.md) for the Android Studio + gradle process. Quick summary: open `mobile/android/` in Android Studio, Build → Generate Signed Bundle / APK → AAB → upload to Play Console manually.

---

## 6. App Store / Play Store listings

Codemagic publishes the iOS binary; you still need to fill out the **store listings** manually. Ready-to-paste copy lives in [`STORE_LISTINGS.md`](./STORE_LISTINGS.md).

**App Store Connect** ([appstoreconnect.apple.com](https://appstoreconnect.apple.com)):
- App name: `Sky Score`
- Bundle ID: `uk.co.skyscore.app` (must match the yaml)
- Category: Productivity / Reference
- Description, keywords, support URL (skyscore.co.uk)
- Screenshots: 6.7" iPhone (1290×2796), 6.5" iPhone (1242×2688), 12.9" iPad (2048×2732)
- Privacy policy URL (required) — `https://skyscore.co.uk/privacy`
- Age rating questionnaire

**Play Console** ([play.google.com/console](https://play.google.com/console)):
- App name: `Sky Score`
- Package name: `uk.co.skyscore.app` (must match)
- Category: Tools or House & Home
- Short + full description
- Screenshots: phone (16:9 or 9:16 minimum 320px), tablet (optional)
- Feature graphic 1024×500
- Content rating questionnaire
- Target audience + content
- Data safety form

---

## 7. Apple Section 4.2 — surviving the review

Apple frequently rejects apps that look like web wrappers. Sky Score's defence:

> **"Score where I am right now"** — uses native GPS via @capacitor/geolocation to identify the user's current postcode and return a noise/livability score. This is a meaningful use of device hardware that browsers (Safari) cannot replicate as cleanly, and provides ongoing value to users who walk between locations.

Mention this verbatim in the App Review notes field. Add a screenshot showing the locate-me button being tapped → results appearing.

If rejected: tighten the explanation, add additional native features (background notifications, native share), resubmit. Most apps clear review on the second attempt.

Full review notes (paste into App Store Connect → App Review → Notes): [`APPLE_REVIEW_NOTES.md`](./APPLE_REVIEW_NOTES.md).

---

## 8. Update cycle (after first ship)

For minor web changes (CSS, JS, copy):
1. Edit `index.html`, deploy to S3 + CloudFront *as before* — that ships the PWA / web changes
2. To ship the change to native users too:
   - **iOS**: trigger a Codemagic build for `ios-workflow`
   - **Android**: rebuild locally per `ANDROID_BUILD.md`, upload AAB to Play Console
3. iOS auto-uploads to TestFlight; Android upload is manual
4. Promote to production via App Store Connect / Play Console

For native config changes (new plugin, app id, signing): edit `mobile/capacitor.config.ts` or `codemagic.yaml`, commit, trigger build (iOS) or rebuild locally (Android).

The native shell is essentially a thin wrapper — most updates are web-only and don't need a binary release. Plan to release a binary every 2–4 weeks at most to keep both stores fresh; more often than that is rarely worth the review-cycle cost.
