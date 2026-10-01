"""Is every dataset we serve the newest its publisher has released? One table.

WHY THIS EXISTS (2026-10-01). Air quality served DEFRA's 2022 maps while 2023
and 2024 were out, unnoticed for eight weeks, because the year was a filename
nothing compared with anything. The same afternoon showed the crime workbook's
URL had 404'd since August, hidden by a cache - a fresh clone could not have
fetched it. House prices were the only dataset whose script asked its publisher
for something newer. This asks every publisher that can be asked.

EVERY DATASET IS LISTED, CHECKED OR NOT. A dataset with no automatic check is
printed with the reason, because a list that omits a member reads as complete
(the repo has paid for that more than once). Each served version is read from
its ONE holder in the script that loads it - never retyped here.

  current       we serve the publisher's newest release
  NEWER         the publisher has released something newer: roll it   (exit 1)
  BROKEN        the source we fetch from no longer resolves            (exit 1)
  info          something newer exists but is known not to apply
  covered       another gate checks it (named)
  not checked   no automatic check, and why
  live          queried per request; nothing to roll
  INCONCLUSIVE  the publisher could not be asked. Never read as current.

Advisory preflight stage (network). INCONCLUSIVE rows are also printed as lines
starting "INCONCLUSIVE:" so preflight surfaces them rather than reading ok.

    python scripts/check_data_freshness.py
"""

from __future__ import annotations

import calendar
import datetime
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The holders of what we serve. All import cheaply: their heavy dependencies
# are imported inside the functions that need them.
import build_city_neighbourhoods  # noqa: E402
import build_flight_paths  # noqa: E402
import build_hpi_prices  # noqa: E402
import build_progress8  # noqa: E402
import check_air_quality_vintage  # noqa: E402
import load_defra_air_quality  # noqa: E402
import load_nspl  # noqa: E402
import refresh_crime_from_ons  # noqa: E402

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
TODAY = datetime.date.today()

CRIME_PAGE = ('https://www.ons.gov.uk/peoplepopulationandcommunity/crimeandjustice/'
              'datasets/policeforceareadatatables')
NSPL_SEARCH = ('https://www.arcgis.com/sharing/rest/search?q='
               + urllib.parse.quote('title:"National Statistics Postcode Lookup" AND owner:ONSGeography_data')
               + '&sortField=modified&sortOrder=desc&num=50&f=json')
KS4_PAGE = 'https://explore-education-statistics.service.gov.uk/find-statistics/key-stage-4-performance'
# KS4 cohorts with no KS2 baseline, for which DfE publishes no Progress 8
# (build_progress8.py's docstring has the DfE wording). A release for one of
# these is not a roll.
NO_PROGRESS8 = frozenset({'2024/25', '2025/26'})
# DEFRA strategic noise mapping round served (road and aircraft). DEFRA has
# announced no Round 5 date; its services will appear under the next number.
NOISE_ROUND = 4
NOISE_WCS = ('https://environment.data.gov.uk/spatialdata/{kind}-noise-all-metrics-england-round-{n}'
             '/wcs?service=WCS&request=GetCapabilities')
AIRAC_DAYS = 28


