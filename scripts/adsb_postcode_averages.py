"""Average CAP 1498 overflights a day at every live postcode Sky Score covers, per publishable airport.

WHY THIS EXISTS
---------------
The last part of step 2 of "how often planes pass" (ROADMAP "IN PROGRESS: how often planes fly"). Step 1
(scripts/adsb_movements.py) checks the community tracking against the CAA's own monthly movements per
airport; scripts/adsb_overflights.py counts overflights per 100 m British National Grid cell per day, per
airport. This turns the year's day files into the figure a resident asks for, at every live postcode in the
council areas the score Lambda covers (LAD_TO_BOROUGH, read through build_borough_bands.load_lad_map(), never
copied): overflights on an average day from each airport, on that airport's westerly, easterly and mixed days
separately (classify_day()), at both of CAP 1498's angles, with the number of days behind each average.
NOTHING HERE IS PUBLISHED: the file stays in data/adsb/ (gitignored) until Bill publishes under ODbL.

WHICH AIRPORTS: THE PUBLISH RULE (year_rule(), chosen 2026-10-22; Bill: as accurate as possible)
- EVERY MONTH THE CAA HAS PUBLISHED is checked: each airport's tracked movements against Table 03 for that
  month (data/caa/table_03_aircraft_movements_YYYY-MM.csv), through adsb_movements.period_verdict() and so
  coverage_verdict(), with report()'s arithmetic (outage days left out, the official figure scaled by
  usable_share(), circuits read both ways). The counts are the day files' own (meta 'movements'), the same
  movements that credit each overflight to its airport; on 2026-10-22 they reproduced report()'s July and
  August ratios to the tenth of a percent at all 15 airports.
- An airport is published only when it passed EVERY month checked, and at least MIN_CHECKED_MONTHS of them.
  An airport that fails is ABSENT from the file, its reason recorded once, never a column of zeros.
- ONLY DAYS OF MONTHS THE AIRPORT PASSED enter its averages. A month with no CAA figure yet (September 2026)
  or one the day files cannot cover whole (October 2026) cannot be checked, so its days are left out and
  listed: Luton passed six of the eight months and failed two with no other sign (February 93.2%, June
  72.7%), so a month nobody has checked is not assumed good. They come in when the CAA publishes the month
  (rerun this; nothing is recounted).
- Days are left out exactly as adsb_overflights.average() leaves them out (feed outages by feed_gaps() over
  every stored UK profile; classify_day() None), held together by a test.

ABSENT IS NOT ZERO, AND THE FILE SAYS WHICH
- `mean` 0.0 (with `total` 0) is a MEASURED zero: the airport is published, its days of that kind were
  counted, and none of its traffic passed over the cell at that angle under 7,000 ft.
- `mean` NaN is NOT MEASURED: the airport had no kept day of that kind (`days` 0), so there is nothing to
  average. Never 0.
- A failing airport is not in `airports` at all; meta['not_published'] says why, once.
- A postcode with no ONS grid reference is not in the file (counted in meta); Northern Ireland is left out
  explicitly, because NSPL gives BT grid references on the IRISH Grid (postcode_grid.py) and the day files'
  cells are British. No covered council is in Northern Ireland: the meta's count is of every BT row in NSPL
  (63,293 on the August 2026 edition), none of them in a covered council.
- THE FILE HOLDS ONLY THE PUBLISHED AIRPORTS, so a postcode can read quiet from them under busy sky (Biggin
  Hill, TN16 3GH, 2026-10-22: 6.3 a westerly day from Heathrow, the only published airport over it, under 28.8
  a day of all traffic, Biggin Hill's own flying being "other"). `context_all_traffic_unpublishable` says how busy:
  every pass over the cell, every airport and "other" alike. It is context for whoever reads the file,
  never a figure to publish: it includes airports that failed the rule and traffic no official count checks.

POSTCODES: live ones (no `doterm`) whose ladNNcd (the year suffix resolved by prefix, exactly one column) is a
covered council, each read in the 100 m cell holding NSPL's own `east1m`/`north1m`, never a re-projection:
postcode_grid.grid_ref() is handed a transformer that refuses, so a row it would project is left out and
counted. A postcode reads its CELL's count (the cell's centre was inside the cone), as adsb_overflights does.
NSPL's `gridind` travels with each postcode as its position quality, never a reason to drop it: 1 is the
building nearest the postcode's mean; 5 (imputed by ONS) and 6 (sector mean) can sit hundreds of metres out
(scripts/load_nspl.py), so a figure for one must say so. 9 (no position) is left out and counted.

WHAT THE FILE HOLDS (data/adsb/postcode-averages.npz, written .partial then renamed; no pickles)
  postcode, lad, city, easting, northing, gridind: one row per postcode
  airports [A], classes ('westerly', 'easterly', 'mixed'), angles (48.5, 60): the axes
  days [A, 3]: the days behind each airport's average of each kind
  total [P, A, 3, 2]: passes summed over those days (whole counts, exact)
  mean [P, A, 3, 2]: total / days, float32; NaN where days is 0
  context_all_traffic_unpublishable [P, 2], context_days: UNPUBLISHABLE context (see above): all passes over
    the cell a day, every kept day of the checked months, no direction split
  meta (JSON): the definition, every monthly verdict, the rule, what was left out and why, the licence

LIMITS (those of the counter, stated so a figure is read correctly): heights are above sea level, not the
ground (high airfields count high); a cell counts a pass once however often it returns within it; mixed days
are their own class, not split by hour; the year is the months checked, not a calendar year.

Usage (the system Python under -I: it reads NSPL and the CAA tables, both downloads, and needs numpy,
pyproj and tzdata):
    python -I scripts/adsb_postcode_averages.py --verdicts           # monthly verdicts and the rule only
    python -I scripts/adsb_postcode_averages.py                      # build data/adsb/postcode-averages.npz
    python -I scripts/adsb_postcode_averages.py --at "TW9 3PZ" --at "SW11 1AA"   # read the built file
"""

