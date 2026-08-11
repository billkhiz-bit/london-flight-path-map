#!/usr/bin/env python3
"""Derive borough-level road-noise and air-quality bands from the source data.

WHY THIS EXISTS
---------------
The three map fill layers - road noise, flood risk, air quality - were curated
for London and New York and ABSENT for the other seven cities. Absent did not
render as absent: `renderDefraTiles()` falls back with `|| 'moderate'` and
`|| 'low'`, so every borough of Greater Manchester, the West Midlands,
Merseyside, both Yorkshires, Tyne and Wear and Bristol was painted a single
confident colour claiming a reading nobody had taken. Measured 2026-08-11: one
distinct fill colour across every borough of all seven, against three for London.

London's own values were no better sourced, only better disguised - a hand-
written `BOROUGH_ROAD_NOISE` literal with no script behind it, the same
editorial shape as the Ofsted bands that Progress 8 replaced.

So this derives BOTH inputs for EVERY city from published sources, the way
build_progress8.py and build_hpi_prices.py already do for schools and prices.

WHAT IT MEASURES, AND WHERE THE THRESHOLDS COME FROM
----------------------------------------------------
Every band boundary is anchored on a published guideline. None is a tertile or
a percentile: a band that is defined relative to the other boroughs cannot say
"all of them are loud", which is the answer that would matter most.

  ROAD NOISE   DEFRA Strategic Noise Mapping Round 4, road Lden, England.
               Banded on the SHARE OF ADDRESSES at or above the WHO 2018
               guideline for road traffic, 53 dB Lden:

                 high      >= 2/3 of postcodes over the WHO guideline
                 moderate  1/2 to 2/3
                 low       < 1/2

               NOT the borough median, which was tried first and measured on
               2026-08-11: medians across UK urban boroughs cluster in 50-60 dB,
               so a 53 dB cut split them near the mode and put 30 of London's 33
               boroughs in one band with `low` never occurring anywhere. That is
               a true number and a useless map - a near-uniform choropleth is the
               exact complaint that started this work.

               Population exposure above a threshold is also the statistic DEFRA
               and WHO themselves report, so this is the conventional measure
               rather than a convenient one. The boundaries are round fractions -
               a half, two-thirds - not percentiles of the cohort: a band defined
               against the other boroughs cannot return "all of them are loud",
               which is the answer that would matter most.

               MEASURED SPREAD across the 77 boroughs with coverage: 31.1% to
               95.6%, median 55.7%. So the middle band holds most boroughs and
               that is a property of the data rather than a flaw in the cut -
               most UK urban boroughs really are alike on road noise, with the
               genuinely quiet outer districts (Rushcliffe 31%, Broxtowe 32%,
               Harrow 39%) and the central-London extremes (Westminster 91%,
               City of London 96%) at the ends. A first attempt at 75%/50% put
               79% of boroughs in one band and is recorded here so it is not
               retried.

               The median is still recorded, as `roadNoiseLdenMedian`, because it
               is what the detail panel can state plainly.

  AIR QUALITY  DEFRA background pollution maps, 1 km grid, 2022 annual means.
               Each borough's mean NO2 and PM2.5 is expressed as a ratio to its
               WHO 2021 guideline (NO2 10, PM2.5 5 ug/m3) and the WORSE of the
               two decides the band - the limiting pollutant, not an average of
               unlike things:

                 excellent  <= 1.0x   meets the WHO guideline
                 good       <= 1.5x
                 moderate   <= 2.5x
                 poor        > 2.5x

WHY POSTCODE CENTROIDS RATHER THAN BOROUGH AREA
------------------------------------------------
An area-weighted median is dominated by whatever is empty. Outer boroughs are
mostly parks, reservoir and farmland, so an area median reports the quiet of
places nobody lives at. Sampling at NSPL postcode centroids weights toward where
addresses actually are, and it is the same idiom load_defra_raster.py uses to
populate the per-postcode table.

FLOOD IS NOT DERIVED HERE. There is no Environment Agency machinery in this repo
yet; `plannedComponents.flood` still says planned. It is left untouched rather
than defaulted, and the renderer no longer invents a value for it.

  pip install rasterio pyproj numpy
  python scripts/build_borough_bands.py                 # report, change nothing
  python scripts/build_borough_bands.py --check         # exit 1 on disagreement
  python scripts/build_borough_bands.py --write         # update borough-extra
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / 'data'
NSPL_CSV = DATA / 'nspl.csv'
NO2_CSV = DATA / 'defra_mapno22022.csv'
PM25_CSV = DATA / 'defra_mappm252022g.csv'
BOROUGH_EXTRA = DATA / 'borough-extra.json'
SCORE_APP = REPO_ROOT / 'backend' / 'lambdas' / 'score' / 'app.py'

# WHO guidelines. These are the anchors; changing one changes the meaning of
# every band below it, so they are named rather than inlined as bare numbers.
WHO_ROAD_LDEN_DB = 53.0  # WHO 2018 Environmental Noise Guidelines, road traffic
WHO_NO2_UGM3 = 10.0  # WHO 2021 global air quality guidelines, annual mean
WHO_PM25_UGM3 = 5.0  # WHO 2021 global air quality guidelines, annual mean
# Share of a borough's addresses at or above the WHO road-traffic guideline.
ROAD_HIGH_SHARE = 200.0 / 3.0  # two-thirds
ROAD_MODERATE_SHARE = 50.0

ROAD_VINTAGE = 'DEFRA Strategic Noise Mapping Round 4 (published 2022), road Lden'
AQ_VINTAGE = 'DEFRA background pollution maps, 2022 annual mean, 1 km grid'

# Wales is not in the England road-noise coverage; Natural Resources Wales
# publishes its own. A city here gets air quality (the DEFRA grid is UK-wide)
# and no road band, rather than a silently empty one.
NO_ROAD_COVERAGE = {'cardiff'}


def load_lad_map():
    """LAD code -> (city, borough), imported from the score Lambda.

    NOT a copy. The Lambda is the single holder of this mapping and a second
    copy here would drift the moment a city is added - which is exactly the
    defect that took six cities off the map on 2026-08-10, two registries where
    one would do.
    """
    spec = importlib.util.spec_from_file_location('score_app_bands', SCORE_APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.LAD_TO_BOROUGH)


def collect_postcodes(lad_map, limit=None):
    """One pass over NSPL: {city: {borough: [(lat, lon), ...]}}.

    One pass, not one per city. The file is 806 MB and re-reading it per city
    would turn a two-minute job into a twenty-minute one for no benefit.
    """
    if not NSPL_CSV.exists():
        raise SystemExit(f'NSPL not found at {NSPL_CSV}')
    out = defaultdict(lambda: defaultdict(list))
    seen = 0
    with NSPL_CSV.open(newline='', encoding='utf-8-sig') as fh:
        for idx, row in enumerate(csv.DictReader(fh)):
            if limit and idx >= limit:
                break
            entry = lad_map.get(row.get('lad25cd', ''))
            if not entry:
                continue
            try:
                lat, lon = float(row['lat']), float(row['long'])
            except (KeyError, ValueError):
                continue
            # NSPL parks terminated/unlocatable postcodes at (99.999, 0.0).
            if lat > 90 or lat < -90:
                continue
            city, borough = entry
            out[city][borough].append((lat, lon))
            seen += 1
    print(f'  {seen:,} postcodes across {len(out)} cities')
    return out


def sample_raster(tif_path, points):
    """Sample a GeoTIFF at (lat, lon) points. Returns a list of valid values.

    Values of 0 or nodata mean 'below the lowest mapped band', which is an
    absence of noise rather than a reading of zero, so they are dropped rather
    than averaged in as silence.
    """
    import numpy as np
    import rasterio
    from pyproj import Transformer

    with rasterio.open(tif_path) as ds:
        band = ds.read(1).astype('float64')
        transform = ds.transform
        nodata = ds.nodata
        crs = ds.crs
        height, width = band.shape

    tr = Transformer.from_crs('EPSG:4326', crs, always_xy=True)
    lons = np.array([p[1] for p in points])
    lats = np.array([p[0] for p in points])
    xs, ys = tr.transform(lons, lats)
    inv = ~transform
    cols, rows = inv * (xs, ys)
    cols = np.floor(cols).astype(int)
    rows = np.floor(rows).astype(int)
    inside = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
    vals = np.full(len(points), np.nan)
    vals[inside] = band[rows[inside], cols[inside]]
    good = np.isfinite(vals) & (vals > 0)
    if nodata is not None:
        good &= vals != nodata
    return vals[good], int(inside.sum())


def load_aq_grid():
    """DEFRA 1 km background grids as {(easting_km, northing_km): value}.

    The published CSVs are British National Grid cell centres at 1 km spacing,
    so flooring a coordinate to the kilometre finds its cell without a spatial
    index.
    """
    grids = {}
    for name, path in (('no2', NO2_CSV), ('pm25', PM25_CSV)):
        if not path.exists():
            raise SystemExit(f'missing {path}')
        cells = {}
        with path.open(newline='', encoding='utf-8-sig') as fh:
            reader = csv.reader(fh)
            header_seen = False
            for row in reader:
                if len(row) < 4:
                    continue
                try:
                    x, y, v = float(row[1]), float(row[2]), float(row[3])
                except ValueError:
                    header_seen = True
                    continue
                cells[(int(x // 1000), int(y // 1000))] = v
        print(f'  {name}: {len(cells):,} cells{"" if header_seen else " (no header row seen)"}')
        grids[name] = cells
    return grids


def sample_aq(grids, points):
    """Mean NO2 and PM2.5 over a borough's postcode centroids."""
    from pyproj import Transformer

    tr = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    sums = {'no2': 0.0, 'pm25': 0.0}
    counts = {'no2': 0, 'pm25': 0}
    for lat, lon in points:
        e, n = tr.transform(lon, lat)
        key = (int(e // 1000), int(n // 1000))
        for k in ('no2', 'pm25'):
            v = grids[k].get(key)
            if v is not None and v >= 0:
                sums[k] += v
                counts[k] += 1
    return {
        k: (sums[k] / counts[k] if counts[k] else None) for k in ('no2', 'pm25')
    }, counts


def road_band(exposed_pct):
    """Band from the share of addresses at or above the WHO guideline."""
    if exposed_pct is None:
        return None
    if exposed_pct >= ROAD_HIGH_SHARE:
        return 'high'
    if exposed_pct >= ROAD_MODERATE_SHARE:
        return 'moderate'
    return 'low'


def aq_band(no2, pm25):
    if no2 is None and pm25 is None:
        return None, None
    ratios = []
    if no2 is not None:
        ratios.append(no2 / WHO_NO2_UGM3)
    if pm25 is not None:
        ratios.append(pm25 / WHO_PM25_UGM3)
    worst = max(ratios)
    if worst <= 1.0:
        return 'excellent', worst
    if worst <= 1.5:
        return 'good', worst
    if worst <= 2.5:
        return 'moderate', worst
    return 'poor', worst


def derive(limit=None):
    """Compute {city: {borough: {...}}} from the published sources."""
    print('loading the borough mapping from the score Lambda...')
    lad_map = load_lad_map()
    print(f'  {len(lad_map)} LAD codes')

    print('scanning NSPL...')
    by_city = collect_postcodes(lad_map, limit=limit)

    print('loading DEFRA air-quality grids...')
    grids = load_aq_grid()

    import numpy as np

    results = {}
    for city in sorted(by_city):
        tif = DATA / f'defra_road_lden_{city}.tif'
        have_road = tif.exists() and city not in NO_ROAD_COVERAGE
        city_out = {}
        for borough, points in sorted(by_city[city].items()):
            rec = {'postcodes': len(points)}

            if have_road:
                vals, inside = sample_raster(tif, points)
                if vals.size:
                    exposed = 100.0 * float((vals >= WHO_ROAD_LDEN_DB).sum()) / vals.size
                    rec['roadNoiseLdenMedian'] = round(float(np.median(vals)), 1)
                    rec['roadNoiseAboveWhoPct'] = round(exposed, 1)
                    rec['roadNoise'] = road_band(exposed)
                    rec['roadNoiseCoverage'] = round(100 * vals.size / len(points), 1)
                    rec['roadNoiseVintage'] = ROAD_VINTAGE

            aq, counts = sample_aq(grids, points)
            band, worst = aq_band(aq['no2'], aq['pm25'])
            if band:
                if aq['no2'] is not None:
                    rec['no2AnnualMeanUgm3'] = round(aq['no2'], 1)
                if aq['pm25'] is not None:
                    rec['pm25AnnualMeanUgm3'] = round(aq['pm25'], 1)
                rec['airQuality'] = band
                rec['airQualityWhoRatio'] = round(worst, 2)
                rec['airQualityVintage'] = AQ_VINTAGE
            city_out[borough] = rec
        results[city] = city_out
    return results


def report(results):
    for city in sorted(results):
        print(f'\n{city}')
        for borough, r in sorted(results[city].items()):
            road = (
                f"{r['roadNoise']:8s} {r['roadNoiseAboveWhoPct']:5.1f}% over WHO "
                f"(med {r['roadNoiseLdenMedian']:4.1f} dB)"
                if 'roadNoise' in r
                else 'NO ROAD DATA                    '
            )
            aq = (
                f"{r['airQuality']:9s} NO2 {r['no2AnnualMeanUgm3']:4.1f} "
                f"PM2.5 {r['pm25AnnualMeanUgm3']:4.1f} ({r['airQualityWhoRatio']:.2f}x WHO)"
                if 'airQuality' in r
                else 'NO AQ DATA'
            )
            print(f'  {borough:28s} {r["postcodes"]:6,d} pc  {road}  {aq}')


DERIVED_KEYS = (
    'roadNoise',
    'roadNoiseLdenMedian',
    'roadNoiseAboveWhoPct',
    'roadNoiseCoverage',
    'roadNoiseVintage',
    'no2AnnualMeanUgm3',
    'pm25AnnualMeanUgm3',
    'airQuality',
    'airQualityWhoRatio',
    'airQualityVintage',
)


def apply_to_extra(results, write):
    """Compare or write the derived values into data/borough-extra.json.

    Returns the number of differences. `--check` uses that as its exit code so
    a drifted holder fails preflight the way prices and Progress 8 already do.
    """
    with BOROUGH_EXTRA.open(encoding='utf-8') as fh:
        extra = json.load(fh)

    diffs = []
    skipped_cities = []
    for city, boroughs in results.items():
        if city not in extra:
            # Cardiff and Nottingham are BACKEND_ONLY_CITIES: scored by the API,
            # deliberately not on the site, so they have no borough-extra entry.
            # Noted, NOT counted as a disagreement - a gate that fails on a
            # deliberate product decision is a gate that gets switched off.
            skipped_cities.append(city)
            continue
        for borough, rec in boroughs.items():
            target = extra[city].get(borough)
            if target is None:
                # Fall back to the SAME containment rule the frontend's
                # getExtraData() uses, so a key the site will successfully look
                # up is the key we write to. London's holder calls Barking and
                # Dagenham 'Barking'; writing an exact-match-only key would put
                # the borough's data somewhere the map never reads.
                lower = borough.lower()
                for key in extra[city]:
                    k = key.lower()
                    if lower == k or lower in k or k in lower:
                        target = extra[city][key]
                        break
            if target is None:
                diffs.append(f'{city}.{borough}: not in borough-extra.json')
                continue
            for key in DERIVED_KEYS:
                new = rec.get(key)
                old = target.get(key)
                if new is None:
                    continue
                if old != new:
                    diffs.append(f'{city}.{borough}.{key}: {old!r} -> {new!r}')
                    if write:
                        target[key] = new

    if skipped_cities:
        print(f'\nnot on the site, skipped: {", ".join(sorted(skipped_cities))}')

    if write and diffs:
        with BOROUGH_EXTRA.open('w', encoding='utf-8', newline='\n') as fh:
            json.dump(extra, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
        print(f'wrote {BOROUGH_EXTRA} ({len(diffs)} field(s) updated)')
    return diffs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true', help='exit 1 if the holder disagrees')
    ap.add_argument('--write', action='store_true', help='update data/borough-extra.json')
    ap.add_argument('--limit', type=int, help='only read N NSPL rows (smoke test)')
    args = ap.parse_args()

    results = derive(limit=args.limit)
    report(results)

    if not (args.check or args.write):
        print('\n(report only; pass --write to update borough-extra.json)')
        return 0

    diffs = apply_to_extra(results, write=args.write)
    if args.check:
        if diffs:
            print(f'\n{len(diffs)} disagreement(s) between borough-extra.json and the sources:')
            for d in diffs[:40]:
                print(f'  {d}')
            if len(diffs) > 40:
                print(f'  ...and {len(diffs) - 40} more')
            return 1
        print('\nborough-extra.json agrees with DEFRA on every derived field.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
