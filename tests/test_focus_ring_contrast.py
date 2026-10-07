"""Focus rings on the front page, its reports pages and the full map reach 3:1 (audit 2026-10-05, I-7).

The ring was the brand orange #f27d26: 2.44:1 on the front page's background, 2.17:1 on the
map's water, under WCAG 2.2's 3:1 for a focus indicator (1.4.11, non-text contrast). Since
2026-10-07 every focus rule on these pages uses a --focus token, #d35a12, the colour the site
bar already uses for "you are here".

Two things are checked, statically, per file:
  - no focus rule draws its ring in var(--orange) again: the next new control copying an
    older rule is how this would come back
  - --focus reaches 3:1 against every background colour the file defines (--bg, --paper,
    --water where present) and against white

    python -m pytest tests/test_focus_ring_contrast.py
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FILES = ['home/index.html', 'home/reports/index.html', 'home/reports/street/index.html', 'index.html']
BACKGROUNDS = ('--bg', '--paper', '--water')


def luminance(hex_colour):
    h = hex_colour.lstrip('#')
    channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def tokens(text):
    return dict(re.findall(r'(--[a-z-]+):\s*(#[0-9a-fA-F]{6})\b', text))


@pytest.mark.parametrize('rel', FILES)
def test_no_focus_ring_is_drawn_in_the_brand_orange(rel):
    text = (REPO / rel).read_text(encoding='utf-8')
    rules = re.findall(r'[^{}]*:focus(?:-visible)?[^{}]*\{([^}]*)\}', text)
    assert rules, f'{rel}: no focus rules found, so this check would pass on nothing'
    bad = [r.strip() for r in rules if re.search(r'(outline|stroke)\s*:[^;]*var\(--orange\)', r)]
    assert not bad, f'{rel}: focus rules still drawing in var(--orange): {bad}'


@pytest.mark.parametrize('rel', FILES)
def test_the_focus_colour_reaches_3_to_1_on_every_background(rel):
    t = tokens((REPO / rel).read_text(encoding='utf-8'))
    assert '--focus' in t, f'{rel}: no --focus token'
    grounds = {name: t[name] for name in BACKGROUNDS if name in t} | {'white': '#ffffff'}
    low = {name: round(contrast(t['--focus'], colour), 2) for name, colour in grounds.items()}
    assert all(v >= 3.0 for v in low.values()), f'{rel}: --focus {t["--focus"]} against {low}'
