#!/usr/bin/env python3
"""Planes overhead per postcode district, as pages a search engine can read: /planes-overhead/<district>/.

WHY THIS EXISTS (2026-10-28)
----------------------------
Step 1 of the marketing plan (26 Oct): people search "TW9 flight path", and what nobody else publishes is how many
planes pass overhead, measured, postcode by postcode. The front page tells one postcode at a time, from a script,
and robots.txt keeps crawlers out of /data/, so a search engine sees none of it. Bill's rulings (28 Oct):

- the figures are BUILT INTO each page, as the area pages bake their scores (a crawler reads the page as served);
- a page only for a district where some postcode is shown PAGE_FROM or more a day on some kind of day;
- at /planes-overhead/<district>/, lower case.

WHERE A FIGURE MAY COME FROM
- Every figure is read from data/planes/ (scripts/build_planes_overhead.py): the files the front page's answer
  reads, so a page can say only what the answer says. Their airports are the ones that passed coverage_verdict()
  in every month; a figure is rounded as shown, '<1' is never 0, and a cone's edge is a [least, most] pair. Nothing
  here works a figure out again from the averages.
- The averages file (data/adsb/postcode-averages.npz) is read for each postcode's council and position only: which
  councils a page names, and which districts are near it.
- NSPL (data/nspl.csv, the edition the averages were built from) gives each district's live postcodes, so a page
  says how much of its district was measured.

WHICH DISTRICTS GET NO PAGE, AND WHY (measured 28 Oct, on 988 districts)
- No postcode reaches PAGE_FROM a day (Bill): the page would be "under 1 a day" hundreds of times over.
- Mostly outside the covered councils: CM13 has 1 of its 702 live postcodes in Havering, so a page named CM13
  would speak for 701 postcodes nobody measured. COVERED_FROM of the live postcodes must be measured.
- Mostly large users (NSPL usrtypind 1: PO boxes, firms with a postcode of their own): SE1P, N1P, W1A. Their
  positions are a sorting office, not a street. LARGE_UNDER of the live postcodes at most.
- Fewer than MIN_POSTCODES measured: too little to be a page. Thin pages in bulk are what search engines call
  doorway pages, and they cost the whole domain (build_area_pages.MIN_FACTS, same reason).

THE WORDING GATE
tests/test_public_wording.py forbids a page to say how often planes pass except through the planes files. These
pages may, because this builder is their only writer and --check (preflight) holds every page byte-equal to what
the files build, so a figure typed into one goes red. The allowance names this folder, never a looser pattern.

OUTPUT, GITIGNORED LIKE data/planes/ (the repo is public, and these pages carry every district's figures: pushing
them would publish them before Bill's review and before the site, which his 26 Oct ruling keeps first)
  planes-overhead/<district>/index.html, planes-overhead/index.html   the pages
  sitemap-planes.xml                  listed in robots.txt beside sitemap.xml (one writer per file)
  data/planes-pages-manifest.json     TRACKED: each page's bytes, md5 (S3's ETag) and the day its content last
                                      changed, which dates the sitemap (git cannot date an ignored file)

AFTER A PLANES ROLL, RERUN THIS (the pages bake the figures, as area pages bake scores)

    python scripts/build_planes_overhead.py --write
    python scripts/build_planes_pages.py --write
    python scripts/make.py planes-deploy
    python scripts/make.py planes-pages-deploy

USAGE
    python scripts/build_planes_pages.py --write
    python scripts/build_planes_pages.py --check     # the pages on disk == what --write would write
    python scripts/build_planes_pages.py --list      # every district, and why it has a page or not
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

import build_area_pages as area  # noqa: E402  pylint: disable=wrong-import-position

PLANES = REPO / 'data' / 'planes'
AVERAGES = REPO / 'data' / 'adsb' / 'postcode-averages.npz'
NSPL = REPO / 'data' / 'nspl.csv'
OUT = REPO / 'planes-overhead'
SITEMAP = REPO / 'sitemap-planes.xml'
FLIGHT_GEOMETRY = REPO / 'js' / 'flight_geometry.mjs'
PLANES_JS = REPO / 'js' / 'planes.mjs'
URL_ROOT = '/planes-overhead/'

PAGE_FROM = 10  # Bill, 2026-10-28: some postcode shown this many a day or more, on some kind of day
COVERED_FROM = 0.5  # share of the district's live postcodes the covered councils hold
LARGE_UNDER = 0.5  # share of its live postcodes that may be large users
MIN_POSTCODES = 20  # measured postcodes, at least
NEARBY = 8  # districts with a page, nearest first, linked from each page
# A postcode the files do not list under an airport was shown under 1 a day from it on every kind of day (0 or
# '<1': build_planes_overhead.reaches_one). The files cannot tell the two apart, so neither can a page.
UNLISTED = '<1'


# ----------------------------------------------------------------- what the site already says, read not retyped

def airport_names(src: Path = FLIGHT_GEOMETRY) -> dict[str, str]:
    """{code: name} from the site's own table, js/flight_geometry.mjs AIRPORT_NAME."""
    block = re.search(r'^export const AIRPORT_NAME = \{\n(.*?)^\};', src.read_text(encoding='utf-8'), re.M | re.S)
    if not block:
        raise SystemExit(f'{src.name}: AIRPORT_NAME not found')
    return dict(re.findall(r"^\s+([A-Z]{3}): '([^']+)',$", block.group(1), re.M))


