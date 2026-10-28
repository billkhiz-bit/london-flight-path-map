#!/usr/bin/env python3
"""Whether an N65 map may be published: our contours against the CAA's own, by the rule Bill agreed on 27 Oct 2026.

WHY THIS EXISTS (2026-10-28)
----------------------------
N65 is how many planes a day pass louder than 65 dB: the "how often, how loud" that an energy average such as Lden
hides, and the remedy for the cone's knife edge (a postcode just off a flight path hears planes it is not under).
It will be computed per postcode by ECAC Doc 29 from our flight tracks and EASA's aircraft noise tables. None of it
is published unless it reproduces the CAA's published N65 contours. This is N65's coverage_verdict()
(scripts/adsb_movements.py), written BEFORE the model, so the model is built to pass a fixed test and the test is
never bent to fit the model.

THE RULE (Bill, 27 Oct, "yes to both"; project memory n65-phase0)
- Heathrow, against CAA ERCD 2601 (annual average 16-hour day, 07:00-23:00, 30 Mar 2025 - 29 Mar 2026): the area
  inside the N65 contour above 50, 100 and 200 events within AREA_BAND of the CAA's at EACH level; above 500 within
  SMALL_AREA_BAND (a few km2 by the runways, where a small shift is a large share); the population inside the
  50-event contour within POPULATION_BAND, which catches a contour of the right size in the wrong place.
- Gatwick, against CAA ERCD 2602 (summer average 16-hour day, 16 Jun - 15 Sep 2025): AREA_BAND at every level.
- AREA_BAND is lopsided on purpose: reading under the CAA gets the tighter side, because a map that errs must err
  loud, never quieter than the yardstick (COVERAGE_FLOOR's direction).
- LIKE FOR LIKE: our tracks for the CAA's exact period, day and window. Never 2026 against 2025: Heathrow's areas moved
  up to 14% from 2024 to 2025 on their own, which would hide or fake a miss.
- The deciding run uses EASA's FULL noise database (DECIDING_DATABASE). The free legacy tables (v2.3, 2020) are for
  building only: own data covers ~48% of Heathrow's movements and proxies' errors can cancel.
- Any miss, at any level, at either airport, and anything not measured: nothing is published.

The population check counts people with ONS figures where the CAA uses CACI's 2025 update of the 2021 Census
(ERCD 2601, note to Table 16): POPULATION_BAND is wide enough for that difference and no wider.

Nothing here reads EASA's tables, and nothing published may: their terms forbid reproducing the data or benchmarking
types. The targets below are the CAA's published figures, each held by a test against the reports' own text.
"""
from __future__ import annotations

# (least, most) of ours / CAA's - 1. Exact edges pass.
AREA_BAND = (-0.10, 0.15)
SMALL_AREA_BAND = (-0.30, 0.30)
POPULATION_BAND = (-0.20, 0.20)
DECIDING_DATABASE = 'easa-anp-full'  # what EASA sends on request; 'easa-anp-2.3' (the free legacy tables) never decides
_EPS = 1e-9  # 184.8 x 0.9 is not exactly 166.32 in floating point: an exact edge must pass

# The CAA's published N65 contours. Each figure is held against the report's text by tests/test_n65_gate.py.
TARGETS = {
    'LHR': {
        'source': 'CAA ERCD 2601 (Aug 2026), Table 16',
        'period': ('2025-03-30', '2026-03-29'), 'day': 'annual average', 'window': '07:00-23:00',
        'areas_km2': {50: 184.8, 100: 111.0, 200: 59.7, 500: 7.3},
        'bands': {50: AREA_BAND, 100: AREA_BAND, 200: AREA_BAND, 500: SMALL_AREA_BAND},
        'population_above_50': 528_800,
    },
    'LGW': {
        'source': 'CAA ERCD 2602 (May 2026), Table 15',
        'period': ('2025-06-16', '2025-09-15'), 'day': 'summer average', 'window': '07:00-23:00',
        'areas_km2': {20: 118.5, 50: 85.6, 100: 62.0, 200: 46.8, 500: 2.1},
        'bands': {20: AREA_BAND, 50: AREA_BAND, 100: AREA_BAND, 200: AREA_BAND, 500: AREA_BAND},
        'population_above_50': None,  # not part of Gatwick's rule
    },
}


def within(ours: float, theirs: float, band: tuple[float, float]) -> tuple[bool, float]:
    """(inside the band, ours / theirs - 1)."""
    gap = ours / theirs - 1
    return band[0] - _EPS <= gap <= band[1] + _EPS, gap


def _band_words(band):
    return f'{band[0]:+.0%} to {band[1]:+.0%}'


def airport_verdict(code: str, run: dict | None) -> tuple[bool, list[str]]:
    """(passes, a line per check) for one airport's run: {'period': (first, last), 'day', 'window',
    'areas_km2': {events: km2}, 'population_above_50': people or None}. A check that cannot be made fails."""
    target = TARGETS[code]
    if run is None:
        return False, [f'{code}: no run']
    lines, ok = [], True
    for key in ('period', 'day', 'window'):
        have = tuple(run.get(key) or ()) if key == 'period' else run.get(key)
        if have != target[key]:
            ok = False
            lines.append(f"{code}: not like for like: {key} {have!r}, the CAA's is {target[key]!r}")
    for level, theirs in target['areas_km2'].items():
        ours = run.get('areas_km2', {}).get(level)
        band = target['bands'][level]
        if ours is None:
            ok = False
            lines.append(f'{code} >{level}: not measured')
            continue
        good, gap = within(ours, theirs, band)
        ok &= good
        lines.append(f'{code} >{level}: {ours:.1f} km2 against {theirs:.1f} ({gap:+.1%}; {_band_words(band)}) '
                     + ('pass' if good else 'MISS'))
    if target['population_above_50'] is not None:
        ours = run.get('population_above_50')
        if ours is None:
            ok = False
            lines.append(f'{code} population >50: not measured')
        else:
            good, gap = within(ours, target['population_above_50'], POPULATION_BAND)
            ok &= good
            lines.append(f"{code} population >50: {ours:,.0f} against {target['population_above_50']:,} ({gap:+.1%}; "
                         f'{_band_words(POPULATION_BAND)}) ' + ('pass' if good else 'MISS'))
    return ok, lines


def publish_verdict(runs: dict, database: str) -> tuple[bool, list[str]]:
    """(may N65 be published, every line behind the answer) for {airport: run} made with `database`. Both
    airports must pass on the deciding database; a run on anything else reports its result and decides nothing."""
    ok, lines = True, []
    for code in TARGETS:
        good, said = airport_verdict(code, runs.get(code))
        ok &= good
        lines += said
    if database != DECIDING_DATABASE:
        lines.append(f'built with {database!r}: a building run, never a deciding one ({DECIDING_DATABASE!r} decides)')
        ok = False
    return ok, lines