import argparse
import csv
import datetime as dt
import importlib.util
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DAY_DIR = ROOT / 'data' / 'adsb' / 'overflights'
CAA_DIR = ROOT / 'data' / 'caa'
NSPL_CSV = ROOT / 'data' / 'nspl.csv'
OUT = ROOT / 'data' / 'adsb' / 'postcode-averages.npz'
OUT_ALL_MONTHS = ROOT / 'data' / 'adsb' / 'postcode-averages-unchecked-months-too.npz'


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ao = _load('adsb_overflights')
mv = _load('adsb_movements')
postcode_grid = _load('postcode_grid')

CLASSES = ('westerly', 'easterly', 'mixed')  # classify_day()'s labels; None leaves a day out
MIN_CHECKED_MONTHS = 6  # year_rule(): half a year of checked tracking, winter and summer timetables both
# Days adsb.lol's archive does not hold, so no day file can exist. Each is treated as an outage day (left out,
# the official figure scaled to the rest, as report() treats a day whose feed failed); any OTHER missing day
# leaves its month unchecked, because a file that was never made must not pass as an outage. Measured on
# 2026-10-21 by the fetch (data/adsb/raw/2026-05-05 holds one 237 MB tar against ~3.7 GB on a normal day).
ARCHIVE_GAPS = {
    dt.date(2026, 5, 5): "adsb.lol's archive for the day is near-empty (237 MB against ~3.7 GB)",
    dt.date(2026, 5, 6): 'adsb.lol has no archive for the day (404)',
}
CAA_MONTHLY_GLOB = 'table_03_aircraft_movements_????-??.csv'


class _Unplaced(Exception):
    pass


class _NoReprojection:
    """The transformer handed to postcode_grid.grid_ref(): a postcode is read at ONS's own grid reference or
    not at all, so its lat/long fallback (Northern Ireland, rows with no reference) must never run here."""

    def transform(self, *_):
        raise _Unplaced


# ---------------------------------------------------------------- which days, which airports


def caa_months(caa_dir=CAA_DIR):
    """{'YYYYMM': {code: official movements}} from every monthly Table 03 in `caa_dir`, each read by
    adsb_movements.caa_table() (one period per file, each airport matching exactly one row). A file whose
    period is not the month its name gives is refused: the name is how a month is found."""
    out = {}
    for path in sorted(caa_dir.glob(CAA_MONTHLY_GLOB)):
        period, official = mv.caa_table(path)
        if period != path.stem[-7:].replace('-', ''):
            raise SystemExit(f'{path.name} holds period {period}, not the month its name gives')
        out[period] = official
    return out


def read_metas(day_files):
    """{day: (meta, path)} for these day files, reading each file's meta alone."""
    metas = {}
    for path in day_files:
        meta = ao.read_meta(path)
        metas[dt.date.fromisoformat(meta['day'])] = (meta, Path(path))
    if len(metas) != len(day_files):
        raise SystemExit('the same day appears twice among the day files')
    return metas


