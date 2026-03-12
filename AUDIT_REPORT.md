# Sky Score — Full Project Audit Report
**Date:** March 10-11, 2026 | **Deadline:** March 17, 2026

---

## Critical — Fix Before Submission

### BUG: NHS distances are doubled
- **File:** `backend/lambdas/nhs/app.py`, line 98
- **Issue:** Haversine formula has `R * 2 * 2` instead of `R * 2` — all NHS GP distances show as 2x actual
- **Status:** FIXED

### PROJECT_DOCUMENTATION.md is severely outdated
- Says 9 Lambdas (should be 10 — missing MultiAgent)
- Says ~2,700 lines frontend (actual: 3,898)
- Says 5 Nova modes (should be 6 + multi-agent)
- Says 7 data sources (should be 10+)
- Says 30 NYC neighbourhoods (should be ~151)
- Score formula outdated (missing Liveability factor, 5 buyer personas)
- Still says "London Flight Path Map" throughout (should be "Sky Score")
- Missing /multi-agent API endpoint and multi_agent in file structure
- **Status:** NEEDS REWRITE

---

## Backend Issues

### Branding (old name references)
| File | Line | Issue | Status |
|------|------|-------|--------|
| template.yaml | 3 | Description says "London Flight Path Map - Backend API" | FIXED |
| template.yaml | 28 | Description says "London Flight Path Map API" | FIXED |
| transport/app.py | 47 | User-Agent header says `LondonFlightMap/1.0` | FIXED |

### Configuration
| File | Line | Issue | Status |
|------|------|-------|--------|
| template.yaml | Report timeout | 60s too tight for 2048-token Nova Pro generation | FIXED to 90s |
| transport/epc/sold_prices/nhs | CORS | Missing `Authorization` in AllowHeaders (inconsistent with AI Lambdas) | Noted |

### Security
| File | Severity | Issue | Status |
|------|----------|-------|--------|
| favourites/app.py | MEDIUM | No authentication — any client can read/write/delete any user's favourites | Noted (post-hackathon) |
| report/app.py | LOW | `str.format(**location_data)` could crash on curly-brace values | Noted |

### Code Quality
| File | Line | Issue | Status |
|------|------|-------|--------|
| analyze_image/app.py | 3 | Unused `import base64` | FIXED |
| favourites/app.py | 28-34 | Convoluted Decimal-to-float conversion | Noted |

---

## Frontend Issues

### Branding
- Zero instances of "London Flight Path Map" in user-visible text
- One internal localStorage key `flightmap_device_id` (line 3224) — not user-visible

### Dead Code (can be removed)
| Line | Item | Notes |
|------|------|-------|
| 2434 | `renderFlightPaths()` | Superseded by `renderCityFlightPaths()` |
| 2676 | `renderAirports()` | Superseded by `renderCityAirports()` |
| 1744 | `fetchCrimeData()` | Never called — crime data comes from static objects |
| 1762 | `renderCrimeResult()` | Companion to above, never called |
| 3357 | `getActiveBoroughExtra()` | Never called — code uses `getExtraData()` |
| 547 | `LONDON_CENTER` | Duplicated in `CITIES.london.center` |
| 550 | `BOROUGH_POSTCODES` | 29-entry object, never referenced |
| 560 | `BOROUGH_COORDS` | 29-entry object, never referenced |
| 1408 | `postcodeMarker` | Declared, never used |
| 1413 | `defraImages` | Declared, never used |
| 2184 | `acResults` | Assigned, never read |
| 2498 | `currentFlights` | Assigned, never read |

### Console Statements (11 total)
All in `catch` blocks (console.warn/console.error). Acceptable for production — useful for debugging.

### Missing .catch() on Promise Chains
Lines 3127, 3138, 3142, 3145 in `updateSidebarPostcode()` — low risk since underlying functions have internal try/catch.

### Accessibility
Significant gap — zero ARIA attributes, no labels, no keyboard navigation. Full compliance is post-hackathon work.

### Other
- Line 3889: Fragile resize handler calls `renderNycBoroughs()` without features argument
- Lines 3833-3848: Chat uses `innerHTML +=` (should use `insertAdjacentHTML`)

---

## Documentation Issues

### HACKATHON_SUBMISSION.md — GOOD
- All technical claims verified accurate
- Well-structured, compelling narrative
- Zero grammatical errors
- **Missing:** Demo video link and inline screenshots (recommended for winning entries)

### README.md — GOOD
- Branding correct ("Sky Score" throughout)
- All stats accurate and up-to-date
- **Minor:** Claims MIT license but no LICENSE file exists

### .gitignore — TOO MINIMAL
Only excludes `backend/samconfig.toml` and `backend/.aws-sam/`. Updated to include `.claude/`, `__pycache__/`, `.env`, OS files.

