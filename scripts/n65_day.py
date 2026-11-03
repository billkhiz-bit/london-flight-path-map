#!/usr/bin/env python3
"""N65 for one day at one airport, end to end: N65 step 5 (docs/lessons/n65.md).

WHY THIS EXISTS (2026-11-03)
----------------------------
Every piece of N65 was built and held on its own: the publish rule (n65_gate), one flight's loudest level at one point
(n65_doc29, held to ECAC's 3,516 worked rows) and at many (n65_grid), which ANP aircraft stands for a flight
(n65_types), its default procedure flown for the day's air (n65_profiles, held to ECAC's 26 profile cases), its ADS-B
ground track (n65_tracks) and its 3-D path (n65_path). This joins them for one day: every movement the plane counter
finds (scripts/adsb_movements.py, the counter behind the planes pages) in the CAA's 16-hour day (07:00-23:00 local),
its LAmax at every 100 m cell, and N65 per cell, the number of that day's flights reaching 65 dB LAmax (Doc 29 Vol 2
5-9: "reaching or exceeding"). Then the areas above 50, 100, 200 and 500 events, n65_gate's levels.

EVERY GAP IS SAID, NEVER FILLED. A movement with no type, no ANP candidate, no procedure, no runway, no track or no air
is NOT COMPUTED with its reason, counted, and never given a level. The share computed is reported beside every figure.
The trip length (so the take-off weight) is not in ADS-B: every departure is flown at BOTH the lightest and the heaviest
stage its procedure offers, and the day's N65 is reported as that bracket (n65_path.stages_for), never one picked.

ONE EVENT PER FLIGHT AT A PLACE: the greatest of its segments' levels (Doc 29 4-10). A path that passes a place twice
(Appendix F's u(k)) counts once here, a reading said.

PRUNING, PROVEN EXACT. A segment is evaluated only at cells within the distance where its loudest possible level (the
noise table at either end's power or any tabulated power between, plus the largest installation effect, the largest
start-of-roll directivity on a take-off roll, the day's impedance and the substitution delta; lateral attenuation never
adds) can still reach the threshold, PRUNE_MARGIN_DB below it for safety. A cell reaching the threshold therefore gets
exactly the level the unpruned sum gives (tests/test_n65_day.py holds that, with and without the margin). The
start-of-roll term in the bound is safety only: it can lift a cell by at most 1 dB (jet) or 2 dB (propeller), and only
within 762 m behind a roll segment's start at full strength, where every cell is far inside the reach anyway; at the
reach's edge sound runs along the ground and lateral attenuation takes ~10 dB, so leaving it out moves no cell (both
mutations that drop it survive the tests for that reason, measured 2026-11-03).

NOTHING HERE MAY BE PUBLISHED: scripts/n65_gate.py decides that, and only on EASA's full database. EASA's tables never
enter the repo; the per-flight rows (types, levels) go only to a path OUTSIDE it, and the day's grid only outside it or
to a gitignored folder (refused otherwise).

    python -I -B scripts/n65_day.py day --extract <main clone>/data/adsb/extract/2026-07-15.jsonl.gz --airport LHR \
        --anp <v2.3 tables> --anp <v9 dir> --candidates <subs csv> --candidates <own-data csv> \
        --registry <faa-engines.csv> --operator-engines <airline-engines.csv> --metar-dir <main clone>/data/metar \
        --air data/metar/EGLL-2026-07-air.csv --out <outside the repo> [--workers 4]
    python -I -B scripts/n65_day.py combine --day <west.npz>=0.63 --day <east.npz>=0.37 --out <outside the repo>

Run with the system Python (adsb_movements needs tzdata, numpy and pyproj); `-I -B` keeps it from importing or writing
anything beside the extract. The air file comes from `scripts/fetch_metar.py <month> <month> --airport LHR --air`.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import itertools
import json
import math
import re
import subprocess
import sys
import time
import zoneinfo
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / 'scripts'))
import n65_doc29 as d29  # noqa: E402
import n65_grid as grid  # noqa: E402
import n65_path as pa  # noqa: E402
import n65_profiles as pr  # noqa: E402
import n65_tracks as tr  # noqa: E402
import n65_types as nt  # noqa: E402

THRESHOLD_DB = 65.0
LEVELS = (50, 100, 200, 500)  # n65_gate's Heathrow levels
CELL_M = 100.0
WINDOW_LOCAL = (7, 23)  # the CAA's 16-hour day, 07:00-23:00 local (ERCD 2601)
PRUNE_MARGIN_DB = 0.5
REACH_D_M = np.geomspace(d29.NPD_MIN_DISTANCE_M, 100_000.0, 700)
EXTEND_M = 80_000.0  # tracks run straight on this far past their observed ends (s3.6.6), beyond any grid
AIR_MAX_GAP_S = 2 * 3600  # a movement more than two hours from any weather report has no air
INHG_HPA = 33.8639
# Aerodrome elevation, ft (EGLL AD 2.2, AIRAC 2026-10-29: "83 FT"). Another airport needs its row: refused without.
ELEVATION_FT = {'LHR': 83.0}
OP_OF_KIND = {'take-off': 'D', 'landing': 'A'}
MOUNTS = {'wing': 'wing', 'fuselage': 'fuselage', 'prop': 'prop', 'propeller': 'prop'}

# The largest the installation effect (4-15) and the start-of-roll directivity (4-22 to 4-25) can add, by mount: read
# off the formulas themselves (a bound for pruning, never a level).
_PHI = np.linspace(0.0, 180.0, 36001)
INSTALL_MAX_DB = {m: max(0.0, float(np.max(grid.installation_correction(_PHI, m)))) for m in ('wing', 'fuselage', 'prop')}
_PSI = np.radians(np.linspace(90.0, 180.0, 9001))
SOR_MAX_DB = {e: max(0.0, float(np.max(grid.start_of_roll(-100.0 * np.abs(np.cos(_PSI)) - 1e-9, np.full(_PSI.size, 100.0), e))))
              for e in ('jet', 'prop')}


# ----------------------------------------------------------------- EASA's noise tables (read in place, never kept)


def noise_tables(*dirs: Path) -> dict:
    """{'aircraft': {ACFT_ID: (NPD_ID, mount)}, 'curves': {(NPD_ID, op): n65_doc29.npd_curves(...)}}: LAmax only, every
    tabulated distance. A later release replaces an NPD id's curves whole, as n65_types.load_anp() does. The v9
    workbook heads its lateral directivity column 'Wing' (its first value) instead of 'Lateral Directivity
    Identifier': the column is read by name, else as the one whose every value is a mount (a reading, said)."""
    aircraft, curves = {}, {}
    for d in dirs:
        rows = nt._table(Path(d), 'Aircraft')
        col = next((k for k in rows[0] if k and 'directivity' in k.lower()), None) if rows else None
        if col is None and rows:
            col = next((k for k in rows[0] if k and all(str(r.get(k) or '').strip().lower() in MOUNTS for r in rows)),
                       None)
        for r in rows:
            acft = nt._clean(r.get('ACFT_ID'))
            if not acft:
                continue
            mount = MOUNTS.get(nt._clean(r.get(col)).lower()) if col else None
            aircraft[acft] = (nt._clean(r.get('NPD_ID')), mount)
        fresh: dict = {}
        for r in nt._table(Path(d), 'NPD'):
            if nt._clean(r.get('Noise Metric')).upper() != 'LAMAX':
                continue
            op = nt._clean(r.get('Op Mode')).upper()
            if op not in nt.OPS:
                continue
            levels = {}
            for k, v in r.items():
                m = re.fullmatch(r'L_(\d+)ft', str(k).strip())
                if m and v not in (None, ''):
                    levels[float(m.group(1))] = float(v)
            fresh.setdefault((nt._clean(r['NPD_ID']), op), []).append((float(r['Power Setting']), levels))
        curves.update({k: d29.npd_curves(v) for k, v in fresh.items()})
    return {'aircraft': aircraft, 'curves': curves}