def kinds(src: Path = PLANES_JS) -> list[tuple[str, str]]:
    """[(kind, label)] in the order the front page's answer shows them, from js/planes.mjs KINDS."""
    line = re.search(r'^const KINDS = (\[.*\]);$', src.read_text(encoding='utf-8'), re.M)
    if not line:
        raise SystemExit(f'{src.name}: KINDS not found')
    found = re.findall(r"\['(\w+)', '([^']+)', (?:'\w+'|null)\]", line.group(1))
    if len(found) != 3:
        raise SystemExit(f'{src.name}: KINDS has changed shape: {line.group(1)}')
    return found


def one(v) -> str:
    return 'under 1' if v == '<1' else str(v)


def per_day(v) -> str:
    """One figure as the front page's answer writes it (js/planes.mjs perDay, held equal by a test)."""
    if v is None:
        return 'not measured'
    if v == 0:
        return 'none'
    if isinstance(v, list):
        return f'up to {one(v[1])} a day' if v[0] == 0 else f'{one(v[0])} to {one(v[1])} a day'
    return f'{one(v)} a day'


MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']


def period(months) -> str:
    """'January to August 2026' from ['202601', '202608'] (js/planes.mjs period, held equal by a test)."""
    (y1, m1), (y2, m2) = ((m[:4], int(m[4:])) for m in months)
    if y1 == y2:
        return f'{MONTHS[m1 - 1]} to {MONTHS[m2 - 1]} {y2}'
    return f'{MONTHS[m1 - 1]} {y1} to {MONTHS[m2 - 1]} {y2}'


def most(v) -> int:
    """The most a figure can mean, for comparing with a whole number: a range's top; '<1' and None are 0."""
    if isinstance(v, list):
        v = v[1]
    return v if isinstance(v, int) else 0


# ----------------------------------------------------------------- the one judgement on the page

# BANDS, NOT A MIDDLE FIGURE (Bill, 2026-10-28, option C of three). Near an approach a sector is two places: TW9 1 on
# a west day is 66 postcodes at ~317 and 25 under 10, with 69 on the path's edge between them. Its median (317) is
# true of none of the quiet 25: the same mistake as averaging west and east days, which he ruled out on 25 Oct ("true
# on no day"), made in space instead of time. Least-to-most ("1 to 317") was true and said nothing: every TW9 sector
# read alike, and 464 pages reading alike is the doorway shape PAGE_FROM exists to avoid. So a cell counts the
# sector's postcodes in bands, and the size of the busiest figure goes on the line above the table (bands alone read
# SE10's 89-153 and Kew's 317 both as "100+").
BANDS = ((100, 'at 100+'), (10, 'at 10 to 99'), (0, 'under 10'))  # (from, words), busiest first
EDGE = 'on an edge'
BAND_ORDER = ('at 100+', 'at 10 to 99', EDGE, 'under 10')
BANDS_SAID = (f'The table counts the postcodes of each sector by how many planes pass over them a day: '
              f'{BANDS[0][0]} or more, {BANDS[1][0]} to {BANDS[0][0] - 1}, or under {BANDS[1][0]}.')


def band(v) -> str:
    """The band one shown figure falls in: '<1' and 0 are under 10."""
    n = 0 if v == '<1' else v
    return next(words for start, words in BANDS if n >= start)


def sector_parts(figs: list) -> list[str]:
    """A group of postcodes counted by band, for one airport on one kind of day: ['66 at 100+', '69 on an edge', ...].

    `figs` holds one figure per postcode, as the planes files hold it: an int (0 only where measured zero), '<1'
    (also every postcode the files do not list under this airport, UNLISTED), or [least, most] for a postcode on a
    cone's edge. An edge postcode counts in a band when both its ends fall in it ([150, 317] is 100+ either way);
    only one whose ends fall in different bands is EDGE, where the band itself is the coin toss. Never None: the
    caller says "not measured" itself. Empty bands are left out.
    """
    counts = Counter()
    for v in figs:
        ends = {band(x) for x in v} if isinstance(v, list) else {band(v)}
        counts[ends.pop() if len(ends) == 1 else EDGE] += 1
    return [f'{counts[words]:,} {words}' for words in BAND_ORDER if counts[words]]


def sector_reading(figs: list) -> str:
    """The parts as one phrase: "66 at 100+, 69 on an edge, 25 under 10"."""
    return ', '.join(sector_parts(figs))


