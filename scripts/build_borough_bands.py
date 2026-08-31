#!/usr/bin/env python3
"""Derive borough-level road-noise, air-quality and flood-risk bands.

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

So this derives ALL THREE for EVERY city from published sources, the way
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

  TRANSPORT    NaPTAN, the DfT national public transport access node register.
               Banded on the SHARE OF ADDRESSES within 800 m of a rail, metro
               or tram access node - 800 m being the standard ten-minute-walk
               planning threshold:

                 excellent  >= 3/4 of postcodes within 800 m
                 good       >= 1/2
                 moderate   >= 1/4
                 poor       <  1/4

               RAIL/METRO/TRAM ONLY, NOT BUS, and that is the load-bearing
               choice. 416,539 of NaPTAN's 435,298 nodes are bus stops; include
               them and essentially every urban postcode is within 800 m of one,
               which measures nothing. This is accessibility to the HIGH-CAPACITY
               network and must be described as that. It is NOT PTAL, which is
               an all-modes, London-only calculation that cannot be reproduced
               for the other cities - using the PTAL name for this would be the
               same overclaim as calling an estimate a DEFRA sample.

               MEASURED SPREAD across all 81 boroughs: 9.5% (Coventry) to 100%,
               median 49.8%. The quarter boundaries are round fractions of
               addresses chosen for being sayable in words, not percentiles; on
               this cohort they happen to split it fairly evenly, which is a
               property of this cohort and not the definition.

  HEALTHCARE   NHS Organisation Data Service, active GP practices and branch
               surgeries. Banded on the SHARE OF ADDRESSES within 500 m of one:

                 excellent  >= 3/4 of postcodes within 500 m
                 good       >= 1/2
                 moderate   <  1/2

               Only three bands because HEALTH_SCORE has three; there is no
               `poor` tier to assign.

               500 m rather than the 800 m used for transport, and the reason is
               measured rather than aesthetic: surgeries are dense enough that a
               1 km radius put 68 of 81 boroughs in `excellent` and none in
               `moderate`. Branch surgeries are included, because the question
               is whether a resident can reach a GP and a branch is a place you
               can attend.

  FLOOD RISK   Environment Agency Risk of Flooding from Rivers and Sea (NAFRA2),
               fetched by scripts/fetch_ea_flood_risk.py. Banded on the SHARE OF
               ADDRESSES at Medium or High risk - that is the 1%-annual-chance
               threshold, the same cut that defines Flood Zone 3 in planning, so
               it is the conventional line rather than one invented here:

                 high    >= 10% of postcodes at Medium or High
                 medium  >=  2%
                 low     <   2%

               The app's flood scale has three levels, while the EA publishes
               four (High / Medium / Low / Very low). Collapsing on the planning
               threshold keeps the boundary meaningful; averaging the four into
               three would not.

WHY POSTCODE CENTROIDS RATHER THAN BOROUGH AREA
------------------------------------------------
An area-weighted median is dominated by whatever is empty. Outer boroughs are
mostly parks, reservoir and farmland, so an area median reports the quiet of
places nobody lives at. Sampling at NSPL postcode centroids weights toward where
addresses actually are, and it is the same idiom load_defra_raster.py uses to
populate the per-postcode table.

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
from collections import Counter, defaultdict
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

# Share of a borough's addresses at Medium or High flood risk (>= 1% annual
# chance), which is the Flood Zone 3 planning threshold.
FLOOD_HIGH_SHARE = 10.0
FLOOD_MEDIUM_SHARE = 2.0
# Codes written by fetch_ea_flood_risk.py, ordered by severity.
FLOOD_MEDIUM_OR_HIGH = (3, 4)
FLOOD_UNAVAILABLE = 255

ROAD_VINTAGE = 'DEFRA Strategic Noise Mapping Round 4 (published 2022), road Lden'
AQ_VINTAGE = 'DEFRA background pollution maps, 2022 annual mean, 1 km grid'
FLOOD_VINTAGE = 'Environment Agency Risk of Flooding from Rivers and Sea (NAFRA2)'
TRANSPORT_VINTAGE = 'NaPTAN (DfT) rail, metro and tram access nodes'
HEALTH_VINTAGE = 'NHS Organisation Data Service, active GP practices and branch surgeries'

GP_JSON = DATA / 'nhs-gp-practices.json'
# 500 m, the standard walkable-neighbourhood distance, CHOSEN BY MEASUREMENT.
# GP surgeries are dense, so a generous radius stops discriminating: at 1 km,
# 68 of 81 boroughs came out `excellent` and NONE came out `moderate`, which is
# a true statement about GP density and a useless input to a score. Measured
# spread of the borough share across five radii:
#     300 m  8.9-58.5   400 m 17.5-79.6   500 m 24.0-91.5
#     600 m 30.8-97.5   800 m 42.8-100.0
# 500 m has the widest spread (67.5 points) and a median near the middle of the
# range, so the three bands each carry boroughs.
GP_RADIUS_M = 500.0
HEALTH_EXCELLENT_SHARE = 75.0
HEALTH_GOOD_SHARE = 50.0

NAPTAN_CSV = DATA / 'naptan.csv'
# Rail station access areas and entrances, metro/underground entrances, tram and
# metro access points, and platforms. Deliberately excludes BCT (bus stop on
# street), which is 96% of the register.
NAPTAN_RAIL_TYPES = {'RLY', 'RSE', 'PLT', 'TMU', 'MET'}
WALK_RADIUS_M = 800.0
TRANSPORT_EXCELLENT_SHARE = 75.0
TRANSPORT_GOOD_SHARE = 50.0
TRANSPORT_MODERATE_SHARE = 25.0

# Wales is not in the England road-noise coverage; Natural Resources Wales
# publishes its own. A city here gets air quality (the DEFRA grid is UK-wide)
# and no road band, rather than a silently empty one.
NO_ROAD_COVERAGE = {'cardiff'}
# Same reason: RoFRS is an Environment Agency (England) product, and New York
# keeps its curated FEMA-derived bands.
NO_FLOOD_COVERAGE = {'cardiff', 'nyc'}


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


def collect_postcodes(lad_map, limit=None, extra_postcodes=None):
    """One pass over NSPL: {city: {borough: [(lat, lon), ...]}}.

    `extra_postcodes` is a set of postcodes whose coordinates are also wanted -
    the GP surgeries. Collected in the SAME pass because the file is 806 MB and
    a second scan to geocode ten thousand postcodes would cost as much as the
    first.

    One pass, not one per city. The file is 806 MB and re-reading it per city
    would turn a two-minute job into a twenty-minute one for no benefit.
    """
    if not NSPL_CSV.exists():
        raise SystemExit(f'NSPL not found at {NSPL_CSV}')
    out = defaultdict(lambda: defaultdict(list))
    extra_coords = {}
    seen = 0
    with NSPL_CSV.open(newline='', encoding='utf-8-sig') as fh:
        for idx, row in enumerate(csv.DictReader(fh)):
            if limit and idx >= limit:
                break
            if extra_postcodes:
                pc = (row.get('pcds') or '').replace(' ', '').upper()
                if pc in extra_postcodes:
                    try:
                        extra_coords[pc] = (float(row['lat']), float(row['long']))
                    except (KeyError, ValueError):
                        pass
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
    if extra_postcodes:
        print(f'  {len(extra_coords):,}/{len(extra_postcodes):,} GP postcodes geocoded')
    return out, extra_coords


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


def sample_codes(tif_path, points):
    """Sample a classified GeoTIFF at (lat, lon) points. Returns raw codes.

    Deliberately NOT sample_raster(): that drops values of 0, because for the
    Lden rasters 0 means 'below the lowest mapped band'. For flood, 0 is a real
    class - not in any modelled risk polygon - and dropping it would compute the
    share of at-risk addresses among the at-risk addresses, which is 100% by
    construction.
    """
    import numpy as np
    import rasterio
    from pyproj import Transformer

    with rasterio.open(tif_path) as ds:
        band = ds.read(1)
        transform = ds.transform
        crs = ds.crs
        height, width = band.shape

    tr = Transformer.from_crs('EPSG:4326', crs, always_xy=True)
    xs, ys = tr.transform(np.array([p[1] for p in points]), np.array([p[0] for p in points]))
    cols, rows = ~transform * (xs, ys)
    cols = np.floor(cols).astype(int)
    rows = np.floor(rows).astype(int)
    inside = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
    codes = np.full(len(points), FLOOD_UNAVAILABLE, dtype='uint8')
    codes[inside] = band[rows[inside], cols[inside]]
    return codes, int(inside.sum())


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


def load_gp_postcodes():
    """{normalised postcode: None} for every active GP practice / branch."""
    if not GP_JSON.exists():
        raise SystemExit(
            f'{GP_JSON} not found. Build it with:\n'
            '  python scripts/fetch_nhs_gp_practices.py'
        )
    with GP_JSON.open(encoding='utf-8') as fh:
        doc = json.load(fh)
    out = {p['postcode'].replace(' ', '').upper() for p in doc['practices'].values()}
    print(f'  {len(out):,} distinct GP postcodes ({doc["count"]:,} practices)')
    # Same reasoning as the NaPTAN guard: an empty set is a failed read, and it
    # would publish 'moderate' healthcare for every borough rather than nothing.
    if not out:
        raise SystemExit(
            f'{GP_JSON} parsed but yielded ZERO GP postcodes. '
            'Refusing to continue: an empty index publishes a healthcare band '
            'for every borough that no data supports.'
        )
    return out


def health_band(share):
    """Three bands, because HEALTH_SCORE has three. There is no `poor` tier."""
    if share is None:
        return None
    if share >= HEALTH_EXCELLENT_SHARE:
        return 'excellent'
    if share >= HEALTH_GOOD_SHARE:
        return 'good'
    return 'moderate'


def load_naptan_grid():
    """Rail/metro/tram nodes indexed into 1 km British National Grid cells.

    A grid, not a spatial library: the search radius is 800 m, so a 3x3 block of
    1 km cells always contains every candidate and the whole lookup stays in the
    standard library.
    """
    if not NAPTAN_CSV.exists():
        raise SystemExit(
            f'NaPTAN not found at {NAPTAN_CSV}. Fetch with:\n'
            '  curl -o data/naptan.csv '
            '"https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv"'
        )
    grid = defaultdict(list)
    kept = 0
    with NAPTAN_CSV.open(newline='', encoding='utf-8-sig', errors='replace') as fh:
        for row in csv.DictReader(fh):
            if row.get('StopType') not in NAPTAN_RAIL_TYPES:
                continue
            try:
                e, n = float(row['Easting']), float(row['Northing'])
            except (KeyError, ValueError):
                continue
            grid[(int(e // 1000), int(n // 1000))].append((e, n))
            kept += 1
    print(f'  {kept:,} rail/metro/tram access nodes indexed')
    # ZERO ROWS IS A FAILED READ, not a country with no stations. The
    # file-exists check above passes for a NaPTAN export whose StopType or
    # Easting column has been renamed upstream - it opens, it parses, it yields
    # nothing - and every borough then publishes 'poor' transport into both
    # score holders. Fail here rather than downstream.
    if kept == 0:
        raise SystemExit(
            f'{NAPTAN_CSV} parsed but yielded ZERO rail/metro/tram nodes. '
            'The file exists and is readable, so this is a schema change, not a '
            'missing download - check the StopType and Easting/Northing column '
            'names. Refusing to continue: an empty index would publish '
            "'poor' transport for every borough, into both holders."
        )
    return grid


def transport_share(grid, points):
    """Share of points within WALK_RADIUS_M of any indexed node."""
    return points_within(grid, points, WALK_RADIUS_M)


def points_within(grid, points, radius_m):
    """Share of points within radius_m of anything in a 1 km-cell grid."""
    import numpy as np
    from pyproj import Transformer

    tr = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    xs, ys = tr.transform(
        np.array([p[1] for p in points]), np.array([p[0] for p in points])
    )
    r2 = radius_m * radius_m
    near = 0
    for x, y in zip(xs, ys, strict=True):
        cx, cy = int(x // 1000), int(y // 1000)
        hit = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for sx, sy in grid.get((cx + dx, cy + dy), ()):
                    if (sx - x) ** 2 + (sy - y) ** 2 <= r2:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break
        near += hit
    # AN EMPTY INDEX IS NOT A ZERO SHARE.
    #
    # `grid` empty means the register could not be read - a renamed column in
    # NaPTAN, an empty GP export - not that every postcode is far from a
    # station. Returning 0.0 for that made transport_band() answer 'poor' and
    # health_band() answer 'moderate' for EVERY borough, and `transport` is
    # 0.25 of liveability. Worse, --write-lambda copies the same value into the
    # score Lambda, so both holders agreed and test_borough_data_parity stayed
    # green while both were wrong.
    #
    # The file-exists guards above cannot see this: a renamed column opens and
    # parses perfectly and yields nothing.
    if not grid:
        return None
    return 100.0 * near / len(points) if points else None


def transport_band(share):
    if share is None:
        return None
    if share >= TRANSPORT_EXCELLENT_SHARE:
        return 'excellent'
    if share >= TRANSPORT_GOOD_SHARE:
        return 'good'
    if share >= TRANSPORT_MODERATE_SHARE:
        return 'moderate'
    return 'poor'


def flood_band(medium_or_high_pct):
    """Band from the share of addresses at or above the 1% annual chance line."""
    if medium_or_high_pct is None:
        return None
    if medium_or_high_pct >= FLOOD_HIGH_SHARE:
        return 'high'
    if medium_or_high_pct >= FLOOD_MEDIUM_SHARE:
        return 'medium'
    return 'low'


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

    print('loading NHS GP register...')
    gp_postcodes = load_gp_postcodes()

    print('scanning NSPL...')
    by_city, gp_coords = collect_postcodes(lad_map, limit=limit, extra_postcodes=gp_postcodes)

    # Same 1 km-cell grid trick as NaPTAN, over the geocoded surgeries.
    from pyproj import Transformer as _T

    _tr = _T.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    gp_grid = defaultdict(list)
    for lat, lon in gp_coords.values():
        e, n = _tr.transform(lon, lat)
        gp_grid[(int(e // 1000), int(n // 1000))].append((e, n))

    print('loading DEFRA air-quality grids...')
    grids = load_aq_grid()

    print('loading NaPTAN...')
    naptan = load_naptan_grid()

    import numpy as np

    results = {}
    for city in sorted(by_city):
        tif = DATA / f'defra_road_lden_{city}.tif'
        have_road = tif.exists() and city not in NO_ROAD_COVERAGE
        flood_tif = DATA / f'ea_flood_risk_{city}.tif'
        have_flood = flood_tif.exists() and city not in NO_FLOOD_COVERAGE
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

            if have_flood:
                codes, _inside = sample_codes(flood_tif, points)
                known = codes[codes != FLOOD_UNAVAILABLE]
                if known.size:
                    at_risk = int(np.isin(known, FLOOD_MEDIUM_OR_HIGH).sum())
                    pct = 100.0 * at_risk / known.size
                    rec['floodMediumOrHighPct'] = round(pct, 2)
                    rec['flood'] = flood_band(pct)
                    rec['floodCoverage'] = round(100 * known.size / len(points), 1)
                    rec['floodVintage'] = FLOOD_VINTAGE

            gp_share = points_within(gp_grid, points, GP_RADIUS_M)
            if gp_share is not None:
                rec['healthcareWithin1kmPct'] = round(gp_share, 1)
                rec['healthcare'] = health_band(gp_share)
                rec['healthcareVintage'] = HEALTH_VINTAGE

            share = transport_share(naptan, points)
            if share is not None:
                rec['transportWithin800mPct'] = round(share, 1)
                rec['transport'] = transport_band(share)
                rec['transportVintage'] = TRANSPORT_VINTAGE

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
            fl = (
                f"flood {r['flood']:6s} {r['floodMediumOrHighPct']:5.2f}% >=1%/yr"
                if 'flood' in r
                else 'flood NO DATA           '
            )
            tr_ = (
                f"tr {r['transport']:9s} {r['transportWithin800mPct']:5.1f}% <800m"
                if 'transport' in r
                else 'tr NO DATA            '
            )
            hc = (
                f"hc {r['healthcare']:9s} {r['healthcareWithin1kmPct']:5.1f}% <1km"
                if 'healthcare' in r
                else 'hc NO DATA           '
            )
            print(f'  {borough:28s} {r["postcodes"]:6,d} pc  {road}  {aq}  {fl}  {tr_}  {hc}')


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
    'transport',
    'transportWithin800mPct',
    'transportVintage',
    'healthcare',
    'healthcareWithin1kmPct',
    'healthcareVintage',
    'flood',
    'floodMediumOrHighPct',
    'floodCoverage',
    'floodVintage',
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
    # PER-FIELD COMPARISON COUNTS (2026-08-31).
    #
    # `if new is None: continue` below means a field the DERIVATION could not
    # produce is skipped silently, so missing data was indistinguishable from
    # agreement. `data/` is gitignored, so an absent raster is the normal state
    # on any machine but the one that fetched it - and it is the state a new
    # city is in. Proven: with the road rasters absent this printed
    # "borough-extra.json agrees with DEFRA on every derived field" and exited
    # 0; so did an EMPTY derivation.
    #
    # This is the only gate that crosses a source boundary for road noise (0.35
    # of `environment`), air quality (0.45), transport (0.25 of `live`) and
    # healthcare (0.10). Nothing in tests/ or backend/tests/ reads NaPTAN, the
    # NHS register or the DEFRA grids at all.
    compared = Counter()
    holder_only = Counter()
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
                    # Recorded, not silently dropped. A field the holder
                    # PUBLISHES that the source no longer produces is the
                    # interesting case - it means we are serving a number
                    # nothing can currently reproduce.
                    if old is not None:
                        holder_only[key] += 1
                    continue
                compared[key] += 1
                if old != new:
                    diffs.append(f'{city}.{borough}.{key}: {old!r} -> {new!r}')
                    if write:
                        target[key] = new

    if skipped_cities:
        print()
        print(f'not on the site, skipped: {", ".join(sorted(skipped_cities))}')

    # SAY WHAT WAS COMPARED, ALWAYS. A run that compared everything and a run
    # whose loop never executed used to print the same sentence.
    print()
    print(f'{"field":<26} {"compared":>8}  {"holder-only":>11}')
    for key in DERIVED_KEYS:
        flag = '' if compared[key] else '   <- NOTHING COMPARED'
        print(f'{key:<26} {compared[key]:>8}  {holder_only[key]:>11}{flag}')

    if not write:
        # PER-FIELD FLOOR, not a global one. A global `compared > 0` is
        # satisfied by air quality alone while every road field is absent -
        # the same shape this repo has now closed in five other gates.
        empty = [k for k in DERIVED_KEYS if not compared[k]]
        if empty:
            diffs.append(
                'COMPARED NOTHING for '
                + ', '.join(empty)
                + ' - the source produced no value for these anywhere, so agreement '
                'was never tested. Fetch the rasters, or this is not a pass.'
            )

    if write and diffs:
        with BOROUGH_EXTRA.open('w', encoding='utf-8', newline='\n') as fh:
            json.dump(extra, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
        print(f'wrote {BOROUGH_EXTRA} ({len(diffs)} field(s) updated)')
    return diffs


LAMBDA_FIELDS = (
    'transport',
    'healthcare',
    # Added for methodology v3.9, 2026-08-26, when air quality and flood stopped
    # being display-only. These are the CONTINUOUS fields, not the three-band
    # summaries beside them: the bands exist to colour a map and are far too
    # coarse to score (68.1% of `airQuality` is 'moderate', 63.7% of `flood` is
    # 'low'), while the ratios discriminate across 60 and 69 distinct values.
    # The bands stay in borough-extra.json alone, because they are still only
    # drawn.
    'airQualityWhoRatio',
    'floodMediumOrHighPct',
    # Added for methodology v4.0, 2026-08-29, when road noise stopped being the
    # last display-only input. The SHARE over WHO's 53 dB Lden guideline, not
    # the median dB beside it: the median carries 41 distinct values across 73
    # boroughs against the share's 69, over an interquartile range of 1.7 dB.
    # roadNoise, roadNoiseLdenMedian and roadNoiseCoverage stay in
    # borough-extra.json alone - the band colours a map and the other two are
    # reported by /v1/environment, none of them scores.
    'roadNoiseAboveWhoPct',
)

# The two holders disagree on ONE borough's name: borough-extra.json keys it
# `Barking`, the Lambda keys it `Barking and Dagenham`, which is the borough's
# actual name.
#
# WITHOUT THIS, write_lambda SILENTLY SKIPS IT. It searches the Lambda source
# for "'Barking': {", finds nothing, prints one line among many and moves on -
# so Barking and Dagenham would be the single London borough with no
# airQualityWhoRatio, and get_env_score() would return None for it while its 32
# neighbours scored. Found on the first --sync-lambda dry run, 2026-08-26.
#
# DUPLICATED FROM tests/test_borough_data_parity.py ON PURPOSE, and guarded
# rather than extracted. No test in this repo imports from scripts/ and no
# script imports from tests/, so extracting means inventing a shared module for
# one entry. The precedent is _US_AIRPORT_CODES in the score Lambda, duplicated
# the same day for the same reason with a drift-guard test beside it:
# test_name_aliases_match_the_builder() fails if these two ever diverge. Do not
# add an entry here without adding it there.
#
# Declared, never fuzzy-matched - a fuzzy match would also pair a genuinely
# missing borough with a similar one and report success.
NAME_ALIASES = {'Barking': 'Barking and Dagenham'}


def write_lambda(results, write):
    """Put the derived SCORING fields into the score Lambda's borough dicts.

    WHY THIS EXISTS AND WHY ROAD NOISE STILL DOES NOT. Anything the Lambda
    SCORES has to live in both holders, because the Lambda scores from its own
    CITIES dict and the site scores from borough-extra.json - leaving a scored
    input in one holder puts the site and the API on different numbers, which is
    the divergence class this repo has shipped three times.

    Until 2026-08-26 that meant `transport` and `healthcare` alone, and this
    docstring said road noise, air quality and flood were "display-only, so
    borough-extra.json is their single holder". Methodology v3.9 makes air
    quality and flood SCORED, via the `environment` component, so two of those
    three moved and the sentence had to move with them. **Road noise remains
    display-only** and remains single-holder; it is scheduled for v4.0 as part
    of the `quiet` noise composite, and this line is the thing to change then.

    tests/test_borough_data_parity.py compares the two holders and is the guard
    that this stayed honest; validate_borough_vocabulary() at Lambda import is
    the guard that the categorical values are legal.

    Handles both source shapes: London's multi-line borough dicts and the newer
    cities' single-line ones, and both value shapes: categorical bands written
    as quoted strings, and the v3.9 ratios written as bare numbers. Writing a
    float as a quoted string is the obvious way to get this wrong - the Lambda
    would import fine and every comparison against it would be a string compare.
    """
    import re

    def block_extent(text, opening_index):
        """(start, end) of a brace-delimited literal, by matching depth."""
        depth = 0
        for i in range(opening_index, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    return opening_index, i
        raise SystemExit('unbalanced braces in the Lambda source')

    src = SCORE_APP.read_text(encoding='utf-8')
    changed = 0
    for city, boroughs in results.items():
        # SCOPE THE SEARCH TO THIS CITY'S OWN DICT. A global search for
        # "'Hillingdon': {" finds LONDON_PREVIOUS_PT at line 183 long before
        # LONDON_BOROUGHS at line 782, and writes the scoring field into the
        # previous-vintage price table that ?compare=previous reads. Measured:
        # it silently patched 81 lines of the wrong dict on the first run.
        anchor = f'{city.upper()}_BOROUGHS = {{'
        if src.find(anchor) < 0:
            print(f'    {city}: no {anchor.rstrip(" ={")} in the Lambda source')
            continue

        for borough, rec in boroughs.items():
            # The Lambda's key, which is not always the site's - see NAME_ALIASES.
            borough = NAME_ALIASES.get(borough, borough)
            # Relocated per borough: every edit shifts every later offset, so a
            # block range computed once goes stale after the first write.
            at = src.find(anchor)
            city_start, city_end = block_extent(src, src.index('{', at))
            for field in LAMBDA_FIELDS:
                value = rec.get(field)
                if value is None:
                    continue
                # Locate this borough's dict literal, then its extent by brace
                # matching. Regex alone cannot find the end of a nested dict.
                key = re.escape(f"'{borough}': {{")
                mo = re.search(key, src[city_start : city_end + 1])
                if not mo:
                    print(f'    {city}/{borough}: not found inside {anchor.rstrip(" ={")}')
                    continue
                start, end = block_extent(src, city_start + mo.end() - 1)
                body = src[start : end + 1]
                # A categorical band is a quoted string; a v3.9 ratio is a bare
                # number. Quoting the number would import cleanly and turn every
                # downstream comparison into a string compare, so the literal is
                # derived from the value's type rather than assumed.
                if isinstance(value, str):
                    literal = f"'{value}'"
                    existing = re.search(rf"'{field}': '([a-z-]+)'", body)
                    unchanged = existing is not None and existing.group(1) == value
                else:
                    literal = repr(round(float(value), 2))
                    existing = re.search(rf"'{field}': (-?[0-9]+(?:\.[0-9]+)?)", body)
                    unchanged = existing is not None and existing.group(1) == literal
                if existing:
                    if unchanged:
                        continue
                    new_body = (
                        body[: existing.start()] + f"'{field}': {literal}" + body[existing.end() :]
                    )
                else:
                    # Insert before the closing brace, matching the local style:
                    # multi-line dicts get their own indented line.
                    if '\n' in body:
                        indent = ' ' * 8
                        new_body = body[:-1].rstrip()
                        if not new_body.endswith(','):
                            new_body += ','
                        new_body += f"\n{indent}'{field}': {literal},\n    }}"
                    else:
                        new_body = body[:-1].rstrip()
                        if not new_body.endswith(','):
                            new_body += ','
                        new_body += f" '{field}': {literal}}}"
                src = src[:start] + new_body + src[end + 1 :]
                changed += 1
    if changed and write:
        SCORE_APP.write_text(src, encoding='utf-8', newline='')
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true', help='exit 1 if the holder disagrees')
    ap.add_argument('--write', action='store_true', help='update data/borough-extra.json')
    ap.add_argument(
        '--write-lambda',
        action='store_true',
        help="also put scoring fields into the score Lambda's borough dicts",
    )
    ap.add_argument('--limit', type=int, help='only read N NSPL rows (smoke test)')
    ap.add_argument(
        '--sync-lambda',
        action='store_true',
        help='propagate scoring fields from borough-extra.json into the Lambda, no derivation',
    )
    args = ap.parse_args()

    # --sync-lambda deliberately SKIPS derive(). Everything else here re-derives
    # from DEFRA, the EA WMS, NaPTAN and a 2.7M-row NSPL scan, which is minutes
    # of work and needs the network for flood; propagating an already-derived
    # value into the second holder needs none of it.
    #
    # THIS IS A COPY, NOT A DERIVATION, AND THE DISTINCTION MATTERS. It trusts
    # borough-extra.json to be current and can only make the Lambda agree with
    # it - it cannot tell you whether that file still agrees with DEFRA. That is
    # what `--check` is for, and it is the gate that should run first. Used the
    # other way round this would launder a stale value into a second holder and
    # make the parity test go green on two copies of the same wrong number,
    # which is precisely the failure recorded in feedback-empty-index-is-not-a-
    # zero-reading.
    if args.sync_lambda:
        extra = json.loads(BOROUGH_EXTRA.read_text(encoding='utf-8'))
        wanted = set(LAMBDA_FIELDS)
        staged = {
            city: {
                name: {k: v for k, v in rec.items() if k in wanted}
                for name, rec in boroughs.items()
            }
            for city, boroughs in extra.items()
        }
        n = write_lambda(staged, write=args.write)
        verb = 'written into' if args.write else 'would change in'
        print(f'{n} field(s) {verb} {SCORE_APP.name}')
        if not args.write:
            print('(dry run; pass --write to apply)')
        return 0

    results = derive(limit=args.limit)
    report(results)

    if not (args.check or args.write):
        print('\n(report only; pass --write to update borough-extra.json)')
        return 0

    if args.write_lambda:
        n = write_lambda(results, write=True)
        print(f'\n{n} field(s) written into {SCORE_APP.name}')

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
