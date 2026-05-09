# Codemagic setup for Sky Score

The `codemagic.yaml` at the repo root defines two workflows (`ios-workflow`, `android-workflow`). This guide covers the **dashboard tasks** — the secrets and integrations Codemagic needs that can't live in the yaml file.

Do these once; subsequent builds just push code and tap "Start new build" in the Codemagic UI.

---

## 1. Connect the repo

1. Sign in at [codemagic.io](https://codemagic.io)
2. **Add application** → choose GitHub → pick `billkhiz-bit/london-flight-path-map`
3. Codemagic auto-detects `codemagic.yaml` at root. You should see both `ios-workflow` and `android-workflow` listed in the left sidebar.

---

## 2. iOS: App Store Connect integration

This lets Codemagic auto-sign builds and upload to TestFlight.

1. Codemagic dashboard → **Teams** → **Integrations** → **App Store Connect**
2. **Generate API key** in App Store Connect → Users and Access → Keys → `+` (Codemagic walks you through it)
3. Upload the `.p8` private key to Codemagic, paste the Key ID and Issuer ID
4. Name the integration `codemagic_asc` (matches the yaml's `integrations: app_store_connect: codemagic_asc`)
5. Select your team

After this, the iOS workflow's `ios_signing` block will automatically fetch certs and provisioning profiles for `uk.co.skyscore.app`. Codemagic creates them if they don't exist yet.

---

## 3. Android: keystore + Play Console service account

### 3a. Generate the Android keystore (one-off, on this machine)

```bash
keytool -genkey -v -keystore sky-score-release.jks \
  -keyalg RSA -keysize 2048 -validity 10000 -alias sky-score
```

You'll be prompted for a keystore password, key password, and identity info. **Save these — you'll need them in step 3b and you cannot regenerate them later** (Play Store binds the app identity to this keystore for the lifetime of the listing).

### 3b. Upload to Codemagic

1. Dashboard → **Teams** → **Code signing identities** → **Android keystores** → **Add keystore**
2. Reference name: `sky_score_keystore` (matches yaml's `android_signing: - sky_score_keystore`)
3. Upload `sky-score-release.jks`, paste keystore password, key password, key alias `sky-score`

### 3c. Google Play service account

This lets Codemagic upload AABs to the Play Console.

1. Play Console → **Setup** → **API access** → **Create new service account** (sends you to Google Cloud)
2. Google Cloud → IAM → Service accounts → create with Project Editor + Service Account User roles
3. Generate JSON key, download
4. Back in Play Console → grant the service account access (Releases tab → All apps → Account permissions)
5. Codemagic dashboard → **Teams** → **Environment variables** → **Add group** named `google_play_credentials`
6. Add variable `GCLOUD_SERVICE_ACCOUNT_CREDENTIALS`, paste the JSON contents, mark as **Secure**

---

## 4. First build

1. In Codemagic dashboard, click `android-workflow` → **Start new build** → master branch
2. Watch the log. First build takes ~10 min.
3. Output: an `.aab` artifact downloadable from the build page, automatically uploaded to Play Console internal track if `publishing.google_play` succeeded.
4. Same for `ios-workflow` — output is `.ipa`, uploaded to TestFlight.

---

## 5. App Store / Play Store listings

Codemagic publishes the binaries; you still need to fill out the **store listings** manually:

**App Store Connect** ([appstoreconnect.apple.com](https://appstoreconnect.apple.com)):
- App name: `Sky Score`
- Bundle ID: `uk.co.skyscore.app` (must match the yaml)
- Category: Productivity / Reference
- Description, keywords, support URL (skyscore.co.uk)
- Screenshots: 6.7" iPhone (1290×2796), 6.5" iPhone (1242×2688), 12.9" iPad (2048×2732)
- Privacy policy URL (required)
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

## 6. Apple Section 4.2 — surviving the review

Apple frequently rejects apps that look like web wrappers. Sky Score's defence:

> **"Score where I am right now"** — uses native GPS via @capacitor/geolocation to identify the user's current postcode and return a noise/livability score. This is a meaningful use of device hardware that browsers (Safari) cannot replicate as cleanly, and provides ongoing value to users who walk between locations.

Mention this verbatim in the App Review notes field. Add a screenshot showing the locate-me button being tapped → results appearing.

If rejected: tighten the explanation, add additional native features (background notifications, native share), resubmit. Most apps clear review on the second attempt.

---

## 7. Update cycle (after first ship)

For minor web changes (CSS, JS, copy):
1. Edit `index.html`, deploy to S3 + CloudFront *as before* — that ships the PWA / web changes
2. To ship the change to native users too: trigger a Codemagic build for the affected platform
3. Codemagic uploads to TestFlight + Play Console internal track
4. Promote to production via App Store Connect / Play Console

For native config changes (new plugin, app id, signing): edit `mobile/capacitor.config.ts` or `codemagic.yaml`, commit, trigger build.

The native shell is essentially a thin wrapper — most updates are web-only and don't need a binary release. Plan to release a binary every 2–4 weeks at most to keep both stores fresh; more often than that is rarely worth the review-cycle cost.