def overall_reading(figs: list) -> str:
    """The line above a table, for a whole district on one kind of day: the busiest figure, then the bands."""
    busiest = max(most(v) for v in figs)
    if busiest == 0:
        return f'under 1 a day at all {len(figs):,} of its postcodes'
    return f'up to {busiest} a day; of its {len(figs):,} postcodes, {sector_reading(figs)}'


# ----------------------------------------------------------------- inputs

def pc_key(pc: str):
    """Sort key for a district, sector or postcode in reading order: TW2 before TW10, TW9 1 before TW9 10."""
    out = []
    for part in re.findall(r'[A-Z]+|\d+', pc.upper()):
        out.append((0, int(part), '') if part.isdigit() else (1, 0, part))
    return out


def read_planes(planes: Path = PLANES):
    """(airports.json, {district: file}) from the files the front page reads."""
    meta = json.loads((planes / 'airports.json').read_text(encoding='utf-8'))
    files = {d: json.loads((planes / f'{d}.json').read_text(encoding='utf-8')) for d in meta['districts']}
    return meta, files


def district_context(path: Path = AVERAGES) -> dict:
    """{district: {'lads': Counter, 'city': str, 'at': (easting, northing)}}: councils and positions, no figures."""
    with np.load(path, allow_pickle=False) as z:
        pcs, lads, cities = z['postcode'], z['lad'], z['city']
        east, north = z['easting'].astype(float), z['northing'].astype(float)
    by, sums = {}, {}
    for k, pc in enumerate(pcs):
        d = str(pc).split()[0]
        c = by.setdefault(d, {'lads': Counter(), 'cities': Counter()})
        c['lads'][str(lads[k])] += 1
        c['cities'][str(cities[k])] += 1
        s = sums.setdefault(d, [0.0, 0.0, 0])
        s[0] += east[k]
        s[1] += north[k]
        s[2] += 1
    return {d: {'lads': c['lads'], 'city': c['cities'].most_common(1)[0][0],
                'at': (sums[d][0] / sums[d][2], sums[d][1] / sums[d][2])} for d, c in by.items()}


def district_totals(districts, nspl: Path = NSPL) -> dict[str, tuple[int, int]]:
    """{district: (live postcodes, of them large users)} from NSPL, for the districts asked about."""
    want, live, large = set(districts), Counter(), Counter()
    with nspl.open(newline='', encoding='utf-8-sig') as fh:
        reader = csv.reader(fh)
        header = next(reader)
        try:
            ip, it, iu = header.index('pcds'), header.index('doterm'), header.index('usrtypind')
        except ValueError as exc:
            raise SystemExit(f'{nspl.name}: {exc}: NSPL has changed') from exc
        for r in reader:
            d = r[ip].split(' ')[0].upper()
            if d in want and not r[it].strip():
                live[d] += 1
                large[d] += r[iu].strip() == '1'
    return {d: (live[d], large[d]) for d in want}


# ----------------------------------------------------------------- which districts, and what each says

def figures_by_airport(f: dict) -> dict[str, dict[str, list]]:
    """{airport: {postcode: [figure per kind, the files' order]}} for every postcode of the district, UNLISTED
    filled in where the file lists the postcode under no figure from that airport."""
    pcs = list(f['postcodes']) + list(f['none'])
    codes = {code for listed in f['postcodes'].values() for code in listed}
    return {code: {pc: f['postcodes'].get(pc, {}).get(code, [UNLISTED] * 3) for pc in pcs} for code in codes}


def verdict(f: dict, totals: tuple[int, int]) -> str | None:
    """None when the district gets a page; otherwise why not, in words for --list."""
    measured = len(f['postcodes']) + len(f['none'])
    live, large = totals
    busiest = max((most(v) for listed in f['postcodes'].values() for figs in listed.values() for v in figs),
                  default=0)
    if busiest < PAGE_FROM:
        return f'busiest postcode {busiest} a day (< {PAGE_FROM})'
    if measured > live:
        raise SystemExit(f"{f['district']}: {measured} measured, {live} live in NSPL: not the averages' edition")
    if measured < COVERED_FROM * live:
        return f'{measured} of {live} postcodes in the covered councils (< {COVERED_FROM:.0%})'
    if large > LARGE_UNDER * live:
        return f'{large} of {live} postcodes are large users (> {LARGE_UNDER:.0%})'
    if measured < MIN_POSTCODES:
        return f'{measured} postcodes measured (< {MIN_POSTCODES})'
    return None


def nearest(name: str, at: dict, with_page: list[str]) -> list[str]:
    """The NEARBY districts with a page closest to `name`, by the mean position of their postcodes."""
    x, y = at[name]
    others = sorted((math.hypot(at[d][0] - x, at[d][1] - y), pc_key(d), d) for d in with_page if d != name)
    return [d for _, _, d in others[:NEARBY]]


