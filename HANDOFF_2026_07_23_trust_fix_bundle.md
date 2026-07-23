# Handoff — 2026-07-23 · Trust-fix bundle shipped + deployed

> Session record for the post-Haatch trust-fix wave. Brief:
> `Desktop/SKY_SCORE_SITE_SESSION_BRIEF_2026-07-23.md`. Context: Aini Hashim
> (Haatch) passed warm on 23 Jul — progress needs commercial proof (a signed
> pilot or LOI plus outcome evidence) — which lifted the 19 Jul site freeze,
> including the pricing page. Everything below is live on skyscore.co.uk.

## What shipped (all 8 brief changes)

| # | Change | Where |
|---|---|---|
| 1 | Founder/About + contact identity | `/pricing` + `/api/` founder blocks; footer Contact link; privacy §1. "Bilal Khizar, finance professional turned AI builder", nouns and numbers only |
| 2 | Privacy notice on the API signup form | `score-demo/index.html` (notice + working `#signup` anchor — the `/api/` deep link had been silently broken); `privacy.html` §2a rewritten (it flatly denied the signup form existed; now documents purpose, lawful basis, storage incl. APIGW key metadata, retention, deletion route) |
| 3 | Pricing page (NEW) | `/pricing` — 90-day pilot £2,500 + VAT as centrepiece (day-0 metric, day-45 review, day-90 written evidence report, credited in full against first-year licence), Free tier (live), **Professional £499/mo "Launching"** (Bill's in-session decision, replacing the £49 proposal — £49 undercut the pilot/licence ladder), Enterprise POA, founder block. GoatCounter events on every CTA. £12k floor printed nowhere |
| 4 | API reference rendering fix | Swagger UI 5.17.14 self-hosted at `score-demo/vendor/` (sha384 of each file verified against the previously pinned SRI values). Removes the unpkg.com single point of failure — unpkg regenerated the pinned files on 8–9 Jul, and any byte drift against the SRI hashes silently blanked the page. GoatCounter added so failures are visible |
| 5 | App Store link | Site footer (`appstore-footer-click` event) + `/pricing` and `/api/` founder blocks. v1.0.21 confirmed live via iTunes lookup |
| 6 | DEFRA freshness + badge honesty | Legend: "Round 4 is the latest official strategic noise mapping round; DEFRA expects Round 5 around 2027." METHODOLOGY §7 echo + changelog. Air-quality AND flood detail-panel badges corrected to "borough-level rating (curated)" — those layers fill from `data/borough-extra.json`, not DEFRA/EA/EPA/FEMA services |
| 7 | api.skyscore.co.uk | AWS side complete: edge custom domain + us-east-1 wildcard cert + base-path mapping → `prod`. **Waiting only on the Cloudflare CNAME (see Pending)** |
| 8 | Contact email swap | `support@skyscore.co.uk` (live since 2026-05-21 per `EMAIL_SETUP.md`; MX re-verified 23 Jul) replaces `billkhiz@gmail.com` on every public surface: footer, `/api/` incl. JSON-LD, `/pricing`, `robots.txt`, `.well-known/security.txt`, SUPPORT.md, SUBPROCESSORS.md |

Also decided: **livability convention stays** (US "livability" in brand
phrases/metadata, British "Liveability" as the score component — deck already
mirrors the site). **Consumers stay free.**

## Bonus fixes found along the way

- **GoatCounter was CSP-blocked on every page.** `count.js` delivers via
  `sendBeacon` (connect-src) with an `<img>` fallback (img-src); the host was
  only ever in script-src. All five pages fixed. **Historic funnel-event
  numbers are undercounts.**
- **CI had failed every push since 18 May** — three stacked causes: stale
  chat e2e specs + an 8-vs-7 layer-toggle count (chat UI and live-flights
  toggle were removed in May), root pytest dying at collection on the removed
  chat Lambda, and ruff-format drift across all seven lambda files. All
  fixed; CI now gates on the maintained `backend/tests` suite (62/62). The
  legacy root suite's 21 stale tests (epc/favourites/nhs) need a triage
  session.
- **`make web-deploy` uploaded privacy to a dead S3 key.** The
  `sky-score-rewrite-index` CloudFront function rewrites extensionless paths
  to `<path>/index.html`, so the flat `privacy` key was never served — live
  `/privacy` had been a stale manual copy for months. Makefile fixed; dead
  keys deleted; CLAUDE.md documents the mapping.
- **Signup Lambda log hygiene** (backend deployed 23 Jul): raw emails no
  longer logged to CloudWatch; retention documented (see Pending — one
  console click). CFN cannot adopt the auto-created log group
  (AlreadyExists, rollback observed); IaC import is a logged follow-up.
- Stale docs corrected: template holds only the 7 active Lambdas (the
  "12 Lambdas (7 active + 5 dormant)" claim was wrong), SUPPORT.md's
  key-less liveness probe, SUBPROCESSORS' Google Play tense + GoatCounter
  scope, `.gitignore` patterns that silently excluded the archived prototype.

## Verification evidence

- Preflight per commit: ESLint 0 errors; html-validate green across all 7
  public pages (gate widened in `package.json`); Prettier clean; ruff +
  `backend/tests` 62/62; API-host drift check = 1 host; adversarial review
  workflow (security dimension) + inline correctness/honesty/a11y sweeps.
- Post-deploy: `/pricing` 200 with £2,500/£499/founder/CTA strings;
  `/privacy` serving the corrected §2a + 2026-07-23 date;
  `tests/live-mobile-verify.mjs` PASS at 360/390/414 (classic layout, zero
  overflow); e2e 16/16 against production; EPC + `/v1/score` +
  `/v1/regions` (with key) + signup OPTIONS all healthy post-backend-deploy.

## Pending on Bill

1. **EPC bearer token rotation — oldest open security item.** `.env` is
   byte-identical to 7 May (the in-session "rotated + updated" answer did not
   reach the file; live EPC still works, so the old exposed token remains
   valid). Regenerate on the EPC service's My account page →
   `EPC_BEARER_TOKEN=...` in `.env` → `cd backend && sam deploy`
   (samconfig.toml now exists locally; it never migrated from the OneDrive
   clone and is gitignored).
2. **Cloudflare DNS** — activate api.skyscore.co.uk:
   `CNAME api → d1pr4crjutz9z8.cloudfront.net`, **DNS only (grey cloud)**.
   Then next session: swap the raw execute-api URLs out of METHODOLOGY.md
   (lines 4 + 744), the `/api/` curl sample, and `openapi.yaml` servers.
3. **One console click**: CloudWatch Logs →
   `/aws/lambda/london-flight-map-SignupFunction-vLApmPCZyQTD` → Edit
   retention → 30 days (`flightmap-dev` lacks `logs:PutRetentionPolicy`).
4. **`git push`** — local master is ahead of origin (8 commits,
   `7eb1984..89a7608`); pushing is user-only by project rule. CI should go
   green on this push for the first time since May.
5. Gmail MCP re-auth (enables an end-to-end support@ delivery check);
   Migadu/DKIM (~€19/yr) before any cold B2B outreach sent *from* the domain.

## Session commits (local master, oldest first)

| Commit | What |
|---|---|
| `7eb1984` | Housekeeping: 19 Jul docs echo, archive, stale e2e specs fixed |
| `818374f` | Trust-fix bundle: pricing + pilot, founder identity, privacy truth, honest badges |
| `476a8dc` | Trust-fix doc surfaces (METHODOLOGY, LICENSING, SUPPORT, SUBPROCESSORS, sitemap, robots, security.txt, package.json) |
| `e0920eb` | CI un-broken; pricing joins web-deploy |
| `9a480a4` | Professional tier £499/mo (user decision) |
| `5fc4d10` | Merge `site-trust-fixes-2026-07-23` |
| `4fd1d37` | Deploy fixes: log-group AlreadyExists + SUPPORT probe |
| `2cdade2` | Makefile: `<name>/index.html` key fix |
| `89a7608` | Echo work: README, ROADMAP, CLAUDE |

## Cross-references

- `ROADMAP.md` — 2026-07-23 last-reviewed entry (canonical state)
- `memory/` — `project-trust-fix-2026-07-23`, `project-pricing-ladder`,
  `feedback-cloudfront-extensionless-s3-keys`,
  `feedback-goatcounter-csp-beacon`, `feedback-gitbash-shell-gotchas`
- `Desktop/90_DAY_ROADMAP.md` — July 23 outcome bullet
- `Desktop/SKY_SCORE_PILOT_ONE_PAGER.md` — contact slot now
  `support@skyscore.co.uk · skyscore.co.uk/pricing`