# ----------------------------------------------------------------- the grid and one flight's levels on it


class Grid:
    """Square cells of `cell` metres in British National Grid, `nx` by `ny` from the corner (x0, y0); observers at
    each cell's centre on the aerodrome's ground plane (z = 0: Doc 29's nominal ground plane, terrain not modelled)."""

    def __init__(self, x0: float, y0: float, nx: int, ny: int, cell: float = CELL_M):
        self.x0, self.y0, self.nx, self.ny, self.cell = x0, y0, nx, ny, cell
        self.xc = x0 + cell * (np.arange(nx) + 0.5)
        self.yc = y0 + cell * (np.arange(ny) + 0.5)

    @classmethod
    def around(cls, x: float, y: float, half_x_m: float, half_y_m: float, cell: float = CELL_M):
        nx, ny = int(round(2 * half_x_m / cell)), int(round(2 * half_y_m / cell))
        return cls(round((x - half_x_m) / cell) * cell, round((y - half_y_m) / cell) * cell, nx, ny, cell)

    @property
    def size(self) -> int:
        return self.nx * self.ny

    def near(self, a, b, radius: float) -> tuple[np.ndarray, np.ndarray]:
        """(flat cell indices, their observers (n, 3)) within `radius` of segment a-b's ground projection."""
        lo_x, hi_x = min(a[0], b[0]) - radius, max(a[0], b[0]) + radius
        lo_y, hi_y = min(a[1], b[1]) - radius, max(a[1], b[1]) + radius
        i0 = max(int(math.floor((lo_x - self.x0) / self.cell)), 0)
        i1 = min(int(math.ceil((hi_x - self.x0) / self.cell)), self.nx)
        j0 = max(int(math.floor((lo_y - self.y0) / self.cell)), 0)
        j1 = min(int(math.ceil((hi_y - self.y0) / self.cell)), self.ny)
        if i0 >= i1 or j0 >= j1:
            return np.empty(0, np.int64), np.empty((0, 3))
        xs, ys = np.meshgrid(self.xc[i0:i1], self.yc[j0:j1])
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = np.clip(((xs - ax) * dx + (ys - ay) * dy) / length2, 0.0, 1.0) if length2 else np.zeros_like(xs)
        dist2 = (xs - (ax + t * dx)) ** 2 + (ys - (ay + t * dy)) ** 2
        keep = dist2 <= radius * radius
        jj, ii = np.nonzero(keep)
        flat = (jj + j0) * self.nx + (ii + i0)
        obs = np.column_stack([xs[keep], ys[keep], np.zeros(int(keep.sum()))])
        return flat.astype(np.int64), obs


