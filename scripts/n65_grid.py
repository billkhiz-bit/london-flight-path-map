#!/usr/bin/env python3
"""The loudest moment of one flight at MANY places at once: scripts/n65_doc29.py's arithmetic over arrays of observers.

WHY THIS EXISTS (2026-11-03, N65 step 5's first piece)
------------------------------------------------------
Step 5 counts, for one day at Heathrow, every flight's LAmax at every 100 m cell: about 1,300 flights, ~50 segments
each, and ~80,000 cells, so ~5 billion segment-and-receptor evaluations. n65_doc29.segment_lmax() does ONE observer in
pure Python (and is held to ECAC Doc 29 Volume 3's own 3,516 worked rows by tests/test_n65_doc29.py). This module is
the SAME arithmetic, formula by formula, over numpy arrays of observers, and tests/test_n65_grid.py holds it equal to
n65_doc29 on every branch (behind / alongside / ahead, the observer on the path's line, a vertical segment, the
observer above the aircraft, take-off rolls, banked turns, single- and multi-power tables, extrapolation past the
tables), so it inherits ECAC's check rather than needing its own. Nothing here is a figure that may be published:
scripts/n65_gate.py decides that.

ONLY THE MAXIMUM LEVEL, and no line-of-sight blockage, exactly as n65_doc29 (its docstring says why).
UNITS: metres, degrees, dB; `observers` is an (N, 3) array of x, y, z in the same frame as the path.
"""
from __future__ import annotations

import itertools

import n65_doc29 as d29
import numpy as np


def npd_level(curves, power, d_m):
    """n65_doc29.npd_level over arrays: linear in log distance on each curve (4-4, 4-5a/b), linear in power between
    the two bracketing curves (4-3), extrapolating past either end as the scalar does."""
    d = np.maximum(np.asarray(d_m, float), d29.NPD_MIN_DISTANCE_M)
    power = np.maximum(np.broadcast_to(np.asarray(power, float), d.shape), d29.MIN_POWER)
    logd = np.log10(d)

    def level_at(points):
        ds = np.array([p[0] for p in points])
        ls = np.array([p[1] for p in points])
        i = np.clip(np.searchsorted(ds, d, side='left'), 1, len(points) - 1)
        d0, d1, l0, l1 = ds[i - 1], ds[i], ls[i - 1], ls[i]
        return l0 + (l1 - l0) * (logd - np.log10(d0)) / (np.log10(d1) - np.log10(d0))

    if len(curves) == 1:
        return level_at(curves[0][1])
    powers = np.array([c[0] for c in curves])
    levels = np.stack([level_at(c[1]) for c in curves])  # (curves, N)
    i = np.clip(np.searchsorted(powers, power, side='left'), 1, len(curves) - 1)
    cols = np.arange(d.size)
    l0 = levels[i - 1, cols] if d.ndim else levels[i - 1]
    l1 = levels[i, cols] if d.ndim else levels[i]
    p0, p1 = powers[i - 1], powers[i]
    return l0 + (l1 - l0) * (power - p0) / (p1 - p0)


def installation_correction(phi_deg, mount):
    """4-15 over arrays; propeller aircraft have none (4-16)."""
    coeff = d29.INSTALLATION[mount]
    phi_deg = np.asarray(phi_deg, float)
    if coeff is None:
        return np.zeros_like(phi_deg)
    a, b, c = coeff
    phi = np.radians(np.maximum(phi_deg, 0.0))
    return 10 * np.log10((a * np.cos(phi) ** 2 + np.sin(phi) ** 2) ** b / (c * np.sin(2 * phi) ** 2 + np.cos(2 * phi) ** 2))


def lateral_attenuation(beta_deg, lateral_m):
    """4-18 and 4-19 over arrays."""
    beta_deg = np.asarray(beta_deg, float)
    lateral_m = np.asarray(lateral_m, float)
    gamma = np.where(lateral_m <= d29.GAMMA_FULL_M, 1.089 * (1 - np.exp(-0.00274 * lateral_m)), 1.0)
    lam = np.where(beta_deg < 0, d29.BETA_BELOW_ZERO_DB,
                   np.where(beta_deg <= d29.BETA_FLAT_DEG,
                            1.137 - 0.0229 * beta_deg + 9.72 * np.exp(-0.142 * beta_deg), 0.0))
    return gamma * lam


def start_of_roll(q_m, d_sor_m, engine):
    """4-22 to 4-25 over arrays: zero wherever the observer is not behind the roll's start."""
    q = np.asarray(q_m, float)
    dsr = np.asarray(d_sor_m, float)
    live = (q < 0) & (dsr > 0)
    safe = np.where(live, dsr, 1.0)
    psi = np.degrees(np.arccos(np.clip(np.where(live, q, -1.0) / safe, -1.0, 1.0)))
    psi = np.clip(psi, 90.0, 180.0)
    r = np.radians(psi)
    if engine == 'prop':
        dsor = (-34643.898 + 30722162 / psi - 11491573931 / psi ** 2 + 2.34928567e12 / psi ** 3
                - 2.83584442e14 / psi ** 4 + 2.02271504e16 / psi ** 5 - 7.90084471e17 / psi ** 6
                + 1.30506872e19 / psi ** 7)
    else:
        dsor = (2329.44 - 8.0573 * psi + 11.51 * np.exp(r) - 3.4601 * psi / np.log(r)
                - 17403338.3 * np.log(r) / psi ** 2)
    out = np.where(dsr <= d29.SOR_NORMALISING_M, dsor, dsor * d29.SOR_NORMALISING_M / safe)
    return np.where(live, out, 0.0)


