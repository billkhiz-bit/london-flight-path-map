# Cost of Living: an assessment, parked on this branch

Status: ASSESSED 2026-11-03, NOT BUILT. The founder plans to commit to it in a month or two; until then it lives on
the `cost-of-living` branch only, so master's ROADMAP stays free of a feature nobody is building yet. Nothing here is
code, and nothing here is published.

The brief: an estimated monthly cost to live in an area for a defined household (v1: London boroughs; a single renter
and a couple renting, no children), shown beside the liveability scores ("Is it pleasant, and what will it actually
cost me?"), deepening the affordability score rather than sitting apart from it.

| File | What it holds |
|---|---|
| `roadmap-entry.md` | The roadmap entry: four phases (ingestion, the household model, UI and API, later), acceptance criteria, effort in sessions |
| `methodology-draft.md` | A methodology draft in METHODOLOGY.md's style: the household model, sources, assumptions, limitations, update schedule |
| `integration.md` | How it meets the existing `afford` score: the recommendation (beside it, plus one input swap for the Renter view) and the measurements behind it |
| `open-questions.md` | Open questions and risks, each with a way to resolve it |

Before picking it up:
- The wording gate (`tests/test_public_wording.py`) refuses "£N a month" shaped like one of our prices, so cost
  figures need their own allow-list first (`open-questions.md`).
- The Fuel Finder developer terms and the Minimum Income Standard's licence were not readable from here: the founder
  opens them in a browser and pastes them in.
- Re-check every source's latest edition (the drafts are dated 2026-11-03), and merge master into this branch first.
- The Renter-view input swap is a methodology change (v5.8): the founder's call, with the site and API reproducing
  each other (`tests/borough-score-parity.mjs`).
