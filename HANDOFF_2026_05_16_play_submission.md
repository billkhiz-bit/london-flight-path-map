# HANDOFF: Sky Score Android v1.0 → Play Console — 2026-05-16 EOD

> **Pickup point** for the next session. Created end-of-day 2026-05-16 once the full Android pipeline (keystore → signed AAB → screenshots → feature graphic) was built locally + committed. Bill pauses here before opening Play Console. Delete this file once Sky Score Android v1.0 is live on Play Store.

## Where you are right now

Today's session shipped two parallel arcs:

1. **iOS v1.0.1 submitted to Apple for review** (Wave 13.18.1, ~14:30 BST). Build 19 of Sky Score iOS is in Apple's review queue with the orange radar icon and the persisted-cert pipeline. Awaiting verdict 24–72h. See `HANDOFF_2026_05_14_icon_ship.md` for the iOS arc's forensic trail.

2. **Android pipeline established** (Wave 13.19, ~15:50 BST). First-ever signed Sky Score AAB built locally on Windows via Android Studio's JDK + gradle. Ready for Play Console upload. **This handoff covers Android only.**

The Android shipping path is now end-to-end automatable: keystore generated, `build.gradle` wired for env-var-driven signing, gradle `bundleRelease` produces a signed AAB, screenshots + feature graphic auto-rendered via Playwright. Three commits today on the Android side (`c136e61`, `bc11bb7`, `301ec8f`).

## What's ready locally (not yet on Play)

| Artefact | Path |
|---|---|
| Upload keystore | `C:\Users\bilal\.keystores\sky-score-release.jks` (2.7 KB) |
| **Keystore credentials (TO DELETE after step 1 below)** | `C:\Users\bilal\.keystores\sky-score-credentials.txt` (724 bytes, plaintext) |
| Signed AAB (3.6 MB, 9.7 MB uncompressed) | `C:\Users\bilal\OneDrive\Desktop\london-flight-path-map\mobile\android\app\build\outputs\bundle\release\app-release.aab` |
| Phone screenshots (3 × 1080×1920) | `mobile/fastlane/metadata/android/en-GB/images/phoneScreenshots/` |
| Feature graphic (1024×500) | `mobile/fastlane/metadata/android/en-GB/images/featureGraphic/featureGraphic.png` |
| Metadata (title, short, full, changelog) | `mobile/fastlane/metadata/android/en-GB/*.txt + changelogs/default.txt` |
| Privacy policy URL (Play requires it) | `https://skyscore.co.uk/privacy` — HTTP 200 verified |

**Upload-key SHA-256** (memorise / save):
```
A5:53:4A:8F:91:54:37:D6:2E:6C:72:D7:AE:F6:1B:66:B3:4D:1D:84:E1:13:8C:1A:51:8C:6C:B6:52:22:50:AB
```

If Play App Signing is enabled on first upload (recommended), this upload-key fingerprint will NOT be the one used for Android App Links. Play Console generates a separate app-signing-key fingerprint after upload — find at Play Console → Setup → App integrity → App signing.

## What to do FIRST when you return

### 1. Save the keystore password, then delete the credentials file

Critical — `sky-score-credentials.txt` is plaintext on disk and contains the 28-char random password.

```bash
# Open in Notepad
notepad "C:\Users\bilal\.keystores\sky-score-credentials.txt"

# Copy the "Store password" line value into your password manager (Bitwarden)
# with tag "Sky Score Android keystore"

# Then delete:
rm "C:\Users\bilal\.keystores\sky-score-credentials.txt"
```

This was deliberately left for you to confirm — destructive secret ops need explicit confirmation. Future Claude sessions will see the file and remind you again if you forget.

### 2. Back up the keystore to encrypted storage

Copy `sky-score-release.jks` to a 1Password attachment or encrypted USB. **If you lose this without Play App Signing enabled, you'd have to publish Sky Score under a new package name (disaster).** Play App Signing (step 5 below) is the insurance.

### 3. Create the Play Console app record

https://play.google.com/console → **Create app**:

- App name: `Sky Score: postcode noise data`
- Default language: **English (United Kingdom)**
- App or game: **App**
- Free or paid: **Free**
- Declarations: accept Play Developer Programme Policies + US export laws

