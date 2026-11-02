"""N65 step 4: a flight's height, speed and engine power from its procedural steps (scripts/n65_profiles.py).

Held two ways.
1. ECAC's own worked results. Doc 29 5th edition Volume 3 Part 2 publishes flight-profile reference cases (17
   departures, 9 approaches, two hypothetical aircraft) computed by Volume 2 Appendix B from procedural steps, with
   every profile point's distance, height, true airspeed and corrected net thrust. These tests fly each case and
   require ECAC's points. The workbook is ECAC's and stays in the gitignored data/n65/; without it they skip and say
   why. None of its values is copied here.
2. MADE-UP aircraft (ZZJET, ZZPROP: every coefficient invented) hold each rule anywhere, by hand-worked values.

EASA's ANP tables never enter this repo: one test flies every ANP default profile when the gitignored tables are on
the machine and asserts shapes only (it flies, it moves forward, it lands), never a figure. Offline only.
"""

import csv
import dataclasses
import importlib.util
import itertools
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PART2 = REPO / 'data' / 'n65' / 'source' / 'doc29-5th' / 'Doc29-5th_Edition-Volume_3_Part_2-Workbook-readonly.xlsx'
ANP_V23 = REPO / 'data' / 'n65' / 'source' / 'anp-v2.3' / 'tables'
ANP_V9 = Path.home() / 'data' / 'easa-anp-v9'  # EASA's newer release, kept outside the repo (docs/lessons/n65.md)


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pr = _load('n65_profiles')
Step, Point, Atmosphere, REF = pr.Step, pr.Point, pr.Atmosphere, pr.REFERENCE
K, G = 1.68781, 32.174

# JUDGED AT ECAC'S PRINT PRECISION (1 Nov). Volume 3 prints every value to 0.1 (ft, kt, lb), so rounding alone allows
# 0.05; the measured worst on height, speed and thrust is 0.050. Distances add up step by step, and an Accelerate step
# stops iterating once two altitude estimates agree within a foot (B6.1.3), so implementations agreeing on the method
# differ in its last digits: measured worst 0.145 ft (in 50,000), and iterating further or recomputing the distance at
# the final altitude moves cases by 10 to 22 ft. 0.2 ft is 6 cm along a flight, nothing to a noise level.
DIST_FT, HEIGHT_FT, TAS_KT, THRUST_LB = 0.2, 0.06, 0.06, 0.06


# ----------------------------------------------------------------- ECAC's reference cases (Volume 3 Part 2)


def _as_printed(row):
    """A Table C-6.2 row as Volume 3 prints it, which is what ECAC's results were computed from.
    The workbook writes the step inputs as unrounded metric conversions (a 15.2 m height to 14 decimals); the printed
    table rounds them to 0.1, and only those reproduce ECAC's points: unrounded, one case's last airborne point sits
    0.5 ft off and its Level-Decel thrusts move by up to 0.9 lb. The workbook also files the Level-Idle steps' distance
    under Descent Angle; ANP's own tables put it under Distance, where the module reads it."""
    row = dict(row)
    if pr._norm(row['steptype']) == 'levelidle' and row.get('distance') in (None, ''):
        row['distance'], row['descentangle'] = row['descentangle'], None
    for k in ('startaltitude', 'startcas', 'touchdownroll', 'distance'):
        if isinstance(row.get(k), float):
            row[k] = round(row[k], 1)
    return row


@pytest.fixture(scope='module')
def ecac():
    if not PART2.exists():
        pytest.skip(f'{PART2.relative_to(REPO)} is not on this machine (gitignored: ECAC Doc 29 Vol 3 Part 2 workbook)')
    openpyxl = pytest.importorskip('openpyxl')
    wb = openpyxl.load_workbook(PART2, read_only=True, data_only=True)

    def sheet(name):
        it = wb[name].iter_rows(values_only=True)
        head = next(it)
        return pr.keyed(dict(zip(head, r, strict=False)) for r in it if r and r[0] is not None)

    tables = [sheet(s) for s in ('C-2(Jet_Coeff)', 'C-3(Prop_Coeff)', 'C-4(Aerodynamic_Coeff)', 'C-5(Default_Weights)')]
    perf = {pr._text(a['acftid']): pr.performance_from_rows(a, *tables) for a in sheet('C-1(Aircraft)')}
    steps = {
        'D': sheet('C-6.1(DepartureProcedure_Steps)'),
        'A': [_as_printed(r) for r in sheet('C-6.2(ApproachProcedure_Steps)')],
    }
    results = {}
    for name in ('D1-(Arrival_Results)', 'D2-(Departure_Results)'):
        for r in sheet(name):
            results.setdefault(pr._text(r['casenumber']), []).append(r)
    cases = [(op, c) for op, s in (('D', 'C8-(Departure_Cases)'), ('A', 'C7-(Arrival_Cases)')) for c in sheet(s)]
    wb.close()  # read_only holds the file open until closed (a Windows lock on ECAC's workbook)
    return {'perf': perf, 'steps': steps, 'results': results, 'cases': cases}


def _fly(ecac, op_wanted):
    """(case, our points, ECAC's points) for every reference case of one operation."""
    for op, c in ecac['cases']:
        if op != op_wanted:
            continue
        cid, acft, proc = pr._text(c['casenumber']), pr._text(c['acftid']), pr._text(c['procedure'])
        atm = Atmosphere(float(c['elevation']), float(c['temperature']), float(c['slpressure']), float(c['headwind']))
        rows = [r for r in ecac['steps'][op] if pr._text(r['acftid']) == acft and pr._text(r['profileid']) == proc]
        assert rows, f'case {cid}: no steps for {acft} {proc}'
        perf = ecac['perf'][acft]
        steps = pr.steps_from_rows(rows)
        ours = pr.departure(perf, steps, perf.weights['1'], atm) if op == 'D' else pr.approach(perf, steps, atm)
        yield cid, ours, sorted(ecac['results'][cid], key=lambda r: r['pointnumber'])


