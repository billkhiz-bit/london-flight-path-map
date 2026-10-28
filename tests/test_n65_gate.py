"""The N65 publish gate (2026-10-28): Bill's 27 Oct rule, held before any model exists.

`scripts/n65_gate.py` decides whether an N65 map may be published by comparing our contours with the CAA's (ERCD 2601
Heathrow, ERCD 2602 Gatwick). These tests hold: the CAA's own figures pass on the deciding database; each band's
edges, both sides, with reading UNDER the CAA the tighter one; Heathrow's 500-event band and population check; a level,
a population or an airport not measured fails; another period, day or window fails however close the areas; a run
on the free legacy tables never decides; and every target equals the figure in the report's own text (skipped, with
the reason, where the gitignored reports are not on this machine). Offline only.
"""
import importlib.util
import re
import sys
from pathlib import Path

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


gate = _load('n65_gate')
FULL = gate.DECIDING_DATABASE


def _run(code, scale=None, population=1.0, **override):
    """A run equal to the CAA's figures, each level times scale[level] (default 1)."""
    t = gate.TARGETS[code]
    run = {'period': t['period'], 'day': t['day'], 'window': t['window'],
           'areas_km2': {lv: km2 * (scale or {}).get(lv, 1.0) for lv, km2 in t['areas_km2'].items()},
           'population_above_50': None if t['population_above_50'] is None else t['population_above_50'] * population}
    run.update(override)
    return run


def _both(**lhr):
    return {'LHR': _run('LHR', **lhr), 'LGW': _run('LGW')}


def test_the_caas_own_figures_pass_on_the_deciding_database():
    ok, lines = gate.publish_verdict(_both(), FULL)
    assert ok, lines


@pytest.mark.parametrize('factor, passes', [(0.90, True), (0.899, False), (1.15, True), (1.151, False)])
def test_each_area_band_edge(factor, passes):
    for level in (50, 100, 200):
        assert gate.publish_verdict(_both(scale={level: factor}), FULL)[0] is passes, (level, factor)
    runs = {'LHR': _run('LHR'), 'LGW': _run('LGW', scale={500: factor})}  # Gatwick: AREA_BAND at every level
    assert gate.publish_verdict(runs, FULL)[0] is passes


def test_reading_under_the_caa_gets_the_tighter_side():
    assert gate.publish_verdict(_both(scale={100: 1.12}), FULL)[0]
    assert not gate.publish_verdict(_both(scale={100: 0.88}), FULL)[0]


@pytest.mark.parametrize('factor, passes', [(0.70, True), (0.69, False), (1.30, True), (1.31, False)])
def test_heathrows_500_event_band_is_wider(factor, passes):
    assert gate.publish_verdict(_both(scale={500: factor}), FULL)[0] is passes


@pytest.mark.parametrize('factor, passes', [(0.80, True), (0.79, False), (1.20, True), (1.21, False)])
def test_population_inside_the_50_event_contour(factor, passes):
    assert gate.publish_verdict(_both(population=factor), FULL)[0] is passes


def test_anything_not_measured_fails():
    run = _run('LHR')
    del run['areas_km2'][200]
    ok, lines = gate.publish_verdict({'LHR': run, 'LGW': _run('LGW')}, FULL)
    assert not ok and 'LHR >200: not measured' in lines
    ok, lines = gate.publish_verdict({'LHR': _run('LHR', population_above_50=None), 'LGW': _run('LGW')}, FULL)
    assert not ok and 'LHR population >50: not measured' in lines
    ok, lines = gate.publish_verdict({'LHR': _run('LHR')}, FULL)
    assert not ok and 'LGW: no run' in lines


@pytest.mark.parametrize('key, value', [('period', ('2026-01-01', '2026-08-31')), ('day', 'summer average'),
                                        ('window', '00:00-24:00')])
def test_another_period_day_or_window_never_passes(key, value):
    ok, lines = gate.publish_verdict(_both(**{key: value}), FULL)
    assert not ok and any(f'not like for like: {key}' in line for line in lines)


def test_a_run_on_the_free_legacy_tables_never_decides():
    ok, lines = gate.publish_verdict(_both(), 'easa-anp-2.3')
    assert not ok and any('a building run, never a deciding one' in line for line in lines)


def _report(name):
    path = REPO / 'data' / 'n65' / 'text' / name
    if not path.exists():
        pytest.skip(f'{path.relative_to(REPO)} is not on this machine (gitignored: data/n65/, from the CAA reports)')
    return path.read_text(encoding='utf-8', errors='replace')


def test_heathrows_targets_are_the_reports_figures():
    text = _report('ercd-lhr-2025.txt')
    table = text[text.index('Table 16 Heathrow 2006 and 2025 annual average 16-hour day N65'):][:2500]
    for level, km2 in gate.TARGETS['LHR']['areas_km2'].items():
        row = re.search(rf'^> {level}\s+(.*)$', table, re.M).group(1).split()
        assert row[1] == f'{km2:.1f}', (level, row)  # 2006 area, 2025 area, change, ...
    row50 = re.search(r'^> 50\s+(.*)$', table, re.M).group(1).split()
    assert float(row50[4]) * 1000 == gate.TARGETS['LHR']['population_above_50']  # population, thousands
    assert '30 March 2025' in text or '30 Mar 2025' in text


def test_gatwicks_targets_are_the_reports_figures():
    text = _report('gatwick-2025-contours.txt')
    start = [m.start() for m in re.finditer(r'Table 15 Gatwick 2025 summer day actual modal split N65', text)][-1]
    table = text[start:][:1500]
    for level, km2 in gate.TARGETS['LGW']['areas_km2'].items():
        assert re.search(rf'^> {level}\s+{km2:.1f}\s', table, re.M), level
