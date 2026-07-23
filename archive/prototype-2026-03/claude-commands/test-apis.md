Test all Sky Score API endpoints using parallel subagents for speed.

Base URL: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod`

Launch subagents in parallel to test all endpoints simultaneously:

**Agent 1 — Chat + Report (slow endpoints):**
- POST `/chat` with `{"message": "What is Sky Score?", "history": []}`
- POST `/report` with `{"postcode": "SW1A1AA"}`

**Agent 2 — Data APIs (fast endpoints):**
- GET `/transport?postcode=SW1A1AA`
- GET `/epc?postcode=SW1A1AA`
- GET `/sold-prices?postcode=SW1A1AA`
- GET `/nhs?postcode=SW1A1AA`

**Agent 3 — Favourites:**
- GET `/favourites`

## After all agents report back:

Combine into a single results table:
| Endpoint | Status | Response Time | Notes |
|----------|--------|---------------|-------|

If any endpoint fails, read its Lambda code in `backend/lambdas/<name>/app.py` and suggest what might be wrong.
