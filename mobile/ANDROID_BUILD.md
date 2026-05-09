# Android build (local, via Android Studio)

Sky Score's Android binary is built **locally on your Windows machine**, not via Codemagic. The pattern is the same one used for Noor: open the Capacitor-generated `mobile/android/` project in Android Studio, generate a signed AAB through the IDE wizard, upload the AAB to Play Console manually.

iOS is the exception that needs cloud CI (Codemagic) because there's no local Mac. Android doesn't need it — gradle runs fine on Windows and the local feedback loop is faster than waiting for a cloud build.

---

## Prerequisites (one-off setup)

1. **Android Studio** installed: <https://developer.android.com/studio>
2. **Java JDK 17+** (Android Studio bundles its own; if you'd rather use the CLI without the IDE, you'll need a system-wide JDK)
3. **Keystore generated** per [`CODEMAGIC_SETUP.md` §3a](./CODEMAGIC_SETUP.md):
   ```bash
   keytool -genkey -v -keystore sky-score-release.jks \
     -keyalg RSA -keysize 2048 -validity 10000 -alias sky-score
   ```
   Save the keystore file somewhere safe **outside the repo** (it's a release credential, do not commit). Standard location: `~/.keystores/sky-score-release.jks`.

---

## Build the AAB (each release)

### Option A: Android Studio GUI (recommended for first release)

1. **Sync the web bundle into Android**:
   ```bash
   cd mobile
   npm run sync             # rebuilds www/ + cap sync into android/
   npm run build:assets     # regenerates icons + splash screens
   ```

2. **Open in Android Studio**:
   - File → Open → `mobile/android/`
   - Wait for Gradle sync to finish (first time: ~5 min while it downloads dependencies)

3. **Bump the version** (manual edit before each release):
   - Open `mobile/android/app/build.gradle`
   - Find the `defaultConfig` block; bump `versionCode` (integer, must strictly increase) AND `versionName` (semver string)
   - Example: `versionCode 4 → 5`, `versionName "1.0.4" → "1.0.5"`
   - **The most common Play Console rejection is versionCode not strictly increasing.** If you forget, Play will refuse the upload with a clear error.

4. **Generate signed AAB**:
   - Build → Generate Signed Bundle / APK
   - Choose **Android App Bundle** (NOT APK — Play Store requires AAB since 2021)
   - Click Next
   - Browse to your `sky-score-release.jks`, paste keystore password, alias `sky-score`, alias password
   - **Tick "Remember passwords"** if you want; the IDE encrypts them per-machine
   - Click Next
   - Choose **Build Variant: release**
   - Choose **Destination Folder** (default `mobile/android/app/release/` is fine)
   - Click Create
   - Wait ~2-3 min for Gradle to bundle, sign, and align
   - Output: `app-release.aab` in the destination folder

5. **Upload to Play Console**:
   - Go to <https://play.google.com/console>
   - Select Sky Score → Production / Internal testing track (whichever you're targeting)
   - Click **Create new release**
   - Drag-drop `app-release.aab` into the upload area
   - Wait for processing (~1-2 min)
   - Fill in the release notes
   - Click **Save** → **Review release** → **Start rollout**

### Option B: Gradle CLI (faster for repeat builds)

Once the keystore is set up and you're past the first build, the CLI path is faster:

1. **Configure signing once** in `mobile/android/app/build.gradle` (or via `~/.gradle/gradle.properties` if you prefer not to put creds in the repo):
   ```groovy
   android {
       signingConfigs {
           release {
               storeFile file(System.getenv("SKY_SCORE_KEYSTORE_PATH") ?: "/path/to/sky-score-release.jks")
               storePassword System.getenv("SKY_SCORE_KEYSTORE_PASSWORD")
               keyAlias "sky-score"
               keyPassword System.getenv("SKY_SCORE_KEY_PASSWORD")
           }
       }
       buildTypes {
           release {
               signingConfig signingConfigs.release
               // existing release config...
           }
       }
   }
   ```

2. **Set the env vars** (in PowerShell):
   ```powershell
   $env:SKY_SCORE_KEYSTORE_PATH = "C:\Users\bilal\.keystores\sky-score-release.jks"
   $env:SKY_SCORE_KEYSTORE_PASSWORD = "..."
   $env:SKY_SCORE_KEY_PASSWORD = "..."
   ```

3. **Bump version** in `app/build.gradle` as above.

4. **Build**:
   ```bash
   cd mobile
   npm run sync && npm run build:assets
   cd android
   ./gradlew bundleRelease
   ```

5. **Output**: `mobile/android/app/build/outputs/bundle/release/app-release.aab`

6. **Upload manually** to Play Console as in Option A step 5.

---

## Why local instead of Codemagic for Android

| | Local (Android Studio / gradle) | Codemagic (cloud) |
|---|---|---|
| Setup time (first release) | ~30 min (install IDE + first sync) | ~30 min (dashboard config + secrets) |
| Per-build time | ~2-3 min on a modern laptop | ~6-10 min queue + build + upload |
| Per-build cost | £0 | ~$0.10 in Codemagic build minutes (free tier covers most needs) |
| Feedback loop | Instant (run on local emulator) | Wait for cloud upload + Play Console processing |
| Requires extra hardware | No (Windows machine works) | No |
| iOS-style "must be cloud" constraint | No | No |
| Keystore in cloud | Stays local | Uploaded to Codemagic dashboard |

iOS only goes to Codemagic because there's no local Mac. Android doesn't have that constraint, and the local path is materially faster.

---

## Play Console: app signing key (one-off, first upload)

When you upload your **first** AAB to Play Console, Google offers **Play App Signing** — they generate a separate "app signing key" used for delivery to users, while you keep an "upload key" (your local keystore) for signing your uploads.

**Recommended: enable Play App Signing.** Benefits:
- If you ever lose the keystore, Google can reset the upload key (you can't reset the app signing key — losing it means you'd have to publish a new app under a new package name, which is a disaster)
- Smaller app downloads via Google's dynamic delivery
- No downside that affects this app

The first upload's wizard walks you through it. Tick the box, accept Google's app-signing terms, done.

---

## Linking Android App Links (deep linking)

After your first signed build, run this to get the SHA-256 fingerprint:

```bash
keytool -list -v -keystore sky-score-release.jks \
  -alias sky-score | grep "SHA256:"
```

Copy the colon-separated hex string and paste into `.well-known/assetlinks.json`, replacing the `REPLACE:WITH:KEYSTORE:SHA256:FINGERPRINT:WHEN:GENERATED` placeholder. Then deploy `.well-known/` per `OPERATIONS.md`.

If you enable Play App Signing, **use the Play App Signing key's SHA-256, not your upload key's**. You can find the Play App Signing fingerprint in Play Console → Setup → App integrity → App signing.

---

## When to Codemagic-ify Android later

If the manual Android Studio cycle starts feeling slow (e.g. you're shipping daily binaries), the existing `mobile/android/` Capacitor project is fully Codemagic-compatible — the deleted `android-workflow` from `codemagic.yaml` history is in commit `397c4cc` if you ever want to restore it. Adding it back means uploading the keystore + service account JSON to Codemagic's dashboard; ~1 hour of dashboard work.

For Sky Score's expected cadence (binary release every 2-4 weeks), local Android Studio is the right choice.