def reach_m(curves, p_lo: float, p_hi: float, extra_db: float, threshold_db: float) -> float:
    """The slant distance (m) beyond which a segment powered between p_lo and p_hi cannot reach threshold_db, with
    `extra_db` the most every correction can add: the noise table's level at either power and at every tabulated power
    between (the level is piecewise linear in power, so its greatest is at one of them), the next distance on
    REACH_D_M past the last that reaches it (PRUNE_MARGIN_DB short of it), inf if even 100 km does."""
    powers = [p_lo, p_hi, *(c[0] for c in curves if p_lo < c[0] < p_hi)]
    level = np.max([grid.npd_level(curves, p, REACH_D_M) for p in powers], axis=0) + extra_db
    hits = np.nonzero(level >= threshold_db - PRUNE_MARGIN_DB)[0]
    if not hits.size:
        return 0.0
    return math.inf if hits[-1] + 1 >= REACH_D_M.size else float(REACH_D_M[hits[-1] + 1])


def flight_levels(path, g: Grid, curves, mount: str, adjust_db: float, threshold_db: float) -> np.ndarray:
    """One flight's LAmax at every cell of `g` that one of its segments could bring to `threshold_db`, -inf elsewhere
    (n65_grid.segment_lmax, the greatest over segments, 4-10). `adjust_db` is added to every level: the day's impedance
    (4-6) plus the substitution delta. Exact where it matters: see the module's docstring."""
    out = np.full(g.size, -np.inf)
    engine = 'prop' if mount == 'prop' else 'jet'
    for a, b in itertools.pairwise(path):
        if (a[0], a[1], a[2]) == (b[0], b[1], b[2]):
            continue
        roll = len(a) > 5 and bool(a[5])
        extra = adjust_db + INSTALL_MAX_DB[mount] + (SOR_MAX_DB[engine] if roll else 0.0)
        r = reach_m(curves, min(a[3], b[3]), max(a[3], b[3]), extra, threshold_db)
        z_min = min(a[2], b[2])
        if r <= z_min:
            continue  # every point of the segment is at least z_min away from the ground
        flat, obs = g.near(a, b, math.sqrt(r * r - z_min * z_min) if math.isfinite(r) else 1e9)
        if not flat.size:
            continue
        lv = grid.segment_lmax(a[:3], b[:3], a[3], b[3], obs, curves, mount, a[4], adjust_db, roll)
        out[flat] = np.maximum(out[flat], lv)
    return out


