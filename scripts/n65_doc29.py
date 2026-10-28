#!/usr/bin/env python3
"""The loudest moment of one flight at one place, by ECAC Doc 29 (5th edition, May 2026): what N65 counts.

WHY THIS EXISTS (2026-10-28)
----------------------------
N65 is the number of flights a day whose maximum sound level LAmax reaches 65 dB (Doc 29 Vol 2 s5: NATX counts
events "with maximum sound levels reaching or exceeding a threshold"). This module is the arithmetic for one flight
at one point: the noise tables' level for the engine power and distance, corrected for how the engines sit on the
airframe, for sound travelling low over the ground, and for the air's impedance on the day. Nothing in it is a
figure that may be published: scripts/n65_gate.py decides that, and EASA's tables stay out of the repo.

ONLY THE MAXIMUM LEVEL. Doc 29's exposure terms (the duration correction 4-14 and the finite segment correction
4-20) do not apply to LAmax (Vol 2 s4.3.1) and are left out on purpose, not forgotten.

WHAT IS NOT YET HERE, said so it is not mistaken for zero:
- Line-of-sight blockage (optional, 4-8a): left out, as Doc 29 s4.5.8 advises by default (up to 5% smaller
  contours for 5-10 times the computing).
- Bank angle comes in as given; deriving it from a track's turn is the caller's job.

UNITS: metres, degrees, dB. Noise tables arrive in feet, as EASA publishes them, and are converted once by npd_curves().
Held by tests/test_n65_doc29.py against Doc 29 Volume 3's own segment results (its Part 1 workbook, sheet B-2).
"""
from __future__ import annotations

import bisect
import itertools
import math

FT = 0.3048
NPD_MIN_DISTANCE_M = 30.0  # Vol 2 s4.2: "a lower limit of 30 m be imposed on d"
ON_THE_LINE_M = 0.01  # closer than this to a path's line, the observer is on it (geometry(): beta_p)
MIN_POWER = 1.0  # Vol 2 s4.2: a negative power is reset to one pound per engine before extrapolating
GAMMA_FULL_M = 914.0  # 4-19b: past 914 m to the side, the distance factor is 1
BETA_FLAT_DEG = 50.0  # 4-19d: from 50 degrees up, no lateral attenuation
BETA_BELOW_ZERO_DB = 10.857  # Vol 2 s4.5.4: the observer above the aircraft (terrain): Lambda(beta) = 10.857
# 4-15's coefficients (a, b, c), Vol 2 s4.5.3 (5th edition: 0.0039 / 0.062 for wing-mounted, rounded from the 4th's
# 0.00384 / 0.0621; Volume 3's results are reproduced with these). Propeller aircraft: no installation effect (4-16).
INSTALLATION = {'wing': (0.0039, 0.062, 0.8786), 'fuselage': (0.1225, 0.329, 1.0), 'prop': None}
REFERENCE_IMPEDANCE = 409.81  # 4-6: the impedance of the noise tables' reference day, N s / m3
SOR_NORMALISING_M = 762.0  # 4-25: past 762 m (2,500 ft) behind, the start-of-roll directivity fades as 762 / d


# ----------------------------------------------------------------- noise-power-distance tables (Vol 2 s4.2)

def npd_curves(rows):
    """[(power, [(distance_m, level), ...]), ...] sorted, from rows of (power, {distance_ft: level})."""
    out = []
    for power, by_ft in rows:
        pts = sorted((d * FT, level) for d, level in by_ft.items())
        out.append((float(power), pts))
    return sorted(out)


def _level_at(points, d):
    """Level at distance d on one curve: linear in log distance between the two points around d, extrapolated from
    the first two or the last two outside them (4-4, 4-5a, 4-5b)."""
    ds = [p[0] for p in points]
    i = bisect.bisect_left(ds, d)
    i = min(max(i, 1), len(points) - 1)  # the pair (i-1, i) brackets d, or is the end pair to extrapolate from
    (d0, l0), (d1, l1) = points[i - 1], points[i]
    return l0 + (l1 - l0) * (math.log10(d) - math.log10(d0)) / (math.log10(d1) - math.log10(d0))


def npd_level(curves, power, d_m):
    """The table's level for engine power `power` at slant distance `d_m`: linear in power between (or beyond) the two
    nearest tabulated powers (4-3), each read at the distance by _level_at."""
    d = max(d_m, NPD_MIN_DISTANCE_M)
    power = max(power, MIN_POWER)
    powers = [c[0] for c in curves]
    if len(curves) == 1:
        return _level_at(curves[0][1], d)
    i = bisect.bisect_left(powers, power)
    i = min(max(i, 1), len(curves) - 1)
    (p0, c0), (p1, c1) = curves[i - 1], curves[i]
    l0, l1 = _level_at(c0, d), _level_at(c1, d)
    return l0 + (l1 - l0) * (power - p0) / (p1 - p0)