def geometry(s1, s2, observers):
    """n65_doc29.geometry for every observer: arrays of q, d1, d2, dp, ds, lateral, beta, side, and where-codes
    (-1 behind, 0 alongside, 1 ahead), plus the scalar length."""
    s1 = np.asarray(s1, float)
    s2 = np.asarray(s2, float)
    obs = np.atleast_2d(np.asarray(observers, float))
    seg = s2 - s1
    length = float(np.sqrt(seg @ seg))
    u = seg / length
    rel1 = obs - s1
    q = rel1 @ u
    d1 = np.sqrt(np.einsum('ij,ij->i', rel1, rel1))
    rel2 = obs - s2
    d2 = np.sqrt(np.einsum('ij,ij->i', rel2, rel2))
    dp = np.sqrt(np.maximum(d1 * d1 - q * q, 0.0))
    where = np.where(q < 0, -1, np.where(q > length, 1, 0))
    ds = np.where(where == -1, d1, np.where(where == 1, d2, dp))
    gx, gy = seg[0], seg[1]
    glen = float(np.hypot(gx, gy))
    if glen:
        cross = (gx * rel1[:, 1] - gy * rel1[:, 0]) / glen
        lateral_track = np.abs(cross)
    else:
        cross = np.zeros(len(obs))
        lateral_track = np.hypot(rel1[:, 0], rel1[:, 1])
    side = np.where(cross > 0, -1, 1)
    if not glen:
        beta_p = np.full(len(obs), 90.0)
    else:
        n = np.array([-gy / glen, gx / glen, 0.0])
        w = np.cross(u, n)
        if w[2] < 0:
            w = -w
        to_sp = s1 + q[:, None] * u - obs
        beta_p = np.degrees(np.arctan2(to_sp @ w, np.abs(to_sp @ n)))
        beta_p = np.where(dp < d29.ON_THE_LINE_M, 0.0, beta_p)
    # Behind or ahead: from the nearest end (s4.5.5).
    end_z = np.where(where == -1, s1[2], s2[2])
    d_end = np.where(where == -1, d1, d2)
    z = end_z - obs[:, 2]
    lat_end = np.sqrt(np.maximum(d_end * d_end - z * z, 0.0))
    with np.errstate(divide='ignore', invalid='ignore'):
        beta_end = np.where(d_end > 0, np.degrees(np.arcsin(np.clip(z / np.where(d_end > 0, d_end, 1.0), -1.0, 1.0))), 90.0)
    lateral = np.where(where == 0, lateral_track, lat_end)
    beta = np.where(where == 0, beta_p, beta_end)
    return {'length': length, 'q': q, 'd1': d1, 'd2': d2, 'dp': dp, 'ds': ds, 'where': where,
            'lateral': lateral, 'beta': beta, 'beta_p': beta_p, 'side': side}


def segment_power(p1, p2, g):
    """4-12 over arrays: at the nearer end behind or ahead, else changing with the square along the segment."""
    along = np.sqrt(np.maximum(p1 * p1 + g['q'] / g['length'] * (p2 * p2 - p1 * p1), 0.0))
    return np.where(g['where'] == -1, p1, np.where(g['where'] == 1, p2, along))


def segment_lmax(s1, s2, p1, p2, observers, curves, mount, bank_deg=0.0, impedance=0.0, takeoff_roll=False):
    """n65_doc29.segment_lmax for every observer (4-8a, 4-9a on a take-off roll; no line-of-sight blockage)."""
    g = geometry(s1, s2, observers)
    phi = g['beta'] + g['side'] * bank_deg
    sor = start_of_roll(g['q'], g['lateral'], 'prop' if mount == 'prop' else 'jet') if takeoff_roll else 0.0
    return (npd_level(curves, segment_power(p1, p2, g), g['ds']) + installation_correction(phi, mount)
            - lateral_attenuation(g['beta'], g['lateral']) + sor + impedance)


def event_lmax(path, observers, curves, mount, impedance=0.0):
    """n65_doc29.event_lmax for every observer (4-10): the greatest of the flight's segments at each."""
    obs = np.atleast_2d(np.asarray(observers, float))
    best = np.full(len(obs), -np.inf)
    for a, b in itertools.pairwise(path):
        if (a[0], a[1], a[2]) == (b[0], b[1], b[2]):
            continue
        roll = len(a) > 5 and bool(a[5])
        np.maximum(best, segment_lmax(a[:3], b[:3], a[3], b[3], obs, curves, mount, a[4], impedance, roll), out=best)
    return best


def count_at_least(levels, threshold_db=65.0):
    """N65 at each observer from a (flights, N) array of LAmax: how many flights reach the threshold (Vol 2 s5,
    "reaching or exceeding")."""
    return (np.asarray(levels) >= threshold_db).sum(axis=0)
