"""Every postcode the full map's area names point at is a LIVE postcode (audit I-14, 2026-11-12).

`LONDON_AREA_MAP` in index.html turns a typed area name ("Mayfair") into a postcode to look up. Nine pointed at postcodes
Royal Mail had retired, Hendon's as recently as April 2026, so the search answered NOT FOUND for real London places. The
list rots on its own as postcodes are retired, so it is held to the NSPL edition the repo loads: each postcode must be
live there (no `doterm`). Large users (`usrtypind` 1) are allowed: 14 of the list are town-centre offices (Canary Wharf
E14 5AB, Westminster SW1E 6QP), live and placed where the area is; rule A is about planes counts, not a place's point.
The nine replaced on 12 Nov took the nearest live RESIDENTIAL postcode in their district all the same.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NSPL = REPO / 'data' / 'nspl.csv'


def area_postcodes() -> dict[str, str]:
    html = (REPO / 'index.html').read_text(encoding='utf-8')
    start = html.index('const LONDON_AREA_MAP = {')
    body = html[start:html.index('\n      };', start)]
    pairs = re.findall(r"^\s*(?:'([^']+)'|([A-Za-z][\w ]*?)):\s*'([A-Z0-9]{2,4} [0-9][A-Z]{2})',", body, re.M)
    return {(q or b): pc for q, b, pc in pairs}


def test_the_map_lists_its_area_names():
    found = area_postcodes()
    assert len(found) >= 100, f'only {len(found)} area names read from LONDON_AREA_MAP: the parse is broken'
    assert found.get('Mayfair') and found.get('Hendon')


@pytest.mark.skipif(not NSPL.exists(), reason='data/nspl.csv is not on this machine (the NSPL roll, HANDOVER)')
def test_every_area_postcode_is_live():
    want = area_postcodes()
    with NSPL.open(newline='', encoding='utf-8-sig') as fh:
        reader = csv.reader(fh)
        header = next(reader)
        ix = {c: header.index(c) for c in ('pcds', 'doterm', 'usrtypind')}
        seen = {r[ix['pcds']]: (r[ix['doterm']].strip(), r[ix['usrtypind']].strip()) for r in reader if r[ix['pcds']] in set(want.values())}
    missing = sorted(f'{name} {pc}' for name, pc in want.items() if pc not in seen)
    retired = sorted(f'{name} {pc} (ended {seen[pc][0]})' for name, pc in want.items() if pc in seen and seen[pc][0])
    assert not missing, f'not in NSPL at all: {missing}'
    assert not retired, f'retired postcodes: give each the nearest live residential postcode in its district: {retired}'