def councils(lads: Counter) -> list[tuple[str, str, str | None]]:
    """[(city, council, its area page's path or None)], most postcodes first."""
    out = []
    for lad, _ in lads.most_common():
        city, borough = area.app.LAD_TO_BOROUGH[lad]
        path = f'/area/{area.slug(city)}/{area.slug(borough)}/'
        out.append((city, borough, path if (REPO / path.strip('/') / 'index.html').exists() else None))
    return out


def model(name: str, f: dict, meta: dict, ctx: dict, totals: tuple[int, int], names: dict, nearby: list[str],
          order: list[tuple[str, str]]) -> dict:
    """Everything a district's page says, before any HTML."""
    col = {c: i for i, c in enumerate(meta['classes'])}
    figs = figures_by_airport(f)
    sectors: dict[str, list[str]] = {}
    for pc in sorted(set(f['postcodes']) | set(f['none']), key=pc_key):
        sectors.setdefault(pc[:-2], []).append(pc)  # the sector: all but the inward code's two letters

    def reading(values, how, unmeasured):
        # A kind of day with no figure is not measured (build_planes_overhead.figures: null, never 0).
        values = [v for v in values if v is not None]
        return how(values) if values else unmeasured

    tables, also = [], []
    for code in sorted(figs, key=lambda c: (-max(most(v) for vs in figs[c].values() for v in vs), c)):
        info, by_pc = meta['airports'][code], figs[code]
        top = max(most(v) for vs in by_pc.values() for v in vs)
        if top < PAGE_FROM:
            also.append({'name': names.get(code, code), 'most': per_day(top)})
            continue
        tables.append({
            'code': code, 'name': names.get(code, code), 'period': period(info['months']),
            'columns': [(label, f"{info['share_pct'][kind]}% of days") for kind, label in order],
            'overall': [(label, info['share_pct'][kind],
                         reading([by_pc[pc][col[kind]] for pc in by_pc], overall_reading, 'not measured'))
                        for kind, label in order],
            # Each cell a list of band phrases, one line each, so a narrow column never breaks "at 10 to 99".
            'rows': [(sector, len(pcs), [reading([by_pc[pc][col[kind]] for pc in pcs], sector_parts,
                                                 ['not measured']) for kind, _ in order])
                     for sector, pcs in sectors.items()],
        })
    measured = len(f['postcodes']) + len(f['none'])
    live = totals[0]
    # The note explains EDGE only where a reading says it: a range inside one band reads as that band.
    edges = any(EDGE in text for t in tables for text in [*(o[2] for o in t['overall']),
                                                            *(p for row in t['rows'] for c in row[2] for p in c)])
    return {
        'district': name, 'slug': name.lower(), 'city': ctx['city'],
        'city_label': area.CITY_LABEL.get(ctx['city'], ctx['city'].title()),
        'councils': councils(ctx['lads']),
        'measured': measured, 'live': live,
        'periods': sorted({t['period'] for t in tables}),
        'tables': tables, 'also': also,
        'edge': edges, 'approx': len(f['approx']), 'other': len(f['other']),
        'example': next(iter(sectors.values()))[0],
        'definition': f"{meta['definition']} {meta['direction_rule']}",
        'credits': meta['credits'], 'licence': meta['licence'],
        'nearby': nearby,
    }


# ----------------------------------------------------------------- HTML

