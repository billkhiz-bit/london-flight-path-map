"""The front page's "Which areas fit" cuts are the map's own band cuts.

Why this exists (2026-10-14): js/home-engine.mjs filters council areas on the
figures their cards print - "keep me away from busy roads", "a station nearby" -
and each condition is promised to mean what the map's colours mean. The cuts
live in the engine as FIT_CUTS because a browser cannot import the Python that
draws the bands, so this asks scripts/build_borough_bands.py itself, either side
of every cut, and asks the score engine which aircraft band a 10 means. A band
re-cut there and not here would leave the front page filtering on a line the
map no longer draws.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))

import app  # noqa: E402
import build_borough_bands as bands  # noqa: E402

EPS = 0.01


def fit_cuts():
    text = (REPO / 'js' / 'home-engine.mjs').read_text(encoding='utf-8')
    block = re.search(r'export const FIT_CUTS = \{(.*?)\};', text, re.S)
    assert block, 'FIT_CUTS not found in js/home-engine.mjs: the holder moved'
    cuts = {k: float(v) for k, v in re.findall(r'(\w+):\s*(-?[\d.]+)', block.group(1))}
    assert set(cuts) == {'quietLowBand', 'roadShare', 'floodShare', 'airRatio', 'railShare', 'progress8'}, sorted(cuts)
    return cuts


def test_road_cut_is_the_low_band():
    # The engine: an area fits when its share is BELOW the cut.
    cut = fit_cuts()['roadShare']
    assert bands.road_band(cut - EPS) == 'low'
    assert bands.road_band(cut) != 'low'


def test_flood_cut_is_the_low_band():
    cut = fit_cuts()['floodShare']
    assert bands.flood_band(cut - EPS) == 'low'
    assert bands.flood_band(cut) != 'low'


def test_air_cut_is_the_edge_of_poor():
    # The engine: an area fits when its ratio is AT OR BELOW the cut. The band takes the worse of
    # NO2 and PM2.5 as a ratio to WHO, so a single pollutant at cut x guideline reaches it.
    cut = fit_cuts()['airRatio']
    assert bands.aq_band(cut * bands.WHO_NO2_UGM3, None)[0] != 'poor'
    assert bands.aq_band((cut + EPS) * bands.WHO_NO2_UGM3, None)[0] == 'poor'


def test_rail_cut_is_good_or_better():
    cut = fit_cuts()['railShare']
    assert bands.transport_band(cut) in {'good', 'excellent'}
    assert bands.transport_band(cut - EPS) not in {'good', 'excellent'}


def test_aircraft_cut_is_the_lowest_band_alone():
    # A council area's quiet score is one of the band values, so ">= cut" must select 'low' and nothing else.
    cut = fit_cuts()['quietLowBand']
    assert [band for band, quiet in app.IMPACT_TO_QUIET.items() if quiet >= cut] == ['low']


def test_schools_cut_is_the_england_average():
    # Progress 8 is published on a scale whose 0 IS the England average; there is no band to mirror.
    assert fit_cuts()['progress8'] == 0


# The front page filters the open-data CSV, which prints each figure ROUNDED, while the map's bands
# are cut on the UNROUNDED share (METHODOLOGY s7.1, by design). So an area printed on a cut can be
# filtered one way and coloured the other: Bradford's road share prints 50.0, exactly on the cut,
# and agrees today only because its unrounded share is on the moderate side (review 2026-10-15).
# So this asks the real question for every area: does the Find condition, on the printed figure,
# make the same call as the band the map paints? A data roll that splits them fails here, and the
# choice (publish another decimal, or say so on the page) is made then. Progress 8 has no map band,
# and DfE itself publishes it to 2 dp, so its printed figure IS the figure: nothing to compare.
AGREE = {
    # Find cut key: (CSV column, the borough-extra band field, the band(s) the Find condition means)
    'roadShare': ('road_noise_above_who_pct', 'roadNoise', {'low'}),
    'floodShare': ('flood_medium_or_high_pct', 'flood', {'low'}),
    'airRatio': ('air_quality_who_ratio', 'airQuality', {'good', 'moderate', 'excellent'}),
    'railShare': ('rail_within_800m_pct', 'transport', {'good', 'excellent'}),
}
FIND_TEST = {
    'roadShare': lambda v, c: v < c,
    'floodShare': lambda v, c: v < c,
    'airRatio': lambda v, c: v <= c,
    'railShare': lambda v, c: v >= c,
}


def test_find_and_the_map_make_the_same_call_for_every_area():
    import csv
    import json
    rows = list(csv.DictReader((REPO / 'open-data' / 'sky-score-boroughs.csv').open(encoding='utf-8-sig')))
    extra = json.loads((REPO / 'data' / 'borough-extra.json').read_text(encoding='utf-8'))
    cuts, compared, disagree = fit_cuts(), 0, []
    for row in rows:
        rec = (extra.get(row['city']) or {}).get(row['borough'])
        if not rec:
            continue  # API-only areas: no map band to disagree with
        for key, (col, band_field, good) in AGREE.items():
            if row.get(col, '') == '' or band_field not in rec:
                continue
            compared += 1
            find = FIND_TEST[key](float(row[col]), cuts[key])
            if find != (rec[band_field] in good):
                disagree.append(f'{row["borough"]}: {col} {row[col]} vs band {rec[band_field]}')
    # A floor, so a renamed column or a city key that stops matching cannot pass by comparing nothing.
    assert compared >= 300, f'only {compared} area/condition pairs compared'
    assert not disagree, 'the Find list and the map disagree: ' + '; '.join(disagree)
