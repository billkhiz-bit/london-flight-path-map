"""Every built page's title, description and share tags fit a search result and agree with each other (2026-11-11).

The SEO audit of 2026-11-10 found 395 of 498 planes pages with titles past the ~60 characters a search result shows,
nearly every area and planes description past ~160, and no share tags at all on the planes pages (a link pasted into a
chat or a post showed a bare address). `build_area_pages.page_title()` and `fit()` are the one rule for both builders:
a title keeps " | Sky Score" only where it fits, a description is the longest of its versions that fits, never cut
mid-word. Held here on the pages as built, as a visitor (or a crawler) gets them; the planes pages are gitignored, so
where they are absent (CI) only the area pages are read.
"""
import html
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import build_area_pages as area  # noqa: E402

TITLE = re.compile(r'<title>(.*?)</title>', re.S)
META = re.compile(r'<meta (name|property)="([^"]+)" content="([^"]*)"')
CANONICAL = re.compile(r'<link rel="canonical" href="([^"]+)"')


def problems(text: str) -> list[str]:
    """What is wrong with one page's head, in words; empty when nothing is."""
    found = []
    title = html.unescape(TITLE.search(text).group(1)) if TITLE.search(text) else ''
    meta = {k: html.unescape(v) for _, k, v in META.findall(text)}
    canonical = CANONICAL.search(text)
    desc = meta.get('description', '')
    if not title or len(title) > area.TITLE_MAX:
        found.append(f'title {len(title)} characters: {title!r}')
    if not desc or len(desc) > area.DESC_MAX:
        found.append(f'description {len(desc)} characters')
    if meta.get('og:title') != title:
        found.append('og:title is not the title')
    if meta.get('og:description') != desc:
        found.append('og:description is not the description')
    if not canonical or meta.get('og:url') != canonical.group(1):
        found.append('og:url is not the canonical address')
    if meta.get('og:site_name') != 'Sky Score' or meta.get('twitter:card') != 'summary':
        found.append('no og:site_name or twitter:card')
    return found


DESCRIPTION = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"')
NOINDEX = re.compile(r'<meta\s+name="robots"\s+content="[^"]*noindex')


def hand_written_pages() -> list[tuple[str, str]]:
    """(path, text) for every page the Makefile uploads that no page builder writes and a search engine may index.
    The list is the wording gate's (the Makefile's own upload commands), never one typed here."""
    sys.path.insert(0, str(ROOT / 'tests'))
    from test_public_wording import published_pages

    out = []
    for rel in published_pages():
        if rel.startswith(('area/', 'planes-overhead/')):
            continue
        text = (ROOT / rel).read_text(encoding='utf-8')
        if not NOINDEX.search(text):
            out.append((rel, text))
    return out


def built_pages() -> list[Path]:
    pages = sorted((ROOT / 'area').rglob('index.html'))
    planes = ROOT / 'planes-overhead'
    if planes.is_dir():
        pages += sorted(planes.rglob('index.html'))
    return pages


class PageMeta(unittest.TestCase):
    def test_every_built_page_fits_a_search_result_and_shares_cleanly(self):
        pages = built_pages()
        self.assertGreater(len(pages), 100, 'the area pages are missing: run build_area_pages.py --write')
        bad = {}
        for p in pages:
            found = problems(p.read_text(encoding='utf-8'))
            if found:
                bad[str(p.relative_to(ROOT))] = found
        self.assertEqual(bad, {}, f'{len(bad)} pages: {dict(list(bad.items())[:3])}')

    def test_every_hand_written_page_fits_a_search_result(self):
        # Audit M-22 (2026-11-13): the limits were held on the BUILT pages only, so /bay-area/ shipped a 99-character
        # title and the front page a 257-character description. Every other page the Makefile uploads and a search
        # engine may index (no robots noindex) is held to the same two numbers; its share tags stay its own.
        pages = hand_written_pages()
        self.assertGreater(len(pages), 10, f'only {len(pages)} hand-written pages found: the Makefile parse changed')
        bad = {}
        for rel, text in pages:
            m = TITLE.search(text)
            title = html.unescape(m.group(1)).strip() if m else ''
            d = DESCRIPTION.search(text)
            desc = html.unescape(d.group(1)) if d else ''
            found = []
            if not title or len(title) > area.TITLE_MAX:
                found.append(f'title {len(title)} characters: {title!r}')
            if len(desc) > area.DESC_MAX:
                found.append(f'description {len(desc)} characters')
            if found:
                bad[rel] = found
        self.assertEqual(bad, {}, f'{len(bad)} pages: {bad}')

    def test_a_title_keeps_the_brand_only_where_it_fits(self):
        self.assertEqual(area.page_title('Camden noise & liveability score'), 'Camden noise & liveability score | Sky Score')
        long = 'Planes overhead in B93: flight paths over Solihull'  # 50, and 62 with the brand
        self.assertEqual(area.page_title(long, 'Planes overhead in B93, Solihull'), long)
        too_long = 'x' * 61
        self.assertEqual(area.page_title(too_long, 'Short'), 'Short | Sky Score')

    def test_a_description_is_the_longest_version_that_fits_never_a_cut(self):
        self.assertEqual(area.fit('a' * 161, 'b' * 160, 'c'), 'b' * 160)
        self.assertEqual(area.fit('short', 'shorter'), 'short')


if __name__ == '__main__':
    unittest.main()
