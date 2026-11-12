"""The N65 gate's input made by code from the day files (scripts/n65_gate_run.py), 2026-11-12: N65's frozen method.

Every day file here is MADE UP (shaped like scripts/n65_day.py's), so it runs anywhere. Held: the period and the
missing days come from the files; the average day is named from the period; rule 1 multiplies each day by its own
scale and refuses a day without one; rule 2 reads the 5-12 shares and refuses a day without them; rule 3 judges both
stage ends; days made by other code are refused; the CAA's own areas pass every level, and still do after the verdict
file's JSON round trip; a hybrid run decides nothing; the CLI writes the verdict beside the days. Item 3: the people
inside each end's 50-event contour are counted from a population file and judged; a contour at the grid's edge refuses
the count; the CLI refuses a Heathrow run without the file unless --no-population (then "not measured"), and never asks
for it on Gatwick's. Offline only.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import n65_gate as gate  # noqa: E402
import n65_gate_run as gr  # noqa: E402

N = 20_000  # cells of 100 m: 0.01 km2 each


def _meta(day, **over):
    m = {'airport': 'LHR', 'day': day, 'window_local': '07:00-23:00', 'threshold_db': 65.0, 'cell_m': 100.0,
         'grid': {'x0': 0.0, 'y0': 0.0, 'nx': 200, 'ny': 100}, 'computed_share': 0.97, 'scale': 1.0,
         'spread': {'s_db': 2.0, 'z_cut': 5.0, 'floor_db': 55.4605}, 'variant': 'default', 'code': 'c0de',
         'anp_fingerprint': 'f00d'}
    m.update(over)
    return m


def _arrays(arrivals, light=None, heavy=None, spread=None):
    """Plain counts and their spread twins (the spread ones `spread` times the plain, default the same)."""
    z = np.zeros(N)
    a = {'arrivals': np.asarray(arrivals, float), 'departures_light': z if light is None else np.asarray(light, float),
         'departures_heavy': z if heavy is None else np.asarray(heavy, float)}
    a.update({f'{k}_p': v * (spread if spread is not None else 1.0) for k, v in list(a.items())})
    return a


def _target_counts():
    """A count grid whose areas ARE the CAA's Heathrow figures: 18,480 cells reach 50, 11,100 reach 100, ..."""
    c = np.zeros(N)
    c[:18480], c[:11100], c[:5970], c[:730] = 60, 150, 300, 600
    return c


def _days(first, n, **meta):
    d0 = dt.date.fromisoformat(first)
    return [(d0 + dt.timedelta(days=k)).isoformat() for k in range(n)]


def test_the_period_and_its_missing_days_come_from_the_files():
    names = ['2025-03-30', '2025-03-31', '2025-04-02', '2025-04-03']
    days = [(_meta(d), _arrays(np.full(N, 10.0))) for d in names]
    airport, runs, about = gr.build_runs(days)
    assert airport == 'LHR'
    for end in gate.STAGE_ENDS:
        assert runs[end]['period'] == ('2025-03-30', '2025-04-03')
        assert runs[end]['missing_days'] == ['2025-04-01']
        assert runs[end]['day'] == '5-day average'
        assert all(isinstance(k, int) for k in runs[end]['areas_km2'])


def test_the_average_day_is_named_from_the_period():
    assert gr.day_kind(('2025-03-30', '2026-03-29')) == 'annual average'  # ERCD 2601's year
    assert gr.day_kind(('2025-06-16', '2025-09-15')) == 'summer average'  # ERCD 2602's 92-day summer
    assert gr.day_kind(('2025-03-30', '2026-03-28')) == '364-day average'
    assert gr.day_kind(('2025-06-16', '2025-09-14')) == '91-day average'


def test_rule_1_scales_each_day_by_its_own_factor():
    # 40 a day everywhere on both days; scaled by 1.0 and 2.0 the average day is 60 (reaches 50), unscaled 40 (does not).
    days = [(_meta('2025-03-30', scale=1.0), _arrays(np.full(N, 40.0))),
            (_meta('2025-03-31', scale=2.0), _arrays(np.full(N, 40.0)))]
    assert gr.build_runs(days)[1]['light']['areas_km2'][50] == pytest.approx(N * 0.01)
    assert gr.build_runs(days, scaled=False)[1]['light']['areas_km2'][50] == 0.0


