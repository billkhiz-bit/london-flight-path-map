# Codemagic setup for Sky Score (iOS only)

The `codemagic.yaml` at the repo root defines a single workflow (`ios-workflow`). Codemagic only handles iOS for Sky Score, mirroring the Noor pattern: cloud Mac is essential because there's no local Mac, but Android builds locally on Windows via Android Studio (see [`ANDROID_BUILD.md`](./ANDROID_BUILD.md)).

This guide reflects the **actual working configuration as of Wave 13.8.14** (2026-05-10). The path here is the result of 12 iterations of debugging Codemagic's Personal Account signing model — read the gotchas section before reproducing on another app.

---

## Account type: Personal vs Team

**Personal Account** (what Sky Score uses):
- Single Apple Developer Portal "key pool" — multiple API keys stored together
- No named integrations; the `integrations.app_store_connect: <name>` yaml pattern doesn't resolve
- Pre-flight signing auto-picks from the pool with logic we can't observe or override
- **Use the env-var-based signing pattern in this doc**

**Team Account** (different setup, not covered here):
- Per-integration named credentials in Team Settings → Integrations
- Use the `integrations.app_store_connect: codemagic_asc` pattern with a matching named integration

If you have a Team Account, our yaml will need different wiring than what's documented below.

---

## 1. Connect the repo

