#!/usr/bin/env python3
"""Generate one static, indexable page per borough, plus an index.

WHY THIS EXISTS
---------------
The sitemap listed eight URLs and every one of them was a product or marketing
page. The map is client-side, so a crawler fetching skyscore.co.uk gets a shell
and no scores - which means the organic surface was not weak, it was absent.
There was nothing for anyone to find and nothing for the badge (D2) to link
back to.

These pages are the content half. Each one is a real page about a real place,
carrying the numbers we already publish, rendered server-side at build time so
they exist without JavaScript.

WHAT IT WILL NOT DO
-------------------
It never invents a field. Every figure comes from resolve_query - the same
function /v1/score answers with - and anything absent is OMITTED rather than
defaulted. That is the rule the rest of this repo has paid to learn: a borough
with no flood reading gets no flood line, not a reassuring one.

It also refuses to write a page it could not populate. `--check` fails if any
page would carry fewer than MIN_FACTS real figures, because 99 thin pages is
worse for a domain than none: that is the shape search engines call doorway
pages, and it would put the site's whole reputation behind filler.

AFTER A DATA VINTAGE ROLL, RERUN THIS
-------------------------------------
The pages bake their scores, so a vintage roll silently puts 99 static pages out
of step with /v1/score. `tests/area-page-freshness.mjs` is a blocking gate that
compares the two and will go red until the pages are regenerated and redeployed.
The /area/ index bakes the same scores in its comparison tables (2026-10-25), so
`--check` also fails while the index on disk differs from what --write would write:

    python scripts/build_area_pages.py --write
    make area-deploy meta-deploy

USAGE
    python scripts/build_area_pages.py --write     # write area/ and sitemap
    python scripts/build_area_pages.py --check     # verify, write nothing
"""
from __future__ import annotations

import argparse
import functools
import html
import json
import re
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))

import app  # noqa: E402  pylint: disable=wrong-import-position

sys.path.insert(0, str(REPO / 'scripts'))
# The Bay Area's inputs in words, each with its source and year, and its US-scales line: ONE holder, read by the
# full map's card (through index.html's generated block), the front page's card and these pages (2026-11-07).
import build_bayarea_records as bay_records  # noqa: E402  pylint: disable=wrong-import-position

# The map's holder. Loaded eagerly and NOT guarded: if this file moves, the
# right outcome is a crash, not 99 quietly thinner pages.
_BOROUGH_EXTRA = json.loads(
    (REPO / 'data' / 'borough-extra.json').read_text(encoding='utf-8')
)

OUT = REPO / 'area'
SITE = 'https://skyscore.co.uk'
# A page below this many real figures is not worth publishing. Six is what the
# thinnest covered borough carries (score, four components, one price figure).
MIN_FACTS = 6

# Each city region's name is the API's (app.CITIES[...]['name']), the one the map and
# /v1/score already use. This was a second hand-written list until 2026-10-07, and two of
# its fourteen had drifted (website audit M3): 'Leicestershire' where everything else says
# Leicester, and 'Nottinghamshire', which claimed the whole county for a region that is the
# City of Nottingham with Broxtowe, Gedling and Rushcliffe, four of its eight authorities.
CITY_LABEL = {key: city['name'] for key, city in app.CITIES.items()}


def slug(text: str) -> str:
    """URL slug. Kept deliberately lossy-but-stable.

    A borough name is the only input, so collisions are checked by the caller
    rather than guarded against here - a silent collision would overwrite one
    borough's page with another's, which is the WA8 join defect in a new place.
    """
    s = re.sub(r"[^a-z0-9]+", '-', text.lower()).strip('-')
    return re.sub(r'-{2,}', '-', s)


