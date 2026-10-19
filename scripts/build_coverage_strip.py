"""The front page's coverage strip: every region the search covers, with its council areas, derived.

WHY (2026-10-19). The front page's search answers for 13 UK city regions, New York and the Bay Area
(facts only), but nothing on it said which before you typed: the map's city buttons (`#chips`) list the
12 cities the front-page map draws, so Cardiff, Nottingham and Greater Norwich were searchable and never
named, and a visitor from Exeter learnt "not covered" only after searching. Bill agreed the strip after
looking at another data site's coverage list; its look was not copied.

DERIVED, NEVER TYPED. The UK regions, their names and their council-area counts come from the score
Lambda's registry (`app.CITIES`: `name`, `country`, `boroughs`), as `build_area_pages.py` derives the
coverage sentence; New York's borough count from the same registry; the Bay Area's 50 cities from
`data/us-bayarea-cities.json`, the outlines the map draws. The markup lives between the COVERAGE-STRIP
markers in `home/index.html`; never edit it there.

A PLAIN LIST, NOT CHIPS: nothing to click through to yet, and a chip that looks clickable but does
nothing is a false affordance. If the area index gains a heading id per region, each name can link.

    python scripts/build_coverage_strip.py --write   # rewrite the strip from the registry
    python scripts/build_coverage_strip.py --check   # offline, blocking: the strip == the registry, and
                                                     # its UK numbers add up to the page's own "97 ... in 13"
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))
import app  # noqa: E402  pylint: disable=wrong-import-position

HOME = REPO / 'home' / 'index.html'
BAY_AREA = REPO / 'data' / 'us-bayarea-cities.json'
BEGIN = '<!-- COVERAGE-STRIP:BEGIN (scripts/build_coverage_strip.py --write; never edit by hand) -->'
END = '<!-- COVERAGE-STRIP:END -->'
INDENT = ' ' * 10
# The page's own coverage figure, the "Four ways" card: the strip must add up to it.
FIGURE = re.compile(r'<div class="fig">(\d+)<small>council areas in (\d+) UK city regions')


def uk_regions() -> list[tuple[str, int]]:
    """(name, council areas) for every UK region the API covers, alphabetically."""
    return sorted((cfg['name'], len(cfg['boroughs'])) for cfg in app.CITIES.values()
                  if cfg.get('country') == 'United Kingdom')


def render() -> str:
    """The strip's markup, indented to sit inside the search card."""
    nyc = len(app.CITIES['nyc']['boroughs'])
    bay = len(json.loads(BAY_AREA.read_text(encoding='utf-8'))['features'])
    items = ''.join(f'<li>{html.escape(name)} <b>{n}</b></li>' for name, n in uk_regions())
    # ONE LINE, OPENED ON DEMAND. Written out in the card, the list made it four lines taller and the card
    # then covered the whole faded London map behind it, the backdrop Bill chose on 2026-10-07
    # (tests/front-page.mjs probed 0 points clear of the card). A native <details> keeps the card one line
    # taller, and the list is one click away before anyone types.
    return (f'{INDENT}{BEGIN}\n'
            f'{INDENT}<details class="covers"><summary>Which places does it cover?</summary><ul>{items}</ul> '
            f"council areas, plus New York's {nyc} boroughs and {bay} Bay Area cities (facts only).</details>\n"
            f'{INDENT}{END}\n')


def current(page: str) -> str | None:
    """The strip as the page holds it, whole lines from BEGIN to END, or None if the markers are not there once."""
    if page.count(BEGIN) != 1 or page.count(END) != 1:
        return None
    start = page.rfind('\n', 0, page.index(BEGIN)) + 1
    stop = page.index('\n', page.index(END)) + 1
    return page[start:stop]


def check(page: str) -> list[str]:
    """Every rule the strip keeps. Returns the problems; empty means it passes."""
    problems = []
    held = current(page)
    if held is None:
        return [f'{HOME.relative_to(REPO)}: the COVERAGE-STRIP markers must appear exactly once each']
    if held.replace('\r\n', '\n') != render():
        problems.append('the strip differs from the registry: run --write')
    figure = FIGURE.search(page)
    if not figure:
        problems.append('the page\'s coverage figure ("<n> council areas in <m> UK city regions") is not there')
    else:
        regions = uk_regions()
        total, count = sum(n for _, n in regions), len(regions)
        if (int(figure.group(1)), int(figure.group(2))) != (total, count):
            problems.append(f'the page says {figure.group(1)} council areas in {figure.group(2)} UK city regions; '
                            f'the registry gives {total} in {count}')
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true', help='rewrite the strip from the registry')
    mode.add_argument('--check', action='store_true', help='offline: the strip and the page keep their rules')
    args = ap.parse_args(argv)
    page = HOME.read_text(encoding='utf-8')
    if args.write:
        held = current(page)
        if held is None:
            print(f'FAIL: place the two COVERAGE-STRIP markers in {HOME.relative_to(REPO)} once, then --write')
            return 1
        HOME.write_text(page.replace(held, render()), encoding='utf-8', newline='')
        page = HOME.read_text(encoding='utf-8')
    problems = check(page)
    regions = uk_regions()
    print(f'coverage strip: {len(regions)} UK regions, {sum(n for _, n in regions)} council areas, plus New York '
          f'and the Bay Area')
    if problems:
        print('FAIL:\n  ' + '\n  '.join(problems))
        return 1
    print('ok: the strip matches the registry and the page\'s own figure')
    return 0


if __name__ == '__main__':
    sys.exit(main())