def plan_days(metas, classify=None):
    """The first pass of adsb_overflights.average(), kept identical so these averages leave out what its
    averages leave out (tests/test_adsb_postcode_averages.py holds the two together): outage days by
    feed_gaps() over every stored UK profile (a day it cannot judge is kept), then classify() (classify_day()
    by default) for every kept airport-day, None for an airport the procedure file no longer draws."""
    classify = classify or ao.classify_day
    gaps = mv.feed_gaps({d: m['feed']['uk'] for d, (m, _) in metas.items()}, 'uk')
    kept = sorted(d for d in metas if not gaps[d])
    bearings = {code: {des: brg for des, (_, brg) in ap['runways'].items()} for code, ap in ao.uk_airports().items()}
    labels, unknown = {}, set()
    for d in kept:
        meta = metas[d][0]
        for code in meta['codes']:
            if code == ao.OTHER:
                continue
            if code not in bearings:
                labels[(d, code)] = None
                unknown.add(code)
                continue
            labels[(d, code)] = classify(code, meta['movements'][code], bearings[code])
    return {'gaps': gaps, 'kept': kept, 'labels': labels, 'unknown': unknown}


def _moved(meta, code):
    """(movements, circuit movements) one day file counted at one airport: report()'s two sums."""
    m = meta['movements'][code]
    n = sum(sum(h) for kind in ('landing', 'take-off') for h in m[kind].values())
    c = sum(sum(h) for kind in ('landing', 'take-off') for h in m.get('circuits', {}).get(kind, {}).values())
    return n, c


def month_verdicts(metas, gaps, official_by_month):
    """({code: {'YYYYMM': verdict}}, {'YYYYMM': why unchecked}): coverage_verdict() for every airport in every
    month with a CAA figure, by adsb_movements.report()'s arithmetic on the day files' own counts. A verdict is
    {'ok', 'reason', 'readings', 'tracked', 'circuits', 'official', 'kept_days', 'period_days'}; `official` is
    the CAA's figure scaled to the kept days, `readings` which reading of the circuits fitted (with, without).
    A month is checked only when every one of its days has a day file or is
    one of ARCHIVE_GAPS (left out like an outage day); any other absent day leaves the month unchecked."""
    out, unchecked = defaultdict(dict), {}
    for period, official in sorted(official_by_month.items()):
        whole = mv.period_days(period)
        absent = sorted(d for d in whole if d not in metas)
        unexplained = [d for d in absent if d not in ARCHIVE_GAPS]
        if unexplained:
            unchecked[period] = (f'{len(unexplained)} of its {len(whole)} days have no day file '
                                 f'({unexplained[0]}{" ..." if len(unexplained) > 1 else ""})')
            continue
        present = sorted(d for d in whole if d in metas)
        open_days = [d for d in present if not gaps[d]]
        for code, n_official in sorted(official.items()):
            kept = {}
            for d in open_days:
                meta = metas[d][0]
                # A day the airport could not be measured on (no field level) is not an outage: it stays a
                # missing day and the month cannot pass, as in report().
                if code in meta['codes'] and meta['fields'].get(code, {}).get('field') is not None:
                    kept[d] = _moved(meta, code)
            missing = len(open_days) - len(kept)
            tracked = sum(n for n, _ in kept.values())
            circuits = sum(c for _, c in kept.values())
            share = mv.usable_share({d: n for d, (n, _) in kept.items()}, whole)
            scaled = n_official * share if share else None
            if any(gaps[d] is None for d in present):
                ok, reason = False, 'feed not judged on every day'
            else:
                ok, reason = mv.period_verdict(tracked, scaled, True, missing, circuits, len(kept), len(whole))
            # Which reading of the circuits fitted, each asked of coverage_verdict() on its own, so year_rule()
            # can ask for ONE reading across the months as coverage_verdict() asks for one at both ends.
            readings = {'with circuits': ok and mv.coverage_verdict(tracked, scaled, True)[0],
                        'without circuits': ok and mv.coverage_verdict(tracked - circuits, scaled, True)[0]}
            out[code][period] = {'ok': ok, 'reason': reason, 'readings': readings, 'tracked': tracked,
                                 'circuits': circuits, 'official': None if scaled is None else round(scaled, 1),
                                 'kept_days': len(kept), 'period_days': len(whole)}
    return dict(out), unchecked