def _compare(ecac, op):
    wrong, seen, n = [], set(), 0
    for cid, ours, ref in _fly(ecac, op):
        seen.add(cid)
        if len(ours) != len(ref):
            wrong.append((cid, 'number of points', len(ours), len(ref)))
            continue
        for i, (a, b) in enumerate(zip(ours, ref, strict=True), start=1):
            n += 1
            for name, x, y, tol in (
                ('distance', a.distance_ft, b['distance'], DIST_FT),
                ('height', a.height_ft, b['altitude'], HEIGHT_FT),
                ('tas', a.tas_kt, b['trueairspeed'], TAS_KT),
                ('thrust', a.thrust, b['correctednetthrust'], THRUST_LB),
            ):
                if abs(x - y) > tol:
                    wrong.append((cid, i, a.step, name, round(x - y, 3)))
    return wrong, seen, n


def test_every_departure_reference_case_is_flown_as_ecac_flies_it(ecac):
    wrong, seen, n = _compare(ecac, 'D')
    cases = {pr._text(c['casenumber']) for op, c in ecac['cases'] if op == 'D'}
    assert seen == cases and len(cases) >= 17, 'Volume 3 has 17 departure cases'
    assert n == sum(len(ecac['results'][c]) for c in cases)
    assert wrong == [], f'{len(wrong)} departure values differ from ECAC, first: {wrong[:6]}'


def test_every_approach_reference_case_is_flown_as_ecac_flies_it(ecac):
    wrong, seen, n = _compare(ecac, 'A')
    cases = {pr._text(c['casenumber']) for op, c in ecac['cases'] if op == 'A'}
    assert seen == cases and len(cases) >= 9, 'Volume 3 has 9 approach cases'
    assert n == sum(len(ecac['results'][c]) for c in cases)
    assert wrong == [], f'{len(wrong)} approach values differ from ECAC, first: {wrong[:6]}'


def test_every_result_belongs_to_a_case(ecac):
    cases = {pr._text(c['casenumber']) for _, c in ecac['cases']}
    assert set(ecac['results']) == cases  # nothing ECAC published is left unflown


# ----------------------------------------------------------------- made-up aircraft


def _jet(**over):
    """ZZJET: a made-up twin jet. Every number is invented."""
    base = dict(
        acft_id='ZZJET',
        engines=2,
        max_landing_weight_lb=100_000.0,
        max_static_thrust_lb=20_000.0,
        power_parameter='CNT (lb)',
        jet={
            'maxtakeoff': (20_000.0, -20.0, 0.25, 0.0, 0.0),
            'maxclimb': (13_000.0, -5.0, 0.35, -1e-5, 0.0),
            'idleapproach': (900.0, -5.0, 0.15, -1e-5, 0.0),
        },
        aero={
            ('D', 'T1'): {'B': 0.008, 'C': 0.45, 'R': 0.075},
            ('D', 'CLEAN'): {'R': 0.06},
            ('A', 'CLEAN'): {'R': 0.06},
            ('A', 'F1'): {'R': 0.08},
            ('A', 'FULL'): {'R': 0.12, 'D': 0.4},
        },
        weights={'1': 120_000.0},
    )
    base.update(over)
    return pr.Performance(**base)


PROP = pr.Performance(
    'ZZPROP',
    2,
    40_000.0,
    5_000.0,
    'CNT (% of Max Static Thrust)',
    prop={'maxtakeoff': (0.8, 2500.0), 'maxclimb': (0.8, 2000.0)},
    aero={('D', 'T15'): {'B': 0.01, 'C': 0.6, 'R': 0.1}, ('D', 'CLEAN'): {'R': 0.07}},
    weights={'1': 45_000.0},
)
W_TO = 120_000.0
W_APP = 90_000.0  # 90% of ZZJET's maximum landing weight (B-40)
TAKEOFF = Step('takeoff', 'T1', 'maxtakeoff')
TO_1000 = [TAKEOFF, Step('climb', 'T1', 'maxtakeoff', end_altitude_ft=1000.0)]


def _sigma(h, atm=REF):
    return atm.sigma(atm.elevation_ft + h)


def _flat(rows):
    """Rows of numbers as one list, for pytest.approx (which compares flat sequences only)."""
    return [float(x) for row in rows for x in row]


def test_the_reference_day_is_the_standard_atmosphere():
    assert (REF.theta(0), REF.delta(0), REF.sigma(0)) == pytest.approx((1.0, 1.0, 1.0))
    assert REF.pressure_altitude(5000) == pytest.approx(5000, abs=1e-6)  # B-6 undoes B-4 at standard pressure
    assert REF.delta(10_000) == pytest.approx(0.6877, abs=1e-4)  # the ISA pressure ratio at 10,000 ft
    hot = Atmosphere(elevation_ft=1000, temperature_c=35)
    assert hot.temp_c(1000) == pytest.approx(35)  # the surface temperature is the aerodrome's
    assert hot.temp_c(2000) == pytest.approx(35 - 0.003566 * 1000 * 5 / 9)  # B-2: ISA lapse above it
    assert hot.sigma(1000) < REF.sigma(1000)  # hot air is thinner
    assert -1000 < Atmosphere(qnh_inhg=30.92).pressure_altitude(0) < -850  # high pressure: ~1,000 ft per inHg below