def test_a_day_without_its_scale_is_refused_unless_asked_unscaled():
    days = [(_meta('2025-03-30', scale=None), _arrays(np.full(N, 40.0)))]
    with pytest.raises(gr.Refused, match='rule 1'):
        gr.build_runs(days)
    assert gr.build_runs(days, scaled=False)


def test_rule_2_reads_the_shares_and_refuses_a_day_without_them():
    # Plain counts 40, shares 1.5 x (60): only the spread run reaches 50.
    days = [(_meta('2025-03-30'), _arrays(np.full(N, 40.0), spread=1.5))]
    assert gr.build_runs(days)[1]['heavy']['areas_km2'][50] == pytest.approx(N * 0.01)
    assert gr.build_runs(days, spread=False)[1]['heavy']['areas_km2'][50] == 0.0
    old = {k: v for k, v in _arrays(np.full(N, 40.0)).items() if not k.endswith('_p')}
    with pytest.raises(gr.Refused, match='rule 2'):
        gr.build_runs([(_meta('2025-03-30'), old)])
    assert gr.build_runs([(_meta('2025-03-30'), old)], spread=False)


def test_both_stage_ends_are_judged():
    c = _target_counts()
    heavy = np.zeros(N)
    heavy[:2000] = 60  # the heavy end adds departures only where 50 is already reached: the light end reads 184.8
    days = [(_meta(d), _arrays(c, heavy=heavy)) for d in _days('2025-03-30', 365)]
    result = gr.verdict(days)
    assert any(line.startswith('[light] LHR >50: 184.8 km2') and line.endswith('pass') for line in result['lines'])
    heavier = np.zeros(N)
    heavier[:1200] = 600  # the heavy end's 500-event area 12.0 km2 against 7.3 (+64%): a MISS on that end alone
    days = [(_meta(d), _arrays(c, heavy=heavier)) for d in _days('2025-03-30', 365)]
    result = gr.verdict(days)
    assert any(line.startswith('[heavy] LHR >500') and line.endswith('MISS') for line in result['lines'])
    assert any(line.startswith('[light] LHR >500') and line.endswith('pass') for line in result['lines'])


def test_days_made_by_other_code_or_tables_are_refused():
    for key, value in (('code', 'other'), ('anp_fingerprint', 'other'), ('variant', 'hybrid'), ('threshold_db', 70.0)):
        days = [(_meta('2025-03-30'), _arrays(np.full(N, 1.0))), (_meta('2025-03-31', **{key: value}),
                                                                  _arrays(np.full(N, 1.0)))]
        with pytest.raises(gr.Refused, match=f'{key} differs'):
            gr.build_runs(days)
    with pytest.raises(gr.Refused, match='given twice'):
        gr.build_runs([(_meta('2025-03-30'), _arrays(np.full(N, 1.0)))] * 2)


def test_the_caas_own_areas_pass_every_level_and_still_do_after_the_files_round_trip():
    days = [(_meta(d), _arrays(_target_counts(), heavy=np.zeros(N))) for d in _days('2025-03-30', 365)]
    result = gr.verdict(days)
    levels = [line for line in result['lines'] if ' km2 against ' in line]
    assert len(levels) == 8 and all(line.endswith('pass') for line in levels), levels
    # Not a pass: no population given (the gate says "not measured"), and the made-up tables are no deciding database.
    assert not result['ok']
    assert '[light] LHR population >50: not measured' in result['lines']
    assert any('a building run, never a deciding one' in line for line in result['lines'])
    # The verdict file is JSON: its runs, read back, must still be judged level by level.
    back = json.loads(json.dumps(result))['runs']
    ok, lines = gate.bracket_verdict('LHR', back)
    assert sum(line.endswith('pass') for line in lines if ' km2 against ' in line) == 8, lines


def test_a_hybrid_run_is_a_bound_and_decides_nothing():
    days = [(_meta(d, variant='hybrid'), _arrays(_target_counts())) for d in _days('2025-03-30', 3)]
    assert any('a bound, never the model' in line for line in gr.verdict(days)['lines'])


def _interior_target_counts():
    """_target_counts()'s areas, every cell away from the grid's edge (a population count refuses an edge)."""
    nx, ny = 200, 100
    inner = [j * nx + i for j in range(1, ny - 1) for i in range(1, nx - 1)]
    c = np.zeros(N)
    for share, value in ((18480, 60), (11100, 150), (5970, 300), (730, 600)):
        c[inner[:share]] = value
    return c, inner


