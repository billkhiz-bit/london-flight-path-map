"""llms.txt says only what the site says, and links only to pages that exist (2026-11-02).

/llms.txt is a plain summary of the site for language-model tools (llmstxt.org): a title, a one-paragraph summary,
then sections of links. Its words are held by tests/test_public_wording.py like every published page; this file
holds the rest: the coverage sentence is the site's own (how-it-works says it), every skyscore.co.uk link is a page
in a sitemap, the only outside link is the methodology the site's own footer links, and the Makefile uploads it.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # the wording gate, read as a module
SITE = 'https://skyscore.co.uk'
# The numbers and "facts only" must match; how-it-works goes on inside the bracket ("facts only, with no score on the
# site yet"), llms.txt closes it there.
COVERAGE = re.compile(r'(\d+) council areas in (\d+) UK city regions, plus New York\'s (\d+) boroughs and (\d+) Bay Area '
                      r'cities \(facts only')
OUTSIDE_LINKS_ALLOWED = {
    # The methodology the site's footer links ("METHODOLOGY V5.7"); it lives in the public repo.
    'https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md',
}


def text():
    return (ROOT / 'llms.txt').read_text(encoding='utf-8')


def sitemap_urls():
    urls = set()
    for name in ('sitemap.xml', 'sitemap-planes.xml'):
        path = ROOT / name
        if path.exists():
            urls |= set(re.findall(r'<loc>([^<]+)</loc>', path.read_text(encoding='utf-8')))
    return urls


class LlmsTxtTests(unittest.TestCase):

    def test_its_shape_is_llmstxt_org(self):
        lines = text().splitlines()
        self.assertTrue(lines[0].startswith('# '), 'starts with the site name as a level-1 heading')
        self.assertTrue(any(line.startswith('> ') for line in lines[1:4]), 'a one-paragraph summary follows it')
        self.assertIn('## Optional', text())

    def test_the_coverage_sentence_is_the_sites_own(self):
        ours = COVERAGE.search(text())
        site = COVERAGE.search((ROOT / 'how-it-works' / 'index.html').read_text(encoding='utf-8'))
        self.assertIsNotNone(ours, 'llms.txt must say the coverage sentence')
        self.assertIsNotNone(site, 'how-it-works no longer says it: find its holder before changing this test')
        self.assertEqual(ours.groups(), site.groups())

    def test_every_link_is_a_page_we_publish(self):
        links = re.findall(r'\]\((https?://[^)\s]+)\)', text())
        self.assertGreater(len(links), 10)
        known = sitemap_urls()
        planes_live = (ROOT / 'sitemap-planes.xml').exists()
        missing = [u for u in links if u not in OUTSIDE_LINKS_ALLOWED and u.startswith(SITE)
                   and u not in known and (planes_live or '/planes-overhead/' not in u)]
        outside = [u for u in links if not u.startswith(SITE) and u not in OUTSIDE_LINKS_ALLOWED]
        self.assertEqual(missing, [], 'linked but in no sitemap')
        self.assertEqual(outside, [], 'an outside link nobody reviewed')

    def test_the_makefile_uploads_it(self):
        makefile = (ROOT / 'Makefile').read_text(encoding='utf-8')
        self.assertIn('aws s3 cp llms.txt', makefile)
        self.assertIn("'/llms.txt'", makefile, 'and invalidates it, or an edit waits out the cache')

    def test_the_drift_check_compares_it(self):
        # Found 2026-11-02 after the first deploy: the drift check listed robots.txt and sitemap.xml but not
        # llms.txt, so a meta-deploy that never uploaded it (or a stale live copy) would have passed unseen.
        drift = (ROOT / 'scripts' / 'check_deploy_drift.sh').read_text(encoding='utf-8')
        self.assertRegex(drift, r'(?m)^llms\.txt\|llms\.txt\r?$')

    def test_the_wording_gate_reads_it(self):
        import test_public_wording as gate  # pylint: disable=import-outside-toplevel
        self.assertIn('llms.txt', gate.everything())
        self.assertIn('Quiet Skies is an estimate', gate.shown('llms.txt')[0])


if __name__ == '__main__':
    unittest.main()
