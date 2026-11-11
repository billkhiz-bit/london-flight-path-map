"""The yardstick bar can be seen against its track (audit M-14, 2026-11-11).

A bar beside a named yardstick (the WHO guideline, a typical borough) is drawn from a true zero so the two lengths
compare; the comparison is the picture's point. The yardstick was #c8c7c4 on the map's #e4e3e0 track (1.32:1) and
#c4c1b8 on the area pages' (1.40:1 light, 2.22:1 dark): there, but barely. WCAG 1.4.11 asks 3:1 of a graphic a
reader needs; the figures are printed beside it, so this is a floor we hold, not a strict failure we fixed. Read from
the holders: index.html's rule for the map, build_area_pages' palettes for every built page.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import build_area_pages as area  # noqa: E402


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip('#')
    def channel(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(h[i:i + 2]) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def token(css: str, name: str) -> str:
    m = re.search(rf'--{name}:\s*(#[0-9a-fA-F]{{6}})', css)
    assert m, f'--{name} not found'
    return m.group(1)


class Yardstick(unittest.TestCase):
    def test_the_maps_yardstick_against_its_track(self):
        page = (ROOT / 'index.html').read_text(encoding='utf-8')
        rule = re.search(r'\.t-track i\.yard \{[^}]*background:\s*(#[0-9a-fA-F]{6})', page)
        self.assertIsNotNone(rule, 'the map\'s yardstick colour must be a hex value in its own rule')
        track = re.search(r'\.t-track \{[^}]*background:\s*var\(--bg\)', page)
        self.assertIsNotNone(track, 'the track is drawn in --bg')
        self.assertGreaterEqual(contrast(rule.group(1), token(page, 'bg')), 3.0)

    def test_the_built_pages_yardstick_against_its_track_light_and_dark(self):
        for name, palette in (('light', area.PALETTE_LIGHT), ('dark', area.PALETTE_DARK)):
            with self.subTest(name):
                self.assertGreaterEqual(contrast(token(palette, 'yard'), token(palette, 'track')), 3.0)


if __name__ == '__main__':
    unittest.main()
