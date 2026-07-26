"""
Sky Score, ONS NSPL postcode-table loader.

One-time (per NSPL vintage) batch script that loads every positioned UK
postcode from the ONS National Statistics Postcode Lookup into the
DynamoDB table `london-flight-map-postcodes`. Once the table is populated
and the score Lambda has `POSTCODE_TABLE` set, postcode resolution is
served locally and postcodes.io is demoted to a fallback for misses.

The Lambda works with or without this table. Nothing here is required for
the API to function: a table miss, a missing table, an unusable centroid,
a terminated postcode without opt-in, or any DynamoDB error all fall
through to postcodes.io exactly as today.

PRE-REQUISITES (run once, locally, never in the Lambda environment):

  pip install boto3 tqdm

  NOTE: no rasterio, no pyproj. Unlike scripts/load_defra_raster.py this
  loader is pure CSV, there is no raster sampling and no CRS transform.
  NSPL already publishes WGS84 lat/long, so the values are copied through
  unchanged at 6 decimal places (~0.1 m, far finer than a postcode unit).

  AWS credentials with write access to `london-flight-map-postcodes`.
  Already covered by the flightmap-dev IAM policy at
  backend/iam-policy.json, which grants DynamoDB PutItem / GetItem /
  DeleteItem / Query / Scan / UpdateItem on
  `arn:aws:dynamodb:eu-west-2:*:table/london-flight-map-*`. The
  `london-flight-map-` prefix is load-bearing, not cosmetic: every ARN in
  that policy is scoped to the wildcard, so a table named anything else is
  both undeployable by SAM and unwritable by flightmap-dev.

INPUT NEEDED:

  ONS National Statistics Postcode Lookup (NSPL), one row per UK postcode,
  live and terminated, with WGS84 centroid and the full ONS geography
  hierarchy. Free. Updated quarterly (Feb / May / Aug / Nov).

  Download (pick "NSPL Online Latest Centroids", CSV):
  https://geoportal.statistics.gov.uk/datasets/ons::nspl-online-latest-by-postcode/

  Catalogue page:
  https://www.data.gov.uk/dataset/national-statistics-postcode-lookup-uk

  Save the extracted CSV as `data/nspl.csv`. `data/*` is gitignored, so the
  805 MB file never enters the repository.

  Columns read (stable across NSPL editions): pcds, doterm, gridind,
  lad25cd, ctry25cd, rgn25cd, lat, long. The 2026-02 edition has 36
  columns and 2,723,596 data rows.

  LICENCE: Office for National Statistics, National Statistics Postcode
  Lookup, released under the Open Government Licence v3.0. Contains OS
  data (c) Crown copyright and database right; Royal Mail data (c) Royal
  Mail copyright and database right; National Statistics data (c) Crown
  copyright and database right.

  The attribution obligation SURVIVES INTO ANY DERIVED EXPORT. The
  Enterprise "score your whole city" CSV is such an export: any file we
  hand a customer that carries these centroids must carry the ONS + OGL
  v3.0 attribution with it. See LICENSING.md.

USAGE (a four-rung escalation ladder, climb it in order):

  # 1. Schema + mapping checks. ~1 second, no AWS, no data scan.
  python scripts/load_nspl.py --self-test

  # 2. Parse the first 100 rows and print 5 mapped items. ~2 seconds,
  #    no AWS calls beyond client construction, no writes.
  python scripts/load_nspl.py --limit 100 --dry-run

  # 3. Real writes for the first 5,000 rows, proves throughput and
  #    credentials. ~10 seconds. Leaves the checkpoint untouched.
  AWS_PROFILE=flightmap python scripts/load_nspl.py --limit 5000

  # 4. The full run. ~6-7 HOURS (measured 2026-07-26), resumable, ~GBP 1.50.
  AWS_PROFILE=flightmap python scripts/load_nspl.py

WHAT IT LOADS AND WHAT IT SKIPS:

  All counts below were measured against the on-disk 2026-02 edition:
  2,723,596 data rows, 805,857,415 bytes.

  SKIP  gridind == '9'
        24,203 rows with no grid reference. Their lat/long carry the
        99.999999 / 0.000000 sentinel pair.

        EMPIRICAL NOTE: in this edition that single test excludes exactly
        the full unloadable set. The 13,156 Channel Islands (L93000001)
        and Isle of Man (M83000003) rows plus the 11,047 blank-geography
        GB rows are both strict subsets of it, and 13,156 + 11,047 =
        24,203 exactly. The two tests below are defence-in-depth for
        future editions, not currently load-bearing.

        NEVER test the sentinel with `long == 0`. Longitude 0 is a
        legitimate London value, postcodes sit on both sides of the
        Greenwich meridian (SE10 9NF is -0.006020). `gridind == '9'` was
        verified to match the lat >= 99 set exactly, with no discrepancy.

  SKIP  ctry25cd in {'L93000001', 'M83000003'}
        Channel Islands and Isle of Man. Never positioned by ONS.

  SKIP  blank lad25cd or blank ctry25cd
        No usable geography. 11,047 rows, of which 1,667 are LIVE.

  LOAD  terminated postcodes (doterm non-empty), tagged with `dt`.
        904,453 of the loadable rows.

        Rationale: terminated postcodes still appear in Land Registry
        Price Paid records, EPC certificates and customer back-books, and
        postcodes.io 404s every one of them. Loading them is a genuine
        coverage differentiator and costs ~GBP 0.50 one-off (904,453 WRU
        at the rates in the cost block below).

        WARNING: 36.9% of terminated London rows are coarse-positioned
        (gridind 5 / 6 / 8, meaning imputed, sector-mean, or pre-Gridlink)
        against 0.3% of live London rows. A sector-mean centroid can sit
        hundreds of metres out, easily across a flight-path contour band.
        That is precisely why the Lambda hides terminated postcodes behind
        `?includeTerminated=true` and surfaces `positionQuality` when it
        does serve them. Do not let a terminated row masquerade as a live
        building-level one.

  RESULT  2,699,393 rows written.
          1,794,940 live + 904,453 terminated.
          London (E09) = 332,308, being 180,983 live + 151,325 terminated.

  Non-London rows are loaded WITHOUT a `b` attribute. That is deliberate:
  the resolver returns admin_district = None for them, which produces the
  existing "Borough not currently supported" 404 byte-for-byte unchanged.
  A UK-wide table is the whole point, a London-only table would leave
  postcodes.io carrying exactly the load we are trying to remove.

  The loader also writes a `__META__` provenance singleton, last, and only
  after a run that reaches the end of the CSV. No real postcode contains
  an underscore, so it cannot collide. Nothing in the Lambda reads it; it
  exists for operators and the future offline city-scale scorer.

  Because it is provenance, and therefore trusted, a WRONG one is worse
  than none. The loader refuses to replace a good record with a
  degenerate one: a run that wrote zero rows (schema drift skips every
  row while the table keeps its previous, now mislabelled, contents), a
  run resumed from a checkpoint whose totals cannot be reconstructed, or
  a run that wrote far fewer rows than the load it would replace (a
  truncated download). On refusal it prints the item as a ready-to-paste
  put-item so an operator can stamp it by hand after checking.

EXPECTED RUNTIME, COST AND RESUMABILITY:

  MEASURED 2026-07-26 (first real full run, start to finish): 2,699,393 rows
  in 5.80 HOURS wall-clock, ~129 rows/s sustained at the default 64 workers.
  Plan around ~6 hours.

  The estimate this paragraph used to carry — ~1,300/s and ~35 minutes — was
  roughly 10x optimistic and should not be trusted again. It extrapolated
  linearly from the DEFRA loader's ~500 writes/s at 25 workers, which assumed
  both that throughput scales with worker count and that per-item PutItem
  matches BatchWriteItem throughput (see the note above _flush_batch). Neither
  held. The run is CPU-bound on the CLIENT, not throttled by DynamoDB: 2.7M
  individual HTTPS requests each pay TLS plus SigV4 signing, and the process
  burns far more CPU than an I/O-bound job should. Raising --workers will not
  fix this and may make it worse.

  THE REAL FIX FOR THE NEXT QUARTERLY ROLL is one line of IAM: grant
  dynamodb:BatchWriteItem on london-flight-map-* in backend/iam-policy.json,
  then switch _flush_batch to BatchWriteItem (25 items per signed request,
  ~25x fewer round trips). The current per-item design exists ONLY because
  that action is not granted, not because it is preferable.

  A brand-new PAY_PER_REQUEST table also ramps its capacity rather than
  starting at full throughput, so the first few minutes are slower still.

  Throttling is handled by boto3 adaptive retry (max_attempts 10), which
  adds client-side rate limiting when DynamoDB pushes back, so the run
  self-throttles and continues instead of dying. Lower --workers if
  throttling still dominates.

  COST. Every figure below is eu-west-2 on-demand at the rates published
  on 2026-07-25; re-check them at the next quarterly reload. DynamoDB last
  cut its write price in November 2024, and the pre-cut rate was exactly
  double the current one, so a stale quote here is a 2x error.

    Rate basis: USD 0.7065 per million write request units, USD 0.1413
    per million read request units, USD 0.306 per GB-month storage,
    USD 0.22 per GB-month PITR. Converted at USD 1 ~= GBP 0.79.

    WRITES, one-off. Every item is far under 1 KB, so 1 WRU each:
      2,699,393 WRU = USD 1.91 ~= GBP 1.50 for the full load.

    STORAGE, monthly. Item sizes measured through _row_to_item over all
    2,723,596 rows run from 39 bytes (a live Northern Irish postcode:
    key, lat, lon, lad and nothing else) to 85 bytes (a terminated,
    coarse-positioned London one carrying b, rgn, dt and q), mean 58.8.
    DynamoDB adds ~100 bytes of per-item overhead, so 2,699,393 items at
    ~159 bytes ~= 429 MB:
      storage   0.429 GB x USD 0.306 = USD 0.13/month
      PITR      0.429 GB x USD 0.22  = USD 0.09/month
                PointInTimeRecoveryEnabled is true on this table, see
                backend/template.yaml. It is easy to forget and it is
                roughly 40% of the bill.
      TOTAL     ~USD 0.23/month ~= GBP 0.18/month

    READS. An eventually-consistent GetItem on a sub-4 KB item is 0.5
    RRU, so a 100,000-postcode Enterprise backfill is 50,000 RRU =
    USD 0.007 against this table (USD 0.014 including the paired
    noise-raster GetItem), and 1,000,000 scores cost USD 0.07.

  Interrupt at any time with Ctrl-C. Re-running resumes from the last
  checkpoint in `.nspl_load_checkpoint`, a small JSON object carrying the
  row index, the running counters and the NSPL vintage it was taken
  against. It is written atomically (temp file + os.replace) and ONLY at
  an instant when the write buffer is empty, so it can never name a row
  whose item has not already reached DynamoDB. Rows processed after the
  last checkpoint are re-done on resume, which is harmless: PutItem with
  the same key is a full idempotent overwrite. A from-scratch re-run is
  equally safe, just slower. There is no partial-item state to reconcile
  and no delete pass; a re-run against an existing table converges to the
  same contents.

  The counters travel with the row index so that a resumed run's __META__
  describes the whole load and not just its final segment. A checkpoint
  from a different vintage, an unparseable one, or one predating this
  format is refused or downgraded rather than trusted: a wrong resume
  index is the single failure mode that leaves silent holes, and a hole
  is invisible in production because the Lambda falls back to
  postcodes.io on a miss.

  The checkpoint is only deleted after a run reaches the end of the CSV.
  --limit and --dry-run never read it and never delete it.

VERIFICATION AFTER LOAD (also printed at the end of a clean run):

  AWS_PROFILE=flightmap aws dynamodb describe-table --table-name london-flight-map-postcodes --query "Table.ItemCount" --region eu-west-2
    ItemCount is refreshed roughly every six hours, so it lags a fresh
    load. The get-item checks below are the immediate proof.

  AWS_PROFILE=flightmap aws dynamodb get-item --table-name london-flight-map-postcodes --key '{"postcode":{"S":"SW111AA"}}' --region eu-west-2
    expect b = Wandsworth

  AWS_PROFILE=flightmap aws dynamodb get-item --table-name london-flight-map-postcodes --key '{"postcode":{"S":"E16AN"}}' --region eu-west-2
    expect b = City of London (boundary check, NOT Tower Hamlets)

  AWS_PROFILE=flightmap aws dynamodb get-item --table-name london-flight-map-postcodes --key '{"postcode":{"S":"BR11HB"}}' --region eu-west-2
    expect dt = 198412 and q = 8 (terminated + coarse)

  AWS_PROFILE=flightmap aws dynamodb get-item --table-name london-flight-map-postcodes --key '{"postcode":{"S":"__META__"}}' --region eu-west-2

  curl -s -H "x-api-key: $KEY" "https://api.skyscore.co.uk/v1/score?postcode=SW11+1AA" | jq '.location, .sources[2]'
    sources[2] should credit ONS NSPL with postcodes.io as fallback once
    POSTCODE_TABLE is set on the Lambda.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 stdout so the arrows / pound signs / borough names in our help
# text and progress lines render on Windows cp1252 consoles. Python 3.7+.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ---- Configuration ----

NSPL_CSV_PATH = Path('data/nspl.csv')  # relative to the repo root; run from the repo root
TABLE_NAME = 'london-flight-map-postcodes'
AWS_REGION = 'eu-west-2'
BATCH_SIZE = 500  # rows buffered before a parallel flush
WRITE_WORKERS = 64  # default concurrency; --workers overrides
CHECKPOINT_PATH = Path('.nspl_load_checkpoint')
CHECKPOINT_EVERY = 1000
NSPL_VINTAGE = '2026-02'
META_KEY = '__META__'
EXCLUDED_COUNTRIES = {'L93000001', 'M83000003'}  # Channel Islands, Isle of Man
LAT_SENTINEL = 99.0  # unpositioned rows carry lat 99.999999

# Expected NSPL header width and the subset of columns we actually read.
EXPECTED_HEADER_LEN = 36
REQUIRED_COLUMNS = ('pcds', 'doterm', 'gridind', 'lad25cd', 'ctry25cd', 'rgn25cd', 'lat', 'long')

# LAD25 code -> canonical London borough name.
#
# These 33 strings MUST be byte-identical to the LONDON_BOROUGHS keys in
# backend/lambdas/score/app.py. normalise_borough() is a plain case-sensitive
# dict membership test followed by one alias lookup, and calc_score() then
# indexes boroughs[name] directly, so a single character out and the postcode
# 404s with "Borough not currently supported".
#
# House rules, all three of which differ from how ONS writes them elsewhere:
#   'and' never '&'          -> 'Barking and Dagenham', not 'Barking & Dagenham'
#   lowercase 'upon'         -> 'Kingston upon Thames', not 'Kingston Upon Thames'
#   no honorific prefixes    -> 'Kensington and Chelsea', not
#                               'Royal Borough of Kensington and Chelsea'
# The one exception is E09000001, which keeps its 'City of' because that is
# the borough's actual name and the canonical key.
#
# This map lives HERE, in the offline loader, and must never be copied into the
# Lambda. Audit item I4 was closed on 2026-07-24 by making score/app.py the
# single holder of borough metadata; a LAD-code-to-name table in the Lambda
# would reopen it by creating a second borough table in a second place. With
# the name denormalised into the data, a boundary change or a rename is a data
# reload, not a Lambda deploy.
#
# Verified against the on-disk file: exactly these 33 distinct E09 codes appear,
# and no others, across 332,308 rows.
LONDON_LAD_TO_BOROUGH = {
    'E09000001': 'City of London',
    'E09000002': 'Barking and Dagenham',
    'E09000003': 'Barnet',
    'E09000004': 'Bexley',
    'E09000005': 'Brent',
    'E09000006': 'Bromley',
    'E09000007': 'Camden',
    'E09000008': 'Croydon',
    'E09000009': 'Ealing',
    'E09000010': 'Enfield',
    'E09000011': 'Greenwich',
    'E09000012': 'Hackney',
    'E09000013': 'Hammersmith and Fulham',
    'E09000014': 'Haringey',
    'E09000015': 'Harrow',
    'E09000016': 'Havering',
    'E09000017': 'Hillingdon',
    'E09000018': 'Hounslow',
    'E09000019': 'Islington',
    'E09000020': 'Kensington and Chelsea',
    'E09000021': 'Kingston upon Thames',
    'E09000022': 'Lambeth',
    'E09000023': 'Lewisham',
    'E09000024': 'Merton',
    'E09000025': 'Newham',
    'E09000026': 'Redbridge',
    'E09000027': 'Richmond upon Thames',
    'E09000028': 'Southwark',
    'E09000029': 'Sutton',
    'E09000030': 'Tower Hamlets',
    'E09000031': 'Waltham Forest',
    'E09000032': 'Wandsworth',
    'E09000033': 'Westminster',
}

# ONS region (former GOR) code -> name. England only; region is an
# England-only geography, so Scottish / Welsh / Northern Irish rows carry a
# 'S99999999'-style placeholder that simply misses this map and gets no `rgn`.
#
# Verified: all 332,308 E09 rows carry rgn25cd = E12000007, so `region` is
# 'London' for every postcode that can ever reach a 200 response.
REGION_CODE_TO_NAME = {
    'E12000001': 'North East',
    'E12000002': 'North West',
    'E12000003': 'Yorkshire and The Humber',
    'E12000004': 'East Midlands',
    'E12000005': 'West Midlands',
    'E12000006': 'East of England',
    'E12000007': 'London',
    'E12000008': 'South East',
    'E12000009': 'South West',
}


def _positive_limit(value):
    """argparse type for --limit. A row count below 1 is rejected, not coerced.

    `--limit 0` is the dangerous one, because 0 is falsy and every guard in
    run_load() spells the limit test as a plain truth test: the checkpoint is
    read instead of the state being zeroed, `idx - resume_from >= 0` is true on
    the first row but only checked as `if limit and ...` so it never breaks, and
    the end-of-run block stamps __META__ and unlinks the checkpoint. So
    `--limit 0` runs the FULL 2.7M-row load WITH WRITES ON and then deletes the
    resume state of any real run in flight, which is the exact opposite of what
    --limit's own help text promises.

    Rejecting beats silently treating 0 as "the full run" (that is what --limit
    means already, by omission) and beats clamping it to 1 (an operator who
    typed 0 meant something we cannot infer). Failing at parse time also costs
    nothing: it happens before the CSV is opened and before any AWS client
    exists.
    """
    try:
        rows = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{value!r} is not an integer')
    if rows < 1:
        raise argparse.ArgumentTypeError(
            f'must be 1 or more (got {rows}); omit --limit entirely for the full run')
    return rows


def parse_args():
    p = argparse.ArgumentParser(
        description='Load the ONS NSPL postcode table into DynamoDB '
                    f'({TABLE_NAME}). See the module docstring for the full '
                    'runbook: download URL, licence, skip policy, cost, '
                    'runtime and post-load verification.',
    )
    p.add_argument(
        '--limit', type=_positive_limit, default=None, metavar='N',
        help='Process only the first N rows of the NSPL CSV. Use this to prove '
             'the pipeline before committing to the full 2.7M-row run. A '
             'limited run deliberately IGNORES the checkpoint file: it neither '
             'resumes from it nor deletes it, so a --limit smoke test can '
             'never truncate or corrupt a real full run that is part-way '
             'through. --limit 5000 takes about 10 seconds with writes on. N '
             'must be 1 or more; 0 and negatives are rejected rather than read '
             'as "no limit", which would silently run the whole load.',
    )
    p.add_argument(
        '--dry-run', action='store_true',
        help='Parse and map rows but perform no DynamoDB writes, printing the '
             'first 5 mapped items as DynamoDB low-level JSON so you can '
             'eyeball the attribute shape. The boto3 client is still built, so '
             'a missing or wrong AWS_PROFILE still surfaces in seconds. Like '
             '--limit it IGNORES the checkpoint, and it always starts at row 0 '
             'so its totals cover every row it claims to have examined. Pair '
             'with --limit 100 for a ~2 second end-to-end smoke test.',
    )
    p.add_argument(
        '--self-test', action='store_true',
        help='Schema and mapping checks only: BOM handling, header width, the '
             'required columns, the 33-borough map, the spaced-postcode '
             'invariant and the unpositioned-row sentinel rule. Reads the '
             'header plus the first 2,000 rows, makes no AWS calls and needs '
             'no boto3. Runs in about a second. Exits afterwards.',
    )
    p.add_argument(
        '--workers', type=int, default=WRITE_WORKERS, metavar='N',
        help=f'Concurrent PutItem workers per flush (default {WRITE_WORKERS}). '
             'Raising it past ~64 rarely helps because a new PAY_PER_REQUEST '
             'table ramps its capacity gradually. LOWER it (try 16) if the run '
             'is dominated by throttling retries; adaptive retry will keep the '
             'run alive either way, but a lower ceiling wastes fewer retries.',
    )
    return p.parse_args()


def self_test():
    """Verify the CSV schema and the mapping tables without scanning the data.

    The NSPL analogue of the DEFRA loader's CRS self-test. Reads only the
    header and the first 2,000 rows, touches no AWS service and does not
    import boto3, so it is safe and instant on any machine that has the CSV.

    Every check prints PASS or FAIL. Any failure exits 1.
    """
    failures = []

    def check(number, ok, label, detail=''):
        status = 'PASS' if ok else 'FAIL'
        print(f'{status} {number}. {label}')
        if detail:
            print(f'       {detail}')
        if not ok:
            failures.append(number)

    def check_borough_map():
        """Check 3. The only check that needs no input file, because it guards a
        Lambda-visible contract (borough names) rather than the CSV schema."""
        names = list(LONDON_LAD_TO_BOROUGH.values())
        check(
            3, len(LONDON_LAD_TO_BOROUGH) == 33 and len(set(names)) == 33,
            'LONDON_LAD_TO_BOROUGH has 33 codes mapping to 33 distinct names',
            f'{len(LONDON_LAD_TO_BOROUGH)} codes, {len(set(names))} distinct names',
        )

    if not NSPL_CSV_PATH.exists():
        # Still report check 3 so a machine without the 805 MB download gets
        # something useful out of --self-test.
        check_borough_map()
        print(f'FAIL NSPL CSV not found at {NSPL_CSV_PATH.resolve()}')
        print('     Download from '
              'https://geoportal.statistics.gov.uk/datasets/ons::nspl-online-latest-by-postcode/')
        print('     Save the extracted CSV as data/nspl.csv and run from the repo root.')
        sys.exit(1)

    with open(NSPL_CSV_PATH, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        sample = []
        for idx, row in enumerate(reader):
            if idx >= 2000:
                break
            sample.append(row)

    # 1. BOM regression guard. The file is UTF-8 WITH a BOM; opened as plain
    #    'utf-8' the first key comes back as U+FEFF + 'pcd7' (an invisible
    #    prefix, named rather than pasted so this file stays pure ASCII) and
    #    every lookup of a first-column name silently misses.
    first_key = header[0] if header else '<empty>'
    check(
        1, first_key == 'pcd7',
        "first DictReader key is 'pcd7' (utf-8-sig strips the BOM)",
        f'got {first_key!r}',
    )

    # 2. Header width and the columns we actually read.
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    check(
        2, len(header) == EXPECTED_HEADER_LEN and not missing,
        f'header has {EXPECTED_HEADER_LEN} columns and all required columns present',
        f'got {len(header)} columns; missing: {missing or "none"}',
    )

    check_borough_map()

    # 4. Spaced-form invariant. The Lambda derives the display postcode as
    #    key[:-3] + ' ' + key[-3:] rather than storing pcds, which is only sound
    #    while the inward code is always the final three characters. Verified
    #    across all 2,723,596 rows of this edition with zero violations; this
    #    check catches a future edition changing the format.
    bad_spacing = []
    for row in sample:
        pcds = (row.get('pcds') or '').strip()
        pc = pcds.replace(' ', '').upper()
        if not pc:
            continue
        if f'{pc[:-3]} {pc[-3:]}' != pcds:
            bad_spacing.append(pcds)
    check(
        4, not bad_spacing,
        f"spaced-form invariant holds on all {len(sample):,} sampled rows",
        f'violations: {bad_spacing[:3] or "none"}',
    )

    # 5. Sentinel rule. Unpositioned rows are identified by gridind == '9', not
    #    by a coordinate test. Longitude 0 is a legitimate London value, so
    #    `long == 0` must never be used as the sentinel.
    sentinel_without_flag = []
    flag_without_sentinel = []
    for row in sample:
        gridind = (row.get('gridind') or '').strip()
        try:
            lat = float(row.get('lat') or 'nan')
        except ValueError:
            lat = float('nan')
        if gridind == '9' and not lat >= LAT_SENTINEL:
            flag_without_sentinel.append(row.get('pcds'))
        if gridind != '9' and lat >= LAT_SENTINEL:
            sentinel_without_flag.append(row.get('pcds'))
    check(
        5, not sentinel_without_flag and not flag_without_sentinel,
        "gridind == '9' matches lat >= 99.0 exactly on the sample",
        f'gridind 9 without sentinel lat: {flag_without_sentinel[:3] or "none"}; '
        f'sentinel lat without gridind 9: {sentinel_without_flag[:3] or "none"}',
    )

    if failures:
        print(f'\nSelf-test FAILED ({len(failures)} check(s): {sorted(failures)}).')
        print('Do not run the loader until these pass; a schema drift here means '
              'either silently wrong items or a silently empty table.')
        sys.exit(1)

    print('\nSelf-test passed. Schema, borough map and sentinel rule all check out.')


def _row_to_item(row):
    """Map one NSPL CSV row to a DynamoDB item, or None if the row is skipped.

    PURE: no I/O, no AWS, no globals beyond the module-level config maps. This
    is the unit-testable core, so ALL skip logic lives here rather than in the
    scan loop.

    Optional attributes are OMITTED when they carry the default value, so
    absence is meaningful and the common case is the cheapest item:
      no `b`   -> not one of the 33 London boroughs
      no `rgn` -> region is an England-only geography
      no `dt`  -> the postcode is LIVE (presence of `dt` IS the terminated flag)
      no `q`   -> building-level positional quality (gridind 1)

    `pcds` is deliberately NOT stored. The Lambda derives the spaced display
    form from the key, which removes an attribute from 2.7M items and removes a
    field that could drift out of sync with the key it duplicates.

    NEVER add a bare `except Exception` here or in the caller's row loop (audit
    finding I-F): it swallows KeyboardInterrupt on a 40-minute run and hides
    real bugs behind a skip counter.
    """
    try:
        pcds = row['pcds']
        gridind = row['gridind']
        lad = row['lad25cd']
        ctry = row['ctry25cd']
        doterm = row['doterm']
        rgn = row['rgn25cd']
    except KeyError:
        # Column absent from the header entirely, i.e. a schema change. The
        # self-test exists to catch this before a full run starts.
        return None

    # DictReader yields None for a short row's trailing fields, so normalise
    # before any string method touches these.
    gridind = (gridind or '').strip()
    lad = (lad or '').strip()
    ctry = (ctry or '').strip()
    doterm = (doterm or '').strip()
    rgn = (rgn or '').strip()

    # Unpositioned, or no usable geography. See the docstring's skip policy.
    if gridind == '9' or not lad or not ctry or ctry in EXCLUDED_COUNTRIES:
        return None

    try:
        lat = float(row['lat'])
        lon = float(row['long'])
    except (KeyError, TypeError, ValueError):
        # TypeError matters as much as ValueError here: csv.DictReader yields
        # None (restval) for a short row's trailing fields, and float(None)
        # raises TypeError, not ValueError. The row loop has no bare
        # `except Exception` by design (audit I-F), so an escaping TypeError
        # would kill a 40-minute run outright. The Lambda's mirror-image
        # coercion in _lookup_postcode_local catches the same three.
        return None

    # Belt and braces behind the gridind test. Never test `lon == 0`: longitude
    # 0 is a real London value (SE10 9NF is -0.006020) and postcodes sit on both
    # sides of the Greenwich meridian.
    if lat >= LAT_SENTINEL:
        return None

    # Key format is byte-identical to london-flight-map-noise-raster so one
    # normalisation serves both tables and they can be merged later without a
    # re-key. Max key length is 7 characters across all 2,723,596 rows.
    pc = (pcds or '').strip().replace(' ', '').upper()
    if not pc:
        return None

    item = {
        'postcode': {'S': pc},
        'lat': {'N': f'{lat:.6f}'},
        'lon': {'N': f'{lon:.6f}'},
        'lad': {'S': lad},
    }

    borough = LONDON_LAD_TO_BOROUGH.get(lad)
    if borough:
        item['b'] = {'S': borough}

    region = REGION_CODE_TO_NAME.get(rgn)
    if region:
        item['rgn'] = {'S': region}

    if doterm:
        item['dt'] = {'S': doterm}

    if gridind and gridind != '1':
        item['q'] = {'N': gridind}

    return item


def _flush_batch(ddb, items, workers):
    """Write a buffered batch of already-mapped items to DynamoDB.

    Parallel per-item PutItem, never BatchWriteItem and never the boto3
    resource-level batch_writer(). MEASURED 2026-07-26: this reaches only
    ~130 rows/s, NOT the "comparable to BatchWriteItem" claimed below — the
    run is client-CPU-bound on 2.7M separate TLS + SigV4 handshakes. Granting
    dynamodb:BatchWriteItem and switching to it is the single highest-value
    change to this script. flightmap-dev's IAM policy grants PutItem /
    GetItem / DeleteItem / Query / Scan / UpdateItem on `london-flight-map-*`;
    BatchWriteItem is a separate IAM action and is not granted. Expanding IAM
    is not the fix, and the loader deliberately does not need it: a
    ThreadPoolExecutor of per-item PutItems reaches throughput comparable to
    BatchWriteItem under PAY_PER_REQUEST.

    Throttling is absorbed by the client's adaptive retry configuration (see
    run_load), which rate-limits client-side on a ProvisionedThroughputExceeded
    response rather than failing the batch and forcing a checkpoint resume.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _put(item):
        ddb.put_item(TableName=TABLE_NAME, Item=item)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_put, items))


