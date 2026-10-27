"""Planes overhead, as the front page will be told it (2026-10-26).

`scripts/build_planes_overhead.py` turns the per-postcode averages into one static file per postcode district.
These tests hold, on a handful of synthetic postcodes: the figures as shown (a measured zero, "<1", rounding half
up as JavaScript would); a range on a cone's edge and one figure elsewhere; a kind of day not measured written
as null, never 0; a postcode with nothing reaching 1 a day listed as measured-none, apart from one never measured;
coarse positions and uncounted traffic flagged, the uncounted figure itself never written; only the averages'
published airports; and --check catching a stale, missing or extra file and a manifest out of step.
Offline only.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bp = _load('build_planes_overhead')
NAN = float('nan')
AIRPORTS = ['LCY', 'LHR']


def _averages(rows):
    """Arrays and meta as adsb_postcode_averages writes them, from rows of
    (postcode, gridind, {airport: (mean, lo, hi)} with each a westerly/easterly/mixed triple, context a day)."""
    p, a = len(rows), len(AIRPORTS)
    mean, lo, hi = (np.zeros((p, a, 3, 2), np.float32) for _ in range(3))
    for k, (_, _, by_airport, _) in enumerate(rows):
        for code, (m, low, high) in by_airport.items():
            x = AIRPORTS.index(code)
            mean[k, x, :, 0], lo[k, x, :, 0], hi[k, x, :, 0] = m, low, high
    arrays = {
        'postcode': np.array([r[0] for r in rows]), 'gridind': np.array([r[1] for r in rows], np.int8),
        'airports': np.array(AIRPORTS), 'angles': np.array([48.5, 60.0]),
        'days': np.array([[104, 78, 41], [125, 64, 34]], np.int32),
        'mean': mean, 'mean_lo': lo, 'mean_hi': hi,
        'context_all_traffic_unpublishable': np.array([[r[3], r[3]] for r in rows], np.float32),
    }
    meta = {'published': {c: {'months': ['202601', '202608']} for c in AIRPORTS}}
    return arrays, meta


def _same(m):
    return (m, m, m)


ROWS = [
    ('TW9 3PZ', 1, {'LHR': _same((310, 4, 168))}, 215.0),  # Kew: under the approach, one figure each (~200 from LHR)
    ('TW3 3QL', 1, {'LHR': ((7, 0, 3), (7, 0, 3), (339, 0, 3))}, 9.0),  # Hounslow: a cone's edge on west days
    ('TW9 9ZZ', 1, {'LHR': _same((0.2, 0.1, 0.3))}, 0.6),  # nothing reaching 1 a day: measured, none
    # 4 a day in a cell beside it, too few for a range: shown "<1" on every kind of day, so not listed either.
    ('TW9 9ZY', 1, {'LHR': ((0.2, 0.1, 0.3), (0.2, 0.1, 0.3), (4, 0.1, 0.3))}, 0.6),
    ('E16 2QD', 5, {'LHR': _same((104, 1, 60)), 'LCY': _same((36, NAN, 12))}, 160.0),  # a coarse position
    ('TN16 3GH', 1, {'LHR': _same((6.3, 0.4, 3.2))}, 28.8),  # Biggin Hill: mostly flying we cannot count
]


def test_the_figures_as_shown():
    assert [bp.shown(v) for v in (0, 0.004, 0.49, 0.5, 2.5, 309.9)] == [0, '<1', '<1', 1, 3, 310]  # 2.5 -> 3, not 2


def test_what_overhead_means_is_stated_from_the_thresholds_counted_with():
    """Derive, never copy (2026-10-27 review): the definition every answer carries and the method on How it works
    state the counter's own thresholds, so a threshold changed without its wording is red here, not live."""
    ao, am = bp.ao, _load('adsb_movements')
    angle, ceiling = f'{bp.ANGLE:g} degrees or more', f'{ao.CEILING_FT:,} ft'
    assert angle in bp.DEFINITION and ceiling in bp.DEFINITION
    page = (REPO / 'how-it-works' / 'index.html').read_text(encoding='utf-8')
    method = page[page.index('id="planes-overhead"'):]
    method = method[:method.index('</section>')]
    # "within 5%" is one figure only while the CAA check is symmetric (0.95 to 1.05)
    assert round(1 - am.COVERAGE_FLOOR, 6) == round(am.COVERAGE_CEILING - 1, 6)
    for stated in (angle, ceiling, f'{ao.DIRECTION_DAY_SHARE:.0%} of the airport', f'within {1 - am.COVERAGE_FLOOR:.0%}'):
        assert stated in method, stated


