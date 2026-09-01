"""Offline city-scale bulk scorer — score a whole book of addresses to CSV.

The Enterprise "score your whole city / whole book" deliverable, and the
pilot demo artefact: run the customer's portfolio FOR them before the
conversation, rather than handing them an API and hoping.

WHY THIS IS A SCRIPT AND NOT AN ENDPOINT:

  /v1/score/batch caps at 100 queries and runs inside a 28-second Lambda
  timeout. A 100,000-address book is 1,000 calls against a monthly quota of
  1,000 — i.e. the entire free tier, or a metering conversation nobody wants
  to have mid-pilot. Offline, the same work costs pennies of DynamoDB reads
  and no quota at all.

ZERO METHODOLOGY DRIFT, BY CONSTRUCTION:

  This script does NOT reimplement scoring. It imports the score Lambda and
  calls `resolve_query()` — the exact function the live API calls, one layer
  below HTTP. Every threshold, weight, persona, alias, NYC ZIP mapping and
  terminated-postcode rule is therefore shared with production by
  construction, not by discipline.

  That matters because this output goes to a CUSTOMER. A bulk CSV whose
  scores differ from the API's, even slightly, is worse than no CSV: it
  turns the methodology into something that has to be defended rather than
  cited. Audit I4 closed the same class of problem by making score/app.py
  the single holder of borough metadata; reimplementing the engine here
  would quietly reopen it.

IMPORT ORDER IS LOAD-BEARING:

  score/app.py reads POSTCODE_TABLE and NOISE_RASTER_TABLE at MODULE level,
  so they must be in os.environ BEFORE the import. Get this wrong and both
  resolve to '', the local NSPL tier silently disables itself, and every
  lookup falls through to postcodes.io — a free community service — for the
  whole run. The run still succeeds, just slowly and indefensibly, which is
  exactly the fair-use problem the NSPL table was built to remove. That is
  why _load_score_app() sets the environment itself rather than trusting
  the caller's shell.

PERFORMANCE, MEASURED 2026-07-27:

  Each query costs up to two DynamoDB GetItems (postcode, then noise
  raster), both per-item calls. Measured on a 5,484-postcode book sampled
  across all 33 London boroughs, on a 28-core machine:

    workers=4    86.7 rows/s
    workers=16  371.1 rows/s
    workers=32  500.2 rows/s   <- peak, hence the default
    workers=64  360.6 rows/s   <- worse, not better

  That inversion past 32 is the same client-CPU bound the NSPL loader hit:
  beyond a point the threads contend over TLS and SigV4 signing rather than
  waiting on DynamoDB. RAISING --workers IS NOT A SPEED KNOB above ~32 and
  will cost you throughput. The figures are machine-dependent; re-measure
  on a different box before quoting them.

  Throughput also climbs with book size as start-up cost amortises: the
  same 16 workers gave 127 rows/s over 250 rows and 371 over 5,484.

  A 100,000-address book therefore extrapolates to roughly 3-4 minutes.
  That is an EXTRAPOLATION, not a measurement — the largest real run to
  date is 5,484 rows.

  SETTLED BY THAT MEASUREMENT: a BatchGetItem prefetch was earmarked as the
  same ~25x win it was for the loader. It is not worth building. Reads are
  far cheaper than the loader's writes, so there is no user-visible problem
  left to solve, and it would cost a second interpretation of NSPL rows
  outside _lookup_postcode_local. Revisit only if a book arrives that is
  orders of magnitude larger than 100k.

COST, at eu-west-2 on-demand rates checked 2026-07-25 (USD 0.1413 per
million read request units, USD 1 ~= GBP 0.79):

  100,000 addresses x 2 reads = 200,000 RRU = USD 0.028 ~= GBP 0.02.
  The read cost is a rounding error; the wall-clock is the real budget.

USAGE:

  python scripts/score_bulk.py --input book.csv --output scored.csv
  python scripts/score_bulk.py --input book.csv --output scored.csv \
      --persona family --include-terminated
  python scripts/score_bulk.py --input book.csv --dry-run --limit 20

  Input is either a CSV with a postcode column (named postcode/POSTCODE/
  post_code/pc, case-insensitive) or a plain text file with one postcode
  per line. Output is written INCREMENTALLY, so an interrupted run leaves a
  usable partial CSV that shows exactly how far it got.
"""

import argparse
import csv
import importlib.util
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ---- Configuration ----

POSTCODE_TABLE = 'london-flight-map-postcodes'
NOISE_RASTER_TABLE = 'london-flight-map-noise-raster'
AWS_REGION = 'eu-west-2'
SCORE_WORKERS = 32  # measured peak 2026-07-27; 64 is SLOWER, see the docstring
PROGRESS_EVERY = 500

