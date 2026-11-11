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
  data/planes-districts-by-council.json  TRACKED (2026-11-01): which districts each council's AREA page links to
                                      (council_index); names only, no figure

AFTER A PLANES ROLL, RERUN THIS (the pages bake the figures, as area pages bake scores; the area pages bake the
links, so a district gaining or losing its page moves them too: build_area_pages.py --check reds until rerun)

    python scripts/build_planes_overhead.py --write
    python scripts/build_planes_pages.py --write
    python scripts/build_area_pages.py --write
    python scripts/make.py planes-deploy
    python scripts/make.py planes-pages-deploy
    python scripts/make.py area-deploy         # after the pages it links to
    python scripts/make.py meta-deploy         # the sitemaps, last

USAGE
    python scripts/build_planes_pages.py --write
    python scripts/build_planes_pages.py --check     # the pages on disk == what --write would write
    python scripts/build_planes_pages.py --list      # every district, and why it has a page or not
    python scripts/build_planes_pages.py --write --home   # the front page's planes band only (2026-11-03), from the
    python scripts/build_planes_pages.py --check --home   # committed council index: no tracks needed
    python scripts/build_planes_pages.py --check --inputs-from <main clone>   # a worktree checking against the tracks
                                                     # and built pages of another clone, reading only

The front page's dark band (home/index.html, between the PLANES-BAND markers) is written by --write too, from the
council index's `consultation` entry: Heathrow's consultation while it is open, the planes pages from the day after.
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
from typing import NamedTuple

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
STREET_REPORT = REPO / 'js' / 'street_report.mjs'
URL_ROOT = '/planes-overhead/'

PAGE_FROM = 10  # Bill, 2026-10-28: some postcode shown this many a day or more, on some kind of day
COVERED_FROM = 0.5  # share of the district's live postcodes the covered councils hold
LARGE_UNDER = 0.5  # share of its live postcodes that may be large users
MIN_POSTCODES = 20  # measured postcodes, at least
NEARBY = 8  # districts with a page, nearest first, linked from each page
# An area page links a district's page when its council holds this share or more of the district's measured
# postcodes (agreed with Bill 2026-10-31): a district split across a boundary is linked from both sides, one that
# only grazes a council is not.
LINK_FROM = 0.10
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
BANDS_SAID = ("Each sector's bar splits its postcodes by how many planes pass over them a day; the figure above "
              "it counts those in the busiest band the sector reaches. The list above gives the whole district's "
              'counts.')

# THE BAND BAR (declutter, 2026-11-03; Bill: "do the proposed fixes", audit items 4 and 6). A cell showed every band
# as a line ("137 at 100+ / 200 on an edge / 450 under 10"): true, but four numbers a cell made a table no one could
# scan. Now a cell SHOWS the busiest band it reaches and draws all of them as one bar, each band's width its count of
# postcodes; the bar's label (screen readers, and a hover title) says every count. Still bands, never a middle figure:
# the bar IS the bands. Built from the cell's own phrases (sector_parts), so the bar and the words cannot disagree.
# Colours: the full map's planes layer (build_planes_layer.COLOURS: its 10-49 step for "10 to 99", its 100-199 step
# for "100+"), held equal by tests/test_build_planes_pages.py, so a band reads the same on the map and on these pages.
BAND_CLASS = {'at 100+': 'b100', 'at 10 to 99': 'b10', EDGE: 'bedge', 'under 10': 'b0'}
BAND_COLOURS = {'at 100+': '#9a4316', 'at 10 to 99': '#dc8a4a'}
BAND_KEY = (('at 100+', f'{BANDS[0][0]} or more'), ('at 10 to 99', f'{BANDS[1][0]} to {BANDS[0][0] - 1}'),
            (EDGE, EDGE), ('under 10', f'under {BANDS[1][0]}'))


def split_bands(parts: list[str]) -> tuple[list[str], list[tuple[int, str, str]]]:
    """A cell's phrases as (other lines, bands). A band is sector_parts' "<count> <band words>", kept as (count,
    words, phrase), busiest first; anything else ("up to 317 a day", "not measured", "at all 2 postcodes") is a line."""
    lines, bands = [], []
    for phrase in parts:
        n, _, words = phrase.partition(' ')
        if words in BAND_CLASS and n.replace(',', '').isdigit():
            bands.append((int(n.replace(',', '')), words, phrase))
        else:
            lines.append(phrase)
    return lines, bands


def band_bar(bands: list[tuple[int, str, str]]) -> str:
    """The bands as one bar, each band's width its count of postcodes; its label says every count."""
    label = 'Postcodes by planes a day: ' + ', '.join(phrase for _, _, phrase in bands)
    segments = ''.join(f'<i class="{BAND_CLASS[words]}" style="flex-grow:{n}"></i>' for n, words, _ in bands)
    return f'<div class="bands" role="img" aria-label="{e(label)}" title="{e(label)}">{segments}</div>'


def cell_html(parts: list[str], top: bool = False) -> str:
    """One cell: its lines (the busiest figure, where the cell has one), the busiest band's count, then the bar.
    `top` marks the first line as the cell's head (the consultation pack's "up to N a day")."""
    lines, bands = split_bands(parts)
    shown = lines + [bands[0][2]] if bands else lines
    html = ''.join(f'<span class="top">{e(p)}</span>' if top and i == 0 else f'<span>{e(p)}</span>'
                   for i, p in enumerate(shown))
    return html + (band_bar(bands) if bands else '')


def bands_in(cells) -> set[str]:
    """The bands any of these cells draws."""
    return {words for cell in cells for _, words, _ in split_bands(cell)[1]}


def band_key(present: set[str]) -> str:
    """The bar's key, after the words above a table: only the bands its cells draw, so "on an edge" appears only
    where a bar has an edge (the edge note's own rule). The words say it, so the swatches are hidden from readers."""
    return ('<span class="key" aria-hidden="true">'
            + ''.join(f'<span><i class="{BAND_CLASS[band]}"></i>{e(words)}</span>'
                      for band, words in BAND_KEY if band in present)
            + '</span>')


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


class Day(NamedTuple):
    """One kind of day across a district. `busiest` is None where it was not measured (null, never 0)."""
    busiest: int | None
    parts: list[str]
    total: int


def day_figure(figs: list) -> Day:
    values = [v for v in figs if v is not None]
    return Day(max(most(v) for v in values), sector_parts(values), len(values)) if values else Day(None, [], 0)


def day_headline(day: Day) -> str:
    """The figure as a page leads with it, always with its "Up to": a bare 318 would read as every postcode's, and TW9's
    66 under 10 say otherwise."""
    if day.busiest is None:
        return 'Not measured'
    return 'Under 1' if day.busiest == 0 else f'Up to {day.busiest}'