# Resume state for a from-scratch run. `row` is the last row FULLY ACCOUNTED
# FOR, so a resume starts at row + 1. `countsComplete` records whether the
# running totals can be trusted to describe the WHOLE load: it drops to False
# when a checkpoint carries a usable row index but not the counters behind it,
# and it is sticky from that point on so the flag survives further resumes and
# still reaches _write_meta().
_ZERO_STATE = {
    'row': 0,
    'written': 0,
    'skipped': 0,
    'terminated': 0,
    'london': 0,
    'mismatches': 0,
    'countsComplete': True,
}
_COUNTER_KEYS = ('row', 'written', 'skipped', 'terminated', 'london', 'mismatches')


def _write_checkpoint(state):
    """Persist resume state atomically.

    Written to a sibling temp file and os.replace()d into position. A plain
    write_text() truncates before it writes, so a Ctrl-C landing inside that
    window leaves a zero-byte checkpoint and throws away a 35-minute run.
    os.replace() is atomic on both POSIX and Windows, so the file on disk is
    always either the previous complete JSON object or the new one.

    The counters ride along with the row index deliberately: a resumed run has
    to know what the earlier segments wrote, or the __META__ it stamps at the
    end describes only its own final segment. See _write_meta().
    """
    payload = dict(state)
    payload['vintage'] = NSPL_VINTAGE
    tmp = CHECKPOINT_PATH.parent / (CHECKPOINT_PATH.name + '.tmp')
    tmp.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    os.replace(tmp, CHECKPOINT_PATH)


