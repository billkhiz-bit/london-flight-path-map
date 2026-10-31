"""Every page and PDF we publish keeps CLAUDE.md's wording rules (2026-10-24).

The rules ("The product, in facts safe to repeat") were enforced by reading. The /talks/ handout broke two of them
for a month, unseen: a price list outside /pricing, and "the data underneath is all published under the Open
Government Licence". No gate read the pages a visitor reads, so this one does.

WHICH FILES: the Makefile's own upload commands (`aws s3 cp <page>.html`, and every `aws s3 sync <dir>/`: its HTML,
and its PDFs where the command includes "*.pdf"), so a file is checked because it is published, never because
somebody remembered to list it; plus the modules under js/ that write text into those pages. js/vendor/ is
third-party code, not our words. A PDF is read for itself: an HTML page fixed but never re-rendered leaves the old
sentence live in its PDF.

WHAT IS READ: what a visitor sees. The text, the `alt`, `title`, `aria-label` and `placeholder` attributes, the
page's description and link-preview tags, and the strings inside its scripts (template literals and their nested
`${...}` too; each string with its tags stripped and its entities and escapes decoded, as the browser would show
it; URLs dropped). Never comments (the pages' comments quote the rules they keep) and never the
Content-Security-Policy (it names cubitt33.goatcounter.com).

A RULE THAT NEEDS AN EXCEPTION gets it here, by file and by phrase, with its reason; anything new then fails until
someone reads it.
"""
import html
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Attributes whose value a visitor reads, or a search engine / link preview shows.
SHOWN_ATTRS = ('alt', 'title', 'aria-label', 'placeholder')
SHOWN_META = re.compile(r'^(description|og:.+|twitter:.+)$')
JS_ESCAPE = re.compile(r'\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)', re.S)
JS_SIMPLE_ESCAPES = {'n': ' ', 't': ' ', 'r': ' ', 'b': '', 'f': '', 'v': ''}


def _makefile_commands():
    """The Makefile's commands, each with its backslash-continued lines joined."""
    text = (ROOT / 'Makefile').read_text(encoding='utf-8')
    return re.sub(r'\\\r?\n', ' ', text).splitlines()


def published_pages():
    """Every HTML page the Makefile uploads, as repo-relative paths."""
    pages = set()
    for cmd in _makefile_commands():
        pages.update(re.findall(r'aws s3 cp ([\w./-]+\.html)\b', cmd))
        for folder in re.findall(r'aws s3 sync ([\w./-]+/) ', cmd):
            if '--include' not in cmd or '"*.html"' in cmd:
                pages.update(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).rglob('*.html'))
    return sorted(pages)


def published_pdfs():
    pdfs = set()
    for cmd in _makefile_commands():
        for folder in re.findall(r'aws s3 sync ([\w./-]+/) ', cmd):
            if '"*.pdf"' in cmd or '--include' not in cmd:
                pdfs.update(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).rglob('*.pdf'))
    return sorted(pdfs)


def published_modules():
    return sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'js').rglob('*.mjs') if 'vendor' not in p.parts)


def _decode_js(raw):
    def one(m):
        e = m.group(1)
        if e.startswith('u{'):
            return chr(int(e[2:-1], 16))
        if e[0] == 'u' and len(e) == 5:
            return chr(int(e[1:], 16))
        if e[0] == 'x' and len(e) == 3:
            return chr(int(e[1:], 16))
        return JS_SIMPLE_ESCAPES.get(e, '' if e == '\n' else e)
    return JS_ESCAPE.sub(one, raw)


def as_shown_string(raw):
    """A script string as the page would show it: escapes decoded, tags (whole or cut by a concatenation) gone,
    entities decoded."""
    s = _decode_js(raw)
    s = re.sub(r'<[^<>]*>', ' ', s)
    s = re.sub(r'<[a-zA-Z/!][^<>]*$', ' ', s)       # '<a href="' + url + ...
    s = re.sub(r'^\s*["\']?\s*/?>', ' ', s)          # ... + '">Open data</a>'
    return html.unescape(s)


