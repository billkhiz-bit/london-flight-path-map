"""The planes overhead counts, offered under the ODbL as one download for /open-data/ (2026-11-25).

WHY: the counts in data/planes/ are built from adsb.lol's flight tracks (ODbL 1.0), so publishing them makes them a
Derivative Database, which the ODbL says must be offered under the same licence. Bill accepted that share-alike on
2026-10-15 (LICENSING.md, adsb.lol), and the offer was to follow "a few weeks" after the counts went live on
2026-10-27. It had not been built by 2026-11-25, when it was found while listing the site's open work: nothing held the
promise. tests/test_planes_open_data.py now does.

WHAT: open-data/sky-score-planes-overhead.zip holds two files.
  planes-overhead.csv  one row per postcode and airport listed in data/planes/, and one row per postcode no published
                       airport reaches (airport blank, none_listed 1). For each kind of day (CLASSES' order) a low and a
                       high column: equal for one figure, a range where the postcode sits on the edge of the overhead
                       cone, both blank where the airport had no day of that kind (not measured, never 0).
  README.txt           what the figures mean, every sentence READ from data/planes/airports.json (the definition, the
                       direction rule, the postcodes rule, the months and days, the credits, the licence), never typed.

The zip is NOT tracked in git (a binary that changes with every planes roll): `open-data-deploy` runs --write first.
It is deterministic (rows sorted, fixed timestamps, fixed compression), so two builds from the same files are byte
for byte the same, and --check proves that and the round trip against data/planes/ without needing the file on disk.

Usage: python scripts/build_planes_open_data.py --write | --check
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLANES = REPO / 'data' / 'planes'
OUT = REPO / 'open-data' / 'sky-score-planes-overhead.zip'
CSV_NAME = 'planes-overhead.csv'
README_NAME = 'README.txt'
FIXED_TIME = (1980, 1, 1, 0, 0, 0)  # the earliest a zip can hold: no build date, so a rebuild is byte-identical
ODBL_URL = 'https://opendatacommons.org/licenses/odbl/1-0/'
DBCL_URL = 'https://opendatacommons.org/licenses/dbcl/1-0/'

sys.path.insert(0, str(REPO / 'scripts'))
from build_planes_pages import airport_names  # noqa: E402  the site's own name table (js/flight_geometry.mjs)


def load():
    meta = json.loads((PLANES / 'airports.json').read_text(encoding='utf-8'))
    files = {}
    for district in meta['districts']:
        files[district] = json.loads((PLANES / f'{district}.json').read_text(encoding='utf-8'))
    return meta, files


def low_high(fig):
    """One kind of day's figure as (low, high): a number twice, a cone-edge range as its ends, nothing as blanks."""
    if fig is None:
        return '', ''
    if isinstance(fig, list):
        return fig[0], fig[1]
    return fig, fig


def columns(classes):
    out = ['postcode', 'district', 'airport']
    for c in classes:
        out += [f'{c}_low', f'{c}_high']
    return out + ['none_listed', 'approx_position', 'other_traffic']


def rows(meta, files):
    classes = meta['classes']
    out = []
    for district in sorted(files):
        f = files[district]
        approx, other = set(f['approx']), set(f['other'])
        for pc, listed in f['postcodes'].items():
            for code, figs in listed.items():
                if len(figs) != len(classes):
                    raise SystemExit(f'{district}.json {pc} {code}: {len(figs)} figures for {len(classes)} kinds of day')
                cells = [v for fig in figs for v in low_high(fig)]
                out.append([pc, district, code, *cells, 0, int(pc in approx), int(pc in other)])
        for pc in f['none']:
            out.append([pc, district, '', *([''] * (2 * len(classes))), 1, int(pc in approx), int(pc in other)])
    out.sort(key=lambda r: (r[0], r[2]))
    return out


def csv_text(meta, table):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(columns(meta['classes']))
    w.writerows(table)
    return buf.getvalue()