def _read_checkpoint():
    """Load resume state, or _ZERO_STATE if there is nothing usable to resume.

    Every failure path here restarts the load from row 0. Re-writing rows that
    are already in the table costs time and write units but cannot corrupt
    anything: PutItem on the same key is a full idempotent overwrite. Resuming
    on a half-understood checkpoint is the only outcome that can silently leave
    holes, so it is never the fallback.
    """
    state = dict(_ZERO_STATE)
    if not CHECKPOINT_PATH.exists():
        return state

    # The read itself is a failure path like any other, so it is inside a try:
    # a checkpoint that is not valid UTF-8 (say it was rewritten by a tool that
    # emits UTF-16) would otherwise abort the loader with a raw
    # UnicodeDecodeError out of pathlib, while every other corruption mode here
    # restarts cleanly from row 0. UnicodeDecodeError is a ValueError, not an
    # OSError, so both roots are named.
    try:
        raw = CHECKPOINT_PATH.read_text(encoding='utf-8').strip()
    except (OSError, UnicodeDecodeError) as exc:
        print(f'{CHECKPOINT_PATH} could not be read ({exc}); starting from row 0.')
        return state

    if not raw:
        print(f'{CHECKPOINT_PATH} is empty; starting from row 0.')
        return state

    try:
        saved = json.loads(raw)
    except ValueError:
        print(f'{CHECKPOINT_PATH} is unreadable ({raw[:40]!r}); starting from row 0.')
        return dict(_ZERO_STATE)

    # Checkpoints written before 2026-07-25 were a bare row index, and that
    # index was recorded WITHOUT regard to whether the write buffer had been
    # flushed: it can sit up to BATCH_SIZE-1 items ahead of what actually
    # reached DynamoDB. Resuming from it is what left silent holes in the first
    # place, so it is not honoured. Re-scanning from row 0 costs ~6-7 hours and
    # ~GBP 1.50 of idempotent re-writes; a hole costs a wrong answer that
    # nothing detects.
    #
    # The test sits HERE, after the parse, because that is where a bare index
    # actually lands: json.loads('5000') does not raise, it returns int 5000.
    # `bool` is excluded because it is an int subclass and a bare `true` is
    # garbage rather than a legacy row index, so it belongs in the message
    # below.
    if isinstance(saved, int) and not isinstance(saved, bool):
        print(f'{CHECKPOINT_PATH} is a pre-2026-07-25 bare row index, which could '
              'be written before its rows were flushed. Ignoring it and starting '
              'from row 0 rather than resuming past rows that may never have been '
              'written. Delete it to silence this on the next run.')
        return dict(_ZERO_STATE)

    if not isinstance(saved, dict):
        print(f'{CHECKPOINT_PATH} is not a checkpoint object; starting from row 0.')
        return dict(_ZERO_STATE)

    # A row index only means anything against the CSV it was counted from.
    # Resuming a 2026-02 checkpoint against a 2026-05 download would skip to an
    # index pointing somewhere else entirely in the new file.
    if saved.get('vintage') != NSPL_VINTAGE:
        print(f'Checkpoint was taken against NSPL vintage {saved.get("vintage")!r} but '
              f'this run is {NSPL_VINTAGE!r}; ignoring it and starting from row 0.')
        return dict(_ZERO_STATE)

    for key in _COUNTER_KEYS:
        try:
            state[key] = int(saved.get(key, 0))
        except (TypeError, ValueError):
            print(f'Checkpoint field {key!r} is not a number; starting from row 0.')
            return dict(_ZERO_STATE)
    # Absent means "written by something that did not track this", so assume the
    # conservative answer rather than the convenient one.
    state['countsComplete'] = bool(saved.get('countsComplete', False))
    return state