e = area.e


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def render(m: dict) -> str:
    d = m['district']
    council_names = [b for _, b, _ in m['councils']]
    where = listed(council_names)
    measured = (f"All {m['live']:,} of its postcodes measured" if m['measured'] == m['live']
                else f"{m['measured']:,} of its {m['live']:,} postcodes measured, the ones in {where}")
    airports = listed([t['name'] for t in m['tables']])
    sections = []
    for t in m['tables']:
        # 'Flying west' -> 'flies west', 'Both ways' -> 'flies both ways': the answer's own labels.
        overall = '\n'.join(f"<li>On a day it flies {e(label.lower().removeprefix('flying '))} ({share}% of days): "
                            f'{e(text)}</li>' for label, share, text in t['overall'])
        head = ''.join(f'<th scope="col">{e(label)}<span class="note">{e(share)}</span></th>'
                       for label, share in t['columns'])
        rows = '\n'.join(f'<tr><th scope="row">{e(sector)}<span class="note">{n} postcode{"s" if n != 1 else ""}'
                         f'</span></th>' + ''.join('<td>' + ''.join(f'<span>{e(p)}</span>' for p in c) + '</td>'
                                                   for c in cells) + '</tr>'
                         for sector, n, cells in t['rows'])
        sections.append(
            f'<h2 id="{e(t["code"].lower())}">From {e(t["name"])}</h2>\n'
            f'<p>Planes land and take off into the wind, so the weather decides which way {e(t["name"])} flies, '
            f'and that decides how many pass over {e(d)}. Across its postcodes, {e(t["period"])}:</p>\n'
            f'<ul class="overall">\n{overall}\n</ul>\n'
            f'<p class="note-p">{e(BANDS_SAID)}</p>\n'
            '<div class="tw">\n<table>\n'
            f'<caption class="visually-hidden">Planes overhead from {e(t["name"])} in {e(d)}, by postcode sector '
            f'and the way {e(t["name"])} flies</caption>\n'
            f'<thead><tr><th scope="col">Sector</th>{head}</tr></thead>\n<tbody>\n{rows}\n</tbody>\n'
            '</table>\n</div>')
    if m['also']:
        sections.append('<p class="note-p">Also counted here: '
                        + '; '.join(f"{e(a['name'])}, at most {e(a['most'])} over any of its postcodes"
                                    for a in m['also']) + '.</p>')
    notes = []
    if m['edge']:
        notes.append('On an edge: the postcode is on the edge of a flight path, where a few metres decide whether a '
                     'plane counts as overhead, and the fewest and the most within 100 m of it fall in different '
                     'bands.')
    if m['approx']:
        notes.append(f"{m['approx']} of its postcodes have a position ONS estimates, so their figures may be for "
                     'a spot a few hundred metres away.')
    if m['other']:
        notes.append(f"Over {m['other']} of its postcodes, other flying passes too, from airfields, helicopters and "
                     'airports we cannot check against official counts, so few planes from the airports we count '
                     'does not mean a quiet sky there.')
    note_html = '\n'.join(f'<p class="note-p">{e(n)}</p>' for n in notes)
    area_links = '\n'.join(f'<li><a href="{e(path)}">{e(b)}: noise and liveability score</a></li>'
                           for _, b, path in m['councils'] if path)
    nearby = ' '.join(f'<a href="{URL_ROOT}{e(n.lower())}/">{e(n)}</a>' for n in m['nearby'])
    first_period = m['periods'][0] if len(m['periods']) == 1 else '; '.join(m['periods'])
    return PAGE.format(
        title=e(f'Planes overhead in {d}: flight paths over {council_names[0]} | Sky Score'),
        description=e(f'How many planes pass over {d} ({where}) on a day {airports} flies west, east or both ways, '
                      f'postcode sector by sector. Counted from flight tracking, {first_period}.')[:300],
        canonical=f'{area.SITE}{URL_ROOT}{m["slug"]}/',
        district=e(d), city_label=e(m['city_label']), where=e(where),
        measured=e(measured), period=e(first_period), example=e(m['example']),
        sections='\n\n'.join(sections), notes=note_html,
        definition=e(m['definition']),
        counted=e(f'Counted from community flight tracking, checked against the CAA\'s monthly totals for '
                  f'{airports}.'),
        credits=e('; '.join(m['credits'])), licence=e(m['licence']),
        area_links=area_links or '<li><a href="/area/">Every area we cover</a></li>',
        nearby=nearby or '<a href="/planes-overhead/">Every district</a>',
    )


