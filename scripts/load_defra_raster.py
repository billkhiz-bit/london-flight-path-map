"""
Sky Score v3.1, DEFRA Lden raster sampler.

One-time batch script that samples the DEFRA Strategic Noise Mapping
(Round 4, 2022) Lden raster at every UK postcode centroid and writes the
results to DynamoDB. Once the table is populated, the score Lambda
automatically uses raster values for the quiet component (highest
precision tier in the resolution chain).

PRE-REQUISITES (run once, locally, not in the Lambda environment):

  pip install rasterio pyproj boto3 tqdm

INPUTS NEEDED:

  1. DEFRA Lden GeoTIFF (~500 MB, free, OGL v3.0). Listed under "Strategic
     noise mapping (England)-round 4 (2022)" on the gov.uk page below;
     accept the click-through licence and download the Lden GeoTIFF for
     "All sources combined" (or "Aircraft" alone if you want aviation-only):
     https://www.gov.uk/government/collections/strategic-noise-mapping
     Save as `data/defra_lden_2022.tif` relative to project root.

  2. ONS National Statistics Postcode Lookup (NSPL). Lat/lon for every UK
     postcode. Free, OGL v3.0:
     https://geoportal.statistics.gov.uk/datasets/ons::nspl-online-latest-by-postcode/
     Download the CSV (large, ~250 MB after extraction) and save as
     `data/nspl.csv`. The script reads the standard columns `pcds`, `lat`,
     `long` (these names have been stable across NSPL editions).

  3. AWS credentials with write access to the `london-flight-map-noise-raster`
     table (already covered by the flightmap-dev IAM policy at
     backend/iam-policy.json, DynamoDB.PutItem on
     `arn:aws:dynamodb:eu-west-2:*:table/london-flight-map-*`).

USAGE:

  # Sanity-check the CRS transform without any data files (~1 second):
  AWS_PROFILE=flightmap python scripts/load_defra_raster.py --self-test

  # Smoke-test the full pipeline on the first 100 NSPL rows without any
  # DDB writes (~30 seconds, requires both data files):
  AWS_PROFILE=flightmap python scripts/load_defra_raster.py --limit 100 --dry-run

  # Real run on the first 1000 rows (verifies DDB write throughput, ~30 s):
  AWS_PROFILE=flightmap python scripts/load_defra_raster.py --limit 1000

  # Full overnight run (~1 hour, ~1.7M postcodes, ~$2-3 in DDB writes):
  AWS_PROFILE=flightmap python scripts/load_defra_raster.py

EXPECTED RUNTIME:

  ~1.7M postcodes, ~500 writes/sec to DynamoDB on-demand → ~1 hour. The
  GeoTIFF read is local (10 ms/sample) so the bottleneck is DDB writes.
  The script is resumable: if interrupted, re-running picks up at the
  last checkpoint (written every 1000 rows). Postcodes are idempotent
  keys, re-runs overwrite with the same value, never duplicate.

WHAT IT DOES:

  1. Loads the DEFRA GeoTIFF using rasterio
  2. Streams the NSPL CSV row-by-row (postcode, lat, lon)
  3. For each postcode, projects lat/lon to the raster's CRS and samples
     the Lden value at that pixel
  4. Batch-writes (postcode, ldenDb) tuples to DynamoDB (25 per request,
     the AWS BatchWriteItem max)
  5. Logs progress to stdout via tqdm; resumable from a checkpoint if
     interrupted

VERIFICATION AFTER LOAD:

  # Confirm row count (should be ~1.7M minus skipped no-data pixels):
  AWS_PROFILE=flightmap aws dynamodb describe-table \\
    --table-name london-flight-map-noise-raster \\
    --query 'Table.ItemCount' --region eu-west-2

  # Confirm a known postcode resolves via raster (not the v3.0 fallback):
  curl 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score?postcode=TW6+2GA' \\
    -H 'X-Api-Key: <your-key>' | python -c \\
    "import json,sys;d=json.loads(sys.stdin.read());print(d['context']['quietResolution'])"
  # Expect: raster (was: postcode for v3.0 Haversine, borough for v2.x)
"""

import argparse
import csv
import sys
from pathlib import Path

# Force UTF-8 stdout so the en-dashes / arrows / pound signs in our help
# text and progress lines render on Windows cp1252 consoles. Python 3.7+.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ---- Configuration ----

