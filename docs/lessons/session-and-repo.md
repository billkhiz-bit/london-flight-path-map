# Session rhythm and repository location

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> Canonical clone, planning docs, the PUSH ruling, the welcome message.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 1-72 (2026-10-16) -->
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

**2026-07-19 update:** the `Claude Projects\Sky Score.bat` launcher was found still pointing at the OneDrive clone and has been repointed to the projects/ path. Both stale Desktop copies (`london-flight-path-map` and `London Flight Path Map`) were verified fully contained in this clone's history and are scheduled for deletion. Their unique March-era artefacts (original `london_flight_paths.py`/`.html` prototype, March `samconfig.toml`, old `.claude/commands`) are preserved in `archive/prototype-2026-03/` here. The 4 fastlane ASC vars (`ASC_ISSUER_ID`/`ASC_KEY_ID`/`ASC_KEY_FILE_PATH`/`FASTLANE_SKIP_DOCS`) existed only in the OneDrive clone's `.env` — merge into this clone's `.env` before relying on fastlane locally.

## Rolling planning docs

Two project-level planning docs live alongside this file. Read them when picking up work between sessions:
- **`ROADMAP.md`**, the broader rolling plan: vision, three parallel tracks (consumer site, B2B API, competitions/outreach), near-term task list with deadlines, open decisions. The source of truth for "what next".
- **`EXPANSION.md`**, which cities and countries are reachable and what each costs. Read before proposing a new city: the NATION is the unit of work, not the city. Every source behind an English city-region is already national (NSPL, HPI, Price Paid, ONS crime, DEFRA air/road/aircraft, EA flood), so England is nearly free; Wales loses schools, road noise and flood to different publishers, and Scotland changes publisher for five of six components. Ranked on measured 2025 transaction volume - we currently cover 34.6% of English and Welsh sales.
- **`OUTREACH_TARGETS.md`**, who would value the data (aggregated especially), in order, with the pre-send gates (ICO fee, DKIM, rename), the facts safe to quote with their source, a "never say" list and a template per group. **Start every outreach email from it**, and add any new measured fact to its table rather than quoting from memory. The repo is public, so it names organisations only, never people or addresses.
- **`archive/BUILDATHON_PLAN_2026.md`**, the Shared Futures Buildathon plan (event was 2026-06-07). Archived 2026-08-24, 78 days after the event, exactly as its own header promised.

When a task ships or a decision lands, update the relevant doc rather than relying on chat memory.

After any substantial change (feature shipped/removed, audit item closed, vendor relationship changed), follow the **echo-work discipline** in the global `~/.claude/CLAUDE.md` — propagate to README, ROADMAP, LICENSING, AUDIT_REPORT, OUTREACH_LOG, memory, .env.example, tests, AWS surfaces. Doing it now is 2-3× cheaper than re-deriving the context tomorrow. For Sky Score specifically, the "echo loop" almost always touches: README.md (Lambda counts), ROADMAP.md (open decisions resolved), LICENSING.md (data sources), and `~/.claude/projects/.../memory/MEMORY.md` (cross-session facts).

**Cross-project echo**: substantial Sky Score waves (release submitted, big pivot landed, competition outcome confirmed, new submission added/dropped) also belong in the 90-day builder roadmap at `C:\Users\bilal\OneDrive\Desktop\90_DAY_ROADMAP.md` under the "Daily Progress Log" section. Keep that file strategic — competitions, pivots, deadlines, headline wins — not wave-level commit detail. The 90-day file is opened via the `90-Day Roadmap.bat` shortcut in `OneDrive\Desktop\Claude Projects\` to seed cross-session context across all Bill's projects, so Sky Score wave logs going there means future Claude sessions on Noor / LedgerAgent / Siraj see Sky Score's state too.

## Before conversation ends

When the user says goodbye, thanks you, or indicates they're done, run `git status` to check for uncommitted changes. If there are any, remind the user:

```
You have unsaved changes. Would you like me to commit them before you go?
```

If they say yes, create a commit with a clear message describing what changed.

**PUSH. The old "keep git local only, never push" line here is SUPERSEDED
(2026-08-27, Bill's ruling.)** It contradicted the global rule that push/pull is
the only safe sync mechanism, and the contradiction was not harmless: it stalled
**21 commits** on a single machine and cost two round-trips in one session to
resolve, because an explicit "never" cannot be overridden by inference. Follow
the global multi-device workflow - `git fetch` early, surface drift,
`git pull --rebase` before pushing if the branch diverged.

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
  /aws-debug Debug Lambda/API Gateway issues (log read restored 2026-09-04)
  /project:test-apis Test all API endpoints
  /project:review Summarise recent changes

Or just describe what you need, I have full context of this project.
```

