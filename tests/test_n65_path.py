"""N65 step 5: one flight's 3-D path, as Doc 29 Vol 2 s3.6 builds it (scripts/n65_path.py), 2026-11-03.

Every profile here is MADE UP (heights, speeds and thrusts typed for the test, shaped like a jet's): EASA's tables
never enter this public repo. Doc 29's own worked example of s3.6.4 (a 304.8 m climb end cut at 17.2 m, 37.8 m, ...)
holds the height cuts; the rest is held by hand-worked cases and by invariants (a cut point lies on the segment it
cuts; a departure begins at its start of roll and an approach ends where its profile does). Offline only.
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import n65_doc29 as d29  # noqa: E402
import n65_path as pa  # noqa: E402
import n65_profiles as pr  # noqa: E402

FT = 0.3048
P = pr.Point


def test_stage_lengths_follow_doc29s_trip_bands():
    assert [pa.stage_for_trip(n) for n in (0, 499.9, 500, 999, 1000, 2499, 2500, 8499, 8500, 12000)] == \
        ['1', '1', '2', '2', '3', '4', '5', '10', '11', '11']
    with pytest.raises(ValueError):
        pa.stage_for_trip(-1)


def test_an_unknown_trip_is_bracketed_by_the_lightest_and_heaviest_stage_never_one_picked():
    weights = {'1': 150000.0, '2': 160000.0, '3': 172000.0, 'M': 190000.0}
    assert pa.stages_for({'1', '2', '3', 'M'}, weights, None) == [('light', '1'), ('heavy', 'M')]
    # Without weights the order is by number, 'M' heaviest.
    assert pa.stages_for({'2', '1', 'M'}, {}, None) == [('light', '1'), ('heavy', 'M')]
    assert pa.stages_for({'1'}, weights, None) == [('light', '1'), ('heavy', '1')]
    assert pa.stages_for(set(), weights, None) == []


def test_a_known_trip_takes_its_band_and_a_trip_past_the_aircrafts_range_its_heaviest():
    weights = {'1': 150000.0, '2': 160000.0, '3': 172000.0, 'M': 190000.0}
    assert pa.stages_for({'1', '2', '3', 'M'}, weights, 720) == [('trip', '2')]
    assert pa.stages_for({'1', '2', '3', 'M'}, weights, 4000) == [('beyond-range', 'M')]
    assert pa.stages_for({'1', '2', '3'}, weights, 4000) == [('beyond-range', '3')]
    # A band missing inside the range: the next heavier offered (said by its label).
    assert pa.stages_for({'1', '3'}, weights, 720) == [('next-heavier', '3')]


def test_the_procedure_is_default_then_icao_b_then_icao_a_steps_before_fixed():
    assert pa.procedure_for([('steps', 'ICAO_A', '1'), ('steps', 'DEFAULT', '1'), ('steps', 'ICAO_B', '1')], 'D') == \
        ('steps', 'DEFAULT')
    assert pa.procedure_for([('steps', 'ICAO_A', '1'), ('steps', 'ICAO_B', '1')], 'D') == ('steps', 'ICAO_B')
    assert pa.procedure_for([('steps', 'ICAO_A', '1')], 'D') == ('steps', 'ICAO_A')
    assert pa.procedure_for([('fixed', 'DEFAULT', '1'), ('steps', 'ICAO_B', '1')], 'D') == ('steps', 'ICAO_B')
    assert pa.procedure_for([('fixed', 'DEFAULT', '1')], 'D') == ('fixed', 'DEFAULT')
    assert pa.procedure_for([('steps', 'DEFAULT2', '1'), ('steps', 'DEFAULT1', '1')], 'A') == ('steps', 'DEFAULT1')
    # Only procedures the rule does not name: not computed, never a pick among them.
    assert pa.procedure_for([('steps', 'DEFAULT2', '1'), ('steps', 'VISUAL', '1')], 'A') is None
    assert pa.procedure_for([('steps', 'HI_ALT', '1')], 'D') is None


def test_the_headwind_is_the_winds_component_into_the_face():
    assert pa.headwind_kt(270, 10, 270) == pytest.approx(10)
    assert pa.headwind_kt(90, 10, 270) == pytest.approx(-10)
    assert pa.headwind_kt(0, 10, 270) == pytest.approx(0, abs=1e-12)
    assert pa.headwind_kt(50, 9, 89.68) == pytest.approx(9 * math.cos(math.radians(39.68)))


def test_the_aerodrome_pressure_falls_from_qnh_with_height():
    assert pa.pressure_kpa(1013.25, 0) == pytest.approx(101.325)
    assert pa.pressure_kpa(1013.25, 1000) == pytest.approx(89.87, abs=0.01)  # the standard atmosphere at 1 km


def test_the_touchdown_lies_where_a_50_ft_threshold_crossing_meets_the_ground():
    # ANP's approaches cross the threshold at 50 ft on a 3 degree glide, 954 ft before touchdown.
    assert pa.touchdown_offset_m(3.0) / FT == pytest.approx(954.0, abs=0.5)


def test_initial_climb_cuts_reproduce_doc29s_worked_example():
    # s3.6.4: "If the original segment endpoint height is ze = 304.8 m ... z1 would be 17.2 m and z2 would be 37.8 m".
    cuts = pa.sub_heights_m(0.0, 304.8)
    assert [round(z, 1) for z in cuts[:2]] == [17.2, 37.8]
    assert len(cuts) == 6  # z'1..z'7 scaled, the 7th being the end point itself
    assert cuts[-1] == pytest.approx(304.8 * 214.9 / 334.9)


def test_cuts_above_1289_m_keep_the_set_and_a_segment_starting_high_starts_at_k():
    assert pa.sub_heights_m(0.0, 2000.0) == pytest.approx(list(pa.SUB_HEIGHTS_M))
    assert pa.sub_heights_m(300.0, 900.0) == pytest.approx([z * 900 / 609.6 for z in pa.SUB_HEIGHTS_M[:8]
                                                            if 300 < z * 900 / 609.6 < 900])
    assert pa.sub_heights_m(1300.0, 2000.0) == []
    assert pa.sub_heights_m(500.0, 500.0) == []


# A made-up jet departure: roll (0 -> 5,000 ft at 150 kt), climb to 1,000 ft, an acceleration to 210 kt, a climb.
DEPARTURE = [P(0, 0, 0, 20000), P(5000, 0, 150, 18000), P(12000, 1000, 152, 18500),
             P(18000, 1300, 210, 17000), P(30000, 3000, 215, 16000)]
# A made-up approach: level at 3,000 ft, a 3 degree descent, touchdown and a roll with reverse thrust.
APPROACH = [P(-90000, 3000, 210, 1500), P(-57000, 3000, 180, 2500), P(-954, 50, 140, 4500),
            P(0, 0, 140, 4500), P(450, 0, 138, 9000), P(4500, 0, 30, 2000)]


def _on_segment(p, a, b):
    f = (p.distance_ft - a.distance_ft) / (b.distance_ft - a.distance_ft)
    return 0 < f < 1 and p.height_ft == pytest.approx(a.height_ft + f * (b.height_ft - a.height_ft))


def test_a_departure_is_cut_on_the_roll_the_initial_climb_and_where_its_speed_changes():
    out, lift = pa.subsegment(DEPARTURE, 'D')
    assert lift == 5000
    roll = [p for p in out if p.distance_ft <= 5000]
    assert len(roll) == 1 + int(1 + 150 * pa.KT_MS / 10)  # s3.6.2: int(1 + V/10 m/s) segments
    # s3.6.4 on the initial climb (0 to 1,000 ft): the scaled set strictly between, every one on the segment.
    climb = [p for p in out if 5000 < p.distance_ft < 12000]
    assert [p.height_ft * FT for p in climb] == pytest.approx(pa.sub_heights_m(0.0, 1000 * FT))
    assert all(_on_segment(p, DEPARTURE[1], DEPARTURE[2]) for p in climb)
    # The acceleration 152 -> 210 kt (> 20 kt): s3.6.4 cuts it by height first, then s3.6.5 by speed.
    accel = [p for p in out if 12000 < p.distance_ft < 18000]
    assert all(_on_segment(p, DEPARTURE[2], DEPARTURE[3]) for p in accel)
    speeds = [DEPARTURE[2].tas_kt, *(p.tas_kt for p in accel), DEPARTURE[3].tas_kt]
    assert all(abs(b - a) <= pa.SPEED_SPLIT_KT for a, b in zip(speeds, speeds[1:], strict=False))
    assert [p.distance_ft for p in out] == sorted(p.distance_ft for p in out)


def test_the_speed_cut_is_constant_acceleration_with_equal_speed_and_power_steps():
    a, b = P(0, 1000, 150, 18000), P(10000, 1500, 210, 16000)
    cut = pa._split_by_speed(a, b)
    n = int(1 + abs(210 - 150) * pa.KT_MS / 10)
    assert len(cut) == n - 1
    v = [a.tas_kt, *(p.tas_kt for p in cut), b.tas_kt]
    assert [v2 - v1 for v1, v2 in zip(v, v[1:], strict=False)] == pytest.approx([(210 - 150) / n] * n)
    thrust = [a.thrust, *(p.thrust for p in cut), b.thrust]
    assert [t2 - t1 for t1, t2 in zip(thrust, thrust[1:], strict=False)] == pytest.approx([-2000 / n] * n)
    # 3-3i: at constant acceleration each part's length is its mean speed times the equal time step.
    s = [a.distance_ft, *(p.distance_ft for p in cut), b.distance_ft]
    lengths = [s2 - s1 for s1, s2 in zip(s, s[1:], strict=False)]
    means = [(v1 + v2) / 2 for v1, v2 in zip(v, v[1:], strict=False)]
    assert [ln / m for ln, m in zip(lengths, means, strict=True)] == pytest.approx([lengths[0] / means[0]] * n)
    assert all(_on_segment(p, a, b) for p in cut)
    assert pa._split_by_speed(a, P(10000, 1500, 170, 16000)) == []  # 20 kt or less: not cut
    assert len(pa._split_by_speed(a, P(10000, 1500, 175, 16000))) == 1  # 25 kt: cut in int(1 + 12.9 / 10) = 2
    assert pa._split_by_speed(P(0, 0, 150, 9000), P(4000, 0, 30, 2000)) == []  # the landing roll: not here


def test_an_approach_is_cut_on_its_final_descent_in_flight_order():
    out, lift = pa.subsegment(APPROACH, 'A')
    assert lift is None
    final = [p for p in out if -57000 < p.distance_ft < -954]
    heights = [p.height_ft * FT for p in final]
    assert heights == sorted(heights, reverse=True)
    assert sorted(heights) == pytest.approx(pa.sub_heights_m(50 * FT, 3000 * FT))
    assert out[-1] == APPROACH[-1] and out[-3:] == APPROACH[-3:]  # the landing roll keeps its own points


STRAIGHT_EAST = [(-20000.0, -20000.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), (40000.0, 40000.0, 0.0, 0.0)]


def test_a_departure_path_starts_at_the_roll_flies_the_track_and_flags_only_the_roll():
    sub, lift = pa.subsegment(DEPARTURE, 'D')
    track = [(0.0, 0.0, 0.0, 0.0), (500.0, 500.0, 0.0, 0.0), (1000.0, 1000.0, 0.0, 0.0),
             (6000.0, 6000.0, 0.0, 5.0), (12000.0, 12000.0, 0.0, 0.0)]
    path = pa.merge(sub, track, 'D', lift)
    assert path[0][:3] == (0.0, 0.0, 1.0)  # s3.5: the source 1 m above the aerodrome
    roll = [n for n in path if n[5]]
    assert [n[7] for n in roll] == pytest.approx([p.distance_ft * FT for p in sub if p.distance_ft < lift])
    assert 500.0 not in [round(n[7], 3) for n in path]  # a track node inside the roll would start a roll segment
    assert all(n[2] == pa.SOURCE_MIN_M and n[4] == 0.0 for n in path if n[7] <= lift * FT)
    assert all(n[1] == 0.0 and n[0] == pytest.approx(n[7]) for n in path)  # x along the track, y on it
    at_6000 = next(n for n in path if n[7] == 6000.0)
    z_ft, _v, _p = pr.interpolate(sub, 6000.0 / FT)
    assert at_6000[2] == pytest.approx(z_ft * FT) and at_6000[4] == pytest.approx(5.0)
    # Past the profile's end (30,000 ft = 9,144 m) it climbs on at the end gradient, speed and power held (s3.6.6).
    end = path[-1]
    assert end[7] == 12000.0 and end[3] == 16000 and end[6] == 215
    grad = (3000 - 1300) / (30000 - 18000)
    assert end[2] == pytest.approx((3000 + grad * (12000 / FT - 30000)) * FT)


def test_an_approach_path_ends_where_its_profile_does_and_reaches_back_along_its_first_gradient():
    sub, _ = pa.subsegment(APPROACH, 'A')
    track = [(-40000.0, -40000.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), (3000.0, 3000.0, 0.0, 0.0)]
    path = pa.merge(sub, track, 'A')
    assert path[-1][7] == pytest.approx(4500 * FT)  # the roll's last point, not the track's 3,000 m
    assert not any(n[5] for n in path)
    assert path[0][7] == -40000.0 and path[0][2] == pytest.approx(3000 * FT)  # level before -90,000 ft
    assert all(n[4] == 0.0 for n in path if n[7] >= 0)


def test_a_path_needs_its_lift_off_and_an_overlap():
    sub, lift = pa.subsegment(DEPARTURE, 'D')
    with pytest.raises(ValueError):
        pa.merge(sub, STRAIGHT_EAST, 'D')
    with pytest.raises(ValueError):
        pa.merge(sub, [(-9000.0, 0.0, 0.0, 0.0), (-10.0, 0.0, 0.0, 0.0)], 'D', lift)


def test_close_points_with_the_same_speed_and_power_are_one():
    a = (0.0, 0.0, 100.0, 9000.0, 0.0, False, 180.0, 0.0)
    b = (5.0, 0.0, 100.0, 9000.0, 0.0, False, 180.0, 5.0)
    c = (5.0, 0.0, 100.0, 9500.0, 0.0, False, 180.0, 5.0)
    d = (400.0, 0.0, 120.0, 9000.0, 0.0, False, 180.0, 400.0)
    e = (405.0, 0.0, 120.0, 9000.0, 0.0, False, 180.0, 405.0)
    assert pa.drop_close([a, b, d]) == [a, d]
    assert pa.drop_close([a, c, d]) == [a, c, d]  # a different power is a different point
    assert pa.drop_close([a, d, e]) == [a, d, e]  # the path keeps its end


def test_the_height_cuts_leave_lamax_alongside_the_climb_unchanged():
    # For an observer ALONGSIDE a straight segment LAmax comes from its nearest point, with the power there by 4-12,
    # the same as 3-2d at the cut points: cutting a straight climb must not change it (only behind or ahead of the
    # pieces, where the end points' angles are used, can s3.6.4 move LAmax).
    curves = d29.npd_curves([(10000, {200: 95.0, 1000: 82.0, 4000: 68.0, 16000: 50.0}),
                             (20000, {200: 99.0, 1000: 86.0, 4000: 72.0, 16000: 54.0})])
    a, b = P(5000, 200, 150, 18000), P(12000, 1000, 152, 18500)  # above the 1 m source floor: a straight line
    track = [(0.0, 0.0, 0.0, 0.0), (5000.0, 5000.0, 0.0, 0.0)]
    whole = pa.merge([P(0, 0, 0, 20000), P(4000, 0, 140, 19000), a, b], track, 'D', 4000)
    cut = pa.merge([P(0, 0, 0, 20000), P(4000, 0, 140, 19000), a, *pa._split_by_height(a, b, 'D'), b], track, 'D',
                   4000)
    assert len(cut) > len(whole)
    for y in (300.0, 900.0, 2500.0):
        obs = (2900.0, y, 0.0)
        assert d29.event_lmax(cut, obs, curves, 'wing') == pytest.approx(d29.event_lmax(whole, obs, curves, 'wing'),
                                                                         abs=1e-9)
