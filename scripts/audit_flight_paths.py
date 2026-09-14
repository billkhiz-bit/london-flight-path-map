"""
Sky Score, FLIGHT_PATHS audit against DEFRA Lden raster.

For each polyline in index.html's FLIGHT_PATHS, sample 50 points evenly
along the path and look up the Lden value at each point in the DEFRA
Strategic Noise Mapping (Round 4, 2022) GeoTIFF. Report per-path:
  - mean Lden, max Lden, fraction of points >= 55 dB Lden
  - fraction of points outside the raster bbox (i.e. paths drifting
    away from where DEFRA actually publishes contours)
  - flag paths where the path doesn't track real noise

The paths are READ FROM THE SCORE LAMBDA (`CITY_GEOMETRY['london']['paths']`,
the holder /v1/score actually scores against), not mirrored. Until
2026-09-14 (audit M27) this file carried a hand copy "as of 2026-05-07":
4-7 waypoints per path against the 11-23 the live geometry has carried
since the 1 km resample of 2026-08-10, so the audit measured corridors
the product had stopped using. The old note said the mirror was kept in
sync deliberately, "because re-running the audit when paths change is the
whole point" - and nothing re-ran it. Reading the holder means the audit
cannot describe a corridor the engine does not have.

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

ROOT = Path(__file__).resolve().parents[1]


def load_flight_paths():
    """London's corridors from the score Lambda, in this file's [lng, lat] shape."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        'score_app_paths', ROOT / 'backend' / 'lambdas' / 'score' / 'app.py'
    )
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    paths = app.CITY_GEOMETRY['london']['paths']
    return [
        {
            'name': pth['name'],
            'airport': pth['airport'],
            'type': pth['type'],
            'coordinates': [[lon, lat] for lat, lon in pth['coords']],
        }
        for pth in paths
    ]


FLIGHT_PATHS = load_flight_paths()


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
            'freq': path.get('freq', ''),
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
        f.write('- **NoData / below-threshold pixels:** treated as 35 dB (DEFRA only publishes '
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