def test_jet_thrust_takes_the_lower_of_normal_and_hot_b9_to_b11():
    perf = _jet()
    e, f, ga, gb, hh = perf.jet['maxclimb']
    vc, alt = 200.0, 3000.0
    h, t = REF.pressure_altitude(alt), REF.temp_c(alt)
    assert pr.rated_thrust(perf, 'MaxClimb', REF, alt, vc, 0) == pytest.approx(
        e + f * vc + ga * h + gb * h * h + hh * t
    )
    assert pr.rated_thrust(perf, 'Max-Climb', REF, alt, vc, 0) == pr.rated_thrust(perf, 'MAXCLIMB', REF, alt, vc, 0)
    hot = Atmosphere(temperature_c=40.0)
    t = hot.temp_c(0)
    b9 = e + f * vc + hh * t
    b11 = f * vc + (e + hh * 30) * (1 - 0.006 * t) / (1 - 0.006 * 30)
    assert b11 < b9
    assert pr.rated_thrust(perf, 'MaxClimb', hot, 0, vc, 0) == pytest.approx(b11)  # departures: B-11 stands in
    assert pr.rated_thrust(perf, 'MaxClimb', hot, 0, vc, 0, departure=False) == pytest.approx(b9)  # approach: no B-11
    with_hi = _jet(jet={**perf.jet, 'maxclimbhitemp': (15_000.0, -5.0, 0.0, 0.0, -100.0)})
    assert pr.rated_thrust(with_hi, 'MaxClimb', hot, 0, vc, 0) == pytest.approx(15_000 - 5 * vc - 100 * t)  # B-10
    with pytest.raises(KeyError):
        pr.rated_thrust(perf, 'ReduceClimb', REF, 0, vc, 0)


def test_propeller_thrust_is_power_over_speed_b12():
    vt, alt = 180.0, 2000.0
    assert pr.rated_thrust(PROP, 'MaxClimb', REF, alt, 0, vt) == pytest.approx(326 * 0.8 * 2000 / vt / REF.delta(alt))


def test_minimum_thrust_holds_the_engine_out_gradient_b13():
    perf, r = _jet(), 0.075
    wd = W_TO / REF.delta(1000)
    assert pr.minimum_thrust(perf, W_TO, REF, 1000, 180, r) == pytest.approx(
        wd * (math.sin(math.atan(0.012)) / 1.01 + r)
    )
    assert pr.minimum_thrust(perf, W_TO, REF, 1000, 250, r) == pytest.approx(
        wd * (math.sin(math.atan(0.012)) / 0.95 + r)
    )
    with pytest.raises(ValueError):
        pr.minimum_thrust(_jet(engines=1), W_TO, REF, 1000, 180, r)
    # Climbing on it with all engines: sin(gamma) = K (N/(N-1) (sin(atan G')/K + R) - R), whatever the height.
    pts = pr.departure(perf, [*TO_1000, Step('climb', 'T1', 'MinimumThrust', end_altitude_ft=2000.0)], W_TO)
    start, end = pts[-3], pts[-1]
    assert [p.step for p in pts[-2:]] == ['transition', 'climb']
    sin_g = 1.01 * (2 * (math.sin(math.atan(0.012)) / 1.01 + r) - r)
    gradient = (end.height_ft - start.height_ft) / (end.distance_ft - start.distance_ft)
    assert math.atan(gradient) == pytest.approx(math.asin(sin_g))


def test_the_take_off_roll_b15_to_b17():
    perf = _jet()
    pts = pr.departure(perf, [TAKEOFF], W_TO)
    vc = 0.45 * math.sqrt(W_TO)
    cnt2 = 20_000 - 20 * vc
    assert _flat((p.distance_ft, p.height_ft, p.tas_kt) for p in pts) == pytest.approx(
        _flat([(0, 0, 0), (0.008 * W_TO**2 / (2 * cnt2), 0, vc)])
    )
    assert (pts[0].thrust, pts[1].thrust) == pytest.approx((20_000, cnt2))  # standing, then at lift-off speed
    calm = pr.departure(perf, [TAKEOFF], W_TO, Atmosphere(headwind_kt=0))
    assert calm[1].distance_ft == pytest.approx(pts[1].distance_ft * (vc / (vc - 8)) ** 2)  # B-17


def test_a_climb_holds_its_calibrated_airspeed_b19_to_b23():
    perf = _jet()
    steps = [TAKEOFF, Step('climb', 'T1', 'maxtakeoff', end_altitude_ft=1500.0)]
    pts = pr.departure(perf, steps, W_TO)
    p1, p2 = pts[1], pts[2]
    vc = p1.tas_kt
    assert p2.tas_kt * math.sqrt(_sigma(1500)) == pytest.approx(vc)
    cnt_mid = 20_000 - 20 * vc + 0.25 * REF.pressure_altitude(750)
    gamma = math.asin(1.01 * (2 * cnt_mid / (W_TO / REF.delta(750)) - 0.075))
    assert p2.distance_ft - p1.distance_ft == pytest.approx(1500 / math.tan(gamma))
    windy = pr.departure(perf, steps, W_TO, Atmosphere(headwind_kt=20))
    gamma_w = gamma * (vc - 8) / (vc - 20)  # B-22: steeper over the ground into a stronger wind
    assert windy[2].distance_ft - windy[1].distance_ft == pytest.approx(1500 / math.tan(gamma_w))


