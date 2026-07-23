Prepare the Sky Score hackathon submission using parallel subagents. Deadline: March 17, 2026.

Launch 3 subagents in parallel:

**Agent 1 — Documentation review:**
Read `HACKATHON_SUBMISSION.md` and `PROJECT_DOCUMENTATION.md`. Check:
- Are all claims backed by actual code?
- Missing screenshots or demo evidence?
- Documentation quality and completeness
- Any gaps that could be strengthened?

**Agent 2 — Live site health:**
- Fetch `https://d1oe4ftwutjpf.cloudfront.net` and confirm it loads
- POST to `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/chat` with `{"message": "hello", "history": []}` to test API
- Report whether the live app is working

**Agent 3 — Code quality scan:**
- Read `backend/template.yaml` and count AWS services used
- Scan `backend/lambdas/*/app.py` and count Nova integration modes
- Check for any TODO comments, debug code, or hardcoded test data

## After all agents report back:

Score the submission against hackathon criteria:
- Innovation / creativity
- Use of AWS services (target: 10)
- Use of Amazon Nova (target: 6 modes + multi-agent)
- Technical complexity
- User experience
- Documentation quality

Then provide a prioritised action list ordered by impact — what to fix first before submission.
