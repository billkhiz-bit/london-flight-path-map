#!/usr/bin/env python3
"""One flight's three-dimensional path, as ECAC Doc 29 (5th edition, Volume 2 s3.6) builds it: N65 step 5.

WHY THIS EXISTS (2026-11-03)
----------------------------
scripts/n65_profiles.py flies an ANP aircraft's default procedure and returns its PROFILE (height, speed and engine
power against distance along the track). scripts/n65_tracks.py turns an ADS-B trace into the GROUND TRACK the aircraft
actually flew. Doc 29 merges the two (s3.6.6) after cutting the profile finer where the geometry changes fast: the
take-off roll (s3.6.2), the initial climb and final approach (s3.6.4) and any airborne stretch whose speed changes by
more than 20 kt (s3.6.5); then drops points too close together (s3.6.7). The result is the list of segment end points
scripts/n65_doc29.py and scripts/n65_grid.py read: x, y, z (metres), power, bank angle, take-off roll.

It also holds the step's small rules, each a reading said here and in docs/lessons/n65.md:
- WHICH PROCEDURE stands for a flight (procedure_for): ANP's DEFAULT; for departures without one, ICAO_B (the
  "distant" noise abatement procedure, NADP 2), then ICAO_A; for approaches without one, DEFAULT1 (the newer Airbus
  types carry DEFAULT1 and DEFAULT2, which differ only in how long they hold 3,000 ft far out). Procedural steps
  before a published fixed-point profile, because steps answer to the day's air. Anything else: not computed.
- WHICH STAGE LENGTH (stages_for): the trip's distance through Doc 29's G3.5 bands when it is known; when it is not,
  BOTH the lightest and the heaviest stage the aircraft's procedure offers, kept apart (a bracket, never a guess).
- THE TOUCHDOWN POINT: ANP's approach profiles end at touchdown (distance 0) and Doc 29 s3.3.2 measures approach tracks
  from the landing threshold; the profiles themselves cross the threshold at 50 ft on a 3 degree glide (954 ft before
  touchdown), so the touchdown is placed THRESHOLD_CROSSING_FT / tan(glide) past the threshold, the airport's own
  glide angle (AD 2.19). Doc 29 does not say this in words.
- THE HEADWIND along the runway from the day's wind (headwind_kt); the aerodrome pressure from QNH (pressure_kpa).

NOTHING HERE IS EASA'S DATA: profiles arrive from n65_profiles, already flown. Units: profiles in feet and knots, as
Appendix B gives them; tracks and paths in metres. Held by tests/test_n65_path.py on made-up profiles and tracks, and on
Doc 29's own worked example of s3.6.4.
"""
from __future__ import annotations

import bisect
import itertools
import math

import n65_profiles as pr

FT = 0.3048
KT_MS = 0.514444  # knots to metres per second (1852 / 3600)
INF = float('inf')

# Doc 29 Vol 2 G3.5: trip length (nmi) to stage length number; 'M' (the maximum range at MTOW) is not a band.
STAGE_TRIP_NMI = (('1', 0, 500), ('2', 500, 1000), ('3', 1000, 1500), ('4', 1500, 2500), ('5', 2500, 3500),
                  ('6', 3500, 4500), ('7', 4500, 5500), ('8', 5500, 6500), ('9', 6500, 7500), ('10', 7500, 8500),
                  ('11', 8500, INF))
DEPARTURE_PROCEDURES = ('DEFAULT', 'ICAO_B', 'ICAO_A')
APPROACH_PROCEDURES = ('DEFAULT', 'DEFAULT1')
# s3.6.4: the heights (m) the initial climb and final approach are cut at, for at most 1.5 dB of lateral attenuation
# change per sub-segment.
SUB_HEIGHTS_M = (18.9, 41.5, 68.3, 102.1, 147.5, 214.9, 334.9, 609.6, 1289.6)
SPEED_SPLIT_KT = 20.0  # s3.6.5: an airborne segment whose speed changes by more than this is cut ...
SPEED_STEP_MS = 10.0  # ... into int(1 + |dV| / 10) parts, dV in m/s as on the ground roll (3-3a)
CLOSE_M = 10.0  # s3.6.7: adjacent points closer than this with the same speed and power are one
SOURCE_MIN_M = 1.0  # s3.5: the noise source at least 1 m above the aerodrome
THRESHOLD_CROSSING_FT = 50.0  # ANP's approach profiles cross the threshold at 50 ft (see the docstring)


