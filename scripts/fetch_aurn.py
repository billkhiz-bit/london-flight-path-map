"""DEFRA's reference air-quality monitors (AURN): each site's annual NO2 and PM2.5 mean.

WHY (2026-10-13). Step 2 of ROADMAP's "The plan for Breathe London". Breathe London's
sensors are London-only, so on their own they would make London the only city with a
measured air-quality figure. DEFRA's Automatic Urban and Rural Network (AURN) has
reference-grade monitors in every city we cover, so the same release can give every
city a "nearest official monitor" line beside DEFRA's modelled background (PCM) figure.
DISPLAY ONLY, NEVER SCORED: measured air quality in the score would be a methodology
change, decided on its own (EXPANSION.md "Measured air quality"). Nothing reads this
file yet; the line that shows it ships with the Breathe London half.

WHAT IT HOLDS. `data/aurn-sites.json`, checked in: one row per site with a usable annual
mean, its name, site type (Urban Traffic, Urban Background, ...), position, council,
closing date if it closed in the year, and the NO2 and PM2.5 mean with the share of the
year's hours each rests on. Sources are DEFRA's own openair summary files on
uk-air.defra.gov.uk (OGL): `summary_annual_AURN_<year>.rds` for the means and
`AURN_metadata.RData` for the sites. Both are R files, so `--fetch` needs
`pip install pyreadr`; `--check` needs nothing beyond the standard library.

THE YEAR IS THE PCM YEAR, not the newest summary. DEFRA calibrates its PCM background
maps against AURN measurements of the same year, so a measured 2024 mean beside the
modelled 2024 figure compares like with like. The year is read from its one holder,
`load_defra_air_quality.PCM_YEAR`, so when air quality rolls this file's `--check` goes
red until it is re-fetched: the two cannot drift apart.

RATIFIED ONLY. A pollutant's year counts if DEFRA has ratified it to the end of the year,
OR to the site's closing date when the site closed during the year (measured on 2024:
all five rows "ratified" short of 31 Dec were sites that closed, ratified to the day they
closed - Canterbury, Billingham, Nottingham Centre).

CAPTURE FLOOR 75% of the year's hours (Bill, 2026-10-13, the same floor as the Breathe
London plan). Neither network publishes a completeness rule for an annual mean shown to
the public, so ours is a choice and the page that shows it must say so. Measured on
2024: it drops 13 NO2 and 34 PM2.5 means, most of the PM2.5 ones under 15% (instruments
that started late in the year).

NOT A RANKING. UK-AIR warns that ranking monitoring sites is "not scientifically sound":
a kerbside monitor and a background one measure different things. Show the nearest
site with its type; never order sites or cities by these numbers.

ATTRIBUTION, exactly as UK-AIR's data page requires it (read 2026-10-13, their spelling):
"(c) Crown <year> copyright Defra via uk-air.defra.gov.uk, licenced under the Open
Government Licence (OGL)." with a link to the OGL where possible.

    python scripts/fetch_aurn.py --fetch    # network; writes data/aurn-sites.json
    python scripts/fetch_aurn.py --check    # offline, blocking: the file keeps its rules
    python scripts/fetch_aurn.py --verify   # re-derives from the cached raw files (advisory)
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))
from build_city_stations import _point_in_geometry, city_shapes  # noqa: E402
from load_defra_air_quality import PCM_YEAR  # noqa: E402

OUT = REPO / 'data' / 'aurn-sites.json'
RAW = REPO / 'data' / 'aurn'  # gitignored, like every raw download under data/
BASE = 'https://uk-air.defra.gov.uk/openair/R_data/'
SUMMARY_URL = BASE + 'summary_annual_AURN_{year}.rds'
METADATA_URL = BASE + 'AURN_metadata.RData'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'

CAPTURE_FLOOR = 0.75
# Our key -> the summary file's column prefix and the metadata's parameter code.
POLLUTANTS = {'no2': 'NO2', 'pm25': 'PM2.5'}
# A sanity ceiling, not a limit value: an annual mean above these is a broken read.
PLAUSIBLE_MAX = {'no2': 150.0, 'pm25': 100.0}
SITE_TYPES = frozenset({'Urban Background', 'Urban Traffic', 'Urban Industrial', 'Suburban Background',
                        'Suburban Industrial', 'Rural Background'})
ATTRIBUTION = re.compile(r'^© Crown \d{4} copyright Defra via uk-air\.defra\.gov\.uk, '
                         r'licenced under the Open Government Licence \(OGL\)\.$')
OGL_URL = 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/'
# The UK, as a corruption check on the coordinates (a swapped lat/lon fails it).
# A bounding box, deliberately: this asks "is it a UK coordinate at all", never
# "which city is it in" - that is the polygon test below.
UK_BOUNDS = (49.8, -8.7, 60.9, 1.8)

# A city with no usable AURN site (either pollutant) inside its own boundary, and why.
# The check fails on an undeclared city with none AND on a declared city that has one,
# so this cannot go stale in either direction. Empty on the 2024 file (2026-10-13).
# The floor is either pollutant, not NO2 alone: Greater Norwich's one site, Norwich
# Lakenfields, measured NO2 for only 64% of 2024's hours (under the floor) while its
# PM2.5 rests on 98%. Its nearest NO2 that clears the floor is Wicken Fen, 77 km away,
# so the line that shows this file needs a distance scope, as the station line has.
NO_SITE_INSIDE: dict[str, str] = {}


def attribution(year: int) -> str:
    return (f'© Crown {year} copyright Defra via uk-air.defra.gov.uk, '
            'licenced under the Open Government Licence (OGL).')


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - https, our constant
        body = resp.read()
    if len(body) < 1000:
        raise SystemExit(f'{url}: {len(body)} bytes - not a data file')
    dest.write_bytes(body)
    return dest


def read_raw(year: int):
    """(summary rows, metadata rows) from the cached R files, as lists of dicts."""
    import pyreadr  # only --fetch and --verify need it

    summary = pyreadr.read_r(str(RAW / f'summary_annual_AURN_{year}.rds'))[None]
    meta = next(iter(pyreadr.read_r(str(RAW / 'AURN_metadata.RData')).values()))
    return summary.to_dict('records'), meta.to_dict('records')


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def build(year: int, summary: list[dict], meta: list[dict], fetched: str) -> dict:
    """The file's content from the raw rows. Pure: --fetch and --verify both call it."""
    by_site: dict[str, list[dict]] = {}
    for row in meta:
        by_site.setdefault(str(row['site_id']), []).append(row)
    year_end = f'{year}-12-31'
    sites, excluded = [], []
    for row in summary:
        code, name = str(row['code']), str(row['site'])
        rows = by_site.get(code)
        if not rows:
            excluded.append({'code': code, 'site': name, 'reason': 'no row in AURN_metadata'})
            continue
        types = {str(r['location_type']) for r in rows}
        coords = {(round(float(r['latitude']), 5), round(float(r['longitude']), 5)) for r in rows}
        if len(types) != 1 or len(coords) != 1:
            excluded.append({'code': code, 'site': name, 'reason': f'metadata disagrees: {types} {coords}'})
            continue
        lat, lon = coords.pop()
        record = {'code': code, 'name': name, 'type': types.pop(), 'lat': lat, 'lon': lon,
                  'localAuthority': str(rows[0]['local_authority']), 'closed': None}
        for key, col in POLLUTANTS.items():
            mean, capture = _num(row.get(f'{col}.mean')), _num(row.get(f'{col}.capture'))
            if mean is None:
                record[key] = None
                continue
            prow = next((r for r in rows if r['parameter'] == col), None)
            if prow is None:
                excluded.append({'code': code, 'site': name, 'pollutant': key, 'reason': 'no metadata row for it'})
                record[key] = None
                continue
            end = str(prow['end_date'])
            closed = end if re.fullmatch(r'\d{4}-\d{2}-\d{2}', end) and end < year_end else None
            if str(prow['ratified_to']) < (closed or year_end):
                excluded.append({'code': code, 'site': name, 'pollutant': key,
                                 'reason': f'ratified only to {prow["ratified_to"]}'})
                record[key] = None
                continue
            if capture is None or capture < CAPTURE_FLOOR:
                excluded.append({'code': code, 'site': name, 'pollutant': key,
                                 'reason': f'capture {0 if capture is None else round(capture * 100)}% of hours'})
                record[key] = None
                continue
            record[key] = {'mean': round(mean, 1), 'capture': round(capture, 3)}
            record['closed'] = record['closed'] or closed
        if record['no2'] or record['pm25']:
            sites.append(record)
    sites.sort(key=lambda s: s['code'])
    excluded.sort(key=lambda e: (e['code'], e.get('pollutant', '')))
    return {
        'source': ('DEFRA Automatic Urban and Rural Network (AURN), annual means from the openair '
                   'summary files on uk-air.defra.gov.uk'),
        'attribution': attribution(int(fetched[:4])),
        'licence': OGL_URL,
        'year': year,
        'captureFloor': CAPTURE_FLOOR,
        'fetched': fetched,
        'files': {'summary': SUMMARY_URL.format(year=year), 'metadata': METADATA_URL},
        'note': ('Display only, never scored. Reference monitors of different types measure '
                 'different things: show the nearest with its type, never rank them.'),
        'sites': sites,
        'excluded': excluded,
    }