def fetch_text(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode('utf-8', errors='replace')


def resolves(url):
    """True on 200/206, False on 404; raises on anything else, so an outage is
    INCONCLUSIVE rather than "not published"."""
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Range': 'bytes=0-0'})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status in (200, 206)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


# ---- pure helpers (tested offline in tests/test_data_freshness.py) ---------

def crime_editions(html):
    """Every `yearending<month><year>` edition linked from ONS's dataset page, newest first."""
    found = set(re.findall(r'policeforceareadatatables/(yearending([a-z]+)(\d{4}))/', html))
    dated = [(datetime.date(int(y), MONTHS[m], 1), ed) for ed, m, y in found if m in MONTHS]
    return [ed for _, ed in sorted(dated, reverse=True)]


def nspl_editions(results):
    """'YYYY-MM' for every NSPL CSV release in the ONS Geoportal catalogue, newest first."""
    out = set()
    for r in results:
        title = r.get('title', '')
        if r.get('type') != 'CSV Collection' or 'guide' in title.lower():
            continue
        m = re.search(r'\(([A-Za-z]+) (\d{4})\)', title)
        if m and m.group(1).lower() in MONTHS:
            out.add(f'{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}')
    return sorted(out, reverse=True)


def ks4_status(served, latest):
    if latest <= served:
        return 'current'
    return 'info' if latest in NO_PROGRESS8 else 'NEWER'


def airac_current(served, today):
    """The AIRAC cycle in force on `today`, stepping 28 days from the served one."""
    d = datetime.date.fromisoformat(served)
    while d + datetime.timedelta(days=AIRAC_DAYS) <= today:
        d += datetime.timedelta(days=AIRAC_DAYS)
    return d.isoformat()


def latest_complete_year(served, today, probe):
    """Newest COMPLETE calendar year with a published file, or None if even the
    served year's file has gone. The current year's file is year-to-date."""
    for year in range(today.year - 1, served - 1, -1):
        if probe(year):
            return year
    return None


# ---- one row per checked dataset: (served, latest, status, note) ------------

def hpi():
    served = build_hpi_prices.DEFAULT_VINTAGE
    newer = build_hpi_prices.newer_vintage_published(served)
    return (served[:7], (newer or served)[:7], 'NEWER' if newer else 'current',
            'monthly; sh scripts/deploy_hpi_roll.sh (ONS CPIH rolls with it)')


def crime():
    served = refresh_crime_from_ons.EDITION
    editions = crime_editions(fetch_text(CRIME_PAGE))
    if not editions:
        raise RuntimeError("no editions found on ONS's dataset page - its markup has changed")
    if not resolves(refresh_crime_from_ons.XLSX_URL):
        return (served, editions[0], 'BROKEN',
                f"XLSX_URL no longer resolves - copy {served}'s href from the dataset page into XLSX_FILE")
    return (served, editions[0], 'current' if editions[0] == served else 'NEWER',
            'quarterly; refresh_crime_from_ons.py (EDITION + XLSX_FILE), --check --all then --write --all')


def nspl():
    served = load_nspl.NSPL_VINTAGE
    editions = nspl_editions(json.loads(fetch_text(NSPL_SEARCH)).get('results', []))
    if not editions:
        raise RuntimeError('no NSPL CSV releases in the ONS Geoportal catalogue')
    return (served, editions[0], 'current' if editions[0] <= served else 'NEWER',
            'quarterly (Feb/May/Aug/Nov); HANDOVER s0 steps 1-7, and diff REMOVED first')


def air():
    served = load_defra_air_quality.PCM_YEAR
    latest = check_air_quality_vintage.latest_published(served, TODAY.year)
    if latest is None:
        return str(served), '?', 'BROKEN', "the served year's files no longer resolve at DEFRA's datastore"
    return (str(served), str(latest), 'NEWER' if latest > served else 'current',
            'yearly, ~mid-October; ROADMAP "Air quality vintage roll"')


def ks4():
    served = build_progress8.VINTAGE
    m = re.search(r'Academic year (\d{4}/\d{2})', fetch_text(KS4_PAGE))
    if not m:
        raise RuntimeError('no "Academic year" on the DfE KS4 release page')
    latest = m.group(1)
    status = ks4_status(served, latest)
    note = (f'{latest} carries no Progress 8 (no KS2 baseline for that cohort)' if status == 'info'
            else 'yearly; build_progress8.py, then build_area_pages.py --write')
    return served, latest, status, note


def noise():
    served = f'Round {NOISE_ROUND}'
    kinds = ('road', 'airport')
    if not all(resolves(NOISE_WCS.format(kind=k, n=NOISE_ROUND)) for k in kinds):
        return served, '?', 'BROKEN', f"DEFRA's Round {NOISE_ROUND} map services no longer resolve"
    newer = [k for k in kinds if resolves(NOISE_WCS.format(kind=k, n=NOISE_ROUND + 1))]
    return (served, f'Round {NOISE_ROUND + 1}' if newer else served, 'NEWER' if newer else 'current',
            '~5-yearly; DEFRA has announced no Round 5 date' if not newer
            else f'Round {NOISE_ROUND + 1} services live for: {", ".join(newer)} - every aircraft fit refits on it')


def airac():
    served = build_flight_paths.AIRAC
    current = airac_current(served, TODAY)
    if current == served:
        return served, served, 'current', 'every 28 days'
    page = build_flight_paths.EAIP.replace(served, current) + 'EG-AD-2.EGLL-en-GB.html'
    if not resolves(page):
        return served, current, 'current', f'the {current} cycle is not published yet'
    cycles = (datetime.date.fromisoformat(current) - datetime.date.fromisoformat(served)).days // AIRAC_DAYS
    return (served, current, 'NEWER',
            f'{cycles} cycle(s) behind; set AIRAC, then build_flight_paths.py --fetch and --check '
            '(only the date moving means no procedure changed)')


def ppd():
    served = max(build_city_neighbourhoods.PPD_YEARS)
    latest = latest_complete_year(
        served, TODAY, lambda y: resolves(build_city_neighbourhoods.PPD_URL.format(year=y)))
    if latest is None:
        return str(served), '?', 'BROKEN', f'pp-{served}.csv no longer resolves'
    return (str(served), str(latest), 'NEWER' if latest > served else 'current',
            'complete calendar years; build_city_neighbourhoods.py --years N --write-index')


CHECKED = [
    ('HM Land Registry UK HPI (prices, growth)', hpi),
    ('ONS recorded crime (Table C4)', crime),
    ('ONS postcode lookup (NSPL)', nspl),
    ('DEFRA air quality (PCM NO2, PM2.5)', air),
    ('DfE school results (KS4 Progress 8)', ks4),
    ('DEFRA noise maps (road + aircraft)', noise),
    ('UK AIP flight procedures (AIRAC)', airac),
    ('HM Land Registry Price Paid (medians)', ppd),
]

NOT_ROLLED = [
    ('ONS CPIH inflation (L55O)', 'covered', 'rolls with the HPI row; build_hpi_prices.py --check compares it with ONS'),
    ('Environment Agency flood risk', 'covered',
     'preflight "flood == EA service (georef)" compares our mosaic with the EA\'s live map'),
    ('NaPTAN stations (transport share)', 'not checked',
     'a continuously updated register with no edition to compare; rebuild stations + bands quarterly'),
    ('NHS ODS GP practices (healthcare share)', 'not checked',
     'a continuously updated register; rebuild with the bands quarterly'),
    ('Commons Library MSOA names', 'not checked', 'changes only with new MSOA boundaries (after Census 2031)'),
    ('OurAirports runway geometry', 'not checked',
     'community-maintained; runways rarely move, and the AIP row checks the procedures'),
    ('CAA ERCD contours (COVID caveat)', 'not checked',
     'an annual PDF read by hand; measure_covid_understatement.py holds the figures'),
    ('EPC register (/epc)', 'live', 'queried per request'),
    ('Land Registry Price Paid API (/sold-prices)', 'live', 'queried per request'),
    ('TfL Open Data (/transport)', 'live', 'queried per request'),
    ('OpenStreetMap Overpass (/nhs)', 'live', 'queried per request'),
    ('postcodes.io (fallback resolver)', 'live', 'queried per request'),
    ('US federal layers (NTAD, FEMA, EPA)', 'live', 'requested by the browser on the New York map'),
    ('New York borough inputs', 'curated', 'compiled by hand from NYC sources; reviewed manually'),
]


def main():
    rows, failing, inconclusive = [], [], []
    for name, check in CHECKED:
        try:
            served, latest, status, note = check()
        except (OSError, urllib.error.URLError, RuntimeError, ValueError) as exc:
            served, latest, status, note = '?', '?', 'INCONCLUSIVE', str(exc)[:110]
            inconclusive.append(f'{name}: {note}')
        if status in ('NEWER', 'BROKEN'):
            failing.append(name)
        rows.append((name, served, latest, status, note))
    rows += [(name, '-', '-', status, note) for name, status, note in NOT_ROLLED]

    print(f'{"dataset":44} {"served":20} {"newest":20} {"status":13} note')
    for name, served, latest, status, note in rows:
        print(f'{name:44} {str(served):20} {str(latest):20} {status:13} {note}')
    for line in inconclusive:
        print(f'INCONCLUSIVE: {line}')
    if failing:
        print(f'\n{len(failing)} to act on: {", ".join(failing)}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
