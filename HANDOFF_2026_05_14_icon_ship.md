# HANDOFF: App Icon Resubmission — 2026-05-14 EOD

> **Partially superseded by Wave 13.17 (commit `4c0355a`, 2026-05-16).** The §"Apple cert situation" section below is now archival — `CERT_PRIVATE_KEY` env-var persistence eliminated the 2-cert ceiling permanently. The cert revoke-and-retry steps no longer apply; the next Codemagic build creates a single durable cert from the persisted key and every subsequent build reuses it. Icon-verification steps (§"What to do FIRST when you return" items 2–4) still apply unchanged. See `mobile/CODEMAGIC_SETUP.md` section 3 + `ROADMAP.md` "Last reviewed" for the new state.

> **Pickup point** for next session. Started 2026-05-14, paused mid-flight while waiting on Codemagic build 17. Delete this file once Sky Score v1.0.x is approved by Apple.

## Where you are right now

Apple **rejected Sky Score v1.0/build 12** on 2026-05-12 under guideline **2.3.8 (placeholder app icon)**. After 5 build attempts (13, 14, 15, 16) the icon STILL shipped as the Capacitor cyan-X placeholder. The actual root cause was finally identified at the build 16 log:

```
Unable to load source image logo.svg: Input file contains unsupported image format
Unable to load source image icon-only.svg: Input file contains unsupported image format
```

**capacitor-assets v3.0.5 on Codemagic's macOS** can't load the radar-rings SVGs (sharp/libvips chokes on the radial gradients + opacity stops). The build silently skips iOS icon generation, leaving the AppIcon.appiconset with a stale Capacitor placeholder PNG from May 8.

**Fix shipped in commit `3e58d08` (Wave 13.16):** pre-rasterised the four icon SVGs to 1024×1024 PNGs locally using sharp on Windows (which renders fine), committed them alongside the SVGs. capacitor-assets v3 prefers `.png` over `.svg` when both exist.

## The wave history (so you can read the git log in context)

| Wave | Commit | What | Status |
|---|---|---|---|
| 13.14 | `5495eb8` | Redesigned icon SVGs (radar rings + plane) | Shipped — but didn't reach binary |
| 13.15 | `bc3f83b` | Reordered codemagic.yaml so build:assets runs AFTER cap add ios | Shipped — necessary but insufficient |
| 13.16 | `3e58d08` | Rasterised SVGs to PNGs (THIS is the fix that should work) | Shipped — pending build 17 verdict |

Builds 13–16 all shipped with the broken icon. Build 17 is the first that should have the radar design in the iOS binary.

## What to do FIRST when you return

1. **Check Codemagic** at https://codemagic.io/apps. Build 17 status:
   - **Building** → wait for it
   - **Failed at signing step** → revoke older Distribution cert(s) at https://developer.apple.com/account/resources/certificates/list (the cert situation as of 22:35 on 2026-05-14: 2 active certs, both 2027-05-14 expiry. Revoke whichever wasn't created last). Then click **Start new build** in Codemagic.
   - **Failed at "Generate icons + splash from SVG sources" step** → the PNG fix didn't work; debug by clicking into that step and looking for what capacitor-assets generated for iOS. Look for `CREATE ios icon ...` lines vs only `CREATE ios splash ...`. The `ls -la ios/.../AppIcon.appiconset/` sanity log at the end will show truth.
   - **Succeeded with "Post process failed for london-flight-path-map"** → IGNORE. That post-process failure is just TestFlight beta-review submission missing a Feedback Email field. The IPA is in App Store Connect, ready to use.

2. **Verify the icon BEFORE submitting** (this is the gate):
   - App Store Connect → Sky Score → App Store tab → **v1.0.1** (the version we created after the rejection)
   - Currently has build 13 attached (broken icon). Swap to build 17 (or whatever the latest successful build is).
   - Scroll to **Build > Included Assets > App Icon** thumbnail
   - **Must show the orange radar-rings design** (orange disc with white plane silhouette + concentric rings on dark navy background)
   - **If still cyan-X**: STOP. The PNG fix didn't work. Read the build log for "Generate icons + splash from SVG sources" to diagnose.

3. **Reply to the rejection in Resolution Centre** (left sidebar of v1.0.1):
   > Resubmitting as version 1.0.1 with a redesigned app icon — replaced the previous placeholder-style icon with a custom radar/contour design that reflects the app's noise-data functionality.

4. **Submit for Review**.

## App Store Connect state to be aware of

