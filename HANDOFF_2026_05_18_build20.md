# HANDOFF: Sky Score iOS build 20 in Apple re-review — 2026-05-18 EOD

> **Pickup point** for the next session. Created end-of-day 2026-05-18 once Wave 13.20 (iPad layout fix) was shipped end-to-end: code committed + pushed (commits `64cea5b` + `95000c6`), Codemagic ios-workflow built build 20, build 20 resubmitted to Apple in App Store Connect. Bill is logging off; this is the pickup state for whoever (Bill or Claude) opens the next session. Delete this file once Apple approves build 20 and Sky Score iOS goes live.

## Where we are right now

Today's session ran two arcs, both closed before logoff:

1. **Apple rejected build 19** under Guideline 4.0 (Design) at 2026-05-18 — UI "crowded" on iPad Air 11" M3 / iPadOS 26.5. Submission ID `0eb16cc3-ad7f-4eea-a0e8-6953abad3a3a`. Third Apple-rejection arc for Sky Score after 2.3.8 placeholder icon and the earlier metadata gap.

2. **Wave 13.20 fix shipped same-day** (commit `64cea5b`): two new responsive CSS bands (iPad landscape 901-1366px, iPad portrait 640-900px) plus a JS auto-open threshold change so the bottom sheet no longer hides the map on iPad portrait first paint. Verified across 4 viewports via the new `tests/ipad-verify.mjs` harness. Codemagic built build 20, fastlane uploaded to TestFlight, **build 20 resubmitted to Apple ~EOD**.

The iOS arc is now in Apple's hands. Rejection-resubmit cycles typically clear in <24h (reviewer has prior context, re-tests only the cited guideline).

## What to do FIRST when you return

### 1. Check Apple's verdict on build 20

Open <https://appstoreconnect.apple.com/apps> → Sky Score → App Review section. Three states:

- **Approved / In App Store**: proceed to step 2 (web deploy) + step 3 (Android rebuild + Play upload). The 4-month native push is done.
- **Still In Review**: nothing to do. Apple's median time post-resubmit is ~12-18h. If >36h, check the App Store Status page (<https://developer.apple.com/system-status/>) for review-queue delays.
- **Rejected again**: triage the new guideline. The likely candidates if it bounces are 4.0 (different aspect of design) or 2.1 (functionality). Don't assume it's a layout regression — read the new rejection text carefully against the iPad layout work in `index.html` (the new `@media (min-width: 901px) and (max-width: 1366px)` block from line 2008+).

### 2. Web deploy (so web/PWA users get the iPad fix immediately)

Independent of Apple. Once you have a terminal:

```bash
AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"
```

Takes ~2 min total. Invalidation propagates to CloudFront edges in ~5 min. After that, tablet/iPad Safari + Chrome users on `skyscore.co.uk` see the new layout. No coordination with Apple required.

### 3. Rebuild Android AAB so Play upload carries the iPad fix

The AAB sitting at `mobile/android/app/build/outputs/bundle/release/app-release.aab` was built at Wave 13.19 (commit `c136e61`) — **before** the Wave 13.20 iPad fix. If you upload that stale AAB to Play, Android tablet users see the same cramping Apple flagged on iPad.

Rebuild:

```bash
npm run build:android
```

This runs `cd mobile && npm run sync && npm run build:assets && cd android && ./gradlew bundleRelease` per the alias in `package.json`. Takes ~3-5 min on this machine (first-run dependency download already cached from Wave 13.19). Output goes to the same path; the old AAB is overwritten.

After rebuild, resume the 8-step Play Console flow in `HANDOFF_2026_05_16_play_submission.md`. Nothing in that flow changes; only the AAB contents do.

### 4. Save the keystore password, then delete the plaintext file

Still pending from `HANDOFF_2026_05_16_play_submission.md`. Critical — `~/.keystores/sky-score-credentials.txt` is plaintext on disk and contains the 28-char random password.

```bash
notepad "C:\Users\bilal\.keystores\sky-score-credentials.txt"
# Copy "Store password" line value into Bitwarden with tag "Sky Score Android keystore"
rm "C:\Users\bilal\.keystores\sky-score-credentials.txt"
```

Deliberately left for Bill to confirm — destructive secret ops need explicit confirmation, future Claude sessions will keep reminding if forgotten.

## Lower-priority follow-ups

### 5. Delete or assert against the `TARGETED_DEVICE_FAMILY` sed in codemagic.yaml