# ----------------------------------------------------------------- corrections (Vol 2 s4.2.1, s4.5)

def impedance_adjustment(temp_c=15.0, pressure_kpa=101.325):
    """4-6 and 4-7: the noise tables' levels adjusted to the air at the aerodrome (0.074 dB on a standard day)."""
    delta = pressure_kpa / 101.325
    theta = (temp_c + 273.15) / (15.0 + 273.15)
    return 10 * math.log10(416.86 * delta / math.sqrt(theta) / REFERENCE_IMPEDANCE)


def installation_correction(phi_deg, mount):
    """4-15: the change in level to the side, by depression angle below the wing plane. Below the wing plane only:
    a negative angle reads as zero (s4.5.3); propeller aircraft have none (4-16)."""
    coeff = INSTALLATION[mount]
    if coeff is None:
        return 0.0
    a, b, c = coeff
    phi = math.radians(max(phi_deg, 0.0))
    return 10 * math.log10((a * math.cos(phi) ** 2 + math.sin(phi) ** 2) ** b
                           / (c * math.sin(2 * phi) ** 2 + math.cos(2 * phi) ** 2))


def lateral_attenuation(beta_deg, lateral_m):
    """4-18 and 4-19: the extra loss of sound reaching a point low and to the side, over soft ground."""
    gamma = 1.089 * (1 - math.exp(-0.00274 * lateral_m)) if lateral_m <= GAMMA_FULL_M else 1.0
    if beta_deg < 0:
        lam = BETA_BELOW_ZERO_DB
    elif beta_deg <= BETA_FLAT_DEG:
        lam = 1.137 - 0.0229 * beta_deg + 9.72 * math.exp(-0.142 * beta_deg)
    else:
        lam = 0.0
    return gamma * lam


def start_of_roll(q_m, d_sor_m, engine):
    """4-22 to 4-25: the extra level BEHIND a take-off ground-roll segment, where jet exhaust noise lobes rearwards.
    `q_m` is negative behind the segment's start; `d_sor_m` the GROUND distance to that start (Volume 3 measures
    both on the ground, ignoring the source's 1 m: straight behind reads exactly 180 degrees, -13.4791 dB, where the
    slant distance gave 179.885 and -13.4854); `engine` 'jet' or 'prop'. Take-off rolls only (s4.5.7)."""
    if q_m >= 0 or d_sor_m <= 0:
        return 0.0
    psi = math.degrees(math.acos(max(-1.0, min(1.0, q_m / d_sor_m))))  # 90 (to the side) to 180 (straight behind)
    psi = min(max(psi, 90.0), 180.0)  # 4-24 is written for 90 <= psi < 180; Volume 3 evaluates it at 180 too
    r = math.radians(psi)
    if engine == 'prop':
        dsor = (-34643.898 + 30722162 / psi - 11491573931 / psi ** 2 + 2.34928567e12 / psi ** 3
                - 2.83584442e14 / psi ** 4 + 2.02271504e16 / psi ** 5 - 7.90084471e17 / psi ** 6
                + 1.30506872e19 / psi ** 7)
    else:
        dsor = (2329.44 - 8.0573 * psi + 11.51 * math.exp(r) - 3.4601 * psi / math.log(r)
                - 17403338.3 * math.log(r) / psi ** 2)
    return dsor if d_sor_m <= SOR_NORMALISING_M else dsor * SOR_NORMALISING_M / d_sor_m


# ----------------------------------------------------------------- geometry (Vol 2 s4.4.1, s4.5.5)

