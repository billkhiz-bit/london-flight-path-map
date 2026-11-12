"""N65 step 5: one day at one airport (scripts/n65_day.py), 2026-11-03.

Every noise table, aircraft, path and weather report here is MADE UP (shaped like EASA's and the METARs, typed for the
test): EASA's data never enters this public repo. The pruning is held EXACT against the unpruned sum (n65_grid on every
cell), where it matters (every cell that reaches the threshold) and where it does not (no cell that does not is ever
lifted to it). Offline only.
"""
import csv
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import n65_day as nd  # noqa: E402
import n65_doc29 as d29  # noqa: E402
import n65_grid as grid  # noqa: E402
import n65_tracks as tr  # noqa: E402

CURVES = d29.npd_curves([
    (4000, {200: 92.0, 400: 86.1, 630: 82.0, 1000: 77.9, 2000: 71.2, 4000: 64.0, 6300: 59.1, 10000: 53.8, 16000: 47.9, 25000: 41.0}),
    (8000, {200: 96.5, 400: 90.9, 630: 87.0, 1000: 83.1, 2000: 76.8, 4000: 69.9, 6300: 65.2, 10000: 60.1, 16000: 54.5, 25000: 47.8}),
    (14000, {200: 100.1, 400: 94.8, 630: 91.2, 1000: 87.6, 2000: 81.5, 4000: 74.9, 6300: 70.4, 10000: 65.6, 16000: 60.3, 25000: 53.9}),
])
# A made-up departure: a take-off roll (flagged), a climb, a right turn (banked), a climb to 3 km.
DEPARTURE = [(0, 0, 1, 14000, 0, True), (600, 0, 1, 14000, 0, True), (1600, 0, 1, 13500, 0, True),
             (2000, 0, 1, 13500, 0, False), (4000, 0, 160, 13000, 0, False), (7000, 500, 420, 11000, -18, False),
             (9000, 2500, 650, 10500, -18, False), (10000, 6000, 900, 10000, 0, False), (12000, 20000, 3000, 9000, 0, False)]
APPROACH = [(-30000, 800, 1200, 4000, 0, False), (-12000, 0, 640, 5000, 0, False), (-3000, 0, 160, 6000, 0, False),
            (0, 0, 1, 6000, 0, False), (1500, 0, 1, 12000, 0, False), (2500, 0, 1, 2500, 0, False)]


def _brute(path, g, mount, adjust):
    obs = np.column_stack([np.tile(g.xc, g.ny), np.repeat(g.yc, g.nx), np.zeros(g.size)])
    return grid.event_lmax(path, obs, CURVES, mount, adjust)


@pytest.mark.parametrize('mount', ['wing', 'fuselage', 'prop'])
@pytest.mark.parametrize('path', [DEPARTURE, APPROACH], ids=['departure', 'approach'])
@pytest.mark.parametrize('threshold', [65.0, 75.0])
@pytest.mark.parametrize('margin', [nd.PRUNE_MARGIN_DB, 0.0], ids=['margin', 'no-margin'])
def test_pruning_is_exact_wherever_the_threshold_is_reached(path, mount, threshold, margin, monkeypatch):
    # With NO margin the bound must stand on its own terms: every correction that can add (the installation effect,
    # the start-of-roll directivity) is in it at its true maximum, so dropping one turns this red.
    monkeypatch.setattr(nd, 'PRUNE_MARGIN_DB', margin)
    g = nd.Grid(-6000.0, -9000.0, 160, 160, 125.0)
    adjust = 0.3
    want = _brute(path, g, mount, adjust)
    got = nd.flight_levels(path, g, CURVES, mount, adjust, threshold)
    reach = want >= threshold
    assert reach.sum() > 50 and (~reach).sum() > 50  # both sides of the edge are on the grid
    assert np.array_equal(got >= threshold, reach)
    assert np.max(np.abs(got[reach] - want[reach])) <= 1e-9
    assert np.all(got[~reach] <= want[~reach] + 1e-9)  # a pruned cell is never lifted