# Column names accepted for the postcode field, lowercased for comparison.
POSTCODE_COLUMNS = ('postcode', 'post_code', 'postal_code', 'pc', 'zip', 'zipcode')

REPO_ROOT = Path(__file__).resolve().parent.parent
SCORE_APP_PATH = REPO_ROOT / 'backend' / 'lambdas' / 'score' / 'app.py'


def _load_score_app():
    """Import backend/lambdas/score/app.py with the table env vars already set.

    Same import mechanism as tests/conftest.py::load_lambda. The env vars are
    set HERE, before exec_module, because app.py reads them at module level —
    see the module docstring. Setting them afterwards is a silent no-op that
    routes the entire run through postcodes.io.
    """
    os.environ.setdefault('POSTCODE_TABLE', POSTCODE_TABLE)
    os.environ.setdefault('NOISE_RASTER_TABLE', NOISE_RASTER_TABLE)
    os.environ.setdefault('AWS_REGION', AWS_REGION)

    spec = importlib.util.spec_from_file_location('score_app_bulk', SCORE_APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules['score_app_bulk'] = module
    spec.loader.exec_module(module)
    return module


def read_postcodes(path):
    """Return (passthrough_columns, row_iterator) for a CSV or plain-text file.

    A CSV is detected by finding a recognised postcode column in the header.
    Anything else is treated as one postcode per line.

    Every OTHER column in the customer's file is carried through to the output
    untouched. Without that, they have to join our CSV back onto theirs on
    postcode — which is lossy exactly where property books are densest, since
    a block of flats shares one postcode across many rows. Carrying their own
    reference through means the result reconciles row-for-row.

    A passthrough column whose name collides with one of ours is prefixed
    `src_` rather than silently overwriting a computed value: the customer
    sending a column called `score` must not be able to blank the score we
    calculated.
    """
    handle = open(path, newline='', encoding='utf-8-sig')

    first_line = handle.readline()
    handle.seek(0)
    header_cells = [c.strip().lower() for c in first_line.split(',')]
    pc_index = next(
        (i for i, cell in enumerate(header_cells) if cell in POSTCODE_COLUMNS),
        None,
    )

    if pc_index is None:
        def _plain():
            # Plain text, one postcode per line. Blank lines are skipped
            # rather than counted, so row numbers in any error report match
            # what a human sees in the file.
            with handle:
                for number, line in enumerate(handle, start=1):
                    value = line.strip()
                    if value:
                        yield number, value, {}
        return [], _plain()

    reader = csv.DictReader(handle)
    pc_key = reader.fieldnames[pc_index]
    reserved = set(OUTPUT_COLUMNS)
    mapping = {
        name: (f'src_{name}' if name in reserved else name)
        for name in reader.fieldnames
        if name != pc_key
    }

    def _rows():
        with handle:
            for number, row in enumerate(reader, start=1):
                value = (row.get(pc_key) or '').strip()
                if value:
                    yield number, value, {out: row.get(src, '') for src, out in mapping.items()}

    return list(mapping.values()), _rows()


# ---------------------------------------------------------------------------
# Outcome classification
#
# resolve_query() returns (body, status). Status is 200 for a scored result,
# 400 for a malformed query, and 404 for a postcode that resolved to nothing
# we support — a terminated postcode without opt-in, a non-London UK borough,
# a non-NYC US ZIP, or a postcode that simply does not exist.
#
# What the OUTPUT does with a non-200 is a product decision, not a technical
# one, and it is the decision that most shapes how this artefact lands with a
# customer. See the TODO below.
# ---------------------------------------------------------------------------

# Column names mirror the API's own vocabulary (`quiet` / `afford` / `growth`
# / `live` are the four components calc_score actually returns), so a customer
# reading this CSV alongside METHODOLOGY.md or a /v1/score response sees the
# same words for the same things. Do not rename them to prettier synonyms.
OUTPUT_COLUMNS = [
    'input_postcode',
    'status',
    'score',
    'borough',
    'city',
    'matched_postcode',
    'quiet',
    'afford',
    'growth',
    'live',
    'avg_price_gbp',
    'price_trend_pct',
    'noise_impact_band',
    'quiet_resolution',
    'postcode_status',
    'position_quality',
    'methodology_version',
    'note',
    'sources',
]

# Compact per-row attribution. The full text goes in the companion file (see
# write_sources_file); this is the pointer that cannot be separated from the
# data, because OGL v3.0 attribution has to travel WITH the derived work and a
# customer will inevitably email the CSV on its own.
SOURCES_SUFFIX = '.sources.txt'
SOURCES_CELL = 'ONS NSPL, DEFRA, HM Land Registry, MHCLG (OGL v3.0) - see {file}'


def classify_outcome(postcode, body, status):
    """Turn one resolve_query() result into an output row dict.

    DECISION (Bill, 2026-07-27): every input row appears in the output, with a
    machine-readable `status` and a plain-English `note` when it could not be
    scored. Nothing is silently dropped.

    The reasoning: a customer sends 10,000 addresses and a meaningful fraction
    will not score — retired postcodes, typos, stock outside the 33 London
    boroughs. Returning 8,400 rows with no account of the missing 1,600 is a
    result that LOOKS complete and is not, which is the same failure shape as
    the UnprocessedItems trap in the NSPL loader. Here it is worse, because
    the reader is a customer rather than an operator: they cannot tell a
    deliberate exclusion from a bug, so they will assume the latter. A CSV
    that reconciles line-for-line against their input is the artefact that
    survives being checked.

    HONESTY CONSTRAINT WORTH PRESERVING: a 404 for a retired postcode is
    byte-identical to a 404 for one that never existed. That wording is a
    deliberate public API surface (audit L5) and resolve_query does not tell
    us which case occurred. So `not_found` says the postcode MAY be retired
    and points at --include-terminated; it must never assert that it is.
    Claiming a specific cause we cannot observe would be exactly the kind of
    confident-but-unfounded statement this CSV exists to avoid.
    """
    row = {
        'input_postcode': postcode,
        'methodology_version': body.get('methodologyVersion', ''),
    }

    if status == 200:
        components = body.get('components') or {}
        context = body.get('context') or {}
        location = body.get('location') or {}
        row.update({
            'status': 'scored',
            'score': body.get('score'),
            'borough': location.get('borough', ''),
            'city': location.get('city', ''),
            'matched_postcode': location.get('postcode', ''),
            'quiet': components.get('quiet'),
            'afford': components.get('afford'),
            'growth': components.get('growth'),
            'live': components.get('live'),
            # avgPriceUsd for NYC, avgPriceGbp for London. One column holds
            # whichever the city produced; the `city` column disambiguates.
            'avg_price_gbp': context.get('avgPriceGbp', context.get('avgPriceUsd', '')),
            'price_trend_pct': context.get('priceTrendPct', ''),
            'noise_impact_band': context.get('noiseImpactBand', ''),
            # 'raster' (DEFRA sample at the postcode centroid), 'postcode'
            # (Haversine to airports), or 'borough' (aggregate fallback).
            # Surfaced because it is the honest precision of that single row.
            'quiet_resolution': context.get('quietResolution', ''),
            # Present only on --include-terminated runs. positionQuality
            # 'approximate' means an imputed or sector-mean centroid, which
            # can sit far enough out to cross a noise contour band — the
            # customer should be able to filter those out.
            'postcode_status': location.get('postcodeStatus', ''),
            'position_quality': location.get('positionQuality', ''),
            'note': '',
        })
        return row

    error = body.get('error', 'Unknown error')

    if status == 404 and 'supportedBoroughs' in body:
        # attemptedBorough is None whenever normalise_borough could not map the
        # district at all — the common case for a valid UK postcode outside the
        # covered city-regions (Edinburgh, Belfast, most of rural England). Name
        # the district when we have it and stay vague when we do not, rather
        # than printing 'None' at a customer.
        #
        # NOT "the 33 supported London boroughs" (2026-08-22). That was true
        # when written and stopped being true on 2026-08-10: the API now covers
        # 94 UK boroughs across 12 city-regions plus New York. An Enterprise
        # customer running a national file was being told their Manchester
        # postcodes fell outside London - which is both wrong and reads as a
        # much smaller product than they are paying for. No count is quoted
        # here on purpose; /v1/regions is the live answer and cannot go stale.
        attempted = body.get('attemptedBorough')
        row['status'] = 'outside_supported_boroughs'
        row['borough'] = attempted or ''
        row['note'] = (
            f'Resolved to {attempted}, which is outside the supported '
            'city-regions - see /v1/regions for the current list.'
            if attempted else
            'Valid postcode, but it resolves outside the supported '
            'city-regions - see /v1/regions for the current list.'
        )
    elif status == 404 and 'supportedNycBoroughs' in body:
        row['status'] = 'unsupported_zip'
        row['note'] = 'US ZIP outside the five supported NYC boroughs.'
    elif status == 404:
        row['status'] = 'not_found'
        row['note'] = ('Not found in ONS NSPL or postcodes.io. This may be a retired '
                       'postcode — re-run with --include-terminated to score those.')
    elif status == 400:
        row['status'] = 'invalid_query'
        row['note'] = error
    else:
        row['status'] = 'error'
        row['note'] = error

    return row


def write_sources_file(app, output_path):
    """Write the OGL v3.0 attribution that must travel with the exported CSV.

    NOT optional, and not a nicety. scripts/load_nspl.py spells the obligation
    out: "The attribution obligation SURVIVES INTO ANY DERIVED EXPORT. The
    Enterprise 'score your whole city' CSV is such an export." Every row here
    carries an ONS NSPL centroid and a DEFRA-derived quiet score, so the file
    we hand a customer is a derived work under OGL v3.0 and OS/Royal Mail
    copyright. Shipping it bare would put the customer in breach as well as us.

    Generated from the SAME `app.build_sources()` the live API puts in every
    response, so the two cannot drift — and called AFTER the run, so it
    reflects what was actually used: `build_sources()` only credits ONS once
    the local NSPL tier has genuinely served a lookup, never merely because
    the table is configured.
    """
    path = str(output_path) + SOURCES_SUFFIX
    lines = [
        'Sky Score — bulk scoring export',
        '=' * 60,
        '',
        f'Generated from: {output_path}',
        f'Methodology version: {app.METHODOLOGY_VERSION}',
        '',
        'DATA SOURCES AND ATTRIBUTION',
        '',
    ]
    lines += [f'  - {line}' for line in app.build_sources()]
    lines += [
        '',
        'LICENCE',
        '',
        '  Contains public sector information licensed under the Open',
        '  Government Licence v3.0.',
        '  https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/',
        '',
        '  ONS National Statistics Postcode Lookup contains OS data',
        '  (c) Crown copyright and database right; Royal Mail data',
        '  (c) Royal Mail copyright and database right; National Statistics',
        '  data (c) Crown copyright and database right.',
        '',
        '  THIS FILE MUST ACCOMPANY THE CSV. The attribution obligation',
        '  survives into derived works, so the scores may not be',
        '  redistributed without it.',
        '',
    ]
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    return path


def score_book(app, rows, writer, write_lock, workers, progress=True, sources_cell=''):
    """Score every row and stream results to the CSV as they complete.

    Streaming rather than collecting: a 100k book is a long run, and an
    interrupted one should leave a usable partial CSV showing exactly how far
    it got, not an empty file. The lock serialises only the write, so the
    scoring itself stays parallel.

    Order is NOT preserved — completions are written as they land. Rows carry
    their input postcode, so the customer can join; if input order ever needs
    preserving, sort the output afterwards rather than serialising the pool.
    """
    counters = {'scored': 0, 'failed': 0, 'omitted': 0, 'local_served': 0}

    def _one(item):
        _number, postcode, passthrough = item
        query = dict(app_query_defaults)
        query['postcode'] = postcode
        try:
            body, status = app.resolve_query(query)
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the run
            body, status = {'error': f'{type(exc).__name__}: {exc}'}, 500

        # READ IN THE WORKER, where the lookup happened. Attribution is
        # thread-local (it became so on 2026-08-22, when one container crediting
        # ONS for every later response was fixed), and the pool means the thread
        # that answers is never the thread that writes the .sources.txt. So the
        # main thread's view is False no matter what ONS served, and the OGL
        # file credited postcodes.io for lookups ONS actually performed.
        served_locally = app.local_postcode_served()

        output_row = classify_outcome(postcode, body, status)
        if output_row is not None:
            output_row['sources'] = sources_cell
        if output_row is not None and passthrough:
            # Their columns are added AFTER ours, and collisions were already
            # renamed in read_postcodes, so a customer column can never
            # overwrite a computed field.
            output_row.update(passthrough)

        with write_lock:
            if served_locally:
                counters['local_served'] += 1
            if output_row is None:
                counters['omitted'] += 1
            else:
                writer.writerow(output_row)
                if status == 200:
                    counters['scored'] += 1
                else:
                    counters['failed'] += 1

            done = counters['scored'] + counters['failed'] + counters['omitted']
            if progress and done % PROGRESS_EVERY == 0:
                print(f'  {done:,} processed '
                      f'({counters["scored"]:,} scored, {counters["failed"]:,} unscored)')

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_one, rows))

    return counters


