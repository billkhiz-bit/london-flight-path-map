---
name: preflight
description: Run all quality checks before committing Sky Score code. Covers frontend JS/HTML, Python backend + root test suites, ESLint, ruff, API-URL drift, and Playwright.
allowed-tools: Bash, Read, Grep, Glob, Agent
argument-hint: "[--fix to auto-fix] [--skip-e2e to skip Playwright]"
---

# Sky Score Preflight

Run before every commit.

## The one command

```bash
sh scripts/preflight.sh
```

Pass `$ARGUMENTS` straight through (`--fix`, `--skip-e2e`).

**Do not re-implement the checks here.** They live in `scripts/preflight.sh`
so that `make preflight`, `npm run preflight` and this skill all run the same
things and report the same exit code. A checklist in a markdown file drifts
from the script and cannot itself be executed or tested; this one did.

**Read the exit code, not the output.** The script prints a `RESULT: PASS` /
`RESULT: FAIL` line and exits 0 or 1 accordingly. Do not pipe it to `tail`,
`head` or anything else when you care whether it passed — a shell pipeline
exits with the status of its LAST stage, so `preflight | tail` is always 0.

## History, so this is not undone by accident

Rewritten 2026-07-27 after the gate lied in both directions in a single
session:

- **False green.** `make preflight` reported success while running nothing
  at all: `make` is not on PATH in Git Bash on this machine, and every check
  in the old skill was piped to `tail`, so no failure could ever surface.
- **False red.** The Playwright suite reported 14 failures that were all
  spurious — it runs against the *live* CloudFront site and the uncapped
  worker pool produced timeouts indistinguishable from assertion failures.
  Measured: 14 failed / 2 passed at the default, 16 passed at `--workers=2`.
- **A silent gap.** The root suite (`tests/`, 167 tests covering the NSPL
  loader, the bulk scorer and the handler contracts) was never in the gate at
  all. Only `backend/tests` ran.
- **A no-op reading as a tick.** The `pip-audit` step looped over
  `backend/lambdas/*/requirements.txt`, which matches nothing — no Lambda has
  one, every handler is stdlib plus the runtime's boto3 — and swallowed the
  result with `|| true`.

## What blocks, and what does not

**Blocking** (any failure exits 1): ESLint · html-validate · ruff over
`backend/lambdas` *and* `scripts/` + `tests/` · pytest backend · pytest root ·
API base-URL drift · Playwright at `--workers=2`.

**Advisory** (reported, never blocking):

- **Prettier.** Every HTML/JS file in the repo deviates. Bringing `index.html`
  into line is a 19,205-line diff on an 8,462-line deployed file. That is a
  decision to review deliberately, not a chore for a pre-commit hook, and
  blocking on it would make the gate permanently red — which is precisely how
  a gate gets ignored.
- **`npm audit`.** `dependencies` is empty and the site has no build step, so
  nothing from `node_modules` ships. `npm audit --omit=dev` is 0; the dev tree
  carries a changing handful of advisories in the lint toolchain (5 on
  2026-09-14, 2 high) - read the number off `npm audit`, not off this line.

If you change what blocks, change `scripts/preflight.sh` — not this file.

## After the script passes

The script covers everything mechanical. These still need judgement, so run
them on the **changed files** when the diff warrants it:

1. **security-guidance** plugin — always for `backend/lambdas/**`,
   `template.yaml`, or anything touching auth, IAM or user input.
2. **code-review** plugin — on the changed files.
3. **frontend-design** plugin — when `index.html` or a funnel page changed.

## Non-negotiable tests

If either of these breaks, the API-key revocation invariant is broken and the
commit does not go out regardless of what else is green:

- the signup race-recovery test (I-N6)
- the `_safe_revoke_orphan_key` prefix guard (N-Code-1)

## Gotchas

- **A preflight that stops mid-run at `Playwright e2e` with no FAIL line is
  usually the HARNESS, not the gate (2026-09-14).** Claude Code's background
  runner kills a task when system memory runs low, and the Playwright stage
  is where the headless Chromium workers push it over. It happened twice in a
  row with ~6 GB free on a 32 GB machine while Chrome held 12 GB across 61
  processes; the third run passed unchanged once Chrome was trimmed to ~9 GB.
  Tell-tales: the log ends on a stage NAME with no verdict, the notification
  says "stopped because the system is running low on memory", and every stage
  before it is PASS. Do not read it as flaky, do not retry blind, and do not
  reach for `--skip-e2e` (that is a green run by not looking). Check
  `Get-Process | Group-Object Name` for the memory hog, ask Bill to close
  tabs, kill any orphaned `chrome-headless-shell.exe` the dead run left
  behind, then run ONCE more. Log the run to a file with the exit code
  appended (`sh scripts/preflight.sh > log 2>&1; echo EXIT=$? >> log`) so a
  killed run still shows how far it got.
