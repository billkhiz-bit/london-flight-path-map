"""The About page names only publishers we really use (2026-10-24, Bill: "What you can hold us to").

/about/ names the organisations its figures come from, each in a `<span class="src">`. A name there is a public
claim that Sky Score uses that publisher's data, so each must map to a source in LICENSING.md's live tables (the
API's and the site's, never "Removed sources", which lists what we stopped using). The map below is the one place
a new name is added; a name on the page that it does not know fails, so neither side can drift from the other.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The name as the About page says it -> the words LICENSING.md uses for that source.
PUBLISHERS = {
    'DEFRA': 'DEFRA',
    'Environment Agency': 'Environment Agency',
    'ONS': 'ONS',
    'HM Land Registry': 'HM Land Registry',
    'Department for Education': 'Department for Education',
    'Department for Transport': 'DfT National Public Transport Access Nodes',
    'NHS': 'NHS Organisation Data Service',
    'UK AIP (NATS)': 'UK Aeronautical Information Publication (UK AIP)',
    'Breathe London': 'Breathe London',
    'FAA': 'FAA',
    'US Census Bureau': 'US Census Bureau',
    'Bureau of Transportation Statistics': 'BTS National Transportation Noise Map',
    'FEMA': 'FEMA',
    'EPA': 'US EPA',
}


def named_on_about():
    html = (ROOT / 'about' / 'index.html').read_text(encoding='utf-8')
    return re.findall(r'<span class="src">([^<]+)</span>', html)


def live_sources():
    """LICENSING.md's source rows, from the API's table to the start of "Removed sources"."""
    text = (ROOT / 'LICENSING.md').read_text(encoding='utf-8')
    start = text.index('## Sources used by the B2B API')
    end = text.index('## Removed sources')
    return text[start:end]


class AboutSourcesTests(unittest.TestCase):
    def test_the_page_names_publishers(self):
        self.assertGreaterEqual(len(named_on_about()), 5, 'the About page names almost no publishers: was the line removed?')

    def test_every_name_on_the_page_is_known_here(self):
        unknown = sorted(set(named_on_about()) - set(PUBLISHERS))
        self.assertEqual(unknown, [], 'named on /about/ but not mapped to LICENSING.md here: add it to PUBLISHERS')

    def test_every_name_is_a_live_source_in_licensing(self):
        live = live_sources()
        missing = sorted(name for name in set(named_on_about()) if PUBLISHERS.get(name) and PUBLISHERS[name] not in live)
        self.assertEqual(missing, [], 'named on /about/ but not a live source in LICENSING.md (removed, or never used)')


if __name__ == '__main__':
    unittest.main()