# A completed run must not replace good provenance with a worse record. Reload
# vintages grow (NSPL has never shrunk between editions), so a load that comes
# in materially under the one it would replace is a truncated download, not a
# smaller Britain.
META_MIN_FRACTION_OF_PREVIOUS = 0.9


def _previous_meta_rows(ddb):
    """Return (read_succeeded, rowsWritten of the existing __META__ or None)."""
    try:
        from botocore.exceptions import BotoCoreError, ClientError  # type: ignore
    except ImportError:  # pragma: no cover - botocore is imported by run_load first
        BotoCoreError = ClientError = ()

    try:
        resp = ddb.get_item(TableName=TABLE_NAME, Key={'postcode': {'S': META_KEY}})
    except (BotoCoreError, ClientError) as exc:
        # Deliberately narrow, and deliberately NOT `except Exception` (audit
        # finding I-F). Both botocore roots are caught because a throttle, a
        # missing table and an expired credential all mean the same thing here:
        # we cannot see what we are about to overwrite.
        print(f'Could not read the existing {META_KEY}: {exc}')
        return False, None

    item = resp.get('Item')
    if not item:
        return True, None
    try:
        return True, int(item['rowsWritten']['N'])
    except (KeyError, TypeError, ValueError):
        return True, None


def _write_meta(ddb, written, skipped, mismatches, counts_complete):
    """Write the `__META__` load-provenance singleton, unless that would replace
    a good record with a degenerate one.

    Called ONLY at the end of a run that reached the end of the CSV, never
    under --limit or --dry-run. A resumed run arrives here with its counters
    seeded from the checkpoint, so `written` and `skipped` describe the WHOLE
    load and not merely the final segment.

    '__META__' cannot collide with a real postcode: no UK postcode contains an
    underscore. Nothing in the Lambda reads this item; it exists so an operator
    (or the future offline city-scale scorer) can tell which NSPL vintage is in
    the table and under what skip policy it was loaded. That is exactly why a
    wrong one is worse than none: it is provenance, and it is trusted.

    Four refusals, every one of which fires on a run that finished CLEANLY,
    which is precisely when the counts look authoritative and are not:

      counts_complete=False   resumed from a checkpoint that carried a usable
                              row index but not the counters behind it, so the
                              totals under-count by an unknown amount.
      written == 0            schema drift. _row_to_item() catches KeyError and
                              returns None, so one renamed column (lad25cd ->
                              lad26cd in a future NSPL edition) skips all 2.7M
                              rows without raising. The table keeps its previous
                              contents, so stamping vintage + rowsWritten=0 over
                              them would mislabel good data.
      previous unreadable     cannot see what is about to be overwritten.
      written << previous     a truncated or partial download. The run is clean
                              and every row it saw was loaded; the file was
                              short.

    On refusal the item is printed as a ready-to-paste put-item, so an operator
    who has checked the run can stamp it by hand without paying for another
    35-minute reload.

    Returns True if the item was written.
    """
    item = {
        'postcode': {'S': META_KEY},
        'vintage': {'S': NSPL_VINTAGE},
        'loadedAt': {'S': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')},
        'rowsWritten': {'N': str(written)},
        'rowsSkipped': {'N': str(skipped)},
        'policy': {'S': 'UK-wide; gridind=9 excluded; terminated loaded and tagged via dt'},
        'source': {'S': 'ONS NSPL via Geoportal, Open Government Licence v3.0'},
    }
    # Only recorded when non-zero, so its presence is itself the alarm.
    if mismatches:
        item['pcdsMismatches'] = {'N': str(mismatches)}

    read_ok, previous = _previous_meta_rows(ddb)

    if not counts_complete:
        reason = ('this run resumed from a checkpoint that carried no counters, so '
                  f'the {written:,} it would record understates the load by an '
                  'unknown amount')
    elif written == 0:
        reason = ('this run wrote ZERO rows. Every row was skipped, which means the '
                  'CSV schema has drifted (a renamed column makes _row_to_item '
                  'return None for all of them). Run --self-test')
    elif not read_ok:
        reason = f'the existing {META_KEY} could not be read, so it cannot be compared'
    elif previous is not None and written < previous * META_MIN_FRACTION_OF_PREVIOUS:
        reason = (f'this run wrote {written:,} rows against the {previous:,} recorded '
                  'by the load already in the table. NSPL does not shrink between '
                  'editions, so suspect a truncated download')
    else:
        reason = None

    if reason is None:
        ddb.put_item(TableName=TABLE_NAME, Item=item)
        return True

    print('')
    print('*' * 78)
    print(f'REFUSING to overwrite {META_KEY}: {reason}.')
    print('')
    print('Whatever rows this run did write are in the table and are fine; only the')
    print(f'provenance singleton is withheld, so the previous {META_KEY} (if any)')
    print('still describes the data that is actually there.')
    print('')
    print('If you have checked the run and want this record anyway, stamp it with:')
    print(f'  AWS_PROFILE=flightmap aws dynamodb put-item --table-name {TABLE_NAME} \\')
    print(f'    --region {AWS_REGION} --item \'{json.dumps(item, separators=(",", ":"))}\'')
    print('*' * 78)
    return False


def run_load(limit, dry_run, workers):
    """Stream the NSPL CSV and write postcode items to DynamoDB.

    Streaming is mandatory, not stylistic: the CSV is 805,857,415 bytes and
    must never be read into memory. utf-8-sig is likewise mandatory, the file
    is BOM-prefixed and plain utf-8 makes the first key U+FEFF + 'pcd7'.
    """
    # Lazy imports so the file stays readable and reviewable without the deps.
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
        from tqdm import tqdm  # type: ignore
    except ImportError as exc:
        print(f'Missing dependency: {exc}')
        print('Install with: pip install boto3 tqdm')
        sys.exit(1)

    if not NSPL_CSV_PATH.exists():
        print(f'NSPL CSV not found at {NSPL_CSV_PATH.resolve()}')
        print('Download from '
              'https://geoportal.statistics.gov.uk/datasets/ons::nspl-online-latest-by-postcode/')
        print('Save the extracted CSV as data/nspl.csv and run this script from the repo root.')
        sys.exit(1)

    # Resume from the checkpoint if it exists. Skipped entirely under --limit
    # AND under --dry-run, so neither smoke test resumes (or later deletes) a
    # real full run.
    #
    # --dry-run has to be here as well as --limit, not because it could damage
    # the checkpoint (it never writes one) but because resuming would make it
    # LIE. A dry run that starts at row 1,500,001 skips the first 1.5M rows
    # wholesale, including the spaced-postcode audit that is the only guard
    # between a future NSPL edition changing format and a wrong
    # location.postcode, and would then print seeded totals for rows it never
    # looked at. The whole point of --dry-run is to examine the data, so it
    # always examines it from row 0.
    #
    # The stored row is the last row FULLY ACCOUNTED FOR (written or skipped and
    # counted), so the resume starts at the row after it. Re-processing the
    # stored row instead would double-count it in the seeded totals, and it buys
    # nothing: the checkpoint is only ever written at an instant when the buffer
    # is empty, so that row's item is already in DynamoDB. Row 0 can never be a
    # checkpoint (the first one needs idx >= CHECKPOINT_EVERY), so 0 is an
    # unambiguous "no checkpoint" and a fresh run still starts at row 0.
    state = dict(_ZERO_STATE) if (limit or dry_run) else _read_checkpoint()
    checkpoint = state['row']
    resume_from = checkpoint + 1 if checkpoint else 0
    if checkpoint:
        print(f'Resuming at row {resume_from:,} '
              f'({state["written"]:,} written and {state["skipped"]:,} skipped '
              'by earlier segments of this load)')

    # Build the client BEFORE the scan, even under --dry-run, so a missing or
    # wrong AWS_PROFILE surfaces in seconds instead of after a long parse.
    #
    # Adaptive retry is a justified deviation from the DEFRA loader's
    # boto3 defaults: this run writes 2,699,393 items, 6.4x more, and a
    # brand-new PAY_PER_REQUEST table ramps its capacity rather than starting
    # at full throughput, so early throttling is expected rather than
    # exceptional. Adaptive mode adds client-side rate limiting on throttle, so
    # the run self-throttles and continues instead of dying and forcing a
    # checkpoint resume.
    ddb = boto3.client(
        'dynamodb',
        region_name=AWS_REGION,
        config=Config(retries={'max_attempts': 10, 'mode': 'adaptive'}),
    )
    print(f'DynamoDB client: {AWS_REGION}, adaptive retry (max_attempts=10) enabled '
          'so throttling on a ramping on-demand table slows the run instead of killing it.')

    if dry_run:
        print('DRY-RUN MODE: no DynamoDB writes will be performed. Always starts at '
              'row 0 and reports only the rows it actually examined; the checkpoint '
              'is neither read nor deleted.')
    if limit:
        print(f'LIMIT: processing first {limit:,} NSPL rows. Checkpoint neither read nor deleted.')
    print(f'Workers: {workers}, batch size: {BATCH_SIZE}.')

    # Counters are SEEDED from the checkpoint, not zeroed, so that every total
    # below (and the __META__ built from them) describes the whole load rather
    # than whichever segment this particular process happened to run.
    batch = []
    written = state['written']
    skipped = state['skipped']
    terminated_written = state['terminated']
    london_written = state['london']
    mismatches = state['mismatches']
    counts_complete = state['countsComplete']
    resumed_written = state['written']
    last_checkpoint = checkpoint
    samples_logged = 0
    SAMPLE_LOG_LIMIT = 5

    with open(NSPL_CSV_PATH, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(tqdm(reader, desc='postcodes', initial=resume_from)):
            if idx < resume_from:
                continue
            if limit and (idx - resume_from) >= limit:
                break

            item = _row_to_item(row)
            if item is None:
                skipped += 1
            else:
                pc = item['postcode']['S']

                # Spaced-form audit. Free, and the only thing standing between a
                # future NSPL edition changing format and a wrong
                # `location.postcode` in every API response for the affected rows.
                if f'{pc[:-3]} {pc[-3:]}' != (row['pcds'] or '').strip():
                    mismatches += 1

                if 'dt' in item:
                    terminated_written += 1
                if 'b' in item:
                    london_written += 1

                if dry_run and samples_logged < SAMPLE_LOG_LIMIT:
                    print(f'  sample {samples_logged + 1}: '
                          f'{json.dumps(item, separators=(",", ":"))}')
                    samples_logged += 1

                batch.append(item)

                if len(batch) >= BATCH_SIZE:
                    if not dry_run:
                        _flush_batch(ddb, batch, workers)
                    written += len(batch)
                    batch.clear()

            # Checkpoint. Two conditions, guarding opposite mistakes:
            #
            #   `not batch` — row `idx` may only be recorded at an instant when
            #   the buffer is EMPTY, i.e. every item derived from a row at or
            #   before `idx` has already reached DynamoDB. Recording `idx`
            #   unconditionally (as this did until 2026-07-25) puts the
            #   checkpoint AHEAD of what was written, and the `idx < resume_from`
            #   skip above then drops the difference forever. Measured over
            #   the real 2,723,596-row file: 2,684 of the 2,701 checkpoints the
            #   old rule wrote had a mean of 267 and up to 499 parsed items still
            #   sitting unwritten in the buffer. The same window opens whenever
            #   ex.map() in _flush_batch re-raises a PutItem failure, not only on
            #   Ctrl-C.
            #
            #   evaluated for EVERY row, skipped or not — this sits after the
            #   `if item is None` branch rather than below a `continue`, which is
            #   the DEFRA loader's remaining bug (load_defra_raster.py:385-391):
            #   there the checkpoint is unreachable for a skipped row, so a run
            #   of them advances nothing. 22 of the 2,723 expected checkpoints
            #   were lost that way here, and the Channel Islands / Isle of Man
            #   rows skip in one contiguous 13,156-row block.
            #
            # The two interact: a skip run that starts while the buffer is
            # part-full cannot checkpoint until the next flush empties it, so the
            # checkpoint lags. That direction is only ever bounded re-work, never
            # loss — measured worst case 6,532 rows against a 1,009-row mean.
            if (not limit and not dry_run and not batch
                    and idx - last_checkpoint >= CHECKPOINT_EVERY):
                _write_checkpoint({
                    'row': idx,
                    'written': written,
                    'skipped': skipped,
                    'terminated': terminated_written,
                    'london': london_written,
                    'mismatches': mismatches,
                    'countsComplete': counts_complete,
                })
                last_checkpoint = idx

    # Flush the remainder.
    if batch:
        if not dry_run:
            _flush_batch(ddb, batch, workers)
        written += len(batch)
        batch.clear()

    # Provenance and checkpoint cleanup. The loop ran to the end of the CSV, so
    # there is nothing left to resume even if __META__ is refused below.
    if not limit and not dry_run:
        if _write_meta(ddb, written, skipped, mismatches, counts_complete):
            print(f'Wrote the {META_KEY} provenance item (vintage {NSPL_VINTAGE}).')
        CHECKPOINT_PATH.unlink(missing_ok=True)
        # Only present if a previous process died between the temp write and
        # the os.replace inside _write_checkpoint().
        (CHECKPOINT_PATH.parent / (CHECKPOINT_PATH.name + '.tmp')).unlink(missing_ok=True)

    verb = 'Would have written' if dry_run else 'Wrote'
    print(f'\nDone. {verb}: {written:,} postcodes.')
    if checkpoint:
        print(f'  (whole load; this process handled {written - resumed_written:,} of them '
              f'after resuming at row {checkpoint:,})')
    print(f'  skipped (unpositioned / no geography / excluded country): {skipped:,}')
    print(f'  terminated (tagged with dt): {terminated_written:,}')
    print(f'  London boroughs (tagged with b): {london_written:,}')
    print(f'  spaced-form mismatches: {mismatches:,}')

    if mismatches:
        print('')
        print('*' * 78)
        print('WARNING: the spaced-postcode invariant NO LONGER HOLDS.')
        print(f'{mismatches:,} row(s) had pcds != key[:-3] + " " + key[-3:].')
        print('')
        print('The Lambda DERIVES its display postcode from the key rather than')
        print('storing pcds, so `location.postcode` will be WRONG for those rows.')
        print('')
        print('Fix before serving this data:')
        print('  1. Add a `pcds` attribute to the item in _row_to_item().')
        print('  2. Add a read-side fallback in the Lambda: use the stored `pcds`')
        print('     when present, fall back to the derivation when absent.')
        print('  3. Reload, then re-verify with the get-item checks below.')
        print('*' * 78)

    if not dry_run and not limit:
        print('\nVerify with:')
        print(f'  AWS_PROFILE=flightmap aws dynamodb describe-table --table-name {TABLE_NAME} '
              '--query "Table.ItemCount" --region eu-west-2')
        print('    (ItemCount refreshes roughly every 6 hours, so it lags a fresh load, '
              'the get-item checks below are the immediate proof)')
        for key, expect in (
            ('SW111AA', 'expect b=Wandsworth'),
            ('E16AN', 'expect b=City of London (boundary check)'),
            ('BR11HB', 'expect dt=198412, q=8'),
            (META_KEY, 'load provenance'),
        ):
            print(f'  AWS_PROFILE=flightmap aws dynamodb get-item --table-name {TABLE_NAME} '
                  f'--key \'{{"postcode":{{"S":"{key}"}}}}\' --region eu-west-2   -> {expect}')
        print('  curl -s -H "x-api-key: $KEY" '
              '"https://api.skyscore.co.uk/v1/score?postcode=SW11+1AA" | jq \'.location, .sources[2]\'')


def main():
    args = parse_args()
    if args.self_test:
        self_test()
        return
    run_load(limit=args.limit, dry_run=args.dry_run, workers=args.workers)


if __name__ == '__main__':
    main()