def readme(meta, table, names):
    classes = meta['classes']
    lines = [
        'Sky Score: planes overhead, by postcode',
        '',
        'LICENCE',
        f'This database is made available under the Open Database License (ODbL) 1.0: {ODBL_URL}',
        'Any rights in individual contents of the database are licensed under the Database Contents License: '
        f'{DBCL_URL}',
        'It is built from adsb.lol flight tracks, themselves under the ODbL, so anything you make from it and publish as a '
        'database is under the ODbL too. Credit "aircraft positions via adsb.lol (ODbL)" and "Sky Score (skyscore.co.uk)".',
        '',
        'CREDITS',
        *[f'- {c}' for c in meta['credits']],
        '',
        'WHAT A FIGURE IS',
        meta['definition'],
        'Each figure is the average number of aircraft overhead on a day of that kind, from one airport. '
        f'The kinds of day are {", ".join(classes)}. {meta["direction_rule"]}',
        'An airport is listed for a postcode only where it reaches an average that rounds to 1 on at least one kind of '
        'day. A postcode that no airport reaches has one row with the airport blank and none_listed 1.',
        meta['postcodes_rule'],
        '',
        'COLUMNS',
        '- postcode, district: the postcode and its postcode district.',
        '- airport: the airport\'s IATA code (below), blank on a none_listed row.',
        *[f'- {c}_low, {c}_high: the figure on {c} days. Equal for one figure; a range where the postcode sits on the '
          'edge of the overhead cone; both blank where the airport had no day of that kind (not measured, never 0).'
          for c in classes],
        '- none_listed: 1 when no airport here reaches the listing floor for this postcode.',
        # The two flags in the planes pages' own words (build_planes_pages.py, the district notes).
        '- approx_position: 1 when the postcode has a position ONS estimates, so its figures may be for a spot a few '
        'hundred metres away.',
        '- other_traffic: 1 when other aircraft pass too: helicopters, and planes from airfields and airports we cannot '
        'check against official counts. So a low count from the airports we count does not mean a quiet sky there.',
        '',
        'AIRPORTS (months counted; days of each kind)',
    ]
    for code in sorted(meta['airports']):
        a = meta['airports'][code]
        months = f'{a["months"][0][:4]}-{a["months"][0][4:]} to {a["months"][-1][:4]}-{a["months"][-1][4:]}'
        days = ', '.join(f'{c} {a["days"][c]}' for c in classes)
        lines.append(f'- {code} {names.get(code, code)}: {months}; {days}')
    lines += ['', f'{len(table):,} rows; {len({r[0] for r in table}):,} postcodes.', '']
    return '\n'.join(lines)


def build() -> bytes:
    meta, files = load()
    table = rows(meta, files)
    names = airport_names()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name, text in ((CSV_NAME, csv_text(meta, table)), (README_NAME, readme(meta, table, names))):
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, text.encode('utf-8'), compresslevel=9)
    return buf.getvalue()


def round_trip(blob: bytes) -> list[str]:
    """Problems found reading the zip back against data/planes/: every listed figure and every none postcode once."""
    meta, files = load()
    classes = meta['classes']
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        got = list(csv.reader(io.StringIO(z.read(CSV_NAME).decode('utf-8'))))
    header, body = got[0], got[1:]
    problems = [] if header == columns(classes) else [f'header {header}']
    seen = {}
    for r in body:
        seen[(r[0], r[2])] = r
    want = 0
    for f in files.values():
        for pc, listed in f['postcodes'].items():
            for code, figs in listed.items():
                want += 1
                r = seen.get((pc, code))
                cells = [str(v) for fig in figs for v in low_high(fig)]
                if r is None or r[3:3 + 2 * len(classes)] != cells:
                    problems.append(f'{pc} {code}: {r and r[3:3 + 2 * len(classes)]} != {cells}')
        for pc in f['none']:
            want += 1
            if (pc, '') not in seen:
                problems.append(f'{pc}: none_listed row missing')
    if want != len(body):
        problems.append(f'{len(body)} rows for {want} expected')
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    if not (args.write or args.check):
        ap.error('pass --write or --check')
    blob = build()
    if args.check:
        if build() != blob:
            print('FAIL: two builds from the same files differ: the zip is not deterministic')
            return 1
        problems = round_trip(blob)
        if problems:
            print(f'FAIL: {len(problems)} problem(s) reading the zip back against data/planes/: {problems[:5]}')
            return 1
        if OUT.exists() and OUT.read_bytes() != blob:
            print(f'FAIL: {OUT.relative_to(REPO)} differs from a fresh build: run --write')
            return 1
        print(f'ok: {len(blob):,} bytes, deterministic, every figure in data/planes/ read back once')
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(blob)
        print(f'wrote {OUT.relative_to(REPO)} ({len(blob):,} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
