# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Compact Instructions

When context fills up, always preserve:
- AWS deployment details (API URL, CloudFront ID, S3 bucket, region)
- The current task the user is working on
- Any file changes made during this session that haven't been committed
- Branding: always "Sky Score", never "London Flight Path Map" in user-facing text

## Before conversation ends

When the user says goodbye, thanks you, or indicates they're done, run `git status` to check for uncommitted changes. If there are any, remind the user:

```
You have unsaved changes. Would you like me to commit them before you go?
```

If they say yes, create a commit with a clear message describing what changed. Keep git local only — never push.

## On conversation start

When the user starts a new conversation (first message, greeting, or asks what they can do), display this welcome message:

```
Sky Score

Available commands:
  /project:deploy-frontend   Upload to S3 + invalidate CloudFront
  /project:deploy-backend    SAM build + deploy Lambdas
  /project:deploy-all        Deploy everything
  /preflight                 Pre-commit quality checks (lint, security, a11y)
  /careful                   Enable production safety mode (blocks destructive AWS commands)
  /aws-debug                 Debug Lambda/API Gateway issues
  /project:test-apis         Test all API endpoints
  /project:review            Summarise recent changes

Or just describe what you need — I have full context of this project.
```

## Project

Sky Score — a full-stack property noise & livability scoring tool for NYC/London, built for the Amazon Nova AI Hackathon. Single-page frontend (`index.html`) backed by 10 AWS Lambda functions orchestrated via SAM.

## Branding

Always use "Sky Score" in all public-facing files and UI text.

## Do NOT add Co-Authored-By lines to git commits

## Quality & Plugins

- Run `/preflight` before every commit — checks ESLint, HTML validation, Prettier, Python lambdas, security, and Playwright tests
- Run `/careful` before touching live AWS resources — blocks destructive commands
- Use `/aws-debug` when Lambda errors or API Gateway 5xx issues occur
- Use **context7** to look up D3.js, AWS SDK, or SAM docs before using unfamiliar APIs
- Use **security-guidance** when editing Lambda functions or API Gateway config
- Use **code-review** on all changed files before committing
- Use **frontend-design** when modifying the UI in index.html

## Build & Deploy

```bash
# Frontend — upload to S3 then invalidate CloudFront
AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"

# Backend — SAM build + deploy (always clean .aws-sam first)
cd backend && rm -rf .aws-sam && AWS_PROFILE=flightmap sam build && AWS_PROFILE=flightmap sam deploy
```

## Architecture

- **Frontend**: Single `index.html` (~3,750 lines) — vanilla JS, D3.js maps, all UI logic inline
- **Backend**: `backend/template.yaml` — SAM/CloudFormation defining 10 Lambdas + API Gateway + DynamoDB
- **Lambda functions** (all in `backend/lambdas/<name>/app.py`):
  - `chat` — Nova 2 Lite for simple queries, Nova Pro for complex reasoning (auto-routed)
  - `multi_agent` — Orchestrator + 3 specialist agents (Noise/Market/Livability) + Synthesiser
  - `analyze_image` — Nova Pro multimodal for property listing photos
  - `analyze_document` — Nova Pro multimodal for EPC certs, surveys
  - `report` — Nova Pro 7-section property reports
  - `favourites` — DynamoDB CRUD for saved properties
  - `transport`, `epc`, `sold_prices`, `nhs` — external data API proxies

## Prototype (Sky Score Radar)

- **Location**: `prototype/index.html` — standalone HTML, no dependencies on main app
- **Live URL**: `https://d1oe4ftwutjpf.cloudfront.net/prototype/index.html`
- **Stack**: Three.js (CDN), CSS2DRenderer for labels, UnrealBloomPass for bloom
- **Features**: 3D wireframe terrain, live flight tracking (OpenSky Network), day/night cycle (real GMT/BST), noise contour rings, borough boundaries, corridor heatmap/timelapse
- **Controls**: `R` Reset, `1-3` Camera presets, `P` Screenshot, `N` Time-lapse, `C` Contours, `B` Boroughs, `L` Live/Sim toggle, `V` Corridor view (Daily/Weekly/Monthly), `T` Timelapse replay, `H` Heatmap toggle
- **Mobile**: Fully responsive — touch button bar replaces keyboard shortcuts, collapsible panels via ☰ menu, breakpoints at 768px and 480px. OrbitControls supports pinch/drag natively.
- **Live Data**: OpenSky Network API via CORS proxy (free, no key). Falls back to simulated flights if unavailable.
- **Analytics**: GoatCounter (same `cubitt33` tracker as main site) — prototype visits appear as `/prototype/index.html`
- **Naming**: Use "Sky Score Radar" for the prototype, "Sky Score" for the main app
- **Deploy**: `AWS_PROFILE=flightmap aws s3 cp prototype/index.html s3://london-flight-map-frontend/prototype/index.html --content-type "text/html" --region eu-west-2`

## AWS Resources

- **API Gateway**: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
- **CloudFront**: `https://d1oe4ftwutjpf.cloudfront.net` (distribution EGSSPJKLFL33M)
- **S3 bucket**: `london-flight-map-frontend` (eu-west-2)
- **DynamoDB table**: `london-flight-map-favourites`
- **Bedrock models**: `us.amazon.nova-2-lite-v1:0` (simple) + `us.amazon.nova-pro-v1:0` (complex/multimodal)
- **IAM**: `flightmap-dev` user, `FlightMapDeployPolicy`
- **Region**: eu-west-2 (London)

## Key Conventions

- All Lambda handlers follow the same pattern: `def lambda_handler(event, context)` with CORS headers
- Chat routing logic: keyword detection in `chat/app.py` determines Lite vs Pro model
- Frontend communicates with backend via fetch to API Gateway endpoints
- SAM stack name: `london-flight-map`

## Known Issues (from audit March 10-12, 2026)

See `AUDIT_REPORT.md` for full details. Remaining items:
- **Hackathon submission** needs demo video and inline screenshots
- **Favourites endpoint** has no authentication (post-hackathon)
- **Accessibility**: zero ARIA attributes (post-hackathon)
- **Live aircraft**: OpenSky Network has limited coverage at night and rate limits (~10 req/min anonymous)

### Fixed March 11:
- Contradictory verdicts ("quiet skies" for noisy areas) — `||` vs `??` bug in scoring + verdict rewrite
- Backend data out of sync with frontend (15 noise mismatches, 4 missing boroughs)
- CORS blocking DELETE on favourites, saved location click-to-navigate broken
- Map overlays invisible (road noise too faint, air quality blend mode, flood WMS blank at city zoom)
- All overlays now zoom-aware with debounced refresh

### Fixed March 12:
- Air quality overlay invisible — replaced WMS-only with borough-level colored polygons (poor/moderate/good)
- Save button missing from borough view — added to `updateSidebar()` alongside postcode view
- Road noise blank at city-wide zoom — added zoom threshold, WMS loads at borough level or closer
- Updated legend to 3-tier air quality scale
- Demo script updated with new overlay behavior