@pytest.mark.parametrize('adjust', [0.0, 2.0])
def test_the_bound_is_tight_where_the_installation_effect_peaks(adjust, monkeypatch):
    # The installation effect peaks (+0.40 dB, wing) at a 50 degree depression angle, where lateral attenuation has
    # just gone to zero: there the true level is the noise table's plus 0.40 plus the adjustment, nothing taken away.
    # A level segment 1,500 m up and a column of cells to its side; the threshold set 0.02 dB under the level at
    # 50 degrees, no margin. Leave the 0.40 dB (or the adjustment) out of the bound and that cell is pruned.
    monkeypatch.setattr(nd, 'PRUNE_MARGIN_DB', 0.0)
    z = 1500.0
    path = [(-20000.0, 0.0, z, 14000.0, 0.0, False), (20000.0, 0.0, z, 14000.0, 0.0, False)]
    g = nd.Grid(-5.0, -5.0, 1, 300, 10.0)
    y50 = z / math.tan(math.radians(50.0))
    at50 = d29.segment_lmax(path[0][:3], path[1][:3], 14000.0, 14000.0, (0.0, y50, 0.0), CURVES, 'wing', 0.0, adjust)
    threshold = at50 - 0.02
    want = _brute(path, g, 'wing', adjust)
    got = nd.flight_levels(path, g, CURVES, 'wing', adjust, threshold)
    edge = np.nonzero(want >= threshold)[0]
    assert g.yc[edge.max()] > y50  # the cells reaching it run out past the 50 degree line
    assert np.array_equal(got >= threshold, want >= threshold)


def test_pruning_skips_most_of_the_grid():
    g = nd.Grid(-6000.0, -9000.0, 160, 160, 125.0)
    got = nd.flight_levels(DEPARTURE, g, CURVES, 'wing', 0.0, 65.0)
    assert np.isinf(got).sum() > g.size / 3


def test_the_reach_is_where_the_loudest_possible_level_falls_below_the_threshold():
    r = nd.reach_m(CURVES, 8000.0, 8000.0, 0.0, 65.0)
    # The 8,000 lb curve passes 65.2 dB at 6,300 ft and 60.1 at 10,000 ft: 64.5 dB (65 less the margin) lies between.
    assert 6300 * nd.d29.FT < r < 10000 * nd.d29.FT
    assert grid.npd_level(CURVES, 8000.0, np.array([r])) < 65.0 - nd.PRUNE_MARGIN_DB
    # Between two tabulated powers the greatest is at a knot or an end, so a wider range reaches at least as far.
    assert nd.reach_m(CURVES, 4000.0, 14000.0, 0.0, 65.0) >= nd.reach_m(CURVES, 14000.0, 14000.0, 0.0, 65.0)
    assert nd.reach_m(CURVES, 8000.0, 8000.0, 3.0, 65.0) > r  # an added correction reaches further
    assert nd.reach_m(CURVES, 4000.0, 4000.0, -60.0, 65.0) == 0.0
    assert math.isinf(nd.reach_m(CURVES, 14000.0, 14000.0, 60.0, 65.0))


def test_a_table_louder_at_a_middle_power_reaches_from_that_power():
    # Linear in power between tabulated powers, so over a range the loudest is at an end OR a knot between: a (made-up)
    # table whose middle curve is the loudest far out must reach as far as that curve does.
    odd = d29.npd_curves([(4000, {200: 92.0, 4000: 60.0, 25000: 40.0}), (8000, {200: 96.0, 4000: 70.0, 25000: 52.0}),
                          (14000, {200: 99.0, 4000: 64.0, 25000: 44.0})])
    assert nd.reach_m(odd, 4000.0, 14000.0, 0.0, 65.0) >= nd.reach_m(odd, 8000.0, 8000.0, 0.0, 65.0) > \
        nd.reach_m(odd, 14000.0, 14000.0, 0.0, 65.0)


def test_the_correction_bounds_are_the_formulas_own_maxima():
    phi = np.linspace(0, 180, 1801)
    assert nd.INSTALL_MAX_DB['wing'] == pytest.approx(float(np.max(grid.installation_correction(phi, 'wing'))), abs=1e-4)
    assert nd.INSTALL_MAX_DB['wing'] > 0 and nd.INSTALL_MAX_DB['prop'] == 0.0
    rng = random.Random(7)  # noqa: S311 (a seeded test sample, not security)
    for _ in range(500):
        d = rng.uniform(1, 3000)
        q = -d * rng.uniform(0, 1)
        for engine in ('jet', 'prop'):
            assert d29.start_of_roll(q, d, engine) <= nd.SOR_MAX_DB[engine] + 1e-9


