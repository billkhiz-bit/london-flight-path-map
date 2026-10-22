"""Tests for scripts/build_bayarea_quiet.py, a Bay Area city's aircraft band (release 2, 2026-10-22).

The Census frame is gitignored, so the guards are tested on the committed file and on stand-ins: the mean is
rounded DOWN, so a band never moves quieter than the unrounded estimate; each band starts at its figure; and
the offline check reds a band that is not its mean's, a refitted geometry block, and a Lambda that now reads
differently at a probe, which is how a refit that was never re-derived is caught without the frame. Offline.
"""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('build_bayarea_quiet', REPO_ROOT / 'scripts' / 'build_bayarea_quiet.py')
bq = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bq)


def places():
    doc = json.loads((REPO_ROOT / 'data' / 'us-bayarea-places.json').read_text(encoding='utf-8'))
    return [p for p in doc['places'] if p['kind'] in ('city', 'town')]


def committed():
    return json.loads(bq.OUT.read_text(encoding='utf-8'))


@pytest.mark.parametrize('x, want', [
    (9.999, 9.99), (4.996, 4.99), (5.0, 5.0), (7.5, 7.5), (10.0, 10.0), (0.0, 0.0), (1.2449, 1.24),
])
def test_the_mean_rounds_down_toward_loud(x, want):
    assert bq.floor2(x) == want


@pytest.mark.parametrize('mean, band', [
    (10.0, 'low'), (9.99, 'low-moderate'), (7.5, 'low-moderate'), (7.49, 'moderate'), (5.0, 'moderate'),
    (4.99, 'moderate-high'), (3.0, 'moderate-high'), (1.5, 'high'), (1.49, 'severe'), (0.0, 'severe'),
])
def test_each_band_starts_at_its_figure(mean, band):
    assert bq.band_of(mean) == band


def test_rounding_down_never_moves_a_band_quieter():
    # just under each edge: rounded to NEAREST these would read the quieter band
    for edge in (10.0, 7.5, 5.0, 3.0, 1.5):
        assert bq.band_of(bq.floor2(edge - 0.004)) != bq.band_of(edge)


def test_the_committed_file_passes_its_own_check():
    assert bq.problems(committed(), places()) == []


def _mutated(fn):
    doc = copy.deepcopy(committed())
    fn({r['name']: r for r in doc['cities']}, doc)
    return doc


@pytest.mark.parametrize('mutate, message', [
    # a band one step quieter than its mean
    (lambda rows, doc: rows['San Francisco'].update(band='low'), 'is not the band of'),
    # a mean rounded to nearest instead of down
    (lambda rows, doc: rows['Newark'].update(quiet_mean=9.996), 'to two places'),
    # the geometry was refitted after the file was written
    (lambda rows, doc: doc.update(geometry_sha256='0' * 64), 'refitted'),
    # the Lambda reads differently at a probe than when the file was written
    (lambda rows, doc: rows['South San Francisco']['probe'].update(quiet=9.9), 'at its probe'),
    # the band table itself changed
    (lambda rows, doc: doc['impact_to_quiet'].update(moderate=5.5), 'IMPACT_TO_QUIET'),
    # a city dropped
    (lambda rows, doc: doc['cities'].remove(rows['Colma']), 'exactly the 50 cities'),
])
def test_the_check_reds_each_defect(mutate, message):
    found = bq.problems(_mutated(mutate), places())
    assert any(message in f for f in found), found


def test_a_change_to_the_geometry_block_moves_the_fingerprint(tmp_path, monkeypatch):
    text = bq.LAMBDA.read_text(encoding='utf-8')
    before = bq.fingerprint()
    moved = text.replace("{'code': 'SJC', 'name': 'San Jose'", "{'code': 'SJC', 'name': 'San José'", 1)
    assert moved != text
    stand_in = tmp_path / 'app.py'
    stand_in.write_text(moved, encoding='utf-8')
    monkeypatch.setattr(bq, 'LAMBDA', stand_in)
    assert bq.fingerprint() != before
    # ...but line endings alone do not
    stand_in.write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    assert bq.fingerprint() == before
