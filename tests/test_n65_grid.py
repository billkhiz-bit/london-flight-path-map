"""scripts/n65_grid.py equals scripts/n65_doc29.py, observer by observer, on every branch (2026-11-03).

n65_doc29 is held to ECAC Doc 29 Volume 3's own 3,516 worked rows (tests/test_n65_doc29.py); n65_grid is the same
arithmetic over arrays, so it is held to n65_doc29 here rather than to ECAC again: every branch the scalar takes is
reached ON PURPOSE (a constructed observer for each), plus a seeded random cloud, on made-up noise tables (EASA's stay
out of the repo). Any difference over 1e-9 dB is a defect in the arrays, never "rounding".
"""
import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import n65_doc29 as d29  # noqa: E402
import n65_grid as grid  # noqa: E402

TOL = 1e-9
# Made-up noise tables (power, {distance_ft: level}), shaped like EASA's: louder with power, quieter with distance.
MULTI = d29.npd_curves([
    (4000, {200: 92.0, 400: 86.1, 630: 82.0, 1000: 77.9, 2000: 71.2, 4000: 64.0, 6300: 59.1, 10000: 53.8, 16000: 47.9, 25000: 41.0}),
    (8000, {200: 96.5, 400: 90.9, 630: 87.0, 1000: 83.1, 2000: 76.8, 4000: 69.9, 6300: 65.2, 10000: 60.1, 16000: 54.5, 25000: 47.8}),
    (14000, {200: 100.1, 400: 94.8, 630: 91.2, 1000: 87.6, 2000: 81.5, 4000: 74.9, 6300: 70.4, 10000: 65.6, 16000: 60.3, 25000: 53.9}),
])
SINGLE = d29.npd_curves([(5000, {200: 90.0, 1000: 76.0, 6300: 58.0, 25000: 40.0})])


def scalar(s1, s2, p1, p2, obs, curves, mount, bank, imp, roll):
    return np.array([d29.segment_lmax(s1, s2, p1, p2, tuple(o), curves, mount, bank, imp, roll) for o in obs])


def assert_equal(s1, s2, p1, p2, obs, curves=MULTI, mount='wing', bank=0.0, imp=0.0, roll=False):
    obs = np.asarray(obs, float)
    want = scalar(s1, s2, p1, p2, obs, curves, mount, bank, imp, roll)
    got = grid.segment_lmax(s1, s2, p1, p2, obs, curves, mount, bank, imp, roll)
    worst = float(np.max(np.abs(got - want)))
    assert worst <= TOL, f'arrays differ from n65_doc29 by {worst} dB (mount {mount}, bank {bank}, roll {roll})'


# A climbing departure segment and a descending approach segment, metres.
CLIMB = ((0.0, 0.0, 0.0), (3000.0, 400.0, 300.0))
DESCENT = ((-8000.0, 0.0, 420.0), (-3000.0, 0.0, 160.0))


def test_behind_alongside_ahead_and_to_each_side():
    obs = [(-500, 50, 0), (-500, -50, 0), (1500, 700, 0), (1500, -700, 0), (4500, 900, 0), (4500, -900, 0), (1500, 200, 0)]
    for (s1, s2) in (CLIMB, DESCENT):
        g = grid.geometry(s1, s2, np.asarray(obs, float))
        assert set(g['where'].tolist()) >= {-1, 0, 1} or s1 == DESCENT[0], g['where']
        assert_equal(s1, s2, 9000.0, 12000.0, obs)


def test_observer_on_the_paths_own_line_and_a_vertical_segment():
    # On the line behind a take-off roll (dp under 1 cm), and a segment straight up (no ground track).
    roll = ((0.0, 0.0, 0.0), (1200.0, 0.0, 0.0))
    assert_equal(*roll, 14000.0, 14000.0, [(-800.0, 0.0, 0.0), (-800.0, 0.004, 0.0), (-2500.0, 0.0, 0.0)], roll=True)
    # ALONGSIDE and within 1 cm of the line, just under the source (it sits 1 m up): the only place the on-the-line
    # rule changes anything (behind or ahead, the end point's angle is used instead). Without the rule beta_p is 90.
    raised = ((0.0, 0.0, 1.0), (1200.0, 0.0, 1.0))
    assert_equal(*raised, 14000.0, 14000.0, [(600.0, 0.0, 0.995), (600.0, 0.003, 0.996), (900.0, 0.0, 0.0)], roll=True)
    assert_equal((0.0, 0.0, 100.0), (0.0, 0.0, 600.0), 12000.0, 11000.0, [(300.0, 0.0, 0.0), (0.0, 400.0, 0.0), (-50.0, -50.0, 0.0)])


def test_observer_above_the_aircraft_reads_beta_below_zero():
    # Terrain: an observer higher than the segment (s4.5.4, Lambda = 10.857).
    assert_equal(*DESCENT, 5000.0, 4500.0, [(-5000.0, 300.0, 500.0), (-2000.0, 100.0, 300.0)])


