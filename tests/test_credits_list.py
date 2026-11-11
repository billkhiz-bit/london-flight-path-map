"""How it works' credits list carries each air source's attribution word for word, as its publisher requires.

WHY (2026-11-11): the front page's folds now credit only what must sit beside a figure (adsb.lol's ODbL notice,
Breathe London's line) and link "All sources" to /how-it-works/#credits, so that list must hold every source
a fold leaves out. Breathe London's wording, "License" included, is theirs (breathelondon.org/developers, read
2026-10-11; scripts/fetch_breathe_london.py), and DEFRA's monitor line is uk-air's own: both are READ from the
data files that carry them, never retyped, so a re-fetch with new wording reds here.
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def credits_text():
    page = (ROOT / 'how-it-works' / 'index.html').read_text(encoding='utf-8')
    m = re.search(r'<section id="credits".*?</section>', page, re.S)
    assert m, 'How it works has no #credits section'
    return html.unescape(re.sub(r'<[^>]+>', '', m.group(0)))


def attribution(name):
    return json.loads((ROOT / 'data' / name).read_text(encoding='utf-8'))['attribution']


def test_breathe_london_attribution_word_for_word():
    assert attribution('breathe-london-sensors.json') in credits_text()


def test_defra_monitor_attribution_word_for_word():
    assert attribution('aurn-sites.json') in credits_text()


def test_every_planes_and_energy_source_is_credited():
    text = credits_text()
    for needle in ('adsb.lol', 'Open Database License (ODbL) 1.0', 'Iowa Environmental Mesonet', 'OS Terrain 50',
                   'National Statistics Postcode Lookup', 'Energy Performance of Buildings Register'):
        assert needle in text, needle
