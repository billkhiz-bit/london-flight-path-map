# Audit Report - Sky Score

**Date:** 2026-09-25
**Scope:** every commit since the 13 Sep audit (`92013b7`..`7d22989`), the uncommitted tree, and a sweep of the Lambdas, the main render paths in `index.html`, the extension, the B2B pages and the new `talks/` folder.
**Method:** three read-only reviewers in parallel (code correctness, security, frontend + WCAG 2.2 AA), each told to exclude everything already closed or recorded as a decision in `AUDIT_REPORT_2026-09-13.md`, `AUDIT_REPORT.md` and CLAUDE.md's Known Issues. **Every finding marked FIXED below was re-verified by hand before it was fixed**, and every fix has a check that was proven red on the old code.

## Critical

None.

## Important

| # | Issue | File | Status |
|---|---|---|---|
| I-1 | **`/v1/changes` published "changed from Trafford (Greater Manchester) (+6.3%) to Trafford (Greater Manchester) (+6.3%)".** Since v5.2 the growth yardstick is the sterling pool's fastest riser, and only London is held at the previous vintage, so a yardstick from another city is July's figure published as May's. Reproduced on the live endpoint. The `/changes` page printed the same figure as a "Was" row. | `backend/lambdas/score/app.py` `benchmarks`, `market_context`; `changes.html` | **FIXED, not deployed.** `benchmarks(..., previous=True)` sets `strongestGrowthStandIn` / `steepestFallStandIn`; the summary says the yardstick cannot be compared; the page says "Not held". Spec documents both fields. `test_yardstick_sentence_only_claims_a_change_it_measured` + the extended market-context test, red on the old engine. |
| I-2 | **The public `/talks/` write-up said the deploy credential cannot change its own permissions and that "nothing else in the account is reachable".** False: `IAMRolesForLambda` attaches any policy to a `london-flight-map-*` role (OPERATIONS s3.8, open) and `APIGateway` covers every API in the region. A security statement a prospect could rely on. | `talks/how-the-checks-work.html` | **FIXED, not deployed.** Rewritten to state both gaps plainly; PDF re-rendered. Live until `talks-deploy` runs. |
| I-3 | **Both talks PDFs were untagged** (no structure tree, reading order or language) and were the only format `/talks/` offered. | `talks/*.pdf`, `talks/index.html`, `Makefile` | **FIXED, not deployed.** `scripts/render_talks_pdfs.mjs` renders tagged (verified `/StructTreeRoot`, `/MarkInfo`, `/Lang`, `/Outlines`); the accessible HTML is now published and is the primary link. |
| I-4 | **"SAVED" favourite button at 2.13-2.49:1** (10px `--orange` text). No gate reaches the state: it exists only after a save. | `index.html` `.fav-btn` | **FIXED.** `--orange-text`, measured 4.9-5.6:1 on every panel background. |
| I-5 | **Verified signup would lose keys to email link scanners.** A GET on the confirm link consumes the token and shows the only copy of the key; Safe Links / Mimecast / Proofpoint GET every link first. Also: no per-address send cap (~86k emails/day to one address at the route throttle). | `backend/lambdas/signup/app.py` `handle_confirm`, `start_verification` | **OPEN, latent** (flag off). Recorded as blocking preconditions at the top of OPERATIONS s3.9, before the flip. |

## Minor

