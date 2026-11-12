"""The site's palette holds on every page that has moved to it (Bill, 2026-11-04: "ensure the colour scheme is
consistent"). An audit that day found only seven pages sharing it; the older pages carried a different orange and
a different background, and my own mock-ups had added colours the site never used.

A page joins HELD when it is rebuilt, and cannot drift afterwards. Every other page is declared with its reason, so a
new page must take a side, and a waiting page that reaches the palette has to move to HELD: the list can only shrink.
Colours that carry meaning (scoreColor, the planes bands, the air marks) have their own holders and tests.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

PALETTE = {
    '--bg': '#f4f3ef', '--paper': '#fbfaf8', '--dark': '#141414', '--mid': '#55554f', '--line': '#dedcd6',
    '--orange': '#f27d26', '--orange-ink': '#a85416', '--focus': '#d35a12',
}

HELD = (
    '404.html', 'about/index.html', 'api/index.html', 'home/index.html', 'home/reports/index.html',
    'home/reports/street/index.html', 'how-it-works/index.html', 'pricing.html',
    'area/', 'open-data/', 'bay-area/',
)

WAITING = {}

OWN_COLOURS = {
    'index.html': "the full map: its own surfaces, for a panel that sits on a map",
    'privacy.html': "legal text, on the map's greys; carries no script",
    'terms.html': "legal text, on the map's greys; carries no script",
    'changes.html': 'the dark API change log',
    'score-demo/': 'the dark API console',
    'talks/': 'handouts made for print',
    'home/moved/': 'redirects, no design of their own',
}

NOT_THE_SITE = ('tests/', 'design/', 'preview/', 'mobile/', 'prototype/', 'archive/', 'extension/')


def page_tokens(html):
    """The colour tokens of a page's own :root. A dark-mode block redefines these names on purpose, so it is skipped."""
    css = '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', html, re.S))
    plain = re.sub(r'@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}', '', css)
    tokens = {}
    for block in re.findall(r':root\s*\{([^}]*)\}', plain):
        for name, value in re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', block):
            tokens.setdefault(name, value.strip().lower())
    return tokens


def off_palette(tokens):
    """Each palette name a page gets wrong or lacks, with what it holds instead."""
    return {name: tokens.get(name, 'missing') for name, want in PALETTE.items() if tokens.get(name) != want}


def undeclared(pages):
    declared = (*HELD, *WAITING, *OWN_COLOURS)
    return {p for p in pages if not any(p == d or (d.endswith('/') and p.startswith(d)) for d in declared)}


def site_pages():
    out = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '*.html'], cwd=REPO, capture_output=True,  # noqa: S603, S607  (git, fixed args)
                         text=True, encoding='utf-8', check=True).stdout.split()
    return [p for p in out if not p.startswith(NOT_THE_SITE)]


def read(page):
    return (REPO / page).read_text(encoding='utf-8')


def held_pages():
    return [p for p in site_pages() if any(p == h or (h.endswith('/') and p.startswith(h)) for h in HELD)]


def test_every_held_page_keeps_the_palette():
    pages = held_pages()
    assert len(pages) > 100, 'the area pages have fallen out of this test'
    assert {p: off for p in pages if (off := off_palette(page_tokens(read(p))))} == {}


def test_every_held_entry_still_names_a_page():
    # A renamed or mistyped entry would otherwise leave the check with no failure.
    pages = site_pages()
    assert [h for h in HELD if not any(p == h or (h.endswith('/') and p.startswith(h)) for p in pages)] == []


def test_the_planes_pages_keep_the_palette():
    # 464 generated pages, gitignored, so they are held at their one source: the builders' palette, as the page gets it.
    sys.path.insert(0, str(REPO / 'scripts'))
    sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))
    spec = importlib.util.spec_from_file_location('build_planes_pages', REPO / 'scripts' / 'build_planes_pages.py')
    builder = importlib.util.module_from_spec(spec)
    sys.modules['build_planes_pages'] = builder
    spec.loader.exec_module(builder)
    assert off_palette(page_tokens(f'<style>{builder.STYLE.replace("{{", "{").replace("}}", "}")}</style>')) == {}


def test_every_page_has_taken_a_side():
    assert undeclared(site_pages()) == set()


@pytest.mark.parametrize('prefix', sorted(WAITING))
def test_a_page_that_reached_the_palette_leaves_the_waiting_list(prefix):
    pages = [p for p in site_pages() if p == prefix or p.startswith(prefix)]
    assert pages, f'{prefix} matches nothing: remove it'
    assert [p for p in pages if not off_palette(page_tokens(read(p)))] == []


def test_a_drifted_colour_is_caught():
    drifted = read('pricing.html').replace('#f4f3ef', '#f9f8f5')
    assert off_palette(page_tokens(drifted)) == {'--bg': '#f9f8f5'}


def test_a_lost_token_is_caught():
    lost = re.sub(r'--orange-ink:\s*#a85416;', '', read('pricing.html'))
    assert off_palette(page_tokens(lost)) == {'--orange-ink': 'missing'}


def test_a_dark_block_is_not_read_as_the_page():
    dark = '<style>:root { --bg: #f4f3ef; } @media (prefers-color-scheme: dark) { :root { --bg: #1b1b1a; } }</style>'
    assert page_tokens(dark) == {'--bg': '#f4f3ef'}


def test_a_new_page_must_take_a_side():
    assert undeclared(['pricing.html', 'area/london/hounslow/index.html', 'brand-new/index.html']) == {'brand-new/index.html'}
