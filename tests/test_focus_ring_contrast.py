"""No focus ring on any served page is the brand orange, and every --focus reaches 3:1 (audits 2026-10-05 and 2026-10-09, I-7).

The ring was the brand orange #f27d26: 2.44:1 on the pages' --bg, 2.17:1 on the map's water,
under WCAG 2.2's 3:1 for a focus indicator (1.4.11, non-text contrast). Since 2026-10-07 the
front page, its reports pages and the full map draw it in a --focus token, #d35a12, the colour
the site bar already uses for "you are here".

THE PAGES ARE FOUND, NOT LISTED (2026-10-11). This file named four, and /pricing and /api/,
which carry the same `:focus-visible` rule, stayed at 2.44:1 for two more days: /pricing was
redesigned the day before the first fix and nobody added it (audit 2026-10-09 I-7). Every
served page with a focus rule is now walked, the way tests/test_favicons.py walks them.

Two things are checked, statically:
  - no focus rule on any served page draws its ring in the brand orange, as a literal or
    through any token that holds it. The COLOUR is banned, not the name: 404.html and
    /open-data/ call a darker #c2410c "--orange", and that one passes.
  - every page that defines --focus has it reach 3:1 against each background colour the page
    defines (--bg, --paper, --water where present) and against white

    python -m pytest tests/test_focus_ring_contrast.py
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BRAND_ORANGE = '#f27d26'
BACKGROUNDS = ('--bg', '--paper', '--water')
# Not deployed, or copies another build makes: the same set tests/test_favicons.py skips.
SKIP = {'node_modules', 'archive', 'mobile', '.claude', 'design', 'tests', '.git', 'playwright-report', 'test-results'}
STYLE = re.compile(r'<style\b[^>]*>(.*?)</style>', re.S | re.I)
# One innermost block at a time, selector then body: linear, where a pattern that hunts for
# ':focus' from every position rescans each run of CSS and took 52 s over the full map.
BLOCK = re.compile(r'([^{}]*)\{([^{}]*)\}')
# outline, stroke AND box-shadow: the full map's ranking rows draw their ring as an inset
# box-shadow, and a check that read outline and stroke alone left them orange (I-7, 9 Oct).
RING = re.compile(r'(?:outline|stroke|box-shadow)\s*:([^;]*)')


def luminance(hex_colour):
    h = hex_colour.lstrip('#')
    channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def tokens(text):
    """The LAST definition of each colour token, which is the light theme's on these pages."""
    return dict(re.findall(r'(--[a-z-]+):\s*(#[0-9a-fA-F]{6})\b', text))


def every_definition(text):
    """Every value each colour token is ever given (light, dark, media blocks), lower-cased."""
    out = {}
    for name, value in re.findall(r'(--[a-z-]+):\s*(#[0-9a-fA-F]{6})\b', text):
        out.setdefault(name, set()).add(value.lower())
    return out


def focus_rules(text):
    """The body of every CSS rule whose selector names a focus state, from the page's <style> blocks."""
    return [body for css in STYLE.findall(text) for sel, body in BLOCK.findall(css) if ':focus' in sel]


def focus_pages():
    pages = []
    for path in sorted(REPO.rglob('*.html')):
        if not SKIP.isdisjoint(path.relative_to(REPO).parts):
            continue
        if focus_rules(path.read_text(encoding='utf-8')):
            pages.append(path.relative_to(REPO).as_posix())
    return pages


FOCUS_PAGES = focus_pages()
FOCUS_TOKEN_PAGES = [rel for rel in FOCUS_PAGES if '--focus' in tokens((REPO / rel).read_text(encoding='utf-8'))]


def test_the_scan_reaches_the_pages_that_count():
    # A walk that found nothing would pass every check below vacuously, and a list that
    # dropped one of these is the defect this file was rewritten for.
    for rel in (
        'index.html',
        'home/index.html',
        'home/reports/index.html',
        'home/reports/street/index.html',
        'pricing.html',
        'api/index.html',
        '404.html',
        'open-data/index.html',
    ):
        assert rel in FOCUS_PAGES, f'{rel} has no focus rule any more, or the scan cannot see it'
    for rel in ('index.html', 'home/index.html', 'pricing.html', 'api/index.html'):
        assert rel in FOCUS_TOKEN_PAGES, f'{rel} no longer defines --focus'


def test_the_brand_orange_really_is_under_3_to_1():
    # The ban below rests on this. If the brand colour ever changes, re-measure, do not delete.
    assert contrast(BRAND_ORANGE, '#f4f3ef') < 3.0


@pytest.mark.parametrize('rel', FOCUS_PAGES)
def test_no_focus_ring_is_drawn_in_the_brand_orange(rel):
    text = (REPO / rel).read_text(encoding='utf-8')
    holding = {name for name, values in every_definition(text).items() if BRAND_ORANGE in values}
    bad = []
    for body in focus_rules(text):
        for ring in RING.findall(body):
            used = set(re.findall(r'var\((--[a-z-]+)', ring))
            if BRAND_ORANGE in ring.lower() or used & holding:
                bad.append(ring.strip())
    assert not bad, f'{rel}: focus rings drawn in the brand orange {BRAND_ORANGE} (2.44:1): {bad}'


@pytest.mark.parametrize('rel', FOCUS_TOKEN_PAGES)
def test_the_focus_colour_reaches_3_to_1_on_every_background(rel):
    t = tokens((REPO / rel).read_text(encoding='utf-8'))
    grounds = {name: t[name] for name in BACKGROUNDS if name in t} | {'white': '#ffffff'}
    low = {name: round(contrast(t['--focus'], colour), 2) for name, colour in grounds.items()}
    assert all(v >= 3.0 for v in low.values()), f'{rel}: --focus {t["--focus"]} against {low}'