# Query defaults, overridden per-run from the CLI. Held module-level so the
# worker closure does not have to thread them through every call.
app_query_defaults = {'city': 'london', 'persona': 'balanced'}


def main():
    parser = argparse.ArgumentParser(
        description='Score a book of postcodes offline, reusing the live scoring engine.',
    )
    parser.add_argument('--input', required=True, metavar='PATH',
                        help='CSV with a postcode column, or one postcode per line.')
    parser.add_argument('--output', metavar='PATH',
                        help='Output CSV. Required unless --dry-run.')
    parser.add_argument('--persona', default='balanced',
                        help='Scoring persona (default balanced).')
    parser.add_argument('--city', default='london',
                        help='City context for non-postcode resolution (default london).')
    parser.add_argument('--include-terminated', action='store_true',
                        help='Score retired postcodes that only the local NSPL tier can serve.')
    parser.add_argument('--workers', type=int, default=SCORE_WORKERS,
                        help=f'Concurrent scoring workers (default {SCORE_WORKERS}, the '
                             f'measured peak). Higher is SLOWER: 64 workers measured '
                             f'360 rows/s against 500 at 32.')
    parser.add_argument('--limit', type=int, metavar='N',
                        help='Score only the first N rows. For smoke tests.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Resolve and report counts without writing an output file.')
    args = parser.parse_args()

    if not args.dry_run and not args.output:
        parser.error('--output is required unless --dry-run is given.')

    input_path = Path(args.input)
    if not input_path.exists():
        print(f'Input not found: {input_path}', file=sys.stderr)
        return 1

    print('Loading the score engine from backend/lambdas/score/app.py ...')
    app = _load_score_app()
    print(f'Methodology v{app.METHODOLOGY_VERSION}, '
          f'postcode table {app.POSTCODE_TABLE or "(UNSET - would use postcodes.io!)"}')

    app_query_defaults['city'] = args.city
    app_query_defaults['persona'] = args.persona
    if args.include_terminated:
        app_query_defaults['includeTerminated'] = True

    passthrough_columns, rows = read_postcodes(input_path)
    if args.limit:
        rows = (row for i, row in enumerate(rows) if i < args.limit)
    if passthrough_columns:
        print(f'Carrying through {len(passthrough_columns)} input column(s): '
              f'{", ".join(passthrough_columns)}')

    fieldnames = OUTPUT_COLUMNS + passthrough_columns
    write_lock = threading.Lock()

    sources_cell = SOURCES_CELL.format(
        file=Path(args.output).name + SOURCES_SUFFIX if args.output else 'the accompanying licence file'
    )

    if args.dry_run:
        import io
        sink = io.StringIO()
        writer = csv.DictWriter(sink, fieldnames=fieldnames, extrasaction='ignore')
        counters = score_book(app, rows, writer, write_lock, args.workers,
                              sources_cell=sources_cell)
    else:
        with open(args.output, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            counters = score_book(app, rows, writer, write_lock, args.workers,
                                  sources_cell=sources_cell)

    total = counters['scored'] + counters['failed'] + counters['omitted']
    print()
    print(f'Done. {total:,} rows processed.')
    print(f'  scored:   {counters["scored"]:,}')
    print(f'  unscored: {counters["failed"]:,}')
    if counters['omitted']:
        print(f'  omitted:  {counters["omitted"]:,}')
    if not args.dry_run:
        print(f'  output:   {args.output}')
        # Written last, so build_sources() reflects what the run actually used
        # rather than what was configured — the same honesty rule the API's
        # `sources` array follows.
        #
        # Hand the workers' finding to the thread that writes the file. Without
        # this, `build_sources()` runs on a thread that never resolved a
        # postcode and omits the ONS credit from an export built entirely on ONS
        # centroids - a licensing claim, not a log line, and the file says it
        # MUST accompany the CSV.
        if counters['local_served']:
            app.mark_local_postcode_served()
        sources_path = write_sources_file(app, args.output)
        print(f'  sources:  {sources_path}')
        print()
        print('OGL v3.0 attribution: the .sources.txt file MUST be sent with the CSV.')

    # The local tier is credited only once it has actually served a lookup,
    # never merely because the table is configured — the same honesty rule
    # the API applies to its `sources` array.
    # `app._LOCAL_POSTCODE_SERVED` until 2026-09-01, which stopped existing on
    # 2026-08-22 - so this line raised AttributeError and the Enterprise
    # deliverable crashed AFTER writing its CSV on every run for ten days. It is
    # the last statement in main(), which is why the failure looked like a
    # successful export with a traceback stapled to it.
    if not counters['local_served'] and total:
        print()
        print('WARNING: the local NSPL tier never served a lookup. Every postcode '
              'went to postcodes.io. Check AWS credentials and POSTCODE_TABLE.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
