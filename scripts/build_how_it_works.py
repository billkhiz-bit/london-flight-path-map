"""The /how-it-works/ page's figures: a worked example, the persona weights and two fact lines, derived.

WHY (2026-10-22). Bill asked for a plain-English page saying how a score is worked out. Every number on it
that can move is DERIVED here, never typed into the page: a page explaining the arithmetic that quotes stale
arithmetic would be the one place a reader can catch the product contradicting itself.

FROM WHERE. The score Lambda (`app.calc_score`, `app.PERSONAS`, `app.CITIES`, `app.SNAPSHOT_VINTAGE_LABEL`), the
persona names the site shows (`label:` in index.html's PERSONAS, held to the Lambda's weights by
tests/test_persona_parity.py) and the Bay Area's outlines (data/us-bayarea-cities.json, as the coverage strip
counts them). Four blocks sit between HOW-IT-WORKS markers in how-it-works/index.html; never edit them there.

THE WORKED EXAMPLE is Hounslow, the council area beside Heathrow, under the balanced weights, scored for the
council area as a whole. Its affordability moves with each monthly price roll, so scripts/deploy_hpi_roll.sh
runs --write with the area pages; --check (blocking in preflight) reds when a roll skips it. The points shown
are each rounded score times its weight, and must add up to the published score within the residual the API
publishes (under 0.08), or this refuses to write a sum that does not add up.

    python scripts/build_how_it_works.py --write   # rewrite the four blocks from the engine
    python scripts/build_how_it_works.py --check   # offline, blocking: the page == the engine
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

PAGE = REPO / 'how-it-works' / 'index.html'
SITE = REPO / 'index.html'
BAY_AREA = REPO / 'data' / 'us-bayarea-cities.json'
EXAMPLE = ('london', 'Hounslow', 'balanced')
RESIDUAL = 0.08  # the published reproduction residual (METHODOLOGY, "weights")
BLOCKS = ('EXAMPLE', 'WEIGHTS', 'PRICES', 'COVERAGE')
QUIET_TAG = {  # context.quietResolution -> (tag class, words)
    'borough': ('band', 'area band'),
    'postcode': ('est', 'our estimate'),
    'raster': ('off', 'official data'),
}
COMPONENTS = (  # (key, name on the page), in the order every surface lists them
    ('quiet', 'Quiet Skies'),
    ('afford', 'Affordability'),
    ('growth', 'Price growth'),
    ('live', 'Liveability'),
    ('env', 'Environment'),
)


def markers(block: str) -> tuple[str, str]:
    return (f'<!-- HOW-IT-WORKS-{block}:BEGIN (scripts/build_how_it_works.py --write; never edit by hand) -->',
            f'<!-- HOW-IT-WORKS-{block}:END -->')


def persona_labels() -> dict[str, str]:
    """{persona key: the name the site shows}, read from index.html's PERSONAS so the two never differ."""
    page = SITE.read_text(encoding='utf-8')
    start = page.index('const PERSONAS = {')
    found = dict(re.findall(r"^\s{8}(\w+): \{\s*\n\s*label: '([^']+)'", page[start:start + 15000], re.M))
    missing = set(app.PERSONAS) - set(found)
    if missing:
        raise SystemExit(f'index.html PERSONAS has no label for {sorted(missing)}')
    return {key: found[key] for key in app.PERSONAS}


def pct(weight: float) -> str:
    return f'{round(weight * 100)}%'


def example() -> str:
    city, borough, persona = EXAMPLE
    scored = app.calc_score(borough, city, app.PERSONAS[persona])
    parts, weights = scored['components'], scored['weights']
    rows, points, segments = [], {}, []
    for key, name in COMPONENTS:
        if key not in parts:
            raise SystemExit(f'{borough} has no {key} score; choose an example scored on all five')
        points[key] = round(parts[key] * weights.get(key, 0.0), 2)
        # Quiet Skies says which tier answered (context.quietResolution): a council area as a whole reads the
        # band we set for it, never "our estimate" (that is the route geometry at a postcode) nor DEFRA's figure.
        kind, label = (QUIET_TAG[scored['context']['quietResolution']] if key == 'quiet' else ('off', 'official data'))
        tag = f'<span class="tag {kind}">{label}</span>'
        rows.append(f'<tr><th scope="row"><span class="key key-{key}" aria-hidden="true"></span>{name} {tag}</th>'
                    f'<td>{parts[key]:.1f}</td>'
                    f'<td>{pct(weights.get(key, 0.0))}</td><td>{points[key]:.2f}</td></tr>')
        if points[key] > 0:
            segments.append(f'<span class="seg seg-{key}" style="width:{points[key] * 10:.1f}%"></span>')
    total = sum(points.values())
    if abs(total - scored['score']) > RESIDUAL:
        raise SystemExit(f'the points add up to {total:.2f}, the score is {scored["score"]}: a sum that does not add up')
    quiet_w = weights.get('quiet', 0.0)
    cost = ''
    if parts['quiet'] == 0.0 and quiet_w > 0:
        cost = (f'<p class="cost">Quiet Skies is {pct(quiet_w)} of the score in this view. At 0.0 next to an airport, '
                f'{quiet_w * 10:.1f} of the 10 possible points are out of reach before anything else is counted.</p>')
    return (f'<table class="sum">\n'
            f'  <caption>{html.escape(borough)}, {html.escape(persona_labels()[persona].lower())} view, '
            f'for the council area as a whole</caption>\n'
            f'  <thead><tr><th scope="col">Score</th><th scope="col">Out of 10</th><th scope="col">Weight</th>'
            f'<th scope="col">Points</th></tr></thead>\n'
            f'  <tbody>\n    ' + '\n    '.join(rows) + '\n  </tbody>\n'
            f'  <tfoot><tr><th scope="row">Overall score</th><td></td><td>100%</td>'
            f'<td class="total">{scored["score"]:.1f}</td></tr></tfoot>\n'
            f'</table>\n'
            f'<div class="bar" aria-hidden="true">{"".join(segments)}</div>\n'
            f'<p class="scale" aria-hidden="true"><span>0</span><span>10</span></p>\n'
            f'{cost}\n')