- **v1.0** in ASC: Rejected, build 12 attached. Leave alone.
- **v1.0.1** in ASC: Created earlier today, build 13 attached (BROKEN icon). Need to swap build before submitting.
- **Build 13** uploaded ~21:34, processed Complete. **DO NOT submit** — has the cyan-X placeholder icon.
- **Build 14** uploaded but post-process noise; ignore.
- **Build 15, 16** same — broken icons (built before the SVG-loader bug was identified).
- **Build 17 (or 18+)** — first build with the PNG fix. **This is the one to submit.**

## App Store icon (1024×1024 separate upload, if asked)

If App Store Connect asks you to upload a 1024×1024 App Store Icon separately (not the in-binary one), use:

- `C:\Users\bilal\OneDrive\Desktop\london-flight-path-map\mobile\assets\logo.png` (it's already 1024×1024 opaque, ready for ASC upload)

Or rasterise fresh from `mobile/assets/logo.svg` if you want to tweak the design first.

## Apple cert situation

Distribution certs at https://developer.apple.com/account/resources/certificates/list:
- 1 cert with expiration 2027-05-11 was REVOKED earlier today (the older one)
- 1 cert with expiration 2027-05-11 was REVOKED earlier today
- 1 cert with expiration 2027-05-14 (kept — used by build 13)
- Build 16 created another cert (4CJL6FLL23, 2027-05-14)

So as of EOD 14 May, **2 active distribution certs exist**, both expiring 2027-05-14. Apple's Personal Account limit is 2 — you're at the cap. **Build 17 will fail at signing** (it tries to create a 3rd cert) **unless you revoke one cert first.**

**Revoke order**: pick whichever wasn't created last. The build 16 log shows cert `4CJL6FLL23` was just created — keep that one (it signed build 16 which is in TestFlight). Revoke the older 2027-05-14 cert (the one Codemagic created for build 13).

Or — and this would be the cleaner long-term fix — implement the **`CERT_PRIVATE_KEY` env-var persistence pattern** described in `memory/feedback_codemagic_personal_account_signing.md` ("Future iteration to plan for"). Generate the cert private key once, store it base64-encoded as a Codemagic env var, and the signing script reuses the same cert across builds. Defers the 2-cert ceiling problem indefinitely. ~20 min of work; not blocking the icon ship.

## Files modified today (commits + paths)

| Commit | Files | Purpose |
|---|---|---|
| `5495eb8` (13.14) | `mobile/assets/{logo,icon-foreground,icon-background,icon-only}.svg`, `icons/icon{,-maskable}.svg` | Radar-rings icon redesign |
| `f37045f` (13.14) | `ROADMAP.md` | Echo |
| `bc3f83b` (13.15) | `codemagic.yaml` | Reorder build steps + sanity log |
| `3e58d08` (13.16) | `mobile/assets/{logo,icon-only,icon-foreground,icon-background}.png` | Pre-rasterised PNGs (the actual fix) |

## Memory updates

- `feedback_first_appstore_submission_gotchas.md` — extended with 2.3.8 placeholder-icon section + corrected diagnosis of the codemagic ordering bug + (TODO this session) PNG-vs-SVG lesson

## What I'd add to memory in the next session

When build 17 lands and we confirm the radar icon is in the binary, append to `feedback_first_appstore_submission_gotchas.md`:

> **Capacitor + Codemagic: ship icon SOURCES as PNG, not SVG.** sharp/libvips on Codemagic's macOS environment fails to load complex SVG icons (radial gradients with multiple stops, defs blocks). The failure is silent: capacitor-assets writes splashes, skips icons, exits 0. The only signal is two `Unable to load source image ... Input file contains unsupported image format` lines at the top of the "Generate icons + splash from SVG sources" step's log. Pre-rasterise SVG → PNG locally on a working sharp install (Windows, Linux desktop), commit the PNGs to `mobile/assets/`, and capacitor-assets v3 will prefer them. Splash SVGs continue to work fine because the markup is simpler.

## Time accounting

- ~30 min: misdiagnosed icon SVG (assumed Apple rejected the Material Icons glyph)
- ~15 min: Wave 13.14 redesign + push
- ~30 min: identifying that build 13 still had Capacitor placeholder, diagnosing as codemagic ordering issue
- ~10 min: Wave 13.15 fix + push
- ~10 min: cert revocation + retry sequence
- ~30 min: 4 broken builds (14, 15, 16) before reading the log carefully enough to spot the "Unable to load source image" lines
- ~5 min: Wave 13.16 PNG rasterisation + push (THIS should be the actual fix)

Total: ~2h. Could have been ~30 min if I'd asked for the build log earlier instead of trusting the `2s` step duration as evidence the step worked.
