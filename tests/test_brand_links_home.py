"""The "Sky Score" brand goes home from every public page (Bill, 2026-10-19).

Bill asked that clicking "Sky Score" anywhere, top left for example, brings a visitor back to the front page.
Most pages already linked it; the full map's title and /score-demo/'s heading did not. This finds the FIRST
"Sky Score" a visitor sees on each page (outside scripts, styles and the <title>) and asserts it sits inside a
link to "/". The pages are FOUND, not listed, so a new page is held to it the day it is added; the few that
have no brand are declared with a reason, and a declared page that gains one fails too, so the list cannot
go stale in either direction.
"""
import glob
import html.parser
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATTERNS = ('*.html', 'home/**/*.html', 'api/**/*.html', 'open-data/**/*.html', 'talks/*.html',
            'bay-area/*.html', 'score-demo/*.html', 'area/**/index.html', 'how-it-works/*.html', 'about/*.html',
            'planes-overhead/**/index.html')  # gitignored, built by scripts/build_planes_pages.py (2026-10-28)
# Pages with no site brand, and why. A page here that DOES link its first "Sky Score" home must leave.
NO_BRAND = {
    'home/moved/preview/index.html': 'redirect stub for the old /preview/: its only job is the link home',
    'home/moved/preview/reports/index.html': 'redirect stub for the old /preview/reports/',
    'talks/how-sky-score-works.html': 'printed handout: "Sky Score" is in the document title, and a PDF has no site bar',
}
SKIP = ('script', 'style', 'title', 'template', 'noscript')
VOID = ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr')


class FirstBrand(html.parser.HTMLParser):
    """Whether the first visible "Sky Score" text is inside <a href="/">: True, False, or None if absent."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.skipping, self.links_home = [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skipping += 1
        if tag not in VOID:
            self.stack.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skipping = max(0, self.skipping - 1)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.links_home is None and not self.skipping and 'Sky Score' in data:
            self.links_home = any(t == 'a' and a.get('href') == '/' for t, a in self.stack)


def first_brand(path):
    parser = FirstBrand()
    parser.feed(path.read_text(encoding='utf-8'))
    return parser.links_home


def pages():
    found = set()
    for pattern in PATTERNS:
        found.update(Path(p).relative_to(REPO).as_posix() for p in glob.glob(str(REPO / pattern), recursive=True))
    return sorted(found)


class TheBrandGoesHome(unittest.TestCase):
    def test_every_public_page_links_its_brand_home(self):
        missing = {p for p in pages() if p not in NO_BRAND and first_brand(REPO / p) is not True}
        self.assertEqual(missing, set(), 'the first "Sky Score" on these pages is not a link to "/"')

    def test_the_declared_pages_still_have_no_brand_link(self):
        stale = {p for p in NO_BRAND if (REPO / p).exists() and first_brand(REPO / p) is True}
        self.assertEqual(stale, set(), 'these now link their brand home: remove them from NO_BRAND')

    def test_the_two_pages_fixed_on_19_october(self):
        # The full map's title (whose text applyCityChrome() rewrites, so the link wraps the heading) and the
        # API demo page's heading: the two that did not link home.
        for page in ('index.html', 'score-demo/index.html'):
            with self.subTest(page=page):
                self.assertIs(first_brand(REPO / page), True)

    def test_the_pages_are_found_not_listed(self):
        found = pages()
        self.assertGreater(len(found), 100, 'the globs found almost nothing: have the pages moved?')
        for page in ('index.html', 'home/index.html', 'pricing.html', 'bay-area/index.html'):
            self.assertIn(page, found)


if __name__ == '__main__':
    unittest.main()
