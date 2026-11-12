"""Tests for scripts/build_bayarea_records.py, the Bay Area's city records in the score Lambda (2026-10-22).

Every input file is committed, so these run on the real block: it is what the readers' files give; no US
record carries a UK field name (so no UK ramp can score a US figure); every missing input carries its
reader's reason and no other field is missing; the anchors are the three files' California figures; and the
check reds an edited block. Offline.
"""

import importlib.util
import json
import re
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


# THE SITE'S HOLDER (2026-11-07, the Bay Area's site scores): the same records, written into index.html's
# BAYAREA-RECORDS block by the same derivation, with the anchors, the price top code and the few-residents note
# READ from app.py. The full map scores each city from it, so a hand-edit there is the site and the API
# publishing two numbers for one city.
def test_the_site_block_is_the_same_records_and_the_lambdas_own_constants():
    anchors, rows = br.records()
    lam = br.LAMBDA.read_text(encoding='utf-8').replace('\r\n', '\n')
    site = br.SITE.read_text(encoding='utf-8').replace('\r\n', '\n')
    i, j = br.span(site, br.SITE_START, br.SITE_END, br.SITE)
    assert site[i:j] == br.render_site(anchors, rows, br.lambda_constants(lam))
    constants = br.lambda_constants(lam)
    assert constants['US_PRICE_TOP_CODE'] == app.US_PRICE_TOP_CODE
    assert constants['_CRIME_FEW_RESIDENTS_NOTE'] == app._CRIME_FEW_RESIDENTS_NOTE
    for name, rec in rows:
        assert json.dumps(rec, ensure_ascii=False) in site[i:j], name


@pytest.mark.parametrize('old, new', [
    ('"floodSfhaPct": 7.04}', '"floodSfhaPct": 7.0}'),   # a site value edited by hand
    ('const US_CALIFORNIA_ANCHORS = {"crimePer1000Us": 21.39', 'const US_CALIFORNIA_ANCHORS = {"crimePer1000Us": 21.4'),
    ('const US_PRICE_TOP_CODE = 2000000;', 'const US_PRICE_TOP_CODE = 1000000;'),
])
def test_the_check_reds_an_edited_site_block(tmp_path, monkeypatch, capsys, old, new):
    text = br.SITE.read_text(encoding='utf-8')
    assert text.count(old) == 1
    stand_in = tmp_path / 'index.html'
    stand_in.write_text(text.replace(old, new), encoding='utf-8')
    monkeypatch.setattr(br, 'SITE', stand_in)
    monkeypatch.setattr(sys, 'argv', ['build_bayarea_records.py', '--check'])
    assert br.main() == 1
    assert 'BAYAREA-RECORDS block' in capsys.readouterr().out


# EACH FIGURE WITH ITS SOURCE AND YEAR (Bill, 2026-11-07). The year is READ from the reader's own file, so a roll
# moves the label on the map, the front page and the area pages at once; a typed year would not move.
def test_every_source_label_carries_the_year_its_file_holds():
    sources = br.input_sources()
    assert set(sources) == {'avgPrice', 'trend', 'crimePer1000Us', 'transport', 'roadNoiseUsSharePct', 'floodSfhaPct'}
    assert sources['crimePer1000Us'].endswith(str(data('us-bayarea-crime.json')['year']))
    assert sources['avgPrice'].endswith(data('us-bayarea-prices.json')['vintage'])
    assert sources['trend'].endswith(str(data('us-bayarea-trend.json')['counties'][0]['year']))
    assert sources['floodSfhaPct'].endswith(data('us-bayarea-flood.json')['fema_fetched_utc'][:4])
    assert all(re.search(r'\b(19|20)\d\d\b', label) for label in sources.values()), sources


def test_a_label_follows_its_file_when_the_year_moves(monkeypatch):
    real = br._read

    def rolled(name):
        doc = real(name)
        if name == 'us-bayarea-crime.json':
            doc = {**doc, 'year': 2031}
        return doc

    monkeypatch.setattr(br, '_read', rolled)
    assert br.input_sources()['crimePer1000Us'] == 'California DOJ OpenJustice, 2031'


def test_every_city_says_each_input_with_its_source_and_never_a_placeholder():
    anchors, rows = br.records()
    sources = br.input_sources()
    for name, rec in rows:
        facts = br.input_facts(name, rec, anchors, sources, app.US_PRICE_TOP_CODE, app._CRIME_FEW_RESIDENTS_NOTE)
        assert [label for label, _, _ in facts] == ['Median home value', 'County price trend', 'Crime', 'Rail access',
                                                     'Road noise', 'Flood risk'], name
        for label, figure, source in facts:
            assert source in sources.values() and not re.search(r'None|nan|undefined', figure), (name, label, figure)
        for field, reason in (rec.get('withheld') or {}).items():
            assert any(reason in figure for _, figure, _ in facts), (name, field)
        if rec['priceTopCoded']:
            assert '2000001' not in facts[0][1] and '2,000,001' not in facts[0][1], name


def test_the_site_block_carries_the_sources_and_the_us_scales_line():
    site = br.SITE.read_text(encoding='utf-8')
    assert f'const BAYAREA_INPUT_SOURCES = {json.dumps(br.input_sources(), ensure_ascii=False)};' in site
    assert f'const BAYAREA_US_SCALES = {json.dumps(br.us_scales(len(app.BAYAREA_BOROUGHS)), ensure_ascii=False)};' in site
    assert 'Not comparable with a UK score' in br.us_scales(50)