def test_a_thrust_change_is_spread_over_the_first_1000_ft_b34_to_b37():
    perf = _jet()
    steps = [
        *TO_1000,
        Step('climb', 'T1', 'maxclimb', end_altitude_ft=3000.0),
        Step('climb', 'CLEAN', 'maxclimb', end_altitude_ft=4000.0),
    ]
    pts = pr.departure(perf, steps, W_TO)
    assert [p.step for p in pts] == ['takeoff', 'takeoff', 'climb', 'transition', 'climb', 'climb']  # only on a change
    p1, pi, p2 = pts[2], pts[3], pts[4]
    assert pi.distance_ft - p1.distance_ft == pytest.approx(1000)
    assert pi.height_ft == pytest.approx(
        p1.height_ft + (p2.height_ft - p1.height_ft) * 1000 / (p2.distance_ft - p1.distance_ft)
    )
    vc = p1.tas_kt * math.sqrt(_sigma(p1.height_ft))
    assert pi.tas_kt * math.sqrt(_sigma(pi.height_ft)) == pytest.approx(vc)  # B-36
    assert pi.thrust == pytest.approx(pr.rated_thrust(perf, 'maxclimb', REF, pi.height_ft, vc, pi.tas_kt))  # B-37
    short = pr.departure(perf, [*TO_1000, Step('climb', 'T1', 'maxclimb', end_altitude_ft=1100.0)], W_TO)
    assert short[3].distance_ft - short[2].distance_ft == pytest.approx(
        (short[4].distance_ft - short[2].distance_ft) / 2
    )


def test_an_accelerate_step_reaches_its_speed_b24_to_b28():
    perf = _jet()
    acc = Step('accelerate', 'CLEAN', 'maxclimb', rate_of_climb_fpm=1000.0, end_cas_kt=250.0)
    pts = pr.departure(perf, [*TO_1000, acc], W_TO)
    end = pts[-1]
    assert end.tas_kt * math.sqrt(_sigma(end.height_ft)) == pytest.approx(250)  # B-27
    assert end.thrust == pytest.approx(pr.rated_thrust(perf, 'maxclimb', REF, end.height_ft, 250, end.tas_kt))
    assert end.height_ft > 1000
    level = pr.departure(perf, [*TO_1000, dataclasses.replace(acc, rate_of_climb_fpm=None, accel_pct=100.0)], W_TO)
    assert level[-1].height_ft == pytest.approx(1000)  # all the energy to speed: level (B6.1.5)
    la = pr.departure(perf, [*TO_1000, Step('levelaccelerate', 'CLEAN', 'maxclimb', end_cas_kt=250.0)], W_TO)
    assert _flat(dataclasses.astuple(p)[:4] for p in la) == pytest.approx(
        _flat(dataclasses.astuple(p)[:4] for p in level)
    )
    both = pr.departure(perf, [*TO_1000, dataclasses.replace(acc, accel_pct=60.0)], W_TO)
    esf = pr.departure(perf, [*TO_1000, dataclasses.replace(acc, rate_of_climb_fpm=None, accel_pct=60.0)], W_TO)
    assert both[-1] == esf[-1] and both[-1].height_ft != pytest.approx(end.height_ft)  # energy share wins (B6.1.3)


def test_a_level_step_holds_with_adapted_thrust_b29_b30():
    perf = _jet()
    pts = pr.departure(perf, [*TO_1000, Step('level', 'T1', 'AdaptedThrust', distance_ft=5000.0)], W_TO)
    p1, pi, p2 = pts[-3], pts[-2], pts[-1]
    cnt = 0.075 * W_TO / REF.delta(1000) / 2
    assert pi.step == 'transition' and pi.distance_ft - p1.distance_ft == pytest.approx(1000)  # always (B6.1.4)
    assert (pi.thrust, p2.thrust) == pytest.approx((cnt, cnt))
    assert (p2.distance_ft - p1.distance_ft, p2.height_ft, p2.tas_kt) == pytest.approx((5000, 1000, p1.tas_kt))


def test_a_climb_already_passed_is_skipped_b6_1_3():
    perf = _jet()
    acc = Step('accelerate', 'CLEAN', 'maxclimb', rate_of_climb_fpm=2000.0, end_cas_kt=250.0)
    without = pr.departure(perf, [*TO_1000, acc], W_TO)
    assert without[-1].height_ft > 3000
    assert (
        pr.departure(perf, [*TO_1000, acc, Step('climb', 'CLEAN', 'maxclimb', end_altitude_ft=3000.0)], W_TO) == without
    )


def test_a_propeller_departure_reads_its_power_as_a_percentage():
    pts = pr.departure(
        PROP,
        [Step('takeoff', 'T15', 'maxtakeoff'), Step('climb', 'T15', 'maxtakeoff', end_altitude_ft=1500.0)],
        45_000.0,
    )
    lift_off = 0.6 * math.sqrt(45_000.0)
    assert pts[0].thrust == pytest.approx(326 * 0.8 * 2500 / lift_off)  # B-12 at the rotation speed, standing
    assert pr.npd_power(PROP, pts[1].thrust) == pytest.approx(100 * pts[1].thrust / 5000)
    assert pr.npd_power(_jet(), 12_345.0) == 12_345.0
    with pytest.raises(ValueError):
        pr.npd_power(_jet(power_parameter='Other (RPM)'), 100.0)


# ------------------------------------------- approaches