- **`sed -i` on Git Bash strips EVERY CR from a CRLF file, even when the
  substitution touches one line (2026-09-18).** The diff shows the one line
  you meant; `file` shows "with CRLF line terminators" become plain "ASCII
  text" across all 193 lines. Most of this repo's docs are CRLF in the working
  tree (`CLAUDE.md`, `OPERATIONS.md`, `HANDOVER.md`, this file), so a sed on
  any of them rewrites the whole file and the next `git checkout` or a
  shell gate that compares bytes goes red on a tree that looks identical
  (the 17 Sep `check_log_retention.sh` red was the same family). Use the
  Edit tool on any CRLF file; if a sed is unavoidable, run `file` (or
  `git ls-files --eol`) before and after and restore with `sed -i 's/$/\r/'`
  on the now-LF file. Same lesson as memory
  `feedback-bash-heredoc-and-crlf-patching`, sixth instance.
- **A green preflight says nothing about what git will commit (2026-10-03).**
  Every gate reads the working tree, so a file an old `.gitignore` line
  swallows passes all of them here and is missing on any fresh clone. An
  unanchored `reports/` (meant for a test-output folder at the root) hid
  `preview/reports/` - a page and two PDFs that five gates read - and
  `git status` still printed `?? preview/`, which reads as "all of it is
  new". Before the first commit of a new directory run
  `git add -n <dir>` and compare the list with `ls -R`; anchor ignore
  lines for root folders with a leading slash.
- **A local server the SESSION started can turn a blocking stage red
  (2026-10-18).** Claude served an internal preview with
  `python -m http.server 8941` while preflight ran in the background, and
  "front page is a tool, not a picture" (`tests/front-page.mjs`, which starts
  its own server on 127.0.0.1:8941) failed with `EADDRINUSE`: a red gate with
  nothing wrong in the code under test. The tests bind fixed ports (measured
  that day: 8000 8099 8123 8765 8921-8926 8931 8934 8937 8941 8942 8955 8962).
  Before serving anything locally, list them with
  `grep -rhoE '(127\.0\.0\.1|localhost):[0-9]{4,5}|PORT\s*=\s*[0-9]{4,5}' tests scripts`
  and pick one outside them (8977 was free). When a stage fails with
  `EADDRINUSE`, look for a server the session started before suspecting the
  code, stop it, and re-run; never commit past the red run.
  **Second form, same day: stopping a background preflight does not stop
  it.** On Windows, stopping the harness task ended only its wrapper shell;
  `sh scripts/preflight.sh` and its test servers ran on for 40 minutes beside
  the next run, and "every city switches" (`tests/city-switch.mjs`, port 8924)
  failed with `EADDRINUSE` against the orphan. After stopping one, find the
  tree with `Get-CimInstance Win32_Process | Where-Object CommandLine -match
  'preflight\.sh'` and end it with `taskkill /T /F /PID <the oldest sh.exe>`,
  then confirm no `tests/*.mjs` node or `chrome-headless-shell` is left.
- **The e2e stage tests the LIVE site, not the working tree** (2026-10-23). `playwright.config` sets `baseURL` to
  the CloudFront origin, so a spec that waits for something only the source has (the front page's `#ans-example`,
  built before its deploy) turns preflight red until the deploy. Make such a wait apply only where the page
  carries the element (`settled` in `tests/e2e/accessibility.spec.js`); never read that red as a code defect
  without checking which site it ran against.
- **A background run wrapped as `sh scripts/preflight.sh > log; echo PREFLIGHT_EXIT=$?` reports exit 0 to the
  harness whatever happened** (2026-10-23: two "completed (exit code 0)" notifications were `RESULT: FAIL`). Read
  the echoed `PREFLIGHT_EXIT=` value and the log's `RESULT:` line, never the notification's exit code.
- **Check a claim against the artefact before it goes into a commit message** (2026-10-23). A message said a photo
  showed "no faces but Bill's", copied from a memory note; the photo showed two other people. Open the image, diff
  or data the message describes first: a pushed message cannot be corrected without rewriting history.
