# Audit Report — Sky Score

**Date:** 2026-11-27 · **Code:** master `b74d2458` (live, apart from the iOS fix below) · **Previous:** `AUDIT_REPORT_2026-11-23.md`

Three read-only reviewers in parallel (code review, security, frontend design and accessibility), each told to skip what
the 23 Nov audit found, fixed or accepted, and to read CLAUDE.md and the must-not-undo lists first. Every Important finding
below was re-checked in the session against the code (and, for I-1, against postcodes.io live) before it was written here.

**Files scanned:** the 9 Lambdas (the news sender new since 23 Nov), `backend/template.yaml`, `backend/iam-policy.json`,
`index.html`, `home/index.html`, `js/*.mjs`, `sw.js`, `extension/`, `mobile/` and `codemagic.yaml`, the page builders in
`scripts/`, and the live pages /, /map/ (a UK borough card, Bay Area city cards, Delete all opened but not confirmed),
/area/bayarea/palo-alto/, /area/bayarea/oakland/, /bay-area/, /open-data/ (#planes), /privacy, /terms and /changes at
1366x768, 390x844 and 320x640, plus forced colours, reduced motion and 1.4.12 text spacing. axe-core 4.11 (WCAG 2.0, 2.1,
2.2 AA and best practice): 0 violations on every page and state. `npm audit --omit=dev`: 0 (root and mobile/).

**Found and fixed this week, before this audit (for the record):** CI ran none of its 1,886 root tests from 26 to 27 Nov,
because a test read gitignored data at import (`8e122fb7`); LICENSING.md said the planes ODbL download was "not yet built"
a day after it went live (`cf940015`); the extension's environment footer credited no one, and `scripts/area_summary.mjs`
called DEFRA's map "measured" (`b74d2458`).

## Critical Issues

None.

## Important Issues

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| I-1 | The app's "Score where I am" told a UK user "works in the UK" whenever they stood more than 100 m from a postcode's centre (a park, an airfield, moorland): the reverse lookup used postcodes.io's default 100 m reach. Read live: Richmond Park gave `result: null`; with `radius=2000`, TW10 5HR at 745 m. The map's other reverse lookup already asked for 2 km. iOS 1.0.22's review notes promise it "finds the UK postcode you are standing in". **FIXED 27 Nov** before the build (Bill's pick: hold it): `&radius=2000`, and a Richmond Park case in `tests/native-locate-me.mjs`, proven red first. | `index.html:6083` | Code |
| I-2 | The do-not-email list is matched on the exact address, while the send cap counts the inbox (`mailbox_key()`): `alice+news@gmail.com` or `a.lice@gmail.com` still gets confirmation emails (news, alerts, API keys) after `alice@gmail.com` unsubscribed, against privacy s2a's "so we never write to it again". Reproduced offline by the reviewer for both `updates` and `api`. | `backend/lambdas/signup/app.py:823` vs `:892` | Security |
| I-3 | After an unsubscribe the address stays in rows that never expire: the news sender writes `sent#<issue>#<email>` per member (`news/app.py:256`), and since I-2 of 23 Nov the older `unsub#<token>` rows of a re-joiner are kept; unsubscribe deletes only the member row and the token presented, and MailTable has no TTL. Privacy s2a: "Kept until you unsubscribe; we then delete it, keeping only the address on a do-not-email list". LATENT: no issue has gone out (December's is unapproved) and the only members are Bill's two test addresses. SUBPROCESSORS row 1 is also stale ("one plain-text confirmation email", "the postcode only if its box was ticked"). | `backend/lambdas/news/app.py:256`; `signup/app.py:1438-1443`; `backend/template.yaml` (MailTable) | Security |
| I-4 | In a browser that refuses site storage, Delete all reports "Nothing is saved for this browser on our server any more" while every saved place is still stored: `getDeviceToken()` mints a NEW token on every call when `localStorage` throws, so the save goes in under one token and the delete out under another, which deletes nothing and returns `notDeleted: []`. A single removal "succeeds" the same way. Orphaned places can never be deleted. | `index.html:15365-15392`, `15402`, `15541` | Code |
| I-5 | On the front page's Bay Area card, the "At a glance" values for Rail access and Aircraft noise ("Poor", "Low") exist only as CSS generated content with empty alt text (`content: attr(data-fig) / ""`) and are in none of the tile's words, so a screen reader hears the label and the explanation but never the verdict (WCAG 1.3.1, failure F87). The pattern is right for the Nearby tiles only because their figure is also in their words. Home value is fine. | `js/home-engine.mjs:1160-1166` (`bayGlanceHtml`, new in `be25b5fd`); `home/index.html:503` | Accessibility |

## Minor Issues

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| M-1 | NewsFunction has no log group with a retention: its first run creates one that never expires, against privacy's "retained for 30 days", and turns the blocking preflight check "log retention == privacy.html" red. It does not exist yet, so the template can create it with 30 days now (CloudFormation cannot adopt a group Lambda has made). DO BEFORE THE FIRST PREVIEW. | `backend/template.yaml:1137` | Security |
| M-2 | The news sender can send a member the same issue twice: the `sent#` row is written unconditionally AFTER the SES send, so a failed write (or two overlapping Test presses) sends again; with `retries max_attempts 2` a slow SendEmail can be retried after SES took it. Claim the row first (`attribute_not_exists`). | `backend/lambdas/news/app.py:247-257`, `:60` | Code |
| M-3 | The template says "the deploy user cannot invoke it", but the deploy policy grants `lambda:AddPermission` and `UpdateFunctionCode` on `london-flight-map-*`, and Scan/PutItem/DeleteItem on every `london-flight-map-*` table, the mail list included. Narrow the data actions off `-mail`, `-signups`, `-signup-pending`. | `backend/template.yaml:1131`; `backend/iam-policy.json:67,71,180,186` | Security |
| M-4 | NewsFunction is broader than it needs: `DynamoDBCrudPolicy` (it uses Scan, GetItem, PutItem) and `ses:SendEmail` on `identity/*` with no `ses:FromAddress` condition. Same pattern as 19 Nov's M-4. | `backend/template.yaml:1148-1156` | Security |
| M-5 | 23 Nov's M-1 is half fixed: a listed address now gets the 503 on a full day, but is still answered measurably faster (two GetItems, no SES) than anyone else, so the list can be probed by timing. | `backend/lambdas/signup/app.py:823-835` | Security |
| M-6 | The front page's Bay Area "Home value" tile formats prices by its own rule (`$0.60M` for Emeryville's $604,800, `$1.20M` for Albany) where the map's `formatPriceCompact` says `$605k` and `$1.2M`: one figure, written two ways. | `scripts/build_bayarea_front.py:83` | Code |
| M-7 | Opening a Bay Area city on the front page sends focus to the card's h2, and its new answer-first headline goes into the hero h1 silently: `#lead-said` says nothing, where a postcode search says its lead there. | `js/home-engine.mjs:1029-1042`, `1419-1451` | Accessibility |
| M-8 | The full map's Bay Area card: "Change profile" and "The Bay Area page" have no focus ring of their own, so a phone shows the browser's amber (1.96:1, the defect 23 Nov's M-13 fixed elsewhere); `tests/map-focus-rings.mjs` does not reach them. | `index.html:17362`, `17168` | Accessibility |
| M-9 | /privacy and /terms define no `--focus` and no link focus rule (32 and 18 controls), so a phone shows the amber browser ring (1.87:1). Unmodified browser rings are exempt from AA, so this breaks the project's own M-13/M-16 rule rather than WCAG. | `privacy.html`, `terms.html` | Accessibility |
| M-10 | With 1.4.12 text spacing at 320 px, the merged "Beyond one street" band is 348 px wide: the nowrap pill "Get a key and read the docs" sets an implicit grid column. 19 Nov's M-19 now reaches the three rows too. | `home/index.html:709`, `625`, `1209` | Accessibility |
| M-12 | Found while fixing M-2: `InnerClientBudgetTests` reads `retries['max_attempts']` as the TOTAL attempts, but botocore reads `max_attempts: N` as N RETRIES and stores `total_max_attempts = N + 1` (`botocore/args.py`). So the signup Lambda's `max_attempts: 1` is two attempts a call, and its six hops' true worst case is (2 + 2) x 2 x 6 = 48 s against the 28 s Timeout the test says it fits (24 s). Chat and favourites read the same way. Fix the test's arithmetic, then the budgets it then shows (later pass). | `backend/tests/test_handlers.py:906-908`; `backend/lambdas/signup/app.py:232-236` | Code |
| M-11 | In Windows contrast themes the tile pictures go: the map's `.t-track` bars paint black on black, the rating strip marks its choice by bold alone, and the front page's Bay Area bars (`role="img"`) vanish. The figures stay in text. 23 Nov's I-5 covered legends, not tiles. | `index.html:2944-2954`; `js/home-engine.mjs:1152` | Accessibility |

**Noted, not a finding:** one-click news confirmation (Bill's pick) assumes link scanners run no script; some sandboxing
scanners do, which could confirm a corporate address someone else typed in. Watch the confirm rate if it matters.

## Summary

- Critical: 0
- Important: 5 (I-1 fixed the same day)
- Minor: 12 (M-12 found while fixing M-2)

Recommended order: I-1 (done, so the iOS build can go); M-1 before Bill's first news preview; I-2 and I-3 together with
M-2 (the email batch, before the first issue is approved); I-4 (keep the token in memory too); I-5, M-7, M-8 (the Bay Area
card's accessibility); the rest in a later pass.

## Status (Bill: "yes" to the recommended order, 2026-11-27)

- **I-1 FIXED and on master** (`344ff142`, Bill held the iOS 1.0.22 build for it): `&radius=2000`; a Richmond Park case in
  `tests/native-locate-me.mjs`, red on the old lookup.
- **Fixed on branch `audit-fixes-2026-11-27`**, each check proven red on master's code first (the backend ones by swapping
  master's two Lambda files in and out):
  - **M-1:** `NewsLogGroup` (30 days) in the template, made before the function's first run; held by `test_news_sender.py`.
  - **I-2:** the do-not-email list is read by the address AND its inbox (`suppress_keys()`, one BatchGetItem, so the POST
    stays at six hops) in the signup Lambda and the news sender; an unsubscribe writes both entries. The news sender's copy
    of `mailbox_key()` is held to the signup's by `test_mailbox_key_parity.py`. OPERATIONS s3.10's manual removal names
    both entries.
  - **I-3:** an unsubscribe deletes EVERY token of the address (a scan, one batch delete); the news sender's records are
    `sent#<issue>#<sha256>`, never the address, with `expiresAt` a week after the issue's month (MailTable TTL).
  - **M-2:** the member's copy is CLAIMED (a conditional write) before SES is asked; a failed send gives the claim back;
    SES is not retried (`total_max_attempts: 1`: `max_attempts: 1` would have retried once, see M-12).
  - **I-4:** the saved-places token is kept for the page's life too, and Delete all forgets that copy;
    `tests/favourites-delete-all.mjs` 10 (storage refused).
  - **I-5 and M-7:** the Bay Area glance verdicts are in the words (visually hidden), and the card's headline is said in
    `#lead-said`; `tests/front-page.mjs`.
  - **M-8:** `.bay-change-profile` and `.bay-page-link` take the site's ring; `tests/map-focus-rings.mjs` (phone, 390).
- **Not changed, for Bill:** SUBPROCESSORS.md row 1 is stale ("one plain-text confirmation email", "the postcode only if
  its box was ticked"): a legal register, so its wording waits for his review.
- **Later pass:** M-3 to M-6, M-9 to M-12.