def uk_city_shapes() -> dict:
    """The covered UK cities' boundaries (New York's file is in the same glob)."""
    return {city: geoms for city, (_bbox, geoms) in city_shapes().items() if city != 'nyc'}


def sites_inside(sites: list[dict], geoms: list[dict], key: str | None = None) -> list[str]:
    """Codes of the sites inside the geometries holding `key`, or either pollutant."""
    keys = [key] if key else list(POLLUTANTS)
    return [s['code'] for s in sites
            if any(s.get(k) for k in keys) and any(_point_in_geometry(s['lon'], s['lat'], g) for g in geoms)]


def check(data: dict) -> list[str]:
    """Every rule the file must keep. Returns the problems; empty means it passes."""
    problems = []
    if data.get('year') != PCM_YEAR:
        problems.append(f'year {data.get("year")} is not the PCM year {PCM_YEAR}: re-run --fetch')
    if not ATTRIBUTION.match(data.get('attribution', '')):
        problems.append(f'attribution is not UK-AIR\'s required statement: {data.get("attribution")!r}')
    if data.get('licence') != OGL_URL:
        problems.append('licence link is not the OGL v3')
    if data.get('captureFloor') != CAPTURE_FLOOR:
        problems.append(f'captureFloor {data.get("captureFloor")} is not {CAPTURE_FLOOR}')
    sites = data.get('sites') or []
    codes = [s.get('code') for s in sites]
    if len(codes) != len(set(codes)):
        problems.append('duplicate site codes')
    lat0, lon0, lat1, lon1 = UK_BOUNDS
    for s in sites:
        where = f'{s.get("code")} {s.get("name")}'
        if not (lat0 <= s.get('lat', 0) <= lat1 and lon0 <= s.get('lon', 99) <= lon1):
            problems.append(f'{where}: ({s.get("lat")}, {s.get("lon")}) is not a UK coordinate')
        if s.get('type') not in SITE_TYPES:
            problems.append(f'{where}: unknown site type {s.get("type")!r}')
        if not (s.get('no2') or s.get('pm25')):
            problems.append(f'{where}: carries neither pollutant')
        for key in POLLUTANTS:
            v = s.get(key)
            if v is None:
                continue
            if not (0 < v.get('mean', -1) < PLAUSIBLE_MAX[key]):
                problems.append(f'{where}: {key} mean {v.get("mean")} is not a plausible annual mean')
            if not (CAPTURE_FLOOR <= v.get('capture', 0) <= 1):
                problems.append(f'{where}: {key} capture {v.get("capture")} is outside {CAPTURE_FLOOR}-1')
    # The per-city floor: a count says how many sites survived, never WHICH. Every
    # covered city must hold a usable site inside its own boundary, or say why not.
    for city, geoms in sorted(uk_city_shapes().items()):
        inside = sites_inside(sites, geoms)
        if not inside and city not in NO_SITE_INSIDE:
            problems.append(f'{city}: no usable AURN site inside its boundary, and none declared in NO_SITE_INSIDE')
        if inside and city in NO_SITE_INSIDE:
            problems.append(f'{city}: declared in NO_SITE_INSIDE but {", ".join(inside)} now lies inside: remove it')
    return problems