GAMMA3 = math.radians(3.0)
FINAL = [
    Step('descend', 'FULL', start_altitude_ft=1500.0, start_cas_kt=150.0, descent_angle_deg=3.0),
    Step('descend', 'FULL', start_altitude_ft=50.0, start_cas_kt=145.0, descent_angle_deg=3.0),
    Step('land', 'FULL', touchdown_roll_ft=500.0),
    Step('decelerate', '-NONE-', start_cas_kt=130.0, distance_ft=3000.0, start_thrust_pct=40.0),
    Step('decelerate', '-NONE-', start_cas_kt=30.0, distance_ft=0.0, start_thrust_pct=10.0),
]
APP = [
    Step('descend', 'CLEAN', start_altitude_ft=6000.0, start_cas_kt=250.0, descent_angle_deg=3.0),
    Step('descend', 'F1', start_altitude_ft=3000.0, start_cas_kt=180.0, descent_angle_deg=3.0),
    *FINAL,
]


def test_an_approach_lands_and_rolls_b75_to_b81():
    pts = pr.approach(_jet(), APP)
    assert [p.step for p in pts] == [
        'descend',
        'transition',
        'descend',
        'transition',
        'descend',
        'descend',
        'transition',
        'land',
        'decelerate',
        'decelerate',
    ]
    td = pts[7]
    assert (td.distance_ft, td.height_ft, td.tas_kt) == pytest.approx((0, 0, 0.4 * math.sqrt(W_APP)))
    assert td.thrust == pytest.approx(W_APP / 2 * (0.12 - math.sin(GAMMA3) / 1.03))
    assert _flat((p.distance_ft, p.tas_kt, p.thrust) for p in pts[8:]) == pytest.approx(
        _flat([(500, 130, 8000), (3500, 30, 2000)])
    )
    with pytest.raises(ValueError):
        pr.approach(_jet(), APP[:-1])  # the roll must end with a zero-distance decelerate step


def test_descents_end_where_the_next_step_starts_and_change_thrust_1000_ft_early_b42_to_b47():
    pts = pr.approach(_jet(), APP)
    for p in pts[:7]:  # every point on the 3 degree path to touchdown
        assert p.height_ft == pytest.approx(-p.distance_ft * math.tan(GAMMA3))
    assert pts[3].distance_ft == pytest.approx(pts[4].distance_ft - 1000)  # flap change: 1,000 ft before (B-43)
    assert pts[6].distance_ft == pytest.approx(-50 / math.tan(GAMMA3) / 2)  # a short last step: half of it
    wd = W_APP / REF.delta(6000)
    assert pts[0].thrust == pytest.approx(wd / 2 * (0.06 - math.sin(GAMMA3) / 1.03))  # B-40
    assert pts[1].thrust == pytest.approx(REF.delta(6000) / REF.delta(pts[1].height_ft) * pts[0].thrust)  # B-47
    calm = pr.approach(_jet(), APP, Atmosphere(headwind_kt=0))
    assert calm[0].thrust == pytest.approx(pts[0].thrust + 1.03 * wd * math.sin(GAMMA3) * (0 - 8) / (2 * 250))  # B-48


def test_a_change_of_descent_angle_alone_is_a_thrust_change_b7_1_1():
    same = [
        Step('descend', 'CLEAN', start_altitude_ft=6000.0, start_cas_kt=250.0, descent_angle_deg=3.0),
        Step('descend', 'CLEAN', start_altitude_ft=3000.0, start_cas_kt=220.0, descent_angle_deg=3.0),
        *FINAL,
    ]
    steeper = [dataclasses.replace(same[0], descent_angle_deg=2.8), *same[1:]]
    assert [p.step for p in pr.approach(_jet(), same)][:2] == ['descend', 'descend']  # Case 1: no end point of its own
    assert [p.step for p in pr.approach(_jet(), steeper)][:3] == ['descend', 'transition', 'descend']


@pytest.mark.parametrize('wind', [0.0, 8.0, 15.0])
def test_decelerating_steps_take_the_thrust_their_deceleration_needs_b41_b63(wind):
    steps = [
        Step('descend', 'CLEAN', start_altitude_ft=6000.0, start_cas_kt=250.0, descent_angle_deg=3.0),
        Step('leveldecel', 'CLEAN', start_altitude_ft=3000.0, start_cas_kt=250.0, distance_ft=10_000.0),
        Step('descenddecel', 'F1', start_altitude_ft=3000.0, start_cas_kt=200.0, descent_angle_deg=3.0),
        *FINAL,
    ]
    pts = pr.approach(_jet(), steps, Atmosphere(headwind_kt=wind))
    assert [p.step for p in pts[:7]] == [
        'descend',
        'transition',
        'leveldecel',
        'transition',
        'descenddecel',
        'transition',
        'descend',
    ]
    lvl, dd, after = pts[2], pts[4], pts[6]
    a = K**2 * ((dd.tas_kt - wind) ** 2 - (lvl.tas_kt - wind) ** 2) / (2 * 10_000)
    assert lvl.thrust == pytest.approx(W_APP / REF.delta(3000) / 2 * (0.06 + a / G))  # B-63
    assert pts[3].thrust == lvl.thrust and pts[3].distance_ft == pytest.approx(dd.distance_ft - 1000)
    # B-41 with its TAS read as the horizontal airspeed: (TAS cos g - w) / cos g = TAS - w / cos g (a reading, held by
    # ECAC's cases; with the text's literal form the thrust is several pounds lower).
    w_path = wind / math.cos(GAMMA3)
    a = K**2 * ((after.tas_kt - w_path) ** 2 - (dd.tas_kt - w_path) ** 2) / (2 * 1500 / math.sin(GAMMA3))
    assert dd.thrust == pytest.approx(
        W_APP / REF.delta(3000) / 2 * (0.08 * math.cos(GAMMA3) - math.sin(GAMMA3) + a / G)
    )