def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def geometry(s1, s2, observer):
    """The segment S1-S2 as seen from the observer, all in metres (Figures 4-2 and 4-6/4-7):
    length; q (S1 to the closest point of the segment's extension, negative behind); d1, d2 (to the ends); dp (to the
    extension, perpendicular); ds (to the segment itself, the LAmax distance); where ('behind', 'alongside', 'ahead');
    lateral (to the ground track, for the attenuation); beta (the elevation of the segment's nearest point, which
    LAmax's attenuation and depression angle use); beta_p (the signed elevation of the extension's closest point,
    which exposure levels use: kept so Volume 3's exposure rows can hold it); side (+1 starboard, -1 port)."""
    seg, rel1 = _sub(s2, s1), _sub(observer, s1)
    length = math.sqrt(_dot(seg, seg))
    u = tuple(x / length for x in seg)
    q = _dot(rel1, u)
    d1 = math.sqrt(_dot(rel1, rel1))
    rel2 = _sub(observer, s2)
    d2 = math.sqrt(_dot(rel2, rel2))
    dp = math.sqrt(max(d1 * d1 - q * q, 0.0))
    where = 'behind' if q < 0 else 'ahead' if q > length else 'alongside'
    ds = d1 if where == 'behind' else d2 if where == 'ahead' else dp
    # The ground track: the segment's horizontal direction; the observer's side of it by the sign of the cross product.
    gx, gy = seg[0], seg[1]
    glen = math.hypot(gx, gy)
    cross = (gx * rel1[1] - gy * rel1[0]) / glen if glen else 0.0
    side = -1 if cross > 0 else 1  # to the left of the direction of flight is port
    lateral_track = abs(cross) if glen else math.hypot(rel1[0], rel1[1])
    # beta_p, the angle SpOC, is measured in the plane normal to the flight path, from its horizontal line (n, square
    # to the ground track) up towards the closest point of approach Sp, and keeps its SIGN: on a descending segment
    # seen from ahead, Sp on the extension lies below the ground and beta_p is negative (Doc 29 Vol 3 reports the
    # depression angle as 0 there, where s4.5.3 reads a negative angle as zero). acos(l / dp) alone lost the sign:
    # 3 dB wrong on 273 of Volume 3's 3,516 rows (28 Oct).
    if not glen:
        beta_p = 90.0  # a vertical segment: straight up or down
    elif dp < ON_THE_LINE_M:
        # The observer on the path's own line, e.g. on the runway centreline behind a take-off roll: the sound comes
        # along the line, not down from it. Volume 3 has ~0.1 degrees at R03; 90 here was 3 dB wrong on 36 rows.
        beta_p = 0.0
    else:
        n = (-gy / glen, gx / glen, 0.0)
        w = (u[1] * n[2] - u[2] * n[1], u[2] * n[0] - u[0] * n[2], u[0] * n[1] - u[1] * n[0])
        if w[2] < 0:
            w = tuple(-x for x in w)
        to_sp = tuple(s + q * k - o for s, k, o in zip(s1, u, observer, strict=True))
        beta_p = math.degrees(math.atan2(_dot(to_sp, w), abs(_dot(to_sp, n))))
    if where == 'alongside':
        lateral, beta = lateral_track, beta_p
    else:
        # Behind or ahead: from the nearest end (s4.5.5, "beta = beta1 = sin-1(z1/d1), l = sqrt(d1^2 - z1^2)").
        end, d_end = (s1, d1) if where == 'behind' else (s2, d2)
        z = end[2] - observer[2]
        lateral = math.sqrt(max(d_end * d_end - z * z, 0.0))
        beta = math.degrees(math.asin(max(-1.0, min(1.0, z / d_end)))) if d_end > 0 else 90.0
    return {'length': length, 'q': q, 'd1': d1, 'd2': d2, 'dp': dp, 'ds': ds, 'where': where,
            'lateral': lateral, 'beta': beta, 'beta_p': beta_p, 'side': side}


def segment_power(p1, p2, g):
    """4-12: the power at the point closest to the observer, changing with the square along the segment; at the nearer
    end when the observer is behind or ahead."""
    if g['where'] == 'behind':
        return p1
    if g['where'] == 'ahead':
        return p2
    return math.sqrt(max(p1 * p1 + g['q'] / g['length'] * (p2 * p2 - p1 * p1), 0.0))


def segment_lmax(s1, s2, p1, p2, observer, curves, mount, bank_deg=0.0, impedance=0.0, takeoff_roll=False):
    """4-8a (4-9a on a take-off roll) without line-of-sight blockage: LAmax from one segment at the observer."""
    g = geometry(s1, s2, observer)
    # The depression angle from the SAME point as the distance and the attenuation: the nearest point of the segment
    # (s4.5.5: for Lmax "only the coordinates of that point are required"). Doc 29 names the extension's closest
    # point only for exposure levels, and Volume 3's exposure rows switch to the end point behind a take-off roll
    # just as LAmax does everywhere (tests/test_n65_doc29.py rebuilds that rule from both angles). A reading where the
    # text is silent: the CAA comparison is what confirms it.
    phi = g['beta'] + g['side'] * bank_deg  # s4.5.2: plus to starboard, minus to port (bank positive left turns)
    # Behind the segment, g['lateral'] is the ground distance to its start (OC1 in Figure 4-7).
    sor = start_of_roll(g['q'], g['lateral'], 'prop' if mount == 'prop' else 'jet') if takeoff_roll else 0.0
    return (npd_level(curves, segment_power(p1, p2, g), g['ds']) + installation_correction(phi, mount)
            - lateral_attenuation(g['beta'], g['lateral']) + sor + impedance)


def event_lmax(path, observer, curves, mount, impedance=0.0):
    """4-10: a flight's LAmax at the observer, the greatest of its segments'. `path` is [(x, y, z, power, bank_deg,
    takeoff_roll)] in metres along the flight, in time order; takeoff_roll True on the take-off ground roll's
    points (the segment starting there gets the start-of-roll directivity), and may be left off (False)."""
    best = -math.inf
    for a, b in itertools.pairwise(path):
        if (a[0], a[1], a[2]) == (b[0], b[1], b[2]):
            continue
        roll = len(a) > 5 and bool(a[5])
        best = max(best, segment_lmax(a[:3], b[:3], a[3], b[3], observer, curves, mount, a[4], impedance, roll))
    return best
