"""N65 step 5: the ground track one flight flew, from its ADS-B points (scripts/n65_tracks.py), 2026-11-03.

Every trace here is MADE UP on a flat grid: a runway pair shaped like Heathrow's (two parallel east-west runways 1.4 km
apart, the easterly ends' landing thresholds displaced 300 m into the runway), aircraft lining up, rolling, climbing,
turning and landing at speeds typed for the test. Offline only.
"""
import dataclasses
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import n65_path as pa  # noqa: E402
import n65_tracks as tr  # noqa: E402

FT = 0.3048
KT = 0.514444  # m/s
# 09R/27L along y = 0 from x = 0 to 3,600 m; 09L/27R along y = 1,400. The 09s' thresholds displaced 300 m east.
RUNWAYS = {
    '09R': tr.Runway('09R', (300.0, 0.0), (1.0, 0.0), 3300.0, 90.0, 3.0),
    '27L': tr.Runway('27L', (3600.0, 0.0), (-1.0, 0.0), 3300.0, 270.0, 3.0),
    '09L': tr.Runway('09L', (300.0, 1400.0), (1.0, 0.0), 3300.0, 90.0, 3.0),
    '27R': tr.Runway('27R', (3600.0, 1400.0), (-1.0, 0.0), 3300.0, 270.0, 3.0),
}


def pt(t, x, y, ground=False, gs=150.0, h=None):
    return tr.Pt(float(t), float(x), float(y), ground, gs, h)


def test_a_runways_other_end():
    assert [tr.reciprocal(d) for d in ('09L', '27R', '09R', '15', '33', '36', '18', '04C')] == \
        ['27R', '09L', '27L', '33', '15', '18', '36', '22C']


def test_along_and_across_a_runway():
    rw = RUNWAYS['27L']
    assert rw.along_across(2600.0, 0.0) == (1000.0, 0.0)
    assert rw.along_across(2600.0, -50.0)[1] == pytest.approx(50.0)  # south of a westward runway is its left
    assert rw.point(1000.0) == (2600.0, 0.0)


def test_the_runway_is_the_centreline_run_along_in_its_direction():
    east_on_south = [pt(t, 200 + 70 * t, 5.0) for t in range(10)]
    assert tr.runway_from_points(east_on_south, RUNWAYS, 0, 10) == '09R'
    west_on_north = [pt(t, 3500 - 70 * t, 1390.0) for t in range(10)]
    assert tr.runway_from_points(west_on_north, RUNWAYS, 0, 10) == '27R'
    assert tr.runway_from_points(east_on_south[:2], RUNWAYS, 0, 10) is None  # two points are not a run
    assert tr.runway_from_points([pt(t, 70 * t, 700.0) for t in range(10)], RUNWAYS, 0, 10) is None  # between them


# A take-off from 09R: taxi in from the south, hold at x = 20 (the runway's start, 280 m behind its displaced landing
# threshold), roll at 2 m/s2 (x = 20 + t^2), lift off at t = 45, climb east at 175 kt and 3 m/s.
TAKEOFF_T = 45.0


def _departure(turn_back=False):
    pts = [pt(-200, 20, -150, True, 10), pt(-100, 15, 0, True, 12), pt(-40, 20, 2.0, True, 3)]
    pts += [pt(t, 20 + t * t, -1.0, t < TAKEOFF_T, 2 * t / KT) for t in range(5, 50, 5)]
    pts += [pt(50 + k, 2045 + 90 * k, 0.0, False, 175, 3.0 * k) for k in range(0, 60, 4)]
    if turn_back:  # a right turn of radius 3 km onto a track back west, south of the airport
        cx, cy, r = 7445.0, -3000.0, 3000.0
        for k in range(1, 40):
            a = math.pi / 2 - k * math.pi / 40
            pts.append(pt(110 + 2.5 * k, cx + r * math.cos(a), cy + r * math.sin(a), False, 175))
        pts += [pt(210 + 4 * k, 7445 - 360 * k, -6000.0, False, 175) for k in range(1, 30)]
    return pts