def year_rule(months, min_months=MIN_CHECKED_MONTHS):
    """(publishable, reason) for one airport's year, from its month_verdicts() ({'YYYYMM': verdict}).

    THE RULE (chosen 2026-10-22): published only when its tracking passed coverage_verdict() in EVERY month
    that could be checked (a CAA figure, and day files for the whole month), on ONE reading of its circuits
    for all of them, and at least `min_months` months were checked. Its averages then use the kept days of
    those months only.
    - One reading: an airport's return holds its circuits or leaves them out, so passing some months only
      with them and others only without is coverage_verdict()'s floor-on-one, ceiling-on-the-other flaw at
      the scale of a year (Leeds Bradford passes January to March only without its circuits and every month
      that way, so it stays).
    - Every month, not most: the floor is there so that no figure reads quieter than the sky, and a failed
      month shows that this airport's tracking, or our counting of it, can fall short with no other sign.
      Luton passed six of eight months and failed February (93.2%) and June (72.7%: a transponder stuck
      between 'ground' and 0 ft pulled its measured field level to 0 on eight days, and the movements went
      uncounted); Newcastle, Liverpool and Cardiff each fell short in April or May. A pass in another month is then weaker evidence
      at that airport than at one that never failed. Leaving out only the failed months would publish more
      airports on fewer, seasonally lopsided days; that is Bill's call, not a default.
    - At least six: a year's figure should rest on half a year of checked tracking, winter and summer
      timetables both, as a month needs three quarters of its days (MIN_USABLE_FRACTION) to be judged."""
    if not months:
        return False, 'no month with an official figure to check its tracking against'
    failed = {p: v for p, v in sorted(months.items()) if not v['ok']}
    if failed:
        return False, f'failed {len(failed)} of {len(months)} months checked: ' + '; '.join(
            f'{p}: {v["reason"]}' for p, v in failed.items())
    common = [r for r in ('with circuits', 'without circuits') if all(v['readings'][r] for v in months.values())]
    if not common:
        return False, ('passed every month checked, but no one reading of its circuits fits them all: '
                       'an over-count in some months or a shortfall in others')
    if len(months) < min_months:
        return False, f'only {len(months)} month(s) checked; the rule needs {min_months}'
    return True, f'passed all {len(months)} months checked ({min(months)} to {max(months)}), {common[0]}'


def airports_to_publish(verdicts, codes, min_months=MIN_CHECKED_MONTHS):
    """({code: months whose days it averages}, {code: why it is not published}) for every airport in `codes`
    (the day files' airports, OTHER included: it has no official figure, so it is never published)."""
    publish, refused = {}, {}
    for code in codes:
        ok, reason = year_rule(verdicts.get(code, {}), min_months)
        if ok:
            publish[code] = sorted(p for p, v in verdicts[code].items() if v['ok'])
        else:
            refused[code] = reason if code != ao.OTHER else ('not an airport: transits, helicopters and fields '
                                                              'we do not track, with no official figure to check')
    return publish, refused


# ---------------------------------------------------------------- postcodes


def covered_postcodes(lad_map, nspl=NSPL_CSV):
    """(postcodes, {reason: rows left out}) for every live postcode of a covered council: postcodes is a list
    of (postcode, lad, city, easting, northing, gridind) at ONS's grid reference, gridind its position quality
    (kept, never a reason to drop a postcode, except 9: no position). The LAD column carries a year suffix
    that moves (lad25cd -> lad26cd), so it is found by prefix and must match exactly one column."""
    with nspl.open(newline='', encoding='utf-8-sig') as fh:
        reader = csv.reader(fh)
        header = next(reader)
        postcode_grid.require_grid_columns(header, nspl)
        missing = [c for c in ('pcds', 'doterm', 'gridind', 'lat', 'long') if c not in header]
        lads = [c for c in header if re.fullmatch(r'lad\d{2}cd', c)]
        if missing or len(lads) != 1:
            raise SystemExit(f'{nspl.name}: columns {missing} missing, LAD columns {lads} (need exactly one)')
        ix = {c: header.index(c) for c in ('pcds', 'doterm', 'gridind', 'east1m', 'north1m', 'lat', 'long', lads[0])}
        out, left_out = [], Counter()
        for r in reader:
            pc = r[ix['pcds']].strip().upper()
            if pc.startswith(postcode_grid.IRISH_GRID_PREFIX):
                left_out['Northern Ireland (Irish Grid references), every BT row'] += 1
                continue
            lad = r[ix[lads[0]]].strip()
            if lad not in lad_map:
                continue
            if r[ix['doterm']].strip():
                left_out['terminated (covered councils)'] += 1
                continue
            row = {k: r[ix[k]] for k in ('east1m', 'north1m', 'lat', 'long')}
            row['pcds'] = pc
            gridind = r[ix['gridind']].strip()
            if not (row['east1m'].strip() and row['north1m'].strip()) or gridind == '9':
                left_out['no ONS grid reference (covered councils)'] += 1
                continue
            try:
                e, n = postcode_grid.grid_ref(row, _NoReprojection())
            except _Unplaced:
                left_out['no ONS grid reference (covered councils)'] += 1
                continue
            if not gridind.isdigit():
                raise SystemExit(f'{pc}: gridind {gridind!r} is not a digit: NSPL has changed')
            out.append((pc, lad, lad_map[lad][0], e, n, int(gridind)))
    return out, dict(left_out)


