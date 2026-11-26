"""The front page names every module it imports in a <link rel="modulepreload">, and nothing else (2026-11-24).

Bill: the example "still takes a short while to load". Measured on a throttled phone (4G, CPU 4x), the browser found the
page's scripts in three rounds, each module's imports only once that module had arrived, and asked for no data until
0.93 s in. With every module named in the head, the example's tiles filled 0.3 s sooner (1.44 s to 1.14 s, local). The
list must follow the code: a module added without its hint brings a round back in silence, and a hint for a module the
page no longer imports is a download for nothing. So it is read from the import graph here, never trusted.

Data files are deliberately NOT preloaded: tried the same night, eleven of them took the bandwidth d3 needed and the
tiles came 0.4 s LATER (1.83 s). Re-measure before adding one.

The fonts the page draws ARE preloaded, first: with twelve modules asked for at once, the fonts could miss the first
paint and their swap moved the page on a phone (layout shift 0.0245, over tests/front-page.mjs's 0.02; 0.0003 with them).
A font preload needs `crossorigin`, or the browser fetches the font a second time for the stylesheet.

SKY_HOME and SKY_JS point the test at copies, so it can be proven red without touching the tracked files.
"""
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get('SKY_HOME') or REPO / 'home' / 'index.html')
JS = Path(os.environ.get('SKY_JS') or REPO / 'js')
IMPORT = re.compile(r"""^\s*(?:import|export)\s[^'"]*?from\s*['"]([./][^'"]+)['"]|^\s*import\s*['"]([./][^'"]+)['"]""", re.M)


def page():
    return HOME.read_text(encoding='utf-8')


def js_file(href):
    """A page path ("/js/x.mjs") as a file in JS."""
    assert href.startswith('/js/'), href
    return JS / href[len('/js/'):]


def graph():
    """Every module reached by static imports from the page's own module scripts, as page paths."""
    seen = set()
    todo = re.findall(r'<script type="module" src="(/js/[^"]+)"', page())
    assert todo, 'the front page has module scripts'
    while todo:
        href = todo.pop()
        if href in seen:
            continue
        seen.add(href)
        for m in IMPORT.finditer(js_file(href).read_text(encoding='utf-8')):
            spec = m.group(1) or m.group(2)
            todo.append(spec if spec.startswith('/') else '/js/' + os.path.normpath(os.path.join(os.path.dirname(href[len('/js/'):]), spec)).replace('\\', '/'))
    return seen


def hints():
    return re.findall(r'<link rel="modulepreload" href="([^"]+)"', page())


def test_every_module_the_page_imports_is_named_once_and_nothing_else():
    named = hints()
    assert len(named) == len(set(named)), 'a module named twice'
    assert set(named) == graph(), (sorted(graph() - set(named)), sorted(set(named) - graph()))


def test_every_hint_is_a_file_that_exists():
    for href in hints():
        assert js_file(href).is_file(), href


def test_the_hints_sit_in_the_head_before_the_styles():
    # In the head, the preload scanner finds them while the HTML is still arriving; at the foot they would buy nothing.
    text = page()
    head = text[: text.index('</head>')]
    assert all(f'href="{h}"' in head for h in hints())


def test_the_fonts_come_first_each_one_fonts_css_declares_and_fetched_once():
    text = page()
    fonts = re.findall(r'<link rel="preload" href="([^"]+)" as="font"([^>]*)>', text)
    assert fonts, 'the fonts the page draws are preloaded'
    declared = set(re.findall(r"url\('(/fonts/[^']+\.woff2)'\)", (REPO / 'fonts' / 'fonts.css').read_text(encoding='utf-8')))
    for href, rest in fonts:
        assert href in declared, f'{href} is not a font fonts.css declares'
        assert 'type="font/woff2"' in rest and 'crossorigin' in rest, f'{href}: needs its type and crossorigin'
    first_module = text.index('rel="modulepreload"')
    assert all(text.index(f'href="{href}"') < first_module for href, _ in fonts), 'the fonts are asked for before the modules'


def test_no_data_file_is_preloaded_and_nothing_reaches_another_host():
    # Measured worse (see above). And a hint opens a connection as surely as a request: postcodes.io and our API are asked
    # only when the page asks (privacy s2b; js/place-box.mjs EXAMPLE).
    text = page()
    assert not re.search(r'<link rel="preload"[^>]*as="fetch"', text), 'a data file is preloaded: re-measure first'
    for tag in re.findall(r'<link rel="(?:preload|modulepreload|preconnect|dns-prefetch|prefetch)"[^>]*>', text):
        assert 'postcodes.io' not in tag and 'execute-api' not in tag and 'href="http' not in tag, tag