def script_strings(code):
    """The strings in a script, comments skipped, template literals read through their nested ${...}."""
    out = []
    n = len(code)

    def quoted(i):
        q, j, buf = code[i], i + 1, []
        while j < n and code[j] != q and code[j] != '\n':
            if code[j] == '\\':
                buf.append(code[j:j + 2])
                j += 2
                continue
            buf.append(code[j])
            j += 1
        out.append(''.join(buf))
        return j + 1

    def template(i):  # i: just after the opening backtick
        buf = []
        while i < n:
            c = code[i]
            if c == '\\':
                buf.append(code[i:i + 2])
                i += 2
            elif c == '`':
                out.append(''.join(buf))
                return i + 1
            elif code.startswith('${', i):
                out.append(''.join(buf))
                buf = []
                i = scan(i + 2, '}')
            else:
                buf.append(c)
                i += 1
        out.append(''.join(buf))
        return i

    def scan(i, closer):  # code until its closer at depth 0 (None: the end)
        depth = 0
        while i < n:
            c = code[i]
            if code.startswith('//', i):
                j = code.find('\n', i)
                i = n if j < 0 else j
            elif code.startswith('/*', i):
                j = code.find('*/', i + 2)
                i = n if j < 0 else j + 2
            elif c == '\\':      # only in a regex literal out here: skip what it escapes ("\/\/")
                i += 2
            elif c in '\'"':
                i = quoted(i)
            elif c == '`':
                i = template(i + 1)
            elif c in '{([':
                depth += 1
                i += 1
            elif c in '})]':
                if depth == 0 and c == closer:
                    return i + 1
                depth -= 1
                i += 1
            else:
                i += 1
        return i

    scan(0, None)
    return [as_shown_string(s) for s in out]


class ShownText(HTMLParser):
    """Collects what a visitor sees: text, shown attributes, description tags and script strings."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ld = []
        self._in = None  # 'style', 'script' or 'ld+json' while inside one

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for name in SHOWN_ATTRS:
            if a.get(name):
                self.parts.append(a[name])
        if tag == 'meta' and SHOWN_META.match(a.get('name') or a.get('property') or '') and a.get('content'):
            self.parts.append(a['content'])
        if tag == 'style':
            self._in = 'style'
        elif tag == 'script':
            self._in = 'ld+json' if a.get('type') == 'application/ld+json' else 'script'

    def handle_endtag(self, tag):
        if tag in ('style', 'script'):
            self._in = None

    def handle_data(self, data):
        if self._in == 'style':
            return
        if self._in == 'script':
            self.parts.extend(script_strings(data))
        elif self._in == 'ld+json':
            self.parts.append(data)
            self.ld.append(data)
        else:
            self.parts.append(data)


def priced_in_json_ld(blocks):
    """Every non-zero price a search engine would show from a page's JSON-LD: any `price`, `lowPrice`,
    `highPrice` at any depth (an Offer, an AggregateOffer, a priceSpecification, an @type given as a list)."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key in ('price', 'lowPrice', 'highPrice'):
                if key in node and str(node[key]).strip() not in ('0', '0.0', '0.00', ''):
                    found.append(f'{node.get("name", "?")}: {key} {node[key]}')
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    for block in blocks:
        try:
            walk(json.loads(block))
        except ValueError:
            found.append('a JSON-LD block that does not parse, so its prices cannot be read')
    return found


def shown_from_source(path, source):
    """(text, priced) a visitor or a search engine sees in a file's source, whitespace collapsed."""
    if path.endswith('.mjs'):
        parts, ld = script_strings(source), []
    else:
        parser = ShownText()
        parser.feed(source)
        parts, ld = parser.parts, parser.ld
    text = re.sub(r'https?://[^\s\'"`<>]+', ' ', ' '.join(parts))  # where a request goes, not words anyone reads
    return re.sub(r'\s+', ' ', text), priced_in_json_ld(ld)


def pdf_text(path):
    from pypdf import PdfReader  # in CI's pip line (.github/workflows/ci.yml)
    return ' '.join((page.extract_text() or '') for page in PdfReader(str(ROOT / path)).pages)


_SHOWN = {}


def shown(path):
    if path not in _SHOWN:
        if path.endswith('.pdf'):
            _SHOWN[path] = (re.sub(r'\s+', ' ', pdf_text(path)), [])
        else:
            _SHOWN[path] = shown_from_source(path, (ROOT / path).read_text(encoding='utf-8'))
    return _SHOWN[path]