# ---------------------------------------------------------------- reading the day files at the cells


def day_runs(path, totals=True):
    """{angle: (all-traffic runs [0, j, first, last, n] or None, per-airport runs [a, j, first, last, n])} from
    one day file. The all-traffic runs (every pass, every airport and "other" alike) get a group column of 0 so
    at_cells() reads both kinds; with `totals` False only the per-airport columns are unpacked."""
    with np.load(path, allow_pickle=False) as z:
        cols = {k: z[k] for k in z.files if k.startswith(('airport_', 'cells_'))}
    out = {}
    for angle in ao.ANGLES:
        every = None
        if totals:
            runs = ao.unpack(cols, f'cells_{ao.tag(angle)}')
            every = np.column_stack([np.zeros(len(runs), np.int32), runs])
        out[angle] = (every, ao.unpack(cols, f'airport_{ao.tag(angle)}'))
    return out


def at_cells(runs, j, i, groups):
    """The day's count in each cell (rows j, columns i) for each of these airport indexes, as an
    (n cells, len(groups)) array, 0 where no run holds the cell. Runs [a, j, first, last, n] come sorted and
    disjoint from sweep(); that is checked, because a lookup on unsorted runs would read wrong, not fail."""
    a, rj = runs[:, 0].astype(np.int64), runs[:, 1].astype(np.int64)
    first, last = runs[:, 2].astype(np.int64), runs[:, 3].astype(np.int64)
    row = a * ao.NROWS + rj
    start = row * ao.NCOLS + first
    if len(start) > 1 and (np.any(np.diff(start) <= 0) or np.any((row[1:] == row[:-1]) & (first[1:] <= last[:-1]))):
        raise SystemExit('a day file holds runs that are unsorted or overlap: refusing to read it')
    out = np.zeros((len(j), len(groups)), np.int64)
    if not len(start):
        return out
    for col, g in enumerate(groups):
        q_row = g * ao.NROWS + j
        k = np.searchsorted(start, q_row * ao.NCOLS + i, 'right') - 1
        kc = np.maximum(k, 0)
        hit = (k >= 0) & (row[kc] == q_row) & (last[kc] >= i)
        out[hit, col] = runs[kc[hit], 4]
    return out


def accumulate(metas, plan, publish, cells_j, cells_i, every_month=False, progress=None, context_months=()):
    """(totals [angle, class, cell, airport], days [airport, class], context [angle, cell], context days),
    whole counts summed one day at a time, so memory is one day's runs plus the sums, whatever the days.
    - totals and days: over the kept days each airport averages: its classed kept days in the months it
      passed, or with `every_month` every classed kept day of the year (comparison only: unchecked months).
    - context: every pass over the cell (all traffic, unpublishable), over every kept day of
      `context_months` (or of the year with `every_month`), classed or not."""
    codes = sorted(publish)
    months = {c: set(publish[c]) for c in codes}
    totals = np.zeros((len(ao.ANGLES), len(CLASSES), len(cells_j), len(codes)), np.int64)
    days = np.zeros((len(codes), len(CLASSES)), np.int64)
    context, context_days = np.zeros((len(ao.ANGLES), len(cells_j)), np.int64), 0
    for n, d in enumerate(plan['kept']):
        meta, path = metas[d]
        take = []  # (airport column here, index in the day file, class)
        for col, code in enumerate(codes):
            label = plan['labels'].get((d, code))
            if label is None or not (every_month or f'{d:%Y%m}' in months[code]):
                continue
            if label not in CLASSES:
                raise SystemExit(f'classify_day() returned {label!r}: not one of {CLASSES}')
            take.append((col, meta['codes'].index(code), CLASSES.index(label)))
        in_context = every_month or f'{d:%Y%m}' in context_months
        if not take and not in_context:
            continue
        runs = day_runs(path, totals=in_context)
        for ai, angle in enumerate(ao.ANGLES):
            every, per = runs[angle]
            got = at_cells(per, cells_j, cells_i, [k for _, k, _ in take])
            for x, (col, _, cl) in enumerate(take):
                totals[ai, cl, :, col] += got[:, x]
            if in_context:
                context[ai] += at_cells(every, cells_j, cells_i, [0])[:, 0]
        for col, _, cl in take:
            days[col, cl] += 1
        context_days += in_context
        if progress and (n + 1) % 30 == 0:
            progress(f'{n + 1} of {len(plan["kept"])} kept days read')
    return totals, days, context, context_days