# ----------------------------------------------------------------- choices for one flight


def stage_for_trip(nmi: float) -> str:
    """G3.5: the stage length number for a trip of `nmi` nautical miles (lower bound inclusive)."""
    if nmi < 0 or math.isnan(nmi):
        raise ValueError(f'a trip of {nmi} nmi')
    for stage, lo, hi in STAGE_TRIP_NMI:
        if lo <= nmi < hi:
            return stage
    raise AssertionError('unreachable: the last band is open')


def _stage_order(stage: str, weights: dict) -> tuple:
    """Heavier later: by the stage's default take-off weight where the table gives it, else by number ('M' last)."""
    w = weights.get(stage)
    rank = INF if stage == 'M' else float(stage) if stage.isdigit() else INF
    return (w if w is not None else INF, rank)


def stages_for(have: set[str], weights: dict, trip_nmi: float | None) -> list[tuple[str, str]]:
    """[(label, stage)] for a departure whose procedure offers stages `have` ({'1', '2', ..., 'M'}).

    Trip known: [('trip', its stage)], or [('beyond-range', the heaviest offered)] when ANP gives this aircraft no
    profile that long (G3.5: "the ANP for a given aircraft only includes stage lengths that represent the maximum range
    for the aircraft"). Trip unknown: [('light', lightest), ('heavy', heaviest)], by default weight, so the two bound
    what the unknown weight can do; never one picked as typical."""
    if not have:
        return []
    ordered = sorted(have, key=lambda s: _stage_order(s, weights))
    if trip_nmi is None:
        return [('light', ordered[0]), ('heavy', ordered[-1])]
    wanted = stage_for_trip(trip_nmi)
    if wanted in have:
        return [('trip', wanted)]
    numeric = sorted(int(s) for s in have if s.isdigit())
    if numeric and int(wanted) > numeric[-1]:
        return [('beyond-range', ordered[-1])]
    # A band missing inside the aircraft's range: the next heavier offered (errs loud), said by its label.
    heavier = [s for s in ordered if s.isdigit() and int(s) > int(wanted)] or [ordered[-1]]
    return [('next-heavier', heavier[0])]


def procedure_for(available: list[tuple[str, str, str]], op: str) -> tuple[str, str] | None:
    """(source 'steps'/'fixed', profile id) for op 'D'/'A' from n65_profiles.available(), or None when ANP offers only
    procedures this rule does not name (said as not computed, never a pick among unnamed ones)."""
    order = DEPARTURE_PROCEDURES if op == 'D' else APPROACH_PROCEDURES
    for source in ('steps', 'fixed'):
        ids = {p for s, p, _stage in available if s == source}
        for pid in order:
            if pid in ids:
                return source, pid
    return None


def headwind_kt(wind_from_deg: float, wind_kt: float, heading_deg: float) -> float:
    """The wind's component into the face of an aircraft heading `heading_deg` (true), from a wind blowing FROM
    `wind_from_deg` (true, as a METAR reports it): positive a headwind, negative a tailwind."""
    return wind_kt * math.cos(math.radians(wind_from_deg - heading_deg))


def pressure_kpa(qnh_hpa: float, elevation_m: float) -> float:
    """The air pressure at the aerodrome from its QNH (sea-level pressure on the standard atmosphere), for 4-6/4-7."""
    return qnh_hpa * (1 - 2.25577e-5 * elevation_m) ** 5.25588 / 10.0


def touchdown_offset_m(glide_deg: float) -> float:
    """How far past the landing threshold an approach profile's distance 0 (touchdown) lies (see the docstring)."""
    return THRESHOLD_CROSSING_FT * FT / math.tan(math.radians(glide_deg))


# ----------------------------------------------------------------- the profile cut finer (s3.6.2, 3.6.4, 3.6.5)


