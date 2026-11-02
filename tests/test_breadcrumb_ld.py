"""Every built page's breadcrumb for search engines agrees with the one a visitor sees (2026-11-02).

`build_area_pages.breadcrumb_ld()` writes a schema.org BreadcrumbList into the area pages, /open-data/ and every
planes overhead page (district, index, Heathrow consultation pack and hub), so search results can show the page's
place in the site. Search engines treat markup that disagrees with the page as spam, so the rule held here is:
every item but the last is a link the page's visible breadcrumb also shows (same words, same address, same order),
and the last item is the page itself (its canonical address). Built from the pages on disk, as a visitor gets them;
the planes pages are gitignored, so where they are absent (CI) only the area pages are read.
"""
import html
import json
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SITE = 'https://skyscore.co.uk'
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


class Crumbs(HTMLParser):
    """The visible breadcrumb's links, as (words, href), and the page's canonical address."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.canonical = [], None
        self._in_nav, self._href, self._text = False, None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'link' and a.get('rel') == 'canonical':
            self.canonical = a.get('href')
        if tag == 'nav' and 'crumbs' in (a.get('class') or '').split():
            self._in_nav = True
        elif self._in_nav and tag == 'a':
            self._href, self._text = a.get('href'), []

    def handle_endtag(self, tag):
        if self._in_nav and tag == 'a' and self._href is not None:
            self.links.append((''.join(self._text).strip(), self._href))
            self._href = None
        elif tag == 'nav':
            self._in_nav = False

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)


def breadcrumb_faults(page: str) -> list[str]:
    """What is wrong with one page's BreadcrumbList against its visible breadcrumb ([] = nothing)."""
    blocks = []
    for raw in LD.findall(page):
        if '</' in raw:
            return ['a JSON-LD block holds "</", which can close its <script> early']
        try:
            node = json.loads(raw)
        except ValueError:
            return ['a JSON-LD block does not parse']
        if node.get('@type') == 'BreadcrumbList':
            blocks.append(node)
    if len(blocks) != 1:
        return [f'{len(blocks)} BreadcrumbList blocks (want exactly 1)']
    items = blocks[0].get('itemListElement', [])
    seen = Crumbs()
    seen.feed(page)
    faults = []
    if [i.get('position') for i in items] != list(range(1, len(items) + 1)):
        faults.append('positions are not 1..n')
    if not items or items[-1].get('item') != seen.canonical:
        faults.append(f'the last item is not the page itself ({items[-1].get("item") if items else None} vs '
                      f'canonical {seen.canonical})')
    shown = [(html.unescape(words), SITE + href) for words, href in seen.links]
    want = iter(shown)
    for item in items[:-1]:
        pair = (item.get('name'), item.get('item'))
        if pair not in want:  # consumes the iterator: also holds the ORDER
            faults.append(f'{pair} is not a link the visible breadcrumb shows, in that order ({shown})')
            break
    return faults


def built_pages():
    pages = sorted(ROOT.glob('area/*/*/index.html')) + [ROOT / 'open-data' / 'index.html']
    pages += sorted((ROOT / 'planes-overhead').rglob('index.html')) if (ROOT / 'planes-overhead').is_dir() else []
    return pages


class BreadcrumbLdTests(unittest.TestCase):

    def test_every_built_page_agrees_with_its_visible_breadcrumb(self):
        pages = built_pages()
        self.assertGreaterEqual(len(pages), 103, 'the area pages and /open-data/ are tracked: they must be here')
        bad = {p.relative_to(ROOT).as_posix(): f for p in pages if (f := breadcrumb_faults(p.read_text('utf-8')))}
        self.assertEqual(bad, {})

    def test_the_helper_escapes_a_closing_tag_in_a_name(self):
        import build_area_pages as area  # pylint: disable=import-outside-toplevel
        out = area.breadcrumb_ld([('Sky Score', '/'), ('A </script> B', '/x/')])
        inner = LD.fullmatch(out).group(1)
        self.assertNotIn('</', inner)
        self.assertEqual(json.loads(inner)['itemListElement'][1]['name'], 'A </script> B')


def _page(ld_items, links=(('Sky Score', '/'), ('Areas', '/area/')), canonical=SITE + '/area/london/hounslow/'):
    nav = ' &rsaquo; '.join(f'<a href="{h}">{w}</a>' for w, h in links) + ' &rsaquo; London'
    ld = json.dumps({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i, 'name': n, 'item': u} for i, (n, u) in enumerate(ld_items, 1)]})
    return (f'<html><head><link rel="canonical" href="{canonical}"></head><body>'
            f'<nav class="crumbs" aria-label="Breadcrumb">{nav}</nav>'
            f'<script type="application/ld+json">{ld}</script></body></html>')


GOOD = [('Sky Score', SITE + '/'), ('Areas', SITE + '/area/'), ('Hounslow', SITE + '/area/london/hounslow/')]


class TheCheckCatchesItsDefectsTests(unittest.TestCase):
    """Proven red on each defect it exists for, so a green run means something."""

    def test_a_good_page_passes(self):
        self.assertEqual(breadcrumb_faults(_page(GOOD)), [])

    def test_a_step_the_visitor_does_not_see(self):
        bad = [GOOD[0], ('Best areas', SITE + '/best/'), GOOD[2]]
        self.assertTrue(breadcrumb_faults(_page(bad)))

    def test_steps_out_of_order(self):
        self.assertTrue(breadcrumb_faults(_page([GOOD[1], GOOD[0], GOOD[2]])))

    def test_a_last_item_that_is_not_the_page(self):
        self.assertTrue(breadcrumb_faults(_page([GOOD[0], GOOD[1], ('Hounslow', SITE + '/area/london/')])))

    def test_no_breadcrumb_or_two(self):
        page = _page(GOOD)
        self.assertTrue(breadcrumb_faults(LD.sub('', page)))
        self.assertTrue(breadcrumb_faults(page.replace('</body>', LD.search(page).group(0) + '</body>')))

    def test_a_raw_closing_tag_inside_the_json(self):
        self.assertTrue(breadcrumb_faults(_page([GOOD[0], GOOD[1], ('A </b> B', GOOD[2][1])])))


if __name__ == '__main__':
    unittest.main()
