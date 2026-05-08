---
name: preflight
description: Run all quality checks before committing Sky Score code. Covers frontend JS/HTML, Python backend lambdas, Playwright tests, ESLint, and AWS SAM template.
allowed-tools: Bash, Read, Grep, Glob, Agent
argument-hint: "[--fix to auto-fix issues]"
---

# Sky Score Preflight

Run before every commit. This project is a dual-stack app: vanilla JS frontend (`index.html`), Python Lambda backend, AWS SAM infrastructure.

## Checks (run in order)

### 1. ESLint
```bash
npm run lint 2>&1 | tail -20
```
- If `--fix` passed, run `npm run lint:fix` instead

### 2. HTML Validation
```bash
npm run lint:html 2>&1 | tail -20
```

### 3. Prettier Format Check
```bash
npm run format:check 2>&1 | tail -10
```
- If `--fix` passed, run `npm run format` instead

### 4. Python Lambda Checks
```bash
cd backend && ruff check lambdas/ 2>&1 | tail -20
```
- Verify Python lambdas parse without errors
- Check for hardcoded secrets or credentials

### 4b. Backend Tests
```bash
cd backend && python -m pytest 2>&1 | tail -10
```
- Must be all green before commit. The signup race-recovery test (I-N6) and the
  `_safe_revoke_orphan_key` prefix guard (N-Code-1) are non-negotiable: if they
  break, the API key revocation invariant is broken.

### 4d. API URL drift check (I-N5)
```bash
# All HTML/JS files must reference the same API Gateway host. If a Lambda
# is redeployed and APIGW issues a new id, every file referencing the old
# host will silently break — this catches the drift before commit.
HOSTS=$(grep -hoE 'https?://[a-z0-9]+\.execute-api\.eu-west-2\.amazonaws\.com' \
  index.html score-demo/*.html api/*.html tests/*.mjs 2>/dev/null | sort -u | wc -l)
if [ "$HOSTS" -ne 1 ]; then
  echo "FAIL: API base URL drift across files. Found $HOSTS distinct hosts."
  grep -nE 'https?://[a-z0-9]+\.execute-api\.eu-west-2\.amazonaws\.com' \
    index.html score-demo/*.html api/*.html tests/*.mjs | head -10
  exit 1
fi
echo "PASS: All API URL refs use the same host."
```

### 4c. Python Dependency Vulnerabilities (pip-audit)
```bash
# Run from each lambda dir that has its own requirements.txt.
# pip-audit hits the PyPI Advisory Database; needs network.
for req in backend/lambdas/*/requirements.txt; do
  echo "=== $req ==="
  pip-audit -r "$req" --strict 2>&1 | tail -10 || true
done
```
- Install once: `pip install pip-audit`
- `--strict` means any reported vuln is a hard fail. Triage policy: a CVSS
  >= 7.0 finding blocks the commit; lower-severity findings get logged to
  `AUDIT_REPORT.md` and addressed in the next session.
- Note: each Lambda has its own `requirements.txt` because SAM builds them
  in isolated containers. The deploy bundles only what each function imports.

### 5. Security
- Run **security-guidance** plugin on changed files
- Check for XSS in dynamic HTML rendering
- Verify API keys are loaded from environment, not hardcoded
- Check SAM template for overly permissive IAM policies

### 6. Code Review
- Run **code-review** plugin on changed files
- Check for accessibility issues in HTML

### 7. Playwright Tests (if available)
```bash
npm run test:e2e 2>&1 | tail -20
```
- Only run if Playwright is installed and tests exist

## Output
```
PREFLIGHT, Sky Score
======================
[PASS/FAIL] ESLint
[PASS/FAIL] HTML validation
[PASS/FAIL] Prettier
[PASS/FAIL] Python lambdas
[PASS/FAIL] Backend tests (pytest)
[PASS/FAIL] pip-audit (PyPI vuln scan)
[PASS/FAIL] Security scan
[PASS/FAIL] Code review
[PASS/FAIL] Playwright tests

Issues: n found, n fixed
```

If `--fix` is passed, auto-fix what's possible. Otherwise report only.
