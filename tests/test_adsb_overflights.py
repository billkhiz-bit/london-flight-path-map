"""The CAP 1498 overflight counter behind "how often planes pass" (2026-10-20).

`scripts/adsb_overflights.py` turns a day of community flight tracks into overflights per 100 m cell of
the British National Grid. These tests fly synthetic aircraft past one cell near Kew, on the real UK
airport table, one rule at a time: the cone's radius at both of CAP 1498's angles, one count per pass
however many steps cover a cell, nothing at or above 7,000 ft, the barometric fallback lifted by the
day's measured offset, the 100 m walk finding a cell between two far-apart points, and the averaging
step leaving out an outage day and asking classify_day() (Bill's call) for each day's direction.
Offline only.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pyproj
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


ao = _load('adsb_overflights')
mv = _load('adsb_movements')

AIRPORTS = ao.uk_airports()
CODES = sorted(AIRPORTS)
E0, N0 = 519150.0, 176750.0  # a cell centre by Kew, under Heathrow's 27R approach
_TO_LL = pyproj.Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
OFFSET_FT = 400.0  # Heathrow's (GPS above sea level) minus barometric on the test day
MAN_OFFSET_FT = 200.0  # Manchester's: QNH differs across the country, so its offset does too


def pt(t, e, n, baro, geom):
    lon, lat = _TO_LL.transform(e, n)
    # [epoch_s, lat, lon, alt_baro, alt_geom, gs, track, baro_rate, flags, callsign]
    return [t, lat, lon, baro, geom, 140, 90.0, None, 0, 'TEST1']


def gps(msl_ft, code='LHR'):
    """The GPS height (above the ellipsoid) an aircraft at `msl_ft` above sea level near `code` reports."""
    return msl_ft + ao.GEOID_M[code] / ao.FT_M


def calibration():
    """Two aircraft far from the cell reporting both heights: 29 km from it near Heathrow (offset
    OFFSET_FT) and near Manchester (MAN_OFFSET_FT). The UK-wide median falls between them."""
    n = ao.MIN_OFFSET_POINTS + 50
    return [
        {'icao': 'cal1', 'pts': [pt(10_000 + 10 * k, 490_000, 170_000 + 50 * k, 5000, gps(5000 + OFFSET_FT))
                                 for k in range(n)]},
        {'icao': 'cal2', 'pts': [pt(10_000 + 10 * k, 382_000, 384_000 + 50 * k, 5000,
                                    gps(5000 + MAN_OFFSET_FT, 'MAN')) for k in range(n)]},
    ]


def eastbound(t0, northing, msl_ft=None, baro=None, e_from=E0 - 3000, e_to=E0 + 3000, spacing=350, every=5):
    """Points along a straight line east past the cell; heights by GPS (msl_ft) or barometric only."""
    out, k = [], 0
    for e in np.arange(e_from, e_to + 1, spacing):
        out.append(pt(t0 + every * k, float(e), northing,
                      baro if baro is not None else (msl_ft - OFFSET_FT),
                      gps(msl_ft) if msl_ft is not None else None))
        k += 1
    return out


def count(*traces):
    cells, _ = ao.count_traces([*calibration(), *traces], AIRPORTS, {})
    return cells


def at(cells, angle=48.5, e=E0, n=N0):
    return ao.lookup(cells[angle][0], e, n)


# ---------------------------------------------------------------- the cone


def test_the_cone_radius_at_both_angles():
    assert ao.cone_radius_m(1000, 48.5) == pytest.approx(884.7, abs=0.1)  # 0.885 x the height
    assert ao.cone_radius_m(1000, 60.0) == pytest.approx(577.4, abs=0.1)  # 0.577 x


def _steps(xs, ys, h_m, passes=None):
    n = len(xs)
    return {'x': np.asarray(xs, float), 'y': np.asarray(ys, float), 'h_ft': np.full(n, h_m / ao.FT_M),
            't': np.arange(n, dtype=float), 'trace': np.zeros(n, np.int32),
            'pass': np.asarray(passes if passes is not None else [0] * n)}


def test_a_cell_inside_one_cone_and_not_the_other():
    # One step 1,000 m up, 600 m west of the cell's centre: inside 48.5 degrees' 885 m, outside 60's 577 m.
    cells = ao.count_cells(_steps([E0 - 600], [N0], 1000.0), np.zeros(1, np.int16), len(CODES))
    assert at(cells, 48.5) == 1
    assert at(cells, 60.0) == 0
    # ...and 500 m west is inside both.
    cells = ao.count_cells(_steps([E0 - 500], [N0], 1000.0), np.zeros(1, np.int16), len(CODES))
    assert (at(cells, 48.5), at(cells, 60.0)) == (1, 1)


def test_many_steps_of_one_pass_count_a_cell_once():
    xs = list(np.arange(E0 - 1000, E0 + 1001, 100))  # 21 steps, every one of them over the cell's cone
    cells = ao.count_cells(_steps(xs, [N0] * len(xs), 1000.0), np.zeros(len(xs), np.int16), len(CODES))
    assert at(cells) == 1
    split = [0] * 10 + [1] * 11  # the same steps as two passes: two overflights
    cells = ao.count_cells(_steps(xs, [N0] * len(xs), 1000.0, split), np.zeros(len(xs), np.int16), len(CODES))
    assert at(cells) == 2


def test_a_pass_split_across_chunks_still_counts_once(monkeypatch):
    monkeypatch.setattr(ao, 'STEPS_PER_CHUNK', 3)  # chunks end only between passes
    xs = list(np.arange(E0 - 1000, E0 + 1001, 100))
    passes = [0] * 7 + [1] * 7 + [2] * 7
    cells = ao.count_cells(_steps(xs, [N0] * len(xs), 1000.0, passes), np.zeros(len(xs), np.int16), len(CODES))
    assert at(cells) == 3


# ---------------------------------------------------------------- whole traces


def test_a_pass_over_the_cell_counts_once_and_a_second_pass_later_again():
    first = eastbound(50_000, N0, msl_ft=1000)
    assert at(count({'icao': 'a', 'pts': first})) == 1
    later = eastbound(50_000 + 1200, N0, msl_ft=1000)  # the same aircraft 20 minutes on
    assert at(count({'icao': 'a', 'pts': first + later})) == 2


def test_at_or_above_7000_ft_never_counts():
    assert at(count({'icao': 'h', 'pts': eastbound(50_000, N0, msl_ft=7100)})) == 0
    # 6,900 ft above SEA LEVEL counts: its GPS height (above the ellipsoid) reads ~150 ft more, over 7,000.
    assert at(count({'icao': 'g', 'pts': eastbound(50_000, N0, msl_ft=6900)})) == 1
    # Descending from 7,600 to 6,400 ft across 6 km: only the part under the ceiling counts.
    pts = eastbound(50_000, N0, msl_ft=7000)
    for k, p in enumerate(pts):
        h = 7600 - 1200 * k / (len(pts) - 1)
        p[3], p[4] = h - OFFSET_FT, gps(h)
    cells = count({'icao': 'd', 'pts': pts})
    assert at(cells, e=E0 - 2500) == 0  # under the 7,500 ft stretch
    assert at(cells, e=E0 + 2500) == 1  # under the 6,500 ft stretch


def test_a_barometric_only_aircraft_is_lifted_by_its_airports_offset():
    # Barometric 600 ft is 1,000 ft above sea level near Heathrow on this day: a 270 m cone at 48.5
    # degrees. 250 m beside the cell it counts; read as 600 ft (a 162 m cone) it would not, nor lifted by
    # the UK-wide median (300 ft: a 242 m cone).
    pts = eastbound(50_000, N0 + 250, baro=600)
    assert all(p[4] is None for p in pts)
    assert at(count({'icao': 'b', 'pts': pts})) == 1


def test_gps_height_is_preferred_to_barometric():
    # GPS says 1,000 ft above sea level (a 270 m cone); this aircraft's barometric reading, lifted by the
    # day's offset, would say 500 ft (135 m). 200 m beside the cell, only the GPS reading counts it.
    pts = eastbound(50_000, N0 + 200, msl_ft=1000)
    for p in pts:
        p[3] = 100
    assert at(count({'icao': 'p', 'pts': pts})) == 1


def test_the_100_m_walk_finds_a_cell_between_two_far_apart_points():
    # Two points 2 km apart at 300 ft (an 81 m cone), the cell's centre on the line between them.
    pts = [pt(50_000, E0 - 1000, N0, 300 - OFFSET_FT, gps(300)), pt(50_020, E0 + 1000, N0, 300 - OFFSET_FT, gps(300))]
    assert at(count({'icao': 's', 'pts': pts})) == 1


def test_a_segment_across_a_long_silence_is_not_walked():
    pts = [pt(50_000, E0 - 1000, N0, 300 - OFFSET_FT, gps(300)), pt(50_000 + ao.SEGMENT_GAP_S + 30, E0 + 1000, N0,
                                                                    300 - OFFSET_FT, gps(300))]
    assert at(count({'icao': 's', 'pts': pts})) == 0


def test_the_day_offset_is_measured_per_airport():
    _, meta = ao.count_traces(calibration(), AIRPORTS, {})
    got = meta['heights']['airports']
    assert got['LHR']['offset_ft'] == pytest.approx(OFFSET_FT, abs=0.5)
    assert got['MAN']['offset_ft'] == pytest.approx(MAN_OFFSET_FT, abs=0.5)
    assert got['BHX']['from'] == 'the UK fit'  # no points of its own
    assert got['BHX']['offset_ft'] == pytest.approx((OFFSET_FT + MAN_OFFSET_FT) / 2, abs=0.5)


def test_a_199_m_segment_is_walked_in_steps_no_wider_than_100_m():
    # Code review 2026-10-20: the step count was rounded DOWN, so a 199 m segment had only its ends, 99.5 m
    # either side of the cell's centre, and at 300 ft (an 81 m cone) neither end covered it.
    pts = [pt(50_000, E0 - 99.5, N0, 300 - OFFSET_FT, gps(300)), pt(50_002, E0 + 99.5, N0, 300 - OFFSET_FT, gps(300))]
    assert at(count({'icao': 'w', 'pts': pts})) == 1


def test_the_height_offset_follows_height_not_one_median():
    # 15 Aug near Heathrow (measured 2026-10-20): the gap grew from ~123 ft low down to ~348 ft at 7,000 ft.
    baro = np.repeat(np.arange(500.0, 9500.0, 1000.0), 100)
    a, b = ao.offset_fit(100 + 0.03 * baro, baro)
    assert (a, b) == (pytest.approx(100, abs=0.5), pytest.approx(0.03, abs=1e-4))
    # One band only: the one median, flat.
    assert ao.offset_fit(np.full(100, 250.0), np.full(100, 5000.0)) == (250.0, 0.0)


def test_a_low_barometric_aircraft_takes_the_offset_at_its_own_height():
    # Near Heathrow the gap is 100 ft + 5% of the barometric height (exaggerated from 15 Aug's ~3%). A
    # barometric-only aircraft at 600 ft is then at 730 ft (a 197 m cone at 48.5 degrees) and misses a cell
    # 220 m away; one all-heights median (~325 ft at the median height) would lift it to ~925 ft, a 250 m
    # cone, and count the cell.
    n = ao.MIN_BAND_POINTS + 10
    cal = [{'icao': f'c{band}', 'pts': [pt(10_000 + 10 * k, 490_000, 170_000 + 50 * k, band,
                                            gps(band + 100 + 0.05 * band)) for k in range(n)]}
           for band in range(500, 9000, 1000)]
    cells, meta = ao.count_traces([*cal, {'icao': 'b', 'pts': eastbound(50_000, N0 + 220, baro=600)}], AIRPORTS, {})
    assert meta['heights']['airports']['LHR']['per_1000_ft'] == pytest.approx(50, abs=0.5)
    assert at(cells) == 0


def _fake_day(day):
    meta = {'day': day, 'uk_traces': 1, 'steps': 1, 'passes': 1, 'heights': {'gps_share': 1.0}, 'observed': {}}
    return {angle: (np.zeros((0, 4)), np.zeros((0, 5))) for angle in ao.ANGLES}, meta


def test_one_bad_day_does_not_stop_the_batch_and_observe_keeps_a_file(tmp_path, monkeypatch):
    written = []

    def count_day(path, observers=()):
        if '01-01' in Path(path).name:
            raise ao.DayError('only 3 points carry both heights')
        return _fake_day(mv.day_of(Path(path)).isoformat())

    monkeypatch.setattr(ao, 'count_day', count_day)
    monkeypatch.setattr(ao, 'write_day', lambda cells, meta, out: written.append(out.name))
    files = [str(tmp_path / f'2026-01-0{d}.jsonl.gz') for d in (1, 2)]
    monkeypatch.setattr(sys, 'argv', ['x', *files, '--out-dir', str(tmp_path)])
    assert ao.main() == 1  # the bad day is listed and the run says so...
    assert written == ['2026-01-02.npz']  # ...but the next day was still counted
    # --observe on a day already counted prints the count but keeps the file (only --force recounts).
    (tmp_path / '2026-01-02.npz').write_bytes(b'kept')
    written.clear()
    monkeypatch.setattr(sys, 'argv', ['x', files[1], '--out-dir', str(tmp_path), '--observe', f'{E0},{N0}'])
    assert ao.main() == 0
    assert written == [] and (tmp_path / '2026-01-02.npz').read_bytes() == b'kept'


def test_circuits_are_told_apart_in_classify_days_input():
    t = 1_786_000_000.0  # 2026-08-06 UTC, mid-morning
    by_trace = {0: [(t, 'EMA', 'landing', '27'), (t + 60, 'EMA', 'take-off', '27')],
                1: [(t + 600, 'EMA', 'landing', '27')]}
    out = ao.hourly(by_trace, mv.day_of(Path('2026-08-06.jsonl.gz')), ['EMA'], {(0, t, 'EMA'), (0, t + 60, 'EMA')})
    assert sum(out['EMA']['landing']['27']) == 2 and sum(out['EMA']['take-off']['27']) == 1
    assert sum(out['EMA']['circuits']['landing']['27']) == 1 and sum(out['EMA']['circuits']['take-off']['27']) == 1


# ---------------------------------------------------------------- airports


def test_steps_before_a_landing_belong_to_that_airport_and_a_transit_to_none():
    steps = {'t': np.array([1000.0, 2000.0, 2500.0, 2600.0, 9000.0]), 'trace': np.array([0, 0, 0, 0, 1])}
    moves = {0: [(2550.0, 'LHR', 'landing', '27R')]}
    got = ao.attribute(steps, moves, CODES)
    lhr, other = CODES.index('LHR'), len(CODES)
    # 1,550 s before landing is on the approach; 50 s after is the flare; trace 1 has no movement.
    assert list(got) == [lhr, lhr, lhr, lhr, other]
    steps['t'][0] = 2550.0 - ao.ATTRIBUTE_BEFORE_LANDING_S - 1
    assert ao.attribute(steps, moves, CODES)[0] == other


def test_the_geoid_table_covers_exactly_the_uk_airports():
    assert set(ao.GEOID_M) == set(CODES)
    assert all(44 < v < 53 for v in ao.GEOID_M.values())  # EGM96 over Great Britain


# ---------------------------------------------------------------- storage


def test_runs_survive_the_packed_columns():
    rng = np.random.default_rng(1)
    rows = []
    for a in range(3):
        for j in sorted(rng.choice(np.arange(1000, 1100), 20, replace=False)):
            i = 2000
            for _ in range(int(rng.integers(1, 5))):
                i += int(rng.integers(0, 50))
                length = int(rng.integers(0, 6))
                rows.append([a, j, i, i + length, int(rng.integers(1, 700))])
                i += length + 1
    runs = np.array(rows, np.int32)
    assert np.array_equal(ao.unpack(ao.pack(runs, 'x'), 'x'), runs)
    assert np.array_equal(ao.unpack(ao.pack(runs[:, 1:], 'y'), 'y'), runs[:, 1:])


# ---------------------------------------------------------------- averaging


def _day_file(tmp_path, day, n_lhr, outage=False):
    """A day file with LHR traffic in one cell (n_lhr overflights) and the feed profile of a whole day,
    or of one that lost its first five hours."""
    feed = [100] * (86400 // mv.FEED_BIN_S)
    if outage:
        feed[:30] = [0] * 30
    meta = {'day': day, 'codes': CODES + [ao.OTHER], 'feed': {'uk': feed, 'us': feed},
            'movements': {c: {'landing': {}, 'take-off': {}} for c in CODES}}
    i, j = int(E0 // ao.CELL_M), int(N0 // ao.CELL_M)
    cells = {a: (np.array([[j, i, i, n_lhr]], np.int32), np.array([[CODES.index('LHR'), j, i, i, n_lhr]], np.int32))
             for a in ao.ANGLES}
    path = tmp_path / f'{day}.npz'
    ao.write_day(cells, meta, path)
    return path


def test_the_average_leaves_out_an_outage_day_and_says_so(tmp_path):
    files = [_day_file(tmp_path, f'2026-08-{d:02d}', 10) for d in range(1, 10) if d != 5]
    files.append(_day_file(tmp_path, '2026-08-05', 1000, outage=True))
    res = ao.average(files, classify=lambda code, movements, runways: 'westerly')
    assert res['left_out_outage'] == ['2026-08-05']
    assert '2026-08-05' not in res['kept'] and len(res['kept']) == 8
    g = res['groups'].index(['LHR', 'westerly'])
    assert ao.lookup(res['runs'][48.5], E0, N0, g) == pytest.approx(10)


def test_the_average_asks_classify_day_and_groups_by_its_answer(tmp_path):
    files = [_day_file(tmp_path, f'2026-08-{d:02d}', d) for d in range(1, 10)]
    with pytest.raises(NotImplementedError, match='TODO\\(Bill\\)'):
        ao.average(files)  # the stub: averaging cannot run until the direction rule is chosen
    days = iter(range(1, 10))

    def classify(code, movements, runways):
        assert runways == {d: b for d, (_, b) in AIRPORTS[code]['runways'].items()}
        if code == CODES[0]:  # each day's airports are asked in order, so the first starts a new day
            classify.day = next(days)
        return 'even' if classify.day % 2 == 0 else 'odd'

    res = ao.average(files, classify=classify)
    groups = [tuple(g) for g in res['groups']]
    assert ('LHR', 'even') in groups and ('LHR', 'odd') in groups
    assert res['days_per_group'][groups.index(('LHR', 'even'))] == 4
    lhr_even = ao.lookup(res['runs'][48.5], E0, N0, groups.index(('LHR', 'even')))
    lhr_odd = ao.lookup(res['runs'][48.5], E0, N0, groups.index(('LHR', 'odd')))
    assert (lhr_even, lhr_odd) == (pytest.approx(5), pytest.approx(5))  # (2+4+6+8)/4 and (1+3+5+7+9)/5


def test_a_day_classed_none_is_left_out_of_every_direction(tmp_path):
    files = [_day_file(tmp_path, f'2026-08-{d:02d}', 10 if d != 3 else 1000) for d in range(1, 10)]
    days = iter(range(1, 10))

    def classify(code, movements, runways):
        if code == CODES[0]:
            classify.day = next(days)
        return None if classify.day == 3 else 'westerly'

    res = ao.average(files, classify=classify)
    g = [tuple(x) for x in res['groups']].index(('LHR', 'westerly'))
    assert ao.lookup(res['runs'][48.5], E0, N0, g) == pytest.approx(10)
    assert any(u.startswith('2026-08-03 LHR') for u in res['unclassified'])