STYLE = """
  /* The area pages' look (scripts/build_area_pages.py), so the two read as one site. */
  :root {{ color-scheme: light dark;
    --dark:#141414; --mid:#636363; --line:#e7e5e4; --bg:#fafaf9; --orange:#c2410c; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:0; font-family:'Inter',system-ui,sans-serif; color:var(--dark); background:#fff; line-height:1.6; }}
  a:focus-visible, input:focus-visible, button:focus-visible {{ outline:3px solid #d35a12; outline-offset:2px; }}
  .wrap {{ max-width:760px; margin:0 auto; padding:24px 20px 64px; }}
  a {{ color:var(--orange); }}
  nav.crumbs {{ font-size:12px; color:var(--mid); margin-bottom:20px; }}
  h1 {{ font-size:28px; line-height:1.25; margin:0 0 6px; }}
  .sub {{ color:var(--mid); font-size:14px; margin:0 0 20px; }}
  .check {{ margin:0 0 28px; padding:14px 16px; background:var(--bg); border:1px solid var(--line); border-radius:8px; }}
  .check label {{ display:block; font-weight:600; font-size:14px; margin-bottom:6px; }}
  .check .row {{ display:flex; gap:8px; flex-wrap:wrap; }}
  .check input {{ font:inherit; font-size:16px; padding:8px 10px; border:1px solid var(--mid); border-radius:6px; width:12em; max-width:100%; background:Canvas; color:CanvasText; }}
  .check button {{ font:600 15px/1.5 'Inter', system-ui, sans-serif; padding:8px 16px; border:0; border-radius:6px; background:var(--dark); color:Canvas; cursor:pointer; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th, td {{ text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }}
  thead th {{ font-weight:600; }}
  td span {{ display:block; white-space:nowrap; }}
  /* A phone (the site bar's own breakpoint): four columns of band lines must fit 350 px without a sideways
     scroll, measured on the widest pages (BR1, SK8, SE1) at 390 px, 2026-10-28. */
  @media (max-width: 680px) {{
    table {{ font-size:12.5px; }}
    th, td {{ padding:6px 3px; }}
  }}
  .note {{ display:block; color:var(--mid); font-size:11px; font-weight:400; }}
  .note-p {{ color:var(--mid); font-size:13px; }}
  .tw {{ overflow-x:auto; }}
  .visually-hidden {{ position:absolute; width:1px; height:1px; padding:0;
    margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }}
  h2 {{ font-size:18px; margin:32px 0 8px; }}
  ul.overall {{ margin:0 0 16px; padding-left:18px; }}
  .sources {{ font-size:12px; color:var(--mid); }}
  .nearby a {{ display:inline-block; margin:0 10px 6px 0; }}
  footer {{ margin-top:40px; font-size:12px; color:var(--mid); }}
  /* The site bar (2026-10-06): the front page's header.top, in this page's own font and colours. */
  .site-top {{ display:flex; align-items:center; justify-content:space-between; gap:8px 16px; flex-wrap:wrap; padding:14px clamp(16px, 4vw, 48px); }}
  .site-top .site-brand {{ font-weight:700; font-size:18px; letter-spacing:-0.01em; text-decoration:none; color:var(--dark); }}
  .site-top .site-nav {{ display:flex; gap:4px; flex-wrap:wrap; }}
  .site-top .site-nav {{ align-items:center; }}
  .site-top .site-nav a {{ font-size:14px; font-weight:500; text-decoration:none; padding:8px 12px; border-radius:8px; color:var(--dark); }}
  .site-top .site-nav a.nav-cta {{ box-shadow: inset 0 0 0 1.5px var(--dark); font-weight:600; }}
  .site-top .site-nav a:hover {{ text-decoration: underline; text-decoration-thickness: 1.5px; text-underline-offset: 7px; }}
  .site-top .site-nav a[aria-current] {{ text-decoration: underline; text-decoration-color: var(--orange); text-decoration-thickness: 3px; text-underline-offset: 7px; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --dark:#f5f5f4; --mid:#a1a1a1; --line:#3a3a3a; --bg:#1c1c1c; --orange:#fb923c; }}
    body {{ background:#141414; }}
  }}
  /* The phone menu (2026-10-23), as on the area pages: a popover, so no script. */
  .menu-btn, .menu-close {{ display: none; }}
  .site-top .site-nav[popover] {{ position: static; inset: auto; width: auto; height: auto; margin: 0; padding: 0; border: 0; overflow: visible; background: none; color: inherit; }}
  @supports selector(:popover-open) {{
    @media (max-width: 680px) {{
      .menu-btn, .menu-close {{ display: inline-block; font: 600 14px/1.5 'Inter', system-ui, sans-serif; color: inherit; background: none; border: 0; border-radius: 8px; padding: 8px 12px; box-shadow: inset 0 0 0 1.5px currentColor; cursor: pointer; }}
      .menu-btn:focus-visible, .menu-close:focus-visible {{ outline: 3px solid #d35a12; outline-offset: 2px; }}
      .site-top .site-nav[popover]:not(:popover-open) {{ display: none; }}
      .site-top .site-nav:popover-open {{ position: fixed; inset: 0 0 auto 0; display: grid; gap: 2px; padding: max(12px, env(safe-area-inset-top, 0px)) max(16px, env(safe-area-inset-right, 0px)) 16px max(16px, env(safe-area-inset-left, 0px)); background: Canvas; color: CanvasText; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2); }}
      .site-top .site-nav:popover-open .menu-close {{ justify-self: end; }}
      .site-top .site-nav:popover-open a {{ padding: 12px; font-size: 16px; }}
      .site-top .site-nav::backdrop {{ background: rgba(0, 0, 0, 0.25); }}
    }}
  }}
"""

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<meta name="description" content="{description}" />
<link rel="canonical" href="{canonical}" />
<link rel="icon" href="/favicon.ico" sizes="32x32" />
<link rel="icon" href="/icons/favicon.svg" type="image/svg+xml" />
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
<link rel="stylesheet" href="/fonts/fonts.css" />
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: https://cubitt33.goatcounter.com; connect-src https://cubitt33.goatcounter.com; base-uri 'self'; form-action 'self';" />
<style>""" + STYLE + """</style>
</head>
<body>
<!-- The site bar, the same on every page since 2026-10-06 (the front page's header.top). -->
<nav class="site-top" aria-label="Site"><a class="site-brand" href="/">Sky Score</a><button type="button" class="menu-btn" popovertarget="site-nav">Menu</button><div class="site-nav" id="site-nav" popover><button type="button" class="menu-close" popovertarget="site-nav" popovertargetaction="hide">Close</button><a class="nav-cta" href="/map/">Full map</a><a href="/reports/">Reports</a><a href="/how-it-works/">How it works</a><a href="/pricing">Pricing</a><a href="/api/">API</a><a href="/about/">About</a></div></nav>
<div class="wrap">
"""

FOOT = """
<footer>
<p><a href="/">Sky Score</a> &middot; <a href="/map/">Full map</a> &middot; <a href="/reports/">Reports</a> &middot; <a href="/area/">All areas</a> &middot; <a href="/planes-overhead/">Planes overhead</a> &middot; <a href="/how-it-works/">How it works</a> &middot; <a href="/about/">About</a> &middot; <a href="/api/">For developers</a> &middot; <a href="/privacy">Privacy</a> &middot; <a href="/terms">Terms</a></p>
</footer>
</div>
<script type="module" src="/js/count.mjs"></script>
</body>
</html>
"""

PAGE = HEAD + """<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Sky Score</a> &rsaquo; <a href="/planes-overhead/">Planes overhead</a> &rsaquo; {city_label}</nav>
<main data-district="{district}">
<h1>Planes overhead in {district}</h1>
<p class="sub">{where}, {city_label}. {measured}, {period}.</p>

<form class="check" action="/" method="get">
<label for="postcode">See the figures for one postcode in {district}</label>
<div class="row"><input id="postcode" name="postcode" type="text" autocomplete="postal-code" autocapitalize="characters" spellcheck="false" maxlength="8" required placeholder="{example}" /><button type="submit">Check</button></div>
</form>

{sections}

{notes}

<h2>What counts as overhead</h2>
<p>{definition}</p>

<h2>Near {district}</h2>
<p class="nearby">{nearby}</p>

<h2>The councils</h2>
<ul>
{area_links}
</ul>

<h2>Where these figures come from</h2>
<p class="sources">{counted} {credits}. Licence: {licence}.</p>
<p class="sources"><a href="/how-it-works/#planes-overhead">How the planes are counted</a></p>
</main>
""" + FOOT

INDEX = HEAD + """<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Sky Score</a> &rsaquo; Planes overhead</nav>
<main>
<h1>Planes overhead, district by district</h1>
<p class="sub">How many planes pass over {count} postcode districts, on a day each airport flies west, east or both ways, measured from flight tracking, {period}. Districts where no postcode sees {page_from} a day are left out.</p>
{body}
</main>
""" + FOOT


def render_index(models: list[dict]) -> str:
    by_city: dict[str, list[dict]] = {}
    for m in models:
        by_city.setdefault(m['city_label'], []).append(m)
    body = []
    for label in sorted(by_city):
        items = '\n'.join(f'<li><a href="{URL_ROOT}{e(m["slug"])}/">{e(m["district"])}</a> '
                          f'<span class="note-p">{e(listed([b for _, b, _ in m["councils"]]))}</span></li>'
                          for m in sorted(by_city[label], key=lambda m: pc_key(m['district'])))
        body.append(f'<h2>{e(label)}</h2>\n<ul>\n{items}\n</ul>')
    periods = sorted({p for m in models for p in m['periods']})
    return INDEX.format(title=e('Planes overhead, district by district | Sky Score'),
                        description=e(f'How many planes pass over {len(models)} postcode districts, by the way '
                                      'each airport flies. Counted from flight tracking.'),
                        canonical=f'{area.SITE}{URL_ROOT}', count=len(models), period=e('; '.join(periods)),
                        page_from=PAGE_FROM, body='\n'.join(body))


def render_sitemap(manifest: dict) -> str:
    """sitemap-planes.xml from the manifest: the index, then each district in reading order, each lastmod the day
    its page's content last changed (the manifest's `changed`; the pages are gitignored, so git cannot date them).
    A lastmod that is always the build date is one a crawler learns to ignore (build_area_pages.last_changed)."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path in sorted(manifest, key=lambda p: (p != INDEX_PATH, pc_key(p))):
        loc = '/' + path.removesuffix('index.html')
        prio = '0.7' if path == INDEX_PATH else '0.6'
        out.append(f'  <url><loc>{area.SITE}{loc}</loc><lastmod>{manifest[path]["changed"]}</lastmod>'
                   f'<changefreq>monthly</changefreq><priority>{prio}</priority></url>')
    out.append('</urlset>')
    return '\n'.join(out) + '\n'


