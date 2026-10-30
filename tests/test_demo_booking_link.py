"""The Book a demo link: one holder, the declared pages only, and no deploy while it is a placeholder (2026-10-29).

Bill's plan (Desktop calendly-and-demo-plan-2026-10-29.md, placement ruled 29 Oct): a "Book a demo" button in the top
bar of /pricing and /api/ only, a line on each page, and one beside the live demo's response on /score-demo/. The
site-wide bar waits on the ~20 Nov read of the bar's clicks. The link is his Calendly booking page, which did not exist
when the buttons were built, so it began as a placeholder (the real link went live 2026-10-30).

WHAT THIS HOLDS, from the files the Makefile uploads (test_public_wording.published_pages, so a page is checked
because it is published, never because somebody listed it):
- js/count.mjs DEMO_BOOKING_URL is the ONE holder: a Calendly https link, or the placeholder;
- every Calendly link on every published page reads exactly that, so a changed link cannot leave one page stale, and
  no js module writes one;
- the pages that carry it, and how many times, are exactly DECLARED, so a new placement is a decision, not a drift;
- `booking-link-check` refuses the placeholder on the holder and every declared page, and web-deploy, demo-deploy and
  web-deploy-all run it before they upload anything;
- the privacy policy names the booking service, and its "Last updated" date is the newest dated notice on /changes,
  as its s10 promises for a new subprocessor.
Where the buttons sit, how they look and what they count is tests/front-page.mjs 16g, which reads the DOM.
"""
import re
import unittest

from .test_public_wording import ROOT, published_modules, published_pages

PLACEHOLDER = 'https://calendly.com/SET-ME/sky-score-demo'
# Every page that carries the link, and how many times. A new placement goes here WITH its reason.
DECLARED = {
    'pricing.html': 2,  # the top bar, and the line under the opening (the one a phone sees: its bar is a Menu)
    'api/index.html': 2,  # the top bar, and "Get started" step 5
    'score-demo/index.html': 1,  # beside the live demo's response, where a visitor who just ran the API reads next
    # Bill, 2026-10-30: the front page's three business spots, never its bar (the bar's own filled button is Full map,
    # and the ~6% read runs to ~20 Nov): the "Data for your business" card, the For developers panel, and the line
    # under "Who it is for" (outside WHO-FOR, which is also written into /about/). Counted as card, dev and who.
    'home/index.html': 3,
}
CALENDLY_HREF = re.compile(r'''href=["'](https?://(?:[\w-]+\.)*calendly\.com\b[^"']*)["']''', re.I)
HOLDER = re.compile(r"^export const DEMO_BOOKING_URL = '([^']+)';", re.M)


def holder():
    m = HOLDER.search((ROOT / 'js' / 'count.mjs').read_text(encoding='utf-8'))
    return m.group(1) if m else None


def makefile():
    return (ROOT / 'Makefile').read_text(encoding='utf-8').replace('\r\n', '\n')


