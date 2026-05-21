# Sky Score — Native Release Checklist

> **Status:** iOS v1.0 is **LIVE** on the App Store since 2026-05-20 (build 20, Wave 13.20 iPad fix) — apps.apple.com/gb/app/sky-score/id6768118116. So Section 0 (first-submission ASC prerequisites) is now **skip-able for iOS** — future iOS releases are updates that inherit those fields. Android is **not yet shipped**; its first Play Console upload still has its own one-time setup.

Run through this every time you trigger a Codemagic build that's intended for App Store / Play Store. About 10 minutes; catches the version-bump and config mistakes that cause Apple to reject or Play Console to refuse the upload.

---

## 0. First submission only — App Store Connect dashboard prerequisites

**Skip this section if Sky Score is already approved on the App Store** (i.e. v1.0 is live and you're shipping v1.x). This list is for the first submission *only*; updates inherit most of these.

The first submission for a new App Store app requires a cluster of dashboard fields that fastlane's `deliver` cannot push. Hitting `submit_for_review` before these are set produces a 25+ line error stream. Complete these BEFORE running fastlane:

- [ ] **TestFlight test info** at `<https://appstoreconnect.apple.com/apps/{id}/testflight/test-info>` — Feedback Email + Beta App Review contact (name, phone, email). Otherwise Codemagic's auto-submit-to-TestFlight-external step fails noisily on every build.
- [ ] **App Information**: Primary Category = `Utilities` or `Reference` (Reference is the better fit for Sky Score — data lookup tool); Content Rights Information = "Does not contain, show, or access third-party content".
- [ ] **Age Rating**: click through the 22-question questionnaire → answer **None** / **No** to all (Sky Score has no objectionable content). Result: **4+**.
- [ ] **Pricing and Availability**: pick **GBP 0 (Free)** → tick all territories → Confirm.
- [ ] **App Privacy** — two-step process:
  1. Click **Edit** → "Do you collect data?" → **Yes** → add data types:
     - **Precise Location** (Sky Score uses `enableHighAccuracy: true` per `index.html:2540`) → Not linked to user → Not for tracking → App Functionality only
     - **Product Interaction** (GoatCounter analytics) → Not linked to user → Not for tracking → Analytics only
  2. Click **Publish** at the top of the page. Greyed out until ALL data type entries have all 3 follow-ups answered.
- [ ] **MRDP (Model Reporting Rules for Digital Platforms)** at `<https://appstoreconnect.apple.com/business>` or via Agreements, Tax, and Banking — this form bundles the Personal Service Declaration that the submission error nominally complains about. For Sky Score: "Personal service?" = **No**; entity type = Individual / Sole Trader; tax country = UK; TIN = your 10-digit UTR; VAT = No. Required even for free apps with zero revenue.

**Why this isn't in the main checklist:** these fields are persistent across versions, so once they're set you never touch them again. But on submission #1 they all conspire to block.

---

## 1. Web parity check (does the bundled web match the live site?)

- [ ] Latest changes pushed to S3 + CloudFront and live at <https://skyscore.co.uk/>
- [ ] `mobile/scripts/copy-web.mjs` will pick up the latest `index.html`
- [ ] Local sanity: `cd mobile && npm run sync && npx cap open android` — app launches on emulator and behaves identically to the live web site

If web and native differ, the App Store user gets a different experience from the website user. Bad for trust, bad for support. Always sync.

---

## 2. Version bump

- [ ] Decide the new semantic version (e.g. 1.0.4 → 1.0.5 for a small change, 1.0.4 → 1.1.0 for a feature, 1.0.4 → 2.0.0 for a breaking change)
- [ ] `mobile/capacitor.config.ts` — no version field, this is set per platform below

For **Android (local Android Studio build, see `ANDROID_BUILD.md`)**:
- [ ] `mobile/android/app/build.gradle` — bump `versionCode` (integer, must strictly increase) AND `versionName` (semver string)
- [ ] You must do this manually for each release; no automation

For **iOS (Codemagic cloud build)**:
- [ ] Codemagic auto-bumps `CFBundleVersion` from `BUILD_NUMBER`; `CFBundleShortVersionString` is `"1.0.$BUILD_NUMBER"` (defined in `codemagic.yaml`)
- [ ] If you want a different version scheme (e.g. semantic), edit the yaml's "Set bundle id + version" step

The single most common Play Console rejection is **versionCode not strictly increasing**. Eyeball the gradle file before each Android release.

---

## 3. Native config review

- [ ] `mobile/capacitor.config.ts` — `appId` is unchanged (`uk.co.skyscore.app`). NEVER change this — Apple and Google use it as the immutable app identity
- [ ] No new permissions added to native projects without updating the privacy policy + listings
- [ ] Splash colours match the current web theme (currently `#e4e3e0` light, `#141414` dark)

---

## 4. Icons + splash

- [ ] If `mobile/assets/*.svg` was edited: run `cd mobile && npm run build:assets` locally to preview Android icons, eyeball at common densities (mdpi, xxhdpi)
- [ ] Codemagic regenerates these in cloud, so committing the regenerated PNGs in `android/app/src/main/res` is optional — but regenerating locally catches design errors before you wait 10 min for a cloud build

---

## 5. Pre-flight (web side)

- [ ] `cd /c/Users/bilal/projects/london-flight-path-map && npx html-validate index.html` clean
- [ ] `npm run lint` shows 0 errors (warnings OK)
- [ ] `cd backend && python -m pytest` passes
- [ ] If web changes touched API surface, run `node tests/api.test.mjs` against the live API

---

## 6. Build triggers

### iOS (Codemagic)

- [ ] Push changes to GitHub (`git push origin master`)
- [ ] Confirm Codemagic app's Environment Variables panel has the **`asc` group** with `APP_STORE_CONNECT_PRIVATE_KEY` (Secure, .p8 contents), `APP_STORE_CONNECT_KEY_IDENTIFIER`, `APP_STORE_CONNECT_ISSUER_ID` — these are mandatory; build fails immediately without them. See `mobile/CODEMAGIC_SETUP.md` § 3.
- [ ] In Codemagic UI, click `ios-workflow` → **Start new build** → master branch → wait ~12 min
- [ ] Build succeeded — `.ipa` artefact downloadable; auto-uploaded to TestFlight

If iOS fails, look in the Codemagic log:
- Apple signing: missing or expired provisioning profile → re-run the App Store Connect integration in Codemagic Teams → Integrations
- Web bundle missing files: `copy-web.mjs` exited with a `MISSING` warning → fix the parent web app, push again
- Pod install errors: `xcode: latest` may have rolled to a new version that broke a plugin → pin `xcode: 16.x` in `codemagic.yaml`

### Android (local Android Studio, see `ANDROID_BUILD.md`)

- [ ] `cd mobile && npm run sync && npm run build:assets`
- [ ] Bump `app/build.gradle` versionCode + versionName
- [ ] Build the AAB. **Option A (GUI):** Open `mobile/android/` in Android Studio → Build → Generate Signed Bundle / APK → AAB → release variant → output `app-release.aab`. Wizard prompts for keystore + password. **Option B (CLI, since Wave 13.19):** export `SKY_SCORE_KEYSTORE_PATH` + `SKY_SCORE_KEYSTORE_PASSWORD` env vars, then run `npm run build:android` from repo root (which wraps `./gradlew bundleRelease`; the `signingConfigs.release` block in `build.gradle` picks up the env vars). Output: `mobile/android/app/build/outputs/bundle/release/app-release.aab`.
- [ ] Upload AAB to Play Console manually (Production / Internal testing track)

If Android fails:
- "versionCode X already exists" → bump versionCode, retry
- "signature does not match the existing one" → using a different keystore than the original; only the FIRST keystore can ever sign this app. Recover from your safe copy
- Gradle sync failure → File → Invalidate Caches and Restart in Android Studio

---

## 7. Post-build smoke test

- [ ] **TestFlight (iOS)**: install the new build on your iPhone — verify the locate-me button works, the bottom sheet renders, the score loads
- [ ] **Play Console internal track (Android)**: after upload, opt your test device into the internal track at <https://play.google.com/apps/internaltest> with your test account, install, repeat the same checks

Don't promote to public release until the smoke test passes on at least one real device per platform.

---

## 8. Promote to production

**Android (Play Console):**
- [ ] Internal testing → Promote → Closed testing (optional) → Production
- [ ] Production rollout: start at 1–5% staged rollout, watch crash rates for 24h, scale up

**iOS (App Store Connect):**
- [ ] TestFlight build → Submit for App Store review (via `bundle exec fastlane ios submit_for_review` from `mobile/` — pushes metadata + notes + submits in one step)
- [ ] Review notes are auto-pushed from `mobile/fastlane/metadata/ios/review_information/notes.txt` — no manual paste needed (as of Wave 13.8.5)
- [ ] Wait 24–72h for Apple review
- [ ] If approved: schedule release (immediately or on a date)
- [ ] If rejected: re-read the rejection reason, prep counter-argument from `APPLE_REVIEW_NOTES.md` "If Apple rejects" section, resubmit

---

## 9. After release

- [ ] Add the new version to `CHANGELOG.md` (if you keep one)
- [ ] Update store listing "What's New" copy in `STORE_LISTINGS.md` for next time
- [ ] Tag the release in git: `git tag mobile-v1.0.X && git push --tags`
- [ ] Update `ROADMAP.md` if this release closes a roadmap item

---

## Cadence guidance

- **Web app** (skyscore.co.uk): deploy as often as you like — instant CloudFront invalidation, no review
- **Native binaries**: every 2–4 weeks at most. More often than that and the review-cycle cost (Apple's 1–3 day review per submission) outweighs the user value of staying perfectly in sync with the web
- **Critical bug fix native**: yes, ship a binary release outside the cadence; expedite via App Store Connect's "request expedited review" if needed
