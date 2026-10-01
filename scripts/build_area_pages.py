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
compares the two and will go red until the pages are regenerated and redeployed:

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
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))

import app  # noqa: E402  pylint: disable=wrong-import-position

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

CITY_LABEL = {
    'london': 'London',
    'manchester': 'Greater Manchester',
    'westmidlands': 'West Midlands',
    'westyorkshire': 'West Yorkshire',
    'southyorkshire': 'South Yorkshire',
    'merseyside': 'Merseyside',
    'tyneandwear': 'Tyne and Wear',
    'bristol': 'Bristol',
    'leicester': 'Leicestershire',
    'teesside': 'Teesside',
    'nottingham': 'Nottinghamshire',
    'norwich': 'Greater Norwich',
    'cardiff': 'Cardiff',
    'nyc': 'New York City',
}


def slug(text: str) -> str:
    """URL slug. Kept deliberately lossy-but-stable.

    A borough name is the only input, so collisions are checked by the caller
    rather than guarded against here - a silent collision would overwrite one
    borough's page with another's, which is the WA8 join defect in a new place.
    """
    s = re.sub(r"[^a-z0-9]+", '-', text.lower()).strip('-')
    return re.sub(r'-{2,}', '-', s)


def e(text) -> str:
    return html.escape(str(text), quote=True)


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
    afford_note = 'Scored against borough prices across the whole country, not just this city'
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

    add('Average price', fmt_price(ctx.get('avgPriceGbp')), uk_note('HM Land Registry HPI'))
    trend = ctx.get('priceTrendPct')
    if isinstance(trend, (int, float)):
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
        'mapped': 'Estimated from airport geometry, ladder scaled by the DEFRA Round 4 footprint',
        'unmapped': 'Estimated from airport geometry; DEFRA Round 4 does not map this airport',
        'none': 'No commercial airport in this city region',
    }.get(contour)
    add('Aircraft noise band', (ctx.get('noiseImpactBand') or '').title() or None,
        uk_note(aircraft_note))

    merged = {**painted, **{k: v for k, v in scoring.items() if v is not None}}
    for key, label, note in (
        ('crimeRate', 'Recorded crime', 'ONS Table C4, per 1,000 residents per year'),
        ('p8', 'Progress 8', 'DfE KS4 2023/24 revised, 0.0 is the national average'),
        ('roadNoise', 'Road noise', 'DEFRA road Lden, share of addresses over WHO 53 dB'),
        ('airQuality', 'Air quality', 'DEFRA background maps against WHO 2021'),
        ('flood', 'Flood risk', 'Environment Agency RoFRS, risk after defences'),
        ('transport', 'Transport access', 'NaPTAN, share of postcodes within 800 m of a station'),
        ('healthcare', 'Healthcare access', 'NHS ODS'),
    ):
        raw = merged.get(key)
        if raw in (None, ''):
            continue
        # City of London's crime rate is OUR OWN estimate - ONS suppresses the
        # rate for its small resident population, and the crime gate prints
        # "must not be attributed to ONS" on every run. This page credited ONS
        # for it anyway.
        if key == 'crimeRate' and scoring.get('crimeEstimated'):
            note = 'Sky Score estimate - ONS publishes no rate for this area'
        add(label, f'{raw:g}' if isinstance(raw, (int, float)) else str(raw).title(), uk_note(note))

    return {
        'city': city,
        'borough': borough,
        'score': body['score'],
        'facts': facts,
        'sources': body.get('sources') or [],
        'methodology': body.get('methodologyVersion'),
    }


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
<link rel="stylesheet" href="/fonts/fonts.css" />
<style>
  /* `color-scheme` declared 2026-09-02 (audit D11). These pages carry a
     prefers-color-scheme block below, so they REPAINT for dark mode - but
     without this the browser still renders its own furniture (scrollbars,
     and the canvas painted before our CSS applies) in light, so a dark-mode
     reader gets a white flash and a light scrollbar against a #141414 page.
     Declaring it is what makes the dark block honest. */
  :root {{ color-scheme: light dark;
    --dark:#141414; --mid:#636363; --line:#e7e5e4; --bg:#fafaf9; --orange:#c2410c; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:0; font-family:'Inter',system-ui,sans-serif; color:var(--dark); background:#fff; line-height:1.6; }}
  .wrap {{ max-width:720px; margin:0 auto; padding:24px 20px 64px; }}
  a {{ color:var(--orange); }}
  nav.crumbs {{ font-size:12px; color:var(--mid); margin-bottom:20px; }}
  h1 {{ font-size:28px; line-height:1.25; margin:0 0 6px; }}
  .sub {{ color:var(--mid); font-size:14px; margin:0 0 24px; }}
  .headline {{ display:flex; align-items:baseline; gap:10px; padding:16px 18px; background:var(--bg); border:1px solid var(--line); border-radius:8px; margin-bottom:24px; }}
  .headline .n {{ font-size:34px; font-weight:700; }}
  .headline .of {{ color:var(--mid); font-size:14px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th, td {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ width:42%; font-weight:600; }}
  td .note {{ display:block; color:var(--mid); font-size:11px; }}
  .tw {{ overflow-x:auto; }}
  /* The caption names the table for a screen reader without adding a
     visible heading. Defined here because these pages ship their own
     CSS and do not load the app stylesheet. */
  .visually-hidden {{ position:absolute; width:1px; height:1px; padding:0;
    margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }}
  h2 {{ font-size:16px; margin:32px 0 8px; }}
  .sources {{ font-size:12px; color:var(--mid); }}
  .cta {{ margin:28px 0; padding:16px 18px; border:1px solid var(--line); border-radius:8px; }}
  footer {{ margin-top:40px; font-size:12px; color:var(--mid); }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --dark:#f5f5f4; --mid:#a1a1a1; --line:#3a3a3a; --bg:#1c1c1c; --orange:#fb923c; }}
    body {{ background:#141414; }}
  }}
</style>
</head>
<body>
<div class="wrap">
<nav class="crumbs"><a href="/">Sky Score</a> &rsaquo; <a href="/area/">Areas</a> &rsaquo; {city_label}</nav>
<main data-city="{city}" data-borough="{borough}">
<h1>{borough} noise and liveability</h1>
<p class="sub">{city_label}. Aircraft and road noise, affordability, schools, crime and access, from published sources.</p>

<div class="headline"><span class="n">{score}</span><span class="of">Sky Score out of 10</span></div>

<div class="tw">
<table>
<caption class="visually-hidden">Published measurements for {borough}</caption>
<tbody>
{rows}
</tbody>
</table>
</div>

{cta}

<h2>Where these numbers come from</h2>
<p class="sources">{sources}</p>
<p class="sources">Methodology version {methodology}. Full method: <a href="/score-demo/api-docs.html">API reference</a>.
Figures are for the whole borough; a single address can differ{map_note}.</p>
</main>

<footer>
<p><a href="/">Sky Score</a> &middot; <a href="/area/">All areas</a> &middot; <a href="/api/">For developers</a> &middot; <a href="/privacy">Privacy</a></p>
</footer>
</div>
</body>
</html>
"""


def render(data: dict) -> str:
    city_label = CITY_LABEL.get(data['city'], data['city'].title())
    rows = '\n'.join(
        '<tr><th scope="row">{}</th><td>{}{}</td></tr>'.format(
            e(f['label']),
            e(f['value']),
            f'<span class="note">{e(f["note"])}</span>' if f.get('note') else '',
        )
        for f in data['facts']
    )
    # THE META DESCRIPTION NAMED UK BODIES FOR NEW YORK TOO (2026-08-31, C3).
    #
    # This is the text that appears in a SEARCH RESULT, so "Brooklyn ... from
    # DEFRA, ONS, DfE and HM Land Registry data" was a false provenance claim on
    # the most public surface the page has - and it survived the per-fact note
    # fix, because it is built here and not there. Found by the gate written for
    # the notes, which is the argument for writing the gate.
    uk_city = app.CITIES[data['city']].get('country') == 'United Kingdom'
    source_clause = (
        'from DEFRA, ONS, DfE and HM Land Registry data'
        if uk_city
        else 'from public New York City sources'
    )
    desc = (
        f"{data['borough']} scores {data['score']} out of 10 on Sky Score. "
        f"Aircraft and road noise, affordability, schools, crime and transport "
        f"for {data['borough']}, {city_label}, {source_clause}."
    )[:300]
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
            f'  <p style="margin:0 0 8px;"><strong>Not on the map yet.</strong> {e(city_label)} is a preview: '
            'these borough figures are published, but the interactive map does not cover it yet.</p>\n'
            '  <a href="/area/">See every area Sky Score covers</a>\n'
            '</div>'
        )
        map_note = ''
    else:
        cta = (
            '<div class="cta">\n'
            '  <p style="margin:0 0 8px;"><strong>See it on the map.</strong> Noise contours, flight corridors '
            f'and every neighbourhood in {e(city_label)}.</p>\n'
            f'  <a href="/?city={e(data["city"])}&amp;borough={e(data["borough"].replace(" ", "+"))}">'
            f'Open {e(data["borough"])} on the Sky Score map</a>\n'
            '</div>'
        )
        map_note = ', and the map shows postcode-level detail'
    return PAGE.format(
        title=e(f"{data['borough']} noise & liveability score | Sky Score"),
        description=e(desc),
        canonical=f"{SITE}/area/{slug(data['city'])}/{slug(data['borough'])}/",
        city_label=e(city_label),
        # `city` feeds data-city on <main>: the page's machine-readable identity,
        # which tests/area-page-freshness.mjs reads. It used to read the map
        # link, and a preview page has no map link (2026-09-30).
        city=e(data['city']),
        borough=e(data['borough']),
        cta=cta,
        map_note=map_note,
        score=e(data['score']),
        rows=rows,
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
        sources=e('; '.join(str(s) for s in data['sources']) or 'See methodology.'),
        methodology=e(data['methodology'] or ''),
    )


INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Every area Sky Score covers | Sky Score</title>
<meta name="description" content="Noise and liveability scores for {n} boroughs across {c} UK and US city regions, from published UK government and New York City sources." />
<link rel="canonical" href="{site}/area/" />
<link rel="stylesheet" href="/fonts/fonts.css" />
<style>
  /* See the note on the borough template: same reason, same fix. */
  :root {{ color-scheme: light dark;
    --dark:#141414; --mid:#636363; --line:#e7e5e4; --orange:#c2410c; }}
  body {{ margin:0; font-family:'Inter',system-ui,sans-serif; color:var(--dark); line-height:1.6; }}
  .wrap {{ max-width:720px; margin:0 auto; padding:24px 20px 64px; }}
  a {{ color:var(--orange); }}
  h1 {{ font-size:28px; margin:0 0 6px; }}
  h2 {{ font-size:16px; margin:28px 0 6px; }}
  ul {{ margin:0; padding-left:18px; }}
  li {{ margin:2px 0; }}
  .sub {{ color:var(--mid); font-size:14px; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --dark:#f5f5f4; --mid:#a1a1a1; --line:#3a3a3a; --orange:#fb923c; }}
    body {{ background:#141414; }}
  }}
</style>
</head>
<body>
<div class="wrap">
<nav class="sub"><a href="/">Sky Score</a> &rsaquo; Areas</nav>
<main>
<h1>Every area we cover</h1>
<p class="sub">{n} boroughs across {c} city regions. Each page carries the published measurements behind that area's score.</p>
<p class="sub">All of it in one file: <a href="/open-data/">download the open data (CSV)</a>.</p>
{body}
<p class="sub" style="margin-top:32px;"><a href="/">Back to the map</a> &middot; <a href="/api/">For developers</a></p>
</main>
</div>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    if not (args.write or args.check):
        ap.error('pass --write or --check')

    pages, thin, seen = [], [], {}
    for city, cfg in app.CITIES.items():
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
        if sync_scorecards(pages, write=False):
            print('FAIL: index.html AREA_SCORECARDS is stale - run --write')
            return 1
        if sync_open_data(write=False):
            print('FAIL: open-data/ is stale against /v1/score - run --write')
            return 1
        print('OK')
        return 0

    for path, data in pages:
        target = OUT / path / 'index.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(data), encoding='utf-8', newline='\n')

    by_city: dict[str, list] = {}
    for path, data in pages:
        by_city.setdefault(data['city'], []).append((path, data['borough']))
    body = []
    for city in sorted(by_city, key=lambda c: CITY_LABEL.get(c, c)):
        items = '\n'.join(
            f'<li><a href="/area/{p}/">{e(b)}</a></li>' for p, b in sorted(by_city[city], key=lambda x: x[1])
        )
        body.append(f'<h2>{e(CITY_LABEL.get(city, city.title()))}</h2>\n<ul>\n{items}\n</ul>')
    (OUT / 'index.html').write_text(
        INDEX.format(n=len(pages), c=len(by_city), site=SITE, body='\n'.join(body)),
        encoding='utf-8', newline='\n')

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
    ('score', 'Sky Score, 0-10, balanced persona'),
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
    ('healthcare_within_500m_pct', 'Share of postcodes within 500 m of a GP practice (NHS ODS), %'),
    ('air_quality_who_ratio', 'Worse of NO2 and PM2.5 as a multiple of the WHO 2021 guideline (DEFRA)'),
    # Added 2026-09-29: journalists and researchers recognise the pollutants, not our ratio.
    # Blank for the API-preview areas, whose borough averages are derived but not yet held.
    ('no2_ugm3', 'Nitrogen dioxide, borough average of the DEFRA background annual mean, ug/m3 (WHO guideline 10; blank for API-preview areas)'),
    ('pm25_ugm3', 'Fine particles (PM2.5), borough average of the DEFRA background annual mean, ug/m3 (WHO guideline 5; blank for API-preview areas)'),
    ('road_noise_above_who_pct', 'Share of postcodes above the WHO 53 dB Lden road guideline (DEFRA Round 4), %'),
    ('flood_medium_or_high_pct', 'Share of postcodes at Medium or High flood risk (Environment Agency RoFRS), %'),
    ('methodology_version', 'Sky Score methodology version the scores were computed under'),
    ('price_vintage', 'UK House Price Index month the prices are from'),
]


def open_data_rows() -> list[list]:
    """One row per UK borough the API scores, sorted, absent values blank."""
    backend_only = backend_only_cities()
    code_for = {(c, b): code for code, (c, b) in app.LAD_TO_BOROUGH.items()}
    rows = []
    for city in sorted(app.CITIES):
        if city == 'nyc':
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
<meta name="description" content="Download Sky Score's borough-level scores and inputs for {n} UK areas as one CSV: aircraft and road noise, air quality, flood risk, crime, schools and prices, from open government data." />
<link rel="canonical" href="{site}/open-data/" />
<link rel="stylesheet" href="/fonts/fonts.css" />
<style>
  :root {{ color-scheme: light dark; --dark:#141414; --mid:#636363; --line:#e7e5e4; --bg:#fafaf9; --orange:#c2410c; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:'Inter',system-ui,sans-serif; color:var(--dark); background:#fff; line-height:1.6; }}
  .wrap {{ max-width:760px; margin:0 auto; padding:24px 20px 64px; }}
  a {{ color:var(--orange); }}
  nav.crumbs {{ font-size:12px; color:var(--mid); margin-bottom:20px; }}
  h1 {{ font-size:28px; line-height:1.25; margin:0 0 6px; }}
  h2 {{ font-size:18px; margin:32px 0 8px; }}
  .sub {{ color:var(--mid); margin:0 0 20px; }}
  .dl {{ display:inline-block; padding:12px 18px; border:1px solid var(--line); border-radius:8px; background:var(--bg); font-weight:600; }}
  .tw {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-weight:600; }}
  code {{ font-family:'JetBrains Mono',ui-monospace,monospace; font-size:12px; }}
  footer {{ margin-top:40px; font-size:12px; color:var(--mid); }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --dark:#f5f5f4; --mid:#a1a1a1; --line:#3a3a3a; --bg:#1c1c1c; --orange:#fb923c; }}
    body {{ background:#141414; }}
  }}
</style>
</head>
<body>
<div class="wrap">
<nav class="crumbs"><a href="/">Sky Score</a> &rsaquo; Open data</nav>
<main>
<h1>Open data</h1>
<p class="sub">Every UK area Sky Score covers, in one file: the published score, its five components and the measurements behind them. {n} areas across {c} city regions. Prices: {vintage} UK House Price Index. Methodology version {methodology}.</p>
<p><a class="dl" href="/open-data/{csv}" download>Download {csv} (CSV)</a></p>

<h2>Licence and attribution</h2>
<p>{licence}</p>
<p>Built entirely from open government data, used under the <a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/">Open Government Licence v3.0</a>. If you reuse this file, please also credit the original publishers: DEFRA (noise and air quality), the Environment Agency (flood risk), ONS (crime, postcode lookup), the Department for Education (Progress 8), HM Land Registry (prices), the Department for Transport (NaPTAN) and the NHS Organisation Data Service (GP practices).</p>

<h2>What each column means</h2>
<div class="tw">
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
<p><a href="/">Sky Score</a> &middot; <a href="/area/">All areas</a> &middot; <a href="/api/">For developers</a> &middot; <a href="/privacy">Privacy</a></p>
</footer>
</div>
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
    'with that credit. Reselling the dataset, redistributing it in bulk, or building it into a commercial product or '
    'service needs written permission: <a href="mailto:support@skyscore.co.uk">support@skyscore.co.uk</a>.'
)


def open_data_files() -> dict[str, str]:
    rows = open_data_rows()
    columns = '\n'.join(f'<tr><td><code>{e(c)}</code></td><td>{e(d)}</td></tr>' for c, d in OPEN_DATA_COLUMNS)
    page = OPEN_DATA_PAGE.format(
        n=len(rows), c=len({r[0] for r in rows}), site=SITE, csv=OPEN_DATA_CSV,
        vintage=e(app.SNAPSHOT_VINTAGE_LABEL), methodology=e(app.METHODOLOGY_VERSION),
        licence=OPEN_DATA_LICENCE, columns=columns)
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
    ('/open-data/', '0.7', 'monthly'),
    ('/pricing', '0.8', 'monthly'),
    ('/privacy', '0.3', 'yearly'),
    ('/api/', '0.9', 'monthly'),
    ('/score-demo/', '0.7', 'monthly'),
    ('/score-demo/api-docs.html', '0.6', 'monthly'),
    ('/score-demo/status.html', '0.3', 'weekly'),
    ('/prototype/', '0.5', 'monthly'),
]


def source_file(loc: str) -> str:
    """The repo file a sitemap URL serves, as CloudFront's rewrite maps it."""
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
        log = git('log', '--format=%x00%cs', '--name-only')
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
