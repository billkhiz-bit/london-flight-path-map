"""The Doc 29 arithmetic N65 counts with (2026-10-28), held against Doc 29's own worked results.

`scripts/n65_doc29.py` gives one flight's maximum sound level at one point. ECAC publishes reference cases with every
intermediate value (Doc 29 5th edition, Volume 3 Part 1 workbook, sheet B-2: 3,516 segment-and-receptor rows for two
reference aircraft on four routes). These tests recompute each row from its inputs and require ECAC's values: the
segment geometry (length, the distances to its ends and to its extension, q, and for observers alongside the lateral
displacement and elevation angle), the depression angle with bank, the installation correction, the lateral
attenuation, the impedance adjustment and the noise-table interpolation. The workbook is ECAC's and stays in the
gitignored data/n65/; without it these tests skip and say why. The two smaller tests below run anywhere.
Offline only.
"""
import importlib.util
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WORKBOOK = REPO / 'data' / 'n65' / 'source' / 'doc29-5th' / 'Doc29-5th_Edition-Volume_3_Part_1-Workbook.xlsx'


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d29 = _load('n65_doc29')
FT = d29.FT


@pytest.fixture(scope='module')
def ecac():
    """ECAC's reference cases: {sheet: [row dict]} for the sheets the tests read."""
    if not WORKBOOK.exists():
        pytest.skip(f'{WORKBOOK.relative_to(REPO)} is not on this machine (gitignored: ECAC Doc 29 Vol 3 workbook)')
    openpyxl = pytest.importorskip('openpyxl')
    wb = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)
    out = {}
    for sheet in ('A-1_Aircraft', 'A-7_NPD_Curves', 'A-12_Receptors', 'B-2_Segment_Results'):
        rows = wb[sheet].iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else '' for h in next(rows)]
        out[sheet] = [dict(zip(header, r, strict=False)) for r in rows if r and r[0] is not None]  # rows run short
    return out


def _rows(ecac):
    receptors = {r['receptor_ID']: (r['X coordinate (m)'], r['Y coordinate (m)'], r['Height (m)'])
                 for r in ecac['A-12_Receptors']}
    for r in ecac['B-2_Segment_Results']:
        get = {k.split('(')[0]: v for k, v in r.items()}  # 'angle_beta(°)' -> 'angle_beta'
        s1 = tuple(get[f'segment_start_{a}'] * FT for a in 'xyz')
        s2 = tuple(get[f'segment_end_{a}'] * FT for a in 'xyz')
        yield r['case_ID'], receptors[r['receptor_ID']], s1, s2, get


def _close(a, b, tol):
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=tol)


# JUDGED IN DECIBELS (28 Oct). ECAC's own geometry differs from an exact recomputation by up to 3e-4 of a distance
# (1-2 cm in hundreds of metres; rounding in its feet/metres conversions) and, by a curved arrival's runway end, by
# up to 0.3 m of lateral displacement: worth at most 0.004 dB. So distances are held to DISTANCE_REL, and the angles
# and the lateral displacement by what they do to a level: the corrections they give, to DB.
DISTANCE_REL = 5e-4
DB = 0.005


def test_geometry_matches_ecac_on_every_row(ecac):
    mount = {a['Aircraft Identifier'].strip(): a['Lateral Directivity Identifier'].strip().lower()
             for a in ecac['A-1_Aircraft']}
    wrong, alongside = [], 0
    for case, o, s1, s2, get in _rows(ecac):
        if s1 == s2:
            continue
        g = d29.geometry(s1, s2, o)
        for name, ours, theirs in (('length', g['length'], get['segment_length']), ('d1', g['d1'], get['distance_d1']),
                                   ('d2', g['d2'], get['distance_d2']), ('dp', g['dp'], get['slant_distance'])):
            if not math.isclose(ours, theirs * FT, rel_tol=DISTANCE_REL, abs_tol=0.05):
                wrong.append((case, get['receptor_ID'], get['segment_ID'], name, ours, theirs * FT))
        # q follows from the distances (q = (d1^2 - d2^2 + l^2) / 2l), so their small differences carry into it,
        # scaled by distance over segment length: up to 0.46 m on a curve's short segments. Judged on that scale.
        if not math.isclose(g['q'], get['distance_q'] * FT, abs_tol=DISTANCE_REL * max(g['d1'], g['d2'])):
            wrong.append((case, get['receptor_ID'], get['segment_ID'], 'q', g['q'], get['distance_q'] * FT))
        # Volume 3 tabulates EXPOSURE levels: their depression angle is the extension's closest point (beta_p), except
        # behind a take-off roll or ahead of a landing roll, where it is the end point's, as LAmax's always is (beta).
        ground = max(s1[2], s2[2]) <= 1.0 + 1e-6  # Volume 3's ground roll runs 1 m up
        roll = ground and ((case[4] == 'D' and g['where'] == 'behind') or (case[4] == 'A' and g['where'] == 'ahead'))
        phi = (g['beta'] if roll else g['beta_p']) + g['side'] * (get['bank_angle'] or 0.0)
        if abs(d29.installation_correction(phi, mount[case[:4]]) - get['engine_Install_correction']) > DB:
            wrong.append((case, get['receptor_ID'], get['segment_ID'], 'installation from phi', phi, get['angle_phi']))
        if g['where'] == 'alongside':
            alongside += 1
            if abs(d29.lateral_attenuation(g['beta'], g['lateral']) - get['lateral_attenuation']) > DB:
                wrong.append((case, get['receptor_ID'], get['segment_ID'], 'lateral from beta, l', g['beta'],
                              get['angle_beta']))
    assert alongside >= 50, 'too few observers alongside a segment to test the elevation angle (81 on 28 Oct)'
    assert wrong == [], f'{len(wrong)} values differ from ECAC, first: {wrong[:5]}'