| # | Issue | File | Status |
|---|---|---|---|
| M-1 | Sold-prices panel said "cannot be loaded ... due to browser security restrictions" for a postcode with no recorded sales (the endpoint had answered 200), and called Rightmove an "official source". | `index.html` `fetchSoldPrices`, `renderSoldPrices` | **FIXED.** Three outcomes (`'none'` / `'unavailable'` / rows); `tests/uk-city-panel.mjs` forces each by stubbing `/sold-prices`, 4 of 6 checks red against the live site. |
| M-2 | Extension collapsed an unreadable sold-prices body into "No Land Registry sales recorded" - the mirror of M-1. | `extension/content/panel.js` | **FIXED.** Non-array `transactions` renders "not available". |
| M-3 | Badge served from our own origin with no CSP, and echoed any caller text under the brand. | `score/app.py` `_svg_response`, `handle_badge` | **FIXED, not deployed.** `default-src 'none'`; echo capped at 10 characters. Two tests. |
| M-4 | Client postcode lookup and autocomplete put unvalidated input into the postcodes.io PATH (client twin of the 7 Sep server traversal fix). | `index.html` `lookupPostcode`, `fetchAutocomplete` | **FIXED.** Same `[A-Z0-9]{1,8}` rule as the Lambda. |
| M-5 | A failed `stations.json` load was memoised until reload, while the panel said "for now". | `index.html` `ensureStations` | **FIXED.** A failed load retries on the next search. |
| M-6 | Embed snippet interpolated the postcode into `alt` unescaped (not exploitable today; the snippet is pasted onto third-party pages). | `index.html` `embedSnippet` | **FIXED.** `escapeHtml`. |
| M-7 | `real_trend_pct` comment said "halves away from zero"; the code (correctly) rounds halves toward +infinity, like `Math.round`. | `score/app.py` | **FIXED** (comment). |
| M-8 | `web-deploy-all` ran `web-deploy` before `data-deploy` (already recorded; closed in this pass). | `Makefile` | **FIXED.** Gated by `test_web_deploy_all_ships_data_before_the_page`. |
| M-9 | **Measured (real CDP touch drags, SW11 1AA, 390x844 / 320x568 / 844x390).** (a) The close button was `absolute` inside the card, which became its own scroller on 24 Sep, so it scrolled away: y=247 at open, **y=-3666** once the card was read to its end. (b) With a result open, `/privacy` and `/terms` are unreachable at all three sizes: below the fold in portrait (the sidebar holds 81-133px of overflow and its `scrollTop` stays 0 under 20 drags - it is `pointer-events: none`), under the bottom nav in landscape. Both are fine in the landing state, which is all `tests/mobile-legal-links.mjs` checks. | `index.html` `.result-close` (<=900px block) | **(a) FIXED** - `position: sticky`, y=247 at every scroll depth on all three sizes; new `net_check` `tests/result-close-reachable.mjs`, proven red 3 of 3 on the old CSS. **(b) OPEN, a decision**: the links are one tap away (close the result) now that close is always reachable; showing the footer inside the result state is a layout choice, not a fix. |
| M-10 | The chat grounding check sees digits only; numbers written as words ("fifty out of a hundred") are not checked. | `backend/lambdas/chat/app.py` `extract_numbers` | **OPEN**, a known limitation. Worth stating wherever the check is presented as the control. |
| M-11 | Signup email carries a user-supplied postcode that is truncated but not shape-validated. | `signup/app.py` | **OPEN, latent**; folded into I-5's precondition list. |
| M-12 | `toggleFavourite()` updates the first `.fav-btn` in the document, not the clicked one. Correct today (only one renders). | `index.html` | **OPEN**, no user impact today. |
| M-13 | `/talks/` card links do not say they open a PDF. | `talks/index.html` | **FIXED** by I-3: cards open the HTML; the PDF links say "as a PDF". |
| M-14 | An empty sold-prices list can also mean Land Registry returned sales with no numeric price (the Lambda drops them), which renders as "no recorded sales". Rare. | `sold_prices/app.py` | **OPEN**, noted. |

## Summary

- Critical: 0
- Important: 5 (4 fixed, 1 open and latent behind the off flag)
- Minor: 14 (9 fixed, 1 part-fixed (M-9: the close button; the footer half is a decision), 4 open)
- Swept clean: chat decimals-only fix holds; `real_trend_pct` matches the site's `scoredTrend`; `aircraftQuietCoverage` wiring; nhs/transport/favourites Lambdas; extension permissions (`storage` only) and messaging; secrets (`.env`, `samconfig.toml` ignored; only the public demo key is tracked); live HSTS/`nosniff`/`no-cache`; em dashes absent from every deployed page and `talks/`; `npm audit` root 1 moderate (dev-only), `mobile/` 7 already recorded.

**Deploy needed to close I-1, I-2, I-3 and M-3 in production:** SAM (ScoreFunction only), `demo-deploy` (spec), `data-deploy web-deploy` (index.html + changes page), `talks-deploy`.
