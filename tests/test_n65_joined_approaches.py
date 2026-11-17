"""Rule 8 of N65's frozen method (Bill, 2026-11-17): approaches whose threshold crossing was not heard.

On Heathrow's 2025 days (one a month) the receivers missed the runway on 16-98% of arrivals; each was last heard on the
glide path, a median 74-568 m out at 65-140 ft. n65_tracks.joined_end() joins one straight to the threshold when its
LAST airborne point heard was on the extended centreline (within ON_RUNWAY_M), at most JOIN_MAX_M out and under
JOIN_MAX_FT above the field, the same join approach_track() makes from a crossing heard; anything else stays no track,
its kind said (JOIN_REFUSED). tally() keeps the joined inside the arrivals and apart; rule_scales() gives rule 1's
scale without them; cut_approach() is the rule's check (a heard approach cut, so the rule must join it). Every trace is
MADE UP on the flat runway pair tests/test_n65_tracks.py uses. Offline only.
"""
import dataclasses
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import n65_day as nd  # noqa: E402
import n65_path as pa  # noqa: E402
import n65_tracks as tr  # noqa: E402

FT = 0.3048
# 27L lands west along y = 0 onto its threshold at x = 3,600 (as tests/test_n65_tracks.py); its far end is x = 300.
RW = tr.Runway('27L', (3600.0, 0.0), (-1.0, 0.0), 3300.0, 270.0, 3.0)
GLIDE = math.tan(math.radians(3.0))
TCH_M = 50 * FT  # the glide path crosses the threshold at 50 ft
ON_GLIDE = object()
T_LANDING = 0.0
LAST_KT = 131.0  # the speed of the last point heard, and only of it


def pt(t, x, y, ground=False, gs=140.0, h=None):
    return tr.Pt(float(t), float(x), float(y), ground, gs, h)


def _final(last_m, last_ft=ON_GLIDE, across=0.0, to_runway=False):
    """A straight-in final to 27L heard every 140 m from 12 km out on a 3-degree glide at 140 kt, last heard `last_m`
    before the threshold at LAST_KT (that point `across` m off the centreline, at `last_ft` above the field: on the glide
    unless given, None for no height). `to_runway`: heard on in to the threshold and down the runway (a crossing heard)."""
    pts, t = [], -400.0
    for d in np.arange(12000.0, last_m, -140.0):
        pts.append(pt(t, 3600 + d, 0.0, h=TCH_M + d * GLIDE))
        t += 2.0
    h = TCH_M + last_m * GLIDE if last_ft is ON_GLIDE else None if last_ft is None else last_ft * FT
    pts.append(pt(t, 3600 + last_m, across, gs=LAST_KT, h=h))
    if to_runway:
        for d in np.arange(last_m - 140.0, -3000.0, -140.0):
            t += 2.0
            pts.append(pt(t, 3600 + d, 0.0, ground=d < -400, h=max(TCH_M + d * GLIDE, 0.0)))
    return pts


def test_an_approach_last_heard_near_the_threshold_is_joined_to_it():
    track, how = tr.approach_track(_final(600.0), RW, T_LANDING, roll_m=1500.0)
    assert how == 'threshold-joined'
    td = pa.touchdown_offset_m(3.0)
    by_s = {round(n[0], 6): n for n in track}
    assert by_s[round(-td, 6)][1:3] == pytest.approx((3600.0, 0.0))  # the threshold
    # ... reached from the LAST point heard: the join carries that point's speed (a join from the one before it would
    # carry 140 kt, and on a straight final would look the same otherwise).
    assert by_s[round(-td, 6)][3] == pytest.approx(LAST_KT)
    assert by_s[0.0][1:3] == pytest.approx((3600.0 - td, 0.0))  # the touchdown point, on the centreline
    assert track[-1][0] == pytest.approx(1500.0)
    assert [n[0] for n in track] == sorted(n[0] for n in track)
    assert track[0][0] == pytest.approx(-12000.0 - td)


def test_the_join_is_the_one_a_crossing_heard_gives():
    # The same final heard all the way in (threshold-seen) and cut 600 m out (threshold-joined): one track, node for
    # node (on a straight final the join IS the heard path; only the speed and height columns may differ).
    seen, how_seen = tr.approach_track(_final(40.0, to_runway=True), RW, T_LANDING, roll_m=1500.0)
    joined, how_joined = tr.approach_track(_final(600.0), RW, T_LANDING, roll_m=1500.0)
    assert (how_seen, how_joined) == ('threshold-seen', 'threshold-joined')
    assert len(seen) == len(joined)
    for a, b in zip(seen, joined, strict=True):
        assert a[:3] == pytest.approx(b[:3], abs=1e-6)


@pytest.mark.parametrize('last_m, last_ft, across, joined', [
    (1000.0, ON_GLIDE, 0.0, True),  # at the 1 km limit
    (1000.5, ON_GLIDE, 0.0, False),  # just past it
    (600.0, 299.9, 0.0, True),  # just under 300 ft
    (600.0, 300.0, 0.0, False),  # at it: "under" 300 ft
    (600.0, None, 0.0, False),  # no height is not under it
    (600.0, ON_GLIDE, 100.0, True),  # on the centreline's edge (ON_RUNWAY_M)
    (600.0, ON_GLIDE, -100.5, False),  # off it
])
def test_only_an_approach_last_heard_near_low_and_on_the_centreline_is_joined(last_m, last_ft, across, joined):
    track, how = tr.approach_track(_final(last_m, last_ft, across), RW, T_LANDING)
    assert (how == 'threshold-joined') is joined, how
    assert (track is not None) is joined
    if not joined:
        assert how.startswith(tr.NOT_HEARD) and tr.join_refusal(how) in tr.JOIN_REFUSED


