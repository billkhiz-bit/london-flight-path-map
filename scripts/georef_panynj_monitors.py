"""Georeference the Port Authority's monitor maps by their drawn runways (2026-10-16).

The Monthly Noise Monitor Report shows each monitor only as a pin on a map image (the
site table gives a street and town). This places every pin to about 10-120 m. Inputs
are the report images in gitignored data/us-monitors/panynj/ (pypdf extracts them);
the placed positions are checked in, in data/us-noise-monitors.json.

Three ways it went wrong while being built, each now refused, not shipped: Newark's
pink frame read as runways put its monitors in Michigan at a "0.00 px" fit (the fit was
one-directional); LaGuardia's scale moved 9% between two colour thresholds (also
one-directional); and the JFK map's two airports collapsed to one runway cluster. Hence
a SYMMETRIC fit, three thresholds per map, and a per-monitor position spread limit.

Web maps are Mercator, north up and conformal, so pixel = (x0 + s*lon, y0 - s*merc(lat))
with ONE scale s. The FAA's runway thresholds give the real runway lines; s, x0, y0 are
fitted so those lines lie on the map's magenta runway strokes (minimising the mean
distance of points along them to the nearest magenta pixel). Pins are the blue-violet
blobs; each is matched to its site by the label position read from the map.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage, optimize

REPO = str(Path(__file__).resolve().parent.parent)
PROC = json.load(open(f'{REPO}/data/us-flight-procedures.json', encoding='utf-8'))['airports']


def merc(lat):
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def unmerc(y):
    return math.degrees(2 * math.atan(math.exp(math.radians(y))) - math.pi / 2)


def masks(path, tol=(170, 150, 40, 30), groups=1):
    a = np.asarray(Image.open(path).convert('RGB')).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    pin = (r < 140) & (g < 90) & (b > 190)
    rw = (r > tol[0]) & (b > tol[1]) & (np.abs(r - b) < 70) & (r - g > tol[2]) & (b - g > tol[3])
    # The image's own frame is coloured on some maps (Newark's is pink): never a runway.
    m = 14
    for k in (pin, rw):
        k[:m, :] = k[-m:, :] = False
        k[:, :m] = k[:, -m:] = False
    return pin, runway_cluster(rw, groups=groups)


def runway_cluster(rw, link=60, groups=1):
    """Keep the densest group of magenta pieces: the drawn runways. Pieces are joined
    when their centroids are within `link` px; the group with the most pixels wins."""
    lab, n = ndimage.label(rw)
    if n == 0:
        return rw
    idx = range(1, n + 1)
    cent = np.array(ndimage.center_of_mass(rw, lab, idx))
    size = np.array(ndimage.sum(rw, lab, idx))
    group = list(range(n))
    def find(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if np.hypot(*(cent[i] - cent[j])) < link:
                group[find(i)] = find(j)
    roots = np.array([find(i) for i in range(n)])
    top = sorted(set(roots), key=lambda r: -size[roots == r].sum())[:groups]
    keep = [i + 1 for i in range(n) if roots[i] in top]
    return np.isin(lab, keep)


def runway_lines(codes):
    """Each runway as threshold-to-reciprocal-threshold, sampled at 60 points."""
    pts = []
    for code in codes:
        rws = PROC[code]['runways']
        done = set()
        for des, info in rws.items():
            num = int(des[:2])
            side = des[2:]
            recip = f'{(num + 18 - 1) % 36 + 1:02d}' + {'L': 'R', 'R': 'L', 'C': 'C', '': ''}[side]
            if recip not in rws or frozenset((des, recip)) in done:
                continue
            done.add(frozenset((des, recip)))
            (la1, lo1), (la2, lo2) = info['thr'], rws[recip]['thr']
            for t in np.linspace(0, 1, 60):
                pts.append((lo1 + t * (lo2 - lo1), merc(la1 + t * (la2 - la1))))
    return np.array(pts)


def runway_segments(codes):
    """[(lon1, merc1, lon2, merc2)] threshold to reciprocal threshold."""
    segs = []
    for code in codes:
        rws = PROC[code]['runways']
        done = set()
        for des, info in rws.items():
            num, side = int(des[:2]), des[2:]
            recip = f'{(num + 18 - 1) % 36 + 1:02d}' + {'L': 'R', 'R': 'L', 'C': 'C', '': ''}[side]
            if recip not in rws or frozenset((des, recip)) in done:
                continue
            done.add(frozenset((des, recip)))
            (la1, lo1), (la2, lo2) = info['thr'], rws[recip]['thr']
            segs.append((lo1, merc(la1), lo2, merc(la2)))
    return np.array(segs)


def seg_dist(px, py, segs_px):
    """Distance from each pixel to the nearest of the projected segments."""
    best = np.full(px.shape, np.inf)
    for ax, ay, bx, by in segs_px:
        dx, dy = bx - ax, by - ay
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)
        best = np.minimum(best, np.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def calibrate(rw_mask, codes):
    """Fit s, x0, y0 by a SYMMETRIC chamfer: runway points to the nearest magenta pixel
    AND magenta pixels to the nearest runway. One direction alone does not fix the
    scale: any scale that keeps the runways inside the drawn strokes scores zero
    (LaGuardia's scale moved 9% between two colour thresholds that way)."""
    dist = ndimage.distance_transform_edt(~rw_mask)
    lines = runway_lines(codes)
    segs = runway_segments(codes)
    ys, xs = np.nonzero(rw_mask)
    s0 = ((xs.max() - xs.min()) / (lines[:, 0].max() - lines[:, 0].min())
          + (ys.max() - ys.min()) / (lines[:, 1].max() - lines[:, 1].min())) / 2
    x00 = xs.mean() - s0 * lines[:, 0].mean()
    y00 = ys.mean() + s0 * lines[:, 1].mean()

    def parts(p):
        s, x0, y0 = p
        px = x0 + s * lines[:, 0]
        py = y0 - s * lines[:, 1]
        inside = (px >= 0) & (px < dist.shape[1] - 1) & (py >= 0) & (py < dist.shape[0] - 1)
        if inside.mean() < 0.95:
            return 1e6, 1e6
        fwd = ndimage.map_coordinates(dist, [py, px], order=1)
        sp = np.column_stack([x0 + s * segs[:, 0], y0 - s * segs[:, 1], x0 + s * segs[:, 2], y0 - s * segs[:, 3]])
        back = seg_dist(xs.astype(float), ys.astype(float), sp)
        return float(fwd.mean()), float(back.mean())

    def cost(p):
        f, b = parts(p)
        return f + b

    best = None
    for f in (0.8, 0.9, 1.0, 1.1, 1.2):
        res = optimize.minimize(cost, [s0 * f, x00, y00], method='Nelder-Mead',
                                options={'xatol': 1e-4, 'fatol': 1e-5, 'maxiter': 6000})
        if best is None or res.fun < best.fun:
            best = res
    s, x0, y0 = best.x
    fwd, back = parts(best.x)
    px = x0 + s * lines[:, 0]
    py = y0 - s * lines[:, 1]
    p95 = float(np.percentile(ndimage.map_coordinates(dist, [py, px], order=1), 95))
    m_per_px = 111320 * math.cos(math.radians(np.mean([unmerc(v) for v in lines[:, 1]]))) / s
    return (s, x0, y0), fwd, p95, m_per_px, back


def pins(pin_mask, opening=True):
    if opening:  # label text touching a pin falls away; Teterboro's small pins do not survive it
        disc = np.hypot(*np.mgrid[-2:3, -2:3]) <= 2.0
        pin_mask = ndimage.binary_opening(pin_mask, structure=disc)
    lab, n = ndimage.label(pin_mask)
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if 25 <= len(xs) <= 900:
            w, h = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
            if 0.6 <= w / h <= 1.6 and len(xs) / (w * h) > 0.55:
                out.append((xs.mean(), ys.mean(), len(xs)))
    return out


def to_latlon(params, x, y):
    s, x0, y0 = params
    return unmerc((y0 - y) / s), (x - x0) / s


def km(a, b):
    p = math.pi / 180
    x = (b[1] - a[1]) * p * math.cos((a[0] + b[0]) / 2 * p)
    return 6371 * math.hypot(x, (b[0] - a[0]) * p)


def run(image, codes, hints, max_spread_m=150, opening=True):
    """Calibrate at three magenta thresholds and place every pin with each. A monitor
    is accepted when the runways lie on the strokes (forward <= 1 px) and its three
    positions agree within max_spread_m: the scale's uncertainty AT THAT MONITOR."""
    cals = []
    for tol in ((170, 150, 40, 30), (160, 140, 30, 20), (185, 165, 55, 45)):
        pin_mask, rw_mask = masks(image, tol, groups=len(codes))
        cals.append(calibrate(rw_mask, codes))
    params, fwd, _, mpp, back = cals[0]
    found = pins(masks(image)[0], opening)
    print(f'{image.split("/")[-1]} [{",".join(codes)}]: {mpp:.2f} m/px (thresholds give '
          f'{min(c[3] for c in cals):.2f}-{max(c[3] for c in cals):.2f}); runways on magenta '
          f'{max(c[1] for c in cals):.2f} px ({max(c[1] * c[3] for c in cals):.0f} m); {len(found)} pins')
    out, used = {}, set()
    for site, (hx, hy) in hints.items():
        if not found:
            print('  no pins detected')
            break
        j, (px, py, area) = min(enumerate(found), key=lambda t: (t[1][0] - hx) ** 2 + (t[1][1] - hy) ** 2)
        off = math.hypot(px - hx, py - hy)
        if j in used or off > 25:
            print(f'  {site}: NO PIN near the label hint ({hx},{hy}); nearest {off:.0f} px')
            continue
        used.add(j)
        pos = [to_latlon(c[0], px, py) for c in cals]
        spread = max(km(a, b) for a in pos for b in pos) * 1000
        ok = spread <= max_spread_m and max(c[1] * c[3] for c in cals) <= 100  # runways within 100 m of the strokes
        lat, lon = pos[0]
        print(f'  {site:9} -> {lat:.5f}, {lon:.5f}  spread {spread:4.0f} m  {"ok" if ok else "REFUSED"}')
        if ok:
            out[site] = [round(lat, 5), round(lon, 5), round(spread)]
    extra = [f for k, f in enumerate(found) if k not in used]
    if extra:
        print(f'  pins with no site: {[(round(x), round(y)) for x, y, _ in extra]}')
    return out


if __name__ == '__main__':
    which = sys.argv[1]
    hints = json.loads(sys.argv[2])
    codes = sys.argv[3].split(',')
    res = run(f'{REPO}/data/us-monitors/panynj/{which}', codes, hints, opening=len(sys.argv) < 5)
    print(json.dumps(res))
