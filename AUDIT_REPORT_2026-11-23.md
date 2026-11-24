# Audit Report — Sky Score

**Date:** 2026-11-23 · **Code:** master `53e9abd9` (live) · **Previous:** `AUDIT_REPORT_2026-11-19.md`

Three read-only reviewers in parallel (code review, security, frontend design and accessibility), each told to skip what
the 19 Nov audit fixed or accepted. Every Important finding below was re-checked in the session against the code before
it was written here. Branches not yet on master (`news-sender`, `audit-17-capitals`, `faa-2612-on-53e9abd9`) were not
reviewed, except where a finding bears on them.

**Files scanned:** the 8 Lambdas, `backend/template.yaml`, `index.html`, `home/index.html`, `js/*.mjs`, `sw.js`, the page
builders in `scripts/`, and the live pages /, /map/ (with a borough card, Rankings, Saved, the planes layer), /pricing,
/about/, /how-it-works/, /api/, /area/london/hounslow/ and /planes-overhead/tw4/ at 1366x768 and 390x844 (plus 320x640,
844x390, 320x192, forced colours, reduced motion and 1.4.12 text spacing). axe-core: 0 violations on every page and state.

## Critical Issues

None.

## Important Issues

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| I-1 | The do-not-email list is read only for news sign-ups: an address that unsubscribed still gets API-key and score-alert confirmation emails, against privacy s2a's "so we never write to it again" and the module's own comment (found by two reviewers; ran with a stub: updates 0 sent, consumer 1, api 1) | `backend/lambdas/signup/app.py:816` | Security / privacy |
| I-2 | Joining news again deletes the member's old unsubscribe token, so the unsubscribe link in every earlier email stops working ("You are not on the list"), against OPERATIONS s3.10 and PECR; `test_signup_updates.py:291` asserts the old behaviour on purpose. Latent until the news sender sends (branch `news-sender`), so it must be fixed before the first issue | `backend/lambdas/signup/app.py:1320-1327` | Code / consent |
| I-3 | The borough card's aircraft-noise tile says "scaled by the size of each airport's DEFRA noise map" in every city, though Teesside's airport is unmapped, South Yorkshire has no commercial airport and New York is not DEFRA; the area page picks its caption from `_defra_contour_status()` and the card does not | `js/panel-findings.mjs:389`, called at `index.html:13830` | Code / accuracy |
| I-4 | No SES bounce or complaint monitoring: `send_email` passes no configuration set and no reputation alarm exists, so 200 made-up addresses a day (the send ceiling) could push the bounce rate towards SES's review level unseen, and fills the ceiling for real sign-ups | `backend/lambdas/signup/app.py:140, 829-836, 1055-1068` | Security / operations |
| I-5 | In Windows contrast themes (forced colours) every legend loses its colour key (DEFRA scale, flight-path lines, planes steps, the front page's ramp), selected tabs and the active city lose their mark, and the two filled buttons lose their outline. Beyond WCAG 2.2 AA in normal colours; the standard Windows low-vision setting | `index.html:817, 830, 3372, 5240-5264`; `home/index.html:117, 248, 302, 559, 698` | Accessibility |

## Minor Issues

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| M-1 | A listed (do-not-email) address answers 201 while the day's ceiling is full where any other gets 503, and faster: the list can be probed | `signup/app.py:820-836` | Security |
| M-2 | The service worker stores the `/v1/signup/*` confirm and unsubscribe pages (token in a hidden field) since CloudFront serves them on skyscore.co.uk | `sw.js:357-363, 444-452` | Security |
| M-3 | Deeply nested JSON or a 4,300+ digit integer gives a 500 on anonymous signup and favourites (only `JSONDecodeError` caught) | `signup/app.py:281`; `favourites/app.py:225, 260`; `chat/app.py:361`; `score/app.py:12331` | Security / robustness |
| M-4 | SignupFunction and FavouritesFunction hold Scan/Query/BatchGet they never use | `backend/template.yaml:476, 928-942` | Security (least privilege) |
| M-5 | Both send counters rise before the SES send, so an SES outage uses up visitors' daily allowance | `signup/app.py:961-966` v `845-877` | Code |
| M-6 | "Use a different address" resets the page's send count even for the same address, so the strip can claim a send the Lambda declined | `js/news-signup.mjs:120-127` | Code |
| M-7 | A redraw (profile change) brings back an alert form already sent, with the address restored | `index.html:15002-15019`, `14250` | Code |
| M-8 | The confirm page says "Confirmed" when an API-key holder's score-alert sign-up was refused (`already-registered`) | `signup/app.py:1254-1258` | Code |
| M-9 | A borough card drawn while a city's outlines are still loading is never redrawn, so its planes row can be missing | `index.html:13741-13749` | Code |
| M-10 | `sensorLine`, `monitorLine`, `airNotes` exported but unused; CLAUDE.md still describes `airNotes()` | `js/street_report.mjs:138-144, 351` | Dead code |
| M-11 | The news strip drops focus to `<body>` when the third send hides "Send it again" (2.4.3) | `js/news-signup.mjs:113` | Accessibility |
| M-12 | The merged band's audience list (`id="who"`) has no heading, so it sits under "Data for your business" in the outline (1.3.1) | `home/index.html:1153` | Accessibility |
| M-13 | Some full-map controls (city buttons, footer links, SAVE) fall back to the browser's ring; Chromium's phone amber is 1.87-2.3:1 (1.4.11) | `index.html` (city switch, footers, `.fav-btn`) | Accessibility |
| M-14 | The phone planes legend's busiest swatches are 1.38:1 and 2.36:1 on its dark ground (1.4.11) | `index.html:3829` | Accessibility |
| M-15 | How it works' approach plane bobs forever with no pause (2.2.2) | `how-it-works/index.html:202` | Accessibility |
| M-16 | The map's footers carry an `aria-label` a footer inside main/aside cannot have | `index.html:5392, 5645` | Accessibility |
| M-17 | The front page map puts 33 council buttons in the Tab order (42 Tabs to reach "Sign me up") | `home/index.html` (map paths) | Accessibility |
| M-18 | Much of the full map's text is 8-9 px (phone city switch, legend notes, desktop footer) | `index.html:458, 4816, 5150, 5204, 5268` | Design |
| M-19 | With 1.4.12 text spacing at 320 px, the developers band and How it works' table scroll sideways | `home/index.html` dev band; `how-it-works/index.html` | Accessibility |
| M-20 | The masked address is likely read as "b bullet bullet…" by screen readers | `js/news-signup.mjs:28` | Accessibility |
| M-21 | Phone map: the search card touches the right edge; SAVE has no padding | `index.html:4888` | Design |
| M-22 | Desktop map footer separators at 1.97:1 (the phone footer's were fixed 7 Sep) | `index.html:492` | Design |
| M-23 | `lang="en"` on some pages, `en-GB` on others | `/, /about/, /how-it-works/`, built pages | Accessibility |

## Summary

- Critical: 0
- Important: 5
- Minor: 23

Recommended order: I-1, I-2, M-1, M-2, M-3, M-8 (the sign-up and consent batch, before the news sender's first issue);
I-3 (accuracy); I-4 (SES monitoring); I-5 and M-11 to M-16 (accessibility). The rest are design choices or small, for a
later pass.

## Status (Bill: "go with recommended", 2026-11-23)

Batches 1 to 3 on branch `audit-fixes-2026-11-23`, to deploy after the 24 Nov meetings:

- **Fixed:** I-1, I-2, M-1, M-2, M-3, M-8 (sign-up and consent); I-3 (the card's aircraft sentence per city, held to each
  area page's caption by `tests/uk-city-panel.mjs`).
- **Done:** I-4, LIVE 23 Nov 22:08 (Bill ran `sh scripts/create_ses_alarms.sh --test`: both alarms OK, all four test
  emails arrived). A bot check on the sign-up forms stays a product question.
- **Fixed (batch 4, Bill: "go with recommended" again):** I-5 (contrast themes: `tests/forced-colours.mjs`, light and
  dark), M-11 (and its wider cause: the resend button was `disabled` while sending, so EVERY press lost focus), M-12,
  M-13, M-14, M-16 (`tests/map-focus-rings.mjs`), M-15 (`tests/approach-strip.mjs`, whose old motion check was
  `anim >= 0` and could not fail). Each test proven red on master.
- **Found while fixing, fixed:** the map made a saved-places token on EVERY page load and sent it, against privacy
  s2e ("Browsing and scoring never generate one"); with Bill's pick A for "Delete all saved places" the same day,
  dated on /changes.
- **Later pass:** M-4, M-5, M-6, M-7, M-9, M-10, M-17 to M-23 (design choices or tidy-ups).