def test_corrections_match_ecac_on_every_row(ecac):
    mount = {a['Aircraft Identifier'].strip(): a['Lateral Directivity Identifier'].strip().lower()
             for a in ecac['A-1_Aircraft']}
    wrong, n = [], 0
    for case, _, _, _, get in _rows(ecac):
        n += 1
        m = mount[case[:4]]
        ours = (d29.installation_correction(get['angle_phi'], m),
                d29.lateral_attenuation(get['angle_beta'], get['lateral_displacement'] * FT),
                d29.impedance_adjustment())
        theirs = (get['engine_Install_correction'], get['lateral_attenuation'], get['acoustic_impedance_adjustment'])
        for name, a, b in zip(('installation', 'lateral', 'impedance'), ours, theirs, strict=True):
            if not _close(a, b, 0.005):
                wrong.append((case, name, round(a, 4), b))
    assert n > 3000
    assert wrong == [], f'{len(wrong)} corrections differ from ECAC, first: {wrong[:5]}'


def test_the_noise_table_is_read_as_ecac_reads_it(ecac):
    tables = {}
    for r in ecac['A-7_NPD_Curves']:
        key = (r['Aircraft Identifier'].strip(), r['Noise Descriptor'].strip(), r['Operation Mode'].strip())
        by_ft = {float(k.split('_')[1].split()[0]): v for k, v in r.items() if k.startswith('L_')}
        tables.setdefault(key, []).append((r['Power Setting (lb)'], by_ft))
    curves = {k: d29.npd_curves(v) for k, v in tables.items()}
    wrong = []
    for case, _, _, _, get in _rows(ecac):
        c = curves[(case[:4], 'SEL', case[4])]  # JETFAC -> JETF, arrival
        ours = d29.npd_level(c, get['NPD_interpolation_thrust'], get['NPD_interpolation_distance'] * FT)
        if not _close(ours, get['baseline_SEL'], 0.005):
            wrong.append((case, round(ours, 3), get['baseline_SEL']))
    assert wrong == [], f'{len(wrong)} table readings differ from ECAC, first: {wrong[:5]}'


def test_interpolation_and_extrapolation_by_hand():
    curves = d29.npd_curves([(1000, {200: 90.0, 2000: 70.0}), (3000, {200: 96.0, 2000: 76.0})])
    assert d29.npd_level(curves, 1000, 632.456 * FT) == pytest.approx(80.0, abs=1e-3)  # halfway in log distance
    assert d29.npd_level(curves, 2000, 200 * FT) == pytest.approx(93.0)  # halfway in power
    assert d29.npd_level(curves, 1000, 20000 * FT) == pytest.approx(50.0)  # outwards from the last two
    assert d29.npd_level(curves, 1000, 1.0) == d29.npd_level(curves, 1000, d29.NPD_MIN_DISTANCE_M)  # 30 m floor
    assert d29.npd_level(curves, -50, 200 * FT) == d29.npd_level(curves, d29.MIN_POWER, 200 * FT)


def test_a_flight_is_as_loud_as_its_loudest_segment():
    curves = d29.npd_curves([(5000, {200: 95.0, 400: 89.0, 1000: 81.0, 2000: 74.0, 4000: 66.0, 10000: 52.0})])
    path = [(-5000, 0, 300, 5000, 0.0), (0, 0, 300, 5000, 0.0), (5000, 0, 600, 5000, 0.0)]
    below = d29.event_lmax(path, (0, 0, 0), curves, 'wing')
    assert below == pytest.approx(d29.npd_level(curves, 5000, 300) + d29.installation_correction(90, 'wing')
                                  - d29.lateral_attenuation(90, 0.0))
    assert d29.event_lmax(path, (0, 1500, 0), curves, 'wing') < below  # to the side: farther and attenuated


def test_start_of_roll_matches_ecac_on_every_row(ecac):
    """Behind a take-off ground roll (Volume 3's departures, ground segments 1 m up) ECAC's start-of-roll correction;
    everywhere else none: ahead of a take-off roll, landing rolls and anything airborne get 0."""
    mount = {a['Aircraft Identifier'].strip(): a['Lateral Directivity Identifier'].strip().lower()
             for a in ecac['A-1_Aircraft']}
    wrong, applied = [], 0
    for case, o, s1, s2, get in _rows(ecac):
        if s1 == s2:
            continue
        g = d29.geometry(s1, s2, o)
        roll = case[4] == 'D' and max(s1[2], s2[2]) <= 1.0 + 1e-6
        engine = 'prop' if mount[case[:4]] == 'prop' else 'jet'
        ours = d29.start_of_roll(g['q'], g['lateral'], engine) if roll else 0.0  # behind: lateral = ground distance
        applied += ours != 0.0
        if abs(ours - get['start_of_roll_correction']) > DB:
            wrong.append((case, get['receptor_ID'], get['segment_ID'], round(ours, 3), get['start_of_roll_correction']))
    assert applied >= 20, f'only {applied} rows behind a take-off roll: the test barely reaches the correction'
    assert wrong == [], f'{len(wrong)} start-of-roll corrections differ from ECAC, first: {wrong[:5]}'


def test_the_start_of_roll_fades_past_762_m_and_never_applies_ahead():
    near = d29.start_of_roll(-700.0, 700.0, 'jet')  # straight behind, inside the normalising distance
    assert near == pytest.approx(d29.start_of_roll(-1.0, 1.0, 'jet'))  # same angle, any distance up to 762 m
    assert d29.start_of_roll(-1524.0, 1524.0, 'jet') == pytest.approx(near * 762 / 1524)
    assert d29.start_of_roll(10.0, 500.0, 'jet') == 0.0  # ahead of the segment's start
