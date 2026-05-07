# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Compact Instructions

When context fills up, always preserve:
- AWS deployment details (API URL, CloudFront ID, S3 bucket, region)
- The current task the user is working on
- Any file changes made during this session that haven't been committed
- Branding: always "Sky Score", never "London Flight Path Map" in user-facing text

## Canonical repo location

**Use `C:\Users\bilal\projects\london-flight-path-map`** for any work on this repo. The `OneDrive\Desktop\london-flight-path-map` clone was the legacy location; OneDrive's filesystem-level sync can corrupt `.git/` if it interrupts a write mid-transaction (the user's global CLAUDE.md flags this risk explicitly). The OneDrive clone was retired on 2026-05-07 once the in-flight DEFRA loader finished — only `data/` (782 MB of NSPL CSV + DEFRA GeoTIFF, gitignored) was migrated by `mv`; everything else came from `git clone` of the GitHub remote.

If a future session lands you back in `OneDrive\Desktop\london-flight-path-map`, exit and `cd` to the projects/ path before doing anything destructive. If the OneDrive clone has come back from the dead (e.g. someone restored from a backup), prefer running on the projects/ clone and `git pull` to catch up rather than working in OneDrive.

## Rolling planning docs

Two project-level planning docs live alongside this file. Read them when picking up work between sessions:
- **`ROADMAP.md`**, the broader rolling plan: vision, three parallel tracks (consumer site, B2B API, competitions/outreach), near-term task list with deadlines, open decisions. The source of truth for "what next".
- **`BUILDATHON_PLAN.md`**, focused single-purpose doc for the Shared Futures Buildathon (deadline 2026-05-15, event 2026-06-07). Will be archived after the event.

When a task ships or a decision lands, update the relevant doc rather than relying on chat memory.

## Before conversation ends

When the user says goodbye, thanks you, or indicates they're done, run `git status` to check for uncommitted changes. If there are any, remind the user:

```
You have unsaved changes. Would you like me to commit them before you go?
```

If they say yes, create a commit with a clear message describing what changed. Keep git local only, never push.

## On conversation start

When the user starts a new conversation (first message, greeting, or asks what they can do), display this welcome message:

```
Sky Score

Available commands:
  /project:deploy-frontend Upload to S3 + invalidate CloudFront
  /project:deploy-backend SAM build + deploy Lambdas
  /project:deploy-all Deploy everything
  /preflight Pre-commit quality checks (lint, security, a11y)
  /careful Enable production safety mode (blocks destructive AWS commands)
  /aws-debug Debug Lambda/API Gateway issues
  /project:test-apis Test all API endpoints
  /project:review Summarise recent changes

Or just describe what you need, I have full context of this project.
```

## Project

Sky Score, a property noise + livability data tool for UK and NYC. Originally built for the Amazon Nova AI Hackathon; pivoted in May 2026 from "AI-powered" to "data-first" positioning. Consumer site is the marketing engine; the B2B `/v1/score` API is the product. Single-page frontend (`index.html`) backed by 7 active AWS Lambda functions orchestrated via SAM (5 Bedrock Lambdas remain dormant in the template; `live_flights` was removed in May 2026 pending OpenSky licensing).

## Branding

Always use "Sky Score" in all public-facing files and UI text.

## Do NOT add Co-Authored-By lines to git commits

## Quality & Plugins

- Run `/preflight` before every commit, checks ESLint, HTML validation, Prettier, Python lambdas, security, and Playwright tests
- Run `/careful` before touching live AWS resources, blocks destructive commands
- Use `/aws-debug` when Lambda errors or API Gateway 5xx issues occur
- Use **context7** to look up D3.js, AWS SDK, or SAM docs before using unfamiliar APIs
- Use **security-guidance** when editing Lambda functions or API Gateway config
- Use **code-review** on all changed files before committing
- Use **frontend-design** when modifying the UI in index.html

## Build & Deploy

```bash
# Frontend, upload to S3 then invalidate CloudFront
AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"

# Score demo (B2B API tester), same pattern as prototype
AWS_PROFILE=flightmap aws s3 cp score-demo/index.html s3://london-flight-map-frontend/score-demo/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/score-demo/*"

# Backend, SAM build + deploy (always clean .aws-sam first)
# EPC bearer token is required after the 2026-05-30 service migration.
# Source from .env (gitignored); never paste the token into source files or chat.
set -a && source ../.env && set +a && \
  cd backend && rm -rf .aws-sam && \
  AWS_PROFILE=flightmap sam build && \
  AWS_PROFILE=flightmap sam deploy --parameter-overrides \
    EpcBearerToken="$EPC_BEARER_TOKEN"
```

**Local env setup**: copy `.env.example` to `.env` and fill in:
- `EPC_BEARER_TOKEN` — from the My account page on `get-energy-performance-data.communities.gov.uk`

The `.env` file is gitignored. The EPC SAM parameter uses `NoEcho: true` so the value doesn't appear in CloudFormation events. AllowedPattern `^.+$` on the parameter blocks deploys with empty / missing tokens.

**Token rotation**:
- EPC: regenerate from the My account page on `get-energy-performance-data.communities.gov.uk` whenever the token has touched a chat log, terminal scrollback, or any unencrypted persistence
- Update `.env` and redeploy after rotation

## Architecture