1. Sign in at [codemagic.io](https://codemagic.io) using GitHub OAuth (same identity that owns `london-flight-path-map`)
2. **Apps** → **Add application** → **GitHub** → pick `billkhiz-bit/london-flight-path-map`
3. Project type: **Ionic** (Capacitor inherits Ionic's build pattern)
4. Codemagic auto-detects `codemagic.yaml` at root → finishes the wizard

You should see `Sky Score iOS` (the `name:` from the yaml) on your apps dashboard.

---

## 2. Apple Developer Portal — add the Sky Score Fastlane key to the pool

Sky Score uses a **separate API key from Noor's** to avoid scope conflicts. Generate it once in App Store Connect, then add to Codemagic.

### Generate the API key (one-off, at App Store Connect)

1. [appstoreconnect.apple.com](https://appstoreconnect.apple.com) → **Users and Access** → **Integrations** → **App Store Connect API**
2. Click **Generate API Key** (blue `+`)
3. Name: `Sky Score Fastlane` (or whatever — it's just for your reference)
4. Access role: **App Manager**
5. **Download the `.p8` file IMMEDIATELY** — Apple shows the download button only once. Save it to `C:\Users\bilal\OneDrive\Desktop\SkyScore\Secrets\AuthKey_<KeyID>.p8`
6. Note down the **Key ID** (10 chars, also embedded in the .p8 filename) and **Issuer ID** (UUID at the top of the page)

### Add the key to Codemagic's Developer Portal pool

1. Codemagic → **Personal Account Settings** → **Integrations**
2. Find **Apple Developer Portal** → **Manage keys** → **Add another key**
3. Fill in:
   - **Name**: `Sky Score Fastlane` (matches what you named it in ASC)
   - **Issuer ID**: from step above
   - **Key ID**: from step above
   - **API Key (.p8)**: upload the file from your Secrets folder

Green dot = authenticated. Don't delete the existing Noor key — it can coexist with Sky Score's.

---

## 3. App-level environment variables (THIS IS THE CRITICAL STEP)

Sky Score's signing bypasses Codemagic's pre-flight signing and uses explicit credentials passed via env vars. **Without these set, the build fails immediately at the signing step with "No matching profiles found".**

Codemagic dashboard → your **london-flight-path-map** app → **Environment variables** tab. Add four variables, all in a group called `asc`:

| Variable | Value | Secure? | Notes |
|---|---|---|---|
| `APP_STORE_CONNECT_PRIVATE_KEY` | full contents of the `.p8` file (paste PEM text including `-----BEGIN`/`-----END` lines) | ✅ Yes | This IS the ASC API secret |
| `APP_STORE_CONNECT_KEY_IDENTIFIER` | the 10-char Key ID (e.g. `J746LSWAPG`) | No | Public identifier |
| `APP_STORE_CONNECT_ISSUER_ID` | the UUID from the ASC API page | No | Public identifier, one per account |
| `CERT_PRIVATE_KEY` | raw multi-line RSA PEM (see below for how to generate; paste the whole `-----BEGIN/-----END` block, newlines included) | ✅ Yes | Persists the Distribution cert across builds — without this, every build creates a new cert and hits Apple's 2-cert Personal Account cap |

**Group name must be `asc`** — the yaml has `environment.groups: [asc]` which imports vars from this group. Variables in other groups (or no group) won't reach the build.

### Generating `CERT_PRIVATE_KEY` (one-off, then never again)

The codemagic.yaml's "Fetch signing files via ASC API" step writes this env var to `/tmp/cert_private_key.pem` on every build and passes it to `app-store-connect fetch-signing-files`. ASC sees the same public key every time, so it matches the existing Distribution cert and reuses it instead of creating a new one.

```bash
# 1. Generate a 2048-bit RSA private key (anywhere off-repo — e.g. your Desktop).
openssl genrsa -out cert_private_key.pem 2048

# 2. Open cert_private_key.pem in Notepad (or any plain-text editor).
#    The file is short — about 27 lines — and starts with:
#      -----BEGIN RSA PRIVATE KEY-----
#    and ends with:
#      -----END RSA PRIVATE KEY-----

# 3. Select all (Ctrl+A), copy (Ctrl+C).

# 4. Codemagic dashboard → App Settings → Environment Variables → 'asc' group
#    → CERT_PRIVATE_KEY → paste (Ctrl+V), tick Secure, Save.
#    Codemagic's textarea preserves the newlines between PEM lines — confirm
#    the saved value still shows multiple lines.

# 5. Delete the local cert_private_key.pem — the env var is now the persistence.
```

**Why raw PEM and not base64?** An earlier iteration (Wave 13.17) base64-encoded the key into the env var. The Git Bash → clip.exe → web textarea transfer corrupted some bytes silently, and the build failed at the openssl validation guard. Switching to raw PEM eliminates the encoding round-trip — same format Codemagic already handles successfully for `APP_STORE_CONNECT_PRIVATE_KEY`.

**Before the first build with this key**, revoke any orphaned Distribution certs at [developer.apple.com/account/resources/certificates/list](https://developer.apple.com/account/resources/certificates/list) so there's a free slot for the new persisted cert. (Personal Accounts cap at 2 Distribution certs.) After this first build, every subsequent build reuses the same cert — no more cap problems.

> 💡 The exact same env-var names are read by:
> - `app-store-connect fetch-signing-files` (signing setup script)
> - `app-store-connect publish` (TestFlight upload)
> - All other Codemagic CLI tools that need ASC API auth
>
> No flags or paths need editing — the CLI tools auto-detect these env vars.

---

## 4. Apple-side prerequisites

Before any build, these must exist on Apple's side:

| Item | Where | Notes |
|---|---|---|
| **Bundle ID** `uk.co.skyscore.app` | developer.apple.com → Identifiers | App IDs → App → Explicit → uncheck all capabilities |
| **App record** "Sky Score" | App Store Connect → My Apps → + → New App | Link to the Bundle ID above |
| **App Review Information saved** | App Store Connect → 1.0 Prepare for Submission | Required at least ONCE before fastlane lanes work (see fastlane gotchas memory) |
| **Distribution profile** | developer.apple.com → Profiles | `Sky Score App Store` — manually created once, the build script reuses |

The `app-store-connect fetch-signing-files --create` script step will auto-create the profile if missing, but having it pre-created makes the first build smoother.

---

## 5. First iOS build

1. Codemagic dashboard → **Sky Score iOS** app → blue **Start new build** button
2. Modal: **Build branch** → master → ⬛ Enable SSH/VNC unchecked → **Start new build**
3. Wait ~12 minutes. The 9 build stages:
   1. Preparing build machine (boots Mac mini M2)
   2. Install npm deps (`npm ci`)
   3. Assemble web bundle
   4. Generate icons + splash
   5. Add iOS platform (`cap add ios && cap sync ios`)
   6. Pod install
   7. Set bundle id + version
   8. Fetch signing files via ASC API (writes `$CERT_PRIVATE_KEY` raw PEM to `/tmp/cert_private_key.pem` → `app-store-connect fetch-signing-files --create --certificate-key=@file:`)
   9. Build .ipa (`xcode-project build-ipa`)
   10. Publishing to App Store Connect (auto-upload to TestFlight)

4. Output: `.ipa` artefact downloadable from the build page, automatically uploaded to TestFlight if publishing succeeds
5. From TestFlight, install on your iPhone for smoke testing before submitting for App Store review

---

## 6. Known gotchas (from the 12-iteration debug session)

These are documented in detail in `~/.claude/projects/.../memory/feedback_fastlane_gotchas.md` and `feedback_codemagic_node_wildcard.md`. Short version:

1. **`node: 20.x` syntax fails** — Codemagic's `n` version manager rejects `.x` wildcards. Use bare major: `node: 20`.
2. **`integrations.app_store_connect: <name>` doesn't work on Personal Accounts** — there are no named integrations. Use env vars instead (the pattern in this doc).
3. **`environment.ios_signing` block triggers pre-flight signing** that uses the Developer Portal pool with opaque selection logic. For multi-key pools (e.g. Noor + Sky Score keys both present), pre-flight may pick the wrong key. Removing the `ios_signing` block disables pre-flight; scripts do signing manually with explicit env-var credentials.
4. **`fetch-signing-files` needs the cert private key passed via `--certificate-key=@file:<path>`** — without it, the CLI tool can't save signing certificates ("Cannot save Signing Certificates without certificate private key"). Note the `@file:` prefix is required; plain `@<path>` fails as "Provided value not valid". (Earlier waves tried `--certificate-key-path`, which the live CLI rejects.)
5. **(Resolved — Wave 13.17/13.18.)** Earlier waves generated a fresh RSA key per build with `openssl genrsa`, so every build created a new Distribution cert and Apple's Personal Account 2-cert ceiling capped builds after ~2 runs. Now the cert private key is persisted as the `CERT_PRIVATE_KEY` Codemagic env var (see section 3) — same public key every time, so `fetch-signing-files` matches and reuses the existing cert instead of creating a new one. Initially attempted in 13.17 with base64 encoding; the Git Bash → clip.exe → web-textarea transfer silently corrupted bytes, so 13.18 switched to raw multi-line PEM (same format `APP_STORE_CONNECT_PRIVATE_KEY` already uses, no encoding round-trip).
6. **`environment.groups: [asc]` must be in the yaml** — variables set in the dashboard's Environment Variables panel are invisible to the build unless the group is explicitly imported.

---

## 7. Asset generation (icons + splash)

The icon and splash sources live as SVGs at `mobile/assets/`:
- `logo.svg` (full-bleed icon, 1024×1024)
- `icon-foreground.svg` + `icon-background.svg` (Android adaptive icon — used for the local Android build)
- `splash.svg` + `splash-dark.svg` (light + dark splash, 2732×2732)

These are passed to `@capacitor/assets`, which generates 130+ platform-specific PNG variants. The `ios-workflow` runs this as a build step automatically; locally:

```bash
cd mobile
npm run build:assets
```

To **change the icon design**, edit the SVGs in `mobile/assets/` and rerun `npm run build:assets`. Keep the inner safe zone (60% of canvas) for the airplane silhouette so Android's adaptive shape masks don't clip it.

---

## 8. Android (separate workflow, local)

Android does NOT use Codemagic. See [`ANDROID_BUILD.md`](./ANDROID_BUILD.md) for the Android Studio + gradle process. Quick summary: open `mobile/android/` in Android Studio, Build → Generate Signed Bundle / APK → AAB → upload to Play Console manually.

---

## 9. App Store / Play Store listings

Codemagic publishes the iOS binary; you still need to fill out the **store listings**. As of Wave 13.8.5, **all listing metadata is auto-pushed via fastlane** from text files in `mobile/fastlane/metadata/ios/en-GB/`:

```bash
cd mobile
bundle exec fastlane ios metadata_only
```

This pushes description, keywords, support URL, marketing URL, privacy URL, copyright, promotional text, subtitle, app name, and App Review notes. **Don't edit these in App Store Connect's web UI** — they'll drift from git. Edit the `.txt` files in the repo and re-run the lane.

The only thing left to upload manually is **screenshots** (5 PNGs per device size, taken on an iPhone via TestFlight install).

---

## 10. Apple Section 4.2 — surviving the review

The "Score where I am" GPS button is Sky Score's defence against Apple's Section 4.2 Minimum Functionality rejection. The full review notes are auto-pushed to ASC by the fastlane `metadata_only` lane (from `mobile/fastlane/metadata/ios/review_information/notes.txt`). Rejection counter-argument scripts live in `APPLE_REVIEW_NOTES.md`.

---

## 11. Update cycle (after first ship)

For minor web changes (CSS, JS, copy):
1. Edit `index.html`, deploy to S3 + CloudFront — that ships the web + PWA changes
2. To ship the change to native iOS users: trigger a Codemagic build for `ios-workflow`
3. Codemagic auto-uploads to TestFlight; promote to production via App Store Connect → submit for review

For native config changes (new plugin, capability, signing): edit `mobile/capacitor.config.ts` or `codemagic.yaml`, commit, trigger Codemagic build.

The native shell is essentially a thin wrapper — most updates are web-only and don't need a binary release. Plan to release a binary every 2–4 weeks at most to keep both stores fresh; more often than that is rarely worth the review-cycle cost.