def _population_file(path, points):
    """A made-up n65_population file: [(east, north, residents)] on _meta()'s grid (100 m cells from 0, 0)."""
    e, n, r = zip(*points, strict=True)
    np.savez_compressed(path, meta=json.dumps({'kind': gr.pop.KIND, 'source': gr.pop.SOURCE, 'census_sha256': 'x'}),
                        east=np.asarray(e, float), north=np.asarray(n, float), residents=np.asarray(r, np.int32),
                        large_user=np.zeros(len(e), bool), retired=np.zeros(len(e), bool))
    return path


def test_the_people_inside_the_50_event_contour_are_counted_and_judged(tmp_path):
    counts, inner = _interior_target_counts()
    i, j = inner[0] % 200, inner[0] // 200  # a cell inside the 50-event contour
    people = gr.pop.load(_population_file(tmp_path / 'p.npz', [
        (i * 100 + 50, j * 100 + 50, 528_800),  # the CAA's own figure, inside
        (19_950, 9_950, 999_999)]))  # a far corner cell at 0: outside
    days = [(_meta(d), _arrays(counts, heavy=np.zeros(N))) for d in _days('2025-03-30', 365)]
    result = gr.verdict(days, population=people)
    for end in gate.STAGE_ENDS:
        assert result['runs'][end]['population_above_50'] == 528_800
        assert result['about']['population'][end]['postcodes'] == 1
    assert '[light] LHR population >50: 528,800 against 528,800 (+0.0%; -20% to +20%) pass' in result['lines']
    judged = [line for line in result['lines'] if ' km2 against ' in line or 'population >50' in line]
    assert len(judged) == 10 and all(line.endswith('pass') for line in judged), judged
    assert not result['ok']  # the made-up tables are no deciding database
    # Without the file the run says "not measured" and the gate fails it: never a guess.
    assert gr.verdict(days)['runs']['light']['population_above_50'] is None


def test_a_contour_at_the_grids_edge_refuses_the_count(tmp_path):
    people = gr.pop.load(_population_file(tmp_path / 'p.npz', [(150, 150, 10)]))
    days = [(_meta(d), _arrays(_target_counts())) for d in _days('2025-03-30', 2)]  # starts at cell 0: the edge
    with pytest.raises(gr.Refused, match="population \\(light\\): the 50-event contour reaches the grid's edge"):
        gr.build_runs(days, population=people)


def _write_days(tmp_path, counts):
    for d in ('2025-03-30', '2025-03-31'):
        np.savez_compressed(tmp_path / f'LHR-{d}-n65.npz', meta=json.dumps(_meta(d)),
                            **{k: v.astype(np.float32) for k, v in _arrays(counts).items()})


def test_the_cli_writes_the_verdict_beside_the_days(tmp_path):
    _write_days(tmp_path, np.full(N, 40.0))
    people = _population_file(tmp_path / 'p.npz', [(150, 150, 10)])
    assert gr.main(['--day', str(tmp_path / 'LHR-*-n65.npz'), '--population', str(people)]) == 0
    written = list(tmp_path.glob('gate-LHR-2025-03-30_2025-03-31-default-scaled-spread.json'))
    assert len(written) == 1
    result = json.loads(written[0].read_text(encoding='utf-8'))
    assert result['about']['days'][0]['scale'] == 1.0 and result['runs']['light']['day'] == '2-day average'
    assert result['runs']['light']['population_above_50'] == 0  # counted: nothing reaches 50 here
    assert gr.main(['--day', str(tmp_path / 'nothing-*.npz')]) == 2


def test_the_cli_refuses_without_the_population_file_unless_asked(tmp_path, capsys):
    _write_days(tmp_path, np.full(N, 40.0))
    days = ['--day', str(tmp_path / 'LHR-*-n65.npz')]
    assert gr.main([*days, '--population', str(tmp_path / 'missing.npz')]) == 2
    assert 'REFUSED: no population file' in capsys.readouterr().out
    assert gr.main([*days, '--population', str(tmp_path / 'missing.npz'), '--no-population']) == 0
    assert 'LHR population >50: not measured' in capsys.readouterr().out
    # Gatwick's rule has no population check, so its run never asks for the file.
    for d in ('2025-06-16', '2025-06-17'):
        np.savez_compressed(tmp_path / f'LGW-{d}-n65.npz', meta=json.dumps(_meta(d, airport='LGW')),
                            **{k: v.astype(np.float32) for k, v in _arrays(np.full(N, 40.0)).items()})
    assert gr.main(['--day', str(tmp_path / 'LGW-*-n65.npz'), '--population', str(tmp_path / 'missing.npz')]) == 0
