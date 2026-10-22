"""Per-postcode overflight averages, and who may be published (2026-10-22).

`scripts/adsb_postcode_averages.py` reads the year's day files at every covered postcode's cell, for the
airports whose tracking passed coverage_verdict() in every month the CAA has published. These tests hold its
rules on tiny synthetic day files and a seven-row NSPL, one at a time: the year rule (every month checked, one
reading of the circuits, six months at least); a month with no CAA figure left out of every average; the
monthly verdict by report()'s arithmetic (a day with no field level, a feed too sparse to judge, circuits that
fit one reading only); a failing airport ABSENT, never a column of zeros; a measured zero (0) told apart from
not measured (NaN); the days left out exactly as adsb_overflights.average() leaves them out, with counts that
differ by day so a wrongly kept day shows; the all-traffic context column, unpublishable by name; a day with
no file passing as an outage only when the archive is known to lack it; and a postcode read at ONS's British
grid reference or not at all (Northern Ireland out, nothing re-projected, its position quality carried).
Offline only.
"""
import datetime as dt
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pa = _load('adsb_postcode_averages')
ao = _load('adsb_overflights')
mv = _load('adsb_movements')

CODES = sorted(ao.uk_airports())
E0, N0 = 519150.0, 176750.0  # a cell centre by Kew (the overflight tests' cell)
CELL = (int(N0 // ao.CELL_M), int(E0 // ao.CELL_M))  # (j, i)
QUIET = (CELL[0] + 50, CELL[1] + 50)  # 5 km away: no run ever covers it
NBINS = 86400 // mv.FEED_BIN_S
W, E, M = (pa.CLASSES.index(c) for c in ('westerly', 'easterly', 'mixed'))


def _hours(n):
    return [0] * 9 + [n] + [0] * 14


def _day_file(tmp_path, day, lhr_runway='27L', lhr_moves=100, mme_moves=50, lhr_passes=7, outage=False,
              lhr_circuits=0, no_field=()):
    """One synthetic day file: LHR lands `lhr_moves` on one runway end (`lhr_circuits` of them circuits) and
    puts `lhr_passes` overflights on CELL; Teesside lands `mme_moves` and puts 3 there, OTHER traffic 11, so the
    cell's all-traffic count is lhr_passes + 14. An airport in `no_field` had no field level that day."""
    feed = [100] * NBINS
    if outage:
        feed[:30] = [0] * 30
    movements = {c: {'landing': {}, 'take-off': {}, 'circuits': {'landing': {}, 'take-off': {}}} for c in CODES}
    movements['LHR']['landing'][lhr_runway] = _hours(lhr_moves)
    if lhr_circuits:
        movements['LHR']['circuits']['landing'][lhr_runway] = _hours(lhr_circuits)
    movements['MME']['landing']['23'] = _hours(mme_moves)
    fields = {c: {'field': 0, 'how': 'test'} for c in CODES}
    for code in no_field:
        fields[code] = {'field': None, 'how': 'too few aircraft'}
        movements[code] = {'landing': {}, 'take-off': {}, 'circuits': {'landing': {}, 'take-off': {}}}
    meta = {'day': day, 'codes': CODES + [ao.OTHER], 'feed': {'uk': feed, 'us': feed}, 'movements': movements,
            'fields': fields}
    j, i = CELL
    rows = [[CODES.index('LHR'), j, i, i, lhr_passes], [CODES.index('MME'), j, i, i, 3], [len(CODES), j, i, i, 11]]
    by_airport = np.array(rows, np.int32)
    cells = {a: (np.array([[j, i, i, lhr_passes + 14]], np.int32), by_airport) for a in ao.ANGLES}
    path = tmp_path / f'{day}.npz'
    ao.write_day(cells, meta, path)
    return path


def _february(tmp_path, skip=(), **kw):
    return [_day_file(tmp_path, f'2026-02-{d:02d}', **kw) for d in range(1, 29) if d not in skip]


def _postcodes(city='london'):
    """Two postcodes: one in CELL (a building-level position), one in a cell nothing passes over (imputed)."""
    return [('TW9 3PZ', 'E09000027', city, E0 + 3, N0 - 21, 1),
            ('TW9 9ZZ', 'E09000027', city, QUIET[1] * 100 + 50.0, QUIET[0] * 100 + 50.0, 5)]


# ---------------------------------------------------------------- the year rule


def _month(ok=True, readings=('with circuits', 'without circuits'), reason='98.0% of the official count'):
    return {'ok': ok, 'reason': reason if ok else 'misses flights (90.0% of the official count): would understate',
            'readings': {r: ok and r in readings for r in ('with circuits', 'without circuits')}}


def test_published_only_when_every_month_checked_passes_on_one_reading():
    months = {f'2026{m:02d}': _month() for m in range(1, 7)}
    assert pa.year_rule(months)[0]
    # One failed month of six, however good the rest: not published, and the month is named.
    ok, reason = pa.year_rule({**months, '202604': _month(ok=False)})
    assert not ok and '202604' in reason
    # Every month passed, but January to March only without circuits and April to June only with them.
    split = {p: _month(readings=('without circuits',) if p < '202604' else ('with circuits',)) for p in months}
    assert not pa.year_rule(split)[0]
    # The same months all passing without circuits is one reading: published (Leeds Bradford, 2026).
    assert pa.year_rule({p: _month(readings=('without circuits',)) for p in months})[0]
    # Five months is under the six the rule asks for; no month at all is never a pass.
    assert not pa.year_rule({p: v for p, v in months.items() if p != '202606'})[0]
    assert pa.year_rule({}) == (False, 'no month with an official figure to check its tracking against')


def test_a_month_without_a_caa_figure_is_left_out_unless_asked_for(tmp_path):
    # February has a CAA figure and passes; March has none, and its days carry 1,000 passes each, so any of
    # them in an average shows. By default they are in no average and not in the context column either.
    files = _february(tmp_path) + [_day_file(tmp_path, f'2026-03-{d:02d}', lhr_passes=1000) for d in range(1, 11)]
    arrays, meta = pa.build(files, {'202602': {'LHR': 2800}}, _postcodes(), min_months=1)
    assert arrays['days'][0].tolist() == [28, 0, 0] and meta['published']['LHR']['months'] == ['202602']
    assert arrays['total'][0, 0, W].tolist() == [7 * 28, 7 * 28]
    assert int(arrays['context_days']) == 28 and arrays['context_all_traffic_unpublishable'][0].tolist() == [21, 21]
    assert meta['months_unchecked'] == {'202603': 'no CAA figure on disk yet'}
    # --every-month (comparison only) takes them in.
    arrays, _ = pa.build(files, {'202602': {'LHR': 2800}}, _postcodes(), every_month=True, min_months=1)
    assert arrays['days'][0].tolist() == [38, 0, 0]
    assert arrays['total'][0, 0, W, 0] == 7 * 28 + 1000 * 10 and int(arrays['context_days']) == 38


# ---------------------------------------------------------------- the monthly verdict, by report()'s arithmetic


def test_the_monthly_verdict_follows_reports_arithmetic(tmp_path, monkeypatch):
    # LHR: 100 landings a day, 20 of them circuits, against 2,240 official (80 a day): 125% with its circuits,
    # 100% without, so it passes ONE way. Teesside: 50 a day, but no field level on Saturday 14 February: an
    # unmeasured day, never an outage, so the month cannot pass (counted, it would read 96.4% and pass).
    files = [_day_file(tmp_path, f'2026-02-{d:02d}', lhr_circuits=20, no_field=('MME',) if d == 14 else ())
             for d in range(1, 29)]
    metas = pa.read_metas(files)
    verdicts, unchecked = pa.month_verdicts(metas, pa.plan_days(metas)['gaps'], {'202602': {'LHR': 2240, 'MME': 1400}})
    lhr, mme = verdicts['LHR']['202602'], verdicts['MME']['202602']
    assert not unchecked
    assert (lhr['ok'], lhr['tracked'], lhr['circuits'], lhr['official'], lhr['kept_days']) == (True, 2800, 560, 2240, 28)
    assert lhr['readings'] == {'with circuits': False, 'without circuits': True} and 'without circuits' in lhr['reason']
    assert (mme['ok'], mme['reason']) == (False, '1 day(s) unmeasured: the period is incomplete')
    # A feed too sparse to judge (five days present, the rest archive gaps: under FEED_MIN_REFERENCE_DAYS
    # nearby) fails the month for that reason, as report() says it, not for whatever the arithmetic then does.
    sparse = tmp_path / 'sparse'
    sparse.mkdir()
    for d in range(6, 29):
        monkeypatch.setitem(pa.ARCHIVE_GAPS, dt.date(2026, 2, d), 'test: the archive has no such day')
    metas = pa.read_metas([_day_file(sparse, f'2026-02-{d:02d}') for d in range(1, 6)])
    gaps = pa.plan_days(metas)['gaps']
    assert all(g is None for g in gaps.values())
    verdicts, _ = pa.month_verdicts(metas, gaps, {'202602': {'LHR': 2800}})
    assert (verdicts['LHR']['202602']['ok'], verdicts['LHR']['202602']['reason']) == (False, 'feed not judged on every day')


# ---------------------------------------------------------------- absent is not zero


def test_a_failing_airport_is_absent_and_a_measured_zero_is_not_nan(tmp_path):
    files = _february(tmp_path)
    # LHR: 28 x 100 tracked against 2,800 official (100%). Teesside: 28 x 50 against 9,000 (16%): it fails.
    arrays, meta = pa.build(files, {'202602': {'LHR': 2800, 'MME': 9000}}, _postcodes(), min_months=1)
    assert list(arrays['airports']) == ['LHR']  # Teesside and OTHER are not columns of zeros...
    assert set(meta['not_published']) == set(CODES) - {'LHR'} | {ao.OTHER}  # ...each is listed, once
    assert 'misses flights' in meta['not_published']['MME']
    assert dict(zip(pa.CLASSES, arrays['days'][0].tolist(), strict=True)) == {'westerly': 28, 'easterly': 0, 'mixed': 0}
    mean, total = arrays['mean'], arrays['total']
    assert mean[0, 0, W, 0] == pytest.approx(7) and total[0, 0, W, 0] == 7 * 28  # the cell under the traffic
    assert mean[1, 0, W, 0] == 0.0 and total[1, 0, W, 0] == 0  # a measured zero: 28 westerly days, no pass
    assert np.isnan(mean[:, 0, [E, M], :]).all()  # no easterly or mixed day: not measured, never 0
    # The context column is every pass over the cell (LHR 7 + Teesside 3 + OTHER 11), Teesside's failed tracking
    # and OTHER's unchecked traffic included, which is why its name says it may not be published.
    ctx = arrays['context_all_traffic_unpublishable']
    assert ctx[0].tolist() == [21, 21] and ctx[1].tolist() == [0, 0] and int(arrays['context_days']) == 28
    assert 'UNPUBLISHABLE' in meta['context_all_traffic_unpublishable']
    assert arrays['gridind'].tolist() == [1, 5] and meta['position_quality']['counts'] == {'1': 1, '5': 1}


def test_the_days_left_out_are_the_days_average_leaves_out(tmp_path):
    # An outage day (5th) and two quiet days classify_day() leaves out (7th, 8th: under MIN_DAY_MOVEMENTS) carry
    # 1,000 passes each and every other day its own count (the day of the month), so a mean over the wrong days
    # cannot land on the right number; every third day flies easterly.
    files = []
    for d in range(1, 29):
        out = d in (5, 7, 8)
        files.append(_day_file(tmp_path, f'2026-02-{d:02d}', outage=d == 5, lhr_moves=5 if d in (7, 8) else 100,
                               lhr_runway='09L' if d % 3 == 0 else '27L', lhr_passes=1000 if out else d))
    plan = pa.plan_days(pa.read_metas(files))
    res = ao.average(files)
    assert [d.isoformat() for d in plan['kept']] == res['kept']
    assert [d.isoformat() for d in sorted(plan['gaps']) if plan['gaps'][d]] == res['left_out_outage'] == ['2026-02-05']
    assert sorted(f'{d} {c}' for (d, c), lab in plan['labels'].items() if lab is None) == res['unclassified']
    # The build's days and means are average()'s, kind by kind. (2,610 official is 100% of the 2,510 tracked once
    # scaled to the 27 kept days, weekday-weighted: the quiet 7th and 8th are a Saturday and a Sunday.)
    arrays, _ = pa.build(files, {'202602': {'LHR': 2610}}, _postcodes(), every_month=True, min_months=1)
    assert list(arrays['airports']) == ['LHR']
    groups = [tuple(g) for g in res['groups']]
    for cl, kind in enumerate(pa.CLASSES):
        if ('LHR', kind) not in groups:
            assert arrays['days'][0, cl] == 0 and np.isnan(arrays['mean'][:, 0, cl]).all()
            continue
        g = groups.index(('LHR', kind))
        assert arrays['days'][0, cl] == res['days_per_group'][g]
        for angle_index, angle in enumerate(ao.ANGLES):
            assert arrays['mean'][0, 0, cl, angle_index] == pytest.approx(ao.lookup(res['runs'][angle], E0, N0, g))
    assert arrays['days'][0].tolist() == [16, 9, 0]  # 25 kept, classed days: 9 easterly (3rd, 6th, ... 27th)


def test_a_day_without_a_file_is_an_outage_only_when_the_archive_lacks_it(tmp_path, monkeypatch):
    files = _february(tmp_path, skip=(10,))
    metas = pa.read_metas(files)
    gaps = pa.plan_days(metas)['gaps']
    verdicts, unchecked = pa.month_verdicts(metas, gaps, {'202602': {'LHR': 2800}})
    assert '202602' in unchecked and not verdicts  # an unexplained missing file never passes as an outage
    monkeypatch.setitem(pa.ARCHIVE_GAPS, dt.date(2026, 2, 10), 'test: the archive has no such day')
    verdicts, unchecked = pa.month_verdicts(metas, gaps, {'202602': {'LHR': 2800}})
    v = verdicts['LHR']['202602']
    assert not unchecked and v['ok'] and v['kept_days'] == 27  # left out, the official figure scaled to 27 days
    assert v['official'] == pytest.approx(2700, abs=1)


def test_a_name_too_long_for_its_column_is_refused_not_cut(tmp_path):
    with pytest.raises(SystemExit):
        pa.build(_february(tmp_path), {'202602': {'LHR': 2800}}, _postcodes(city='x' * 17), min_months=1)


# ---------------------------------------------------------------- reading the runs at a cell


def test_a_cell_reads_the_run_holding_it_and_nothing_else():
    runs = np.array([[0, 10, 5, 8, 3], [0, 10, 12, 12, 4], [2, 10, 5, 9, 6]], np.int32)
    j, i = np.array([10, 10, 10, 10, 11]), np.array([5, 8, 9, 12, 6])
    got = pa.at_cells(runs, j, i, [0, 2])
    assert got[:, 0].tolist() == [3, 3, 0, 4, 0]  # both ends of a run hold; the column after it does not
    assert got[:, 1].tolist() == [6, 6, 6, 0, 0]
    with pytest.raises(SystemExit):
        pa.at_cells(runs[[1, 0, 2]], j, i, [0])  # unsorted runs would read wrong, so they are refused


# ---------------------------------------------------------------- postcodes


NSPL_HEADER = 'pcd7,pcds,doterm,east1m,north1m,gridind,lad27cd,ctry27cd,lat,long'


def test_postcodes_are_live_british_and_at_ons_grid_reference(tmp_path):
    rows = [
        '"TW9 3PZ","TW9 3PZ","","519153","0176729","1","E09000027","E92000001",51.47,-0.29',
        '"TW9 1AA","TW9 1AA","201001","519000","0176000","1","E09000027","E92000001",51.46,-0.30',  # terminated
        # No grid reference, though gridind says 1: only the never-re-project rule can leave it out.
        '"TW9 2AA","TW9 2AA","","","","1","E09000027","E92000001",51.46,-0.30',
        # A BT postcode is on the Irish Grid: left out as such, even under a covered council's code.
        '"BT1 1AA","BT1 1AA","","334316","0374675","1","E09000027","N92000002",54.60,-5.93',
        '"AB1 0AA","AB1 0AA","","385386","0801193","1","S12000033","S92000003",57.10,-2.24',  # not covered
        # Imputed by ONS (gridind 5): coarse, so its quality travels with it, but it is not dropped.
        '"TW9 5AA","TW9 5AA","","518800","0175900","5","E09000027","E92000001",51.46,-0.30',
        '"TW9 6AA","TW9 6AA","","518700","0175800","9","E09000027","E92000001",51.46,-0.30',  # gridind 9: none
    ]
    nspl = tmp_path / 'nspl.csv'
    nspl.write_text('\n'.join([NSPL_HEADER, *rows]) + '\n', encoding='utf-8')
    got, left_out = pa.covered_postcodes({'E09000027': ('london', 'Richmond upon Thames')}, nspl)
    assert got == [('TW9 3PZ', 'E09000027', 'london', 519153.0, 176729.0, 1),  # lad27cd found by its prefix
                   ('TW9 5AA', 'E09000027', 'london', 518800.0, 175900.0, 5)]
    assert left_out == {'Northern Ireland (Irish Grid references), every BT row': 1,
                        'terminated (covered councils)': 1, 'no ONS grid reference (covered councils)': 2}
    two = tmp_path / 'two.csv'
    two.write_text(NSPL_HEADER.replace('ctry27cd', 'lad26cd') + '\n' + rows[0] + '\n', encoding='utf-8')
    with pytest.raises(SystemExit):
        pa.covered_postcodes({'E09000027': ('london', 'x')}, two)  # two LAD columns: stop, never guess