# ---------------------------------------------------------------- the file


def build(day_files, official_by_month, postcodes, every_month=False, progress=None, min_months=MIN_CHECKED_MONTHS):
    """Everything the file holds, as {name: array} plus 'meta', from day files, the CAA's monthly figures
    ({'YYYYMM': {code: n}}) and the postcodes (covered_postcodes()'s list)."""
    metas = read_metas(day_files)
    plan = plan_days(metas)
    verdicts, unchecked = month_verdicts(metas, plan['gaps'], official_by_month)
    codes = sorted({c for m, _ in metas.values() for c in m['codes']})
    publish, refused = airports_to_publish(verdicts, codes, min_months)
    pub = sorted(publish)

    pc, lad, city = (_fixed([p[k] for p in postcodes], width, what)
                     for k, width, what in ((0, 8, 'postcode'), (1, 9, 'LAD code'), (2, 16, 'city id')))
    east = np.array([p[3] for p in postcodes], dtype=float)
    north = np.array([p[4] for p in postcodes], dtype=float)
    gridind = np.array([p[5] for p in postcodes], dtype=np.int8)
    cj, ci = (north // ao.CELL_M).astype(np.int64), (east // ao.CELL_M).astype(np.int64)
    if len(cj) and (cj.min() < 0 or cj.max() >= ao.NROWS or ci.min() < 0 or ci.max() >= ao.NCOLS):
        raise SystemExit('a postcode lies off the British National Grid the day files use')
    cell_key, cell_of = np.unique(cj * ao.NCOLS + ci, return_inverse=True)
    checked = sorted(p for p in official_by_month if p not in unchecked)
    totals, days, context, context_days = accumulate(metas, plan, publish, cell_key // ao.NCOLS, cell_key % ao.NCOLS,
                                                     every_month, progress, set(checked))

    if totals.max(initial=0) > np.iinfo(np.int32).max:
        raise SystemExit('a summed count over 2**31: not a real count')
    # [angle, class, cell, airport] -> [postcode, airport, class, angle]
    total = totals.transpose(2, 3, 1, 0)[cell_of].astype(np.int32)
    with np.errstate(invalid='ignore', divide='ignore'):
        mean = (total / days[None, :, :, None]).astype(np.float32)
    mean[:, days == 0, :] = np.nan  # no day of this kind: not measured, never 0
    # [angle, cell] -> [postcode, angle]; NaN, never 0, when no day was read
    every = (context.T[cell_of] / context_days if context_days else np.full((len(pc), len(ao.ANGLES)), np.nan))
    in_months = {f'{d:%Y%m}' for d in metas}
    meta = {
        'definition': 'CAA CAP 1498 overflights (above 48.5 and 60 degrees, under 7,000 ft) per 100 m BNG cell, '
                      'averaged per day of each kind; a postcode reads the cell holding its ONS grid reference',
        'zero_and_nan': {'0': 'measured zero: the airport is published, its days of this kind were counted, and none '
                              'of its traffic passed over the cell at this angle',
                         'NaN': 'not measured: the airport had no kept day of this kind (days is 0)',
                         'airport absent': 'not published: see not_published'},
        'rule': ('an airport is published only when its tracking passed coverage_verdict() in every month checked '
                 f'(a CAA figure and a day file for every day), on one reading of its circuits, at least '
                 f'{min_months} of them'),
        'min_checked_months': min_months,
        'days_used': ('every classed kept day of the year, unchecked months too (comparison only)' if every_month
                      else "each airport's classed kept days in the months it passed; unchecked months left out"),
        'published': {c: {'months': publish[c], 'days': dict(zip(CLASSES, days[k].tolist(), strict=True))}
                      for k, c in enumerate(pub)},
        'not_published': refused,
        'monthly_verdicts': verdicts,
        'months_unchecked': {**unchecked, **{m: 'no CAA figure on disk yet' for m in sorted(in_months)
                                             if m not in official_by_month}},
        'days': {'files': len(metas), 'kept': len(plan['kept']), 'first': min(metas).isoformat(),
                 'last': max(metas).isoformat(),
                 'left_out_outage': [d.isoformat() for d in sorted(metas) if plan['gaps'][d]],
                 'not_judged': [d.isoformat() for d in sorted(metas) if plan['gaps'][d] is None],
                 'archive_gaps': {d.isoformat(): why for d, why in ARCHIVE_GAPS.items()},
                 'unclassified': sorted(f'{d} {c}' for (d, c), lab in plan['labels'].items()
                                        if lab is None and c in publish)},
        'airports_no_longer_drawn': sorted(plan['unknown']),
        'context_all_traffic_unpublishable': (
            'UNPUBLISHABLE CONTEXT, never a published figure: every pass over the cell a day (every airport, '
            'published or not, and other traffic), averaged over every kept day of '
            + ('the year' if every_month else f'the months checked ({", ".join(checked)})')
            + f', {context_days} days, no direction split'),
        'position_quality': {
            'counts': {str(k): int(v) for k, v in zip(*np.unique(gridind, return_counts=True), strict=True)},
            'meaning': "NSPL gridind: 1 the building nearest the postcode's mean (best); 3 within 50 m; 5 imputed by "
                       'ONS; 6 the postcode sector mean (5 and 6 can sit hundreds of metres out, scripts/load_nspl.py); '
                       '9 (no position) left out'},
        'cells': int(len(cell_key)),
        'generator': 'scripts/adsb_postcode_averages.py',
        'licence': 'derived from adsb.lol (ODbL 1.0) and CAA Table 03; unpublished',
    }
    return {
        'postcode': pc, 'lad': lad, 'city': city, 'easting': east, 'northing': north, 'gridind': gridind,
        'airports': np.array(pub, dtype='<U5'), 'classes': np.array(CLASSES), 'angles': np.array(ao.ANGLES),
        'days': days.astype(np.int32), 'total': total, 'mean': mean,
        'context_all_traffic_unpublishable': every.astype(np.float32), 'context_days': np.int32(context_days),
    }, meta


def _fixed(values, width, what):
    """`values` as a fixed-width string array, refusing any longer than `width`: numpy would cut it silently."""
    if any(len(v) > width for v in values):
        raise SystemExit(f'a {what} longer than {width} characters: the file would cut it')
    return np.array(values, dtype=f'<U{width}')


def write(arrays, meta, out):
    """One .npz, written whole or not at all (a .partial renamed), as the day files are."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + '.partial')
    with open(tmp, 'wb') as fh:
        np.savez_compressed(fh, meta=np.array(json.dumps(meta, separators=(',', ':'))), **arrays)
    os.replace(tmp, out)


def read(path):
    """(arrays, meta) from a written file; no pickles are loaded."""
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files if k != 'meta'}
        meta = json.loads(str(z['meta']))
    return arrays, meta


# ---------------------------------------------------------------- command line


def _verdict_table(verdicts, unchecked, publish, refused):
    months = sorted({p for v in verdicts.values() for p in v})
    print('tracked / CAA (scaled to the kept days) per month, with circuits; c = passed only without them '
          '(ratio shown without); * = failed\n')
    print('airport ' + ' '.join(f'{p:>7}' for p in months) + '   year')
    for code in sorted(verdicts):
        cells = []
        for p in months:
            v = verdicts[code].get(p)
            plain = v and v['ok'] and not v['readings']['with circuits']
            cells.append(f'{"-":>7}' if v is None or not v['official'] else
                         f'{(v["tracked"] - (v["circuits"] if plain else 0)) / v["official"]:6.1%}'
                         + ('c' if plain else ' ' if v['ok'] else '*'))
        print(f'{code:7} ' + ' '.join(cells) + ('   PUBLISHED' if code in publish else '   not published'))
    for p, why in sorted(unchecked.items()):
        print(f'month {p} not checked: {why}')
    print()
    for code, why in sorted(refused.items()):
        print(f'NOT PUBLISHED {code}: {why}')


def _per_day(v):
    """A mean for printing: a small non-zero value never prints as 0.0, which is the measured zero's text."""
    return '0' if v == 0 else f'{v:.1f}' if v >= 0.05 else f'{v:.3f}'


def _readout(path, wanted):
    arrays, meta = read(path)
    index = {p.replace(' ', ''): k for k, p in enumerate(arrays['postcode'])}
    airports = list(arrays['airports'])
    print(f'{path.name}: {len(arrays["postcode"]):,} postcodes, {meta["cells"]:,} cells; {meta["days_used"]}')
    for code, info in meta['published'].items():
        print(f'  {code}: days {info["days"]}; months passed {info["months"][0]}-{info["months"][-1]}')
    for want in wanted:
        k = index.get(want.replace(' ', '').upper())
        if k is None:
            print(f'{want}: not in the file (not a live postcode of a covered council, or no grid reference)')
            continue
        quality = int(arrays['gridind'][k])
        print(f'\n{arrays["postcode"][k]} ({arrays["lad"][k]}, {arrays["city"][k]}), '
              f'BNG {arrays["easting"][k]:.0f},{arrays["northing"][k]:.0f}, gridind {quality}'
              + ('' if quality == 1 else ' (A COARSE POSITION: it can sit hundreds of metres out)')
              + '; per day at 48.5 (60) degrees, from these published airports only:')
        for a, code in enumerate(airports):
            m = arrays['mean'][k, a]
            if not np.nansum(m):
                continue
            print(f'  {code}: ' + '  '.join(
                f'{c} {_per_day(m[x, 0])} ({_per_day(m[x, 1])})' if np.isfinite(m[x, 0]) else f'{c} not measured'
                for x, c in enumerate(CLASSES)))
        quiet = [code for a, code in enumerate(airports) if not np.nansum(arrays['mean'][k, a])]
        if quiet:
            print(f'  measured zero on every kind of day measured: {", ".join(quiet)}')
        every = arrays['context_all_traffic_unpublishable'][k]
        print(f'  UNPUBLISHABLE CONTEXT, all traffic over the cell (every airport and "other", '
              f'{int(arrays["context_days"])} kept days, no direction split): '
              f'{_per_day(every[0])} ({_per_day(every[1])}) a day')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('files', type=Path, nargs='*', help='day files (default: every data/adsb/overflights/*.npz)')
    ap.add_argument('--caa-dir', type=Path, default=CAA_DIR)
    ap.add_argument('--verdicts', action='store_true', help='print the monthly verdicts and the rule, build nothing')
    ap.add_argument('--every-month', action='store_true',
                    help='average every kept day, unchecked months too (comparison only; its own file)')
    ap.add_argument('--out', type=Path, help=f'default {OUT.relative_to(ROOT)}')
    ap.add_argument('--at', action='append', default=[], help='read these postcodes from the built file')
    a = ap.parse_args()
    out = a.out or (OUT_ALL_MONTHS if a.every_month else OUT)
    if a.at:
        _readout(out, a.at)
        return 0
    files = a.files or sorted(DAY_DIR.glob('*.npz'))
    official = caa_months(a.caa_dir)
    if a.verdicts:
        metas = read_metas(files)
        plan = plan_days(metas)
        verdicts, unchecked = month_verdicts(metas, plan['gaps'], official)
        publish, refused = airports_to_publish(verdicts, sorted({c for m, _ in metas.values() for c in m['codes']}))
        _verdict_table(verdicts, unchecked, publish, refused)
        return 0
    t0 = time.time()

    def progress(text):
        print(f'  {text} ({time.time() - t0:.0f} s)', flush=True)

    lad_map = _load('build_borough_bands').load_lad_map()
    postcodes, left_out = covered_postcodes(lad_map)
    progress(f'{len(postcodes):,} live postcodes in {len({p[1] for p in postcodes})} of {len(lad_map)} covered '
             f'councils; left out {left_out}')
    arrays, meta = build(files, official, postcodes, a.every_month, progress)
    meta['postcodes_left_out'] = left_out
    write(arrays, meta, out)
    progress(f'wrote {out}')
    for k, code in enumerate(arrays['airports']):
        m = arrays['mean'][:, k, :, 0]
        print(f'  {code}: ' + ', '.join(
            f'{c} {int(np.sum(m[:, x] > 0)):,} postcodes > 0 (>= 1 a day: {int(np.sum(m[:, x] >= 1)):,})'
            if arrays['days'][k, x] else f'{c} not measured' for x, c in enumerate(CLASSES)))
    for code, why in meta['not_published'].items():
        print(f'  NOT PUBLISHED {code}: {why}')
    print(f'  position quality (NSPL gridind): {meta["position_quality"]["counts"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
