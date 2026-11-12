#!/usr/bin/env python3
"""The ground track one flight actually flew, from its ADS-B trace: N65 step 5 (docs/lessons/n65.md).

WHY THIS EXISTS (2026-11-03)
----------------------------
Doc 29 builds a flight path from a ground track and a profile (Vol 2 s3.6). The profile comes from ANP's default
procedure (scripts/n65_profiles.py); the ground track can come from radar (s3.2.1, s3.4.1), and ours comes from each
flight's own ADS-B positions, so N65 follows where aircraft really turned. This module turns one movement's points into
that track, with the distance s Doc 29 measures along it (s3.3.2): from the START OF ROLL for a departure; for an
approach, from the touchdown point that scripts/n65_path.touchdown_offset_m() places past the landing threshold
(negative before it). It also gives the bank angle Doc 29 needs for the engine installation effect, from the track's
own turns (B-14), since a profile is flown straight (s3.6.1).

THE RULES, each a reading where Doc 29 leaves it to the user:
- The RUNWAY a movement used: the counter's (scripts/adsb_movements.py) where it named one; else the runway whose
  centreline (within ON_RUNWAY_M) the aircraft ran along, in its direction, near the movement's time.
- The START OF ROLL (start_of_roll()): the last point at most ROLL_START_KT on that runway's centreline in the run
  that ends the take-off; else, for a rolling start, where that run joined the centreline; when neither was heard,
  the start of the TAKE-OFF RUN (AD 2.13's TORA, Runway.tora_start_m; Bill's ruling of 3 Nov, built 12 Nov), said by
  its label, never a guessed intersection. The landing threshold stands in, said, only for a runway with no TORA start:
  at Heathrow 09L/09R it is displaced ~309 m, which started those rolls late.
- The take-off and landing rolls run on the centreline (the runway is straight); the airborne track is the observed
  positions resampled every SPACING_M along their own length, which also smooths the few metres of position noise.
- The BANK from the track's curvature over BANK_WINDOW_M either side of a node, B-14 with the observed ground speed,
  positive for left turns (Doc 29 s4.5.2), capped at BANK_LIMIT_DEG against a glitch in the positions (said by count).
- Beyond the observed track the path runs straight on (s3.6.6), so it covers the whole calculation grid.

Pure: points arrive in British National Grid metres (the caller projects them) and nothing here reads a file.
Held by tests/test_n65_tracks.py on made-up traces.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

import n65_path

FT = 0.3048
G_FTS2 = 32.174
ON_RUNWAY_M = 100.0  # a point this close to a centreline is on that runway (Heathrow's parallels are 1.4 km apart)
CENTRELINE_M = 60.0  # a ground-roll point this close to the centreline is snapped onto it
ROLL_START_KT = 15.0  # the last point this slow on the runway before a take-off is where its roll starts
ENTRY_MAX_KT = 40.0  # ... else a run that joined the centreline slower than this started rolling there
SPACING_M = 200.0
BANK_WINDOW_M = 400.0
BANK_LIMIT_DEG = 30.0
MIN_TRACK_M = 2000.0  # an observed airborne track shorter than this is not a track
DEPARTURE_AFTER_S = 1800.0  # the trace read after a take-off ...
APPROACH_BEFORE_S = 1800.0  # ... and before a landing


@dataclass(frozen=True)
class Runway:
    """One runway end, in grid metres: its landing threshold, the unit vector of the direction aircraft move along it
    (from the true bearing, turned onto the grid by the caller), its length to the opposite threshold, its true bearing
    (for the headwind), its ILS glide angle (for the touchdown point) and where its take-off run starts, metres past
    the landing threshold (negative behind it; AD 2.13's TORA start), or None where that is not known."""

    designator: str
    threshold: tuple[float, float]
    direction: tuple[float, float]
    length_m: float
    true_bearing: float
    glide_deg: float
    tora_start_m: float | None = None

    def along_across(self, x: float, y: float) -> tuple[float, float]:
        """(along, across): metres past the threshold in the direction of movement, and to the left (+) or right."""
        dx, dy = x - self.threshold[0], y - self.threshold[1]
        ux, uy = self.direction
        return dx * ux + dy * uy, ux * dy - uy * dx

    def point(self, along: float) -> tuple[float, float]:
        return self.threshold[0] + along * self.direction[0], self.threshold[1] + along * self.direction[1]


def reciprocal(designator: str) -> str:
    """'09L' -> '27R', '15' -> '33': the same runway's other end."""
    num, side = int(designator[:2]), designator[2:]
    return f'{(num + 18 - 1) % 36 + 1:02d}' + {'L': 'R', 'R': 'L', 'C': 'C', '': ''}[side]


@dataclass(frozen=True)
class Pt:
    """One trace point in grid metres: time (epoch s), x, y, on the ground, ground speed (kt or None) and the observed
    height above the field (m or None; kept to compare with the profile, never used to fly it)."""

    t: float
    x: float
    y: float
    ground: bool
    gs_kt: float | None
    height_m: float | None


def runway_from_points(pts: list[Pt], runways: dict[str, Runway], t0: float, t1: float) -> str | None:
    """The runway whose centreline the aircraft ran along, in its direction, between t0 and t1: the most points within
    ON_RUNWAY_M of a centreline (and inside the runway or its first 5 km either way), moving along it; None if no
    runway has three."""
    best, best_n = None, 2
    for des, rw in runways.items():
        on = [(p.t, rw.along_across(p.x, p.y)[0]) for p in pts if t0 <= p.t <= t1
              and abs(rw.along_across(p.x, p.y)[1]) <= ON_RUNWAY_M
              and -5000 <= rw.along_across(p.x, p.y)[0] <= rw.length_m + 5000]
        if len(on) > best_n and on[-1][1] > on[0][1]:
            best, best_n = des, len(on)
    return best


def _resample(poly: list[tuple[float, float, float, float | None, float | None]], spacing: float, keep=()):
    """poly [(s, x, y, gs, h)] with s increasing, every `spacing` metres along s plus both ends and `keep`."""
    ss = [p[0] for p in poly]
    grid = set(_frange(ss[0], ss[-1], spacing)) | {ss[0], ss[-1]} | {s for s in keep if ss[0] <= s <= ss[-1]}
    out = []
    for s in sorted(grid):
        i = min(max(bisect.bisect_left(ss, s), 1), len(poly) - 1)
        a, b = poly[i - 1], poly[i]
        f = (s - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
        gs = _lerp(a[3], b[3], f)
        h = _lerp(a[4], b[4], f)
        out.append((s, a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), gs, h))
    return out


def _frange(a, b, step):
    k = math.ceil(a / step)
    while k * step < b:
        yield k * step
        k += 1


def _lerp(a, b, f):
    if a is None or b is None:
        return a if b is None else b if a is None else None
    return a + f * (b - a)


def _arc(points_xy):
    s, out = 0.0, [0.0]
    for (x0, y0), (x1, y1) in zip(points_xy, points_xy[1:], strict=False):
        s += math.hypot(x1 - x0, y1 - y0)
        out.append(s)
    return out


def _thin(pts: list[Pt], min_m: float = 5.0) -> list[Pt]:
    """Points closer than `min_m` to the previous kept one are dropped (a hover of position noise, not a track)."""
    out = []
    for p in pts:
        if not out or math.hypot(p.x - out[-1].x, p.y - out[-1].y) >= min_m:
            out.append(p)
    return out


def start_of_roll(pts: list[Pt], rw: Runway, t_takeoff: float) -> tuple[float, float | None, str]:
    """(metres past the threshold where the roll starts, the time it was there or None, how it was found).

    The take-off's RUN is the stretch of centreline points (within CENTRELINE_M, from 500 m behind the threshold to the
    far end, in the 15 minutes before the take-off) that ends the take-off, cut where the points go backwards or fall
    silent for two minutes. 'roll-seen': its last point at most ROLL_START_KT (lining up, or holding on the runway).
    'roll-entered': none was that slow but the run's first point was under ENTRY_MAX_KT (a rolling start from where it
    joined the centreline). Neither (the start was not heard): 'roll-at-tora-start', where the runway's take-off run
    starts (rw.tora_start_m, AD 2.13), or 'roll-at-threshold', the landing threshold, for a runway that has none."""
    on = []
    for p in pts:
        a, c = rw.along_across(p.x, p.y)
        if t_takeoff - 900 <= p.t <= t_takeoff and abs(c) <= CENTRELINE_M and -500 <= a <= rw.length_m:
            on.append((p.t, a, p.gs_kt))
    if not on:
        return _unheard(rw)
    run = [on[-1]]
    for prev in reversed(on[:-1]):
        if run[0][0] - prev[0] > 120 or prev[1] > run[0][1] + 50:
            break
        run.insert(0, prev)
    slow = [r for r in run if r[2] is not None and r[2] <= ROLL_START_KT]
    if slow:
        return slow[-1][1], slow[-1][0], 'roll-seen'
    if run[0][2] is not None and run[0][2] <= ENTRY_MAX_KT:
        return run[0][1], run[0][0], 'roll-entered'
    return _unheard(rw)


def _unheard(rw: Runway) -> tuple[float, None, str]:
    """An unheard start of roll: the take-off run's start where the runway has one, else the landing threshold."""
    if rw.tora_start_m is not None:
        return rw.tora_start_m, None, 'roll-at-tora-start'
    return 0.0, None, 'roll-at-threshold'


def departure_track(pts: list[Pt], rw: Runway, t_takeoff: float, spacing: float = SPACING_M):
    """The departure's ground track [(s, x, y, gs, h)] from the start of roll (s = 0), and how its start was found
    (start_of_roll()'s label). None (with a reason) when fewer than MIN_TRACK_M of airborne track were heard.

    Up to the take-off only points on the runway ahead of the start of roll belong to this roll (snapped onto the
    centreline); after it every point is the flight's, wherever it goes (an easterly departure turning back west
    passes behind its own start of roll)."""
    a_sor, t_sor, how = start_of_roll(pts, rw, t_takeoff)
    t_from = t_sor if t_sor is not None else t_takeoff - 120
    after = []
    for p in pts:
        if not (t_from < p.t <= t_takeoff + DEPARTURE_AFTER_S):
            continue
        a, c = rw.along_across(p.x, p.y)
        on_runway = abs(c) <= CENTRELINE_M and a_sor <= a <= rw.length_m
        if on_runway and (p.t <= t_takeoff or p.ground):
            after.append(Pt(p.t, *rw.point(a), p.ground, p.gs_kt, p.height_m))
        elif p.t > t_takeoff and not p.ground:
            after.append(p)
    sx, sy = rw.point(a_sor)

    seq = _thin([Pt(t_from, sx, sy, True, 0.0, 0.0), *after])
    if len(seq) < 3:
        return None, 'no-track: under three points after the start of roll'
    s = _arc([(p.x, p.y) for p in seq])
    if s[-1] - (rw.length_m - a_sor) < MIN_TRACK_M:
        return None, f'no-track: {s[-1]:.0f} m heard from the start of roll'
    poly = [(si, p.x, p.y, p.gs_kt, p.height_m) for si, p in zip(s, seq, strict=True)]
    return _resample(poly, spacing), how


def approach_track(pts: list[Pt], rw: Runway, t_landing: float, spacing: float = SPACING_M, roll_m: float = 0.0):
    """The approach's ground track [(s, x, y, gs, h)], s = 0 at the touchdown point, negative before it, running on
    along the centreline `roll_m` past touchdown for the landing roll. None (with a reason) when the threshold
    crossing or MIN_TRACK_M of approach was not heard."""
    window = [p for p in pts if t_landing - APPROACH_BEFORE_S <= p.t <= t_landing + 300]
    crossing = next((p.t for p in window if 0 <= rw.along_across(p.x, p.y)[0] <= rw.length_m
                     and abs(rw.along_across(p.x, p.y)[1]) <= ON_RUNWAY_M), None)
    if crossing is None:
        return None, 'no-track: the threshold crossing was not heard'
    # The whole approach in time order (downwind legs past the threshold included), from after any time on the ground.
    on_ground = [p.t for p in window if p.ground and p.t < crossing]
    since = max(on_ground, default=-math.inf)
    before = _thin([p for p in window if since < p.t < crossing and not p.ground])
    if len(before) < 2:
        return None, 'no-track: under two points before the threshold'
    seq = [*before, Pt(crossing, *rw.threshold, False, before[-1].gs_kt, None)]
    s = _arc([(p.x, p.y) for p in seq])
    if s[-1] < MIN_TRACK_M:
        return None, f'no-track: {s[-1]:.0f} m heard before the threshold'
    td = n65_path.touchdown_offset_m(rw.glide_deg)
    poly = [(si - s[-1] - td, p.x, p.y, p.gs_kt, p.height_m) for si, p in zip(s, seq, strict=True)]
    tdx, tdy = rw.point(td)
    poly.append((0.0, tdx, tdy, poly[-1][3], 0.0))
    if roll_m > 0:
        ex, ey = rw.point(td + roll_m)
        poly.append((roll_m, ex, ey, None, 0.0))
    return _resample(poly, spacing, keep=(0.0, -td)), 'threshold-seen'


def bank_angles(track: list[tuple], window_m: float = BANK_WINDOW_M, limit_deg: float = BANK_LIMIT_DEG):
    """[(s, x, y, bank_deg)] and how many nodes hit the limit. B-14: tan(bank) = 2.85 V^2 / (r g), V the ground speed
    (kt), r the turn radius (ft) from the heading change across `window_m` either side; positive for LEFT turns
    (Doc 29 s4.5.2: starboard wing up); 0 where the speed is unknown or the track straight."""
    ss = [n[0] for n in track]
    out, capped = [], 0
    for i, (s, x, y, gs, _h) in enumerate(track):
        lo = bisect.bisect_left(ss, s - window_m)
        hi = min(bisect.bisect_right(ss, s + window_m) - 1, len(track) - 1)
        bank = 0.0
        if 0 < i and i < len(track) - 1 and lo < i < hi and gs:
            h_in = _heading(track[lo], track[i])
            h_out = _heading(track[i], track[hi])
            turn = (h_out - h_in + 180) % 360 - 180  # degrees, positive clockwise (a right turn)
            length = (track[hi][0] - track[lo][0]) / 2
            if turn and length > 0:
                radius_ft = length / math.radians(abs(turn)) / FT
                bank = math.degrees(math.atan(2.85 * gs * gs / (radius_ft * G_FTS2)))
                if bank > limit_deg:
                    bank, capped = limit_deg, capped + 1
                bank = -bank if turn > 0 else bank
        out.append((s, x, y, bank))
    return out, capped


def _heading(a, b):
    """Grid heading (degrees clockwise from grid north) from node a to node b."""
    return math.degrees(math.atan2(b[1] - a[1], b[2] - a[2])) % 360


def extend(track: list[tuple], before_m: float, after_m: float) -> list[tuple]:
    """The track run straight on `before_m` before its first node and `after_m` past its last (s3.6.6), each along its
    end segment, bank 0. Nodes are (s, x, y, bank)."""
    out = list(track)
    if before_m > 0:
        (s0, x0, y0, _), (s1, x1, y1, _) = track[0], track[1]
        d = math.hypot(x1 - x0, y1 - y0)
        out.insert(0, (s0 - before_m, x0 - (x1 - x0) / d * before_m, y0 - (y1 - y0) / d * before_m, 0.0))
    if after_m > 0:
        (s0, x0, y0, _), (s1, x1, y1, _) = track[-2], track[-1]
        d = math.hypot(x1 - x0, y1 - y0)
        out.append((s1 + after_m, x1 + (x1 - x0) / d * after_m, y1 + (y1 - y0) / d * after_m, 0.0))
    return out
