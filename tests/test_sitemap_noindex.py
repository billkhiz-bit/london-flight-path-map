"""No page in sitemap.xml asks search engines not to index it (2026-11-09).

Search Console emailed "Excluded by 'noindex' tag" for a page in a sitemap: /score-demo/status.html was listed in
sitemap.xml while its own <meta name="robots"> said noindex,follow. A sitemap says "index this", the tag says "do
not": Google reports the contradiction and trusts the sitemap less. build_area_pages.write_sitemap() now refuses a
noindex page; this test holds the file it wrote, and proves the detector red on the page that caused it.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_area_pages as bap  # noqa: E402

SITE = 'https://skyscore.co.uk'


class SitemapNoindex(unittest.TestCase):
    def test_no_sitemap_page_asks_noindex(self):
        locs = re.findall(r'<loc>([^<]+)</loc>', (ROOT / 'sitemap.xml').read_text(encoding='utf-8'))
        self.assertTrue(locs, 'sitemap.xml lists no URLs')
        hidden = [loc for loc in locs if bap.asks_noindex(bap.source_file(loc.removeprefix(SITE)))]
        self.assertEqual(hidden, [], 'listed in sitemap.xml, but the page asks not to be indexed')

    def test_detector_is_red_on_the_page_that_caused_it(self):
        # The status page stays noindex on purpose; if it ever loses the tag, this says so rather than passing blind.
        self.assertTrue(bap.asks_noindex('score-demo/status.html'))
        self.assertTrue(bap.asks_noindex('talks/index.html'))
        self.assertFalse(bap.asks_noindex('home/index.html'))

    def test_detector_reads_the_forms_we_write(self):
        for tag in ('<meta name="robots" content="noindex">', "<meta name='robots' content='noindex,follow'>",
                    '<META CONTENT="NoIndex" NAME="Robots" />', '<meta name="googlebot" content="noindex">'):
            self.assertTrue(bap.noindex_in(tag), tag)
        for tag in ('<meta name="robots" content="index,follow">', '<meta name="description" content="noindex me">',
                    '<!-- noindex: a comment is not a tag -->'):
            self.assertFalse(bap.noindex_in(tag), tag)


if __name__ == '__main__':
    unittest.main()