IDLE_STEPS = [
    Step('descend', 'CLEAN', start_altitude_ft=6000.0, start_cas_kt=250.0, descent_angle_deg=2.8),
    Step('descendidle', 'CLEAN', start_altitude_ft=4000.0, start_cas_kt=240.0, descent_angle_deg=3.0),
    Step('levelidle', 'CLEAN', start_altitude_ft=3000.0, start_cas_kt=220.0, distance_ft=8000.0),
    Step('descendidle', 'F1', start_altitude_ft=3000.0, start_cas_kt=190.0, descent_angle_deg=3.0),
    Step('descend', 'FULL', start_altitude_ft=1600.0, start_cas_kt=150.0, descent_angle_deg=3.0),
    *FINAL[1:],
]


def test_idle_steps_fly_at_idle_and_change_thrust_only_out_of_idle_b7_1_2_b7_1_4():
    pts = pr.approach(_jet(), IDLE_STEPS)
    assert [p.step for p in pts[:9]] == [
        'descend',
        'transition',
        'descendidle',
        'levelidle',
        'descendidle',
        'transition',
        'descend',
        'descend',
        'transition',
    ]
    for p in pts[2:6]:
        vc = p.tas_kt * math.sqrt(_sigma(p.height_ft))
        assert p.thrust == pytest.approx(pr.rated_thrust(_jet(), 'IdleApproach', REF, p.height_ft, vc, p.tas_kt, False))
    # On the reference day the idle steps fly their inputs as given (the non-ISA adjustments are identities).
    assert pts[2].tas_kt == pytest.approx(240 / math.sqrt(_sigma(4000)))
    assert (pts[4].height_ft, pts[4].distance_ft - pts[3].distance_ft) == pytest.approx((3000, 8000))


def _gs(tas_kt, wind_kt, gamma):
    """Speed along a descending path into a headwind, ft/s (B-57)."""
    return math.sqrt((K * tas_kt) ** 2 - (K * wind_kt * math.sin(gamma)) ** 2) - K * wind_kt * math.cos(gamma)


def test_idle_steps_keep_the_reference_days_deceleration_on_any_day_b57_to_b60_b73_b74():
    day = Atmosphere(elevation_ft=1500, temperature_c=35, qnh_inhg=29.6, headwind_kt=12)
    w = day.headwind_kt
    pts = pr.approach(_jet(), IDLE_STEPS, day)
    di1, li, di2, nxt = pts[2], pts[3], pts[4], pts[6]

    def isa(cas, h):
        return cas / math.sqrt(REF.sigma(h))  # the reference day: ISA at a sea-level aerodrome

    # Descend-Idle into Level-Idle (B-58): the start height stays, the start speed moves.
    assert di1.height_ft == 4000
    ref = (_gs(isa(220, 3000), w, GAMMA3) ** 2 - _gs(isa(240, 4000), w, GAMMA3) ** 2) / (2 * 1000 / math.sin(GAMMA3))
    got = (_gs(li.tas_kt, w, GAMMA3) ** 2 - _gs(di1.tas_kt, w, GAMMA3) ** 2) / (2 * 1000 / math.sin(GAMMA3))
    assert got == pytest.approx(ref) and di1.tas_kt != pytest.approx(240 / math.sqrt(_sigma(4000, day)))
    # Level-Idle (B-73, B-74): the length moves.
    ref = (K * (isa(190, 3000) - w)) ** 2 - (K * (isa(220, 3000) - w)) ** 2
    got = (K * (di2.tas_kt - w)) ** 2 - (K * (li.tas_kt - w)) ** 2
    length = di2.distance_ft - li.distance_ft
    assert got / (2 * length) == pytest.approx(ref / (2 * 8000)) and length != pytest.approx(8000)
    # Descend-Idle into Descend (B-59, B-60): the start speed stays, the start height moves.
    assert di2.tas_kt == pytest.approx(190 / math.sqrt(_sigma(3000, day)))
    ref = (_gs(isa(150, 1600), w, GAMMA3) ** 2 - _gs(isa(190, 3000), w, GAMMA3) ** 2) / (2 * 1400 / math.sin(GAMMA3))
    path = (di2.height_ft - nxt.height_ft) / math.sin(GAMMA3)
    assert (_gs(nxt.tas_kt, w, GAMMA3) ** 2 - _gs(di2.tas_kt, w, GAMMA3) ** 2) / (2 * path) == pytest.approx(ref)
    assert di2.height_ft != pytest.approx(3000)


def test_a_level_step_without_a_speed_holds_the_next_points():
    steps = [*IDLE_STEPS[:2], Step('level', 'CLEAN', start_altitude_ft=3000.0, distance_ft=2000.0), *IDLE_STEPS[2:]]
    pts = pr.approach(_jet(), steps)
    level = next(p for p in pts if p.step == 'level')
    assert level.tas_kt == pytest.approx(220 / math.sqrt(_sigma(3000)))


# ------------------------------------------- along the profile (Vol 2 s3.6)