def test_the_roll_starts_at_the_last_slow_point_of_the_run_that_takes_off():
    assert tr.start_of_roll(_departure(), RUNWAYS['09R'], TAKEOFF_T) == (-280.0, -40.0, 'roll-seen')


def test_a_rolling_start_starts_where_it_joined_and_an_unheard_start_is_the_threshold_said():
    rolling = [pt(-300, 20, -150, True, 8)] + [pt(t, 400 + 30 * t, 0.0, True, 25 + 2 * t) for t in range(0, 40, 5)]
    assert tr.start_of_roll(rolling, RUNWAYS['09R'], 40.0) == (100.0, 0.0, 'roll-entered')
    unheard = [pt(t, 1500 + 70 * t, 0.0, True, 100 + t) for t in range(0, 20, 5)]
    assert tr.start_of_roll(unheard, RUNWAYS['09R'], 20.0) == (0.0, None, 'roll-at-threshold')
    # Bill's 3 Nov ruling: where the runway's take-off run starts behind a displaced landing threshold (Heathrow 09R,
    # ~308 m), an unheard start is the TORA start, said, never the threshold.
    displaced = dataclasses.replace(RUNWAYS['09R'], tora_start_m=-308.0)
    assert tr.start_of_roll(unheard, displaced, 20.0) == (-308.0, None, 'roll-at-tora-start')
    assert tr.start_of_roll([], displaced, 20.0) == (-308.0, None, 'roll-at-tora-start')
    # A stop on the runway BEFORE a backtrack is not this take-off's start: the run is cut where it goes backwards.
    backtrack = [pt(-300, 3000, 0.0, True, 5), *(pt(-280 + 20 * k, 3000 - 140 * k, 0.0, True, 18) for k in range(1, 11)),
                 pt(-60, 200, 0.0, True, 10), *(pt(t, 200 + t * t, 0.0, True, 2 * t / KT) for t in range(5, 45, 5))]
    assert tr.start_of_roll(backtrack, RUNWAYS['09R'], 40.0)[:2] == (-100.0, -60.0)
    # A backtrack at 25 kt, then a rolling start at its end with no point under 15 kt: the start is where it turned
    # round (the run cut at the backtrack), never where the backtrack began.
    rolling_back = [*(pt(-280 + 20 * k, 3000 - 300 * k, 0.0, True, 25) for k in range(1, 11)),
                    *(pt(t, 10 + 2 * t * t, 0.0, True, 20 + 3 * t) for t in range(5, 45, 5))]
    assert tr.start_of_roll(rolling_back, RUNWAYS['09R'], 40.0) == (-300.0, -80.0, 'roll-entered')


def test_a_departure_track_runs_from_the_start_of_roll_along_the_centreline_then_the_flight():
    track, how = tr.departure_track(_departure(), RUNWAYS['09R'], TAKEOFF_T, spacing=200.0)
    assert how == 'roll-seen'
    s0, x0, y0, _gs, _h = track[0]
    assert (s0, x0, y0) == (0.0, 20.0, 0.0)
    assert all(n[2] == 0.0 for n in track if n[0] <= 2000.0)  # the roll on the centreline (the -1 m snapped)
    assert [n[0] for n in track] == sorted(n[0] for n in track)
    assert all(b[0] - a[0] <= 200.0 + 1e-9 for a, b in zip(track, track[1:], strict=False))
    assert track[-1][1] == pytest.approx(2045 + 90 * 56)


def test_a_departure_that_turns_back_keeps_the_points_behind_its_start_of_roll():
    track, _ = tr.departure_track(_departure(turn_back=True), RUNWAYS['09R'], TAKEOFF_T)
    assert min(n[1] for n in track) < 0  # flown back west past x = 20 (south of the airport)
    assert track[-1][2] == pytest.approx(-6000.0)


def test_a_departure_heard_too_little_is_not_a_track():
    few = [pt(-40, 20, 0, True, 3), pt(10, 120, 0, True, 40), pt(48, 2100, 0, False, 170)]
    track, why = tr.departure_track(few, RUNWAYS['09R'], 45.0)
    assert track is None and why.startswith('no-track')


