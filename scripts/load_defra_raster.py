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

  1. DEFRA Lden GeoTIFF (~500 MB, free, OGL v3.0).

     Strategic noise mapping is published as separate Aircraft and Road
     datasets. For Sky Score's positioning, we recommend the Aircraft
     dataset (the consumer-site differentiator). To combine road +
     aircraft noise, see the "Combined exposure" note below.

     a) Aircraft Noise, All Metrics, England Round 4 (2022):
        https://www.data.gov.uk/dataset/airport-noise-all-metrics-england-round-4
        Or on the publishing service:
        https://ckan.publishing.service.gov.uk/dataset/airport-noise-all-metrics-england-round-4

     b) Road Noise, All Metrics, England Round 4 (2022):
        https://www.data.gov.uk/dataset/38b1444f-47a0-42ca-a358-0d145fcf7d5c/road-noise-all-metrics-england-round-4
        Or: https://environment.data.gov.uk/dataset/562c9d56-7c2d-4d42-83bb-578d6e97a517

     Both pages have a "Download data by area of interest and format"
     tool. Select:
       Area of interest: All of England
       Format: GeoTIFF
       Metric: Lden (day-evening-night, the primary indicator)
     Submit, wait ~5 min for the export, then download.
     Save as `data/defra_lden_2022.tif`.

     Reference (umbrella page):
     https://www.gov.uk/government/publications/strategic-noise-mapping-2022

     Methodology explanation:
     https://www.gov.uk/government/publications/strategic-noise-mapping-2022/explaining-the-2022-noise-maps

     Combined exposure (v2 enhancement, not yet implemented):
     run the loader twice with both rasters and combine via logarithmic
     dB sum: combined = 10*log10(10^(road/10) + 10^(aircraft/10)).
     For v1, pick the single source that matters most for your use case.

  2. ONS National Statistics Postcode Lookup (NSPL). Lat/lon for every UK
     postcode. Free, OGL v3.0. Updated quarterly (Feb / May / Aug / Nov).

     Catalogue page:
     https://www.data.gov.uk/dataset/national-statistics-postcode-lookup-uk

     ONS landing page:
     https://www.ons.gov.uk/methodology/geography/geographicalproducts/postcodeproducts

     Direct CSV download (Feb 2026 release, ~250 MB extracted):
     https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/419355d8a54741f19025ba97e35da55a/csv?layers=0

     Save as `data/nspl.csv`. The script reads the standard columns
     `pcds`, `lat`, `long` (stable across NSPL editions).

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

  # A second city. DEFRA publishes one raster per agglomeration, and the
  # bundled London raster covers only 493005-568005E / 155995-206995N, so
  # Greater Manchester needs its own export and its own pass:
  AWS_PROFILE=flightmap python scripts/load_defra_raster.py \\
    --geotiff data/defra_lden_2022_manchester.tif
  # Each raster keeps its own resume checkpoint, so the second pass does not
  # inherit the first one's progress and skip the CSV.

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

# Shared write policy (adaptive retry, bounded wait, fatal-code list). Sibling
# module, so a plain import works when this is run the documented way - as
# `python scripts/load_defra_raster.py`, which puts scripts/ on sys.path. The
# fallback covers loading this file by path, which is how its tests reach it.
try:
    import ddb_write
except ImportError:  # pragma: no cover - depends on how the file was loaded
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ddb_write

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


# Lden sanity range, DEFRA values are 30-95 dB; pixels outside this
# range are nodata sentinels (often 0, 255, or large negative numbers
# depending on the GeoTIFF encoding).
LDEN_MIN = 30.0
LDEN_MAX = 100.0


def checkpoint_path_for(geotiff):
    """Resume checkpoint, namespaced per raster.

    DEFRA publishes one raster per agglomeration, so covering a second city
    means a second full pass over the same NSPL CSV with a different GeoTIFF.
    A single shared checkpoint file would make that second pass resume from
    wherever the first one finished and skip almost every postcode — a run
    that exits cleanly, prints "Done", and writes nearly nothing.

    Rows are keyed by postcode and the rasters cover disjoint areas, so
    separate passes never contend: each writes only the postcodes inside its
    own bbox and falls through on the rest.
    """
    return Path(f'.defra_load_checkpoint_{Path(geotiff).stem}')