def test_interpolation_is_linear_in_time_for_speed_and_power_3_2():
    pts = [
        Point(0, 0, 100, 1000),
        Point(1000, 100, 200, 3000),
        Point(2000, 100, 200, -500),
        Point(3000, 200, 100, -1500),
    ]
    assert pr.interpolate(pts, 500) == pytest.approx(
        (50, math.sqrt((100**2 + 200**2) / 2), math.sqrt((1000**2 + 3000**2) / 2))
    )
    assert pr.interpolate(pts, 1500)[2] == pytest.approx(-500 + 3500 * math.sqrt(0.5))  # 3-2g: positive to negative
    assert pr.interpolate(pts, 2500)[2] == pytest.approx(-math.sqrt((500**2 + 1500**2) / 2))  # 3-2e: both negative
    up = [Point(0, 0, 100, -1000), Point(1000, 0, 100, 1000)]
    assert pr.interpolate(up, 250)[2] == pytest.approx(-1000 + 2000 * 0.5)  # 3-2f: negative to positive
    assert pr.interpolate(pts, 4000) == pytest.approx((300, 100, -1500))  # beyond: hold speed and power (s3.6.6)
    assert pr.interpolate(pts, -500) == pytest.approx((-50, 100, 1000))


def test_the_take_off_roll_is_cut_by_equal_speed_steps_3_3():
    kt = 1 / (K * 0.3048)  # knots per m/s
    roll = pr.takeoff_roll(Point(0, 0, 0, 25_000), Point(1600 / 0.3048, 0, 75 * kt, 20_000))
    # Doc 29's own example (Figure 3-5): 1,600 m to 75 m/s makes 8 segments ending at 25, 100, ... 1,600 m.
    assert [p.distance_ft * 0.3048 for p in roll] == pytest.approx([0, 25, 100, 225, 400, 625, 900, 1225, 1600])
    assert [p.thrust for p in roll] == pytest.approx([25_000 - 625 * k for k in range(9)])  # 3-3e: equal steps
    rolling = pr.takeoff_roll(Point(0, 0, 20 * kt, 25_000), Point(1600 / 0.3048, 0, 75 * kt, 20_000))
    assert len(rolling) == 1 + int(1 + 55 / 10) and rolling[-1].distance_ft == pytest.approx(1600 / 0.3048)


# ------------------------------------------- EASA's tables (made-up files of the same shape)


def _csv(path, header, rows):
    with open(path, 'w', encoding='latin-1', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(header)
        w.writerows(rows)


def _xlsx(path, header, rows):
    openpyxl = pytest.importorskip('openpyxl')
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)


AIRCRAFT_HEAD = [
    'ACFT_ID',
    'Description',
    'Engine Type',
    'Number Of Engines',
    'Max Gross Landing Weight (lb)',
    'Max Sea Level Static Thrust (lb)',
    'NPD_ID',
    'Power Parameter',
]
JET_HEAD = ['ACFT_ID', 'Thrust Rating', 'E', 'F', 'Ga', 'Gb', 'H', 'K1', 'K2', 'K3', 'K4']
AERO_HEAD = ['ACFT_ID', 'Op Type', 'Flap_ID', 'B', 'C', 'D', 'R']
DEP_HEAD = [
    'ACFT_ID',
    'Profile_ID',
    'Stage Length',
    'Step Number',
    'Step Type',
    'Thrust Rating',
    'Flap_ID',
    'End Point Altitude (ft)',
    'Rate Of Climb (ft/min)',
    'End Point CAS (kt)',
    'Accel Percentage (%)',
]
APP_HEAD = [
    'ACFT_ID',
    'Profile_ID',
    'Step Number',
    'Step Type',
    'Flap_ID',
    'Start Altitude(ft)',
    'Start CAS (kt)',
    'Descent Angle (deg)',
    'Touchdown Roll (ft)',
    'Distance (ft)',
    'Start Thrust',
]
FPP_HEAD = [
    'ACFT_ID',
    'Op Type',
    'Profile_ID',
    'Stage Length',
    'Point Number',
    'Distance (ft)',
    'Altitude AFE (ft)',
    'TAS (kt)',
    'Power Setting',
]