def sub_heights_m(z_low: float, z_high: float) -> list[float]:
    """s3.6.4, 3-4: the heights (m, ascending) strictly between z_low and z_high at which a climb (or, read in reverse,
    an approach) segment is cut. z_e is its upper end, capped at 1289.6 m; z'_N the set member nearest z_e; the cuts
    z_e z'_i / z'_N, from the first above z_low. An upper end above 1289.6 m keeps the 1289.6 m cut itself."""
    if z_high <= z_low or z_low >= SUB_HEIGHTS_M[-1]:
        return []
    z_e = min(z_high, SUB_HEIGHTS_M[-1])
    n = min(range(len(SUB_HEIGHTS_M)), key=lambda i: abs(SUB_HEIGHTS_M[i] - z_e))
    cuts = [z_e * SUB_HEIGHTS_M[i] / SUB_HEIGHTS_M[n] for i in range(n + 1)]
    return [z for z in cuts if z_low < z < z_high]


def _at(a: pr.Point, b: pr.Point, s_ft: float, step: str) -> pr.Point:
    z, v, p = pr.interpolate([a, b], s_ft)  # 3-2a, 3-2b, 3-2d (and 3-2e to 3-2g for negative power)
    return pr.Point(s_ft, z, v, p, step)


def _split_by_height(a: pr.Point, b: pr.Point, op: str) -> list[pr.Point]:
    """The points s3.6.4 inserts between a and b (flight order): on a climbing departure segment, or a descending
    approach segment, below 1289.6 m."""
    za, zb = a.height_ft * FT, b.height_ft * FT
    climbing, descending = zb > za, zb < za
    if not ((op == 'D' and climbing) or (op == 'A' and descending)):
        return []
    lo, hi = min(za, zb), max(za, zb)
    heights = sub_heights_m(lo, hi)
    if descending:
        heights = heights[::-1]
    out = []
    for z in heights:
        f = (z - za) / (zb - za)
        out.append(_at(a, b, a.distance_ft + f * (b.distance_ft - a.distance_ft), 'sub-height'))
    return out


def _split_by_speed(a: pr.Point, b: pr.Point) -> list[pr.Point]:
    """s3.6.5: an airborne segment whose speed changes by more than 20 kt, cut into int(1 + |dV| / 10 m/s) parts of
    equal speed change at constant acceleration (3-3f to 3-3i), power changing by equal steps (3-3e), height linear in
    distance (3-2a)."""
    if a.height_ft <= 0 and b.height_ft <= 0:
        return []  # the ground rolls are cut by s3.6.2 and the landing roll's steps
    v1, v2 = a.tas_kt * KT_MS, b.tas_kt * KT_MS
    if abs(b.tas_kt - a.tas_kt) <= SPEED_SPLIT_KT or v1 + v2 <= 0:
        return []
    n = int(1 + abs(v2 - v1) / SPEED_STEP_MS)
    dv = (v2 - v1) / n
    length = b.distance_ft - a.distance_ft
    out, travelled = [], 0.0
    for k in range(1, n):
        travelled += (v1 + dv * (k - 0.5)) * 2 * length / ((v2 + v1) * n)  # 3-3i
        f = travelled / length if length else 0.0
        out.append(pr.Point(a.distance_ft + travelled, a.height_ft + f * (b.height_ft - a.height_ft),
                            (v1 + dv * k) / KT_MS, a.thrust + (b.thrust - a.thrust) * k / n, 'sub-speed'))
    return out


def takeoff_roll_points(points: list[pr.Point]) -> tuple[list[pr.Point], float]:
    """A departure profile with its ground roll cut by s3.6.2 (n65_profiles.takeoff_roll), and the lift-off distance
    (ft). The roll is the profile's leading run of points at height 0."""
    k = 0
    while k + 1 < len(points) and points[k + 1].height_ft <= 0:
        k += 1
    if k == 0:
        return list(points), points[0].distance_ft
    roll = [points[0]]
    for a, b in itertools.pairwise(points[: k + 1]):
        roll += pr.takeoff_roll(a, b)[1:]
    return roll + list(points[k + 1:]), points[k].distance_ft


def subsegment(points: list[pr.Point], op: str) -> tuple[list[pr.Point], float | None]:
    """The profile cut as s3.6.2 (departures), s3.6.4 and s3.6.5 require, in that order; and the lift-off distance
    (ft) for a departure (None for an approach)."""
    lift = None
    if op == 'D':
        points, lift = takeoff_roll_points(points)
    out = [points[0]]
    for a, b in itertools.pairwise(points):
        by_height = [a, *_split_by_height(a, b, op), b]
        for c, d in itertools.pairwise(by_height):
            out += [*_split_by_speed(c, d), d]
    return out, lift


