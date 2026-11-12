"""The Bay Area's area pages and the /area/ index (2026-11-07, the site's Bay Area release).

Each Bay Area page says its score is on US scales, says every input in the records builder's words with its
source and year, and never borrows New York's affordability note (it said "Scored against New York's five
boroughs, the only US prices held" for every US city until this release). The /area/ index says THE coverage
sentence, the same one how-it-works and llms.txt say. Read from the built pages, offline.
"""

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))
import app  # noqa: E402
import build_bayarea_records as records  # noqa: E402

SPEC = importlib.util.spec_from_file_location('build_area_pages_us', REPO / 'scripts' / 'build_area_pages.py')
pages = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pages)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_llms_txt import COVERAGE  # noqa: E402  (THE sentence's pattern, one holder)


def page(name):
    return (REPO / 'area' / 'bayarea' / pages.slug(name) / 'index.html').read_text(encoding='utf-8')


def text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).replace('&#x27;', "'").replace('&amp;', '&')


def test_every_bay_area_city_has_a_page_with_the_apis_score_on_us_scales():
    scales = records.us_scales(len(app.CITIES['bayarea']['boroughs']))
    for name in app.CITIES['bayarea']['boroughs']:
        body, _ = app.resolve_query({'borough': name, 'city': 'bayarea'})
        shown = text(page(name))
        assert f'{body["score"]} Sky Score out of 10' in shown, name
        assert scales in shown, f'{name}: the US-scales line is missing'
        assert "New York's five boroughs" not in shown and 'the only US prices held' not in shown, name


def test_every_input_is_said_with_its_source_and_year():
    anchors, rows = records.records()
    sources = records.input_sources()
    for name, rec in rows:
        shown = text(page(name))
        for label, _figure, source in records.input_facts(name, rec, anchors, sources, app.US_PRICE_TOP_CODE):
            assert source in shown, (name, label)
            assert re.search(r'\b20\d\d\b', source), (name, label, source)


def test_the_area_index_says_the_one_coverage_sentence():
    index = text((REPO / 'area' / 'index.html').read_text(encoding='utf-8'))
    ours = COVERAGE.search(index + '.') or COVERAGE.search(index)
    site = COVERAGE.search((REPO / 'how-it-works' / 'index.html').read_text(encoding='utf-8'))
    assert ours and site and ours.groups() == site.groups(), 'the /area/ index and how-it-works say different coverage'
    assert '(facts only' not in index