def breadcrumb_ld(trail: list[tuple[str, str]]) -> str:
    """The page's breadcrumb for search engines (schema.org BreadcrumbList, 2026-11-02).

    `trail` is (name, path) from the front page down to the page itself. Every item but the last is a link the
    page's visible breadcrumb also shows, and the last is the page's own canonical address
    (tests/test_breadcrumb_ld.py holds both, on every built page). A city with no page of its own is left out
    rather than given an address it does not have. So the JSON cannot close its <script>, '</' is escaped."""
    items = [{'@type': 'ListItem', 'position': i, 'name': name, 'item': SITE + path}
             for i, (name, path) in enumerate(trail, 1)]
    body = json.dumps({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': items},
                      ensure_ascii=False, separators=(',', ':'))
    return '<script type="application/ld+json">' + body.replace('</', r'<\/') + '</script>'


def e(text) -> str:
    return html.escape(str(text), quote=True)


# THE PLANES OVERHEAD LINKS (2026-11-01). Each borough's page links the /planes-overhead/<district>/ pages of the
# postcode districts it covers, from the tracked index scripts/build_planes_pages.py writes (its council_index: a
# district holding a tenth or more of its measured postcodes in the council). Keyed on the ONS council code, never
# the name. Read, not guarded, like borough-extra.json: a missing index is a crash, not 102 pages quietly without
# links. Names only: an area page never says how often planes pass (tests/test_public_wording.py).
PLANES_BY_COUNCIL = REPO / 'data' / 'planes-districts-by-council.json'


@functools.cache
def _planes_index() -> dict:
    return json.loads(PLANES_BY_COUNCIL.read_text(encoding='utf-8'))


def _planes_by_council() -> dict[str, list[str]]:
    return _planes_index()['councils']


def consultation_line(city: str, borough: str, today: str | None = None) -> str:
    """The area page's way into Heathrow's consultation pack (2026-11-02, Bill: "make the links clear and easy to
    navigate"): a line straight to this council's own pack page, while the consultation is open; '' otherwise, or when
    the pack has no page for the council. Read from the index the planes builder writes (its `consultation` entry,
    from the pages it built), so an area page never links a pack page that is not there. Dated like the pack: after
    the closing day --check reds until --write drops the line. Names only, no figure (the wording gate)."""
    c = _planes_index().get('consultation')
    today = today or datetime.now(UTC).strftime('%Y-%m-%d')
    if not c or today > c['until']:
        return ''
    paths = {c['councils'][lad] for lad, where in app.LAD_TO_BOROUGH.items()
             if tuple(where) == (city, borough) and lad in c['councils']}
    if len(paths) != 1:
        return ''
    day = datetime.strptime(c['until'], '%Y-%m-%d')
    return (f"<p><strong>Heathrow's expansion consultation is open until {day.day} {day.strftime('%B')} {day.year}.</strong> "
            f'<a href="{e(paths.pop())}">The planes over {e(borough)} today, for the consultation</a>, district by '
            'district.</p>\n')


def _district_order(d: str):
    """Postcode order (TW2 before TW10), so a borough with two council codes is not ordered by app.py's dict."""
    m = re.match(r'([A-Z]+)(\d+)(.*)', d)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (d, 0, '')


def planes_links(city: str, borough: str) -> list[str]:
    """The districts this borough's page links, in postcode order; [] when none."""
    found = {d for lad, where in app.LAD_TO_BOROUGH.items() if tuple(where) == (city, borough)
             for d in _planes_by_council().get(lad, [])}
    return sorted(found, key=_district_order)


def planes_section(city: str, borough: str) -> str:
    """The page's "Planes overhead" block, or '' (no heading at all) when no district page covers the borough."""
    districts = planes_links(city, borough)
    if not districts:
        return ''
    links = ', '.join(f'<a href="/planes-overhead/{e(d.lower())}/">{e(d)}</a>' for d in districts)
    return ('<h2>Planes overhead</h2>\n'
            + consultation_line(city, borough)
            + f'<p>Planes overhead pages for the postcode districts covering {e(borough)}: {links}.</p>\n\n')


def fmt_price(value):
    return f'£{value:,.0f}' if isinstance(value, (int, float)) else None


def _painted_for(city, borough):
    """borough-extra.json's key for a borough is not always the Lambda's.

    THE ALIAS IS DECLARED IN FOUR OTHER PLACES AND WAS MISSING FROM THIS ONE
    (2026-08-31, audit I5). The Lambda keys `Barking and Dagenham`;
    borough-extra.json keys `Barking`. This did a raw `.get(borough)`, missed,
    and fell back to `{}` - so that borough's page silently lost **Road noise,
    Air quality and Flood risk**, three rows every other London page carries,
    while the data sat in the file under the other name.

    Nothing noticed because the remaining facts still cleared MIN_FACTS - the
    same "a defensive fallback turned a wrong key into a quietly worse product"
    shape the comment above records for `hasattr`.

    This is the SAME containment rule build_borough_bands.apply_to_extra and the
    frontend's getExtraData() already use, so all three resolve a borough the
    same way. Exact match first, so a longest-prefix collision cannot beat an
    exact one.
    """
    holder = _BOROUGH_EXTRA.get(city) or {}
    if borough in holder:
        return holder[borough]
    lower = borough.lower()
    for key, rec in holder.items():
        k = key.lower()
        if lower == k or lower in k or k in lower:
            return rec
    return {}


# THE API-ONLY PAGES SHOWED NO ENVIRONMENT ROWS (website audit I16, 2026-10-07).
#
# The road noise, air quality and flood rows print BANDS, and the bands live in
# data/borough-extra.json alone - the map's holder, which leaves BACKEND_ONLY_CITIES out on
# purpose. So the 11 Cardiff, Nottingham and Norwich pages showed none of the three, while the
# Lambda's record held the continuous figure behind each and the Environment score used it.
#
# They print that figure instead of a band. Re-banding it here is the trap: bands are cut on the
# UNROUNDED share (METHODOLOGY s7.1) and the Lambda holds the rounded one, so a borough sitting on a
# cut would land on the wrong side. A city that joins the map gains bands and switches by itself.
MEASURED_FIELD = {
    'roadNoise': 'roadNoiseAboveWhoPct',
    'airQuality': 'airQualityWhoRatio',
    'flood': 'floodMediumOrHighPct',
}


# What the page's visuals draw, as held.
VISUAL_FIGURES = ('roadNoiseAboveWhoPct', 'floodMediumOrHighPct', 'no2AnnualMeanUgm3', 'pm25AnnualMeanUgm3', 'crimeRate')


def measured_value(key: str, value: float) -> str:
    """Display text for one measured environment figure, printed as held (never re-rounded).

    `key` is a MEASURED_FIELD key and `value` the Lambda's figure. The row's note column already
    names the source and the threshold, so this is the reading itself:

      roadNoise   share of postcodes over WHO's 53 dB Lden road guideline, a percentage (48.9)
      airQuality  the worse of NO2 and PM2.5 as a multiple of its WHO 2021 guideline (1.49)
      flood       share of postcodes at Environment Agency Medium-or-High risk, a percentage (0.43)
    """
    shown = f'{value:g}'
    if key == 'airQuality':
        # A multiple, not "N% above": the conversion reads oddly at 1.01 and breaks below 1.
        return f'{shown} × the WHO 2021 guideline'
    if key in ('roadNoise', 'flood'):
        return f'{shown}% of postcodes'
    raise KeyError(key)


def gather(city: str, borough: str) -> dict | None:
    """Every published figure for one borough, absent keys omitted."""
    body, status = app.resolve_query({'borough': borough, 'city': city})
    if status != 200 or not isinstance(body.get('score'), (int, float)):
        return None
    ctx = body.get('context') or {}
    comp = body.get('components') or {}
    # Two holders, and both are read deliberately.
    #
    # The Lambda's own borough record carries what SCORING uses (crimeRate, p8,
    # transport, healthcare); data/borough-extra.json carries what the MAP
    # paints (road noise, air quality, flood) plus vintages. Neither is a
    # superset, so a page built from one alone is thinner than the data we hold.
    #
    # The first version of this read `app.BOROUGH_EXTRA` behind a hasattr()
    # guard. That attribute does not exist, so the guard returned {} and every
    # one of the 99 pages silently lost crime, schools, transport, healthcare,
    # road noise, air quality and flood - and still passed --check, because the
    # remaining eight facts cleared MIN_FACTS. A defensive guard turned a wrong
    # attribute name into a quietly worse product. Both lookups now raise.
    scoring = app.CITIES[city]['boroughs'][borough]
    painted = _painted_for(city, borough)

    facts = []

    def add(label, value, note=None):
        if value in (None, '', 'None'):
            return
        facts.append({'label': label, 'value': value, 'note': note})

    # GROWTH IS COHORT-RELATIVE; AFFORDABILITY IS NOT, SINCE v5.0 (2026-09-09).
    #
    # These pages carried ONE note over both rows, added 2026-09-03 when both
    # components were min-max scaled within the city. Affordability moved to a
    # NATIONAL log anchor at v5.0, so that note became false on the row it was
    # written for while staying true on the row beside it - which is exactly the
    # shape that lets a caveat outlive its reason. Two notes now, each saying
    # what its own row does.
    #
    # The original defect is worth keeping in view: Barking and Dagenham
    # published `Affordability 10.0` at GBP 371,030 while Stockton-on-Tees
    # published `0.0` at GBP 170,923 - 2.2x cheaper, reading as least
    # affordable - with the price in the same table for a reader to notice the
    # contradiction. v5.0 removes the contradiction rather than disclosing it,
    # and the within-city standing the old scale implied is now published as an
    # explicit rank.
    #
    # NEITHER is wrapped in uk_note(): these are methodology caveats, not UK
    # source attributions, and both are just as true of New York.
    prices = [r.get('avgPrice') for r in app.CITIES[city]['boroughs'].values()
              if r.get('avgPrice')]
    growth_note = None
    if len(prices) > 1:
        # v5.1: say which trend the score is built on, READ from the response
        # (context.growthBasis) rather than assumed - New York is nominal.
        basis = (body.get('context') or {}).get('growthBasis')
        basis_note = (
            'after inflation (real terms), ' if basis == 'real'
            else 'in cash terms, ' if basis == 'nominal' else ''
        )
        # v5.2: the anchor is the currency pool, not this city - the same move
        # v5.0 made for affordability, for the same reason, and the note takes
        # the same shape as afford_note below. New York's pool is its own five
        # boroughs, so its note still says so. The within-city rank is READ
        # from the response (context.growthRankInCity), like priceRankInCity.
        if basis == 'real':
            growth_note = (
                f'Price trend {basis_note}scored against every borough Sky Score covers in this '
                'currency, not just this city'
            )
        else:
            growth_note = (
                f'Price trend {basis_note}scaled among the {len(prices)} areas of this city, '
                'which is the whole of its currency pool'
            )
        grank = (body.get('context') or {}).get('growthRankInCity') or {}
        if grank.get('rank') and grank.get('of', 0) > 1:
            growth_note += f' - {grank["rank"]} of {grank["of"]} here by trend, fastest-rising first'

    # Derived from the response, never recomputed here: a second implementation
    # of the same rank is a second thing to keep in step.
    rank = (body.get('context') or {}).get('priceRankInCity') or {}
    # Per POOL (audit 2026-10-06, I6; per pool since 2026-11-07): the sterling pool is every UK area covered; a US
    # city's is its own areas (app.pool_of: one pool per US metro). It said "New York's five boroughs, the only US
    # prices held" for every US city, false of the Bay Area's pages and of New York's once the Bay Area was priced.
    if app.CITIES[city].get('country') == 'United Kingdom':
        afford_note = 'Scored against the prices of every UK area we cover, not just this city'
    else:
        pool = app.pool_of(city)
        members = [c for c in app.CITIES if app.pool_of(c) == pool]
        n = sum(len(app.CITIES[c]['boroughs']) for c in members)
        afford_note = (f"Scored among the {n} areas of {CITY_LABEL.get(city, city)} alone, never with another city's "
                       'prices: not comparable with UK scores' if members == [city] else
                       f'Scored among {n} areas in the same price pool: not comparable with UK scores')
    if rank.get('rank') and rank.get('of', 0) > 1:
        afford_note += f' - {rank["rank"]} of {rank["of"]} here by price, cheapest first'

    add('Sky Score', f"{body['score']} / 10")
    add('Quiet skies', f"{comp.get('quiet')} / 10" if comp.get('quiet') is not None else None)
    add('Affordability', f"{comp.get('afford')} / 10" if comp.get('afford') is not None else None,
        afford_note)
    add('Growth', f"{comp.get('growth')} / 10" if comp.get('growth') is not None else None,
        growth_note)
    add('Liveability', f"{comp.get('live')} / 10" if comp.get('live') is not None else None)
    # The FIFTH component, missing from all 99 pages until 2026-09-03 (audit F3).
    # `env` has scored since v3.9 and the pages showed four rows, so the
    # arithmetic a reader could do never reached the headline: Camden's five
    # weighted components give 6.57 -> 6.6, while renormalising the four shown
    # gives 6.92. No note, matching the four components above - the three
    # environment INPUTS below carry their own source lines, and this is their
    # composite. `add` skips None, so New York and Cardiff, which have no `env`,
    # correctly get no row rather than a zero.
    add('Environment', f"{comp.get('env')} / 10" if comp.get('env') is not None else None)
    # THE PER-FACT NOTE IS A UK LITERAL, AND IT WAS PRINTED FOR NEW YORK TOO
    # (2026-08-31, audit C3).
    #
    # Every note below names a UK body, and they were evaluated for every city -
    # so area/nyc/brooklyn/ printed "HM Land Registry HPI", "ONS Table C4",
    # "DEFRA road Lden", "Environment Agency RoFRS" and "NaPTAN" as the sources
    # of its numbers, while the SAME PAGE's sources paragraph, which is derived
    # and correct, said "NYPD CompStat-derived offence rates... curated New York
    # borough median sale prices, in USD... Licence note: OGL v3.0 covers UK
    # Crown copyright and does NOT apply to any data in this response".
    # Brooklyn's own record carries None for all four of those fields.
    #
    # A non-UK city gets NO note rather than an invented one: the derived
    # sources paragraph already carries the correct attribution, and guessing a
    # US source name here would replace a false claim with a made-up one.
    uk = app.CITIES[city].get('country') == 'United Kingdom'

    def uk_note(text):
        return text if uk else None

    # A city scored on the US SCALES (a California-anchored record, the Bay Area) says its inputs in the records
    # builder's own words, each with its source and year, the same words its front-page and map cards use, and the
    # UK rows below find nothing of theirs in its record. Its price is a Census median, its trend county-wide.
    us_scaled = bool(app.CITIES[city].get('usAnchors'))
    if us_scaled:
        anchors, rows = bay_records.records()
        if dict(rows).get(borough) != scoring:
            raise SystemExit(f"{city}/{borough}: the Lambda's record is not what the readers' files give: "
                             'run scripts/build_bayarea_records.py --write')
        for label, figure, source in bay_records.input_facts(borough, scoring, anchors, bay_records.input_sources(),
                                                             app.US_PRICE_TOP_CODE, ctx.get('crimeNote')):
            add(label, figure, source)
    add('Average price', fmt_price(ctx.get('avgPriceGbp')), uk_note('HM Land Registry HPI'))
    trend = ctx.get('priceTrendPct')
    if isinstance(trend, (int, float)) and not us_scaled:
        add('Price trend', f'{trend:+.1f}% year on year', uk_note('HM Land Registry HPI'))
    # THE BAND IS AN ESTIMATE, AND THE CAPTION SAID IT WAS A DEFRA SURVEY
    # (2026-09-13 audit, I24). `noiseImpactBand` is the geometry distance
    # ladder scaled by the airport's DEFRA Round 4 footprint - CLAUDE.md's
    # `impact` row: "geometry ESTIMATE" - and for Teesside and Cardiff, whose
    # airports DEFRA does not map, not even the scaling is a survey. 57 pages
    # carried this caption twenty lines above a sources paragraph saying the
    # opposite. Same mechanism as C3 of 31 Aug (a UK literal per fact row).
    # Derived from the engine's own contour status so a city describes itself.
    contour = app._defra_contour_status(city) if uk else None
    aircraft_note = {
        'mapped': "Estimated from the distance to the airport and its routes, scaled by the size of its DEFRA noise map",
        'unmapped': "Estimated from the distance to the airport and its routes; DEFRA's noise maps do not cover this airport",
        'none': 'No commercial airport in this city region',
    }.get(contour)
    if us_scaled:
        aircraft_note = ("Estimated from the FAA's published routes over the city's residents, fitted to the noise "
                         'monitors of San Francisco and San Jose airports; not a measurement')
    add('Aircraft noise band', (ctx.get('noiseImpactBand') or '').title() or None,
        aircraft_note if us_scaled else uk_note(aircraft_note))

    merged = {} if us_scaled else {**painted, **{k: v for k, v in scoring.items() if v is not None}}
    for key, label, note in (
        ('crimeRate', 'Recorded crime', 'ONS Table C4, per 1,000 residents per year'),
        ('p8', 'Progress 8', 'DfE KS4 2023/24 revised, 0.0 is the national average'),
        ('roadNoise', 'Road noise', 'DEFRA road Lden, share of postcodes over WHO 53 dB'),
        ('airQuality', 'Air quality', 'DEFRA background maps against WHO 2021'),
        # Spelled out since 2026-10-07 (website audit M8): RoFRS, NaPTAN and ODS meant
        # nothing to a reader, and "NHS ODS" did not say what was measured at all.
        ('flood', 'Flood risk', 'Environment Agency, Risk of Flooding from Rivers and Sea, allowing for defences'),
        ('transport', 'Transport access', "The national stop register (NaPTAN), share of postcodes within 800 m of a station"),
        ('healthcare', 'Healthcare access', 'NHS Organisation Data Service, share of postcodes within 500 m of a GP practice'),
    ):
        raw = merged.get(key)
        if raw in (None, ''):
            # No band: an API-only city (audit I16). Print the measured figure the band would be
            # cut from, when the Lambda holds one; a borough holding neither still gets no row.
            field = MEASURED_FIELD.get(key)
            measured = merged.get(field) if field else None
            if isinstance(measured, (int, float)):
                add(label, measured_value(key, measured), uk_note(note))
            continue
        # City of London's crime rate is OUR OWN estimate - ONS suppresses the
        # rate for its small resident population, and the crime gate prints
        # "must not be attributed to ONS" on every run. This page credited ONS
        # for it anyway.
        if key == 'crimeRate' and scoring.get('crimeEstimated'):
            note = 'Sky Score estimate - ONS publishes no rate for this area'
        add(label, f'{raw:g}' if isinstance(raw, (int, float)) else str(raw).title(), uk_note(note))
        if key == 'crimeRate' and scoring.get('crimeEstimated'):
            facts[-1]['estimated'] = True

    return {
        'city': city,
        'uk': uk,
        'borough': borough,
        'score': body['score'],
        # Said on a US-scaled city's page, under its score (Bill's rule): its scales are not the UK's.
        'us_scales': bay_records.us_scales(len(app.CITIES[city]['boroughs'])) if us_scaled else '',
        'facts': facts,
        'sources': body.get('sources') or [],
        'methodology': body.get('methodologyVersion'),
        # What the visuals draw, as held: absent stays absent, and a missing figure simply draws no bar.
        'figures': {key: merged.get(key) for key in VISUAL_FIGURES},
        'avg_price': ctx.get('avgPriceGbp'),
        'price_median': statistics.median(prices) if len(prices) > 1 else None,
    }


# THE SITE'S PALETTE, one holder for every page these two builders write (build_planes_pages.py reads it as
# area.PALETTE_LIGHT). tests/test_site_palette.py holds the built pages to it.
PALETTE_LIGHT = (
    "--bg:#f4f3ef; --paper:#fbfaf8; --dark:#141414; --mid:#55554f; --line:#dedcd6; --orange:#f27d26; --orange-ink:#a85416; "
    "--focus:#d35a12; --track:#e4e3e0; --yard:#807e79;\n    --font-display:'Geist',system-ui,sans-serif; --font-mono:'JetBrains Mono',ui-monospace,monospace;"
)
PALETTE_DARK = '--dark:#f5f5f4; --mid:#a1a1a1; --line:#3a3a3a; --bg:#141414; --paper:#1c1c1c; --orange:#fb923c; --orange-ink:#fb923c; --track:#3a3a3a; --yard:#8c8a85;'

# COUNTED SINCE 2026-10-22. The three templates below (an area page, the area index, open data) carried no
# analytics, so the pages most likely to arrive from a search were the ones GoatCounter could not see. Each now
# loads js/count.mjs (anonymous, cookieless, aggregate: privacy s2c) under the same strict policy the other
# counting pages carry, which tests/test_analytics_first_party.py requires; they load nothing else but their own
# styles and fonts, so the policy blocks nothing they use.
PAGE = """<!doctype html>
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
<meta property="og:type" content="article" />
<meta property="og:site_name" content="Sky Score" />
<meta name="twitter:card" content="summary" />
<link rel="icon" href="/favicon.ico" sizes="32x32" />
<link rel="icon" href="/icons/favicon.svg" type="image/svg+xml" />
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
<link rel="stylesheet" href="/fonts/fonts.css" />
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: https://cubitt33.goatcounter.com; connect-src https://cubitt33.goatcounter.com; base-uri 'self'; form-action 'self';" />
<style>
  /* `color-scheme` declared 2026-09-02 (audit D11). These pages carry a
     prefers-color-scheme block below, so they REPAINT for dark mode - but
     without this the browser still renders its own furniture (scrollbars,
     and the canvas painted before our CSS applies) in light, so a dark-mode
     reader gets a white flash and a light scrollbar against a #141414 page.
     Declaring it is what makes the dark block honest. */
  :root {{ color-scheme: light dark;
    """ + PALETTE_LIGHT + """ }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:0; font-family:'Inter',system-ui,sans-serif; color:var(--dark); background:var(--bg); line-height:1.6; }}
  a:focus-visible {{ outline:3px solid var(--focus); outline-offset:2px; }} /* the site's ring, not the browser's (audit 2026-10-22, M-13) */
  .wrap {{ max-width:1100px; margin:0 auto; padding:24px clamp(16px, 4vw, 48px) 64px; }}
  a {{ color:var(--orange-ink); }}
  nav.crumbs {{ font-size:12px; color:var(--mid); margin-bottom:20px; }}
  h1 {{ font-family:var(--font-display); font-weight:700; font-size:clamp(30px, 4.4vw, 44px); line-height:1.12; letter-spacing:-0.02em; margin:0 0 10px; }}
  .sub {{ color:var(--mid); font-size:16px; margin:0 0 8px; max-width:62ch; }}
  /* FINDINGS FIRST (Bill's pick, 2026-11-04: Stitch's layout, the site's own colours). The score, then each finding in
     plain words with its figure under it. A score's bar takes the map's own colour for that score. */
  .headline {{ display:flex; align-items:baseline; flex-wrap:wrap; gap:6px 12px; margin:28px 0 10px; }}
  .headline .n {{ font-family:var(--font-display); font-size:clamp(56px, 9vw, 84px); font-weight:700; line-height:1; letter-spacing:-0.03em; }}
  .headline .of {{ color:var(--mid); font-size:14px; }}
  .bar {{ height:8px; background:var(--track); border-radius:4px; overflow:hidden; }}
  .bar i {{ display:block; height:100%; border-radius:4px; }}
  .bar.big {{ max-width:520px; margin-bottom:28px; }}
  dl.scores {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:20px 24px; margin:0; padding:24px 0; border-top:1px solid var(--line); border-bottom:1px solid var(--line); }}
  dl.scores dt {{ font-size:14px; font-weight:500; }}
  dl.scores dd {{ margin:0; }}
  dl.scores b {{ font-family:var(--font-display); font-size:22px; font-weight:700; }}
  dl.scores .of {{ font-family:var(--font-mono); font-size:12px; color:var(--mid); }}
  dl.scores .bar {{ margin:6px 0 0; }}
  /* 12px, the site's small print everywhere else; 11px was the one size below it (site audit 2026-11-01). */
  .note {{ display:block; color:var(--mid); font-size:12px; margin-top:4px; }}
  .groups {{ display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:0 48px; margin:8px 0; }}
  @media (max-width: 760px) {{ .groups {{ grid-template-columns:minmax(0, 1fr); }} }}
  section.group {{ padding:24px 0 8px; }}
  section.group + section.group {{ border-top:1px solid var(--line); }}
  section.group h2 {{ font-family:var(--font-mono); font-size:12px; font-weight:500; letter-spacing:0.12em; text-transform:uppercase; color:var(--mid); margin:0 0 14px; }}
  .find {{ margin:0 0 18px; }}
  .find-h {{ margin:0; font-size:19px; font-weight:600; line-height:1.3; }}
  .find-big {{ font-family:var(--font-display); font-size:26px; font-weight:700; letter-spacing:-0.02em; }}
  .find-d {{ margin:2px 0 0; color:var(--mid); font-size:14px; }}
  /* VISUALS (Bill's pick B, 2026-11-04). A bar shows a share of a whole or a figure beside a named yardstick, from a true
     zero; a strip shows where a rating sits among its own words. Aircraft noise and the price trend have nothing honest to
     be drawn against, so they stay as words. Bars and strips are hidden from a screen reader; a caption stays readable
     unless the sentence above it already says the same figures. */
  .vis {{ margin-top:8px; max-width:420px; }}
  .vis-h {{ margin:10px 0 0; font-family:var(--font-mono); font-size:12px; font-weight:500; color:var(--mid); }}
  .vis-cap {{ display:flex; justify-content:space-between; gap:10px; font-size:12.5px; color:var(--mid); margin:6px 0 3px; }}
  .vis-cap b {{ font-family:var(--font-mono); font-size:12.5px; font-weight:500; color:var(--dark); white-space:nowrap; }}
  .vis .bar i {{ background:var(--orange); }}
  .vis .bar i.yard {{ background:var(--yard); }}
  .steps {{ display:flex; gap:3px; margin-top:8px; max-width:420px; font-size:12px; }}
  .steps span {{ flex:1; padding:4px 2px; text-align:center; border-radius:4px; background:var(--track); color:var(--dark); }}
  .steps span.on {{ background:var(--orange); color:#141414; font-weight:600; }}
  h2 {{ font-family:var(--font-display); font-size:20px; font-weight:600; margin:32px 0 8px; }}
  .sources {{ font-size:12px; color:var(--mid); }}
  .cta {{ margin:12px 0 28px; padding:20px 24px; background:var(--paper); border:1px solid var(--line); border-radius:18px; }}
  /* The way to the map is the page's one button: dark, as every button on the site but the front page's search. */
  .cta a {{ display:inline-block; padding:10px 18px; border-radius:10px; background:var(--dark); color:var(--bg); font-weight:600; font-size:14px; text-decoration:none; }}
  .cta a:hover {{ text-decoration:underline; text-underline-offset:3px; }}
  footer {{ margin-top:40px; font-size:12px; color:var(--mid); }}
  /* The site bar (2026-10-06): the front page's header.top, in this page's own font and colours. */
  .site-top {{ display:flex; align-items:center; justify-content:space-between; gap:8px 16px; flex-wrap:wrap; padding:14px clamp(16px, 4vw, 48px); }}
  .site-top .site-brand {{ font-weight:700; font-size:18px; letter-spacing:-0.01em; text-decoration:none; color:var(--dark); }}
  .site-top .site-nav {{ display:flex; gap:4px; flex-wrap:wrap; }}
  .site-top .site-nav {{ align-items:center; }}
  .site-top .site-nav a {{ font-size:14px; font-weight:500; text-decoration:none; padding:8px 12px; border-radius:8px; color:var(--dark); }}
  /* 'You are here' is an underline and Full map an outlined button (Bill, 2026-10-06): --focus, past the 3:1 a state cue needs. */
  .site-top .site-nav a.nav-cta {{ box-shadow: inset 0 0 0 1.5px var(--dark); font-weight:600; }}
  .site-top .site-nav a:hover {{ text-decoration: underline; text-decoration-thickness: 1.5px; text-underline-offset: 7px; }}
  .site-top .site-nav a[aria-current] {{ text-decoration: underline; text-decoration-color: var(--focus); text-decoration-thickness: 3px; text-underline-offset: 7px; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ """ + PALETTE_DARK + """ }}
  }}
  /* The phone menu (2026-10-23). Below 680 px the name and the six links no longer share a row, so the links
     fold behind a Menu button. It is a popover, so it needs no script (privacy and terms allow none, the area
     pages carry none), and a browser without popovers keeps the plain bar. On a wide screen the closed popover
     IS the ordinary row of links, so the browser's popover box is undone first. */
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
</style>
</head>
<body>
<!-- The site bar, the same on every page since 2026-10-06 (the front page's header.top). -->
<nav class="site-top" aria-label="Site"><a class="site-brand" href="/">Sky Score</a><button type="button" class="menu-btn" popovertarget="site-nav">Menu</button><div class="site-nav" id="site-nav" popover><button type="button" class="menu-close" popovertarget="site-nav" popovertargetaction="hide">Close</button><a class="nav-cta" href="/map/">Full map</a><a href="/reports/">Reports</a><a href="/how-it-works/">How it works</a><a href="/pricing">Pricing</a><a href="/api/">API</a><a href="/about/">About</a></div></nav>
<div class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Sky Score</a> &rsaquo; <a href="/area/">Areas</a> &rsaquo; {city_label}</nav>
{crumbs_ld}
<main data-city="{city}" data-borough="{borough}">
<h1>{borough} noise and liveability</h1>
<p class="sub">{city_label}. {topics_cap}, from published sources.</p>

<div class="headline" data-fact><span class="n">{score}</span><span class="of">Sky Score out of 10; on every score here, 10 is best</span></div>
<div class="bar big" aria-hidden="true"><i style="width:{score_width}%;background:{score_colour}"></i></div>
{us_scales}
<dl class="scores">
{scores}
</dl>

<div class="groups">
{groups}
</div>

{cta}

{planes}<h2>Where these numbers come from</h2>
<p class="sources">{sources}</p>
<p class="sources">Methodology version {methodology}. Full method: <a href="https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md">the methodology</a> (and the <a href="/score-demo/api-docs.html">API reference</a>).
Figures are for the whole {unit}; a single address can differ{map_note}.</p>
</main>

<footer>
<p><a href="/">Sky Score</a> &middot; <a href="/map/">Full map</a> &middot; <a href="/reports/">Reports</a> &middot; <a href="/area/">All areas</a> &middot; <a href="/how-it-works/">How it works</a> &middot; <a href="/about/">About</a> &middot; <a href="/api/">For developers</a> &middot; <a href="/privacy">Privacy</a> &middot; <a href="/terms">Terms</a></p>
</footer>
</div>
<script type="module" src="/js/count.mjs"></script>
</body>
</html>
"""


def topics(facts, compact: bool = False) -> str:
    """What this page actually shows, in words (audit 2026-10-06, I7): 22 of 102 pages promised
    schools and showed no schools figure, and Cardiff's promised road noise it does not hold. `compact` says the same
    topics in shorter words, for a description that must fit a search result (2026-11-11)."""
    have = {f['label'] for f in facts}
    noise = ('aircraft and road noise' if 'Road noise' in have else 'aircraft noise') if not compact else 'noise'
    words = [noise, 'prices' if compact else 'affordability']
    for label, word, short in (
        ('Progress 8', 'schools', 'schools'),
        ('Recorded crime', 'crime', 'crime'),
        ('Crime', 'crime', 'crime'),
        ('Transport access', 'transport', 'transport'),
        ('Rail access', 'rail access', 'rail'),
        ('Air quality', 'air quality', 'air'),
        ('Flood risk', 'flood risk', 'flood'),
    ):
        if label in have:
            words.append(short if compact else word)
    return ', '.join(words[:-1]) + ' and ' + words[-1]


# SEARCH RESULTS SHOW ABOUT 60 CHARACTERS OF A TITLE AND 160 OF A DESCRIPTION (the SEO audit of 2026-11-10: 395 of 498
# planes titles and nearly every description ran past them). ONE rule for the area and planes pages: a title keeps
# " | Sky Score" only where it fits; a description is the first of its versions, longest first, that fits, never cut
# mid-word. tests/test_page_meta.py holds every built page to them.
TITLE_MAX, DESC_MAX = 60, 160


def page_title(*cores: str) -> str:
    for core in cores:
        if len(f'{core} | Sky Score') <= TITLE_MAX:
            return f'{core} | Sky Score'
        if len(core) <= TITLE_MAX:
            return core
    return cores[-1]


def fit(*versions: str) -> str:
    for v in versions:
        if len(v) <= DESC_MAX:
            return v
    return versions[-1]


# FINDINGS FIRST (Bill's pick, 2026-11-04: Stitch's layout). gather() is untouched: the same facts, said as findings.
# The scores come first; each other fact sits in one of four groups, in two columns on a wide screen. A fact with no
# place here is a build error, never a silent gap (tests/test_area_findings.py).
SCORE_ROWS = ('Quiet skies', 'Affordability', 'Growth', 'Liveability', 'Environment')
COLUMNS = (
    (('Noise and planes', ('Aircraft noise band', 'Road noise')), ('Air and flood', ('Air quality', 'Flood risk'))),
    # Crime, Rail access, Median home value and County price trend: the Bay Area's inputs, in the records builder's
    # words (2026-11-07), placed where the UK's like-for-like rows sit.
    (('Living here', ('Recorded crime', 'Crime', 'Progress 8', 'Transport access', 'Rail access', 'Healthcare access')),
     ('Property', ('Average price', 'Median home value', 'Price trend', 'County price trend'))),
)
SAID_AS = {'Aircraft noise band': 'Aircraft noise'}


def score_colour(score: float) -> str:
    """The map's scoreColor(), held equal to it by tests/test_area_findings.py."""
    return '#26f27d' if score >= 7 else '#f2b826' if score >= 4 else '#f27d26'


def school_band(p8: float) -> str:
    """DfE's Progress 8 bands, the map's schoolBandFromP8(), held equal to it by tests/test_area_findings.py."""
    if p8 >= 0.5:
        return 'well above average'
    if p8 >= 0.2:
        return 'above average'
    if p8 >= -0.2:
        return 'average'
    return 'below average' if p8 >= -0.5 else 'well below average'


@functools.cache
def london_crime_median() -> float:
    """The map's londonCrimeMedian(): every UK page's rate is read against it, as the map's panel reads it."""
    return statistics.median(r['crimeRate'] for r in _BOROUGH_EXTRA['london'].values()
                             if isinstance(r.get('crimeRate'), (int, float)))


def london_median_said() -> str:
    """The median as every part of a page prints it, so a sentence and a bar's caption cannot differ."""
    return f'{london_crime_median():.1f}'


def crime_against_london(rate: float) -> str:
    """The rate in words, on the map's own thresholds (crimeNote): a bare 87.6 says nothing to a first-time reader."""
    ratio = rate / london_crime_median()
    if ratio >= 1.15:
        return f'{ratio:.1f} times the London median'
    if ratio <= 0.85:
        return f'{1 / ratio:.1f} times lower than the London median'
    return 'close to the London median'


# WHO's 2021 annual guidelines, held equal to js/street_report.mjs AIR_WHO_2021 and the API by tests/test_area_findings.py.
AIR_WHO = {'no2': 10, 'pm25': 5}
RATING_STEPS = ('Poor', 'Moderate', 'Good', 'Excellent')
SCHOOL_STEPS = ('Well below', 'Below', 'Average', 'Above', 'Well above')


def is_figure(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def bar_html(width: float, yard: bool = False) -> str:
    """One bar from a true zero. The sliver keeps a tiny share visible (0.33% of a bar is under two pixels); zero stays zero."""
    drawn = max(width, 0.6) if width > 0 else 0
    return f'<div class="bar" aria-hidden="true"><i{" class=yard" if yard else ""} style="width:{drawn:.2f}%"></i></div>'


def share_bar(pct: float, words: str) -> str:
    """A share of the council's postcodes: the bar's whole is all of them."""
    return f'<div class="vis"><div class="vis-cap"><span>{e(words)}</span><b>{pct:g}%</b></div>{bar_html(pct)}</div>'


def pair_bars(rows: list[tuple[str, float, str, bool]], heading: str = '', said: bool = False) -> str:
    """A figure beside its yardstick, both from a true zero on one scale, so the lengths keep the true ratio. `said`: the
    sentence above gives both figures, so a screen reader need not hear them again."""
    top = max(value for _, value, _, _ in rows) * 1.12
    body = ''.join(f'<div class="vis-cap"><span>{e(name)}</span><b>{e(text)}</b></div>{bar_html(value / top * 100, yard)}'
                   for name, value, text, yard in rows)
    label = f'<p class="vis-h">{e(heading)}</p>' if heading else ''
    return f'<div class="vis"{" aria-hidden=true" if said else ""}>{label}{body}</div>'


def step_strip(names: tuple[str, ...], on: str) -> str:
    """Where a rating sits among its own words. Nothing for a rating outside them: it could not be shown truthfully."""
    if on.lower() not in {n.lower() for n in names}:
        return ''
    cells = ''.join(f'<span{" class=on" if n.lower() == on.lower() else ""}>{e(n)}</span>' for n in names)
    return f'<div class="steps" aria-hidden="true">{cells}</div>'


def visuals(data: dict, city_label: str, uk: bool) -> dict[str, tuple[str, str]]:
    """Each fact's (strip under its headline, bars under its words). A figure a council does not hold draws nothing."""
    fig, name = data.get('figures') or {}, data['borough']
    out: dict[str, tuple[str, str]] = {}
    if is_figure(fig.get('roadNoiseAboveWhoPct')):
        out['Road noise'] = ('', share_bar(fig['roadNoiseAboveWhoPct'], 'Postcodes over the WHO guideline'))
    if is_figure(fig.get('floodMediumOrHighPct')):
        out['Flood risk'] = ('', share_bar(fig['floodMediumOrHighPct'], 'Postcodes at medium or high risk'))
    air = ''.join(pair_bars([(name, fig[key], f'{fig[key]:g} µg/m³', False), ('WHO guideline', AIR_WHO[short], f'{AIR_WHO[short]} µg/m³', True)], heading)
                  for key, short, heading in (('no2AnnualMeanUgm3', 'no2', 'Nitrogen dioxide'), ('pm25AnnualMeanUgm3', 'pm25', 'Fine particles'))
                  if is_figure(fig.get(key)))
    if air:
        out['Air quality'] = ('', air)
    if uk and is_figure(fig.get('crimeRate')):
        median = london_crime_median()
        out['Recorded crime'] = ('', pair_bars([(name, fig['crimeRate'], f"{fig['crimeRate']:g}", False), ('London median', median, london_median_said(), True)], said=True))
    if is_figure(data.get('avg_price')) and is_figure(data.get('price_median')):
        out['Average price'] = ('', pair_bars([(name, data['avg_price'], fmt_price(data['avg_price']), False),
                                               (f'{city_label} median', data['price_median'], fmt_price(data['price_median']), True)]))
    for f in data['facts']:
        if f['label'] in ('Transport access', 'Healthcare access'):
            out[f['label']] = (step_strip(RATING_STEPS, str(f['value'])), '')
        elif f['label'] == 'Progress 8':
            band = school_band(float(f['value']))
            out['Progress 8'] = (step_strip(SCHOOL_STEPS, band if band == 'average' else band.removesuffix(' average')), '')
    return out


def finding(f: dict, uk: bool, strip: str = '', bars: str = '') -> str:
    """One fact as a finding: its plain words, its strip, its figure, its bars, then the source note it always carried."""
    label, value, note = f['label'], f['value'], f.get('note')
    detail = ''
    if label == 'Recorded crime':
        if uk:
            # ONS publishes no rate for the City of London: the figure is ours, and the sentence must say so.
            word, unit = (('Estimated crime', "offences per 1,000 residents a year, Sky Score's estimate") if f.get('estimated')
                          else ('Recorded crime', 'recorded offences per 1,000 residents a year'))
            head = f'{word} is {crime_against_london(float(value))}'
            detail = f'{value} {unit}; the London median is {london_median_said()}.'
        else:
            head, detail = 'Recorded crime', f'{value} recorded offences per 1,000 residents a year.'
    elif label == 'Progress 8':
        head, detail = f'Schools are {school_band(float(value))}', f'Progress 8 is {value}.'
    elif label in ('Average price', 'Price trend'):
        return (f'<div class="find" data-fact><p class="find-d">{e(label)}</p><p class="find-h find-big">{e(value)}</p>{bars}'
                + (f'<span class="note">{e(note)}</span>' if note else '') + '</div>')
    else:
        said = SAID_AS.get(label, label)
        # An API-only city holds no band, only the figure one would be cut from: that reads as a figure, never a word.
        head, detail = (said, str(value)) if re.search(r'\d', str(value)) else (f'{said} is {str(value).lower()}', '')
        if bars and detail:
            detail = ''  # an API-only city's figure: its bar's caption says it, in fuller words
    return (f'<div class="find" data-fact><p class="find-h">{e(head)}</p>{strip}'
            + (f'<p class="find-d">{e(detail)}</p>' if detail else '') + bars
            + (f'<span class="note">{e(note)}</span>' if note else '') + '</div>')


def score_row(f: dict) -> str:
    """One score out of 10, its bar in the map's colour for that score, its note under it."""
    shown = f['value'].split(' / ')[0]
    width = max(0.0, min(100.0, float(shown) * 10))
    return (f'<div data-fact><dt>{e(f["label"])}</dt><dd><b>{e(shown)}</b> <span class="of">/ 10</span>'
            f'<div class="bar" aria-hidden="true"><i style="width:{width:g}%;background:{score_colour(float(shown))}"></i></div>'
            + (f'<span class="note">{e(f["note"])}</span>' if f.get('note') else '') + '</dd></div>')


def findings_html(facts: list[dict], uk: bool, drawn: dict[str, tuple[str, str]] | None = None) -> tuple[str, str]:
    """The scores and the two columns of groups. Every fact must land somewhere: a new label stops the build."""
    by_label = {f['label']: f for f in facts}
    if len(by_label) != len(facts):
        raise ValueError('two facts share a label, so one would vanish from the page')
    placed = {'Sky Score', *SCORE_ROWS, *(label for column in COLUMNS for _, labels in column for label in labels)}
    lost = set(by_label) - placed
    if lost:
        raise ValueError(f'no place on the area page for {sorted(lost)}')
    scores = '\n'.join(score_row(by_label[label]) for label in SCORE_ROWS if label in by_label)
    columns = []
    for column in COLUMNS:
        sections = []
        for name, labels in column:
            found = [finding(by_label[label], uk, *(drawn or {}).get(label, ('', ''))) for label in labels if label in by_label]
            if found:
                sections.append(f'<section class="group"><h2>{e(name)}</h2>\n' + '\n'.join(found) + '\n</section>')
        columns.append('<div>\n' + '\n'.join(sections) + '\n</div>')
    return scores, '\n'.join(columns)


def render(data: dict) -> str:
    city_label = CITY_LABEL.get(data['city'], data['city'].title())
    scores, groups = findings_html(data['facts'], data['uk'], visuals(data, city_label, data['uk']))
    # THE META DESCRIPTION NAMED UK BODIES FOR NEW YORK TOO (2026-08-31, C3).
    #
    # This is the text that appears in a SEARCH RESULT, so "Brooklyn ... from
    # DEFRA, ONS, DfE and HM Land Registry data" was a false provenance claim on
    # the most public surface the page has - and it survived the per-fact note
    # fix, because it is built here and not there. Found by the gate written for
    # the notes, which is the argument for writing the gate.
    uk_city = app.CITIES[data['city']].get('country') == 'United Kingdom'
    source_clause = ('from official public data' if uk_city
                     else 'from public US federal and California sources' if data.get('us_scales')
                     else 'from public New York City sources')
    # "Cardiff, Cardiff" (audit I7): a borough that shares its city's name is named once.
    place = data['borough'] if data['borough'] == city_label else f"{data['borough']}, {city_label}"
    shown = topics(data['facts'])
    lead = f"{data['borough']} scores {data['score']} out of 10 on Sky Score"
    short = topics(data['facts'], compact=True)
    desc = fit(
        f"{lead}. {shown[0].upper() + shown[1:]} for {place}, {source_clause}.",
        f"{lead}. {shown[0].upper() + shown[1:]}, {source_clause}.",
        f"{lead}: {short}, {source_clause}.",
        f"{lead}: {short}.",
    )
    # A PREVIEW CITY HAS NO MAP, SO ITS PAGE MUST NOT OFFER ONE (2026-09-30).
    #
    # Every page linked to /?city=<city>, and the site IGNORES a city that
    # CITY_DATA does not hold, so "Open Norwich on the Sky Score map" opened
    # LONDON's map - the defect a Norwich user had written in about, reached
    # from the page built to fix it. Guarded by tests/area-pages.mjs, which
    # reads the cities the site can open from index.html, not from here.
    if data['city'] in backend_only_cities():
        cta = (
            '<div class="cta">\n'
            f'  <p style="margin:0 0 8px;"><strong>Not on the map.</strong> {e(city_label)} is not on the '
            'interactive map: these borough figures are published here and through the API.</p>\n'
            '  <a href="/area/">See every area Sky Score covers</a>\n'
            '</div>'
        )
        map_note = ''
    else:
        # The Bay Area's map holds cities, ZIPs and San Francisco's neighbourhoods, never a postcode (2026-11-07).
        on_map = (f'The published routes, the federal noise map and every city\'s score in {e(city_label)}.'
                  if data.get('us_scales') else
                  f'Noise contours, flight corridors and every neighbourhood in {e(city_label)}.')
        cta = (
            '<div class="cta">\n'
            f'  <p style="margin:0 0 8px;"><strong>See it on the map.</strong> {on_map}</p>\n'
            # /map/ since 2026-10-06, when the front page took / and the full map moved.
            f'  <a href="/map/?city={e(data["city"])}&amp;borough={e(data["borough"].replace(" ", "+"))}">'
            f'Open {e(data["borough"])} on the Sky Score map</a>\n'
            '</div>'
        )
        map_note = (', and the map shows the routes over each ZIP' if data.get('us_scales')
                    else ', and the map shows postcode-level detail')
    return PAGE.format(
        title=e(page_title(f"{data['borough']} noise & liveability score")),
        description=e(desc),
        canonical=f"{SITE}/area/{slug(data['city'])}/{slug(data['borough'])}/",
        crumbs_ld=breadcrumb_ld([('Sky Score', '/'), ('Areas', '/area/'),
                                 (data['borough'], f"/area/{slug(data['city'])}/{slug(data['borough'])}/")]),
        city_label=e(city_label),
        topics_cap=e(shown[0].upper() + shown[1:]),
        # `city` feeds data-city on <main>: the page's machine-readable identity,
        # which tests/area-page-freshness.mjs reads. It used to read the map
        # link, and a preview page has no map link (2026-09-30).
        city=e(data['city']),
        borough=e(data['borough']),
        cta=cta,
        # Ends in a blank line when there is one, and is '' otherwise, so a page with no district page is
        # byte-identical to before (its sitemap date does not move).
        planes=planes_section(data['city'], data['borough']),
        map_note=map_note,
        unit='city' if data.get('us_scales') else 'borough',
        score=e(data['score']),
        us_scales=f'<p class="sub">{e(data["us_scales"])}</p>\n' if data.get('us_scales') else '',
        score_width=f"{max(0.0, min(100.0, float(data['score']) * 10)):g}",
        score_colour=score_colour(float(data['score'])),
        scores=scores,
        groups=groups,
        # EVERY source, not the first six (2026-09-07, audit I7). The `[:6]`
        # cap silently dropped the tail of the attribution array, and the tail
        # is where the environment datasets sit:
        #
        #   Environment Agency RoFRS   dropped from 90 pages that publish its
        #                              flood band
        #   DEFRA road Lden            dropped from 43
        #   DEFRA PCM air quality      dropped from 10
        #
        # Each affected page PRINTS the row it had just dropped the credit for -
        # "Flood risk | Medium | Environment Agency RoFRS, risk after defences" -
        # and bakes it into the Environment score above it. OGL v3.0 grants
        # reuse ON CONDITION of attribution, and these are our own pages, in our
        # own sitemap.
        #
        # A cap on an attribution list is a cap on a licence obligation, and it
        # was invisible because the array grew past six only when `environment`
        # started scoring at v3.9.
        #
        # The UK AIP (NATS) credit comes from the API's own sources now (audit 2026-10-06, C1),
        # derived from the geometry each city scores with. It was appended here by hand for
        # every UK page until then, which also credited it on South Yorkshire's, a city with
        # no airport; adding it again would print it twice.
        sources=e('; '.join(str(s) for s in data['sources']) or 'See methodology.'),
        methodology=e(data['methodology'] or ''),
    )


INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Every area Sky Score covers | Sky Score</title>
<meta name="description" content="{description}" />
<link rel="canonical" href="{site}/area/" />
<meta property="og:title" content="Every area Sky Score covers | Sky Score" />
<meta property="og:description" content="{description}" />
<meta property="og:url" content="{site}/area/" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="Sky Score" />
<meta name="twitter:card" content="summary" />
<link rel="icon" href="/favicon.ico" sizes="32x32" />
<link rel="icon" href="/icons/favicon.svg" type="image/svg+xml" />
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
<link rel="stylesheet" href="/fonts/fonts.css" />
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: https://cubitt33.goatcounter.com; connect-src https://cubitt33.goatcounter.com; base-uri 'self'; form-action 'self';" />
<style>
  /* See the note on the borough template: same reason, same fix. */
  :root {{ color-scheme: light dark;
    """ + PALETTE_LIGHT + """ }}
  body {{ margin:0; font-family:'Inter',system-ui,sans-serif; color:var(--dark); background:var(--bg); line-height:1.6; }}
  a:focus-visible {{ outline:3px solid var(--focus); outline-offset:2px; }}
  .wrap {{ max-width:720px; margin:0 auto; padding:24px 20px 64px; }}
  a {{ color:var(--orange-ink); }}
  h1 {{ font-family:var(--font-display); font-size:32px; font-weight:700; letter-spacing:-0.02em; margin:0 0 6px; }}
  h2 {{ font-size:16px; margin:28px 0 6px; }}
  ul {{ margin:0; padding-left:18px; }}
  li {{ margin:2px 0; }}
  .sub {{ color:var(--mid); font-size:14px; }}
  /* THE COMPARISON TABLES (2026-10-25). A reader in Poland opened 24 London area pages one at a time from
     this index, going back to it 22 times, because it listed names only. Each city's areas now sit in one
     table, the same figures each area's own page publishes. No script (these pages carry none), so no
     sorting: a narrow screen scrolls the table sideways inside its own box, the area's name held at the left. */
  /* position:relative makes the box the containing block of the visually hidden caption inside it; without
     it the absolutely placed caption escapes the scroll box and widened a 390 px page by 262 px. */
  .tw {{ overflow-x:auto; position:relative; margin:8px 0 4px; }}
  .tw:focus-visible {{ outline:3px solid #d35a12; outline-offset:2px; }}
  table.compare {{ border-collapse:collapse; width:100%; min-width:640px; font-size:14px; font-variant-numeric:tabular-nums; }}
  table.compare th, table.compare td {{ padding:7px 8px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }}
  table.compare thead th {{ font-size:12px; font-weight:600; color:var(--mid); vertical-align:bottom; white-space:normal; }}
  table.compare th[scope="row"], table.compare thead th:first-child {{ text-align:left; position:sticky; left:0; background:var(--page); }}
  table.compare th[scope="row"] {{ font-weight:500; white-space:normal; min-width:8em; }}
  table.compare td.score {{ font-weight:700; }}
  .visually-hidden {{ position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }}
  .key {{ color:var(--mid); font-size:12px; margin:4px 0 0; }}
  :root {{ --page:var(--bg); }}
  @media (prefers-color-scheme: dark) {{
    :root {{ """ + PALETTE_DARK + """ }}
  }}
  /* The site bar (2026-10-06): the front page's header.top, in this page's own font and colours. */
  .site-top {{ display:flex; align-items:center; justify-content:space-between; gap:8px 16px; flex-wrap:wrap; padding:14px clamp(16px, 4vw, 48px); }}
  .site-top .site-brand {{ font-weight:700; font-size:18px; letter-spacing:-0.01em; text-decoration:none; color:var(--dark); }}
  .site-top .site-nav {{ display:flex; gap:4px; flex-wrap:wrap; }}
  .site-top .site-nav {{ align-items:center; }}
  .site-top .site-nav a {{ font-size:14px; font-weight:500; text-decoration:none; padding:8px 12px; border-radius:8px; color:var(--dark); }}
  /* 'You are here' is an underline and Full map an outlined button (Bill, 2026-10-06): --focus, past the 3:1 a state cue needs. */
  .site-top .site-nav a.nav-cta {{ box-shadow: inset 0 0 0 1.5px var(--dark); font-weight:600; }}
  .site-top .site-nav a:hover {{ text-decoration: underline; text-decoration-thickness: 1.5px; text-underline-offset: 7px; }}
  .site-top .site-nav a[aria-current] {{ text-decoration: underline; text-decoration-color: var(--focus); text-decoration-thickness: 3px; text-underline-offset: 7px; }}
  /* The phone menu (2026-10-23). Below 680 px the name and the six links no longer share a row, so the links
     fold behind a Menu button. It is a popover, so it needs no script (privacy and terms allow none, the area
     pages carry none), and a browser without popovers keeps the plain bar. On a wide screen the closed popover
     IS the ordinary row of links, so the browser's popover box is undone first. */
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
</style>
</head>
<body>
<!-- The site bar, the same on every page since 2026-10-06 (the front page's header.top). -->
<nav class="site-top" aria-label="Site"><a class="site-brand" href="/">Sky Score</a><button type="button" class="menu-btn" popovertarget="site-nav">Menu</button><div class="site-nav" id="site-nav" popover><button type="button" class="menu-close" popovertarget="site-nav" popovertargetaction="hide">Close</button><a class="nav-cta" href="/map/">Full map</a><a href="/reports/">Reports</a><a href="/how-it-works/">How it works</a><a href="/pricing">Pricing</a><a href="/api/">API</a><a href="/about/">About</a></div></nav>
<div class="wrap">
<nav class="sub" aria-label="Breadcrumb"><a href="/">Sky Score</a> &rsaquo; Areas</nav>
<main>
<h1>Every area we cover</h1>
<p class="sub">{coverage}. Each page carries the published measurements behind that area's score.</p>
<p class="sub">Each city's areas side by side: the Sky Score and its five parts are out of 10, and 10 is best. A dash means that area's page publishes no figure for it.</p>
<p class="sub">All of it in one file: <a href="/open-data/">download the open data (CSV)</a>.</p>
<p class="sub">The Bay Area's flight paths, city by city: <a href="/bay-area/">the Bay Area page</a>.</p>
{body}
<p class="sub" style="margin-top:32px;"><a href="/map/">Back to the map</a> &middot; <a href="/api/">For developers</a> &middot; <a href="/terms">Terms</a></p>
</main>
</div>
<script type="module" src="/js/count.mjs"></script>
</body>
</html>
"""


# The columns, in the order each area's own page lists them; read from that page's facts, never recomputed.
COMPARE_COLUMNS = ('Sky Score', 'Quiet skies', 'Affordability', 'Growth', 'Liveability', 'Environment',
                   'Average price')
NONE_PUBLISHED = '<td><span aria-hidden="true">&ndash;</span><span class="visually-hidden">none published</span></td>'


def compare_cell(label, facts):
    """One cell: the figure that area's page publishes under `label`, or a dash that says it publishes none.
    The price column takes a US-scaled city's Census median (its page's 'Median home value') under the same cell."""
    labels = (label, 'Median home value') if label == 'Average price' else (label,)
    value = next((f['value'] for f in facts if f['label'] in labels), None)
    if value is None:
        return NONE_PUBLISHED
    value = str(value).removesuffix(' / 10')
    return f'<td class="score">{e(value)}</td>' if label == 'Sky Score' else f'<td>{e(value)}</td>'


def compare_table(city, entries) -> str:
    """One city's areas in one table: the figures their own pages publish, alphabetical."""
    label = CITY_LABEL.get(city, city.title())
    # A US-scaled city's price is a Census MEDIAN, so its column says so (its pages' own label).
    median = any(f['label'] == 'Median home value' for _, d in entries for f in d['facts'])
    head = ''.join(f'<th scope="col">{e("Median home value" if median and c == "Average price" else c)}</th>'
                   for c in COMPARE_COLUMNS)
    rows = '\n'.join(
        f'<tr><th scope="row"><a href="/area/{p}/">{e(d["borough"])}</a></th>'
        + ''.join(compare_cell(c, d['facts']) for c in COMPARE_COLUMNS) + '</tr>'
        for p, d in sorted(entries, key=lambda x: x[1]['borough'])
    )
    # Affordability and growth are scored within a currency pool: the US pages say so row by row, and the table
    # says it once, so nobody sets a New York figure beside a UK one.
    if app.CITIES[city].get('country') == 'United Kingdom':
        note = ''
    elif app.CITIES[city].get('growthNotScored'):
        # The Bay Area (2026-11-07): growth is not scored, and its inputs are on US scales.
        note = (f'<p class="key">Affordability is scored among {e(label)}\'s own areas, and growth is not scored here. '
                f'{e(bay_records.us_scales(len(app.CITIES[city]["boroughs"])))}</p>\n')
    else:
        note = (f'<p class="key">Affordability and growth are scored among {e(label)}\'s own areas: not comparable '
                'with UK scores.</p>\n')
    return (
        f'<div class="tw" role="region" aria-label="{e(label)}: areas compared" tabindex="0">\n'
        f'<table class="compare">\n<caption class="visually-hidden">{e(label)}: each area\'s Sky Score, its five '
        f'parts and its average price</caption>\n<thead><tr><th scope="col">Area</th>{head}</tr></thead>\n'
        f'<tbody>\n{rows}\n</tbody>\n</table>\n</div>\n{note}'
    )


# How the coverage sentence names each city outside the UK, in its order (the counts come from the pages).
ABROAD_WORDS = {'nyc': "New York's {n} boroughs", 'bayarea': '{n} Bay Area cities'}


def render_index(pages) -> str:
    """The /area/ index: one comparison table per city. Used by --write and by --check, so they cannot differ."""
    by_city: dict[str, list] = {}
    for path, data in pages:
        by_city.setdefault(data['city'], []).append((path, data))
    body = [f'<h2>{e(CITY_LABEL.get(city, city.title()))}</h2>\n' + compare_table(city, by_city[city])
            for city in sorted(by_city, key=lambda c: CITY_LABEL.get(c, c))]
    # ONE COVERAGE SENTENCE (2026-10-12). This index said "102 boroughs across 14 city
    # regions" while the front page, /api/, /reports/ and /open-data/ said 97 council areas in
    # 13: both true, one counting New York's boroughs in with the UK's, and read side by side
    # as two claims. Counted per country from the pages themselves, never typed.
    uk = [c for c in by_city if app.CITIES[c].get('country') == 'United Kingdom']
    abroad = [c for c in by_city if c not in uk]
    uk_n = sum(len(by_city[c]) for c in uk)
    # THE coverage sentence, word for word (CLAUDE.md; Bill, 2026-11-07: "plus New York's 5 boroughs and 50 Bay
    # Area cities"): each US city's words here, its count from the pages. A city with no words stops the build.
    unknown = sorted(set(abroad) - set(ABROAD_WORDS))
    if unknown:
        raise SystemExit(f'no coverage words for {unknown}: add them to ABROAD_WORDS')
    us = ' and '.join(ABROAD_WORDS[c].format(n=len(by_city[c])) for c in sorted(abroad, key=list(ABROAD_WORDS).index))
    coverage = f'{uk_n} council areas in {len(uk)} UK city regions' + (f', plus {us}' if us else '')
    # The coverage sentence word for word (tests/test_llms_txt.py's holder); the source clause goes when it will not fit.
    description = fit(f'Noise and liveability scores for {coverage}, from published UK government and US sources.',
                      f'Noise and liveability scores for {coverage}.')
    return INDEX.format(coverage=coverage, site=SITE, body='\n'.join(body), description=e(description))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    if not (args.write or args.check):
        ap.error('pass --write or --check')

    pages, thin, seen = [], [], {}
    for city, cfg in app.CITIES.items():
        # The API scores these and the site shows FACTS (app.SITE_FACTS_ONLY_CITIES, Bill 2026-10-22): an area
        # page is a published SCORE, so none is written until the city's site release crosses the one-way door.
        # Nor for a city the map scores whose pages are not built yet (app.AREA_PAGES_PENDING: the Bay Area,
        # 2026-11-07, whose US inputs need their own findings and notes here before a page can say them).
        if city in app.SITE_FACTS_ONLY_CITIES or city in app.AREA_PAGES_PENDING:
            continue
        for borough in sorted(cfg['boroughs']):
            data = gather(city, borough)
            if data is None:
                continue
            path = f'{slug(city)}/{slug(borough)}'
            if path in seen:
                print(f'FATAL: slug collision {path}: {seen[path]} vs {borough}')
                return 2
            seen[path] = borough
            if len(data['facts']) < MIN_FACTS:
                thin.append((path, len(data['facts'])))
                continue
            pages.append((path, data))

    print(f'{len(pages)} pages would be written; {len(thin)} skipped as too thin')
    if thin:
        for p, n in thin[:10]:
            print(f'  skipped {p}: {n} facts (< {MIN_FACTS})')

    if args.check:
        if not pages:
            print('FAIL: no pages generated at all')
            return 1
        if thin:
            # The module docstring has promised this since the file was
            # written; the code failed only on ZERO pages (audit M24), so 98
            # good pages and one doorway page read as OK.
            print(f'FAIL: {len(thin)} page(s) would carry fewer than {MIN_FACTS} facts')
            return 1
        # EVERY borough page, byte for byte (CRLF-blind), since 2026-11-01. Until then --check compared the index
        # only and left the pages to tests/area-page-freshness.mjs, which compares their SCORES with the live API
        # and so cannot see the planes overhead links: a district gaining or losing its page would have left the
        # pages linking a 404, or missing one, with every gate green.
        stale = [path for path, data in pages
                 if not (OUT / path / 'index.html').exists()
                 or (OUT / path / 'index.html').read_text(encoding='utf-8').replace('\r\n', '\n') != render(data)]
        if stale:
            print(f'FAIL: {len(stale)} area page(s) differ from what --write would write (scores, or the planes '
                  f'overhead links in {PLANES_BY_COUNCIL.name}) - run --write: {", ".join(stale[:5])}')
            return 1
        # And none on disk that --write no longer builds (a borough gone thin, or its city made facts-only):
        # area-deploy SYNCS area/, so a leftover page would be uploaded as current, stale scores and links included.
        leftover = sorted({p.parent.relative_to(OUT).as_posix() for p in OUT.glob('*/*/index.html')}
                          - {path for path, _ in pages})
        if leftover:
            print(f'FAIL: {len(leftover)} area page(s) on disk are no longer built - delete them: {", ".join(leftover[:5])}')
            return 1
        if sync_scorecards(pages, write=False):
            print('FAIL: index.html AREA_SCORECARDS is stale - run --write')
            return 1
        if sync_open_data(write=False):
            print('FAIL: open-data/ is stale against /v1/score - run --write')
            return 1
        # CRLF-blind: a Windows checkout rewrites line endings, and that is not staleness.
        on_disk = (OUT / 'index.html').read_text(encoding='utf-8').replace('\r\n', '\n')
        if on_disk != render_index(pages):
            print('FAIL: area/index.html is stale (its comparison tables bake scores) - run --write')
            return 1
        print('OK')
        return 0

    for path, data in pages:
        target = OUT / path / 'index.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(data), encoding='utf-8', newline='\n')

    (OUT / 'index.html').write_text(render_index(pages), encoding='utf-8', newline='\n')

    sync_scorecards(pages, write=True)
    sync_open_data(write=True)
    # LAST: it dates each URL by whether its file changed, so every file this
    # run writes (index.html's scorecard links and open-data/ included) must
    # already be on disk.
    write_sitemap([p for p, _ in pages])
    print(f'wrote {len(pages)} pages + index + sitemap + index.html scorecard links + open-data/')
    return 0


# --------------------------------------------------------------------------
# Scorecard links for the site's "not covered" panel (2026-09-27)
# --------------------------------------------------------------------------
# A postcode in an API-only city (BACKEND_ONLY_CITIES: no map, no chip) used to
# read NOT COVERED YET with nothing to follow, although a scorecard page for its
# borough existed under area/. index.html's renderOutsideCoverage() now links
# it, from a table written HERE, between markers, from the same list of pages
# this run writes - so the site can never link a page that was not generated,
# and a city leaving BACKEND_ONLY_CITIES drops out of the table by itself.
#
# Keyed on the ONS LAD CODE first, which postcodes.io returns for a full
# postcode (`codes.admin_district`), because name matching has failed in this
# repo five times. Names are the fallback for an OUTCODE search, whose response
# carries no codes: the registry name, lower-cased, plus the bare form of a
# "City of X" name, since ONS and postcodes.io write `Nottingham` where the
# registry holds `City of Nottingham`.
INDEX_HTML = REPO / 'index.html'
SCORECARDS_START = '// AREA-SCORECARDS:START (generated by scripts/build_area_pages.py --write; do not hand-edit)'
SCORECARDS_END = '// AREA-SCORECARDS:END'


@functools.cache
def backend_only_cities() -> frozenset[str]:
    """Read from its single holder, the way build_hpi_prices.py does.

    Cached, because render() asks once per page and each read imports a module.
    """
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location('bhp_area', REPO / 'scripts' / 'build_hpi_prices.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return frozenset(mod._backend_only_cities())  # noqa: SLF001 - the one reader of that holder


def scorecard_block(pages) -> str:
    backend_only = backend_only_cities()
    code_for = {(c, b): code for code, (c, b) in app.LAD_TO_BOROUGH.items()}
    rows = []
    for path, data in sorted(pages, key=lambda p: p[0]):
        city, borough = data['city'], data['borough']
        if city not in backend_only:
            continue
        code = code_for.get((city, borough))
        if code is None:
            raise SystemExit(f'{city}/{borough} has a page but no LAD_TO_BOROUGH code; refusing to key it by name alone')
        names = [borough.lower()]
        if borough.startswith('City of '):
            names.append(borough[len('City of '):].lower())
        rows.append(
            f"        {{ code: '{code}', names: {json.dumps(names)}, city: {json.dumps(app.CITIES[city]['name'])}, "
            f"borough: {json.dumps(borough)}, url: '/area/{path}/' }},"
        )
    if not rows:
        raise SystemExit('no API-only borough has a page; refusing to write an empty scorecard table')
    return '\n'.join(['      const AREA_SCORECARDS = [', *rows, '      ];'])


def sync_scorecards(pages, write: bool) -> bool:
    """True if index.html's block is (or, with write, was) out of date."""
    src = INDEX_HTML.read_text(encoding='utf-8')
    crlf = '\r\n' in src
    text = src.replace('\r\n', '\n')
    i, j = text.find(SCORECARDS_START), text.find(SCORECARDS_END)
    if i < 0 or j < 0:
        raise SystemExit('index.html: AREA-SCORECARDS markers not found')
    new = f'{SCORECARDS_START}\n{scorecard_block(pages)}\n      {SCORECARDS_END}'
    old = text[i : j + len(SCORECARDS_END)]
    if old == new:
        return False
    if write:
        out = text[:i] + new + text[j + len(SCORECARDS_END):]
        INDEX_HTML.write_text(out.replace('\n', '\r\n') if crlf else out, encoding='utf-8', newline='')
    return True


# --------------------------------------------------------------------------
# Open data download (2026-09-28)
# --------------------------------------------------------------------------
# One CSV of every UK borough's published score and inputs, plus a page that
# says what each column is and where it comes from. Built HERE, from the same
# resolve_query() the area pages and /v1/score use, in the same run: a second
# script would be a second holder of the scores, and the first vintage roll
# that reran one and not the other would publish two answers.
#
# UK rows only. New York's inputs come from US publishers under their own
# terms, and one licence line has to be true of every row.
#
# No timestamp in the file, so --check can regenerate it and compare byte for
# byte; the price vintage and methodology version say how current it is.
OPEN_DATA = REPO / 'open-data'
OPEN_DATA_CSV = 'sky-score-boroughs.csv'

# (column, what it is). The page's table is generated from this list, so the
# documentation cannot describe a column the file does not have.
OPEN_DATA_COLUMNS = [
    ('city', 'Sky Score city key'),
    ('city_name', 'City region'),
    ('borough', 'Borough or district, as Sky Score names it'),
    ('ons_code', 'ONS local authority code, for joining to other datasets'),
    ('coverage', '"map and API", or "API preview" for areas not yet on the map'),
    ('score', 'Sky Score, 0-10 (10 is best), with the balanced weighting'),
    ('quiet', 'Quiet skies component, 0-10 (higher is quieter)'),
    ('afford', 'Affordability component, 0-10, national log scale'),
    ('growth', 'Price growth component, 0-10, real terms'),
    ('live', 'Liveability component, 0-10'),
    ('env', 'Environment component, 0-10 (air, road noise, flood)'),
    ('avg_price_gbp', 'Average price, HM Land Registry UK House Price Index'),
    ('price_trend_pct', '12-month price change, nominal, %'),
    ('price_trend_real_pct', '12-month price change after ONS CPIH inflation, %'),
    ('crime_per_1000', 'Recorded offences excluding fraud per 1,000 residents, ONS Table C4'),
    ('progress8', 'DfE Progress 8, 2023/24 (England only; blank where not published)'),
    ('rail_within_800m_pct', 'Share of postcodes within 800 m of a rail, metro or tram stop (NaPTAN), %'),
    ('healthcare_within_500m_pct', 'Share of postcodes within 500 m of a GP practice (NHS Organisation Data Service), %'),
    ('air_quality_who_ratio', 'Worse of NO2 and PM2.5 as a multiple of the WHO 2021 guideline (DEFRA)'),
    # Added 2026-09-29: journalists and researchers recognise the pollutants, not our ratio.
    # Blank for the API-preview areas, whose borough averages are derived but not yet held.
    ('no2_ugm3', 'Nitrogen dioxide, borough average of the DEFRA background annual mean, ug/m3 (WHO guideline 10; blank for API-preview areas)'),
    ('pm25_ugm3', 'Fine particles (PM2.5), borough average of the DEFRA background annual mean, ug/m3 (WHO guideline 5; blank for API-preview areas)'),
    ('road_noise_above_who_pct', 'Share of postcodes above the WHO 53 dB Lden road guideline (DEFRA Round 4), %'),
    ('flood_medium_or_high_pct', 'Share of postcodes at Medium or High flood risk (Environment Agency, Risk of Flooding from Rivers and Sea), %'),
    ('methodology_version', 'Sky Score methodology version the scores were computed under'),
    ('price_vintage', 'UK House Price Index month the prices are from'),
]


def open_data_rows() -> list[list]:
    """One row per UK borough the API scores, sorted, absent values blank."""
    backend_only = backend_only_cities()
    code_for = {(c, b): code for code, (c, b) in app.LAD_TO_BOROUGH.items()}
    rows = []
    for city in sorted(app.CITIES):
        # UK only, by REGISTRY: the file is published under the OGL, which covers no US data. This was
        # `city == 'nyc'`, which would have put the Bay Area's 50 cities in the UK file the day it was scored.
        if app.CITIES[city].get('country') != 'United Kingdom':
            continue
        for borough in sorted(app.CITIES[city]['boroughs']):
            body, status = app.resolve_query({'borough': borough, 'city': city})
            if status != 200 or not isinstance(body.get('score'), (int, float)):
                raise SystemExit(f'open data: {city}/{borough} did not score ({status}); refusing a partial file')
            comp, ctx = body.get('components') or {}, body.get('context') or {}
            rec, painted = app.CITIES[city]['boroughs'][borough], _painted_for(city, borough)

            def first(*vals):
                return next((v for v in vals if v not in (None, '')), '')

            rows.append([
                city, CITY_LABEL.get(city, city.title()), borough, code_for.get((city, borough), ''),
                'API preview' if city in backend_only else 'map and API',
                body['score'], comp.get('quiet', ''), comp.get('afford', ''), comp.get('growth', ''),
                comp.get('live', ''), comp.get('env', ''),
                first(ctx.get('avgPriceGbp')), first(ctx.get('priceTrendPct')), first(ctx.get('priceTrendRealPct')),
                first(rec.get('crimeRate')), first(rec.get('p8')),
                first(painted.get('transportWithin800mPct')), first(painted.get('healthcareWithin500mPct')),
                first(rec.get('airQualityWhoRatio'), painted.get('airQualityWhoRatio')),
                first(painted.get('no2AnnualMeanUgm3')), first(painted.get('pm25AnnualMeanUgm3')),
                first(rec.get('roadNoiseAboveWhoPct'), painted.get('roadNoiseAboveWhoPct')),
                first(rec.get('floodMediumOrHighPct'), painted.get('floodMediumOrHighPct')),
                body.get('methodologyVersion', ''), app.SNAPSHOT_VINTAGE_LABEL,
            ])
    return rows


def open_data_csv(rows) -> str:
    import csv  # noqa: PLC0415
    import io  # noqa: PLC0415

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow([c for c, _ in OPEN_DATA_COLUMNS])
    w.writerows(rows)
    return buf.getvalue()


OPEN_DATA_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Open data - Sky Score</title>
<meta name="description" content="Download Sky Score's borough-level scores and inputs for {n} UK areas as one CSV: aircraft and road noise, air quality, flood risk, crime, schools and prices, from official public data." />
<link rel="canonical" href="{site}/open-data/" />
<meta property="og:type" content="website" />
<meta property="og:url" content="{site}/open-data/" />
<meta property="og:title" content="Open data - Sky Score" />
<meta property="og:description" content="Every UK area Sky Score covers in one CSV: aircraft and road noise, air quality, flood risk, crime, schools and prices. Free for non-commercial use." />
<meta property="og:site_name" content="Sky Score" />
<link rel="icon" href="/favicon.ico" sizes="32x32" />
<link rel="icon" href="/icons/favicon.svg" type="image/svg+xml" />
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
<link rel="stylesheet" href="/fonts/fonts.css" />
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: https://cubitt33.goatcounter.com; connect-src https://cubitt33.goatcounter.com; base-uri 'self'; form-action 'self';" />
<style>
  :root {{ color-scheme: light dark;
    """ + PALETTE_LIGHT + """ }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:'Inter',system-ui,sans-serif; color:var(--dark); background:var(--bg); line-height:1.6; }}
  a:focus-visible {{ outline:3px solid var(--focus); outline-offset:2px; }}
  .wrap {{ max-width:760px; margin:0 auto; padding:24px 20px 64px; }}
  a {{ color:var(--orange-ink); }}
  nav.crumbs {{ font-size:12px; color:var(--mid); margin-bottom:20px; }}
  h1 {{ font-family:var(--font-display); font-size:32px; font-weight:700; letter-spacing:-0.02em; line-height:1.2; margin:0 0 6px; }}
  h2 {{ font-size:18px; margin:32px 0 8px; }}
  .sub {{ color:var(--mid); margin:0 0 20px; }}
  .dl {{ display:inline-block; padding:12px 18px; border:1px solid var(--line); border-radius:10px; background:var(--paper); font-weight:600; }}
  .tw {{ overflow-x:auto; }}
  .tw:focus-visible {{ outline:2px solid var(--focus); outline-offset:2px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-weight:600; }}
  code {{ font-family:'JetBrains Mono',ui-monospace,monospace; font-size:12px; }}
  footer {{ margin-top:40px; font-size:12px; color:var(--mid); }}
  /* The site bar (2026-10-06): the front page's header.top, in this page's own font and colours. */
  .site-top {{ display:flex; align-items:center; justify-content:space-between; gap:8px 16px; flex-wrap:wrap; padding:14px clamp(16px, 4vw, 48px); }}
  .site-top .site-brand {{ font-weight:700; font-size:18px; letter-spacing:-0.01em; text-decoration:none; color:var(--dark); }}
  .site-top .site-nav {{ display:flex; gap:4px; flex-wrap:wrap; }}
  .site-top .site-nav {{ align-items:center; }}
  .site-top .site-nav a {{ font-size:14px; font-weight:500; text-decoration:none; padding:8px 12px; border-radius:8px; color:var(--dark); }}
  /* 'You are here' is an underline and Full map an outlined button (Bill, 2026-10-06): --focus, past the 3:1 a state cue needs. */
  .site-top .site-nav a.nav-cta {{ box-shadow: inset 0 0 0 1.5px var(--dark); font-weight:600; }}
  .site-top .site-nav a:hover {{ text-decoration: underline; text-decoration-thickness: 1.5px; text-underline-offset: 7px; }}
  .site-top .site-nav a[aria-current] {{ text-decoration: underline; text-decoration-color: var(--focus); text-decoration-thickness: 3px; text-underline-offset: 7px; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ """ + PALETTE_DARK + """ }}
  }}
  /* The phone menu (2026-10-23). Below 680 px the name and the six links no longer share a row, so the links
     fold behind a Menu button. It is a popover, so it needs no script (privacy and terms allow none, the area
     pages carry none), and a browser without popovers keeps the plain bar. On a wide screen the closed popover
     IS the ordinary row of links, so the browser's popover box is undone first. */
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
</style>
</head>
<body>
<!-- The site bar, the same on every page since 2026-10-06 (the front page's header.top). -->
<nav class="site-top" aria-label="Site"><a class="site-brand" href="/">Sky Score</a><button type="button" class="menu-btn" popovertarget="site-nav">Menu</button><div class="site-nav" id="site-nav" popover><button type="button" class="menu-close" popovertarget="site-nav" popovertargetaction="hide">Close</button><a class="nav-cta" href="/map/">Full map</a><a href="/reports/">Reports</a><a href="/how-it-works/">How it works</a><a href="/pricing">Pricing</a><a href="/api/">API</a><a href="/about/">About</a></div></nav>
<div class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Sky Score</a> &rsaquo; Open data</nav>
{crumbs_ld}
<main>
<h1>Open data</h1>
<p class="sub">Every UK area Sky Score covers, in one file: the published score, its five components and the measurements behind them. {n} areas across {c} city regions. Prices: {vintage} UK House Price Index. Methodology version {methodology}.</p>
<p><a class="dl" href="/open-data/{csv}" download>Download {csv} (CSV)</a></p>

<h2>Licence and attribution</h2>
<p>{licence}</p>
<p>Built from official public data. Most of it is used under the <a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/">Open Government Licence v3.0</a>; the aircraft noise estimate also uses the flight routes of the UK Aeronautical Information Publication (NATS), which is public but not openly licensed. If you reuse this file, please also credit the original publishers: DEFRA (noise and air quality), the Environment Agency (flood risk), ONS (crime, postcode lookup), the Department for Education (Progress 8), HM Land Registry (prices), the Department for Transport (NaPTAN), the NHS Organisation Data Service (GP practices) and the UK AIP, NATS (flight routes).</p>

<h2>What each column means</h2>
<div class="tw" tabindex="0" role="region" aria-label="What each column means, scrolls sideways on a narrow screen">
<table>
<caption class="visually-hidden" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">Columns in {csv}</caption>
<thead><tr><th scope="col">Column</th><th scope="col">Meaning</th></tr></thead>
<tbody>
{columns}
</tbody>
</table>
</div>

<h2>Read before using</h2>
<p>These are borough-wide figures; a single address can differ, and aircraft noise especially varies by 10-15 dB within a borough. DEFRA's noise maps describe 2021, a lockdown year: its Heathrow 55 dB contour is about half the area of the Civil Aviation Authority's 2024 figure. Blank cells mean a figure is not published for that area, never zero. The method behind every column is in the <a href="https://github.com/billkhiz-bit/london-flight-path-map/blob/master/METHODOLOGY.md">methodology</a>, and the same figures are available per postcode through the <a href="/api/">API</a>.</p>
</main>
<footer>
<p><a href="/">Sky Score</a> &middot; <a href="/map/">Full map</a> &middot; <a href="/reports/">Reports</a> &middot; <a href="/area/">All areas</a> &middot; <a href="/how-it-works/">How it works</a> &middot; <a href="/about/">About</a> &middot; <a href="/api/">For developers</a> &middot; <a href="/privacy">Privacy</a> &middot; <a href="/terms">Terms</a></p>
</footer>
</div>
<script type="module" src="/js/count.mjs"></script>
</body>
</html>
"""

# DECIDED BY BILL 2026-09-28: no competitor reselling. CC BY-NC 4.0, plus an
# explicit extra grant for journalism and academic research, because "non-
# commercial" is fuzzy and would otherwise deter exactly the reuse wanted (a
# newspaper is a business). A licensor may grant MORE than the licence, never
# less. Bulk resale or product use needs written permission.
OPEN_DATA_LICENCE = (
    'Sky Score’s scores in this file are released under '
    '<a href="https://creativecommons.org/licenses/by-nc/4.0/">Creative Commons Attribution-NonCommercial 4.0</a>: '
    'free to use, share and adapt for non-commercial purposes, with credit to "Sky Score (skyscore.co.uk)". '
    '<strong>In addition</strong>, journalists may publish figures, tables and charts from it in news reporting, '
    'including in commercial publications, and academic researchers may use it in published research, in each case '
    'with that credit. Reselling the dataset, redistributing it in bulk for commercial purposes, or building it into a '
    'commercial product or service needs written permission: <a href="mailto:support@skyscore.co.uk">support@skyscore.co.uk</a>.'
)


def open_data_files() -> dict[str, str]:
    rows = open_data_rows()
    columns = '\n'.join(f'<tr><td><code>{e(c)}</code></td><td>{e(d)}</td></tr>' for c, d in OPEN_DATA_COLUMNS)
    page = OPEN_DATA_PAGE.format(
        n=len(rows), c=len({r[0] for r in rows}), site=SITE, csv=OPEN_DATA_CSV,
        vintage=e(app.SNAPSHOT_VINTAGE_LABEL), methodology=e(app.METHODOLOGY_VERSION),
        licence=OPEN_DATA_LICENCE, columns=columns,
        crumbs_ld=breadcrumb_ld([('Sky Score', '/'), ('Open data', '/open-data/')]))
    return {OPEN_DATA_CSV: open_data_csv(rows), 'index.html': page}


def sync_open_data(write: bool) -> bool:
    """True if open-data/ is (or, with write, was) out of date."""
    stale = False
    for name, content in open_data_files().items():
        path = OPEN_DATA / name
        current = path.read_text(encoding='utf-8').replace('\r\n', '\n') if path.exists() else None
        if current != content:
            stale = True
            if write:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8', newline='\n')
    return stale


STATIC_URLS = [
    ('/', '1.0', 'weekly'),
    ('/map/', '0.9', 'weekly'),
    ('/reports/', '0.8', 'monthly'),
    ('/reports/street/', '0.8', 'monthly'),
    ('/how-it-works/', '0.7', 'monthly'),
    ('/about/', '0.6', 'monthly'),
    ('/open-data/', '0.7', 'monthly'),
    ('/bay-area/', '0.8', 'monthly'),
    ('/pricing', '0.8', 'monthly'),
    ('/privacy', '0.3', 'yearly'),
    ('/terms', '0.3', 'yearly'),
    ('/changes', '0.4', 'monthly'),
    ('/api/', '0.9', 'monthly'),
    ('/score-demo/', '0.7', 'monthly'),
    ('/score-demo/api-docs.html', '0.6', 'monthly'),
    # Never /score-demo/status.html: it asks search engines not to index it (a status page), and a sitemap
    # listing a noindex page is a contradiction Google reports. It was listed until 2026-11-09, when Search
    # Console emailed "Excluded by 'noindex' tag" for a sitemap page. write_sitemap() now refuses one.
]

# A page that asks search engines not to index it, read from its own <meta name="robots"> (or "googlebot"): the
# only place our pages say it, as CloudFront sends no X-Robots-Tag. Attributes in either order, any case.
META_TAG = re.compile(r'<meta\b[^>]*>', re.IGNORECASE)
META_ATTR = re.compile(r'([a-z-]+)\s*=\s*["\']([^"\']*)["\']')


def noindex_in(text: str) -> bool:
    """True when `text` holds a robots meta tag whose content includes noindex."""
    for tag in META_TAG.findall(text):
        attrs = dict(META_ATTR.findall(tag.lower()))
        if attrs.get('name') in ('robots', 'googlebot') and 'noindex' in attrs.get('content', ''):
            return True
    return False


def asks_noindex(path: str) -> bool:
    """True when the repo file at `path` asks search engines not to index it."""
    return noindex_in((REPO / path).read_text(encoding='utf-8'))


# URLs whose file is not at the same path in the repo (2026-10-06): the front page
# took /, the full map (still index.html, which a dozen scripts write into) moved
# to /map/, and the reports pages live beside the front page in home/. Their
# deploy keys are in the Makefile (web-deploy, home-deploy).
MOVED_SOURCES = {
    '/': 'home/index.html',
    '/map/': 'index.html',
    '/reports/': 'home/reports/index.html',
    '/reports/street/': 'home/reports/street/index.html',
}


def source_file(loc: str) -> str:
    """The repo file a sitemap URL serves, as CloudFront's rewrite maps it."""
    if loc in MOVED_SOURCES:
        return MOVED_SOURCES[loc]
    if loc.endswith('/'):
        return loc[1:] + 'index.html'
    return loc[1:] if loc.endswith('.html') else loc[1:] + '.html'


def last_changed(files: list[str]) -> dict[str, str]:
    """{repo file: YYYY-MM-DD its content last changed}, read from git.

    A file that differs from HEAD, or that git has never seen, changed today;
    otherwise it is the date of the last commit that touched it. Until
    2026-10-01 every URL carried the build date, so one changed page told
    crawlers that all 112 had changed - and a lastmod that always says "today"
    is one a crawler learns to ignore (Google reads it only where it is
    "consistently and verifiably accurate").
    """
    today = datetime.now(UTC).strftime('%Y-%m-%d')

    def git(*args: str) -> str:
        # Literal arguments and paths this script built; nothing user-supplied.
        return subprocess.run(['git', *args, '--', *files], cwd=REPO, capture_output=True,  # noqa: S603, S607
                              text=True, encoding='utf-8', check=True).stdout

    try:
        status = git('status', '--porcelain', '--untracked-files=all')
        # --first-parent -m: master's own history, each merge listing what it brought in. Plain --name-only lists
        # no files for a merge, so a page merged from a branch (--no-ff) was dated by the BRANCH commit, the day it
        # was written, not the day it reached master: /area/'s comparison tables (written 26 Oct, merged 31 Oct)
        # dated themselves 26 Oct on 2026-11-01. A FAST-FORWARD keeps the branch commits on master's own line, so
        # they still carry the day they were committed: git holds no record of when a fast-forward happened.
        log = git('log', '--first-parent', '-m', '--format=%x00%cs', '--name-only')
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'WARNING: git unavailable ({exc}); every sitemap URL is dated today')
        return dict.fromkeys(files, today)
    dates: dict[str, str] = {}
    when = None
    for line in log.splitlines():
        if line.startswith('\x00'):
            when = line[1:]
        elif line and line not in dates:
            dates[line] = when  # newest first, so the first sighting is the last change
    for line in status.splitlines():
        dates[line[3:].split(' -> ')[-1].strip('"')] = today
    return {f: dates.get(f, today) for f in files}


def write_sitemap(paths: list[str]) -> None:
    """Rewrite sitemap.xml from what was actually generated.

    Generated, never hand-edited: a sitemap listing a page that does not exist
    is a crawl error on every miss, and one omitting pages that do exist wastes
    the whole exercise. Deriving it from the same list that wrote the files
    means the two cannot disagree. Each lastmod is the date that URL's file
    last changed (last_changed), never the date of the build.
    """
    urls = [(loc, prio, freq) for loc, prio, freq in STATIC_URLS]
    urls.append(('/area/', '0.8', 'monthly'))
    urls += [(f'/area/{p}/', '0.6', 'monthly') for p in sorted(paths)]
    files = [source_file(loc) for loc, _, _ in urls]
    missing = [f for f in files if not (REPO / f).exists()]
    if missing:
        raise SystemExit(f'sitemap URLs with no file behind them: {missing}')
    hidden = [f for f in files if asks_noindex(f)]
    if hidden:
        # Refuse rather than drop: either the page should be indexed (remove its noindex) or it should not be
        # listed (remove it from STATIC_URLS). Only a person can say which.
        raise SystemExit(f'sitemap URLs whose page asks not to be indexed: {hidden}')
    dated = last_changed(files)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for (loc, prio, freq), f in zip(urls, files, strict=True):
        out.append(f'  <url><loc>{SITE}{loc}</loc><lastmod>{dated[f]}</lastmod>'
                   f'<changefreq>{freq}</changefreq><priority>{prio}</priority></url>')
    out.append('</urlset>')
    (REPO / 'sitemap.xml').write_text('\n'.join(out) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    raise SystemExit(main())