def weights_table() -> str:
    labels = persona_labels()
    head = ''.join(f'<th scope="col">{name}</th>' for _, name in COMPONENTS)
    body = '\n    '.join(
        f'<tr><th scope="row">{html.escape(labels[p])}</th>'
        + ''.join(f'<td>{pct(w[key])}</td>' for key, _ in COMPONENTS) + '</tr>'
        for p, w in app.PERSONAS.items())
    return (f'<table class="weights">\n'
            f'  <caption>Weight of each score, by view</caption>\n'
            f'  <thead><tr><th scope="col">View</th>{head}</tr></thead>\n'
            f'  <tbody>\n    {body}\n  </tbody>\n'
            f'</table>\n')


def prices() -> str:
    return (f'<li><b>House prices</b> are HM Land Registry\'s monthly price index, now for '
            f'{html.escape(app.SNAPSHOT_VINTAGE_LABEL)}. We update them each month.</li>\n')


def coverage() -> str:
    uk = [cfg for cfg in app.CITIES.values() if cfg.get('country') == 'United Kingdom']
    areas, regions = sum(len(cfg['boroughs']) for cfg in uk), len(uk)
    nyc = len(app.CITIES['nyc']['boroughs'])
    bay = len(json.loads(BAY_AREA.read_text(encoding='utf-8'))['features'])
    return (f'<p>Sky Score covers {areas} council areas in {regions} UK city regions, plus New York\'s {nyc} boroughs '
            f'and {bay} Bay Area cities (facts only, with no score on the site yet).</p>\n')


RENDER = {'EXAMPLE': example, 'WEIGHTS': weights_table, 'PRICES': prices, 'COVERAGE': coverage}


def held(page: str, block: str) -> tuple[str, str] | None:
    """(indent, the block's body) as the page holds it, or None if its markers are not there once each."""
    begin, end = markers(block)
    if page.count(begin) != 1 or page.count(end) != 1:
        return None
    line_start = page.rfind('\n', 0, page.index(begin)) + 1
    indent = page[line_start:page.index(begin)]
    return indent, page[page.index(begin) + len(begin) + 1:page.rfind('\n', 0, page.index(end)) + 1]


def rendered(block: str, indent: str) -> str:
    return ''.join(f'{indent}{line}\n' if line else '\n' for line in RENDER[block]().splitlines())


def check(page: str) -> list[str]:
    problems = []
    for block in BLOCKS:
        found = held(page, block)
        if found is None:
            problems.append(f'the HOW-IT-WORKS-{block} markers must appear exactly once each')
        elif found[1].replace('\r\n', '\n') != rendered(block, found[0]):
            problems.append(f'HOW-IT-WORKS-{block} differs from the engine: run --write')
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true', help='rewrite the four blocks from the engine')
    mode.add_argument('--check', action='store_true', help='offline: the page == the engine')
    args = ap.parse_args(argv)
    page = PAGE.read_text(encoding='utf-8')
    if args.write:
        for block in BLOCKS:
            found = held(page, block)
            if found is None:
                print(f'FAIL: place the HOW-IT-WORKS-{block} markers in {PAGE.relative_to(REPO)} once, then --write')
                return 1
            begin = markers(block)[0]
            at = page.index(begin) + len(begin) + 1
            page = page[:at] + rendered(block, found[0]) + page[at + len(found[1]):]
        PAGE.write_text(page, encoding='utf-8', newline='')
    problems = check(PAGE.read_text(encoding='utf-8'))
    city, borough, persona = EXAMPLE
    print(f'how-it-works: {borough} ({persona}) {app.calc_score(borough, city, app.PERSONAS[persona])["score"]}, '
          f'{len(app.PERSONAS)} views, prices {app.SNAPSHOT_VINTAGE_LABEL}')
    if problems:
        print('FAIL:\n  ' + '\n  '.join(problems))
        return 1
    print('ok: the page matches the engine')
    return 0


if __name__ == '__main__':
    sys.exit(main())