- **Frontend**: Single `index.html` (~3,750 lines), vanilla JS, D3.js maps, all UI logic inline
- **Backend**: `backend/template.yaml`, SAM/CloudFormation defining 12 Lambdas (7 active + 5 dormant) + API Gateway + DynamoDB
- **Active Lambdas** (in `backend/lambdas/<name>/app.py`):
  - `score`, B2B scoring engine, API-key gated (`/v1/score`, `/v1/score/batch`, `/v1/regions`)
  - `signup`, self-service API-key issuance
  - `favourites`, DynamoDB CRUD with `X-Device-Token` auth
  - `epc`, MHCLG EPC certificate proxy (bearer-token auth via `EPC_BEARER_TOKEN`)
  - `sold_prices`, HM Land Registry Price Paid Data proxy
  - `transport`, TfL Open Data station + line-status
  - `nhs`, NHS Service Search via OSM Overpass
- **Dormant Lambdas** (in `template.yaml` but not surfaced in the UI as of May 2026; kept for potential re-introduction):
  - `chat`, `multi_agent`, `analyze_image`, `analyze_document`, `report` — all Bedrock Nova Pro/Lite. Lambda has zero idle cost on on-demand pricing; re-enabling means unhiding the UI block, not redeploying.
- **Removed**: `live_flights` (OpenSky proxy) — terminated in May 2026 pending OpenSky's required written licensing agreement for operational use. Lambda code lives in git (last working commit: `a214ba0`); restore + add OpenSky params back to template + flip the prototype's `liveLicensed` flag to revive.

## Prototype (Sky Score Radar)

- **Location**: `prototype/index.html`, standalone HTML, no dependencies on main app
- **Live URL**: `https://d1oe4ftwutjpf.cloudfront.net/prototype/index.html`
- **Stack**: Three.js (CDN), CSS2DRenderer for labels, UnrealBloomPass for bloom
- **Features**: 3D wireframe terrain, day/night cycle (real GMT/BST), noise contour rings, borough boundaries, corridor heatmap/timelapse, simulated flight tracks (live OpenSky data removed pending licensing — see Active Lambdas note above)
- **Controls**: `R` Reset, `1-3` Camera presets, `P` Screenshot, `N` Time-lapse, `C` Contours, `B` Boroughs, `V` Corridor view (Daily/Weekly/Monthly), `T` Timelapse replay, `H` Heatmap toggle
- **Mobile**: Fully responsive, touch button bar replaces keyboard shortcuts, collapsible panels via ☰ menu, breakpoints at 768px and 480px. OrbitControls supports pinch/drag natively.
- **Analytics**: GoatCounter (same `cubitt33` tracker as main site), prototype visits appear as `/prototype/index.html`
- **Naming**: Use "Sky Score Radar" for the prototype, "Sky Score" for the main app
- **Deploy**: `AWS_PROFILE=flightmap aws s3 cp prototype/index.html s3://london-flight-map-frontend/prototype/index.html --content-type "text/html" --region eu-west-2`

## AWS Resources

- **API Gateway**: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
- **CloudFront**: `https://d1oe4ftwutjpf.cloudfront.net` (distribution EGSSPJKLFL33M)
- **S3 bucket**: `london-flight-map-frontend` (eu-west-2)
- **DynamoDB table**: `london-flight-map-favourites`
- **Bedrock models** (used only by dormant Lambdas): `us.amazon.nova-2-lite-v1:0` (simple) + `us.amazon.nova-pro-v1:0` (complex/multimodal)
- **IAM**: `flightmap-dev` user, `FlightMapDeployPolicy`
- **Region**: eu-west-2 (London)

## Key Conventions

- All Lambda handlers follow the same pattern: `def lambda_handler(event, context)` with CORS headers
- Frontend communicates with backend via fetch to API Gateway endpoints
- SAM stack name: `london-flight-map`

## Submissions

- **Amazon Nova AI Hackathon** (March 2026): Submitted, won $200 AWS credits (blog-post category). Video demo (3:10, with voiceover) complete.
- **Red Bull Basement** (submitted 2026-04-12): Awaiting shortlist decision; if invited, record 60-second pitch video. Positioning: "local friend" AI for renters with health risks.
- **Emergent Ventures / Mercatus** (submitted 2026-04-20): £45,000 ask over 9 months. Awaiting response (form promises within ~1 week). Draft at `Desktop/emergent-ventures-application.txt`.
- **Luma event** (applied 2026-04-23, `luma.com/vy4bnkom`): Submitted Sky Score as the idea (3-sentence pitch). Form fields: name, email, LinkedIn, GitHub (`billkhiz-bit`), phone, cofounder status. No project-URL field on the form. Event name/theme TBC.

Related separate project (not in this repo): **LedgerAgent** is a semi-finalist in the AWS 10,000 AIdeas Competition.

## Known Issues

See `AUDIT_REPORT.md` (last full audit 2026-05-06, refreshed 2026-05-07) for the live list. Standing items not yet addressed:
- **Borough metadata duplication** across chat/multi_agent/score Lambdas (I4) — extract to shared module
- **No DLQ / retry config** on async Lambdas (I6)
- **Stale `PROJECT_DOCUMENTATION.md`** sections (I14, partial fix in `0c20451`)

Most of the May-6 critical findings have shipped fixes — see `AUDIT_REPORT.md` for the triage column.
