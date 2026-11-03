"""The company's LinkedIn page: one holder, the declared pages only, and Google told it is us (2026-11-03).

Bill made a "Sky Score" company page on LinkedIn on 2026-11-02 and asked for it on the website. Placement, his pick
of three on 2026-11-03: the front page's footer and its Organization data (sameAs, which tells search engines the
page and the site are one organisation), both of the full map's footers (desktop and phone link the same places) and
/about/'s "Get in touch". NOT the generated area and planes pages: a footer change there re-dates every one of them
in the sitemap for nothing a reader would call a change.

The page is named for the product, so its address moves at the rename. js/count.mjs LINKEDIN_URL is the ONE holder;
change it there and this test names every copy left behind.

WHAT THIS HOLDS, from the files the Makefile uploads (test_public_wording.published_pages):
- LINKEDIN_URL is a linkedin.com/company/<slug>/ https link;
- every link to a LinkedIn COMPANY page on every published page reads exactly that, on the declared pages only and
  as many times as declared (a personal profile, linkedin.com/in/, is not a company page and is not counted);
- the front page's Organization sameAs carries it;
- count.mjs counts it (`<page>-linkedin`), so whether anyone follows it is read, not guessed; no other js module
  writes the link.
How a click on it counts is tests/front-page.mjs 16f, which clicks every link on /about/.
"""
import json
import re
import unittest

from .test_public_wording import ROOT, published_modules, published_pages

# Every page that carries the link, and how many times. A new placement goes here WITH its reason.
DECLARED = {
    'home/index.html': 1,  # the footer (the Organization's sameAs is held separately below)
    'index.html': 2,  # the full map's desktop footer and its phone sheet's footer: the two link the same places
    'about/index.html': 1,  # "Get in touch", beside Bill's own profile
}
COMPANY_HREF = re.compile(r'''href=["'](https?://(?:[\w-]+\.)*linkedin\.com/company/[^"']*)["']''', re.I)
HOLDER = re.compile(r"^export const LINKEDIN_URL = '([^']+)';", re.M)
JSON_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def holder():
    m = HOLDER.search((ROOT / 'js' / 'count.mjs').read_text(encoding='utf-8'))
    return m.group(1) if m else None


class LinkedInCompanyLinkTests(unittest.TestCase):
    def test_count_mjs_holds_one_company_page_link(self):
        url = holder()
        self.assertIsNotNone(url, "js/count.mjs has no `export const LINKEDIN_URL = '...';`")
        self.assertRegex(url, r'^https://www\.linkedin\.com/company/[a-z0-9-]+/$',
                         'LINKEDIN_URL is not a https://www.linkedin.com/company/<slug>/ link')

    def test_every_published_link_reads_the_holder_on_the_declared_pages_only(self):
        url = holder()
        found, stray = {}, []
        for page in published_pages():
            hrefs = COMPANY_HREF.findall((ROOT / page).read_text(encoding='utf-8'))
            if hrefs:
                found[page] = len(hrefs)
            stray += [f'{page}: {h}' for h in hrefs if h != url]
        self.assertEqual(stray, [], f'a LinkedIn company link that is not LINKEDIN_URL ({url})')
        self.assertEqual(found, DECLARED, 'the pages carrying the LinkedIn company link are not the declared ones')
        modules = [m for m in published_modules() if m != 'js/count.mjs'
                   and 'linkedin.com/company' in (ROOT / m).read_text(encoding='utf-8')]
        self.assertEqual(modules, [], 'a js module writes the LinkedIn link: it would escape the page checks above')

    def test_the_front_page_organization_names_it_in_same_as(self):
        text = (ROOT / 'home' / 'index.html').read_text(encoding='utf-8')
        orgs = []
        for block in JSON_LD.findall(text):
            data = json.loads(block)
            for node in data.get('@graph', [data]):
                if node.get('@type') == 'Organization':
                    orgs.append(node)
        self.assertEqual(len(orgs), 1, 'the front page should declare exactly one Organization')
        self.assertIn(holder(), orgs[0].get('sameAs', []), "the Organization's sameAs does not carry LINKEDIN_URL")

    def test_count_mjs_counts_it(self):
        text = (ROOT / 'js' / 'count.mjs').read_text(encoding='utf-8')
        watched = re.search(r'const WATCHED_LINKS = \{(.*?)\};', text, re.S)
        self.assertIsNotNone(watched, 'js/count.mjs has no WATCHED_LINKS')
        self.assertRegex(watched.group(1), r"\[LINKEDIN_URL\]:\s*'linkedin'",
                         'WATCHED_LINKS does not count LINKEDIN_URL as `linkedin`')


if __name__ == '__main__':
    unittest.main()