def day_html(label: str, share: int, day: Day) -> str:
    """One kind of day: the airport's way of flying, the figure, then its postcodes as one bar with every count said.
    The bar's counts are of POSTCODES and say so: under "Up to 318 a day" a bare 386 reads as planes. Where every postcode
    is under 1 there is nothing to split, and "under 10" beneath "Under 1" would read as a second figure, so it says so."""
    way = label.lower().removeprefix('flying ')
    head = f'<li><p class="way">On a day it flies {e(way)}, {share}% of days</p><p class="big">{e(day_headline(day))}</p>'
    if day.busiest is None:
        return head + '</li>'
    if day.busiest == 0:
        return head + f'<p class="aday">a day, at all {day.total:,} of its postcodes</p></li>'
    _, bands = split_bands(day.parts)
    counts = {words: n for n, words, _ in bands}
    key = ''.join(f'<dt><i class="{BAND_CLASS[band_words]}"></i>{e(said)}</dt><dd>{counts[band_words]:,}</dd>'
                  for band_words, said in BAND_KEY if band_words in counts)
    return (head + f'<p class="aday">a day</p><p class="of-all">Of its {day.total:,} postcodes:</p>'
            + band_bar(bands) + f'<dl class="counts">{key}</dl></li>')


def day_lines(day: Day) -> list[str]:
    """A whole district on one kind of day as table lines (the consultation pack, 2026-11-01), one line each, so a phone's
    narrow column never breaks a band: ['up to 317 a day', '137 at 100+', ...]."""
    if day.busiest is None:
        return ['not measured']
    if day.busiest == 0:
        return ['under 1 a day', f'at all {day.total:,} postcodes']
    return [f'up to {day.busiest} a day', *day.parts]


def district_cell(figs: list) -> list[str]:
    return day_lines(day_figure(figs))


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
    # Large users are left out of the figures (rule A, 2026-11-10), so coverage is judged against the rest: counting
    # them would call a district's PO boxes postcodes outside the covered councils.
    homes = live - large
    if measured > homes:
        raise SystemExit(f"{f['district']}: {measured} measured, {homes} live small users in NSPL: not the averages' edition")
    if measured < COVERED_FROM * homes:
        return f'{measured} of {homes} postcodes in the covered councils (< {COVERED_FROM:.0%})'
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
        days = [(label, info['share_pct'][kind], day_figure([by_pc[pc][col[kind]] for pc in by_pc]))
                for kind, label in order]
        tables.append({
            'code': code, 'name': names.get(code, code), 'period': period(info['months']),
            'columns': [(label, f"{info['share_pct'][kind]}% of days") for kind, label in order],
            # Each cell a list of band phrases, one line each, so a narrow column never breaks "at 10 to 99".
            'rows': [(sector, len(pcs), [reading([by_pc[pc][col[kind]] for pc in pcs], sector_parts,
                                                 ['not measured']) for kind, _ in order])
                     for sector, pcs in sectors.items()],
            'district_cells': [day_lines(day) for _, _, day in days],
            'days': days,
        })
    measured = len(f['postcodes']) + len(f['none'])
    live, large = totals
    # The note explains EDGE only where a reading says it: a range inside one band reads as that band.
    edges = any(EDGE in text for t in tables for text in [*(p for _, _, day in t['days'] for p in day.parts),
                                                            *(p for row in t['rows'] for c in row[2] for p in c)])
    return {
        'district': name, 'slug': name.lower(), 'city': ctx['city'],
        'city_label': area.CITY_LABEL.get(ctx['city'], ctx['city'].title()),
        'councils': councils(ctx['lads']),
        'measured': measured, 'live': live - large, 'large': large,  # 'live' leaves out the large users, as the figures do
        'periods': sorted({t['period'] for t in tables}),
        'tables': tables, 'also': also,
        'edge': edges, 'approx': len(f['approx']), 'other': len(f['other']),
        'example': next(iter(sectors.values()))[0],
        'definition': f"{meta['definition']} {meta['direction_rule']} {meta['postcodes_rule']}",  # required: the builder writes it
        'credits': meta['credits'], 'licence': meta['licence'],
        'nearby': nearby,
    }


# ----------------------------------------------------------------- HTML

e = area.e


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def respond_line(packs: list[tuple[str, str]], until: str) -> str:
    """A district page's way into the consultation pack (2026-11-02, Bill: "make the links clear and easy to
    navigate"): until then the pack was reached only from the index. `packs` is [(council, its pack page)], the
    councils that list this district (council_index) and have a page in the pack; '' when there are none, or once the
    consultation has closed (build() passes none then). Neutral, like the pack: where to find the figures, no view."""
    if not packs:
        return ''
    links = listed([f'<a href="{e(path)}">the planes over {e(b)}</a>' for b, path in packs])
    return (f"<p class=\"respond\">For Heathrow's expansion consultation, open until {e(day_words(until))}: "
            f'{links}, council by council.</p>\n')


