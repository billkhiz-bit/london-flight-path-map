Run a pre-deploy health check on Sky Score using parallel subagents for speed.

Launch 3 subagents in parallel:

**Agent 1 — Frontend check:**
Read `index.html` and check:
- API base URL points to production (`https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`)
- No localhost or hardcoded test URLs remain
- All branding says "Sky Score" (not "London Flight Path Map" in user-visible text)

**Agent 2 — Backend check:**
Read `backend/template.yaml` and check:
- All Lambda functions have reasonable timeout and memory settings
- CORS headers are configured on all API endpoints
- No test/debug environment variables left in

Then check each Lambda's `app.py` in `backend/lambdas/*/app.py`:
- No hardcoded API keys or secrets
- Error handling returns proper CORS headers
- Bedrock model IDs are correct (`us.amazon.nova-2-lite-v1:0` and `us.amazon.nova-pro-v1:0`)

**Agent 3 — Git status:**
Run `git status` and `git diff --stat` to check for uncommitted changes.

## After all agents report back:

Combine the results into a single summary:
- ✓ or ✗ for each check
- List any issues found
- Recommend whether it's safe to deploy
