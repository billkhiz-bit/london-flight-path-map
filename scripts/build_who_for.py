"""Who Sky Score is for: one list of audiences, written into the front page and the About page.

WHY (2026-10-22). Bill asked for "who it's for" and "why I built it" to sit together on an About page, while
the front page keeps its own "Who it is for" (two-thirds of all visits land there). Two hand-kept copies of a
list drift apart, so the list lives HERE once and is written between WHO-FOR markers in both pages; never edit
it there. Each page styles the block its own way (the front page as a card and a list, the About page with a
dark "choosing a home" panel); the words and links are identical by construction.

WHAT IT SAYS. The people who work with homes and places, each with its next step (pricing, the API, the council
areas, the open data). The wording came from the front page's paragraph of 2026-10-02; the next steps from the About
mock-ups Bill chose on 2026-10-22 (variant C, "people first").

ONE BAND SINCE 2026-11-23 (Bill's pick A of the front-page review, claude.ai/artifact/R7xc6qxz6NGonqjUxsd943): the list
sits under "Beyond one street", whose rows already say what a person choosing a home can do (Find areas, a street
report), so the "Buying or renting" card that repeated them and the hero's search, and its own "Who it is for" band, are
gone. The list keeps the id `who`, so /about/'s link to /#who still lands on it (tests/test_home_links.py).

    python scripts/build_who_for.py --write   # rewrite the block in both pages
    python scripts/build_who_for.py --check   # offline, blocking: both pages == this list
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The front page only since 2026-11-03 (declutter): About now says it in one line and links here. To put the list back
# on About, add its path and the WHO-FOR markers to about/index.html.
PAGES = (REPO / 'home' / 'index.html',)
BEGIN = '<!-- WHO-FOR:BEGIN (scripts/build_who_for.py --write; never edit by hand) -->'
END = '<!-- WHO-FOR:END -->'

PRO_LABEL = 'Working with homes and places'
PRO = (
    ('Buying agents and relocation firms', 'A sourced answer before the client asks.', 'See pricing', '/pricing'),
    ('Conveyancers and surveyors', 'Add aircraft noise to the reports you already produce.', 'Use the API', '/api/'),
    ('Islamic home finance', 'Environmental checks with an affordability measure that uses prices only.',
     'Use the API', '/api/'),
    ("Residents' groups", 'Base your case on the official figures.', 'Browse council areas', '/area/'),
    ('Researchers and journalists', 'One open, documented file.', 'Get the open data', '/open-data/'),
)


def rendered(indent: str) -> str:
    """The block, one line per element, every line at `indent` (the BEGIN marker's own indentation)."""
    e = html.escape
    # The label is a HEADING (audit M-12, 2026-11-23): as a <p> after "Data for your business", the five audiences sat
    # under that card in the outline, and About's "Who it is for" link landed on a list nothing named.
    lines = ['<div class="who-pro" id="who">', f'  <h3 class="who-label">{e(PRO_LABEL)}</h3>', '  <ul class="who-list">']
    for who, gives, cta, href in PRO:
        lines.append(f'    <li><b>{e(who)}</b><span>{e(gives)}</span><a href="{href}">{e(cta)} &rarr;</a></li>')
    lines += ['  </ul>', '</div>']
    return ''.join(f'{indent}{line}\n' for line in lines)


def held(page: str) -> tuple[str, str] | None:
    """(the marker's indentation, the text between the markers), or None unless each marker appears once."""
    if page.count(BEGIN) != 1 or page.count(END) != 1:
        return None
    start = page.index(BEGIN)
    indent = page[page.rfind('\n', 0, start) + 1:start]
    body_at = page.index('\n', start) + 1
    end_line = page.rfind('\n', 0, page.index(END)) + 1
    return indent, page[body_at:end_line]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true', help='rewrite the block in both pages')
    mode.add_argument('--check', action='store_true', help='offline: both pages == this list')
    args = ap.parse_args(argv)
    problems = []
    for path in PAGES:
        rel = path.relative_to(REPO).as_posix()
        page = path.read_text(encoding='utf-8')
        found = held(page)
        if found is None:
            problems.append(f'{rel}: the WHO-FOR markers must appear exactly once each')
            continue
        indent, body = found
        want = rendered(indent)
        if args.write and body.replace('\r\n', '\n') != want:
            at = page.index('\n', page.index(BEGIN)) + 1
            page = page[:at] + want + page[at + len(body):]
            path.write_text(page, encoding='utf-8', newline='')
            print(f'wrote {rel}')
        elif not args.write and body.replace('\r\n', '\n') != want:
            problems.append(f'{rel}: the WHO-FOR block differs from scripts/build_who_for.py: run --write')
    if problems:
        print('FAIL:\n  ' + '\n  '.join(problems))
        return 1
    print(f'ok: the front page carries the {len(PRO)} audiences')
    return 0


if __name__ == '__main__':
    sys.exit(main())