def failures_path_for(geotiff):
    """Postcodes whose write could not be made to land, namespaced like the
    checkpoint and for the same reason: two rasters are two independent passes,
    and merging their failure lists would misattribute every line in it."""
    return Path(f'.defra_load_failures_{Path(geotiff).stem}')


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
        '--geotiff', type=Path, default=DEFRA_GEOTIFF_PATH, metavar='PATH',
        help='DEFRA Lden GeoTIFF to sample. Defaults to the London raster. '
             'DEFRA publishes one raster per agglomeration, so covering a '
             'second city means running this again with that city\'s raster; '
             'rows are keyed by postcode and the bboxes are disjoint, so the '
             'passes do not contend. Each raster gets its own resume '
             'checkpoint.',
    )
    p.add_argument(
        '--attribute', default='ldenDb', metavar='NAME',
        help='DynamoDB attribute to write the sampled value into. Defaults to '
             'ldenDb (aircraft Lden). Use roadLdenDb for the road raster: the '
             'two metrics share one row per postcode, and writes go through '
             'UpdateItem so a road pass merges rather than replacing the '
             'aircraft value. Pair this with --geotiff; getting one right and '
             'the other wrong writes road decibels into the aircraft column, '
             'which nothing downstream would flag.',
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


def _flush_batch(ddb, items, attribute='ldenDb', failures_path=None):
    """Write a batch of (postcode, value) pairs to DynamoDB.

    Originally this used `BatchWriteItem` (25 items per call) for speed,
    but flightmap-dev's IAM policy only grants `PutItem` / `DeleteItem`
    on the table — `BatchWriteItem` is a separate IAM action and was
    denied. Rather than expand IAM, we parallelise per-item writes
    via a ThreadPoolExecutor. ~25 concurrent writes get us throughput
    comparable to BatchWriteItem within DynamoDB's PAY_PER_REQUEST mode.

    UPDATEITEM, NOT PUTITEM (2026-08-06). PutItem REPLACES the whole item, so
    the moment a second metric shares this table — road Lden alongside aircraft
    Lden — a road pass would silently delete every aircraft value it touched.
    UpdateItem with SET merges, leaving other attributes intact. Verified
    against the live table before this change, because `dynamodb:UpdateItem`
    appearing in backend/iam-policy.json proves nothing on its own - that file
    is a record of INTENT, and on 2026-09-03 it described a policy that had
    been replaced wholesale.

    (The example this used to give - BatchWriteItem being denied while present
    in the file - stopped being true on 2026-09-04, when the policy was
    restored and the grant went live. The POINT stands: verify against the
    live account with scripts/check_aws_permissions.py, never against the
    file.)

    SURVIVES A DROPPED CONNECTION (2026-08-09). Every write used to be
    unguarded, so `list(ex.map(...))` re-raised the first worker exception and
    one broken socket ended a multi-hour run. The air-quality loader died that
    way twice, a minute before the machine slept each time. Policy is shared
    with it in ddb_write.py rather than pasted, because the part worth getting
    right is FATAL_CODES and two copies of that list would drift.

    Returns the number of items that actually LANDED, which is not necessarily
    len(items) - callers must add this rather than the batch size.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _put(item):
        ddb.update_item(
            TableName=TABLE_NAME,
            Key={'postcode': {'S': item['postcode']}},
            UpdateExpression='SET #a = :v',
            ExpressionAttributeNames={'#a': attribute},
            ExpressionAttributeValues={':v': {'N': item['value']}},
        )

    with ThreadPoolExecutor(max_workers=25) as ex:
        landed = list(ex.map(lambda it: ddb_write.guarded_put(_put, it), items))

    stalled = [
        it['postcode']
        for it, ok in zip(items, landed, strict=True)
        if not ok
    ]
    if stalled and failures_path is not None:
        ddb_write.record_failures(failures_path, stalled)
    return len(items) - len(stalled)


def run_load(limit, dry_run, geotiff=DEFRA_GEOTIFF_PATH, attribute='ldenDb'):
    """Sample the raster at NSPL postcode centroids and write to DynamoDB.

    When `dry_run` is True the DynamoDB writes are skipped and the script
    just reports what it would write. When `limit` is set, only that many
    rows of the NSPL CSV are processed (useful for smoke-tests).
    """
    # Lazy imports so this file is readable without the deps installed.
    # boto3 is imported by ddb_write.make_client rather than here, but it is
    # still checked, so a missing install fails with the install line below
    # instead of a traceback several hundred thousand rows into a run.
    try:
        import importlib.util

        if importlib.util.find_spec('boto3') is None:
            raise ImportError('boto3')
        import rasterio  # type: ignore
        from pyproj import Transformer  # type: ignore
        from tqdm import tqdm  # type: ignore
    except ImportError as exc:
        print(f'Missing dependency: {exc}')
        print('Install with: pip install rasterio pyproj boto3 tqdm')
        sys.exit(1)

    if not geotiff.exists():
        print(f'DEFRA GeoTIFF not found at {geotiff}')
        print('Download from https://www.gov.uk/government/collections/strategic-noise-mapping')
        sys.exit(1)

    checkpoint_file = checkpoint_path_for(geotiff)
    failures_file = failures_path_for(geotiff)

    if not NSPL_CSV_PATH.exists():
        print(f'NSPL CSV not found at {NSPL_CSV_PATH}')
        print('Download from https://geoportal.statistics.gov.uk/datasets/ons::nspl-online-latest-by-postcode/')
        sys.exit(1)

    # Resume from checkpoint if it exists. Skipped when --limit is set
    # to avoid the limited-run resuming a previous full run.
    checkpoint = 0
    if not limit and checkpoint_file.exists():
        checkpoint = int(checkpoint_file.read_text().strip() or 0)
        print(f'Resuming from row {checkpoint:,}')

    # Open the raster
    raster = rasterio.open(geotiff)
    raster_band = raster.read(1)
    raster_transform = raster.transform
    raster_crs = raster.crs

    print(f'Raster: {raster_band.shape[1]}x{raster_band.shape[0]} pixels, CRS={raster_crs}')

    # Postcode WGS84 → raster CRS (likely BNG / EPSG:27700)
    transformer = Transformer.from_crs('EPSG:4326', raster_crs, always_xy=True)

    # DynamoDB, instantiate even in dry-run so a missing AWS profile
    # surfaces immediately rather than after a long sample.
    # Adaptive retry, not a bare client. See ddb_write for why.
    ddb = ddb_write.make_client(AWS_REGION)
    if dry_run:
        print('DRY-RUN MODE: no DynamoDB writes will be performed.')

    if limit:
        print(f'LIMIT: processing first {limit:,} NSPL rows.')

    # Stream NSPL
    batch = []
    written = 0
    skipped = 0
    nodata_skipped = 0
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
                in_bounds = (0 <= row_idx < raster_band.shape[0]
                             and 0 <= col < raster_band.shape[1])
            except (ValueError, TypeError, OverflowError):
                # Specific exceptions only (audit I-F); ~ inversion can
                # raise ValueError/OverflowError on extreme coords; int()
                # on NaN raises ValueError. Catching Exception bare would
                # swallow KeyboardInterrupt and bugs in the call chain.
                in_bounds = False

            if not in_bounds:
                # Outside raster bbox — fall through to v3.0 Haversine
                # at score-time (no DDB write).
                skipped += 1
                continue

            raw_lden = float(raster_band[row_idx, col])

            # DEFRA Round 4 noise rasters only publish contours for
            # >= 40 dB Lden; below that, pixels carry a NoData sentinel
            # (typically a float-max value ~3.4e38, OR raster.nodata if
            # set). Detect both and treat as "below threshold = quiet".
            #
            # Without this, postcodes inside the bbox but outside any
            # noise contour fell through to Haversine (which estimates
            # noise from geometric proximity to airports), wrongly
            # reporting them as loud. Twickenham was the trigger case:
            # close to LHR but below DEFRA's contour, yet Haversine
            # said quiet=1.0 because of geometric distance.
            nodata = raster.nodata
            is_nodata = (raw_lden > 1e30) or (
                nodata is not None and raw_lden == nodata
            )
            if is_nodata:
                # CHANGED 2026-08-03. This used to write lden = 35.0, chosen so
                # lden_db_to_quiet() returned 10.0, on the reasoning above that a
                # postcode outside every contour is quiet. The reasoning holds for
                # Twickenham and fails for London.
                #
                # Measured across 22,622 live London postcodes: **89.5% fall
                # outside DEFRA's aircraft contours**, because those contours are
                # localised lobes around airports — this raster carries data for
                # only 6.2% of its own grid. Writing 35.0 for all of them put
                # **98% of London on a single quiet value of 10.0**, which is not
                # a scoring component, it is a constant. It also states something
                # DEFRA does not: outside the contours there is no measurement,
                # and "not measured" is not "quiet".
                #
                # Skipping instead leaves no row, so _lookup_lden_raster() returns
                # None and the postcode falls through to the Haversine tier —
                # which is exactly the chain METHODOLOGY §4.5 documents, and which
                # the 35.0 fill was silently defeating by making every uncovered
                # postcode look like a successful raster hit.
                #
                # Twickenham still needs solving, but on its own terms: the fault
                # there is Haversine over-penalising positions laterally offset
                # from a runway, and that wants a corridor-aware distance, not a
                # blanket claim that unmapped means silent.
                nodata_skipped += 1
                continue
            elif raw_lden < LDEN_MIN or raw_lden > LDEN_MAX:
                # Anomalous value (negative, etc) — skip rather than guess
                skipped += 1
                continue
            else:
                lden = raw_lden

            if dry_run and samples_logged < SAMPLE_LOG_LIMIT:
                print(f' sample {samples_logged + 1}: {pc} ({lat:.4f},{lon:.4f}) → {lden:.1f} dB')
                samples_logged += 1

            batch.append({'postcode': pc, 'value': f'{lden:.1f}'})

            if len(batch) >= BATCH_SIZE:
                # Add what LANDED, not the batch size. A batch of 25 with 3
                # stalls put 22 rows in the table, and reporting 25 is the same
                # absent-read-as-present error one layer up from the data.
                if dry_run:
                    written += len(batch)
                else:
                    written += _flush_batch(ddb, batch, attribute, failures_file)
                batch.clear()

            # Checkpoint every 1000 NSPL rows, regardless of whether the
            # batch flushed. Earlier this lived inside the flush branch,
            # so for huge stretches of out-of-bbox postcodes the batch
            # never filled, the flush never ran, and no checkpoint was
            # written before an interrupt. With this we can resume mid-run.
            if not limit and not dry_run and idx > 0 and idx % 1000 == 0:
                checkpoint_file.write_text(str(idx))

    # Flush remainder
    if batch:
        if dry_run:
            written += len(batch)
        else:
            written += _flush_batch(ddb, batch, attribute, failures_file)

    # Clean up checkpoint on success, only on a full uninterrupted run
    if not limit and not dry_run:
        checkpoint_file.unlink(missing_ok=True)

    raster.close()
    verb = 'Would have written' if dry_run else 'Wrote'
    print(f'\nDone. {verb}: {written:,} postcodes. Skipped: {skipped:,}.')

    if not dry_run and failures_file.exists():
        stalled = len(failures_file.read_text(encoding='utf-8').split())
        print(
            f'STALLED: {stalled:,} postcodes could not be written and are NOT '
            f'in the table. Named in {failures_file}; re-run once fixed.'
        )

    if not dry_run and not limit:
        # get-item on a KNOWN postcode, never describe-table's ItemCount: that
        # figure refreshes about every six hours, so it reads 0 for most of a
        # load and a run that wrote nothing looks identical to one that worked.
        print('Verify with:')
        print(f' AWS_PROFILE=flightmap aws dynamodb get-item --table-name {TABLE_NAME} \\')
        print('   --key \'{"postcode":{"S":"SW1A1AA"}}\' --region eu-west-2')


def main():
    args = parse_args()
    if args.self_test:
        self_test()
        return
    run_load(
        limit=args.limit,
        dry_run=args.dry_run,
        geotiff=args.geotiff,
        attribute=args.attribute,
    )


if __name__ == '__main__':
    main()