def test_takeoff_roll_start_of_roll_both_engines_and_past_762_m():
    roll = ((0.0, 0.0, 1.0), (1500.0, 0.0, 1.0))
    obs = [(-100, 30, 0), (-400, 300, 0), (-900, 50, 0), (-3000, 1000, 0), (200, 600, 0), (-1, 900, 0)]
    for mount in ('wing', 'fuselage', 'prop'):
        assert_equal(*roll, 14000.0, 14000.0, obs, mount=mount, roll=True)


def test_banked_turns_both_ways_and_every_mount():
    obs = [(1500, 600, 0), (1500, -600, 0), (1500, 50, 0)]
    for mount in ('wing', 'fuselage', 'prop'):
        for bank in (-25.0, 0.0, 18.0):
            assert_equal(*CLIMB, 10000.0, 9000.0, obs, mount=mount, bank=bank, imp=d29.impedance_adjustment(22.0, 100.9))


def test_single_power_table_and_extrapolation_past_every_edge():
    obs = [(1500, 5, 0), (1500, 30000, 0), (1500, 3, 299)]  # nearer than 30 m, farther than the table, at 1 m
    assert_equal(*CLIMB, 500.0, 30000.0, obs, curves=MULTI)  # powers below and above the tabulated ones
    assert_equal(*CLIMB, -200.0, 9000.0, obs, curves=MULTI)  # a negative power resets to one pound
    assert_equal(*CLIMB, 9000.0, 9000.0, obs, curves=SINGLE)


def test_exactly_square_to_the_start_is_alongside_not_behind():
    # q == 0 EXACTLY: a climb with no sideways part (u_y is exactly 0) and an observer straight to the side of its
    # start, so q = 0*u_x + y*0 + 0*u_z with no rounding (dividing by the length rounds anything less contrived:
    # (400, -3000, 0) against (3000, 400, 300) came out -5.7e-14). n65_doc29 calls q == 0 alongside (q < 0 is behind),
    # which changes the angle and the lateral distance used on a climbing segment.
    climb = ((0.0, 0.0, 0.0), (3000.0, 0.0, 300.0))
    g = grid.geometry(*climb, np.array([(0.0, 500.0, 0.0)]))
    assert g['q'][0] == 0.0 and g['where'][0] == 0
    assert_equal(*climb, 9000.0, 12000.0, [(0.0, 500.0, 0.0), (0.0, -1200.0, 0.0)])


def test_nearer_than_30_m_reads_at_30_m():
    # Vol 2 s4.2's lower limit: an observer a few metres from the segment's start.
    g = grid.geometry(*CLIMB, np.array([(10.0, 5.0, 0.0)]))
    assert g['ds'][0] < d29.NPD_MIN_DISTANCE_M
    assert_equal(*CLIMB, 12000.0, 12000.0, [(10.0, 5.0, 0.0), (20.0, -8.0, 1.0)])


def test_a_seeded_random_cloud():
    rng = random.Random(20261103)  # noqa: S311 (a seeded test cloud, not security)
    for _ in range(40):
        s1 = (rng.uniform(-6000, 6000), rng.uniform(-3000, 3000), rng.uniform(0, 900))
        s2 = (s1[0] + rng.uniform(-4000, 4000), s1[1] + rng.uniform(-2000, 2000), max(0.0, s1[2] + rng.uniform(-300, 300)))
        if s1 == s2:
            continue
        obs = [(rng.uniform(-9000, 9000), rng.uniform(-6000, 6000), rng.uniform(0, 60)) for _ in range(60)]
        assert_equal(s1, s2, rng.uniform(1500, 15000), rng.uniform(1500, 15000), obs,
                     mount=rng.choice(['wing', 'fuselage', 'prop']), bank=rng.uniform(-30, 30),
                     roll=rng.random() < 0.15)


def test_event_lmax_is_the_loudest_segment_and_skips_repeated_points():
    path = [(0, 0, 0, 14000, 0, True), (1200, 0, 0, 14000, 0, True), (1200, 0, 0, 14000, 0, False),
            (3000, 200, 150, 12000, 0, False), (8000, 900, 900, 10000, 12, False), (14000, 3000, 1500, 9000, 0, False)]
    obs = np.array([(-600, 40, 0), (2000, 400, 0), (6000, -800, 0), (12000, 2600, 0), (20000, 9000, 0)], float)
    want = np.array([d29.event_lmax(path, tuple(o), MULTI, 'wing', 0.07) for o in obs])
    got = grid.event_lmax(path, obs, MULTI, 'wing', 0.07)
    assert np.max(np.abs(got - want)) <= TOL


def test_count_reaching_the_threshold_includes_exactly_65():
    levels = np.array([[64.999, 65.0, 70.0], [65.0, 64.0, 66.0], [80.0, 10.0, -math.inf]])
    assert grid.count_at_least(levels).tolist() == [2, 1, 2]


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