def _release(d, fmt, weight, aircraft=('ZZJET',), extra_profile=False, fixed=False):
    d.mkdir()
    write, name = (_csv, 'ANP2.3_{}.csv') if fmt == 'csv' else (_xlsx, 'EASA_ANP_database_{}_v9.xlsx')
    write(
        d / name.format('Aircraft'),
        AIRCRAFT_HEAD,
        [[a, 'made up', 'Jet', 2, 100000, 20000, a, 'CNT (lb)'] for a in aircraft],
    )
    write(
        d / name.format('Jet_engine_coefficients'),
        JET_HEAD,
        [
            [a, r, *c, '', '', '', '']
            for a in aircraft
            for r, c in (
                ('MaxTakeoff', (20000, -20, 0.25, 0, 0)),
                ('MaxClimb', (13000, -5, 0.35, -1e-5, 0)),
                ('IdleApproach', (900, -5, 0.15, -1e-5, 0)),
            )
        ],
    )
    write(
        d / name.format('Aerodynamic_coefficients'),
        AERO_HEAD,
        [
            [a, *row]
            for a in aircraft
            for row in (
                ('D', 'T1', 0.008, 0.45, '', 0.075),
                ('A', 'FULL', '', '', 0.4, 0.12),
                ('A', 0, '', '', '', 0.06),
            )
        ],
    )  # a flap called 0, as some are
    write(
        d / name.format('Default_weights'),
        ['ACFT_ID', 'Stage Length', 'Weight (lb)'],
        [[a, 1, weight] for a in aircraft],
    )
    write(
        d / name.format('Default_departure_procedural_steps'),
        DEP_HEAD,
        [[a, 'DEFAULT', 1, 1, 'Takeoff', 'MaxTakeoff', 'T1', '', '', '', ''] for a in aircraft]
        + [[a, 'DEFAULT', 1, 2, 'Climb', 'MaxTakeoff', 'T1', 1500, '', '', ''] for a in aircraft],
    )
    rows = [
        ['ZZJET', 'DEFAULT', 1, 'Level-Idle', 0, 3000, 220, '', '', 9000, ''],
        ['ZZJET', 'DEFAULT', 2, 'Descend-Idle', 0, 3000, 200, 3, '', '', ''],
        ['ZZJET', 'DEFAULT', 3, 'Descend', 'FULL', 1000, 150, 3, '', '', ''],
        ['ZZJET', 'DEFAULT', 4, 'Land', 'FULL', '', '', '', 500, '', ''],
        ['ZZJET', 'DEFAULT', 5, 'Decelerate', '', '', 130, '', '', 3000, 40],
        ['ZZJET', 'DEFAULT', 6, 'Decelerate', '', '', 30, '', '', 0, 10],
    ]
    if extra_profile:
        rows += [[*r[:1], 'OLD', *r[2:]] for r in rows]
    write(d / name.format('Default_approach_procedural_steps'), APP_HEAD, rows)
    write(
        d / name.format('Default_fixed_point_profiles'),
        FPP_HEAD,
        [
            ['ZZOLD', 'D', 'FIXED', 1, n, dist, h, v, p]
            for n, dist, h, v, p in ((2, 5000, 0, 150, 18000), (1, 0, 0, 0, 20000))
        ]
        if fixed
        else [],
    )


def test_load_anp_reads_both_releases_and_the_later_replaces_an_aircraft_whole(tmp_path):
    _release(tmp_path / 'v23', 'csv', 110_000, aircraft=('ZZJET', 'ZZOLD'), extra_profile=True, fixed=True)
    _release(tmp_path / 'v9', 'xlsx', 130_000)
    old = pr.load_anp(tmp_path / 'v23')
    db = pr.load_anp(tmp_path / 'v23', tmp_path / 'v9')
    assert db.performance['ZZJET'].weights == {'1': 130_000.0} and old.performance['ZZJET'].weights == {'1': 110_000.0}
    assert ('ZZJET', 'OLD') in old.approaches and ('ZZJET', 'OLD') not in db.approaches  # replaced whole
    assert 'ZZOLD' in db.performance  # an aircraft only the earlier release has stays
    pts, how = pr.profile(db, 'ZZJET', 'D', 'DEFAULT', 1)
    assert how == 'steps' and pts[1].distance_ft == pytest.approx(
        0.008 * 130_000**2 / (2 * (20000 - 20 * 0.45 * math.sqrt(130_000)))
    )
    app, _ = pr.profile(db, 'ZZJET', 'A', 'DEFAULT')
    assert app[1].distance_ft - app[0].distance_ft == pytest.approx(9000)  # Level-Idle length from Distance (ft)
    assert db.performance['ZZJET'].flap('A', '0', 'R') == 0.06
    fixed, how = pr.profile(db, 'ZZOLD', 'D', 'FIXED', '1')
    assert how == 'fixed' and [(p.distance_ft, p.thrust) for p in fixed] == [(0, 20000), (5000, 18000)]  # in order
    assert pr.available(db, 'ZZOLD', 'D') == [('fixed', 'FIXED', '1'), ('steps', 'DEFAULT', '1')]
    with pytest.raises(KeyError):
        pr.profile(db, 'ZZJET', 'D', 'ICAO_A', '1')


# ------------------------------------------- every ANP default profile (gitignored tables)


def test_every_anp_procedure_flies_on_three_days():
    """Shapes only: every ANP procedure synthesises, a departure never runs backwards and keeps positive thrust, an
    approach ends on the runway; on the reference day an approach never climbs. No ANP figure is read out."""
    if not ANP_V23.exists():
        pytest.skip(f'{ANP_V23.relative_to(REPO)} is not on this machine (gitignored: EASA ANP v2.3 tables)')
    db = pr.load_anp(ANP_V23, *([ANP_V9] if ANP_V9.exists() else []))
    assert db.departures and db.approaches
    bad = []
    for atm in (REF, Atmosphere(83, 30, 29.80, 0), Atmosphere(83, -5, 30.30, 20)):
        for acft, prof, stage in db.departures:
            pts, _ = pr.profile(db, acft, 'D', prof, stage, atm)
            if (
                any(b.distance_ft < a.distance_ft for a, b in itertools.pairwise(pts))
                or min(p.thrust for p in pts) <= 0
            ):
                bad.append(('D', acft, prof, stage, atm))
            if not all(math.isfinite(x) for p in pts for x in dataclasses.astuple(p)[:4]):
                bad.append(('D not finite', acft, prof, stage, atm))
        for acft, prof in db.approaches:
            pts, _ = pr.profile(db, acft, 'A', prof, '1', atm)
            if any(b.distance_ft < a.distance_ft for a, b in itertools.pairwise(pts)) or (0.0, 0.0) not in [
                (p.distance_ft, p.height_ft) for p in pts
            ]:
                bad.append(('A', acft, prof, atm))
            if atm == REF and any(b.height_ft > a.height_ft + 1e-9 for a, b in itertools.pairwise(pts)):
                bad.append(('A climbs', acft, prof))
    assert bad == [], f'{len(bad)} ANP procedures misbehave, first: {bad[:4]}'