def everything():
    return published_pages() + published_pdfs() + published_modules()


def allowed_for(path, allowed):
    return [phrase for where, phrase, _why in allowed if where in ('*', path)]


def matches(pattern, path, flags=0, allowed=()):
    """Each match of pattern on a file, not inside an allowed phrase there, as (start, end, text)."""
    text = shown(path)[0]
    spans = [m.span() for a in allowed_for(path, allowed) for m in re.finditer(a, text)]
    return [(m.start(), m.end(), text) for m in re.finditer(pattern, text, flags)
            if not any(s <= m.start() and m.end() <= e for s, e in spans)]


def hits(pattern, paths, flags=0, allowed=()):
    """{path: [snippet]} for each match of pattern not inside an allowed phrase on that path."""
    found = {}
    for path in paths:
        for s, e, text in matches(pattern, path, flags, allowed):
            found.setdefault(path, []).append(text[max(0, s - 50):e + 50])
    return found


# ---- the rules -------------------------------------------------------------------------------------------------

PRICING = 'pricing.html'
GBP = r'(?:£|\bGBP)\s?'
# Shaped like one of our prices: an amount per month, report, year or call.
PRICE_SHAPE = GBP + r'\d[\d,]*(?:\.\d\d)?\s*(?:a|per|/|an?)\s*(?:month|year|report|lookup|request|call|seat|user)\b'
LICENCE_TIERS = ('council-licence', 'api-enterprise')
# A figure near the word licence, either way round, on any page, /pricing included.
LICENCE_FIGURE = (r'licen[cs]es?\b[^.;:]{0,60}?' + GBP + r'\d' + '|' + GBP + r'\d[\d,]*[^.;:]{0,60}?\blicen[cs]es?\b')
LICENCE_ALLOWED = [
    (PRICING, r'area studies from £750, a 90-day pilot at £2,500 and annual licences',
     "the description's list: a study's and the pilot's prices beside the word, not a licence's"),
    (PRICING, r'Professional at £499 a month and enterprise licences', "the description's list: Professional's price"),
    (PRICING, r'If you go on to an annual licence, the £2,500 comes off its first year', 'the pilot fee, credited'),
    # Area pages credit HM Land Registry ("... £..., Open Government Licence v3.0"): a dataset's licence.
    ('*', r'Open Government Licen[cs]e(?: v\d\.\d)?', "a dataset's licence, not ours"),
    ('*', r'Open Database Licen[cs]e(?: \d\.\d)?', "a dataset's licence, not ours"),
]

# Cubitt33 is named on privacy and terms only (CLAUDE.md, Branding).
CUBITT_PAGES = {'privacy.html', 'terms.html'}

# Cubitt33 is not VAT-registered: VAT may be named only to say so.
VAT_ALLOWED = [
    ('*', r'not registered for VAT', 'says no VAT is charged'),
    ('*', r'not VAT[- ]registered', 'says no VAT is charged'),
]

# AI is said only as an event's name or where AI is NOT used (Bill, 2026-10-24: not "AI slop"). Each phrase below
# was read; a new mention fails until someone reads it and adds it here with its reason. "AI" and its
# abbreviations match by case (so a CSS class "ai" or the word "said" never count); the phrases in any case.
AI_WORDS = (r'\bAI\b|\bA\.I\.|\bLLMs?\b|GPT|OpenAI|GenAI|Claude|Bedrock|Amazon Nova|\bNova \d'
            r'|(?i:artificial intelligence|language models?\b|machine learning|chat ?bots?\b)')
AI_ALLOWED = [
    ('*', r'AI Tinkerers', "an event's name"),
    ('api/index.html', r'No AI summaries layered on top', 'where AI is not used'),
    ('about/index.html', r'none is invented by an AI', 'where AI is not used'),
    ('talks/how-sky-score-works.html', r'No artificial intelligence is involved anywhere on the website',
     'where AI is not used'),
    ('talks/how-sky-score-works.pdf', r'No artificial intelligence is involved anywhere on the website',
     'where AI is not used'),
]
# Bill ruled on 2026-10-25 on the two write-ups once pinned here: "The 57 checks" was archived (repo `archive/`,
# its two S3 copies deleted), and "How Sky Score works" says only that the assistant's question is processed
# in the United States, pointing at the privacy policy. Both now meet the rule like every other page.