def areas_km2(counts: np.ndarray, cell: float = CELL_M, levels=LEVELS) -> dict:
    """{events: km2 of cells whose count reaches it}: the area inside each N65 contour, at the grid's resolution."""
    return {k: float((counts >= k).sum()) * cell * cell / 1e6 for k in levels}


# ----------------------------------------------------------------- the day's air


def read_air(path: Path) -> list[tuple]:
    """[(epoch_s, temp_c, qnh_hpa, wind_from_deg or None, wind_kt or None)] from fetch_metar.py --air's file, in time
    order."""
    out = []
    with open(path, encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh):
            t = dt.datetime.strptime(r['valid'], '%Y-%m-%d %H:%M').replace(tzinfo=dt.UTC).timestamp()
            drct = float(r['drct']) if r['drct'] else None
            sknt = float(r['sknt']) if r['sknt'] else None
            out.append((t, (float(r['tmpf']) - 32) * 5 / 9, float(r['alti']) * INHG_HPA, drct, sknt))
    return sorted(out)


def air_at(rows: list[tuple], t: float) -> tuple | None:
    """(temp_c, qnh_hpa, wind_from_deg or None, wind_kt or None) at time t: temperature and QNH linear between the
    reports either side, the wind the nearest report's; None when no report lies within AIR_MAX_GAP_S."""
    if not rows:
        return None
    ts = [r[0] for r in rows]
    i = bisect.bisect_left(ts, t)
    near = min((k for k in (i - 1, i) if 0 <= k < len(rows)), key=lambda k: abs(ts[k] - t))
    if abs(ts[near] - t) > AIR_MAX_GAP_S:
        return None
    if 0 < i < len(rows) and ts[i] > ts[i - 1]:
        f = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
        temp = rows[i - 1][1] + f * (rows[i][1] - rows[i - 1][1])
        qnh = rows[i - 1][2] + f * (rows[i][2] - rows[i - 1][2])
    else:
        temp, qnh = rows[near][1], rows[near][2]
    return temp, qnh, rows[near][3], rows[near][4]


def headwind_for(air: tuple, rw: tr.Runway) -> tuple[float, str]:
    """(headwind kt along the runway, how): from the wind's direction and speed; a calm wind is 0; a speed with no
    direction (a variable wind) is 0, said; no speed at all is ANP's reference 8 kt, said."""
    _temp, _qnh, wind_from, wind_kt = air
    if wind_kt is None:
        return pr.REFERENCE_HEADWIND_KT, 'wind-missing-reference-8kt'
    if wind_kt == 0:
        return 0.0, 'calm'
    if wind_from is None:
        return 0.0, 'wind-variable-0kt'
    return pa.headwind_kt(wind_from, wind_kt, rw.true_bearing), 'metar'


# ----------------------------------------------------------------- one day


def _safe_out(path: Path) -> bool:
    """Outside the repo, or a path git ignores inside it (the day's grid is EASA-derived)."""
    try:
        path.resolve().relative_to(REPO.resolve())
    except ValueError:
        return True
    r = subprocess.run(['git', '-C', str(REPO), 'check-ignore', '-q', str(path)],  # noqa: S603, S607  (fixed git call)
                       capture_output=True)
    return r.returncode == 0


def _outside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO.resolve())
        return False
    except ValueError:
        return True


_W: dict = {}  # each worker's loaded tables


def _init_worker(cfg: dict):
    import adsb_movements as am  # noqa: F401  (imports tzdata, pyproj in the worker)

    _W['cfg'] = cfg
    _W['profiles'] = pr.load_anp(*map(Path, cfg['anp']))
    _W['noise'] = noise_tables(*map(Path, cfg['anp']))
    _W['grid'] = Grid(*cfg['grid'])
    _W['air'] = read_air(Path(cfg['air']))
    _W['runways'] = {d: tr.Runway(**r) for d, r in cfg['runways'].items()}


