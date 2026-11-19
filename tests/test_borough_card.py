"""The full map's borough card says what the borough's area page says (Bill's pick A, 2026-11-19).

js/panel-findings.mjs `councilLead()` and `AIRCRAFT_BAND_TONE` are the map's copies of scripts/build_area_pages.py
`card_lead()` and `AIRCRAFT_BAND_TONE`. A copy drifts, so the JS is run in node on EVERY borough's own card items (the
area page builder's) and held to the page's sentence word for word. That the map feeds them the same words from its own
data is held in a browser by tests/uk-city-panel.mjs ("A borough's answer card").

Also the advice (audit 2026-11-19 I-1): the card draws each borough's aircraft `note`, so no note may give advice or make
a superlative no gate holds ("the fastest-growing", "you will hear", "Avoid"). The curated `property` notes are not drawn.
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))
spec = importlib.util.spec_from_file_location('build_area_pages', REPO / 'scripts' / 'build_area_pages.py')
pages = importlib.util.module_from_spec(spec)
sys.modules['build_area_pages'] = pages
spec.loader.exec_module(pages)

MAP = (REPO / 'index.html').read_text(encoding='utf-8')
# Each phrase as card_items words it, less its word: what is left after the prefix is the word itself.
PREFIX = {key: phrase.split('{w}')[0] for _, key, _, phrase in pages.CARD_RATED}
PREFIX.update({'crime': 'crime is ', 'schools': 'schools are ', 'transport': 'transport access is ',
               'healthcare': 'healthcare access is ', 'prices': 'prices are '})


def every_card():
    cards = []
    for city, cfg in pages.app.CITIES.items():
        for borough in cfg['boroughs']:
            data = pages.gather(city, borough)
            if not data or len(data['facts']) < pages.MIN_FACTS:
                continue
            items = pages.card_items(data)
            cards.append({
                'where': f'{city}/{borough}',
                'items': [{'key': 'price' if i['key'] == 'prices' else i['key'], 'stand': i['stand'],
                           'word': i['phrase'][len(PREFIX[i['key']]):]} for i in items],
                'lead': pages.card_lead(items),
            })
    return cards


def run_js(script, payload):
    out = subprocess.run(  # noqa: S603 - node with our own fixed script
        ['node', '--input-type=module', '-e', script],  # noqa: S607 - node from PATH, as preflight runs it
        cwd=REPO, input=json.dumps(payload), capture_output=True, text=True, encoding='utf-8', check=True,
    ).stdout
    return json.loads(out)


def test_the_maps_headline_is_the_area_pages_for_every_borough():
    cards = every_card()
    assert len(cards) > 100, f'only {len(cards)} area pages gathered: the loop is broken'
    leads = run_js(
        "import { readFileSync } from 'node:fs';"
        "import { councilLead } from './js/panel-findings.mjs';"
        "const cards = JSON.parse(readFileSync(0, 'utf8'));"
        "console.log(JSON.stringify(cards.map((c) => councilLead(c.items))));",
        cards,
    )
    differ = [(c['where'], c['lead'], got) for c, got in zip(cards, leads, strict=True) if c['lead'] != got]
    assert not differ, f'{len(differ)} boroughs headlined differently, e.g. {differ[:3]}'
    # The comparison reached both outcomes: a headline, and none where nothing stands out.
    assert any(c['lead'] for c in cards) and sum(1 for c in cards if c['lead'] is None) >= 0
    assert sum(1 for c in cards if c['lead']) > 80


def test_the_aircraft_bands_verdicts_are_the_area_pages():
    tone = run_js(
        "import { AIRCRAFT_BAND_TONE } from './js/panel-findings.mjs'; console.log(JSON.stringify(AIRCRAFT_BAND_TONE));", None)
    assert tone == pages.AIRCRAFT_BAND_TONE


def test_no_borough_note_the_card_draws_gives_advice_or_an_ungated_superlative():
    # Barnet's "Most of the borough has quiet skies" describes its own sky and is kept (Bill's call, 19 Nov).
    allowed = {'Some Luton arrivals pass over at high altitude, but this is barely noticeable at ground level. '
               'Most of the borough has quiet skies.'}
    advice = re.compile(r"\b(avoid|negotiat\w*|bargain\w*|visit\w*|you (?:should|will|may|can|could|might)|if you|worth|"
                        r"recommend\w*|best|fastest|slowest|most|least|cheapest|dearest|priciest|highest|lowest|"
                        r"only buy|before (?:buying|committing|making|you)|excellent value|great value|good value)", re.I)
    # Single or double quotes ("Shepherd's"-style text), on the key's line or the next.
    notes = [m.group(2) for m in re.finditer(r"""\bnote:\s*(['"])((?:\\.|(?!\1).)*?)\1""", MAP, re.S)]
    assert len(notes) > 50, f'only {len(notes)} notes read: the parse is broken'
    said = [n for n in notes if advice.search(n) and n not in allowed]
    assert not said, f'notes with advice or an ungated superlative: {said}'


def test_the_card_never_draws_the_curated_property_notes():
    fn = re.search(r'function updateSidebar\(data.*?\n {6}\}\r?\n', MAP, re.S)
    assert fn, 'updateSidebar() not found'
    assert 'data.property' not in fn.group(0)
    assert 'getVerdict' not in MAP and 'PROPERTY ADVICE' not in MAP
