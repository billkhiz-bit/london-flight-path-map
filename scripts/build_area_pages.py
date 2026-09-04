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
import html
import json
import re
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

    # AFFORDABILITY AND GROWTH ARE COHORT-RELATIVE, AND THESE PAGES DID NOT SAY
    # SO (2026-09-03). Both are min-max scaled WITHIN the city, so the cheapest
    # borough of every city scores 10.0 and the priciest 0.0 whatever the money
    # involved. Measured: Barking and Dagenham published `Affordability 10.0`
    # at GBP 371,030 while Stockton-on-Tees published `0.0` at GBP 170,923 - a
    # borough 2.2x CHEAPER reading as the least affordable - with the price in
    # the same table for a reader to notice the contradiction.
    #
    # Nothing was miscomputed and `index.html` and METHODOLOGY both disclose the
    # scaling. These 99 pages did not, and they are the surface a stranger
    # reaches from a search engine with no other context, so an unlabelled
    # relative score reads as an absolute one. Same distinction as the
    # neighbourhood ranking's "best value" label.
    #
    # NOT wrapped in uk_note(): this is a methodology caveat, not a UK source
    # attribution, and it is just as true of New York, where the Bronx scores
    # 10.0 at USD 420,000.
    prices = [r.get('avgPrice') for r in app.CITIES[city]['boroughs'].values()
              if r.get('avgPrice')]
    cohort_note = None
    if len(prices) > 1:
        cohort_note = (
            f'Scaled within this city only - 10 is the cheapest of '
            f'{len(prices)} areas here, not nationally'
        )

    add('Sky Score', f"{body['score']} / 10")
    add('Quiet skies', f"{comp.get('quiet')} / 10" if comp.get('quiet') is not None else None)
    add('Affordability', f"{comp.get('afford')} / 10" if comp.get('afford') is not None else None,
        cohort_note)
    add('Growth', f"{comp.get('growth')} / 10" if comp.get('growth') is not None else None,
        cohort_note)
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
    add('Aircraft noise band', (ctx.get('noiseImpactBand') or '').title() or None,
        uk_note('DEFRA Strategic Noise Mapping Round 4'))

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
<main>
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

<div class="cta">
  <p style="margin:0 0 8px;"><strong>See it on the map.</strong> Noise contours, flight corridors and every neighbourhood in {city_label}.</p>
  <a href="/?city={city}&amp;borough={borough_q}">Open {borough} on the Sky Score map</a>
</div>

<h2>Where these numbers come from</h2>
<p class="sources">{sources}</p>
<p class="sources">Methodology version {methodology}. Full method: <a href="/score-demo/api-docs.html">API reference</a>.
Figures are for the whole borough; a single address can differ, and the map shows postcode-level detail.</p>
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
    return PAGE.format(
        title=e(f"{data['borough']} noise & liveability score | Sky Score"),
        description=e(desc),
        canonical=f"{SITE}/area/{slug(data['city'])}/{slug(data['borough'])}/",
        city_label=e(city_label),
        city=e(data['city']),
        borough=e(data['borough']),
        borough_q=e(data['borough'].replace(' ', '+')),
        score=e(data['score']),
        rows=rows,
        sources=e('; '.join(str(s) for s in data['sources'][:6]) or 'See methodology.'),
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

    write_sitemap([p for p, _ in pages])
    print(f'wrote {len(pages)} pages + index + sitemap')
    return 0


STATIC_URLS = [
    ('/', '1.0', 'weekly'),
    ('/pricing', '0.8', 'monthly'),
    ('/privacy', '0.3', 'yearly'),
    ('/api/', '0.9', 'monthly'),
    ('/score-demo/', '0.7', 'monthly'),
    ('/score-demo/api-docs.html', '0.6', 'monthly'),
    ('/score-demo/status.html', '0.3', 'weekly'),
    ('/prototype/', '0.5', 'monthly'),
]


def write_sitemap(paths: list[str]) -> None:
    """Rewrite sitemap.xml from what was actually generated.

    Generated, never hand-edited: a sitemap listing a page that does not exist
    is a crawl error on every miss, and one omitting pages that do exist wastes
    the whole exercise. Deriving it from the same list that wrote the files
    means the two cannot disagree.
    """
    today = datetime.now(UTC).strftime('%Y-%m-%d')
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, prio, freq in STATIC_URLS:
        out.append(f'  <url><loc>{SITE}{loc}</loc><lastmod>{today}</lastmod>'
                   f'<changefreq>{freq}</changefreq><priority>{prio}</priority></url>')
    out.append(f'  <url><loc>{SITE}/area/</loc><lastmod>{today}</lastmod>'
               f'<changefreq>monthly</changefreq><priority>0.8</priority></url>')
    for p in sorted(paths):
        out.append(f'  <url><loc>{SITE}/area/{p}/</loc><lastmod>{today}</lastmod>'
                   f'<changefreq>monthly</changefreq><priority>0.6</priority></url>')
    out.append('</urlset>')
    (REPO / 'sitemap.xml').write_text('\n'.join(out) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    raise SystemExit(main())