def render(m: dict, packs: list[tuple[str, str]] = (), until: str = '') -> str:
    d = m['district']
    council_names = [b for _, b, _ in m['councils']]
    where = listed(council_names)
    measured = (f"All {m['live']:,} of its postcodes measured" if m['measured'] == m['live']
                else f"{m['measured']:,} of its {m['live']:,} postcodes measured, the ones in {where}")
    if m['large']:  # said, never silent: the left-out post boxes are not postcodes we failed to measure
        measured += (' (1 PO box or other large-user postcode left out)' if m['large'] == 1
                     else f" ({m['large']:,} PO boxes and other large-user postcodes left out)")
    airports = listed([t['name'] for t in m['tables']])
    # "Heathrow and London City fly", "Heathrow flies" (2026-11-11: 62 two-airport descriptions said "flies").
    fly = 'fly' if len(m['tables']) > 1 else 'flies'
    sections = []
    for t in m['tables']:
        overall = '\n'.join(day_html(*day) for day in t['days'])
        head = ''.join(f'<th scope="col">{e(label)}<span class="note">{e(share)}</span></th>'
                       for label, share in t['columns'])
        rows = '\n'.join(f'<tr><th scope="row">{e(sector)}<span class="note">{n} postcode{"s" if n != 1 else ""}'
                         f'</span></th>' + ''.join(f'<td>{cell_html(c)}</td>' for c in cells) + '</tr>'
                         for sector, n, cells in t['rows'])
        sections.append(
            f'<h2 id="{e(t["code"].lower())}">From {e(t["name"])}</h2>\n'
            f'<p>Planes land and take off into the wind, so the weather decides which way {e(t["name"])} flies, '
            f'and that decides how many pass over {e(d)}. Across its postcodes, {e(t["period"])}:</p>\n'
            f'<ul class="overall">\n{overall}\n</ul>\n'
            f'<p class="note-p">{e(BANDS_SAID)} {band_key(bands_in(c for row in t["rows"] for c in row[2]))}</p>\n'
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
    respond = respond_line(list(packs), until)
    return PAGE.format(
        extra_style='\n  .respond { font-weight:600; }' if respond else '',
        respond=respond,
        title=e(area.page_title(f'Planes overhead in {d}: flight paths over {council_names[0]}',
                                f'Planes overhead in {d}, {council_names[0]}', f'Planes overhead in {d}')),
        description=e(area.fit(
            f'How many planes pass over {d} ({where}) on a day {airports} {fly} west, east or both ways, '
            f'postcode sector by sector. Counted from flight tracking, {first_period}.',
            f'How many planes pass over {d} ({where}) on a day {airports} {fly} west, east or both ways, '
            f'sector by sector, {first_period}.',
            f'How many planes pass over {d} ({where}) on a day {airports} {fly} west, east or both ways.',
            f'Planes over {d} on a day {airports} {fly} west, east or both ways.',
        )),
        canonical=f'{area.SITE}{URL_ROOT}{m["slug"]}/',
        crumbs_ld=area.breadcrumb_ld([('Sky Score', '/'), ('Planes overhead', URL_ROOT),
                                      (m['district'], f'{URL_ROOT}{m["slug"]}/')]),
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
    """ + area.PALETTE_LIGHT + """ --band0:#d6d3d1; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:0; font-family:'Inter',system-ui,sans-serif; color:var(--dark); background:var(--bg); line-height:1.6; }}
  a:focus-visible, input:focus-visible, button:focus-visible {{ outline:3px solid var(--focus); outline-offset:2px; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:24px clamp(16px, 4vw, 48px) 64px; }}
  a {{ color:var(--orange-ink); }}
  nav.crumbs {{ font-size:12px; color:var(--mid); margin-bottom:20px; }}
  h1 {{ font-family:var(--font-display); font-weight:700; font-size:clamp(30px, 4.4vw, 44px); line-height:1.12; letter-spacing:-0.02em; margin:0 0 10px; }}
  .sub {{ color:var(--mid); font-size:16px; margin:0 0 20px; max-width:66ch; }}
  .check {{ margin:0 0 28px; padding:16px 20px; background:var(--paper); border:1px solid var(--line); border-radius:18px; }}
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
  /* The band bar (2026-11-03): each band's width its count of postcodes, 2 px apart, the map layer's colours. */
  .bands {{ display:flex; gap:2px; height:8px; max-width:9em; margin:5px 0 1px; border-radius:4px; overflow:hidden; }}
  .bands i {{ display:block; flex:0 1 0; min-width:3px; }}
  .b100 {{ background:""" + BAND_COLOURS['at 100+'] + """; }}
  .b10 {{ background:""" + BAND_COLOURS['at 10 to 99'] + """; }}
  .bedge {{ background:repeating-linear-gradient(135deg, """ + BAND_COLOURS['at 10 to 99'] + """ 0 2px, var(--band0) 2px 4px); }}
  .b0 {{ background:var(--band0); }}
  .key {{ display:inline-flex; flex-wrap:wrap; gap:2px 12px; vertical-align:middle; }}
  .key span {{ display:inline-flex; align-items:center; gap:5px; white-space:nowrap; }}
  .key i {{ display:inline-block; width:14px; height:8px; border-radius:2px; }}
  .note {{ display:block; color:var(--mid); font-size:12px; font-weight:400; }}  /* 12px like the area pages' notes (audit 2026-11-01) */
  .note-p {{ color:var(--mid); font-size:13px; }}
  .tw {{ overflow-x:auto; }}
  .visually-hidden {{ position:absolute; width:1px; height:1px; padding:0;
    margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }}
  h2 {{ font-family:var(--font-display); font-size:22px; font-weight:600; letter-spacing:-0.01em; margin:36px 0 8px; }}
  /* THE MAIN FINDING FIRST (Bill's pick, 2026-11-04: Stitch's layout): how many pass depends on which way the airport
     flies, so each kind of day is one column, "Up to N" the largest figure on the page, its postcodes as one bar. */
  ul.overall {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:24px 40px; list-style:none; margin:20px 0 24px; padding:0; }}
  ul.overall .way {{ margin:0; font-size:14px; color:var(--mid); }}
  ul.overall .big {{ margin:6px 0 0; font-family:var(--font-display); font-size:clamp(32px, 4vw, 44px); font-weight:700; line-height:1.05; letter-spacing:-0.03em; }}
  ul.overall .aday {{ margin:0 0 10px; font-size:14px; color:var(--mid); }}
  ul.overall .of-all {{ margin:0 0 4px; font-size:13px; color:var(--mid); }}
  ul.overall .bands {{ max-width:none; margin:0 0 8px; }}
  dl.counts {{ display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:2px 12px; margin:0; font-size:13px; color:var(--mid); }}
  dl.counts dt {{ display:flex; align-items:center; gap:6px; }}
  dl.counts dt i {{ display:inline-block; width:11px; height:11px; border-radius:2px; flex:none; }}
  dl.counts dd {{ margin:0; font-family:var(--font-mono); font-size:12.5px; font-weight:500; color:var(--dark); text-align:right; }}
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
  .site-top .site-nav a[aria-current] {{ text-decoration: underline; text-decoration-color: var(--focus); text-decoration-thickness: 3px; text-underline-offset: 7px; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ """ + area.PALETTE_DARK + """ --band0:#4a4a48; }}
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

# The index and the consultation pack only (2026-11-01): kept out of STYLE so the district pages stay
# byte-identical (their sitemap dates are the day their CONTENT changed). A format() value: single braces.
EXTRA_STYLE = """
  /* The index (2026-11-01): each council's districts on one line under it, links 24 px or more (WCAG 2.5.8). */
  .jump { margin:0 0 8px; }
  .jump a { display:inline-block; padding:2px 0; margin:0 12px 4px 0; }
  ul.councils { list-style:none; margin:0; padding:0; }
  ul.councils li { padding:8px 0; border-bottom:1px solid var(--line); }
  ul.councils strong { margin-right:8px; }
  ul.councils a { display:inline-block; min-width:24px; padding:2px 0; margin:0 10px 0 0; }
  /* The consultation pack (2026-11-01): its figures for the borough, and a page that prints as a handout. */
  dl.facts { margin:0 0 12px; }
  dl.facts div { padding:8px 0; border-bottom:1px solid var(--line); }
  dl.facts dt { font-weight:600; }
  dl.facts dd { margin:0; }
  .respond { font-weight:600; }
  /* A district's busiest figure heads each cell and may wrap: four columns must fit a phone's 350 px. */
  td span.top { white-space:normal; font-weight:600; }
  @media print {
    .site-top, footer, nav.crumbs, .jump { display:none; }
    .wrap { max-width:none; padding:0; }
    .tw { overflow:visible; }
  }
  @media (max-width: 680px) {
    /* The consultation pack's table counts WHOLE districts (4-digit counts): four columns overflowed 350 px on 19
       of 32 pages (2026-11-01). On a phone each district stacks: its name, then each kind of day as a labelled line.
       Its ARIA roles keep it a table to a screen reader once display stops being table's own. */
    table.pack, table.pack tbody, table.pack tr, table.pack th[scope=row], table.pack td { display:block; }
    table.pack thead { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); }
    table.pack tr { padding:8px 0; border-bottom:1px solid var(--line); }
    table.pack th[scope=row], table.pack td { border:0; padding:2px 0; }
    table.pack th[scope=row] .note { display:inline; margin-left:8px; }
    table.pack td::before { content:attr(data-label); display:block; color:var(--mid); }
    table.pack td span { display:inline; white-space:nowrap; }  /* each band whole, the busiest too */
    table.pack td span + span::before { content:', '; white-space:normal; }  /* the line breaks at a comma */
    /* The band bar ends the text's own line (2026-11-03): under it, it made every district a line longer. */
    table.pack td .bands { display:inline-flex; width:5.5em; margin:0 0 0 8px; vertical-align:middle; }
  }
"""

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<meta name="description" content="{description}" />
<link rel="canonical" href="{canonical}" />
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{description}" />
<meta property="og:url" content="{canonical}" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="Sky Score" />
<meta name="twitter:card" content="summary" />
<link rel="icon" href="/favicon.ico" sizes="32x32" />
<link rel="icon" href="/icons/favicon.svg" type="image/svg+xml" />
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
<link rel="stylesheet" href="/fonts/fonts.css" />
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: https://cubitt33.goatcounter.com; connect-src https://cubitt33.goatcounter.com; base-uri 'self'; form-action 'self';" />
<style>""" + STYLE + """{extra_style}</style>
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
{crumbs_ld}
<main data-district="{district}">
<h1>Planes overhead in {district}</h1>
<p class="sub">{where}, {city_label}. {measured}, {period}.</p>
{respond}
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
{crumbs_ld}
<main>
<h1>Planes overhead, district by district</h1>
<p class="sub">How many planes pass over {count} postcode districts, on a day each airport flies west, east or both ways, measured from flight tracking, {period}. Districts where no postcode sees {page_from} a day are left out.</p>

<form class="check" action="/" method="get">
<label for="postcode">See the figures for your postcode</label>
<div class="row"><input id="postcode" name="postcode" type="text" autocomplete="postal-code" autocapitalize="characters" spellcheck="false" maxlength="8" required placeholder="TW9 3PZ" /><button type="submit">Check</button></div>
</form>

<nav class="jump" aria-label="City regions on this page">{jump}</nav>
{pack}<p class="note-p">Each council lists the districts where it holds a tenth or more of the postcodes, so a district on a boundary is under each of its councils.</p>
{body}
</main>
""" + FOOT


def index_regions(models: list[dict], index: dict) -> dict[str, list[tuple[str, list[str]]]]:
    """{city region's label: [(council, [its districts with a page, postcode order])]}, regions and councils by name.

    The councils are council_index()'s, the area pages' own rule (LINK_FROM), so the index and the area pages list a
    district under the same councils, and a district on a boundary appears under each. Every district with a page
    must appear at least once, and nothing without one: either way the build stops, never a page that drops one.
    """
    with_page = {m['district'] for m in models}
    listed_ = {d for ds in index['councils'].values() for d in ds}
    if missing := sorted(with_page - listed_, key=pc_key):
        raise ValueError(f'districts with a page under no council: {missing}')
    if extra := sorted(listed_ - with_page, key=pc_key):
        raise ValueError(f'councils list districts with no page: {extra}')
    regions: dict[str, list[tuple[str, list[str]]]] = {}
    for lad, districts in index['councils'].items():
        city, borough = area.app.LAD_TO_BOROUGH[lad]
        regions.setdefault(area.CITY_LABEL.get(city, city.title()), []).append((borough, districts))
    return {label: sorted(regions[label]) for label in sorted(regions)}


def render_index(models: list[dict], index: dict, pack: bool = False) -> str:
    """The index: a postcode box, a jump list of city regions, then each region's councils and their districts.

    Until 2026-11-01 it was one line per district with its councils beside it: 16.5 screens on a phone (site audit,
    2026-11-01). Grouped under the councils, every link stays (search engines read them) in far fewer screens.
    """
    regions = index_regions(models, index)
    jump = ' '.join(f'<a href="#{area.slug(label)}">{e(label)}</a>' for label in regions)
    body = []
    for label, councils_ in regions.items():
        items = '\n'.join(f'<li><strong>{e(borough)}</strong> '
                          + ' '.join(f'<a href="{URL_ROOT}{e(d.lower())}/">{e(d)}</a>' for d in districts) + '</li>'
                          for borough, districts in councils_)
        body.append(f'<h2 id="{area.slug(label)}">{e(label)}</h2>\n<ul class="councils">\n{items}\n</ul>')
    periods = sorted({p for m in models for p in m['periods']})
    return INDEX.format(extra_style=EXTRA_STYLE, title=e('Planes overhead, district by district | Sky Score'),
                        description=e(f'How many planes pass over {len(models)} postcode districts, by the way '
                                      'each airport flies. Counted from flight tracking.'),
                        canonical=f'{area.SITE}{URL_ROOT}', count=len(models),
                        crumbs_ld=area.breadcrumb_ld([('Sky Score', '/'), ('Planes overhead', URL_ROOT)]), period=e('; '.join(periods)),
                        page_from=PAGE_FROM, jump=jump, body='\n'.join(body),
                        pack=('<p class="respond"><a href="/planes-overhead/heathrow-consultation/">For Heathrow\'s '
                              'expansion consultation: the planes from Heathrow, council by council</a></p>\n'
                              if pack else ''))


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


# ----------------------------------------------------------------- the consultation pack (2026-11-01)
#
# Heathrow's expansion consultation (open to 22 December 2026). The marketing plan's first technique: one page per
# council, the same baseline for everyone responding, whatever their view (neutral: being seen on one side costs the
# neutrality councils, lenders and journalists buy). Every council with a district page that counts Heathrow's planes
# gets one, by that rule, not a list: Heathrow's approaches cross most of London (32 councils on 1 Nov).
# - The link and its closing date are READ from js/street_report.mjs HAVE_YOUR_SAY (the one holder of "Have your say"
#   links, verified live); no entry with an `until`, no pack.
# - The planes figures are the district pages' own, from the same files (district_cell: day_lines's words);
#   the borough's noise, air and flood are its area page's own (build_area_pages.gather), with that page's sources.
# - The page says "open until" while it is and "closed on" after: built on 23 December it differs, so --check (a
#   blocking preflight stage) reds until --write, and planes-pages-deploy ships the closed wording. Never a 404 for a
#   link someone shared.
# - It shows today's flights on today's routes: never a third runway's routes (none is drawn or guessed anywhere).

PACK_DIR = 'heathrow-consultation'
PACK_AIRPORT = 'LHR'
PACK_HUB_PATH = f'planes-overhead/{PACK_DIR}/index.html'
# The area page's figures the pack repeats, each with the source lines (by their opening words) it credits.
PACK_FACTS = (('Aircraft noise band', ('Aviation noise context', 'Flight routes')),
              ('Road noise', ('Road noise',)),
              ('Air quality', ('Air quality',)),
              ('Flood risk', ('Flood risk',)))


def consultation(src: Path = STREET_REPORT, airport: str = PACK_AIRPORT) -> dict | None:
    """{'href', 'until'} of the airport's "Have your say" link that carries an `until`, read from the street
    report's HAVE_YOUR_SAY; None when it has none (then no pack is built)."""
    block = re.search(rf'^\s+{airport}: \[\n(.*?)^\s+\],$', src.read_text(encoding='utf-8'), re.M | re.S)
    if not block:
        raise SystemExit(f'{src.name}: HAVE_YOUR_SAY.{airport} not found')
    found = re.search(r"href: '(https://[^']+)', until: '(\d{4}-\d{2}-\d{2})'", block.group(1))
    return {'href': found.group(1), 'until': found.group(2)} if found else None


def day_words(iso: str) -> str:
    """'22 December 2026' from '2026-12-22'."""
    y, m, d = (int(x) for x in iso.split('-'))
    return f'{d} {MONTHS[m - 1]} {y}'


def pack_councils(models: list[dict], index: dict, airport: str = PACK_AIRPORT) -> dict[str, list[dict]]:
    """{ONS code: [its districts' models whose page has a table for `airport`]}, councils with one or more only.

    The districts are council_index()'s (a tenth or more of their postcodes in the council), so the pack and the area
    pages list the same districts under a council."""
    by_district = {m['district']: m for m in models}
    out = {}
    for lad, districts in index['councils'].items():
        counted = [by_district[d] for d in districts if any(t['code'] == airport for t in by_district[d]['tables'])]
        if counted:
            out[lad] = counted
    return out


PACK_LEAD = ('Whatever your view, these are the figures for {borough} now: the planes from Heathrow counted '
             "over each of its postcode districts, and the borough's noise, air and flood figures from official data. "
             "They are today's flights on today's routes, not those of a third runway. Sky Score takes no side in "
             'the consultation.')
CELLS_SAID = ('Each cell gives the most planes over any one postcode of the district on that kind of day, and '
              'counts its postcodes in the busiest band reached; the bar splits all of them by how many planes pass '
              "over them a day. Each district's own page goes sector by sector.")

PACK = HEAD + """<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Sky Score</a> &rsaquo; <a href="/planes-overhead/">Planes overhead</a> &rsaquo; <a href="/planes-overhead/heathrow-consultation/">Heathrow consultation</a> &rsaquo; {borough}</nav>
{crumbs_ld}
<main>
<h1>Planes over {borough} today</h1>
<p class="sub">For Heathrow's expansion consultation, {state}.</p>
<p>{lead}</p>
<p class="respond"><a href="{href}">Heathrow's consultation page</a>: how to respond, and Heathrow's own documents.</p>

<h2>Planes from Heathrow, district by district</h2>
<p>Planes land and take off into the wind, so the weather decides which way Heathrow flies, and that decides how many pass over each place. Counted over each postcode, {period}.</p>
<p class="note-p">{cells_said} {key}</p>
<div class="tw">
<!-- [html-validate-disable-block no-redundant-role: on a phone this table is display:block, which drops its table semantics in Safari; the roles keep them] -->
<table class="pack" role="table">
<caption class="visually-hidden">Planes overhead from Heathrow in each postcode district of {borough}, by the way Heathrow flies</caption>
<thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">District</th>{head}</tr></thead>
<tbody role="rowgroup">
{rows}
</tbody>
</table>
</div>
{notes}
<p class="note-p">Each district's own page splits it by postcode sector and counts every airport over it.</p>

<h2>Noise, air and flood in {borough}</h2>
<dl class="facts">
{facts}
</dl>
{area_link}

<h2>What counts as overhead</h2>
<p>{definition}</p>

<h2>Where these figures come from</h2>
<p class="sources">{counted} {credits}. Licence: {licence}.</p>
{area_sources}
<p class="sources"><a href="/planes-overhead/heathrow-consultation/">Every council Heathrow's flights cross</a></p>
</main>
""" + FOOT

PACK_HUB = HEAD + """<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Sky Score</a> &rsaquo; <a href="/planes-overhead/">Planes overhead</a> &rsaquo; Heathrow consultation</nav>
{crumbs_ld}
<main>
<h1>Planes from Heathrow, council by council</h1>
<p class="sub">For Heathrow's expansion consultation, {state}.</p>
<p>Whatever your view, each page below sets out the figures for one council now: the planes from Heathrow counted over each of its postcode districts, and the borough's noise, air and flood figures from official data. They are today's flights on today's routes, not those of a third runway. Sky Score takes no side in the consultation.</p>
<p class="respond"><a href="{href}">Heathrow's consultation page</a>: how to respond, and Heathrow's own documents.</p>
<h2>The {count} councils Heathrow's flights cross</h2>
<p class="note-p">A council is here when one or more of its postcode districts has a planes overhead page counting Heathrow's planes, {period}.</p>
<ul class="councils">
{items}
</ul>
</main>
""" + FOOT


def pack_state(until: str, today: str) -> str:
    return f'open until {day_words(until)}' if today <= until else f'which closed on {day_words(until)}'


def render_pack(lad: str, ms: list[dict], c: dict, today: str, facts: dict | None) -> str:
    """One council's page. `facts` is build_area_pages.gather()'s for the borough (None: none published)."""
    city, borough = area.app.LAD_TO_BOROUGH[lad]
    tables = [next(t for t in m['tables'] if t['code'] == PACK_AIRPORT) for m in ms]
    columns = tables[0]['columns']
    head = ''.join(f'<th scope="col" role="columnheader">{e(label)}<span class="note">{e(share)}</span></th>'
                   for label, share in columns)
    rows = '\n'.join(
        f'<tr role="row"><th scope="row" role="rowheader"><a href="{URL_ROOT}{e(m["slug"])}/">{e(m["district"])}</a>'
        f'<span class="note">{m["measured"]:,} postcode{"s" if m["measured"] != 1 else ""}</span></th>'
        + ''.join(f'<td role="cell" data-label="{e(label)}, {e(share)}">{cell_html(cell, top=True)}</td>'
                  for (label, share), cell in zip(columns, t['district_cells'], strict=True))
        + '</tr>'
        for m, t in zip(ms, tables, strict=True))
    notes = ''
    if any(EDGE in p for t in tables for cell in t['district_cells'] for p in cell):
        notes = ('<p class="note-p">On an edge: the postcode is on the edge of a flight path, where a few metres decide '
                 'whether a plane counts as overhead, and the fewest and the most within 100 m of it fall in different '
                 'bands.</p>')
    shown = {f['label']: f for f in (facts or {}).get('facts', [])}
    items, credited = [], []
    for label, source_heads in PACK_FACTS:
        f = shown.get(label)
        if f is None:  # absence is said, never shown as a reading
            items.append(f'<div><dt>{e(label)}</dt><dd>Not published for {e(borough)}</dd></div>')
            continue
        note = f'<span class="note">{e(f["note"])}</span>' if f.get('note') else ''
        items.append(f'<div><dt>{e(label)}</dt><dd>{e(f["value"])}{note}</dd></div>')
        credited += [s for s in (facts or {}).get('sources', []) if s.startswith(source_heads) and s not in credited]
    area_path = f'/area/{area.slug(city)}/{area.slug(borough)}/'
    has_area = (REPO / area_path.strip('/') / 'index.html').exists()
    return PACK.format(
        extra_style=EXTRA_STYLE,
        title=e(area.page_title(f'Planes over {borough} today: Heathrow consultation',
                                f'Planes over {borough}: Heathrow consultation')),
        description=e(area.fit(
            f'The planes from Heathrow over each postcode district in {borough}, with its official noise, '
            f'air and flood figures: the same for anyone responding to Heathrow\'s expansion '
            f'consultation. Counted from flight tracking, {tables[0]["period"]}.',
            f'The planes from Heathrow over each postcode district in {borough}, with its noise, air and flood '
            f'figures, for anyone responding to Heathrow\'s consultation.',
            f'Heathrow\'s planes over each postcode district in {borough}, with its noise, air and flood figures.',
        )),
        canonical=f'{area.SITE}{URL_ROOT}{PACK_DIR}/{area.slug(borough)}/',
        crumbs_ld=area.breadcrumb_ld([('Sky Score', '/'), ('Planes overhead', URL_ROOT),
                                      ('Heathrow consultation', f'{URL_ROOT}{PACK_DIR}/'),
                                      (borough, f'{URL_ROOT}{PACK_DIR}/{area.slug(borough)}/')]),
        borough=e(borough), state=e(pack_state(c['until'], today)), lead=e(PACK_LEAD.format(borough=borough)),
        href=e(c['href']), period=e(tables[0]['period']), cells_said=e(CELLS_SAID), key=band_key(bands_in(cell for t in tables for cell in t['district_cells'])), head=head, rows=rows,
        notes=notes, facts='\n'.join(items),
        area_link=(f'<p><a href="{e(area_path)}">{e(borough)}: every figure we publish, with its score</a></p>'
                   if has_area else ''),
        definition=e(ms[0]['definition']),
        counted=e("Counted from community flight tracking, checked against the CAA's monthly totals for Heathrow."),
        credits=e('; '.join(ms[0]['credits'])), licence=e(ms[0]['licence']),
        area_sources=''.join(f'<p class="sources">{e(s)}</p>' for s in credited),
    )


def render_pack_hub(packs: dict[str, list[dict]], c: dict, today: str) -> str:
    entries = sorted((area.app.LAD_TO_BOROUGH[lad][1], ms) for lad, ms in packs.items())
    items = '\n'.join(
        f'<li><strong><a href="{URL_ROOT}{PACK_DIR}/{e(area.slug(borough))}/">{e(borough)}</a></strong> '
        f'<span class="note-p">{e(", ".join(m["district"] for m in ms))}</span></li>'
        for borough, ms in entries)
    periods = sorted({t['period'] for ms in packs.values() for m in ms for t in m['tables'] if t['code'] == PACK_AIRPORT})
    return PACK_HUB.format(
        extra_style=EXTRA_STYLE,
        title=e(area.page_title("Heathrow consultation: the planes over each council")),
        description=e(area.fit(
            f'The planes from Heathrow over each of the {len(entries)} councils its flights cross, district '
            f"by district, with official noise, air and flood figures, for Heathrow's expansion consultation.",
            f'The planes from Heathrow over each of the {len(entries)} councils its flights cross, district by district, '
            f"with noise, air and flood figures, for Heathrow's consultation.",
        )),
        canonical=f'{area.SITE}{URL_ROOT}{PACK_DIR}/', state=e(pack_state(c['until'], today)), href=e(c['href']),
        crumbs_ld=area.breadcrumb_ld([('Sky Score', '/'), ('Planes overhead', URL_ROOT),
                                      ('Heathrow consultation', f'{URL_ROOT}{PACK_DIR}/')]),
        count=len(entries), period=e('; '.join(periods)), items=items)


def pack_page_path(lad: str) -> str:
    """A council's page in the pack, as a site path."""
    return f'{URL_ROOT}{PACK_DIR}/{area.slug(area.app.LAD_TO_BOROUGH[lad][1])}/'


def district_packs(district: str, packs: dict[str, list[dict]], c: dict | None, today: str):
    """(packs, until) for render(): the pack pages of the councils listing this district, while the consultation is
    open; ([], '') otherwise. `packs` is pack_councils()'s, so a district page never links a pack page that is not
    built, and one council with two ONS codes is linked once."""
    if c is None or today > c['until']:
        return [], ''
    seen: dict[str, str] = {}
    for lad, ms in packs.items():
        if any(x['district'] == district for x in ms):
            seen.setdefault(pack_page_path(lad), area.app.LAD_TO_BOROUGH[lad][1])
    return ([(b, path) for path, b in seen.items()], c['until']) if seen else ([], '')


def consultation_entry(index: dict, pages: dict, c: dict | None) -> dict | None:
    """What the area pages and the front page read about the pack (2026-11-02), written into the council index: its
    airport, its closing day, its hub and each council's page in it. From the pages this run WRITES, so nothing links
    a pack page that is not built; None when no pack is built."""
    if c is None or PACK_HUB_PATH not in pages:
        return None
    councils = {lad: pack_page_path(lad) for lad in index['councils']
                if pack_page_path(lad).strip('/') + '/index.html' in pages}
    return {'airport': PACK_AIRPORT, 'until': c['until'], 'hub': f'{URL_ROOT}{PACK_DIR}/', 'councils': councils}


def pack_pages(models: list[dict], index: dict, today: str, c: dict | None, gather=None) -> dict[str, str]:
    """{repo path: page} for the hub and each council's page; none without a dated consultation link."""
    if c is None:
        return {}
    gather = gather or area.gather
    packs = pack_councils(models, index)
    pages = {}
    for lad, ms in packs.items():
        city, borough = area.app.LAD_TO_BOROUGH[lad]
        pages[f'planes-overhead/{PACK_DIR}/{area.slug(borough)}/index.html'] = render_pack(
            lad, ms, c, today, gather(city, borough))
    if pages:
        pages[PACK_HUB_PATH] = render_pack_hub(packs, c, today)
    return pages


# ----------------------------------------------------------------- build, write, check

INDEX_PATH = 'planes-overhead/index.html'


def is_district_page(path: str) -> bool:
    """planes-overhead/<district>/index.html: not the index, nor anything under the consultation pack."""
    parts = path.split('/')
    return len(parts) == 3 and parts[1] != PACK_DIR and path != INDEX_PATH


def build(meta, files, ctx, totals, names, order, today: str | None = None):
    """({repo path: page text}, {district: reason it has no page}) from the inputs."""
    today = today or datetime.now(UTC).strftime('%Y-%m-%d')
    reasons = {d: verdict(f, totals[d]) for d, f in files.items()}
    with_page = sorted((d for d, why in reasons.items() if why is None), key=pc_key)
    at = {d: ctx[d]['at'] for d in with_page}
    models = [model(d, files[d], meta, ctx[d], totals[d], names, nearest(d, at, with_page), order)
              for d in with_page]
    index = council_index(with_page, ctx)
    c = consultation()
    by_council = pack_councils(models, index) if c else {}
    pages = {f'planes-overhead/{m["slug"]}/index.html': render(m, *district_packs(m['district'], by_council, c, today))
             for m in models}
    packs = pack_pages(models, index, today, c)
    pages[INDEX_PATH] = render_index(models, index, pack=PACK_HUB_PATH in packs)
    return pages | packs, {d: why for d, why in reasons.items() if why}


COUNCILS = REPO / 'data' / 'planes-districts-by-council.json'


def council_index(with_page: list[str], ctx: dict) -> dict:
    """The area pages' "Planes overhead" links: {ONS council code: [districts with a page, postcode order]}.

    A district is listed under every council holding LINK_FROM or more of its measured postcodes. Keyed on the ONS
    code, never a name (names have failed this repo five times). It holds names only, no figure, so it is TRACKED:
    the area pages are tracked and must build on a clone without the tracks, and the list of pages is public already
    (sitemap-planes.xml). scripts/build_area_pages.py reads it; its --check reds an area page that lags it.
    """
    by: dict[str, list[str]] = {}
    for d in sorted(with_page, key=pc_key):
        lads = ctx[d]['lads']
        total = sum(lads.values())
        for lad, n in sorted(lads.items()):
            if n >= LINK_FROM * total:
                by.setdefault(lad, []).append(d)
    return {
        'about': ('Written by scripts/build_planes_pages.py --write, read by scripts/build_area_pages.py and the '
                  "front page's planes answer (js/planes.mjs): the postcode districts with a /planes-overhead/ page, "
                  'under each council (ONS code) holding link_from or more of their measured postcodes, and, while '
                  "Heathrow's consultation pack is built, its closing day and each council's page in it. "
                  'Never edit by hand.'),
        'link_from': LINK_FROM,
        'councils': {lad: by[lad] for lad in sorted(by)},
    }


def councils_text(index: dict) -> str:
    return json.dumps(index, indent=1) + '\n'


def check_councils(index: dict, path: Path = COUNCILS) -> list[str]:
    """[] when the tracked file says what this build would write (read as JSON, so a CRLF checkout is no change)."""
    try:
        recorded = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return [f'missing: data/{path.name}']
    return [] if recorded == index else [f'{path.name} does not match the built pages: run --write, then '
                                         'scripts/build_area_pages.py --write (the area pages link from it)']


# ----------------------------------------------------------------- the front page's dark band (front-page-v3, 2026-11-03)
#
# Bill's mock v8 (version 12): one DARK band on the front page for Heathrow's consultation, generated, so it switches
# itself off. Written between the PLANES-BAND markers in home/index.html from the council index's `consultation`
# entry (consultation_entry(): its closing day, the hub and each council's page in the pack), never typed: while the
# consultation is open it names the councils and links each one's pack page; from the day after `until` it becomes the
# planes overhead band (the district pages), so --check reds on 23 December until --write re-says it, like the pack's
# own "closed on". Neutral, in the pack's words (PACK_LEAD): today's flights, no side taken. NO planes figure: the
# front page says how often planes pass only through js/planes.mjs (tests/test_public_wording.py FREQUENCY).
HOME = REPO / 'home' / 'index.html'
BAND_BEGIN = '<!-- PLANES-BAND:BEGIN (scripts/build_planes_pages.py --write; never edit by hand) -->'
BAND_END = '<!-- PLANES-BAND:END -->'
# The "New" pill above the question (front-page-v3 step 2): the band's way in. It points at the band, so it goes the day
# the band stops being the consultation's; after that the page holds the two markers and nothing between them.
PILL_BEGIN = '<!-- PLANES-PILL:BEGIN (scripts/build_planes_pages.py --write; never edit by hand) -->'
PILL_END = '<!-- PLANES-PILL:END -->'


def band_open(index: dict, today: str) -> dict | None:
    """The consultation entry while its pack is open on `today` (its last day included), else None."""
    c = (index or {}).get('consultation')
    if not c or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(c.get('until', ''))) or today > c['until'] or not c.get('councils'):
        return None
    return c


def home_band(index: dict, today: str) -> list[str]:
    """The band's lines, unindented: Heathrow's consultation while it is open, the planes overhead pages after."""
    c = band_open(index, today)
    if c is None:
        return [
            '<section class="band band-dark" id="planes-band" aria-labelledby="planes-band-h">',
            '  <div class="wrap">',
            '    <p class="eyebrow">Planes overhead</p>',
            '    <h2 id="planes-band-h">See the planes over your district.</h2>',
            "    <p class=\"lede\">How many planes pass over each postcode district on a day each airport flies west, east or both "
            "ways: counted from flight tracking, and checked against the CAA&#x27;s monthly totals.</p>",
            f'    <a class="pill" href="{URL_ROOT}">Find your district <i aria-hidden="true"></i></a>',
            '  </div>',
            '</section>',
        ]
    named = sorted((area.app.LAD_TO_BOROUGH[lad][1], path) for lad, path in c['councils'].items())
    n = len(named)
    return [
        '<section class="band band-dark" id="planes-band" aria-labelledby="planes-band-h">',
        '  <div class="wrap split">',
        '    <div>',
        "      <p class=\"eyebrow\">Heathrow&#x27;s consultation</p>",
        '      <h2 id="planes-band-h">See the planes over your council.</h2>',
        f"      <p class=\"lede\">Whatever your view, one page for each of the {n} councils Heathrow&#x27;s flights cross: the "
        "planes counted over each of its postcode districts, and its official noise, air and flood figures. Today&#x27;s "
        f"flights on today&#x27;s routes, not those of a third runway. The consultation is open until {e(day_words(c['until']))}.</p>",
        f'      <a class="pill" href="{e(c["hub"])}">Find your council <i aria-hidden="true"></i></a>',
        '    </div>',
        '    <div class="band-card">',
        f'      <h3>The {n} councils</h3>',
        '      <p>The same figures for anyone responding. Sky Score takes no side in the consultation.</p>',
        '      <ul>',
        *(f'        <li><a href="{e(path)}">{e(name)}</a></li>' for name, path in named),
        '      </ul>',
        '    </div>',
        '  </div>',
        '</section>',
    ]


def home_pill(index: dict, today: str) -> list[str]:
    """The "New" pill's line while the consultation is open, nothing after it."""
    if band_open(index, today) is None:
        return []
    return ['<a class="news" href="#planes-band"><b>New</b>Heathrow&rsquo;s consultation: the planes over your council '
            '<i aria-hidden="true">&rarr;</i></a>']


def band_held(page: str, begin: str = BAND_BEGIN, end: str = BAND_END) -> tuple[str, str] | None:
    """(the BEGIN marker's indentation, the text between the markers), or None unless each marker appears once."""
    if page.count(begin) != 1 or page.count(end) != 1:
        return None
    start = page.index(begin)
    indent = page[page.rfind('\n', 0, start) + 1:start]
    body_at = page.index('\n', start) + 1
    return indent, page[body_at:page.rfind('\n', 0, page.index(end)) + 1]


def band_text(index: dict, today: str, indent: str, lines=home_band) -> str:
    return ''.join(f'{indent}{line}\n' for line in lines(index, today))


# Each generated stretch of the front page: its name, its two markers and what it holds.
HOME_PARTS = (('planes band', BAND_BEGIN, BAND_END, home_band), ('"New" pill', PILL_BEGIN, PILL_END, home_pill))


def check_home(index: dict, today: str, path: Path = HOME) -> list[str]:
    """[] when the front page's band and pill are what the council index says on `today` (line endings aside)."""
    page = path.read_text(encoding='utf-8')
    problems = []
    for name, begin, end, lines in HOME_PARTS:
        held = band_held(page, begin, end)
        if held is None:
            problems.append(f"{path.name}: the {name}'s two markers must appear exactly once each")
            continue
        indent, body = held
        if body.replace('\r\n', '\n') != band_text(index, today, indent, lines):
            problems.append(f"{path.parent.name}/{path.name}: the {name} is not what {COUNCILS.name} says today "
                            '(the consultation opened or closed?): run --write, or --write --home')
    return problems


def write_home(index: dict, today: str, path: Path = HOME) -> bool:
    """Rewrite the band and the pill from the council index; True when the page changed."""
    raw = path.read_bytes().decode('utf-8')
    crlf = '\r\n' in raw
    page = raw.replace('\r\n', '\n')
    changed = False
    for name, begin, end, lines in HOME_PARTS:
        held = band_held(page, begin, end)
        if held is None:
            raise SystemExit(f"{path.name}: place the {name}'s two markers once each, then --write")
        indent, body = held
        want = band_text(index, today, indent, lines)
        if body == want:
            continue
        at = page.index('\n', page.index(begin)) + 1
        page = page[:at] + want + page[at + len(body):]
        changed = True
    if changed:
        path.write_bytes((page.replace('\n', '\r\n') if crlf else page).encode('utf-8'))
    return changed


def tracked_index(path: Path = COUNCILS) -> dict:
    """The council index as committed (the band's holder when the tracks are not on this machine)."""
    return json.loads(path.read_text(encoding='utf-8'))


NEEDS = (('data/planes/airports.json', 'scripts/build_planes_overhead.py --write'),
         ('data/adsb/postcode-averages.npz', 'scripts/adsb_postcode_averages.py'),
         ('data/nspl.csv', 'the NSPL roll (HANDOVER)'))


def missing_inputs(root: Path = REPO) -> list[str]:
    """The gitignored inputs not on this machine, each with what makes it (a clone without the tracks has none)."""
    return [f'{need} (made by {how})' for need, how in NEEDS if not (root / need).exists()]


def inputs(root: Path = REPO):
    """Everything a build reads that is not tracked; `root` is another clone with --inputs-from (read only)."""
    meta, files = read_planes(root / 'data' / 'planes')
    ctx = district_context(root / 'data' / 'adsb' / 'postcode-averages.npz')
    return meta, files, ctx, district_totals(files, root / 'data' / 'nspl.csv'), airport_names(), kinds()


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
    ap.add_argument('--home', action='store_true',
                    help="only the front page's planes band, from the committed council index (needs no tracks)")
    ap.add_argument('--inputs-from', type=Path, metavar='CLONE',
                    help='--check / --list only: read the untracked inputs AND the built pages from another clone of '
                         'this repo (a worktree without the tracks); never writes there')
    a = ap.parse_args()
    if not (a.write or a.check or a.list):
        ap.error('pass --write, --check or --list')
    today = datetime.now(UTC).strftime('%Y-%m-%d')
    if a.home:
        # The band reads only the committed index, so it can be written and checked on any clone.
        if a.list or a.inputs_from:
            ap.error('--home takes --write or --check only')
        index = tracked_index()
        if a.write:
            print(f"{'wrote' if write_home(index, today) else 'unchanged:'} the planes band in home/index.html")
        problems = check_home(index, today)
        print('\n'.join(problems) if problems else 'OK: the front page\'s planes band')
        return 1 if problems else 0
    if a.inputs_from and a.write:
        ap.error('--inputs-from reads another clone: it never writes (run --write there, or --write --home here)')
    root = (a.inputs_from or REPO).resolve()
    if missing := missing_inputs(root):
        # The front page's band needs no tracks, so it is checked even here: a band left open after the consultation
        # closes is a defect on any clone, never inconclusive.
        if a.check and (home := check_home(tracked_index(), today)):
            print('FAIL: ' + '; '.join(home))
            return 1
        # Unrunnable is not failed, and never a pass: preflight reads a leading INCONCLUSIVE and names the gate.
        # A deploy must not read it at all (--strict): it would upload whatever happens to be on disk.
        soft = a.check and not (a.write or a.list or a.strict)
        print(('INCONCLUSIVE: ' if soft else 'FAIL: ') + 'missing ' + '; '.join(missing)
              + ('' if soft else ' (the front page\'s band alone: --write --home)'))
        return 0 if soft else 1
    meta, files, ctx, totals, names, order = inputs(root)
    if a.list:
        for d in sorted(files, key=pc_key):
            print(f'  {d:6} {verdict(files[d], totals[d]) or "PAGE"}')
        if not (a.write or a.check):
            return 0
    pages, without = build(meta, files, ctx, totals, names, order)
    # From the pages this run WRITES (each at planes-overhead/<district, lower case>/), so an area page can never
    # link a district page that is not built, whatever build() comes to filter.
    districts = [path.split('/')[1].upper() for path in pages if is_district_page(path)]
    index = council_index(districts, ctx)
    if entry := consultation_entry(index, pages, consultation()):
        index['consultation'] = entry
    packs = sum(path.startswith(f'planes-overhead/{PACK_DIR}/') for path in pages)
    print(f'{len(districts)} district pages and the index; {len(without)} districts without a page; '
          f"{len(index['councils'])} councils link to them; {packs} consultation pack pages")
    if a.write:
        write(pages)
        COUNCILS.write_text(councils_text(index), encoding='utf-8', newline='\n')
        write_home(index, today)
        print(f'wrote {len(pages)} pages, {SITEMAP.name}, {COUNCILS.name} and the front page\'s planes band')
    if a.check:
        problems = check(pages, root) + check_councils(index) + check_home(index, today)
        print('\n'.join(problems) if problems else 'OK')
        if problems:
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