# ----------------------------------------------------------------- merging with the ground track (s3.6.6, 3.6.7)


def _track_at(track, s):
    """(x, y, bank) on a ground track [(s, x, y, bank)] at distance s, straight on beyond either end (s3.6.6)."""
    ss = [n[0] for n in track]
    i = bisect.bisect_left(ss, s)
    i = min(max(i, 1), len(track) - 1)
    (s0, x0, y0, b0), (s1, x1, y1, b1) = track[i - 1], track[i]
    f = (s - s0) / (s1 - s0)
    bank = b0 + min(max(f, 0.0), 1.0) * (b1 - b0)
    if s < ss[0] or s > ss[-1]:
        bank = 0.0  # beyond the observed track the extension is straight
    return x0 + f * (x1 - x0), y0 + f * (y1 - y0), bank


def merge(profile_pts: list[pr.Point], track: list[tuple[float, float, float, float]], op: str,
          lift_ft: float | None = None, power=lambda thrust: thrust) -> list[tuple]:
    """The 3-D path (s3.6.6): every profile point and every track node between the track's first and last node, each
    with the track's x, y and bank and the profile's height, speed and power (3-2 between profile points; beyond the
    profile, n65_profiles.interpolate() holds speed and power and carries the height on the end gradient).

    `profile_pts` and `lift_ft` as subsegment() returns them; `track` [(s_m, x_m, y_m, bank_deg)], s increasing in the
    direction of flight from the start of roll (departures) or the touchdown point (approaches, negative before it);
    `power` turns the profile's thrust into the noise table's power parameter (n65_profiles.npd_power).

    A departure path begins at the start of roll, and its take-off roll keeps s3.6.2's segments only: a track node
    inside the roll would start a new roll segment, and each roll segment carries its own start-of-roll directivity
    (4-22 to 4-25), so the runway's nodes are left out there (the roll is straight along the runway anyway). An
    approach path ends at the profile's last point (the aircraft leaves the runway; taxiing is not counted, s3.6.3),
    and its landing roll likewise keeps the profile's own points. Returns [(x, y, z, power, bank, takeoff_roll,
    speed_kt, s_m)] in metres; the first six are what n65_doc29.event_lmax() and n65_grid.event_lmax() read."""
    if len(track) < 2 or len(profile_pts) < 2:
        raise ValueError('a path needs two track nodes and two profile points')
    s_lo, s_hi = track[0][0], track[-1][0]
    if op == 'D':
        if lift_ft is None:
            raise ValueError('a departure path needs its lift-off distance')
        s_lo = max(s_lo, profile_pts[0].distance_ft * FT)
        ground_lo, ground_hi = s_lo, lift_ft * FT
    else:
        s_hi = min(s_hi, profile_pts[-1].distance_ft * FT)
        ground_lo, ground_hi = 0.0, s_hi
    if s_hi <= s_lo:
        raise ValueError('the track and the profile do not overlap')
    from_track = {round(n[0], 6) for n in track
                  if s_lo <= n[0] <= s_hi and not ground_lo < n[0] < ground_hi}
    ss = sorted({round(p.distance_ft * FT, 6) for p in profile_pts if s_lo <= p.distance_ft * FT <= s_hi}
                | from_track | {round(s_lo, 6), round(s_hi, 6)})
    nodes = []
    for s in ss:
        x, y, bank = _track_at(track, s)
        z_ft, v, p = pr.interpolate(profile_pts, s / FT)
        if z_ft <= 0:
            bank = 0.0
        roll = op == 'D' and s < lift_ft * FT
        nodes.append((x, y, max(z_ft * FT, SOURCE_MIN_M), power(p), bank, roll, v, s))
    return drop_close(nodes)


def drop_close(nodes: list[tuple]) -> list[tuple]:
    """s3.6.7: of two adjacent points within 10 m of each other with the same speed and power, one goes (the later,
    so the path keeps its first point and its end)."""
    out = [nodes[0]]
    for n in nodes[1:]:
        last = out[-1]
        close = math.dist(last[:3], n[:3]) < CLOSE_M
        if close and last[3] == n[3] and last[6] == n[6] and n is not nodes[-1]:
            continue
        out.append(n)
    return out
