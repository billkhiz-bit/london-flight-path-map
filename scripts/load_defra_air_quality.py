#!/usr/bin/env python3
"""Sample DEFRA background air-quality grids at UK postcode centroids.

WHY A SEPARATE LOADER. load_defra_raster.py samples a GeoTIFF with rasterio.
DEFRA's background pollution maps are not rasters — they are CSVs of 1 km grid
cells (`gridcode,x,y,value`) in British National Grid, the same CRS as the noise
rasters. Converting them to GeoTIFF to reuse that loader would be more work than
reading them directly, and would put a lossy step between the published figures
and what we serve.

WHY NOT DAQI. `plannedComponents.airQuality` in the score Lambda names the DEFRA
Daily Air Quality Index. DAQI is a *daily* index reported at monitoring stations
— sparse, and about today's weather as much as the location. For a property
score the right measure is the annual mean concentration on a modelled grid,
which is what the PCM background maps publish and what the WHO guidelines below
are expressed against.

  NO2   annual mean, 2022    WHO 2021 guideline: 10 ug/m3
  PM2.5 annual mean, 2022    WHO 2021 guideline:  5 ug/m3

COVERAGE. Unlike the aircraft noise raster (6.2% of its grid carries data), these
cover the whole UK land surface — 254,905 cells. So air quality does not inherit
the coverage problem that quarantined the aircraft tier, and readings will be
present for essentially every postcode.

  pip install pyproj boto3 tqdm
  AWS_PROFILE=flightmap python scripts/load_defra_air_quality.py --dry-run --limit 200000
  AWS_PROFILE=flightmap python scripts/load_defra_air_quality.py

DO NOT run this while load_defra_raster.py is running. Both write to the same
table through per-item UpdateItems, and they will simply halve each other's
throughput.
"""

import argparse
import csv
import sys
from pathlib import Path

# Shared write policy. Sibling module, so a plain import works when this is run
# the documented way - `python scripts/load_defra_air_quality.py` puts scripts/
# on sys.path. The fallback covers loading this file by path, as its tests do.
try:
    import ddb_write
except ImportError:  # pragma: no cover - depends on how the file was loaded
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ddb_write

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

NO2_CSV = Path('data/defra_mapno22022.csv')
PM25_CSV = Path('data/defra_mappm252022g.csv')
NSPL_CSV = Path('data/nspl.csv')
TABLE_NAME = 'london-flight-map-noise-raster'
AWS_REGION = 'eu-west-2'
BATCH_SIZE = 25
CHECKPOINT = Path('.defra_aq_checkpoint')

# Postcodes whose write could not be made to land. Written out so the run can
# complete without the gap being invisible - a skipped postcode is ABSENT from
# the table, and absent is exactly the state this project keeps misreading as
# "measured and fine" (see MISSING_TOKENS below). A tally alone would not say
# WHICH, so it could not be re-run.
FAILURES = Path('.defra_aq_failures')

# The grids are 1 km. Cell centres sit on x500/y500, so flooring to the
# kilometre and keying on that maps any coordinate to its containing cell.
CELL_M = 1000

# DEFRA writes 'MISSING' for cells outside the modelled domain (sea, and a
# handful of gaps). Treated as absent, never as clean air — the substitution of
# "not measured" for "measured and fine" is this project's most-repeated defect.
MISSING_TOKENS = {'MISSING', '', 'NA', 'NODATA'}