def test_a_range_only_where_the_cells_around_differ_widely():
    assert bp.edge(7, 7, 339)  # Hounslow TW3 3QL
    assert not bp.edge(300, 300, 320)  # busy, and steady: one figure
    assert not bp.edge(1, 1, 3)  # quiet: three times as many, but two planes a day
    assert not bp.edge(0, 0, 0)


def test_what_each_postcode_is_told():
    files = bp.build(*_averages(ROWS))
    tw9, tw3, e16, tn16 = files['TW9.json'], files['TW3.json'], files['E16.json'], files['TN16.json']
    assert tw9['postcodes'] == {'TW9 3PZ': {'LHR': [310, 4, 168]}}
    assert tw3['postcodes'] == {'TW3 3QL': {'LHR': [[7, 339], 0, 3]}}  # west days: a range; a measured zero is 0
    assert tw9['none'] == ['TW9 9ZZ', 'TW9 9ZY'] and 'TW9 9ZY' not in tw9['postcodes']
    # London City had no easterly day measured: null, never 0, and the other figures still stand.
    assert e16['postcodes']['E16 2QD'] == {'LHR': [104, 1, 60], 'LCY': [36, None, 12]}
    assert e16['approx'] == ['E16 2QD'] and tw9['approx'] == []
    assert tn16['other'] == ['TN16 3GH'] and tw9['other'] == [] and tw3['other'] == []
    assert set(files) == {'TW9.json', 'TW3.json', 'E16.json', 'TN16.json', 'airports.json'}


def test_the_uncounted_traffic_figure_is_never_written():
    files = bp.build(*_averages(ROWS))
    text = ''.join(bp.encode(f).decode() for f in files.values())
    assert '28.8' not in text and '215' not in text and 'context' not in text


def test_only_the_averages_published_airports_and_their_days():
    arrays, meta = _averages(ROWS)
    info = bp.build(arrays, meta)['airports.json']
    assert sorted(info['airports']) == AIRPORTS
    assert info['airports']['LHR']['days'] == {'westerly': 125, 'easterly': 64, 'mixed': 34}
    assert info['airports']['LHR']['share_pct'] == {'westerly': 56, 'easterly': 29, 'mixed': 15}
    assert info['classes'] == ['westerly', 'easterly', 'mixed'] and info['angle_deg'] == 48.5
    assert info['districts'] == ['E16', 'TN16', 'TW3', 'TW9']  # only districts with a file: no request 404s
    assert info['bar_full'] == 339  # the busiest figure shown anywhere, a range's top included
    assert '80%' in info['direction_rule'] and '48.5' in info['definition'] and '7,000' in info['definition']
    meta['published'].pop('LCY')  # an airport in the arrays that the meta does not publish: refuse
    with pytest.raises(SystemExit, match='does not publish'):
        bp.build(arrays, meta)


def test_check_finds_every_way_out_of_step(tmp_path):
    out, man = tmp_path / 'planes', tmp_path / 'planes-manifest.json'
    encoded = {name: bp.encode(obj) for name, obj in bp.build(*_averages(ROWS)).items()}
    assert bp.check(encoded, out, man) != []  # nothing written yet
    bp.write(encoded, out, man)
    assert bp.check(encoded, out, man) == []
    (out / 'TW9.json').write_bytes(b'{}\n')
    (out / 'ZZ1.json').write_bytes(b'{}\n')
    (out / 'E16.json').unlink()
    got = bp.check(encoded, out, man)
    assert {'stale: TW9.json', 'no longer built: ZZ1.json', 'missing: E16.json'} <= set(got)
    bp.write(encoded, out, man)  # a rewrite removes the district no longer built
    assert not (out / 'ZZ1.json').exists() and bp.check(encoded, out, man) == []
    recorded = json.loads(man.read_text(encoding='utf-8'))
    recorded['TW9.json']['md5'] = '0' * 32
    man.write_text(json.dumps(recorded), encoding='utf-8')
    assert bp.check(encoded, out, man) == ['planes-manifest.json does not match the built files']