# ----------------------------------------------------------------- build, write, check

INDEX_PATH = 'planes-overhead/index.html'


def build(meta, files, ctx, totals, names, order):
    """({repo path: page text}, {district: reason it has no page}) from the inputs."""
    reasons = {d: verdict(f, totals[d]) for d, f in files.items()}
    with_page = sorted((d for d, why in reasons.items() if why is None), key=pc_key)
    at = {d: ctx[d]['at'] for d in with_page}
    models = [model(d, files[d], meta, ctx[d], totals[d], names, nearest(d, at, with_page), order)
              for d in with_page]
    pages = {f'planes-overhead/{m["slug"]}/index.html': render(m) for m in models}
    pages[INDEX_PATH] = render_index(models)
    return pages, {d: why for d, why in reasons.items() if why}


NEEDS = ((PLANES / 'airports.json', 'scripts/build_planes_overhead.py --write'),
         (AVERAGES, 'scripts/adsb_postcode_averages.py'), (NSPL, 'the NSPL roll (HANDOVER)'))


def missing_inputs() -> list[str]:
    """The gitignored inputs not on this machine, each with what makes it (a clone without the tracks has none)."""
    return [f'{need.relative_to(REPO)} (made by {how})' for need, how in NEEDS if not need.exists()]


def inputs():
    meta, files = read_planes()
    ctx = district_context()
    return meta, files, ctx, district_totals(files), airport_names(), kinds()