def load_grid(path, label):
    """Read a PCM CSV into {(cell_x, cell_y): value}.

    The first six lines are a header block (pollutant, year, metric, units, a
    blank, then the column names), so the data starts at row 7.
    """
    if not path.exists():
        print(f'ERROR: {path} not found. See the module docstring for the URL.')
        sys.exit(1)

    grid = {}
    skipped = 0
    with path.open(encoding='utf-8') as fh:
        for _ in range(6):
            fh.readline()
        for row in csv.reader(fh):
            if len(row) < 4:
                continue
            raw = row[3].strip()
            if raw.upper() in MISSING_TOKENS:
                skipped += 1
                continue
            try:
                x, y, value = int(float(row[1])), int(float(row[2])), float(raw)
            except ValueError:
                skipped += 1
                continue
            grid[(x // CELL_M, y // CELL_M)] = value
    print(f'  {label}: {len(grid):,} cells ({skipped:,} missing)')
    return grid


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--limit', type=int, default=None, metavar='N')
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()

    try:
        from pyproj import Transformer
    except ImportError:
        print('Install with: pip install pyproj boto3 tqdm')
        return 1

    print('loading grids...')
    no2 = load_grid(NO2_CSV, 'NO2')
    pm25 = load_grid(PM25_CSV, 'PM2.5')

    to_bng = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)

    ddb = None
    if not args.dry_run:
        # Adaptive retry, not a bare client. This loader died at 28% on
        # 2026-08-08, one minute before the machine slept at 21:28:12. See
        # ddb_write for the full reasoning.
        ddb = ddb_write.make_client(AWS_REGION)

    start = 0
    if CHECKPOINT.exists() and not args.limit:
        start = int(CHECKPOINT.read_text().strip() or 0)
        print(f'resuming from row {start:,}')

    batch = []
    written = missed = failed = 0
    samples = 0

    def flush():
        from concurrent.futures import ThreadPoolExecutor

        def _put(item):
            names, values, sets = {}, {}, []
            for i, (attr, val) in enumerate(item['attrs'].items()):
                names[f'#a{i}'] = attr
                values[f':v{i}'] = {'N': f'{val:.2f}'}
                sets.append(f'#a{i} = :v{i}')
            ddb.update_item(
                TableName=TABLE_NAME,
                Key={'postcode': {'S': item['postcode']}},
                UpdateExpression='SET ' + ', '.join(sets),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )

        with ThreadPoolExecutor(max_workers=25) as ex:
            landed = list(ex.map(lambda it: ddb_write.guarded_put(_put, it), batch))

        stalled = [
            item['postcode']
            for item, ok in zip(batch, landed, strict=True)
            if not ok
        ]
        if stalled:
            nonlocal failed
            failed += len(stalled)
            ddb_write.record_failures(FAILURES, stalled)

        # Callers add THIS, not len(batch) - a batch of 25 with 3 stalls put 22
        # rows in the table, and reporting 25 would be the same "absent read as
        # present" error one layer up from the data.
        return len(batch) - len(stalled)

    with NSPL_CSV.open(encoding='utf-8', errors='replace') as fh:
        for idx, row in enumerate(csv.DictReader(fh)):
            if idx < start:
                continue
            if args.limit and idx >= args.limit:
                break
            try:
                lat, lon = float(row['lat']), float(row['long'])
            except (KeyError, TypeError, ValueError):
                continue
            # NSPL uses 99.999999 for postcodes with no grid reference.
            if lat > 60.9 or lat < 49.8:
                continue

            x, y = to_bng.transform(lon, lat)
            key = (int(x) // CELL_M, int(y) // CELL_M)

            attrs = {}
            if key in no2:
                attrs['no2Ugm3'] = no2[key]
            if key in pm25:
                attrs['pm25Ugm3'] = pm25[key]
            if not attrs:
                missed += 1
                continue

            pc = row['pcds'].replace(' ', '').upper()
            if args.dry_run:
                if samples < 5:
                    print(f'  sample {samples + 1}: {pc} -> {attrs}')
                    samples += 1
                written += 1
                continue

            batch.append({'postcode': pc, 'attrs': attrs})
            if len(batch) >= BATCH_SIZE:
                written += flush()
                batch.clear()

            if not args.limit and idx % 1000 == 0:
                CHECKPOINT.write_text(str(idx))

    if batch and not args.dry_run:
        written += flush()

    if not args.limit and not args.dry_run:
        CHECKPOINT.unlink(missing_ok=True)

    verb = 'Would have written' if args.dry_run else 'Wrote'
    print(f'\n{verb}: {written:,} postcodes. No grid cell: {missed:,}.')
    if failed:
        print(
            f'STALLED: {failed:,} postcodes could not be written and are NOT in '
            f'the table. Named in {FAILURES}; re-run once the fault is fixed.'
        )
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