Same flow as Noor; you've done this before.

### 4. Upload the AAB to Internal testing track

Sky Score app → **Testing → Internal testing → Create new release**.

- Drag-drop `app-release.aab` from the path above (Windows path: `C:\Users\bilal\OneDrive\Desktop\london-flight-path-map\mobile\android\app\build\outputs\bundle\release\app-release.aab`)
- Release name: auto-populated from the build (will say `1.0 (1)` since `versionCode 1` / `versionName "1.0"` per `build.gradle`)
- Release notes: copy from `mobile/fastlane/metadata/android/en-GB/changelogs/default.txt`

### 5. Enable Play App Signing when prompted

The Internal-track upload wizard will offer Play App Signing. **Tick the box, accept Google's terms.** This is non-negotiable:
- If you lose the `.jks` without App Signing enabled: Sky Score is published forever under a different package name. Disaster.
- With App Signing enabled: Google can reset the upload key for you on request.

### 6. Smoke-test the build on your phone

After internal release rolls out (~5 min), Play Console gives you an opt-in link (Testing → Internal testing → Testers → Copy link). Open it on your Android phone, opt in, install Sky Score from Play, launch it:

- Confirm app icon shows the orange radar (NOT the placeholder cyan-X)
- Confirm map loads
- Confirm "Score where I am" prompts for location permission
- Confirm a postcode search works (try `SW1A 1AA`)

If anything's broken, fix locally, run `npm run build:android`, rebuild AAB, replace internal release. Don't promote to production with a broken internal build.

### 7. Fill the paperwork (Setup section in Play Console)

These are required before Production rollout:

- **App content → Privacy policy** → `https://skyscore.co.uk/privacy`
- **App content → Ads** → No, app does not contain ads
- **App content → App access** → All functionality is available without restrictions (no login)
- **App content → Content rating** → Run the questionnaire, all "No" → **PEGI 3**
- **App content → Target audience and content** → Target age groups: 18+ (or 13+ if you want to include teenagers; either is honest for a property data app). Children: No.
- **App content → News apps** → No (Sky Score isn't a news app)
- **App content → COVID-19 contact tracing and status apps** → No
- **App content → Government apps** → No
- **App content → Financial features** → None (Sky Score isn't a financial app per Google's narrow definition; property data is informational, not financial)
- **App content → Health features** → None
- **App content → Data safety** form is the longest. Per `mobile/STORE_LISTINGS.md`:
  - **Approximate location** — Collected, Optional, Not shared (for "Score where I am")
  - **Precise location** — Collected, Optional, Not shared (same purpose, higher accuracy)
  - **App activity** — Collected, Not shared (GoatCounter analytics; no cookies, no tracking IDs)
  - Everything else: NOT collected
- **Store presence → Main store listing** (paste from `mobile/fastlane/metadata/android/en-GB/*.txt`):
  - App name: `Sky Score: postcode noise data` (50 char limit)
  - Short description: `Independent UK postcode noise + livability data. Score where you are.` (80 char limit)
  - Full description: paste `full_description.txt`
- **Store presence → Store listing → Graphics**:
  - App icon (512×512): Play Console auto-generates from the AAB
  - Feature graphic (1024×500): upload from `mobile/fastlane/metadata/android/en-GB/images/featureGraphic/featureGraphic.png`
  - Phone screenshots: upload all 3 from `mobile/fastlane/metadata/android/en-GB/images/phoneScreenshots/`
- **Store presence → Store settings** → App category: Tools (or House & Home as alt); Tags: Reference, Lifestyle, Productivity
- **Store presence → Languages and translations** → Default: en-GB; no other locales for v1.0

### 8. Promote Internal → Production + Submit for review

Once the paperwork shows all green ticks and you've smoke-tested:

**Release → Production → Create new release** → reuse the same AAB from internal track (Play offers to "Add from library"). Don't re-upload — use the same binary so Internal and Production are bit-identical.

- Release notes: same as internal (copy from `changelogs/default.txt`)
- Staged rollout %: 5% to start (defensive — if a bug surfaces, only 5% of installs hit it; ramp up to 100% over 24–48h once you're confident)
- **Save → Review release → Start rollout to production**

Google's review window: typically <24h, often <4h. Email arrives in your Gmail when approved (or rejected with reasons).

## Wave history (for forensic continuity, latest first)

| Wave | Commit | What |
|---|---|---|
| 13.19.2 | `301ec8f` | npm scripts for screenshot + feature-graphic regeneration |
| 13.19.1 | `bc11bb7` | Echo docs + screenshot install-prompt hide |
| 13.19 | `c136e61` | Android Play Store prep — full signed-AAB pipeline (keystore + build.gradle + AAB + screenshots + feature graphic) |
| 13.18.2 | `0bd8c48` | Echo iOS v1.0.1 submission across in-repo docs |
| 13.18.1 | `9a4a8fc` | Log CERT_PRIVATE_KEY length before validating (iOS) |
| 13.18 | `7e8ba42` | CERT_PRIVATE_KEY → raw PEM (iOS) |
| 13.17.1 | `c2aad10` | Flag iOS HANDOFF cert section as superseded |
| 13.17 | `4c0355a` | Persist CERT_PRIVATE_KEY across builds (iOS) |

## Memory updates

Out-of-repo, in `~/.claude/projects/.../memory/`:

- `project_android_keystore.md` (new) — keystore path, alias, SHA-256, env vars, recovery procedure, Play App Signing dependency
- `feedback_codemagic_personal_account_signing.md` — extended with dashboard Edit-save quirk + final iOS fingerprints (irrelevant to Android but the cross-app lessons sit here)
- `feedback_codemagic_no_auto_trigger.md` — irrelevant to Android (no Codemagic for Android) but documented for iOS post-v1.0.1 follow-up

## 90-day roadmap echo

`C:\Users\bilal\OneDrive\Desktop\90_DAY_ROADMAP.md` → Day 61 (May 16) extended to cover both iOS submission + Android pipeline + cross-app dividend (the env-var-driven signing pattern is reusable for Noor v2 / Siraj / any future Android app from this user account).

## What I deliberately did NOT do

- **Did not delete `sky-score-credentials.txt`** — destructive secret op, waits for you to confirm you've saved the password
- **Did not fix Play Store screenshots 4–5** — layer toggle bar collapses behind a menu at 360-dp wide; that's the v1.1 mobile UX issue per `memory/project_mobile_ux_redesign_v1_1.md`. 3 screenshots meets Play's 2-frame minimum
- **Did not fill `.well-known/assetlinks.json`** — will be Play App Signing's key fingerprint, not the upload key; fill after first Play upload + App Signing key generation, or defer Android App Links to v1.1
- **Did not add Codemagic auto-trigger** — task #4 in the task list; deferred until Apple approves v1.0.1 (don't risk a yaml typo mid-review)
- **Did not set up fastlane supply lane** — auto-uploading metadata + AAB via Play Developer API requires a Play service account JSON you'd configure once; manual upload is faster for a single-app first ship
- **Did not test the AAB on an emulator** — no AVD configured; bundletool + adb install adds 20 min for limited extra confidence over the `jarsigner -verify` pass already done

## Time accounting

- ~5 min: state of play + Android Studio install confirmation
- ~5 min: npm run sync + build:assets (148 Android icon variants)
- ~10 min: keystore + credentials + build.gradle env-var signing wiring
- ~3 min: gradle bundleRelease (first-run, downloads dependencies)
- ~5 min: jarsigner verify + AAB inspection
- ~5 min: Playwright screenshot generator (frames 1-3 succeed, 4-5 timeout)
- ~5 min: PWA install-prompt hide fix + re-generate
- ~3 min: Playwright feature graphic generator
- ~5 min: echo-work across repo docs (README, ROADMAP, ANDROID_BUILD, RELEASE_CHECKLIST)
- ~5 min: memory + 90-day echoes
- ~5 min: this handoff doc

**Total Android-side: ~50 min** of automation, leaving Bill with ~30–45 min of Play Console paperwork + a 5-min smoke test. Apple + Google verdicts both expected within 24–72h.