DEFRA_GEOTIFF_PATH = Path('data/defra_lden_2022.tif')
NSPL_CSV_PATH = Path('data/nspl.csv')
TABLE_NAME = 'london-flight-map-noise-raster'
AWS_REGION = 'eu-west-2'
BATCH_SIZE = 25 # DynamoDB BatchWriteItem max
CHECKPOINT_PATH = Path('.defra_load_checkpoint')

# Lden sanity range, DEFRA values are 30-95 dB; pixels outside this
# range are nodata sentinels (often 0, 255, or large negative numbers
# depending on the GeoTIFF encoding).
LDEN_MIN = 30.0
LDEN_MAX = 100.0


def parse_args():
    p = argparse.ArgumentParser(
        description='Sample the DEFRA Lden raster at UK postcode centroids '
                    'and write to DynamoDB. See module docstring for runbook.',
    )
    p.add_argument(
        '--limit', type=int, default=None, metavar='N',
        help='Process only the first N rows of the NSPL CSV. Useful for '
             'verifying the pipeline before committing to the full ~1.7M '
             'postcode run. Counts toward the resumable checkpoint as if '
             'it were a partial run.',
    )
    p.add_argument(
        '--dry-run', action='store_true',
        help='Skip all DynamoDB writes, just sample the raster and print '
             'what would be written. Use with --limit for a fast (~30 s) '
             'end-to-end smoke test that confirms the raster, CRS '
             'transform, and CSV columns are all working.',
    )
    p.add_argument(
        '--self-test', action='store_true',
        help='Run the WGS84 → BNG CRS transform on a known UK postcode '
             '(SW1A 1AA, Buckingham Palace) without needing the data '
             'files. Verifies pyproj is installed and Transformer behaves '
             'sensibly. Exits after the test.',
    )
    return p.parse_args()


def self_test():
    """Verify the CRS transform layer without any data files.

    Transforms the SW1A 1AA centroid (Buckingham Palace, well-known
    coordinates) from WGS84 to British National Grid (BNG / EPSG:27700,
    the CRS the DEFRA raster is published in). Asserts the result is in
    the expected range so a basic pyproj/PROJ misconfiguration shows up
    immediately.
    """
    try:
        from pyproj import Transformer
    except ImportError:
        print('Missing dependency: pyproj. Install with:')
        print(' pip install pyproj')
        sys.exit(1)

    # SW1A 1AA, Buckingham Palace area, lat/lon from postcodes.io
    sw1a_lat, sw1a_lon = 51.501009, -0.141588
    # Expected BNG coordinates (well-known, ~10 m precision either way)
    expected_x, expected_y = 529090, 179645

    # DEFRA Round 4 rasters use BNG (EPSG:27700). If a future raster
    # is published in a different CRS the loader picks it up at runtime
    # via raster.crs; this self-test just sanity-checks BNG since that's
    # what every DEFRA raster has used.
    transformer = Transformer.from_crs(
        'EPSG:4326', 'EPSG:27700', always_xy=True,
    )
    x, y = transformer.transform(sw1a_lon, sw1a_lat)

    # Allow ±100 m tolerance, well above transform error, well below
    # any catastrophic axis-swap or units bug.
    dx, dy = abs(x - expected_x), abs(y - expected_y)
    if dx > 100 or dy > 100:
        print(f'FAIL CRS transform off by ({dx:.1f} m, {dy:.1f} m)')
        print(f' Got ({x:.1f}, {y:.1f})')
        print(f' Expected ({expected_x}, {expected_y})')
        sys.exit(1)

    print(f'PASS WGS84 → BNG transform: SW1A 1AA → ({x:.0f}, {y:.0f})')
    print(f' (expected ({expected_x}, {expected_y}), within {max(dx,dy):.1f} m)')
    print('Self-test passed. Pyproj + PROJ data are configured correctly.')


