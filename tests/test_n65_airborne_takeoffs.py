"""Rule 6 of N65's frozen method (Bill, 2026-11-15): take-offs first heard in the air (scripts/n65_day.py).

Until a receiver came online (Heathrow 7 Oct 2025, Gatwick 5 Nov 2025) 10-15% of their take-offs were first heard at
about 410-630 ft over the runway's far half, above the plane counter's 400 ft band, so the counter never counted them.
airborne_takeoffs() finds them with the counter's own bounds; the track builder the counter's take-offs use starts
them at the take-off run's start (nothing added for it); tally() keeps them inside the departures and apart;
rule_scales() gives rule 1's scale with and without them. Aircraft fly down Heathrow's REAL runways
(data/flight-procedures.json), as tests/test_adsb_movements.py flies them; the track test uses a made-up flat runway,
as tests/test_n65_tracks.py does. Offline only.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import adsb_movements as am  # noqa: E402
import n65_day as nd  # noqa: E402
import n65_tracks as tr  # noqa: E402

AP = am.load_airports()['LHR']
THR27R, BRG27 = AP['runways']['27R']
FIELD = 0  # the field's pressure level throughout
T0 = 1_000_000.0


def offset(lat, lon, bearing, km):
    """The point `km` from (lat, lon) on `bearing`."""
    d, b = km / 6371.0, math.radians(bearing)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)


def pt(t, lat, lon, alt, track=None):
    # [epoch_s, lat, lon, alt_baro, alt_geom, gs, track, baro_rate, flags, callsign], as the extracts hold them
    return [t, lat, lon, alt, None, 160, BRG27 if track is None else track, None, 0, 'TEST1']


def along_27r(t, km_from, ft_from, km_to=12.0, ft_per_km=262.0, step_km=0.5, step_s=10):
    """Points down 27R's direction (west) from `km_from` km past its landing threshold, `ft_from` ft and climbing
    `ft_per_km` (262 ft a km is an 8% climb), one every `step_s` s."""
    pts, k = [], 0
    while km_from + k * step_km <= km_to + 1e-9:
        km = km_from + k * step_km
        pts.append(pt(t + k * step_s, *offset(*THR27R, BRG27, km), round(ft_from + (km - km_from) * ft_per_km)))
        k += 1
    return pts


def ground_on_27r(t, n=4, step_s=20):
    lat, lon = offset(*THR27R, BRG27, 0.3)
    return [pt(t + i * step_s, lat, lon, 'ground') for i in range(n)]


def heard(points):
    """(the counter's movements, rule 6's take-offs) for one aircraft's points."""
    moves, _ = am.movements({'pts': points}, AP, FIELD)
    return moves, nd.airborne_takeoffs({'pts': points}, AP, FIELD, moves)


def test_a_take_off_first_heard_in_the_air_is_found_on_its_runway():
    # First heard 3 km down 27R at 450 ft (the median the 2025 days showed), climbing west: the counter sees nothing.
    moves, late = heard(along_27r(T0, 3.0, 450))
    assert moves == []
    assert late == [('take-off', '27R', T0)]


def test_a_take_off_the_counter_heard_stays_the_counters():
    # Heard on the runway, then climbing from it without a break: the counter's take-off, nothing added.
    moves, late = heard(ground_on_27r(T0) + along_27r(T0 + 80, 1.5, 0))
    assert [k for k, _, _ in moves] == ['take-off'] and late == []
    # Heard on the runway, silent past RUN_GAP_S, then first heard at 450 ft: still one take-off, the counter's.
    points = ground_on_27r(T0) + along_27r(T0 + 60 + am.RUN_GAP_S + 40, 3.0, 450)
    moves, late = heard(points)
    assert [k for k, _, _ in moves] == ['take-off'] and late == []


def test_first_heard_too_high_or_outside_the_zone_is_not_one():
    assert heard(along_27r(T0, 3.0, am.UNSEEN_BAND_FT + 100))[1] == []
    assert heard(along_27r(T0, 3.0, am.UNSEEN_BAND_FT - 50))[1] == [('take-off', '27R', T0)]
    assert heard(along_27r(T0, 9.0, 450, km_to=18.0))[1] == []  # 9 km down: outside the airport's zone


def test_only_the_start_of_a_stretch_can_be_one():
    # Heard 200 s earlier far out and high (an aircraft passing, then descending low over the field and climbing
    # away): the stretch starts out there, so it is not a take-off first heard in the air.
    far = pt(T0 - 200, *offset(*THR27R, BRG27, 30.0), 9000)
    assert heard([far] + along_27r(T0, 3.0, 450))[1] == []
    # Silent for longer than RUN_GAP_S after that: the climb starts its own stretch, and is one.
    far = pt(T0 - am.RUN_GAP_S - 1, *offset(*THR27R, BRG27, 30.0), 9000)
    assert heard([far] + along_27r(T0, 3.0, 450))[1] == [('take-off', '27R', T0)]