---

## Priority Action List (ordered by impact)

1. ~~Fix NHS haversine bug~~ DONE
2. ~~Fix branding in template.yaml and transport/app.py~~ DONE
3. ~~Increase report Lambda timeout to 90s~~ DONE
4. ~~Remove unused import in analyze_image/app.py~~ DONE
5. ~~Update .gitignore~~ DONE
6. ~~Rewrite PROJECT_DOCUMENTATION.md~~ DONE (fully updated with correct stats)
7. Add demo video to hackathon submission
8. Add screenshots to hackathon submission
9. ~~LICENSE file~~ ALREADY EXISTS
10. ~~Remove dead code from index.html~~ DONE (147 lines removed, 3,898 -> 3,751)
11. Add basic accessibility attributes (post-hackathon)
12. Add favourites authentication (post-hackathon)

---

## March 11, 2026 — Additional Fixes

### Contradictory search verdicts (FIXED)
- `getVerdict()` could say "quiet skies" for boroughs with severe/high noise
- Root cause: `IMPACT_TO_QUIET[d.impact] || 5` treated score 0 (severe noise) as falsy, defaulting to 5
- Fix: Changed `||` to `??` (nullish coalescing) in `calcScores()` and all display logic (8 instances)
- Rewrote `getVerdict()` and inline postcode verdicts to check quiet score before allowing "quiet skies" text

### Backend data sync (FIXED)
- 15 noise level mismatches between frontend and backend Lambda data
- 4 missing London boroughs in backend (Kensington and Chelsea, Brent, City of London, Harrow)
- Borough naming inconsistencies (e.g., "Richmond" vs "Richmond upon Thames")
- NYC boroughs missing from chat Lambda
- Fix: Synced all backend BOROUGH_DATA to match frontend source of truth (34 London + 5 NYC)

### CORS blocking DELETE for favourites (FIXED)
- API Gateway AllowMethods was `GET,POST,OPTIONS` — missing `DELETE`
- Fix: Added DELETE to `template.yaml` global CORS config

### Saved locations click-to-navigate (FIXED)
- Stored format "Chelsea (SW3 5JR)" couldn't be parsed by `triggerSearch()`
- Fix: Added regex parsing to extract area name from saved-item format

### Map overlay visibility (FIXED)
- Road noise: opacity 0.5 too faint → increased to 0.65
- Air quality: `mix-blend-mode: multiply` at 0.35 opacity made AQMA overlay invisible → replaced with borough-level air quality coloring (poor=red, moderate=amber, good=green) + WMS detail, opacity 0.55
- Flood risk: DEFRA WMS only renders at street-level zoom (sub-pixel at city-wide) → replaced with borough-level flood risk coloring (high/medium/low as dark/medium/light blue)
- Save button: added to borough click view (was only in postcode search view)
- All overlays now zoom-aware: `updateDefraTiles()` accounts for D3 zoom transform, debounced refresh on pan/zoom (400ms)

## March 12, 2026 — Additional Fixes

### Air quality overlay invisible (FIXED)
- WMS-only overlay at 0.5 opacity was too subtle on cream background
- Fix: Replaced with borough-level colored polygons (poor=red, moderate=amber, good=green) matching flood risk approach
- WMS detail image retained on top for zoomed-in detail
- Updated legend to 3-tier scale (POOR AIR / MOD AIR / GOOD AIR)
- Works for both London (BOROUGH_EXTRA.airQuality) and NYC (NYC_BOROUGH_EXTRA.airQuality)

### Save button missing from borough view (FIXED)
- Save/bookmark button only existed in `updateSidebarPostcode()` (postcode/area search)
- Fix: Added save button to `updateSidebar()` (borough click view) using borough name as identifier
- Users can now save boroughs as favourites, not just postcodes/areas

### Road noise overlay blank at city-wide zoom (FIXED)
- DEFRA road noise WMS times out at city-wide zoom due to extreme data density (every road in London)
- Fix: Added zoom-level check — only requests WMS when zoomed to borough level or closer (lon span < 0.25°)
- Shows "ZOOM IN TO SEE DEFRA ROAD NOISE CONTOURS" hint label at city-wide zoom
- NYC tile-based road noise unaffected (BTS tiles work at all zoom levels)

### Live aircraft not visible (NOTED — not a code bug)
- OpenSky Network API returns fewer aircraft at night (tested at 23:40 UTC — only 2 in-flight over London)
- API has CORS enabled, returns valid data — code is functioning correctly
- Rate limit: ~10 requests/min for anonymous users; frequent toggling may temporarily show no results
- Daytime usage will show significantly more aircraft
