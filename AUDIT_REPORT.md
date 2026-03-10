# Sky Score — Full Project Audit Report
**Date:** March 10, 2026 | **Deadline:** March 17, 2026

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