# The whole product is never "open government data" or all OGL: UK routes are the UK AIP (NATS)'s.
OGL = r'(?:Open Government Licen[cs]e|\bOGL\b)'
WHOLE_PRODUCT_OGL = [
    r'open government data',
    r'\ball\b[^.<;,()]{0,80}?' + OGL,                       # never across a list ("all items, ...")
    r'\bevery (?:figure|number|dataset|source|score|input|answer)\b[^.<;,()]{0,80}?' + OGL,
    OGL + r'[^.<]{0,40}?\b(?:throughout|everything|all of it|every (?:figure|source|dataset))',
]
OGL_ALLOWED = [
    ('home/reports/sample-area-summary-norwich.pdf', r'All Open Government Licence v3\.0 except the WHO guidelines',
     'true: it closes a list of the DEFRA sources before it, and names the one exception'),
]

# Shares are of postcodes (or US residents), never of addresses or homes.
ADDRESS_SHARE = r'\d+(?:\.\d+)?\s?%\s+of\s+(?:the\s+|its\s+|their\s+)?(?:addresses|homes|properties|households|houses)\b'

# How often planes pass is said only for airports that pass coverage_verdict(). Since 2026-10-26 (branch
# planes-overhead) it is said in ONE place: js/planes.mjs writes the front page's "Planes overhead" block from
# data/planes/*.json, whose airports can only be the year rule's passers (scripts/build_planes_overhead.py refuses
# any other; tests/test_build_planes_overhead.py and tests/planes-model.mjs hold both ends). Its strings carry no
# figure, so these patterns still hold every page: a figure typed into a page or a module stays a defect.
# The SECOND writer (Bill, 2026-10-28): the district pages under planes-overhead/, BUILT with their figures in them
# so a search engine reads them, by scripts/build_planes_pages.py from the same files and nothing else. They pass
# these patterns because they never write "N planes a day" (a cell counts postcodes: "66 at 100+"), and they are
# held by the builder's --check, a blocking preflight stage: every page byte-equal to a fresh build, so a figure
# typed into one goes red there. Should their wording ever trip a pattern, the allowance names that folder and
# this reason, never a looser pattern.
FREQUENCY = [
    (r'\b\d+(?:\.\d+)?\s+(?:planes|flights|aircraft|movements|overflights|arrivals|departures)'
     r'\s+(?:a|per|an|each)\s+(?:day|hour|week|month|year)\b'),
    r'\b(?:planes?|flights?|aircraft|jets?)\b[^.<]{0,30}?\bevery\s+\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?)\b',
]

OLD_BRAND = r'Flight Path Map'


def fmt(found):
    return '\n'.join(f'  {path}: ...{s}...' for path, snippets in sorted(found.items()) for s in snippets)


class PublishedFilesTests(unittest.TestCase):
    def test_the_file_list_is_the_published_one(self):
        pages = published_pages()
        for must in (PRICING, 'home/index.html', 'about/index.html', 'talks/how-sky-score-works.html'):
            self.assertIn(must, pages, 'the Makefile no longer uploads it, or this test no longer reads the Makefile')
        self.assertGreaterEqual(sum(p.startswith('area/') for p in pages), 100, 'the area pages fell out of the list')
        self.assertIn('talks/how-sky-score-works.pdf', published_pdfs())
        self.assertIn('js/home-engine.mjs', published_modules())

    def test_comments_and_the_csp_are_not_read(self):
        text = shown_from_source('x.html', (
            '<meta http-equiv="Content-Security-Policy" content="img-src https://cubitt33.goatcounter.com">'
            '<!-- AI note --><p>Shown</p><script>// AI comment\nconst s = "a string"; /* AI */</script>'))[0]
        self.assertIn('Shown', text)
        self.assertIn('a string', text)
        self.assertNotIn('AI', text)
        self.assertNotIn('cubitt33', text)

    def test_script_strings_read_as_shown(self):
        got = script_strings('x = `<p>${ok ? `&pound;39 a report` : \'\'}</p>`; y = "\\u00a335"; '
                             'z = \'<a href="\' + u + \'">Open data</a>\'; r = /https?:\\/\\//; w = "after";')
        self.assertIn('£39 a report', ' '.join(got))
        self.assertIn('£35', got)
        self.assertIn('Open data', ' '.join(got))
        self.assertIn('after', got, 'a regex literal ate the rest of the line')