The sed at `codemagic.yaml:106` was meant to force iPhone-only target, but Apple reviewed on iPad anyway — either the sed silently no-op'd or Apple ran the iPhone app in iPad compatibility mode. Either way, Wave 13.20 makes iPad a first-class layout, so the sed is no longer load-bearing for the rejection risk.

Two options:

- **Delete the sed step.** Simpler. Universal target is fine now that iPad layout works.
- **Add a build-failing assertion.** If the sed is meant to enforce iPhone-only forever, make it loud: `if grep -q '"1,2"\\|= 1,2' App.xcodeproj/project.pbxproj; then echo "ERROR: device family still Universal after sed"; exit 1; fi`.

Recommend option 1 (delete) because it aligns with the new "iPad is a real target" reality and removes a dead-code-mystery.

### 6. Email setup TODO (deferred from 2026-05-12)

Per `memory/project_email_setup_todo.md`: Cloudflare Email Routing → Gmail for `support@`/`hello@`/`bilal@skyscore.co.uk`. ~25 min. Apple may email during review (build 20 cycle is a re-up of the review email thread). Still worth doing whenever there's a clear hour.

### 7. Water quality data idea

Per `memory/project_water_quality_idea.md`: storm-overflow EDM is the only water layer worth adding. Design note first, not build task. Park until post-Apple-verdict and post-Play-launch — adding new data layers during an active review cycle is asking for a regression.

## Wave history (for forensic continuity, latest first)

| Wave | Commit | What |
|---|---|---|
| 13.20 echo | `95000c6` | Echo iPad fix across HANDOFF / README / ROADMAP / memory / 90-day |
| 13.20 | `64cea5b` | iPad layout pass: new 901-1366px + 640-900px media bands, JS auto-open threshold 900→640, tests/ipad-verify.mjs harness |
| 13.19.3 | `bb07db0` | Play Store submission handoff doc + release checklist update |
| 13.19.2 | `301ec8f` | npm scripts for screenshot + feature-graphic regeneration |
| 13.19.1 | `bc11bb7` | Android echo + screenshot install-prompt hide |
| 13.19 | `c136e61` | Android Play Store prep — full signed-AAB pipeline |
| 13.18.2 | `0bd8c48` | Echo iOS v1.0.1 submission across in-repo docs |
| 13.18.1 | `9a4a8fc` | Log CERT_PRIVATE_KEY length before validating (iOS) — build 19 |

## Memory updates today

Out-of-repo, in `~/.claude/projects/.../memory/`:

- `feedback_first_appstore_submission_gotchas.md` — extended with a Guideline 4.0 / iPad section covering (a) the silent `sed` no-op risk on `TARGETED_DEVICE_FAMILY`, (b) the auto-open-threshold-mirrors-CSS-breakpoint trap that hid the map on iPad portrait, (c) the Wave 13.20 fix structure
- `project_mobile_ux_redesign_v1_1.md` — scoped down: iPad widths now addressed in Wave 13.20; only iPhone-width layer-toggle cramping (~32% of 414px viewport) remains for v1.1
- `MEMORY.md` index — refreshed two lines to reflect the new state

## What I deliberately did NOT do at logoff

- **Did not run AWS S3 / CloudFront commands** — destructive and wants a hands-on terminal. Step 2 above is paste-ready for next session.
- **Did not run `npm run build:android`** — 3-5 min build that might surface gradle/sharp errors better seen interactively. Step 3 above.
- **Did not delete `~/.keystores/sky-score-credentials.txt`** — still waiting on Bill to save the password to Bitwarden first.
- **Did not delete the codemagic.yaml TARGETED_DEVICE_FAMILY sed** — wanted to confirm build 20 actually passes Apple before mutating the iOS build pipeline mid-review-cycle.

## Time accounting (rough)

- ~10 min: triage Apple rejection email + audit existing CSS breakpoints
- ~10 min: design iPad breakpoint strategy + present to Bill
- ~15 min: implement CSS + JS changes
- ~15 min: build Playwright verification harness + debug the auto-open issue
- ~5 min: regression-check desktop + phone viewports
- ~10 min: commit + push + Codemagic build trigger (Bill's hands)
- ~15 min: echo work across HANDOFF / README / ROADMAP / memory / 90-day
- ~5 min: this handoff doc

**Total Claude-side: ~80 min** of focused work, ~3 commits, two pushed to GitHub, build 20 in Apple's queue. Next session pickup should take <5 min via this doc.