def test_each_refusal_says_its_kind():
    def kind(pts):
        return tr.join_refusal(tr.approach_track(pts, RW, T_LANDING)[1])
    assert kind(_final(1500.0)) == 'too far out'
    assert kind(_final(600.0, 400.0)) == 'too high'
    assert kind(_final(600.0, None)) == 'no height'
    assert kind(_final(600.0, across=250.0)) == 'off the centreline'
    assert kind([pt(-30, 5000, 0, ground=True), pt(-20, 4000, 0, ground=True)]) == 'nothing airborne'
    # Last heard beyond the runway's far end (x = 300), on its line: past the threshold, never over the runway.
    assert kind([*_final(5000.0), pt(-10, 200.0, 0.0, h=150.0)]) == 'past the threshold'
    assert tr.join_refusal('no-track: under two points before the threshold') is None
    assert tr.join_refusal(tr.NOT_HEARD) is None


def test_it_is_the_last_point_heard_in_time_not_the_nearest():
    # In to 400 m and 100 ft, then away to the south (a go-around turning off): last heard 600 m off the centreline.
    away = [*_final(400.0), pt(-60, 3200, -300, h=200.0), pt(-50, 3000, -600, h=300.0)]
    assert tr.join_refusal(tr.approach_track(away, RW, T_LANDING)[1]) == 'off the centreline'


def test_a_joined_approach_is_counted_with_the_arrivals_and_apart():
    keys = ('arrivals', 'departures_light', 'departures_heavy', 'departures_light_airborne',
            'departures_heavy_airborne', 'arrivals_joined')
    counts = {k: np.zeros(4, np.int32) for k in keys}
    shares = {f'{k}_p': np.zeros(4) for k in keys}
    res = {'reached': {'light': np.array([0]), 'heavy': np.array([0]), 'approach': np.array([2, 3])},
           'spread': {'light': (np.array([0]), np.array([0.5])), 'heavy': (np.array([0]), np.array([0.5])),
                      'approach': (np.array([2, 3]), np.array([0.75, 0.25]))}}
    nd.tally(counts, shares, {'op': 'A', 'heard': 'low', 'track': 'threshold-seen'}, res)
    nd.tally(counts, shares, {'op': 'A', 'heard': 'low', 'track': 'threshold-joined'}, res)
    nd.tally(counts, shares, {'op': 'D', 'heard': 'low', 'track': 'roll-seen'}, res)
    assert counts['arrivals'].tolist() == [0, 0, 2, 2]
    assert counts['arrivals_joined'].tolist() == [0, 0, 1, 1]
    assert shares['arrivals_p'].tolist() == [0.0, 0.0, 1.5, 0.5]
    assert shares['arrivals_joined_p'].tolist() == [0.0, 0.0, 0.75, 0.25]
    assert counts['departures_light'].tolist() == [1, 0, 0, 0]
    assert not counts['departures_light_airborne'].any()


def test_rule_1s_scale_with_and_without_the_joined_and_the_late_take_offs():
    # 1,200 computed: 60 take-offs first heard in the air, 300 approaches joined.
    assert nd.rule_scales(1245.3, 1200, 60, 300) == {
        'scale': round(1245.3 / 1200, 6), 'scale_without_airborne': round(1245.3 / 1140, 6),
        'scale_without_joined': round(1245.3 / 900, 6), 'scale_without_airborne_or_joined': round(1245.3 / 840, 6)}
    assert nd.rule_scales(1245.3, 300, 0, 300)['scale_without_joined'] is None
    assert set(nd.SCALE_KEYS.values()) == set(nd.rule_scales(1.0, 10, 1, 1))


def _tuples(pts):
    return [dataclasses.astuple(p) for p in pts]


def test_the_check_cuts_a_heard_approach_where_it_came_that_close_so_the_rule_must_join_it():
    heard = _tuples([*_final(40.0, to_runway=True), pt(900, -500, -800, ground=True)])  # the last: after the window
    cut = nd.cut_approach(heard, RW, T_LANDING, 600.0)
    kept = [tr.Pt(*p) for p in cut]
    near = [p for p in kept if T_LANDING - 1800 <= p.t <= T_LANDING + 300 and RW.along_across(p.x, p.y)[0] > -600]
    assert not near  # nothing within 600 m of the threshold, nor over the runway, nor on the ground after
    assert cut[-1] == heard[-1]  # past the window: untouched
    track, how = tr.approach_track(kept, RW, T_LANDING)
    assert how == 'threshold-joined'
    last = max((p for p in kept if p.t <= T_LANDING + 300), key=lambda p: p.t)
    assert 600.0 <= -RW.along_across(last.x, last.y)[0] < 600.0 + 140.0
    # An approach whose crossing was NOT heard is the rule's own case: returned as heard.
    unheard = _tuples(_final(300.0))
    assert nd.cut_approach(unheard, RW, T_LANDING, 600.0) is unheard