class PriceTests(unittest.TestCase):
    def amounts(self):
        """Our prices, read from /pricing (the holder), as numbers."""
        return {a.replace(',', '') for a in re.findall(GBP + r'(\d[\d,]*)', shown(PRICING)[0])}

    def test_pricing_has_prices(self):
        self.assertGreaterEqual(len(self.amounts()), 3, 'no prices read from /pricing: has its markup changed?')

    def test_our_prices_appear_only_on_pricing(self):
        ours = self.amounts()
        found = {}
        for path in everything():
            if path == PRICING:
                continue
            text = shown(path)[0]
            for m in re.finditer(GBP + r'(\d[\d,]*)', text):  # "£250,000" reads 250000, never 250
                if m.group(1).rstrip(',').replace(',', '') in ours:
                    found.setdefault(path, []).append(text[max(0, m.start() - 50):m.end() + 50])
        self.assertEqual(found, {}, 'one of our prices outside /pricing (link to /pricing instead):\n' + fmt(found))

    def test_nothing_shaped_like_a_price_outside_pricing(self):
        found = hits(PRICE_SHAPE, [p for p in everything() if p != PRICING], re.I)
        self.assertEqual(found, {}, 'a price per month, report or call outside /pricing:\n' + fmt(found))

    def test_search_engines_see_no_price_outside_pricing(self):
        priced = {path: shown(path)[1] for path in everything() if path != PRICING and shown(path)[1]}
        self.assertEqual(priced, {}, 'a priced JSON-LD offer outside /pricing')

    def test_no_licence_figure_even_on_pricing(self):
        html_src = (ROOT / PRICING).read_text(encoding='utf-8')
        for tier in LICENCE_TIERS:
            cells = re.findall(rf'<p class="price" data-price="{tier}">(.*?)</p>', html_src, re.S)
            self.assertTrue(cells, f'no {tier} price cell on /pricing: has its markup changed?')
            for cell in cells:
                self.assertNotRegex(cell, r'\d', f'a licence figure on /pricing ({tier}): licences are "On request"')
        found = hits(LICENCE_FIGURE, everything(), re.I, allowed=LICENCE_ALLOWED)
        self.assertEqual(found, {}, 'a figure beside the word licence (licences are "On request"):\n' + fmt(found))


class WordingTests(unittest.TestCase):
    def test_no_vat_is_added(self):
        found = hits(r'\bVAT\b', everything(), allowed=VAT_ALLOWED)
        self.assertEqual(found, {}, 'VAT named other than to say none is charged (Cubitt33 is not registered):\n'
                         + fmt(found))

    def test_cubitt33_only_on_privacy_and_terms(self):
        found = hits(r'Cubitt\s?33', [p for p in everything() if p not in CUBITT_PAGES], re.I)
        self.assertEqual(found, {}, 'Cubitt33 named outside privacy and terms:\n' + fmt(found))

    def test_the_old_name_is_gone(self):
        found = hits(OLD_BRAND, everything(), re.I)
        self.assertEqual(found, {}, 'the old name in public text (always "Sky Score"):\n' + fmt(found))

    def test_ai_only_as_an_event_or_where_it_is_not_used(self):
        found = hits(AI_WORDS, everything(), allowed=AI_ALLOWED)
        self.assertEqual(found, {}, 'AI named other than as an event or where it is not used; read it, then '
                         'reword it or add it to AI_ALLOWED with its reason:\n' + fmt(found))

    def test_the_whole_product_is_never_all_ogl(self):
        found = {}
        for pattern in WHOLE_PRODUCT_OGL:
            for path, snippets in hits(pattern, everything(), re.I, allowed=OGL_ALLOWED).items():
                found.setdefault(path, []).extend(snippets)
        self.assertEqual(found, {}, 'the product called open government data or all OGL (UK routes: UK AIP (NATS)):\n'
                         + fmt(found))

    def test_shares_are_of_postcodes_not_addresses(self):
        found = hits(ADDRESS_SHARE, everything(), re.I)
        self.assertEqual(found, {}, 'a share of addresses or homes (shares are over postcodes):\n' + fmt(found))

    def test_no_page_says_how_often_planes_pass(self):
        found = {}
        for pattern in FREQUENCY:
            for path, snippets in hits(pattern, everything(), re.I).items():
                found.setdefault(path, []).extend(snippets)
        self.assertEqual(found, {}, 'how often planes pass, which only coverage_verdict() airports may say:\n'
                         + fmt(found))