def run_load(limit, dry_run):
    """Sample the raster at NSPL postcode centroids and write to DynamoDB.

    When `dry_run` is True the DynamoDB writes are skipped and the script
    just reports what it would write. When `limit` is set, only that many
    rows of the NSPL CSV are processed (useful for smoke-tests).
    """
    # Lazy imports so this file is readable without the deps installed
    try:
        import rasterio # type: ignore
        import boto3 # type: ignore
        from pyproj import Transformer # type: ignore
        from tqdm import tqdm # type: ignore
    except ImportError as exc:
        print(f'Missing dependency: {exc}')
        print('Install with: pip install rasterio pyproj boto3 tqdm')
        sys.exit(1)

    if not DEFRA_GEOTIFF_PATH.exists():
        print(f'DEFRA GeoTIFF not found at {DEFRA_GEOTIFF_PATH}')
        print('Download from https://www.gov.uk/government/collections/strategic-noise-mapping')
        sys.exit(1)

    if not NSPL_CSV_PATH.exists():
        print(f'NSPL CSV not found at {NSPL_CSV_PATH}')
        print('Download from https://geoportal.statistics.gov.uk/datasets/ons::nspl-online-latest-by-postcode/')
        sys.exit(1)

    # Resume from checkpoint if it exists. Skipped when --limit is set
    # to avoid the limited-run resuming a previous full run.
    checkpoint = 0
    if not limit and CHECKPOINT_PATH.exists():
        checkpoint = int(CHECKPOINT_PATH.read_text().strip() or 0)
        print(f'Resuming from row {checkpoint:,}')

    # Open the raster
    raster = rasterio.open(DEFRA_GEOTIFF_PATH)
    raster_band = raster.read(1)
    raster_transform = raster.transform
    raster_crs = raster.crs

    print(f'Raster: {raster_band.shape[1]}x{raster_band.shape[0]} pixels, CRS={raster_crs}')

    # Postcode WGS84 → raster CRS (likely BNG / EPSG:27700)
    transformer = Transformer.from_crs('EPSG:4326', raster_crs, always_xy=True)

    # DynamoDB, instantiate even in dry-run so a missing AWS profile
    # surfaces immediately rather than after a long sample.
    ddb = boto3.client('dynamodb', region_name=AWS_REGION)
    if dry_run:
        print('DRY-RUN MODE: no DynamoDB writes will be performed.')

    if limit:
        print(f'LIMIT: processing first {limit:,} NSPL rows.')

    # Stream NSPL
    batch = []
    written = 0
    skipped = 0
    samples_logged = 0
    SAMPLE_LOG_LIMIT = 5 # show a few sampled rows so you can eyeball them

    with open(NSPL_CSV_PATH, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(tqdm(reader, desc='postcodes', initial=checkpoint)):
            if idx < checkpoint:
                continue
            if limit and (idx - checkpoint) >= limit:
                break

            try:
                pc = row['pcds'].replace(' ', '').upper()
                lat = float(row['lat'])
                lon = float(row['long'])
            except (KeyError, ValueError):
                skipped += 1
                continue

            # Project to raster CRS
            x, y = transformer.transform(lon, lat)

            # Sample the raster at the pixel containing (x, y)
            try:
                col, row_idx = ~raster_transform * (x, y)
                col, row_idx = int(col), int(row_idx)
                if 0 <= row_idx < raster_band.shape[0] and 0 <= col < raster_band.shape[1]:
                    lden = float(raster_band[row_idx, col])
                else:
                    skipped += 1
                    continue
            except Exception:
                skipped += 1
                continue

            # Skip nodata pixels
            if lden < LDEN_MIN or lden > LDEN_MAX:
                skipped += 1
                continue

            if dry_run and samples_logged < SAMPLE_LOG_LIMIT:
                print(f' sample {samples_logged + 1}: {pc} ({lat:.4f},{lon:.4f}) → {lden:.1f} dB')
                samples_logged += 1

            batch.append({
                'PutRequest': {
                    'Item': {
                        'postcode': {'S': pc},
                        'ldenDb': {'N': f'{lden:.1f}'},
                    }
                }
            })

            if len(batch) >= BATCH_SIZE:
                if not dry_run:
                    ddb.batch_write_item(RequestItems={TABLE_NAME: batch})
                written += len(batch)
                batch.clear()

                # Checkpoint every 1000 rows, only meaningful for full runs
                if not limit and idx % 1000 == 0:
                    CHECKPOINT_PATH.write_text(str(idx))

    # Flush remainder
    if batch:
        if not dry_run:
            ddb.batch_write_item(RequestItems={TABLE_NAME: batch})
        written += len(batch)

    # Clean up checkpoint on success, only on a full uninterrupted run
    if not limit and not dry_run:
        CHECKPOINT_PATH.unlink(missing_ok=True)

    raster.close()
    verb = 'Would have written' if dry_run else 'Wrote'
    print(f'\nDone. {verb}: {written:,} postcodes. Skipped: {skipped:,}.')
    if not dry_run and not limit:
        print('Verify with:')
        print(f' AWS_PROFILE=flightmap aws dynamodb describe-table --table-name {TABLE_NAME} \\')
        print(' --query "Table.ItemCount" --region eu-west-2')


def main():
    args = parse_args()
    if args.self_test:
        self_test()
        return
    run_load(limit=args.limit, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
