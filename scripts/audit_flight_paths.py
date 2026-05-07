"""
Sky Score, FLIGHT_PATHS audit against DEFRA Lden raster.

For each polyline in index.html's FLIGHT_PATHS, sample 50 points evenly
along the path and look up the Lden value at each point in the DEFRA
Strategic Noise Mapping (Round 4, 2022) GeoTIFF. Report per-path:
  - mean Lden, max Lden, fraction of points >= 55 dB Lden
  - fraction of points outside the raster bbox (i.e. paths drifting
    away from where DEFRA actually publishes contours)
  - flag paths where the path doesn't track real noise

Paths are stored in index.html as JS arrays; rather than parse JS we
mirror them here. Update this file when FLIGHT_PATHS in index.html
changes (intentionally kept in sync, not auto-derived, because
re-running the audit when paths change is the whole point).

Usage:
    python scripts/audit_flight_paths.py

Writes FLIGHT_PATHS_AUDIT.md at project root.
"""

import math
import sys
from pathlib import Path

DEFRA_GEOTIFF_PATH = Path('data/defra_lden_2022.tif')
OUTPUT_PATH = Path('FLIGHT_PATHS_AUDIT.md')
SAMPLES_PER_PATH = 50

# Mirror of index.html FLIGHT_PATHS as of 2026-05-07 (after the trim
# that scoped each polyline to its noise-relevant final-approach /
# initial-departure portion only). Coordinates are [lng, lat] pairs.
# Keep this in sync with index.html when paths change.
FLIGHT_PATHS = [
    {'name': 'Lambourne Stack', 'airport': 'LHR', 'type': 'arrival', 'freq': 'high',
     'coordinates': [[-0.18, 51.52], [-0.25, 51.505], [-0.32, 51.495],
                     [-0.38, 51.485], [-0.428, 51.4775]]},
    {'name': 'Biggin Stack', 'airport': 'LHR', 'type': 'arrival', 'freq': 'high',
     'coordinates': [[-0.22, 51.425], [-0.28, 51.44], [-0.34, 51.45],
                     [-0.39, 51.46], [-0.428, 51.4644]]},
    {'name': 'Ockham Stack', 'airport': 'LHR', 'type': 'arrival', 'freq': 'high',
     'coordinates': [[-0.435, 51.37], [-0.435, 51.40], [-0.435, 51.42],
                     [-0.435, 51.44], [-0.435, 51.4644]]},
    {'name': 'Bovingdon Stack', 'airport': 'LHR', 'type': 'arrival', 'freq': 'high',
     'coordinates': [[-0.49, 51.60], [-0.48, 51.56], [-0.47, 51.53],
                     [-0.46, 51.505], [-0.45, 51.4775]]},
    {'name': 'Dep West', 'airport': 'LHR', 'type': 'departure', 'freq': 'high',
     'coordinates': [[-0.489, 51.4775], [-0.55, 51.48], [-0.62, 51.485], [-0.70, 51.49]]},
    {'name': 'Dep SE (Detling)', 'airport': 'LHR', 'type': 'departure', 'freq': 'medium',
     'coordinates': [[-0.428, 51.4775], [-0.35, 51.47], [-0.25, 51.46], [-0.15, 51.445]]},
    {'name': 'Dep NE (BPK)', 'airport': 'LHR', 'type': 'departure', 'freq': 'medium',
     'coordinates': [[-0.428, 51.4775], [-0.35, 51.49], [-0.25, 51.51], [-0.15, 51.53]]},
    {'name': 'Approach East', 'airport': 'LCY', 'type': 'arrival', 'freq': 'medium',
     'coordinates': [[0.20, 51.48], [0.17, 51.485], [0.14, 51.488], [0.11, 51.492],
                     [0.09, 51.497], [0.07, 51.502], [0.0553, 51.5053]]},
    {'name': 'Approach West', 'airport': 'LCY', 'type': 'arrival', 'freq': 'medium',
     'coordinates': [[-0.02, 51.52], [-0.005, 51.517], [0.01, 51.513], [0.025, 51.51],
                     [0.04, 51.508], [0.0553, 51.5053]]},
    {'name': 'Dep East', 'airport': 'LCY', 'type': 'departure', 'freq': 'medium',
     'coordinates': [[0.067, 51.5053], [0.09, 51.505], [0.12, 51.503], [0.16, 51.498],
                     [0.21, 51.49]]},
    # LGW Approach N + LTN Approach S removed 2026-05-07 after the
    # audit confirmed they sit at altitudes (FL90+) where DEFRA shows
    # zero ground noise. Documented in index.html.
]


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two WGS84 points."""
    R = 6371.0
    p = math.pi / 180
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * (1 - math.cos((lon2 - lon1) * p)) / 2)
    return 2 * R * math.asin(math.sqrt(a))


def sample_polyline(coords_lnglat, n_samples):
    """Yield n_samples points evenly spaced by great-circle distance
    along the polyline. Returns list of [lng, lat]."""
    if len(coords_lnglat) < 2:
        return list(coords_lnglat)
    seg_lengths = []
    for i in range(len(coords_lnglat) - 1):
        a, b = coords_lnglat[i], coords_lnglat[i + 1]
        seg_lengths.append(haversine_km(a[1], a[0], b[1], b[0]))
    total = sum(seg_lengths)
    if total == 0:
        return [coords_lnglat[0]] * n_samples

    out = []
    target_step = total / (n_samples - 1)
    cum_target = 0.0
    seg_idx = 0
    cum_along = 0.0
    for _ in range(n_samples):
        while seg_idx < len(seg_lengths) - 1 and cum_along + seg_lengths[seg_idx] < cum_target:
            cum_along += seg_lengths[seg_idx]
            seg_idx += 1
        seg_len = seg_lengths[seg_idx]
        t = (cum_target - cum_along) / seg_len if seg_len > 0 else 0.0
        a, b = coords_lnglat[seg_idx], coords_lnglat[seg_idx + 1]
        out.append([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
        cum_target += target_step
    return out


def main():
    try:
        import rasterio  # type: ignore
        from pyproj import Transformer  # type: ignore
    except ImportError as exc:
        print(f'Missing dependency: {exc}\nInstall with: pip install rasterio pyproj')
        sys.exit(1)

    if not DEFRA_GEOTIFF_PATH.exists():
        print(f'GeoTIFF not found at {DEFRA_GEOTIFF_PATH}')
        sys.exit(1)

    raster = rasterio.open(DEFRA_GEOTIFF_PATH)
    band = raster.read(1)
    transform = raster.transform
    nodata = raster.nodata
    transformer = Transformer.from_crs('EPSG:4326', raster.crs, always_xy=True)

    print(f'Raster: {band.shape[1]}x{band.shape[0]} pixels, CRS={raster.crs}, '
          f'nodata={nodata}')

    rows = []
    for path in FLIGHT_PATHS:
        samples = sample_polyline(path['coordinates'], SAMPLES_PER_PATH)
        ldens = []
        n_in_bbox = 0
        n_in_contour = 0
        n_above_55 = 0
        for lng, lat in samples:
            x, y = transformer.transform(lng, lat)
            try:
                col, row_idx = ~transform * (x, y)
                col, row_idx = int(col), int(row_idx)
                if 0 <= row_idx < band.shape[0] and 0 <= col < band.shape[1]:
                    n_in_bbox += 1
                    raw = float(band[row_idx, col])
                    is_nodata = (raw > 1e30) or (nodata is not None and raw == nodata)
                    if is_nodata:
                        # Below the 40 dB contour, treat as below-threshold.
                        ldens.append(35.0)
                    elif 30.0 <= raw <= 100.0:
                        n_in_contour += 1
                        ldens.append(raw)
                        if raw >= 55.0:
                            n_above_55 += 1
            except (ValueError, TypeError, OverflowError, IndexError):
                # Audit I-F: specific exceptions only. Skip the sample if
                # the inverse-transform / int() / array index can't be
                # computed; bare except would swallow KeyboardInterrupt
                # and bugs in the call chain.
                pass

        # Total path length (km)
        total_km = sum(
            haversine_km(path['coordinates'][i][1], path['coordinates'][i][0],
                         path['coordinates'][i + 1][1], path['coordinates'][i + 1][0])
            for i in range(len(path['coordinates']) - 1)
        )

        if not ldens:
            mean_lden = 0.0
            max_lden = 0.0
        else:
            mean_lden = sum(ldens) / len(ldens)
            max_lden = max(ldens)

        rows.append({
            'name': path['name'],
            'airport': path['airport'],
            'type': path['type'],
            'freq': path['freq'],
            'length_km': total_km,
            'in_bbox_pct': 100.0 * n_in_bbox / SAMPLES_PER_PATH,
            'in_contour_pct': 100.0 * n_in_contour / SAMPLES_PER_PATH,
            'above_55_pct': 100.0 * n_above_55 / SAMPLES_PER_PATH,
            'mean_lden': mean_lden,
            'max_lden': max_lden,
        })

    raster.close()

    # Write report
    with open(OUTPUT_PATH, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# FLIGHT_PATHS audit vs DEFRA Lden raster\n\n')
        f.write('Generated by `scripts/audit_flight_paths.py` on 2026-05-07. '
                'Each FLIGHT_PATHS polyline in `index.html` is sampled at 50 '
                'evenly-spaced points and looked up in the DEFRA Round 4 (2022) '
                'aircraft Lden GeoTIFF (EPSG:27700, England-only bbox). '
                'Out-of-bbox samples (Scotland / NI / outside England) are '
                'excluded from the dB stats. Pixels below the published 40 dB '
                'contour are coded as 35 dB.\n\n')

        f.write('## Per-path stats\n\n')
        f.write('| Path | Airport | Type | Freq | Length km | % in DEFRA bbox | '
                '% in contour (≥40 dB) | % ≥ 55 dB | Mean Lden | Max Lden |\n')
        f.write('|---|---|---|---|---:|---:|---:|---:|---:|---:|\n')
        for r in rows:
            f.write(f'| {r["name"]} | {r["airport"]} | {r["type"]} | {r["freq"]} | '
                    f'{r["length_km"]:.1f} | {r["in_bbox_pct"]:.0f}% | '
                    f'{r["in_contour_pct"]:.0f}% | {r["above_55_pct"]:.0f}% | '
                    f'{r["mean_lden"]:.1f} | {r["max_lden"]:.1f} |\n')

        # Flag paths that don't track real noise
        f.write('\n## Flags\n\n')
        flagged_low = [r for r in rows if r['mean_lden'] < 50.0]
        flagged_outside = [r for r in rows if r['in_bbox_pct'] < 60.0]
        flagged_no_contour = [r for r in rows
                              if r['in_bbox_pct'] >= 60.0 and r['in_contour_pct'] < 30.0]

        if not (flagged_low or flagged_outside or flagged_no_contour):
            f.write('No paths flagged. Every path tracks real DEFRA noise (mean ≥ 50 dB Lden, '
                    '≥60% in DEFRA bbox, ≥30% inside published contour).\n')
        else:
            if flagged_outside:
                f.write('### Paths drifting outside the DEFRA England bbox\n\n')
                f.write('More than 40% of sampled points fall outside the raster — path geometry '
                        'is wrong, or the path crosses into Scotland / NI / open sea.\n\n')
                for r in flagged_outside:
                    f.write(f'- **{r["name"]}** ({r["airport"]} {r["type"]}): '
                            f'{r["in_bbox_pct"]:.0f}% in bbox, length {r["length_km"]:.1f} km\n')
                f.write('\n')

            if flagged_no_contour:
                f.write('### Paths inside bbox but missing the published noise contour\n\n')
                f.write('Path is in the DEFRA-mapped area but mostly outside the 40 dB contour. '
                        'Either the path is offset from where aircraft actually fly today, or '
                        'this is a high-altitude / low-frequency corridor that DEFRA didn\'t '
                        'flag (acceptable for some en-route paths but worth eyeballing).\n\n')
                for r in flagged_no_contour:
                    f.write(f'- **{r["name"]}** ({r["airport"]} {r["type"]}): '
                            f'{r["in_contour_pct"]:.0f}% inside contour, mean Lden {r["mean_lden"]:.1f}\n')
                f.write('\n')

            if flagged_low:
                f.write('### Paths with mean Lden < 50 dB\n\n')
                f.write('Path doesn\'t track meaningfully noisy zones. Check whether the polyline '
                        'is offset, too long (extending past the noise corridor), or whether '
                        'the airport really doesn\'t generate >50 dB exposure on this route.\n\n')
                for r in flagged_low:
                    f.write(f'- **{r["name"]}** ({r["airport"]} {r["type"]}, freq={r["freq"]}): '
                            f'mean {r["mean_lden"]:.1f} dB Lden, length {r["length_km"]:.1f} km\n')
                f.write('\n')

        f.write('\n## Methodology notes\n\n')
        f.write('- **Sampling:** 50 points evenly spaced along the polyline by great-circle distance.\n')
        f.write('- **CRS:** WGS84 → EPSG:27700 (British National Grid) via pyproj.\n')
        f.write(f'- **NoData / below-threshold pixels:** treated as 35 dB (DEFRA only publishes '
                'contours ≥40 dB Lden; below-threshold = quiet by construction).\n')
        f.write('- **Bbox:** DEFRA Round 4 covers England only. Paths stretching into Scotland / '
                'NI / out to sea will show low % in bbox.\n')
        f.write('- **Reproducibility:** re-run `python scripts/audit_flight_paths.py` after any '
                'change to FLIGHT_PATHS in `index.html` (also update the mirrored copy at the '
                'top of this script).\n')

    print(f'\nWrote {OUTPUT_PATH}')
    print(f'Audited {len(rows)} paths.')
    flagged = sum(1 for r in rows if r['mean_lden'] < 50.0 or r['in_bbox_pct'] < 60.0
                  or (r['in_bbox_pct'] >= 60.0 and r['in_contour_pct'] < 30.0))
    print(f'Flagged: {flagged}')


if __name__ == '__main__':
    main()