def test_a_stretch_that_never_climbs_away_is_not_one():
    # A low pass west at 450-500 ft that never reaches CLIMB_FT above the field.
    assert heard(along_27r(T0, 3.0, 450, km_to=8.0, ft_per_km=10.0))[1] == []
    # A go-around first heard coming IN over the threshold at 600 ft: it reaches CLIMB_FT nearer the centre than it
    # was first heard, so it is not climbing away from a take-off.
    inbound = along_27r(T0, -0.5, 600, km_to=4.0, ft_per_km=262.0)
    assert heard(inbound)[1] == []


def test_the_track_of_one_starts_at_the_take_off_runs_start():
    # A made-up flat runway (27L-like: west along y = 0 from x = 3,600 m, its take-off run starting 200 m behind its
    # landing threshold). The aircraft crossed it taxiing 400 s before (slow, on the centreline at along 1,000 m), was
    # silent (as every rule 6 stretch is, past RUN_GAP_S), and was first heard at 150 m over along 1,600 m, climbing
    # west. The track builder the counter's take-offs use finds no roll (the crossing is cut off by the silence) and
    # joins the flight to the runway at the take-off run's start: rule 6's join, with nothing added for it.
    rw = tr.Runway('27L', (3600.0, 0.0), (-1.0, 0.0), 3300.0, 270.0, 3.0, -200.0)
    taxi = [(T0 - 400 + i * 5, 2600.0, -30.0 + 30 * i, True, 10.0, 0.0) for i in range(3)]
    air = [(T0 + k * 2.7, 2000.0 - 200 * k, 0.0, False, 150.0, 150.0 + 16 * k) for k in range(41)]
    assert taxi[-1][0] < T0 - am.RUN_GAP_S
    track, how = tr.departure_track([tr.Pt(*p) for p in taxi + air], rw, T0)
    assert how == 'roll-at-tora-start'
    assert track[0][0] == 0.0 and (track[0][1], track[0][2]) == pytest.approx(rw.point(-200.0))
    # It runs along the runway to the first point heard, then on with the heard track: 3,600 + 200 - 2,000 m to it.
    first = next(n for n in track if n[1] <= 2000.0)
    assert first[0] == pytest.approx(1800.0, abs=1e-6) and abs(first[2]) < 1e-9


def test_one_is_counted_with_the_departures_and_apart():
    labels = ('light', 'heavy')
    keys = ('arrivals', 'departures_light', 'departures_heavy', 'departures_light_airborne',
            'departures_heavy_airborne')
    counts = {k: np.zeros(4, np.int32) for k in keys}
    shares = {f'{k}_p': np.zeros(4) for k in keys}
    res = {'reached': {'light': np.array([0, 1]), 'heavy': np.array([1, 2]), 'approach': np.array([3])},
           'spread': {'light': (np.array([0, 1]), np.array([0.5, 0.25])), 'heavy': (np.array([1, 2]), np.array([.5, .5])),
                      'approach': (np.array([3]), np.array([0.75]))}}
    nd.tally(counts, shares, {'op': 'D', 'heard': 'low'}, res, labels)
    nd.tally(counts, shares, {'op': 'D', 'heard': 'airborne'}, res, labels)
    nd.tally(counts, shares, {'op': 'A', 'heard': 'low'}, res, labels)
    assert counts['departures_light'].tolist() == [2, 2, 0, 0]
    assert counts['departures_light_airborne'].tolist() == [1, 1, 0, 0]
    assert counts['departures_heavy_airborne'].tolist() == [0, 1, 1, 0]
    assert counts['arrivals'].tolist() == [0, 0, 0, 1]
    assert shares['departures_light_p'].tolist() == [1.0, 0.5, 0.0, 0.0]
    assert shares['departures_light_airborne_p'].tolist() == [0.5, 0.25, 0.0, 0.0]
    assert shares['arrivals_p'].tolist() == [0.0, 0.0, 0.0, 0.75]


def test_rule_1s_scale_with_them_and_without_them():
    # July 2026's 1,245.3 a 16-hour day over 1,200 computed, 60 of them first heard in the air.
    assert nd.rule_scales(1245.3, 1200, 60) == {'scale': round(1245.3 / 1200, 6),
                                                'scale_without_airborne': round(1245.3 / 1140, 6)}
    assert nd.rule_scales(1245.3, 0, 0) == {'scale': None, 'scale_without_airborne': None}
    assert nd.rule_scales(1245.3, 60, 60)['scale_without_airborne'] is None