def report(data: dict) -> None:
    sites = data['sites']
    n_no2 = sum(1 for s in sites if s['no2'])
    n_pm = sum(1 for s in sites if s['pm25'])
    print(f'{len(sites)} AURN sites, {data["year"]}: {n_no2} with NO2, {n_pm} with PM2.5; '
          f'{len(data["excluded"])} exclusions')
    for city, geoms in sorted(uk_city_shapes().items()):
        no2, pm = len(sites_inside(sites, geoms, 'no2')), len(sites_inside(sites, geoms, 'pm25'))
        note = f' (declared: {NO_SITE_INSIDE[city]})' if city in NO_SITE_INSIDE else ''
        print(f'  {city:16} inside: {no2} with NO2, {pm} with PM2.5{note}')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fetch', action='store_true', help='download the PCM year and write the file')
    mode.add_argument('--check', action='store_true', help='offline: the checked-in file keeps its rules')
    mode.add_argument('--verify', action='store_true', help='re-derive from the cached raw files and compare')
    args = ap.parse_args(argv)

    if args.fetch:
        download(SUMMARY_URL.format(year=PCM_YEAR), RAW / f'summary_annual_AURN_{PCM_YEAR}.rds')
        download(METADATA_URL, RAW / 'AURN_metadata.RData')
        data = build(PCM_YEAR, *read_raw(PCM_YEAR), fetched=datetime.date.today().isoformat())
        problems = check(data)
        report(data)
        if problems:
            print('NOT WRITTEN, the fetched data breaks its rules:\n  ' + '\n  '.join(problems))
            return 1
        OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'wrote {OUT.relative_to(REPO)}')
        return 0

    if not OUT.exists():
        print(f'FAIL: {OUT.relative_to(REPO)} is missing (it is checked in: restore it or run --fetch)')
        return 1
    data = json.loads(OUT.read_text(encoding='utf-8'))

    if args.verify:
        year = data.get('year')
        raw = [RAW / f'summary_annual_AURN_{year}.rds', RAW / 'AURN_metadata.RData']
        if not all(p.exists() for p in raw):
            print(f'INCONCLUSIVE: the raw files are not cached under {RAW.relative_to(REPO)} (run --fetch)')
            return 0
        try:
            import pyreadr  # noqa: F401 - the R reader; a fresh clone may not have it
        except ImportError:
            print('INCONCLUSIVE: pyreadr is not installed (pip install pyreadr), so the R files cannot be read')
            return 0
        rebuilt = build(year, *read_raw(year), fetched=data['fetched'])
        if rebuilt != data:
            diff = [k for k in data if data.get(k) != rebuilt.get(k)]
            print(f'FAIL: {OUT.relative_to(REPO)} differs from a re-derivation in: {", ".join(diff)}')
            return 1
        print(f'ok: {OUT.relative_to(REPO)} re-derives exactly from the cached {year} files')
        return 0

    problems = check(data)
    report(data)
    if problems:
        print('FAIL:\n  ' + '\n  '.join(problems))
        return 1
    print('ok: every rule holds')
    return 0


if __name__ == '__main__':
    sys.exit(main())