def _fly(job: dict) -> dict:
    """One movement's levels on the grid, as {'row': ..., 'reached': {label: flat cells reaching the threshold}}."""
    cfg, g = _W['cfg'], _W['grid']
    db, noise, runways = _W['profiles'], _W['noise'], _W['runways']
    row = {k: job[k] for k in ('time', 'op', 'icao', 'how', 'anp_id', 'airline')}
    reached: dict = {}

    def stop(reason):
        row['not_computed'] = reason
        return {'row': row, 'reached': reached}

    acft, op = job['anp_id'], job['op']
    rw = runways.get(job['runway'])
    if rw is None:
        return stop('runway-unknown')
    row['runway'] = rw.designator
    air = air_at(_W['air'], job['time'])
    if air is None:
        return stop('no-air')
    headwind, row['wind'] = headwind_for(air, rw)
    temp_c, qnh_hpa = air[0], air[1]
    elev_ft = cfg['elevation_ft']
    atm = pr.Atmosphere(elev_ft, temp_c, qnh_hpa / INHG_HPA, headwind)
    impedance = d29.impedance_adjustment(temp_c, pa.pressure_kpa(qnh_hpa, elev_ft * pa.FT))
    npd_id, mount = noise['aircraft'].get(acft, (None, None))
    curves = noise['curves'].get((npd_id, op)) if npd_id else None
    if not curves or mount is None:
        return stop('no-noise-table')
    available = pr.available(db, acft, op)
    proc = pa.procedure_for(available, op)
    if proc is None:
        return stop('no-procedure')
    source, pid = proc
    row['procedure'] = f'{source}:{pid}'
    if op == 'D':
        have = {s for src, p, s in available if src == source and p == pid}
        perf = db.performance.get(acft)
        stages = pa.stages_for(have, perf.weights if perf else {}, None)
    else:
        stages = [('approach', '1')]
    perf = db.performance.get(acft)

    def power(thrust):
        return pr.npd_power(perf, thrust) if source == 'steps' else thrust

    pts = [tr.Pt(*p) for p in job['pts']]
    profiles = {}  # by stage: the light and heavy sides of a one-stage aircraft are one profile
    for _label, stage in stages:
        if stage in profiles:
            continue
        try:
            profiles[stage] = pr.profile(db, acft, op, pid, stage, atm)[0]
        except (KeyError, ValueError) as e:
            return stop(f'profile-failed: {type(e).__name__}')
    if op == 'D':
        track, how_track = tr.departure_track(pts, rw, job['ts_runway'])
    else:
        roll_m = profiles['1'][-1].distance_ft * pa.FT
        track, how_track = tr.approach_track(pts, rw, job['ts_runway'], roll_m=roll_m)
    if track is None:
        return stop(how_track)
    row['track'] = how_track
    banked, capped = tr.bank_angles(track)
    row['bank_capped'] = capped
    nodes = tr.extend(banked, 0.0 if op == 'D' else EXTEND_M, EXTEND_M if op == 'D' else 0.0)
    done = {}
    for label, stage in stages:
        row[f'stage_{label}'] = stage
        if stage not in done:
            sub, lift = pa.subsegment(profiles[stage], op)
            try:
                path = pa.merge(sub, nodes, op, lift, power)
            except ValueError as e:
                return stop(f'path-failed: {e}')
            lv = flight_levels(path, g, curves, mount, impedance + job['delta'], THRESHOLD_DB)
            done[stage] = np.nonzero(lv >= THRESHOLD_DB)[0].astype(np.int32)
            top = float(np.max(lv))
            row[f'max_db_{label}'] = round(top, 2) if math.isfinite(top) else None
            if label in ('approach', 'light'):
                row.update(_height_check(track, sub, op))
        reached[label] = done[stage]
    return {'row': row, 'reached': reached}


HEIGHT_BANDS_KM = ((3, 6), (6, 12), (12, 25))


