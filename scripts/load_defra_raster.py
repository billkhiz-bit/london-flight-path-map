"""
Sky Score v3.1 — DEFRA Lden raster sampler.

One-time batch script that samples the DEFRA Strategic Noise Mapping
(Round 4, 2022) Lden raster at every UK postcode centroid and writes the
results to DynamoDB. Once the table is populated, the score Lambda
automatically uses raster values for the quiet component (highest
precision tier in the resolution chain).

PRE-REQUISITES (run once, locally — not in the Lambda environment):

  pip install rasterio pyproj boto3 requests tqdm

INPUTS NEEDED:

  1. DEFRA Lden GeoTIFF (~500 MB, free download from data.gov.uk):
     https://www.gov.uk/government/collections/strategic-noise-mapping
     Save as `data/defra_lden_2022.tif` relative to project root.

  2. ONS National Statistics Postcode Lookup (NSPL) CSV — gives lat/lon
     for every UK postcode. Free, OGL:
     https://geoportal.statistics.gov.uk/datasets/ons::nspl-online-latest-by-postcode/
     Save as `data/nspl.csv`.

  3. AWS credentials with write access to the `sky-score-noise-raster`
     table (created via SAM template).

USAGE:

  AWS_PROFILE=flightmap python scripts/load_defra_raster.py

EXPECTED RUNTIME:

  ~1.7M postcodes, ~500 writes/sec to DynamoDB on-demand → ~1 hour.
  GeoTIFF read is local (10ms/sample) so the bottleneck is DDB writes.

WHAT IT DOES:

  1. Loads the DEFRA GeoTIFF using rasterio
  2. Streams the NSPL CSV row-by-row (postcode, lat, lon, etc.)
  3. For each postcode, projects lat/lon to the raster's CRS and samples
     the Lden value at that pixel
  4. Batch-writes (postcode, ldenDb) tuples to DynamoDB
  5. Logs progress to stdout; resumable from a checkpoint if interrupted

NOTE: this is the runbook + code template. The actual run requires the
input files locally and an internet connection to DynamoDB. The Lambda
is forward-compatible — it works with or without the table populated.
"""

import csv
import os
import sys
from pathlib import Path

# ---- Configuration ----

DEFRA_GEOTIFF_PATH = Path('data/defra_lden_2022.tif')
NSPL_CSV_PATH = Path('data/nspl.csv')
TABLE_NAME = 'london-flight-map-noise-raster'
AWS_REGION = 'eu-west-2'
BATCH_SIZE = 25  # DynamoDB BatchWriteItem max
CHECKPOINT_PATH = Path('.defra_load_checkpoint')


def main():
    # Lazy imports so this file is readable without the deps installed
    try:
        import rasterio  # type: ignore
        import boto3  # type: ignore
        from pyproj import Transformer  # type: ignore
        from tqdm import tqdm  # type: ignore
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

    # Resume from checkpoint if it exists
    checkpoint = 0
    if CHECKPOINT_PATH.exists():
        checkpoint = int(CHECKPOINT_PATH.read_text().strip() or 0)
        print(f'Resuming from row {checkpoint:,}')

    # Open the raster
    raster = rasterio.open(DEFRA_GEOTIFF_PATH)
    raster_band = raster.read(1)
    raster_transform = raster.transform
    raster_crs = raster.crs

    # Postcode WGS84 → raster CRS (likely BNG / EPSG:27700)
    transformer = Transformer.from_crs('EPSG:4326', raster_crs, always_xy=True)

    # DynamoDB
    ddb = boto3.client('dynamodb', region_name=AWS_REGION)

    # Stream NSPL
    batch = []
    written = 0
    skipped = 0

    with open(NSPL_CSV_PATH, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(tqdm(reader, desc='postcodes', initial=checkpoint)):
            if idx < checkpoint:
                continue

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
            if lden < 30 or lden > 100:
                skipped += 1
                continue

            batch.append({
                'PutRequest': {
                    'Item': {
                        'postcode': {'S': pc},
                        'ldenDb':   {'N': f'{lden:.1f}'},
                    }
                }
            })

            if len(batch) >= BATCH_SIZE:
                ddb.batch_write_item(RequestItems={TABLE_NAME: batch})
                written += len(batch)
                batch.clear()

                # Checkpoint every 1000 rows
                if idx % 1000 == 0:
                    CHECKPOINT_PATH.write_text(str(idx))

    # Flush remainder
    if batch:
        ddb.batch_write_item(RequestItems={TABLE_NAME: batch})
        written += len(batch)

    # Clean up checkpoint on success
    CHECKPOINT_PATH.unlink(missing_ok=True)

    raster.close()
    print(f'\nDone. Written: {written:,} postcodes. Skipped: {skipped:,}.')
    print(f'Verify with:')
    print(f'  AWS_PROFILE=flightmap aws dynamodb describe-table --table-name {TABLE_NAME} --query "Table.ItemCount"')


if __name__ == '__main__':
    main()