def test_cells_near_a_segment_are_those_within_the_radius_of_its_ground_track():
    g = nd.Grid(0.0, 0.0, 50, 40, 100.0)
    flat, obs = g.near((1000.0, 1000.0, 300.0), (3000.0, 2000.0, 600.0), 450.0)
    xs, ys = np.meshgrid(g.xc, g.yc)
    a, b = np.array([1000.0, 1000.0]), np.array([3000.0, 2000.0])
    pts = np.column_stack([xs.ravel(), ys.ravel()])
    t = np.clip((pts - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1)
    dist = np.hypot(*(pts - (a + t[:, None] * (b - a))).T)
    assert set(flat.tolist()) == set(np.nonzero(dist <= 450.0)[0].tolist())
    assert np.allclose(obs[:, :2], pts[flat]) and np.all(obs[:, 2] == 0)
    assert g.near((-9000.0, -9000.0, 0.0), (-8000.0, -9000.0, 0.0), 100.0)[0].size == 0


def test_areas_count_cells_reaching_each_level():
    counts = np.array([0, 49, 50, 99, 100, 200, 499, 500, 501])
    assert nd.areas_km2(counts, 100.0) == {50: pytest.approx(0.07), 100: pytest.approx(0.05),
                                           200: pytest.approx(0.04), 500: pytest.approx(0.02)}


def _air_file(tmp_path):
    p = tmp_path / 'EGLL-2026-07-air.csv'
    with open(p, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['valid', 'tmpf', 'drct', 'sknt', 'alti'])
        w.writerow(['2026-07-15 06:50', '59.0', '60.00', '10.00', '30.00'])
        w.writerow(['2026-07-15 07:50', '68.0', '', '3.00', '30.10'])
        w.writerow(['2026-07-15 08:50', '68.0', '0.00', '0.00', '30.10'])
        w.writerow(['2026-07-15 13:50', '77.0', '270.00', '', '30.20'])
    return nd.read_air(p)


def _t(hhmm):
    import datetime as dt
    return dt.datetime.strptime(f'2026-07-15 {hhmm}', '%Y-%m-%d %H:%M').replace(tzinfo=dt.UTC).timestamp()


def test_the_days_air_is_interpolated_and_its_wind_the_nearest_reports(tmp_path):
    rows = _air_file(tmp_path)
    temp, qnh, wind_from, wind_kt = nd.air_at(rows, _t('07:20'))  # halfway: 15 C and 20 C, 30.00 and 30.10 inHg
    assert temp == pytest.approx(17.5) and qnh == pytest.approx(30.05 * nd.INHG_HPA)
    assert nd.air_at(rows, _t('07:10'))[2:] == (60.0, 10.0)  # the wind of the nearer report, never a blend
    assert nd.air_at(rows, _t('07:35'))[2:] == (None, 3.0)
    assert nd.air_at(rows, _t('11:20')) is None  # 2 h 30 from the nearest report: no air
    assert nd.air_at(rows, _t('04:00')) is None
    assert nd.air_at([], _t('07:00')) is None


def test_the_headwind_says_how_it_was_found(tmp_path):
    rows = _air_file(tmp_path)
    rw = tr.Runway('09R', (0.0, 0.0), (1.0, 0.0), 3600.0, 90.0, 3.0)
    assert nd.headwind_for(nd.air_at(rows, _t('06:50')), rw) == (pytest.approx(10 * math.cos(math.radians(30))), 'metar')
    assert nd.headwind_for(nd.air_at(rows, _t('07:50')), rw) == (0.0, 'wind-variable-0kt')
    assert nd.headwind_for(nd.air_at(rows, _t('08:50')), rw) == (0.0, 'calm')
    assert nd.headwind_for(nd.air_at(rows, _t('13:50')), rw) == (8.0, 'wind-missing-reference-8kt')


def test_noise_tables_read_lamax_whole_and_the_v9_mount_column_by_its_values(tmp_path):
    v23, v9 = tmp_path / 'v23', tmp_path / 'v9'
    v23.mkdir()
    with open(v23 / 'ANP2.3_Aircraft.csv', 'w', encoding='latin-1', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['ACFT_ID', 'NPD_ID', 'Lateral Directivity Identifier'])
        w.writerow(['ZZ-JET', 'NZ1', 'Wing'])
        w.writerow(['ZZ-TAIL', 'NZ2', 'Fuselage'])
        w.writerow(['ZZ-PROP', 'NZ3', 'Prop'])
    with open(v23 / 'ANP2.3_NPD_data.csv', 'w', encoding='latin-1', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['NPD_ID', 'Noise Metric', 'Op Mode', 'Power Setting', 'L_200ft', 'L_1000ft', 'L_25000ft'])
        w.writerow(['NZ1', 'LAmax', 'D', 10000, 95.0, 80.0, 50.0])
        w.writerow(['NZ1', 'LAmax', 'D', 20000, 99.0, 84.0, 54.0])
        w.writerow(['NZ1', 'SEL', 'D', 20000, 109.0, 94.0, 64.0])  # never read
        w.writerow(['NZ1', 'LAmax', 'A', 3000, 90.0, 75.0, 45.0])
        w.writerow(['NZ1', 'SEL', 'A', 6000, 100.0, 85.0, 55.0])  # never read: the arrival keeps one power
    import openpyxl
    v9.mkdir()
    for name, rows in (('ZZ_Aircraft_v9.xlsx', [['ACFT_ID', 'NPD_ID', 'Wing'], ['ZZ-NEO', 'NZ9', 'Wing'],
                                               ['ZZ-BIZ', 'NZ8', 'Fuselage']]),
                       ('ZZ_NPD_Data_v9.xlsx', [['NPD_ID', 'Noise Metric', 'Op Mode', 'Power Setting', 'L_200ft',
                                                 'L_1000ft'], ['NZ9', 'LAmax', 'D         ', 15000, 93.0, 78.0],
                                                ['NZ1', 'LAmax', 'D', 30000, 101.0, 86.0]])):
        wb = openpyxl.Workbook()
        for r in rows:
            wb.active.append(r)
        wb.save(v9 / name)
    t = nd.noise_tables(v23, v9)
    assert t['aircraft'] == {'ZZ-JET': ('NZ1', 'wing'), 'ZZ-TAIL': ('NZ2', 'fuselage'), 'ZZ-PROP': ('NZ3', 'prop'),
                             'ZZ-NEO': ('NZ9', 'wing'), 'ZZ-BIZ': ('NZ8', 'fuselage')}
    assert t['curves'][('NZ9', 'D')] == [(15000.0, [(200 * d29.FT, 93.0), (1000 * d29.FT, 78.0)])]
    # A later release replaces an NPD id's curves whole: NZ1's departure is v9's one power, never mixed with v2.3's.
    assert [p for p, _ in t['curves'][('NZ1', 'D')]] == [30000.0]
    assert [p for p, _ in t['curves'][('NZ1', 'A')]] == [3000.0]


def test_rule_2_is_doc29s_5_12_with_5_11s_median():
    # Hand-worked (S = 2): L0 = L - 4 ln10 / 20 = L - 0.4605; the share at or above 65 is 1 - Phi((65 - L0) / 2), read
    # from a printed normal table: 1 - Phi(1.2303) = 0.1093, 1 - Phi(0.2303) = 0.4089, 1 - Phi(-0.7697) = 0.7793.
    assert nd.SPREAD_MEDIAN_SHIFT_DB == pytest.approx(0.460517, abs=1e-6)
    got = nd.exceed_probability([63.0, 65.0, 67.0])
    assert got.tolist() == pytest.approx([0.1093, 0.4089, 0.7793], abs=1e-4)
    # The table level is the DECIBEL average, above the median: half the events reach 65 only at 65.46 dB.
    assert float(nd.exceed_probability(65.0 + nd.SPREAD_MEDIAN_SHIFT_DB)) == pytest.approx(0.5, abs=1e-12)
    # Levels are computed down to where a share is under 3e-7 (five standard deviations), said in the module.
    assert nd.SPREAD_FLOOR_DB == pytest.approx(55.4605, abs=1e-4)
    assert float(nd.exceed_probability(nd.SPREAD_FLOOR_DB)) < 3e-7
    assert float(nd.exceed_probability(nd.SPREAD_FLOOR_DB + 1.0)) > 3e-7


def test_rule_4s_hybrid_flies_the_default_power_at_the_observed_heights():
    # Path nodes (x, y, z, power, bank, roll, speed, s); the track (s, x, y, gs, h) heard from s = 1,000 to 9,000 m.
    path = [(0, 0, 1.0, 9000.0, 0, True, 0, 0.0), (1500, 0, 1.0, 9000.0, 0, True, 150, 1500.0),
            (3000, 0, 300.0, 8000.0, 0, False, 170, 3000.0), (6000, 0, 900.0, 7000.0, 5, False, 200, 6000.0),
            (12000, 0, 2000.0, 6000.0, 0, False, 250, 12000.0)]
    track = [(1000.0, 1000, 0, 140, None), (2000.0, 2000, 0, 160, 50.0), (4000.0, 4000, 0, 180, 250.0),
             (9000.0, 9000, 0, 220, 600.0)]
    got = nd.hybrid_heights(path, track)
    assert got[0] == path[0] and got[1] == path[1]  # the take-off roll keeps its own height
    assert got[2][2] == pytest.approx(150.0) and got[3][2] == pytest.approx(250.0 + 2000 / 5000 * 350.0)
    assert got[4] == path[4]  # beyond the heights heard: the default's
    assert [n[3] for n in got] == [n[3] for n in path]  # the default's power, never touched
    assert nd.hybrid_heights(path, [(0.0, 0, 0, 0, None)]) == path  # nothing heard: the default path


@pytest.mark.parametrize('field, how, refused', [
    (None, 'too few aircraft', True),
    (-200.0, 'p10 of 380 in-zone minima (no surface reports)', True),
    (-200.0, 'touchdown median of 421 aircraft', True),  # the month's METAR not cached: the fallback
    (-200.0, 'touchdown median of 421 aircraft, shaped by METAR', False),
])
def test_a_day_whose_field_level_is_not_shaped_by_metar_is_refused(field, how, refused):
    assert (nd.field_refusal(field, how) is not None) is refused


def _caa_month(tmp_path, period, heathrow):
    import adsb_movements as am
    p = tmp_path / f'table_03_{period}.csv'
    with open(p, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['rundate', 'reporting_period', 'reporting_airport_name', 'grand_total'])
        for name, code in am.CAA_NAMES.items():
            w.writerow(['01/01/2027 00:00', period, name, heathrow if code == 'LHR' else 1000])
    return p


def test_rule_1s_yardstick_is_the_caas_month_over_its_days_times_ercds_16_hour_share(tmp_path):
    import datetime as dt
    movements, how = nd.caa_day_movements(_caa_month(tmp_path, '202607', 31000), 'LHR', dt.date(2026, 7, 8))
    assert movements == pytest.approx(31000 / 31 * 1232.0 / 1315.0)
    assert how['grand_total'] == 31000 and how['days_in_month'] == 31
    with pytest.raises(ValueError, match='not 202608'):  # another month's table is never used
        nd.caa_day_movements(_caa_month(tmp_path, '202607', 31000), 'LHR', dt.date(2026, 8, 3))
    with pytest.raises(ValueError, match='no 16-hour share'):
        nd.caa_day_movements(_caa_month(tmp_path, '202607', 31000), 'LGW', dt.date(2026, 7, 8))


def _day_file(path, **meta):
    m = {'airport': 'LHR', 'day': path.stem[4:14], 'grid': {'x0': 0, 'y0': 0, 'nx': 2, 'ny': 1}, 'cell_m': 100.0,
         'threshold_db': 65.0, 'window_local': '07:00-23:00', 'code': 'c0de', 'anp_fingerprint': 'f00d',
         'spread': {'s_db': 2.0}, 'variant': 'default', 'computed_share': 0.97, 'movements': 10}
    m.update(meta)
    z = np.array([60, 0], np.int32)
    np.savez_compressed(path, meta=json.dumps(m), arrivals=z, departures_light=z, departures_heavy=z)
    return str(path)


@pytest.mark.parametrize('key, value', [('code', 'other'), ('anp_fingerprint', 'other'), ('threshold_db', 70.0),
                                        ('window_local', '00:00-24:00'), ('variant', 'hybrid'), ('spread', None)])
def test_combine_refuses_days_made_differently(tmp_path, key, value, capsys):
    a = _day_file(tmp_path / 'LHR-2026-07-08-n65.npz')
    b = _day_file(tmp_path / 'LHR-2026-07-15-n65.npz', **{key: value})
    assert nd.main(['combine', '--day', f'{a}=0.63', '--day', f'{b}=0.37', '--out', str(tmp_path / 'c')]) == 2
    assert f'{key} differs' in capsys.readouterr().out
    c = _day_file(tmp_path / 'LHR-2026-07-15-n65.npz')
    assert nd.main(['combine', '--day', f'{a}=0.63', '--day', f'{c}=0.37', '--out', str(tmp_path / 'c')]) == 0


def test_the_code_fingerprint_moves_with_any_n65_script(tmp_path):
    import shutil
    for name in nd.N65_SCRIPTS:
        shutil.copy(nd.REPO / 'scripts' / name, tmp_path / name)
    before = nd.code_version(tmp_path)
    assert before == nd.code_version(nd.REPO / 'scripts')
    (tmp_path / 'n65_grid.py').write_bytes((tmp_path / 'n65_grid.py').read_bytes().replace(b'\r\n', b'\n'))
    assert nd.code_version(tmp_path) == before  # line endings are not code
    with open(tmp_path / 'n65_grid.py', 'ab') as fh:
        fh.write(b'\n# changed\n')
    assert nd.code_version(tmp_path) != before


def test_an_output_inside_the_repo_must_be_one_git_ignores(tmp_path):
    assert nd._safe_out(tmp_path / 'out')
    assert nd._safe_out(nd.REPO / 'data' / 'n65' / 'step5-out')
    assert not nd._safe_out(nd.REPO / 'scripts' / 'out')
    assert not nd._outside_repo(nd.REPO / 'data' / 'n65' / 'x.csv')
