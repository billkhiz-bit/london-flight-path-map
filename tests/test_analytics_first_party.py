"""Every page counts through our own js/count.mjs, and none loads GoatCounter's script (2026-10-11).

GoatCounter's count.v5.js sends `q: location.search` with every page view and event, a literal
inside its get_data() that no setting reaches, so every page whose address held a postcode sent
the postcode (audit 2026-10-09 I-1), against privacy s2c's "aggregate counts only". The pages
now load js/count.mjs, which sends GoatCounter's documented /count endpoint the path, the
page's own title, the referrer without its query, and screen size, and keeps the
window.goatcounter.count() every event caller uses. tests/front-page.mjs (section 8a) checks
what it sends from a page whose address holds a postcode; this file holds the pages:

  - no served page loads anything from gc.zgo.at, or lists it in its policy
  - every page that counts carries exactly one <script type="module" src="/js/count.mjs">
  - its policy lets that run and send: 'self' in script-src, the counting host in connect-src
    (sendBeacon) and img-src (the fallback)
  - the Bay Area generator writes the same tag, since a hand fix to its page would be undone
  - the module itself never reads location.search

This replaces tests/test_goatcounter_pinned.py, which held eleven pages to GoatCounter's
pinned script and its SRI hash.

    python -m pytest tests/test_analytics_first_party.py
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TAG = '<script type="module" src="/js/count.mjs"></script>'
HOST = 'https://cubitt33.goatcounter.com'
# Not deployed, or copies another build makes: the set tests/test_favicons.py skips.
SKIP = {
    'node_modules',
    'archive',
    'mobile',
    '.claude',
    'design',
    'tests',
    '.git',
    'playwright-report',
    'test-results',
}


def pages():
    for path in REPO.rglob('*.html'):
        if SKIP.isdisjoint(path.relative_to(REPO).parts):
            yield path


def counting_pages():
    return {
        p.relative_to(REPO).as_posix(): p.read_text(encoding='utf-8')
        for p in pages()
        if '/js/count.mjs' in p.read_text(encoding='utf-8')
    }


def directive(text, name):
    m = re.search(r'Content-Security-Policy"\s+content="([^"]*)"', text)
    assert m, 'no Content-Security-Policy'
    d = re.search(rf'(?<![\w-]){name}\s+([^;]*)', m.group(1))
    return d.group(1).split() if d else []


def test_the_scan_reaches_the_pages_that_count():
    found = counting_pages()
    # A walk that finds nothing would pass every check below vacuously.
    assert len(found) >= 11, sorted(found)
    for page in (
        'index.html',
        'home/index.html',
        'home/reports/street/index.html',
        'pricing.html',
        'bay-area/index.html',
    ):
        assert page in found, f'{page} no longer counts, or the scan cannot see it'


def test_no_page_loads_or_allows_goatcounters_script():
    offenders = [p.relative_to(REPO).as_posix() for p in pages() if 'gc.zgo.at' in p.read_text(encoding='utf-8')]
    assert not offenders, f'pages still naming gc.zgo.at (the script that sent the query string): {offenders}'


def test_every_counting_page_carries_exactly_one_tag():
    wrong = {page: text.count(TAG) for page, text in counting_pages().items() if text.count(TAG) != 1}
    assert not wrong, f'pages without exactly one {TAG}: {wrong}'


def test_every_counting_page_policy_lets_it_run_and_send():
    wrong = {}
    for page, text in counting_pages().items():
        missing = []
        if "'self'" not in directive(text, 'script-src'):
            missing.append("script-src 'self'")
        if HOST not in directive(text, 'connect-src'):
            missing.append(f'connect-src {HOST}')
        if HOST not in directive(text, 'img-src'):
            missing.append(f'img-src {HOST}')
        if missing:
            wrong[page] = missing
    assert not wrong, f'policies that block the counter or its beacon: {wrong}'


def test_the_bay_area_generator_writes_the_tag():
    # bay-area/index.html is generated: a hand fix to the page would be undone by --write.
    assert TAG in (REPO / 'scripts' / 'build_bay_area_page.py').read_text(encoding='utf-8')


def test_the_module_never_reads_the_query_string():
    source = (REPO / 'js' / 'count.mjs').read_text(encoding='utf-8')
    code = '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith(('*', '//', '/*')))
    assert 'location.search' not in code
    # The referrer is read once, and only through the helper that drops its query and fragment.
    assert code.count('document.referrer') == 1 and 'withoutQuery(document.referrer)' in code
