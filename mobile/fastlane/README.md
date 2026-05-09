# fastlane configuration for Sky Score

Two-platform fastlane setup. Read this before running any `fastlane` or `make` target that touches the App Store / Play Console.

---

## Setup (one-off, per machine)

### Ruby

fastlane is a Ruby gem; you need Ruby on your `PATH`.

**Windows**:
```powershell
winget install RubyInstallerTeam.RubyWithDevKit.3.3
```

**macOS / Linux**: usually pre-installed; if not, `brew install ruby` or `apt install ruby-full`.

### Bundler + fastlane

```bash
cd mobile
gem install bundler
bundle install     # reads Gemfile, installs fastlane v2.222+
```

### Secrets — env vars

Add these to your shell profile (`~/.bashrc`, PowerShell `$PROFILE`, or a `.env` loaded by the shell):

```bash
# ---- iOS / App Store Connect ----
export ASC_KEY_ID="ABCD1234EF"                                # 10-char alphanumeric
export ASC_ISSUER_ID="abc12345-1234-1234-1234-1234567890ab"   # UUID
export ASC_KEY_FILE_PATH="$HOME/.asc-keys/AuthKey_ABCD1234EF.p8"

# ---- Android / Play Console ----
export PLAY_CONSOLE_JSON_KEY="$HOME/.gcloud/sky-score-play-console.json"
```

**How to get them**:

- **App Store Connect API key** (`.p8` + Key ID + Issuer ID): App Store Connect → Users and Access → Keys → `+` → Generate API Key. Download the `.p8` (you can only download it once — save it carefully). The Key ID is in the table; the Issuer ID is at the top of the Keys page.
- **Play Console service account JSON**: Play Console → Setup → API access → Create new service account (sends you to Google Cloud) → download JSON key → return to Play Console → grant the service account access via Releases tab → All apps → Account permissions.

**Never commit any of these files.** All paths above point outside the repo.

---

## Lanes

### Android

```bash
cd mobile
bundle exec fastlane android deploy_internal       # AAB → Play Console internal testing
bundle exec fastlane android deploy_alpha          # AAB → closed alpha
bundle exec fastlane android deploy_production     # AAB → production at 5% staged rollout
bundle exec fastlane android promote_to_production # promote internal → production
bundle exec fastlane android metadata_only         # listing description / keywords only, no AAB
```

Or via the repo-root Makefile:
```bash
make android-upload     # = deploy_internal
make android-promote    # = promote_to_production
```

The lane reads the AAB from `mobile/android/app/build/outputs/bundle/release/app-release.aab` by default. Override with `ANDROID_AAB_PATH` env var if you've built it elsewhere.

### iOS

```bash
cd mobile
bundle exec fastlane ios submit_for_review    # Submit latest TestFlight build for App Store review
bundle exec fastlane ios metadata_only        # Update App Store description / keywords only
bundle exec fastlane ios screenshots_only     # Upload screenshots
```

Or:
```bash
make ios-submit
```

**Important about iOS**: Codemagic builds the .ipa and auto-uploads to TestFlight (configured in `codemagic.yaml`). fastlane never touches the binary — it only handles App Store Connect metadata + the submit-for-review action. Ordering of a release is:

1. `git push origin master` → Codemagic ios-workflow builds + uploads to TestFlight
2. (manual) Smoke test on iPhone via TestFlight
3. `make ios-submit` → fastlane deliver pushes metadata + flags the build for App Store review

---

## Metadata structure

```
fastlane/
  metadata/
    android/
      en-GB/
        title.txt              max 30 chars
        short_description.txt  max 80 chars
        full_description.txt   max 4000 chars
        changelogs/
          default.txt          max 500 chars (release notes)
    ios/
      en-GB/
        name.txt               max 30 chars
        subtitle.txt           max 30 chars
        keywords.txt           max 100 chars total, comma-separated
        description.txt        max 4000 chars
        promotional_text.txt   max 170 chars (editable post-release)
        release_notes.txt      max 4000 chars (per build)
        marketing_url.txt
        support_url.txt
        privacy_url.txt
```

Edit any of these and run the matching `metadata_only` lane to push the change without re-uploading the binary. Useful for typo fixes or copy iterations between binary releases.

---

## Screenshots (manual the first time)

Both stores require platform-specific screenshot sets at exact sizes:

- **App Store** (iPhone 6.7": 1290×2796, iPhone 6.5": 1242×2688, iPad 12.9": 2048×2732)
- **Play Store** (phone: min 320px on the short side, 16:9 or 9:16; tablet optional)

Take 4-6 per device via TestFlight install + iOS Screenshot capture, or via Android emulator + adb screencap. Drop them in:

```
fastlane/screenshots/
  ios/
    6.7-iPhone/
      01-search.png
      02-result.png
      ...
  android/
    phone/
      ...
```

`fastlane deliver` and `fastlane supply` upload them automatically when the relevant screenshot directories exist. The screenshots/ directory is gitignored — they're large binary files that don't belong in source control. Keep originals in cloud storage / backup.

---

## Troubleshooting

- **"App not found"** when running fastlane: the app must already exist in App Store Connect / Play Console with the matching bundle/package id (`uk.co.skyscore.app`). Create the listing in the web UI first; fastlane updates an existing listing, it doesn't create one.
- **"Authentication failed"** on iOS: API key may have rotated. Generate a new one in App Store Connect → Users and Access → Keys; update env vars.
- **"Service account does not have permission to access this application"** on Android: the service account JSON's email needs to be added in Play Console → Setup → API access → service account → Manage Play Console permissions. Grant at least "Release manager" role.
- **First-time `fastlane supply init` warns about no metadata**: that's fine; fastlane downloads what's currently in Play Console and writes it to `fastlane/metadata/android/en-US/`. Either delete that en-US directory and rely on en-GB, or copy en-GB content into en-US too if you want both locales.