class DemoBookingLinkTests(unittest.TestCase):
    def test_count_mjs_holds_one_calendly_link_or_the_placeholder(self):
        url = holder()
        self.assertIsNotNone(url, 'js/count.mjs has no `export const DEMO_BOOKING_URL = \'...\';`')
        self.assertTrue(
            url == PLACEHOLDER or re.fullmatch(r'https://calendly\.com/[a-z0-9-]+/[a-z0-9-]+', url),
            f'DEMO_BOOKING_URL is neither the placeholder nor a calendly.com/<slug>/<event> link: {url}',
        )

    def test_every_published_link_reads_the_holder_on_the_declared_pages_only(self):
        url = holder()
        found, stray = {}, []
        for page in published_pages():
            hrefs = CALENDLY_HREF.findall((ROOT / page).read_text(encoding='utf-8'))
            if hrefs:
                found[page] = len(hrefs)
            stray += [f'{page}: {h}' for h in hrefs if h != url]
        self.assertEqual(stray, [], f'a booking link that is not DEMO_BOOKING_URL ({url})')
        self.assertEqual(found, DECLARED, 'the pages carrying the booking link are not the declared ones')
        modules = [m for m in published_modules() if m != 'js/count.mjs'
                   and 'calendly.com' in (ROOT / m).read_text(encoding='utf-8')]
        self.assertEqual(modules, [], 'a js module writes a Calendly link: it would escape the page checks above')

    def test_the_deploys_refuse_the_placeholder(self):
        text = makefile()
        m = re.search(r'^booking-link-check:\n((?:\t.*\n)+)', text, re.M)
        self.assertIsNotNone(m, 'the Makefile has no booking-link-check target')
        recipe = m.group(1)
        self.assertIn(PLACEHOLDER.split('/sky-score-demo')[0].replace('https://', ''), recipe)
        grep = re.search(r'grep -l "[^"]+" ([^;|]+?)\s*(?:\|\||;)', recipe)
        self.assertIsNotNone(grep, 'booking-link-check no longer greps the files it guards')
        self.assertEqual(sorted(grep.group(1).split()), sorted(['js/count.mjs', *DECLARED]),
                         'booking-link-check must read the holder and every declared page')
        self.assertIn('exit 1', recipe)
        # grep exits 2 when it cannot read a file: that must refuse too, never pass as "no placeholder" (2026-10-30).
        self.assertIn('-ne 1', recipe, 'booking-link-check must refuse when grep cannot read a file (exit 2)')
        for target in ('web-deploy', 'demo-deploy', 'home-deploy'):
            line = re.search(rf'^{target}:(.*)$', text, re.M)
            self.assertIsNotNone(line, f'no {target} target')
            self.assertIn('booking-link-check', line.group(1).split(), f'{target} no longer runs booking-link-check first')
        every = re.search(r'^web-deploy-all:(.*)$', text, re.M).group(1).split()
        self.assertEqual(every[0], 'booking-link-check', 'web-deploy-all must refuse before fonts and data upload')

    def test_the_privacy_policy_names_the_booking_service_and_dates_it_on_changes(self):
        privacy = (ROOT / 'privacy.html').read_text(encoding='utf-8')
        self.assertIn('Booking a demo', privacy)
        self.assertRegex(privacy, r'<td>Calendly\b', 'the subprocessor table has no Calendly row')
        updated = re.search(r'Last updated: (\d{4}-\d{2}-\d{2})', privacy).group(1)
        changes = (ROOT / 'changes.html').read_text(encoding='utf-8')
        notices = changes[changes.index('id="policy-notices"'):]
        notices = notices[:notices.index('</section>')]
        dates = re.findall(r'<time datetime="(\d{4}-\d{2}-\d{2})"', notices)
        self.assertTrue(dates, 'no dated policy notices on /changes')
        self.assertEqual(updated, max(dates),
                         "privacy.html's Last updated is not the newest Policy notice on /changes (privacy s10)")

    def test_both_bars_style_the_button_with_the_same_rules(self):
        # /pricing and /api/ carry their bar's CSS inline, as every page does, so the button's two rules (the fill,
        # and the 760 px squeeze measured for seven links) exist twice. Held equal here so a change to one cannot
        # leave the other behind (2026-10-30 review; front-page.mjs 16g measures the result at 681 and 760 px).
        def rules(page):
            text = (ROOT / page).read_text(encoding='utf-8').replace('\r\n', '\n')
            start = text.find('/* Book a demo (Bill, 2026-10-29)')
            end_marker = 'nav.top-nav a { padding-left: 7px; padding-right: 7px; } }'
            end = text.find(end_marker, max(start, 0))
            self.assertNotEqual(start, -1, f'{page}: the Book a demo rules are gone from its bar CSS')
            self.assertNotEqual(end, -1, f'{page}: the 760 px rule is gone from its bar CSS')
            return text[start:end + len(end_marker)]
        bar_pages = [p for p in DECLARED if p not in ('score-demo/index.html', 'home/index.html')]  # page lines only
        self.assertEqual(sorted(bar_pages), ['api/index.html', 'pricing.html'])
        self.assertEqual(rules('pricing.html'), rules('api/index.html'),
                         'the Book a demo CSS differs between /pricing and /api/: change both or neither')


if __name__ == '__main__':
    unittest.main()