def _height_check(track, profile_pts, op) -> dict:
    """The observed height above the field minus the profile's, median per distance band (km from the start of roll,
    or to touchdown): how far the default profile sits from what this flight flew. A diagnostic, never an input."""
    out = {}
    for lo, hi in HEIGHT_BANDS_KM:
        diffs = []
        for s, _x, _y, _gs, h in track:
            d = s / 1000 if op == 'D' else -s / 1000
            if h is not None and lo <= d < hi:
                diffs.append(h - pr.interpolate(profile_pts, s / pa.FT)[0] * pa.FT)
        out[f'dz_{lo}_{hi}km'] = round(float(np.median(diffs)), 1) if diffs else None
    return out


def runway_geometry(ap_json: dict, to_grid) -> dict:
    """{designator: Runway kwargs} in grid metres from the procedure file's thresholds and TRUE bearings (each turned
    onto the grid by projecting a point 1 km along it: grid north is ~1.2 degrees off true at Heathrow)."""
    import pyproj

    geod = pyproj.Geod(ellps='WGS84')
    out = {}
    for des, r in ap_json['runways'].items():
        lat, lon = r['thr']
        x, y = to_grid(lon, lat)
        lon2, lat2, _ = geod.fwd(lon, lat, r['true_brg'], 1000.0)
        x2, y2 = to_grid(lon2, lat2)
        d = math.hypot(x2 - x, y2 - y)
        out[des] = {'designator': des, 'threshold': (x, y), 'direction': ((x2 - x) / d, (y2 - y) / d),
                    'length_m': 0.0, 'true_bearing': r['true_brg'], 'glide_deg': r.get('glide_deg', 3.0)}
    for des, r in out.items():
        other = out.get(tr.reciprocal(des))
        if other:
            r['length_m'] = math.dist(r['threshold'], other['threshold'])
    return out


