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
  carries 4 high-severity advisories in the lint toolchain.

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