MANIFEST = REPO / 'data' / 'planes-pages-manifest.json'


def encode(text: str) -> bytes:
    """The bytes a page is written and uploaded as (so its md5 is S3's ETag for a one-part upload)."""
    return text.encode('utf-8')


def read_manifest(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None


def manifest(pages: dict[str, str], recorded: dict | None, today: str) -> dict:
    """{path: {bytes, md5, changed}}: `changed` kept from the recorded manifest while a page's bytes are the same,
    today where they are new or differ."""
    out = {}
    for path in sorted(pages):
        b = encode(pages[path])
        md5 = hashlib.md5(b, usedforsecurity=False).hexdigest()
        was = (recorded or {}).get(path, {})
        out[path] = {'bytes': len(b), 'md5': md5, 'changed': was['changed'] if was.get('md5') == md5 else today}
    return out


def check(pages: dict[str, str], root: Path = REPO) -> list[str]:
    """The differences between what --write would write and what is on disk, as lines (none: in step)."""
    problems = []
    out = root / 'planes-overhead'
    on_disk = {p.relative_to(root).as_posix() for p in out.rglob('index.html')} if out.exists() else set()
    for path in sorted(set(pages) | on_disk):
        if path not in on_disk:
            problems.append(f'missing: {path}')
        elif path not in pages:
            problems.append(f'no longer built: {path}')
        elif (root / path).read_bytes() != encode(pages[path]):
            problems.append(f'stale: {path}')
    recorded = read_manifest(root / MANIFEST.relative_to(REPO))
    if recorded is None or manifest(pages, recorded, today='') != recorded:
        problems.append(f'{MANIFEST.name} does not match the built pages')
    else:
        sitemap = root / SITEMAP.name
        if not sitemap.exists() or sitemap.read_text(encoding='utf-8') != render_sitemap(recorded):
            problems.append(f'{SITEMAP.name} does not match the manifest')
    return problems


def write(pages: dict[str, str], root: Path = REPO, today: str | None = None) -> None:
    """Write every page and remove any district that no longer has one; then the sitemap and, last, the manifest."""
    today = today or datetime.now(UTC).strftime('%Y-%m-%d')
    out = root / 'planes-overhead'
    for old in list(out.rglob('index.html')) if out.exists() else []:
        if old.relative_to(root).as_posix() not in pages:
            old.unlink()
            if not any(old.parent.iterdir()):
                old.parent.rmdir()
    for path, text in pages.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encode(text))
    mpath = root / MANIFEST.relative_to(REPO)
    new = manifest(pages, read_manifest(mpath), today)
    (root / SITEMAP.name).write_text(render_sitemap(new), encoding='utf-8', newline='\n')
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(new, indent=1) + '\n', encoding='utf-8', newline='\n')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--strict', action='store_true', help='a missing input fails --check (planes-pages-deploy)')
    a = ap.parse_args()
    if not (a.write or a.check or a.list):
        ap.error('pass --write, --check or --list')
    if missing := missing_inputs():
        # Unrunnable is not failed, and never a pass: preflight reads a leading INCONCLUSIVE and names the gate.
        # A deploy must not read it at all (--strict): it would upload whatever happens to be on disk.
        soft = a.check and not (a.write or a.list or a.strict)
        print(('INCONCLUSIVE: ' if soft else 'FAIL: ') + 'missing ' + '; '.join(missing))
        return 0 if soft else 1
    meta, files, ctx, totals, names, order = inputs()
    if a.list:
        for d in sorted(files, key=pc_key):
            print(f'  {d:6} {verdict(files[d], totals[d]) or "PAGE"}')
        if not (a.write or a.check):
            return 0
    pages, without = build(meta, files, ctx, totals, names, order)
    print(f'{len(pages) - 1} district pages and the index; {len(without)} districts without a page')
    if a.write:
        write(pages)
        print(f'wrote {len(pages)} pages and {SITEMAP.name}')
    if a.check:
        problems = check(pages)
        print('\n'.join(problems) if problems else 'OK')
        if problems:
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
