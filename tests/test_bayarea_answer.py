"""The Bay Area's answer first (Bill's pick A, 2026-11-26; mock-up claude.ai/artifact/EqrNDgsAhwsrPo51KMAMcE).

A Bay Area city opens on a headline and pills made by ONE rule, scripts/build_bayarea_records.py answer(): each US share
(road noise, crime, flood) against California's own figure, the anchor its US scale is built on. This file holds the rule
at its edges, and reads the rule's words back out of all three holders independently: the front page's data file, the
full map's generated block in index.html, and every built area page. A holder that drifts from the rule fails here as well
as in its builder's --check.
"""

import html
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import build_bayarea_records as bay  # noqa: E402

ANCHORS = {'crimePer1000Us': 20.0, 'roadNoiseUsSharePct': 10.0, 'floodSfhaPct': 4.0}


def rec(road=10.0, crime=20.0, flood=4.0, few=False, transport='moderate', impact='moderate'):
    return {'roadNoiseUsSharePct': road, 'crimePer1000Us': crime, 'floodSfhaPct': flood, 'crimeFewResidents': few,
            'transport': transport, 'impact': impact}


@pytest.mark.parametrize('ratio, word', [
    (2.0, 'far more'), (1.999, 'more'), (1.25, 'more'), (1.249, None), (1.0, None), (0.801, None),
    (0.8, 'less'), (0.501, 'less'), (0.5, 'far less'), (0.0, 'far less'),
])
def test_each_share_is_worded_by_its_ratio_to_californias_figure(ratio, word):
    assert bay.compare_word(10.0 * ratio, 10.0) == word


def test_a_share_not_held_is_never_compared():
    assert bay.compare_word(None, 10.0) is None
    assert [c['key'] for c in bay.california_comparisons(rec(flood=None), ANCHORS)] == ['road', 'crime']


def test_the_headline_names_the_city_and_says_more_first():
    lead = bay.answer_lead('Testville', rec(road=15.0, crime=30.0, flood=1.0), ANCHORS)
    assert lead == 'Testville has more road noise and crime than California as a whole, and far less flood risk'


def test_one_word_serves_where_it_can_else_each_topic_carries_its_own():
    assert bay.answer_lead('T', rec(road=15.0, crime=45.0, flood=4.0), ANCHORS) == \
        'T has more road noise and far more crime than California as a whole'
    assert bay.answer_lead('T', rec(road=7.0, crime=8.0, flood=1.0), ANCHORS) == \
        'T has less road noise, far less crime and far less flood risk than California as a whole'


def test_close_to_california_on_every_share_is_no_headline():
    assert bay.answer_lead('T', rec(), ANCHORS) is None


def test_a_few_residents_crime_rate_leaves_the_headline_and_the_pills():
    a = bay.answer('T', rec(crime=60.0, few=True), ANCHORS)
    assert a['lead'] is None and 'crime' not in {p['key'] for p in a['pills']}
    # Its figure is still compared on the card, marked, never hidden.
    assert [c for c in a['compare'] if c['key'] == 'crime'][0]['few'] is True


def test_pills_follow_the_uk_pages_rules_watch_first():
    a = bay.answer('T', rec(road=15.0, flood=1.0, transport='poor', impact='low'), ANCHORS)
    assert [(p['key'], p['stand']) for p in a['pills']] == [('road', 'watch'), ('rail', 'watch'), ('flood', 'good'), ('aircraft', 'good')]
    # A middle band is no verdict.
    assert bay.answer_pills(rec(transport='moderate', impact='low-moderate'), ANCHORS) == []


# ---- the real 50 cities, read back from every holder ----
ANCHORS_REAL, ROWS = bay.records()
WANT = {name: bay.answer(name, r, ANCHORS_REAL) for name, r in ROWS}


def test_san_francisco_says_the_sentence_bill_approved():
    assert WANT['San Francisco']['lead'] == \
        'San Francisco has more road noise and crime than California as a whole, and far less flood risk'


def test_no_headline_leads_with_a_published_route():
    """Oakland's 10R approach crosses ZIP 94103 but carried 1.7% of Oakland's landings: a route is not a reading."""
    for name, a in WANT.items():
        assert not re.search(r'approach|runway|departure|planes|flights', a['lead'] or '', re.I), name


def test_the_front_pages_file_holds_the_rule_for_every_city():
    rows = json.loads((ROOT / 'data' / 'us-bayarea-front.json').read_text(encoding='utf-8'))['rows']
    assert {r['borough']: r['answer'] for r in rows} == WANT


def test_the_full_maps_block_holds_the_rule_for_every_city():
    page = (ROOT / 'index.html').read_text(encoding='utf-8')
    block = page[page.index('// BAYAREA-RECORDS:START'):page.index('// BAYAREA-RECORDS:END')]
    decl = 'const BAYAREA_ANSWERS = '
    body = block[block.index(decl) + len(decl):block.index('};', block.index(decl)) + 1]
    assert json.loads(re.sub(r',\s*\}$', '}', body.strip())) == WANT


def test_every_area_page_says_the_same_headline_and_pills():
    for name, a in WANT.items():
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        text = (ROOT / 'area' / 'bayarea' / slug / 'index.html').read_text(encoding='utf-8')
        card = re.search(r'<div class="card-main">(.*?)</div>', text, re.S)
        lead = re.search(r'<p class="card-lead">(.*?)</p>', card.group(1)) if card else None
        assert (html.unescape(lead.group(1)) if lead else None) == a['lead'], name
        shown = re.findall(r'<a class="pill (watch|good)" href="#[^"]+">(?:<svg.*?</svg>)?([^<]+)<', card.group(1) if card else '')
        assert shown == [(p['stand'], p['pill']) for p in a['pills']], name
