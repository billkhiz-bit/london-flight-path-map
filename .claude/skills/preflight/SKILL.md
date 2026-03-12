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
PREFLIGHT — Sky Score
======================
[PASS/FAIL] ESLint
[PASS/FAIL] HTML validation
[PASS/FAIL] Prettier
[PASS/FAIL] Python lambdas
[PASS/FAIL] Security scan
[PASS/FAIL] Code review
[PASS/FAIL] Playwright tests

Issues: n found, n fixed
```

If `--fix` is passed, auto-fix what's possible. Otherwise report only.