class RulesCatchTheirDefectsTests(unittest.TestCase):
    """Each rule, shown the defect it exists for, must fail: a pattern loosened later turns this red. Each defect
    is page SOURCE, read through shown_from_source() like a real page, so the reading is tested too."""

    DEFECTS = [
        (PriceTests, 'test_nothing_shaped_like_a_price_outside_pricing', 'home/index.html',
         '<p>Reports cost £39 a report.</p>'),
        (PriceTests, 'test_nothing_shaped_like_a_price_outside_pricing', 'js/home-engine.mjs',
         'const s = `<p>${ok ? `&pound;39 a report` : \'\'}</p>`;'),
        (PriceTests, 'test_our_prices_appear_only_on_pricing', 'js/home-engine.mjs', "const s = 'Only \\u00a335';"),
        (PriceTests, 'test_our_prices_appear_only_on_pricing', 'about/index.html', '<p>Plans from GBP 499.</p>'),
        (PriceTests, 'test_search_engines_see_no_price_outside_pricing', 'api/index.html',
         '<script type="application/ld+json">{"offers":{"@type":["AggregateOffer"],"lowPrice":"35"}}</script>'),
        (PriceTests, 'test_no_licence_figure_even_on_pricing', 'about/index.html',
         '<p>Council licences from £12,000.</p>'),
        (WordingTests, 'test_no_vat_is_added', 'api/index.html', '<p>Professional, a month + VAT</p>'),
        (WordingTests, 'test_cubitt33_only_on_privacy_and_terms', 'about/index.html', '<p>Made by Cubitt33 Ltd.</p>'),
        (WordingTests, 'test_the_old_name_is_gone', 'home/index.html', '<a title="London Flight Path Map">x</a>'),
        (WordingTests, 'test_ai_only_as_an_event_or_where_it_is_not_used', 'home/index.html',
         '<h1>AI-powered property insight</h1>'),
        (WordingTests, 'test_ai_only_as_an_event_or_where_it_is_not_used', 'about/index.html',
         '<img alt="Answers from ChatGPT">'),
        (WordingTests, 'test_ai_only_as_an_event_or_where_it_is_not_used', 'talks/how-sky-score-works.html',
         '<p>The assistant runs on Amazon Nova 2 Lite, through Bedrock.</p>'),
        (WordingTests, 'test_the_whole_product_is_never_all_ogl', 'api/index.html',
         '<script>t = \'The data underneath is all published under the <a href="/l">Open Government Licence</a>.\''
         '</script>'),
        (WordingTests, 'test_the_whole_product_is_never_all_ogl', 'api/index.html',
         '<p>Every figure is published under the Open Government Licence.</p>'),
        (WordingTests, 'test_the_whole_product_is_never_all_ogl', 'api/index.html',
         '<p>Built entirely on open government data.</p>'),
        (WordingTests, 'test_shares_are_of_postcodes_not_addresses', 'index.html',
         '<script>const t = "<b>41%</b> of homes are above 55 dB";</script>'),
        (WordingTests, 'test_no_page_says_how_often_planes_pass', 'home/index.html',
         '<p>About 120 planes a day pass over.</p>'),
        (WordingTests, 'test_no_page_says_how_often_planes_pass', 'home/index.html',
         '<p>A plane every 90 seconds at rush hour.</p>'),
    ]

    def test_each_rule_fails_on_its_defect(self):
        for cls, name, path, source in self.DEFECTS:
            with self.subTest(rule=name, page=path, source=source):
                real = shown(path)  # read (and cached) first, so only this one entry is swapped
                _SHOWN[path] = shown_from_source(path, source)
                try:
                    with self.assertRaises(AssertionError, msg=f'{name} passed a page showing: {source}'):
                        getattr(cls(name), name)()
                finally:
                    _SHOWN[path] = real


if __name__ == '__main__':
    unittest.main()