# A landing on 27L (threshold x = 3,600, landing west). It flies a downwind leg EAST along y = 4,000 from x = -2,000,
# so its first 5.6 km lie PAST the threshold in the landing direction (a test that they are kept), turns right through
# 180 degrees round (20,000, 2,000), comes in along the centreline, crosses the threshold at t = 2 and rolls.
def _approach():
    pts = [pt(-482 + 10 * k, -2000 + 1100 * k, 4000.0, False, 214, 900.0) for k in range(21)]
    for k in range(1, 20):
        a = math.pi / 2 - k * math.pi / 20
        pts.append(pt(-282 + 3.15 * k, 20000 + 2000 * math.cos(a), 2000 + 2000 * math.sin(a), False, 194))
    pts += [pt(-219 + 10.95 * k, 20000 - 820 * k, 0.0, False, 146) for k in range(1, 20)]
    pts += [pt(2 * k, 3600 - 140 * k, 0.0, k > 3, 140 - 8 * k) for k in range(1, 16)]
    return pts


def test_an_approach_track_measures_to_the_touchdown_past_the_threshold():
    rw = RUNWAYS['27L']
    track, how = tr.approach_track(_approach(), rw, -20.0, roll_m=1500.0)
    assert how == 'threshold-seen'
    td = pa.touchdown_offset_m(3.0)
    by_s = {round(n[0], 6): n for n in track}
    assert by_s[0.0][1:3] == pytest.approx((3600.0 - td, 0.0))  # the touchdown point, on the centreline
    assert by_s[round(-td, 6)][1:3] == pytest.approx((3600.0, 0.0))  # the threshold
    assert track[-1][0] == pytest.approx(1500.0)
    assert [n[0] for n in track] == sorted(n[0] for n in track)
    assert min(n[0] for n in track) < -20000  # the downwind leg and the turn are in it, before the threshold
    assert max(n[2] for n in track) == pytest.approx(4000.0, abs=1.0)
    assert min(n[1] for n in track) == pytest.approx(-2000.0)  # the downwind leg from its start, past the threshold


def test_an_approach_whose_threshold_crossing_was_not_heard_is_not_a_track():
    far = [p for p in _approach() if p.x > 4500]
    track, why = tr.approach_track(far, RUNWAYS['27L'], -20.0)
    assert track is None and 'threshold' in why


def _circle(r, gs, left, n=120, spacing=200.0):
    out = []
    for k in range(n):
        a = k * spacing / r
        x, y = r * (1 - math.cos(a)), r * math.sin(a)  # heading north at the origin, turning RIGHT (east)
        out.append((k * spacing, -x if left else x, y, gs, None))
    return out


def test_bank_follows_b14_positive_for_left_turns():
    r, gs = 3000.0, 200.0
    want = math.degrees(math.atan(2.85 * gs * gs / (r / FT * 32.174)))
    for left in (False, True):
        track, capped = tr.bank_angles(_circle(r, gs, left))
        inner = [b for s, _x, _y, b in track[3:-3]]
        assert capped == 0
        assert inner == pytest.approx([want if left else -want] * len(inner), rel=0.01)
    straight, _ = tr.bank_angles([(k * 200.0, 0.0, k * 200.0, 200.0, None) for k in range(20)])
    assert all(b == 0.0 for *_rest, b in straight)


def test_bank_is_capped_and_counted_and_zero_without_a_speed():
    track, capped = tr.bank_angles(_circle(400.0, 250.0, left=True, n=40, spacing=50.0))
    assert capped > 0 and max(b for *_rest, b in track) == tr.BANK_LIMIT_DEG
    no_speed, _ = tr.bank_angles(_circle(3000.0, None, left=True))
    assert all(b == 0.0 for *_rest, b in no_speed)


def test_a_track_runs_straight_on_beyond_its_ends():
    track = [(0.0, 0.0, 0.0, 0.0), (300.0, 300.0, 0.0, 4.0), (700.0, 300.0, 400.0, 0.0)]
    out = tr.extend(track, 1000.0, 2000.0)
    assert out[0] == (-1000.0, -1000.0, 0.0, 0.0)
    assert out[-1] == (2700.0, 300.0, 2400.0, 0.0)
    assert out[1:-1] == track