def day(a) -> int:
    import adsb_movements as am
    import adsb_overflights as ao
    import n65_type_mix as tm
    import pyproj

    out = Path(a.out)
    if not _safe_out(out):
        print(f'REFUSED: --out {out} is a tracked place in the repo; the day grid is EASA-derived')
        return 2
    if a.flights_out and not _outside_repo(Path(a.flights_out)):
        print(f'REFUSED: --flights-out {a.flights_out} is inside the repo; per-flight rows are EASA-derived')
        return 2
    if a.airport not in ELEVATION_FT:
        print(f'REFUSED: no aerodrome elevation for {a.airport} (add its AD 2.2 figure to ELEVATION_FT)')
        return 2
    if a.metar_dir:
        am.METAR_DIR = Path(a.metar_dir)
    t0 = time.time()
    ap = am.load_airports()[a.airport]
    ap_json = json.loads(am.PROCEDURE_FILES[0].read_text(encoding='utf-8'))['airports'][a.airport]
    to_grid = pyproj.Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True).transform
    runways = runway_geometry(ap_json, to_grid)
    rw_objects = {d: tr.Runway(**r) for d, r in runways.items()}
    cx, cy = to_grid(ap['centre'][1], ap['centre'][0])
    g = Grid.around(cx, cy, a.half_x_km * 1000, a.half_y_km * 1000, a.cell)
    anp_types = nt.load_anp(*a.anp)
    cands = nt.index_candidates(*(nt.read_candidates(p) for p in a.candidates))
    registry = tm.read_registry(a.registry)
    operator_engines = nt.read_operator_engines(a.operator_engines) if a.operator_engines else {}
    traces = tm.near_traces(Path(a.extract), ap)
    field, how_field = am.field_level(traces, ap)
    if field is None:
        print(f'REFUSED: no field level ({how_field})')
        return 2
    zone = zoneinfo.ZoneInfo('Europe/London')
    elev_ft = ELEVATION_FT[a.airport]
    geoid_ft = ao.GEOID_M[a.airport] / pa.FT
    jobs, outside, by_how = [], 0, Counter()
    for rec in traces:
        moves, _ = am.movements(rec, ap, field)
        if not moves:
            continue
        pts = []
        for p in rec['pts']:
            x, y = to_grid(p[2], p[1])
            ground = p[3] == 'ground'
            if ground:
                h = 0.0
            elif isinstance(p[4], (int, float)):
                h = (p[4] - geoid_ft - elev_ft) * pa.FT
            elif isinstance(p[3], (int, float)):
                h = (p[3] - am.field_at(field, p[0])) * pa.FT
            else:
                h = None
            pts.append((p[0], x, y, ground, p[5] if isinstance(p[5], (int, float)) else None, h))
        airline = tm.airline_of(rec)
        for kind, rw_name, ts in moves:
            op = OP_OF_KIND.get(kind)
            if op is None:
                continue
            hour = dt.datetime.fromtimestamp(ts, zone).hour
            if not WINDOW_LOCAL[0] <= hour < WINDOW_LOCAL[1]:
                outside += 1
                continue
            res = nt.resolve(rec.get('t') or '', rec.get('r') or '', op, cands, anp_types, registry, airline,
                             operator_engines)
            by_how[res.how] += 1
            if rw_name not in runways:
                window = (ts - 120, ts + 60) if op == 'D' else (ts - 60, ts + 120)
                rw_name = tr.runway_from_points([tr.Pt(*p) for p in pts], rw_objects, *window)
            jobs.append({'time': ts, 'ts_runway': ts, 'op': op, 'icao': res.icao, 'how': res.how, 'airline': airline,
                         'anp_id': res.candidate.anp_id if res.candidate else None,
                         'delta': res.candidate.delta(op) if res.candidate else 0.0,
                         'runway': rw_name, 'pts': pts})
    if a.limit:
        jobs = jobs[: a.limit]
    print(f'{a.airport} {Path(a.extract).name}: field {float(field):.0f} ft ({how_field}); {len(traces)} traces; '
          f'{len(jobs)} movements 07:00-23:00 local ({outside} outside); read in {time.time() - t0:.0f} s')
    cfg = {'anp': [str(p) for p in a.anp], 'grid': (g.x0, g.y0, g.nx, g.ny, g.cell), 'air': str(a.air),
           'runways': runways, 'elevation_ft': elev_ft}
    labels = ('light', 'heavy')
    counts = {'arrivals': np.zeros(g.size, np.int32), 'departures_light': np.zeros(g.size, np.int32),
              'departures_heavy': np.zeros(g.size, np.int32)}
    rows, reasons = [], Counter()
    typed = [j for j in jobs if j['anp_id']]
    for j in jobs:
        if not j['anp_id']:
            rows.append({**{k: j[k] for k in ('time', 'op', 'icao', 'how', 'anp_id', 'airline')},
                         'not_computed': j['how']})
            reasons[(j['op'], j['how'])] += 1
    t1 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init_worker, initargs=(cfg,)) as ex:
        for k, res in enumerate(ex.map(_fly, typed, chunksize=4), 1):
            row = res['row']
            rows.append(row)
            if 'not_computed' in row:
                reasons[(row['op'], row['not_computed'].split(':')[0])] += 1
                continue
            if row['op'] == 'A':
                counts['arrivals'][res['reached']['approach']] += 1
            else:
                for label in labels:
                    counts[f'departures_{label}'][res['reached'][label]] += 1
            if k % 100 == 0:
                print(f'  {k}/{len(typed)} flown, {time.time() - t1:.0f} s')
    computed = sum(1 for r in rows if 'not_computed' not in r)
    n65 = {label: counts['arrivals'] + counts[f'departures_{label}'] for label in labels}
    summary = {
        'airport': a.airport, 'day': Path(a.extract).name.split('.')[0], 'window_local': '07:00-23:00',
        'threshold_db': THRESHOLD_DB, 'cell_m': g.cell, 'grid': {'x0': g.x0, 'y0': g.y0, 'nx': g.nx, 'ny': g.ny},
        'field': {'pressure_altitude_ft': round(float(field)), 'how': how_field},
        'movements': len(jobs), 'outside_window': outside, 'computed': computed,
        'computed_share': round(computed / len(jobs), 4) if jobs else None,
        'by_op': {op: {'movements': sum(1 for j in jobs if j['op'] == op),
                       'computed': sum(1 for r in rows if r['op'] == op and 'not_computed' not in r)} for op in 'AD'},
        'type_how': dict(by_how),
        'not_computed': {f'{op} {why}': n for (op, why), n in sorted(reasons.items())},
        'tracks': dict(Counter(r.get('track') for r in rows if r.get('track'))),
        'winds': dict(Counter(r.get('wind') for r in rows if r.get('wind'))),
        'bank_capped_nodes': sum(r.get('bank_capped', 0) for r in rows),
        'areas_km2': {label: areas_km2(n65[label], g.cell) for label in labels},
        'max_n65': {label: int(n65[label].max()) for label in labels},
        'height_check_m': {op: {band: _median([r.get(band) for r in rows if r['op'] == op]) for band in
                                (f'dz_{lo}_{hi}km' for lo, hi in HEIGHT_BANDS_KM)} for op in 'AD'},
        'database': 'easa-anp-2.3+v9 (a building run; n65_gate decides only on the full database)',
        'seconds': round(time.time() - t0),
    }
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{a.airport}-{summary['day']}"
    np.savez_compressed(out / f'{stem}-n65.npz', meta=json.dumps(summary), **counts)
    (out / f'{stem}-summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    if a.flights_out:
        keys = sorted({k for r in rows for k in r})
        with open(a.flights_out, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, keys)
            w.writeheader()
            w.writerows(rows)
    print(json.dumps({k: summary[k] for k in ('movements', 'computed', 'computed_share', 'not_computed',
                                              'areas_km2', 'max_n65', 'height_check_m', 'seconds')}, indent=1))
    return 0


def _median(values):
    vals = [v for v in values if v is not None]
    return round(float(np.median(vals)), 1) if vals else None


def combine(a) -> int:
    """A weighted average of day grids (e.g. a westerly and an easterly day by the CAA's modal split), per bracket
    side, and its areas: a SHAPE and order-of-magnitude comparison with an annual average, never a like-for-like one."""
    out = Path(a.out)
    if not _safe_out(out):
        print(f'REFUSED: --out {out} is a tracked place in the repo')
        return 2
    days, weights, metas = [], [], []
    for spec in a.day:
        path, w = spec.rsplit('=', 1)
        with np.load(path, allow_pickle=False) as z:
            days.append({k: z[k] for k in z.files if k != 'meta'})
            metas.append(json.loads(str(z['meta'])))
        weights.append(float(w))
    if len({json.dumps(m['grid'], sort_keys=True) for m in metas}) != 1:
        print('REFUSED: the days are on different grids')
        return 2
    cell = metas[0]['cell_m']
    result = {'days': [{'day': m['day'], 'weight': w, 'computed_share': m['computed_share'],
                        'movements': m['movements']} for m, w in zip(metas, weights, strict=True)]}
    for label in ('light', 'heavy'):
        avg = sum(w * (d['arrivals'] + d[f'departures_{label}']) for d, w in zip(days, weights, strict=True))
        result[label] = areas_km2(avg, cell)
    out.mkdir(parents=True, exist_ok=True)
    name = '+'.join(m['day'] for m in metas)
    (out / f'combined-{name}.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
    print(json.dumps(result, indent=1))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('day')
    d.add_argument('--extract', required=True)
    d.add_argument('--airport', default='LHR')
    d.add_argument('--anp', type=Path, action='append', required=True, help='ANP release dir; later ones win')
    d.add_argument('--candidates', type=Path, action='append', required=True)
    d.add_argument('--registry', type=Path)
    d.add_argument('--operator-engines', type=Path)
    d.add_argument('--metar-dir', help="the counter's QNH cache, for the field level (default the repo's data/metar)")
    d.add_argument('--air', type=Path, required=True, help="fetch_metar.py --air's file for the day's month")
    d.add_argument('--out', required=True)
    d.add_argument('--flights-out', help='per-flight rows (EASA-derived): a path outside the repo')
    d.add_argument('--half-x-km', type=float, default=32.0)
    d.add_argument('--half-y-km', type=float, default=18.0)
    d.add_argument('--cell', type=float, default=CELL_M)
    d.add_argument('--workers', type=int, default=4)
    d.add_argument('--limit', type=int, default=0, help='only the first N movements (a trial)')
    c = sub.add_parser('combine')
    c.add_argument('--day', action='append', required=True, help='<day npz>=<weight>')
    c.add_argument('--out', required=True)
    a = p.parse_args(argv)
    return day(a) if a.cmd == 'day' else combine(a)


if __name__ == '__main__':
    raise SystemExit(main())
