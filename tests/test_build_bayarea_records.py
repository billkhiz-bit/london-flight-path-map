"""Tests for scripts/build_bayarea_records.py, the Bay Area's city records in the score Lambda (2026-10-22).

Every input file is committed, so these run on the real block: it is what the readers' files give; no US
record carries a UK field name (so no UK ramp can score a US figure); every missing input carries its
reader's reason and no other field is missing; the anchors are the three files' California figures; and the
check reds an edited block. Offline.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('build_bayarea_records', REPO_ROOT / 'scripts' / 'build_bayarea_records.py')
br = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(br)
sys.path.insert(0, str(REPO_ROOT / 'backend' / 'lambdas' / 'score'))
import app  # noqa: E402

UK_FIELDS = {'crimeRate', 'roadNoiseAboveWhoPct', 'floodMediumOrHighPct', 'airQualityWhoRatio', 'p8', 'schools',
             'healthcare'}
WITHHOLDABLE = {'crimePer1000Us', 'transport', 'floodSfhaPct'}


def data(name):
    return json.loads((REPO_ROOT / 'data' / name).read_text(encoding='utf-8'))


def test_the_block_is_what_the_files_give():
    anchors, rows = br.records()
    text = br.LAMBDA.read_text(encoding='utf-8').replace('\r\n', '\n')
    i, j = br.span(text)
    assert text[i:j] == br.render(anchors, rows)
    assert app.BAYAREA_BOROUGHS == dict(rows)
    assert app.US_CALIFORNIA_ANCHORS == anchors


def test_no_us_record_carries_a_uk_field():
    for name, rec in app.BAYAREA_BOROUGHS.items():
        assert not UK_FIELDS & set(rec), name


def test_a_missing_input_carries_its_readers_reason_and_only_those_may_be_missing():
    for name, rec in app.BAYAREA_BOROUGHS.items():
        missing = {k for k, v in rec.items() if v is None}
        assert missing <= WITHHOLDABLE, name
        assert missing == set(rec.get('withheld', {})), name
        assert all(isinstance(r, str) and r for r in rec.get('withheld', {}).values()), name


def test_the_withheld_sets_are_the_readers_own():
    held = lambda f: {n for n, r in app.BAYAREA_BOROUGHS.items() if f in r.get('withheld', {})}  # noqa: E731
    assert held('floodSfhaPct') == {r['name'] for r in data('us-bayarea-flood.json')['cities'] if r['withheld']}
    assert held('transport') == {r['name'] for r in data('us-bayarea-transport.json')['cities'] if r['withheld']}
    assert held('crimePer1000Us') == {r['name'] for r in data('us-bayarea-crime.json')['cities']
                                      if r['per_1000'] is None}


def test_the_anchors_are_californias_measured_figures():
    assert app.US_CALIFORNIA_ANCHORS == {
        'crimePer1000Us': data('us-bayarea-crime.json')['california']['per_1000'],
        'roadNoiseUsSharePct': data('us-bayarea-road.json')['california']['share_at_or_above_45_db_pct'],
        'floodSfhaPct': data('us-california-flood.json')['sfha_pct'],
    }


def test_the_categorical_fields_are_in_the_scoring_vocabulary():
    app.validate_borough_vocabulary({'bayarea': {'boroughs': app.BAYAREA_BOROUGHS}})


def test_a_top_coded_price_is_the_census_code_never_a_typed_figure():
    capped = {n for n, r in app.BAYAREA_BOROUGHS.items() if r['priceTopCoded']}
    assert len(capped) == 16
    assert {app.BAYAREA_BOROUGHS[n]['avgPrice'] for n in capped} == {2000001}


@pytest.mark.parametrize('old, new', [
    ("'floodSfhaPct': 7.04}", "'floodSfhaPct': 7.0}"),   # a value edited by hand
    ("US_CALIFORNIA_ANCHORS = {'crimePer1000Us': 21.39", "US_CALIFORNIA_ANCHORS = {'crimePer1000Us': 21.4"),
])
def test_the_check_reds_an_edited_block(tmp_path, monkeypatch, capsys, old, new):
    text = br.LAMBDA.read_text(encoding='utf-8')
    assert text.count(old) == 1
    stand_in = tmp_path / 'app.py'
    stand_in.write_text(text.replace(old, new), encoding='utf-8')
    monkeypatch.setattr(br, 'LAMBDA', stand_in)
    monkeypatch.setattr(sys, 'argv', ['build_bayarea_records.py', '--check'])
    assert br.main() == 1
    assert 'not what the readers' in capsys.readouterr().out
