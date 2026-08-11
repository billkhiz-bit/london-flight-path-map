#!/usr/bin/env python3
"""Refresh London borough crime rates from the ONS primary source.

WHY THIS EXISTS (2026-08-03). The repo's crime rates were cited as ONS
*Crime in England and Wales: Police Force Area data tables*, Table C4, and
three boroughs were corrected against it on 2026-08-02 with the conclusion
that "the other 29 were already right, within 10 per 1,000". Checked against
the actual release, that conclusion was drawn from a handful of spot checks
(Richmond, Sutton, Enfield — all genuinely correct) and generalised. Seven
boroughs were out by more than 10 per 1,000, the worst by 20.8, and 17 of 33
carried a crime sub-score wrong by more than 0.3.

Hand-checking a few rows and generalising is precisely how that happened, so
this script exists to make the comparison total and repeatable: it reads every
London row from the published workbook rather than sampling it.

It also extracts the per-offence breakdown Table C4 already carries, so the
consumer site can say *why* a borough scores as it does — "theft from the
person, 92.5 per 1,000" — instead of the unsourced "often driven by nightlife,
tourism, or town centre activity" it said before.

USAGE

    python scripts/refresh_crime_from_ons.py --check    # compare only, exit 1 on drift
    python scripts/refresh_crime_from_ons.py --write    # update data/borough-extra.json
    python scripts/refresh_crime_from_ons.py --check --city manchester

Run --check whenever ONS publishes (quarterly). Rates move with each release,
so drift here is expected and is the signal to roll the vintage, not a bug.

NOTE ON THE DOWNLOAD: use www.ons.gov.uk, not cdn.ons.gov.uk. The cdn host
404s on this path.
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

EDITION = 'yearendingmarch2026'
XLSX_URL = (
    'https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/crimeandjustice/'
    f'datasets/policeforceareadatatables/{EDITION}/pfatablesye{EDITION[4:]}.xlsx'
)
CACHE = Path('data/ons_pfa_tables.xlsx')
EXTRA = Path('data/borough-extra.json')

TOTAL_COL = 'Total recorded crime  (excluding fraud)'
# Offence columns worth surfacing. Deliberately excludes the sub-totals that
# would double-count against their parent (e.g. 'Violence with injury' sits
# inside 'Violence against the person').
OFFENCE_COLS = [
    'Violence against the person',
    'Sexual offences',
    'Robbery',
    'Burglary',
    'Vehicle offences',
    'Theft from the person',
    'Bicycle theft',
    'Shoplifting',
    'Criminal damage and arson',
    'Drug offences',
    'Possession of weapons offences',
    'Public order offences',
]

# The site keys Barking and Dagenham as 'Barking'.
SITE_ALIAS = {'Barking and Dagenham': 'Barking'}

# Which Police Force Area rows belong to each city. Table C4 is published per
# force, and each force block carries Community Safety Partnership rows beneath
# it - CSPs are local-authority level, which is what makes a ten-borough
# city-region separable inside a single-force area.
CITY_PFA = {
    'london': ('Metropolitan Police', 'London, City of', 'City of London'),
    'manchester': ('Greater Manchester',),
    # West Midlands Police is one force covering exactly the seven metropolitan
    # boroughs, so like Greater Manchester the CSP rows need no include-list.
    # That does NOT generalise to the rest of the Core Cities: Northumbria
    # covers Northumberland as well as Tyne and Wear, Avon and Somerset covers
    # Somerset as well as Bristol, and Cardiff spans TWO forces (South Wales and
    # Gwent). Those need an include-list rather than an exclude-list, which this
    # script does not have yet.
    'westmidlands': ('West Midlands',),
    # Leicestershire Police also covers Rutland, which is not ours - hence the
    # include-list below. Every one of the eight authorities has its OWN CSP row,
    # unlike Nottingham, where Broxtowe, Gedling and Rushcliffe share a single
    # 'South Nottinghamshire' partnership and therefore cannot be separated.
    'leicester': ('Leicestershire',),
    # Teesside spans TWO forces: Cleveland covers the four Tees unitaries and
    # Darlington is Durham. Durham also publishes a 'County Durham' row that is
    # not ours, so this needs the include-list as Cardiff does.
    'teesside': ('Cleveland', 'Durham'),
    'westyorkshire': ('West Yorkshire',),
    'southyorkshire': ('South Yorkshire',),
    'merseyside': ('Merseyside',),
    'tyneandwear': ('Northumbria',),
    'bristol': ('Avon and Somerset',),
    # Cardiff is the only city here that spans two forces. CITY_PFA already
    # takes a tuple, so this needs no new machinery - but the include-list is
    # what stops it collecting the whole of South Wales and Gwent.
    'cardiff': ('South Wales', 'Gwent'),
    # Nottingham is NOT here on purpose. ONS publishes `Nottingham` and
    # `South Nottinghamshire`, and Broxtowe, Gedling and Rushcliffe are inside
    # that one combined row rather than published separately. Spreading a single
    # rate across three boroughs would render one measurement as three, which is
    # the defect class this whole file exists to prevent. Decide it explicitly
    # before adding it.
}

# CSP rows that are NOT boroughs. Greater Manchester publishes ELEVEN: the ten
# metropolitan boroughs plus `Manchester Airport`, which is its own partnership.
# Without this it enters as an eleventh borough, and because the comparison
# below SKIPS names it cannot pair up, it would do so silently.
CSP_EXCLUDE = {
    'london': frozenset(),
    'manchester': frozenset({'Manchester Airport'}),
    # West Midlands publishes exactly the seven boroughs plus the force-level
    # 'Unassigned' row, which load_table already skips. Nothing else to drop.
    'westmidlands': frozenset(),
    'westyorkshire': frozenset(),
    'southyorkshire': frozenset(),
    'merseyside': frozenset(),
}

# Cities whose police force covers MORE than the city region. Only these need an
# include-list; a metropolitan county's force is the county.
CSP_INCLUDE = {
    'tyneandwear': frozenset({
        'Gateshead', 'Newcastle upon Tyne', 'North Tyneside', 'South Tyneside', 'Sunderland',
    }),  # Northumbria also covers Northumberland
    'bristol': frozenset({
        'Bath and North East Somerset', 'Bristol, City of', 'North Somerset', 'South Gloucestershire',
    }),  # Avon and Somerset also covers Somerset
    'cardiff': frozenset({
        'Cardiff', 'Vale of Glamorgan', 'Newport', 'Caerphilly',
    }),  # spans TWO forces: South Wales and Gwent
    'leicester': frozenset({
        'Leicester', 'Blaby', 'Charnwood', 'Harborough', 'Hinckley and Bosworth',
        'Melton', 'North West Leicestershire', 'Oadby and Wigston',
    }),  # Leicestershire Police also covers Rutland
    'teesside': frozenset({
        'Hartlepool', 'Middlesbrough', 'Redcar and Cleveland', 'Stockton-on-Tees',
        'Darlington',
    }),  # spans Cleveland and Durham; Durham also publishes a County Durham row
}

# ONS CSP name -> the name the registry holds.
CSP_RENAME = {
    'bristol': {'Bristol, City of': 'City of Bristol'},
    'merseyside': {'St. Helens': 'St Helens'},
}


def lambda_rates(city):
    """Crime rates as the score Lambda holds them, for a city not in
    data/borough-extra.json.

    Greater Manchester is backend-only - the consumer site does not offer it -
    so CITIES is its single holder. London has two holders, and
    tests/test_borough_data_parity.py is what keeps them equal.
    """
    import types

    # Compiled from the SOURCE TEXT rather than imported, and that is not
    # fussiness. importlib honours __pycache__, which it validates on the
    # source's recorded size and mtime. Proving this check can go red means
    # editing app.py and putting it back, and a same-length edit restored
    # within the same clock second matches both - so Python silently ran
    # bytecode compiled from code that no longer existed, and this script
    # reported drift against a value the file did not contain. Reading the
    # text has no cache to be stale.
    path = Path('backend/lambdas/score/app.py')
    mod = types.ModuleType('score_app_crime_check')
    mod.__file__ = str(path)
    # noqa justified: the input is a first-party file inside this repo, read by
    # a maintainer-run script that is never deployed and never sees user input.
    # The alternative, importlib, is what introduced the staleness above.
    exec(  # noqa: S102
        compile(path.read_text(encoding='utf-8'), str(path), 'exec'), mod.__dict__
    )
    # Shaped like a borough-extra.json city block so the comparison below is
    # identical for both holders rather than branching per city.
    return {
        n: {'crimeRate': bd.get('crimeRate')}
        for n, bd in mod.CITIES[city]['boroughs'].items()
    }


def load_table(city='london'):
    import openpyxl

    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f'Downloading {XLSX_URL}')
        req = urllib.request.Request(XLSX_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=180) as r, open(CACHE, 'wb') as f:
            f.write(r.read())
        print(f'  saved {CACHE} ({CACHE.stat().st_size:,} bytes)')

    wb = openpyxl.load_workbook(CACHE, read_only=True, data_only=True)
    rows = list(wb['Table C4'].iter_rows(values_only=True))
    h = next(i for i, r in enumerate(rows) if r and r[0] == 'Police Force Area code')
    hdr = [str(c).replace('\n', ' ').strip() if c else '' for c in rows[h]]

    out = {}
    for r in rows[h + 1:]:
        if not r or not r[1]:
            continue
        # PFA names carry footnote suffixes in this workbook - the City of
        # London row is literally "City of London[note 8]" - so an exact-match
        # tuple silently excluded the one borough --check exists to flag. It
        # reported "in step with ONS" while that borough published a figure ONS
        # does not produce. Strip the suffix before matching.
        pfa = re.sub(r"\[note \d+\]", "", str(r[1])).strip()
        if pfa not in CITY_PFA[city]:
            continue
        # A row with no CSP name is the force-level AGGREGATE, not a place.
        # Including it named the row 'Metropolitan Police' and folded a
        # London-wide average into the per-borough median, so every
        # `vsLondonMedian` ratio was computed against a cohort containing its
        # own summary. Skip it: this table is read for boroughs.
        if not r[3]:
            continue
        name = str(r[3]).strip()
        if 'Unassigned' in name or name in CSP_EXCLUDE.get(city, frozenset()):
            continue
        # INCLUDE-list, for city-regions whose police force is larger than the
        # city. Metropolitan counties need none - West Midlands Police covers
        # exactly the seven boroughs - but Northumbria also covers
        # Northumberland, Avon and Somerset also covers Somerset, and
        # Nottinghamshire covers the whole county. Inverting to an exclude-list
        # there would mean naming every authority we do NOT want and silently
        # gaining a borough whenever ONS adds a CSP row.
        allowed = CSP_INCLUDE.get(city)
        if allowed is not None and name not in allowed:
            continue
        # ONS spells some of these differently from the registry. Mapped rather
        # than fuzzy-matched: a fuzzy match would also pair a genuinely missing
        # borough with a similar one and report success.
        name = CSP_RENAME.get(city, {}).get(name, name)
        rec = {hdr[j]: r[j] for j in range(len(hdr)) if hdr[j]}
        out[name] = rec
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true', help='update data/borough-extra.json')
    ap.add_argument('--check', action='store_true', help='report drift, exit 1 if any')
    ap.add_argument(
        '--city',
        default='london',
        choices=sorted(CITY_PFA),
        help='city to check. london reads data/borough-extra.json and supports '
             '--write; manchester is backend-only, so it reads CITIES directly '
             'and is check-only.',
    )
    args = ap.parse_args()

    ons = load_table(args.city)

    # Greater Manchester's ten rates were verified by hand on 2026-08-09 and all
    # matched. Wiring that in is what stops it being a one-off: ONS republishes
    # quarterly, and a check nobody can re-run decays into a claim.
    if args.city != 'london':
        if args.write:
            print(f'--write is London-only; {args.city} has no borough-extra.json entry.')
            return 2
        data, london = None, lambda_rates(args.city)
    else:
        data = json.loads(EXTRA.read_text(encoding='utf-8'))
        london = data['london']

    # London median per offence, computed across every borough ONS publishes a
    # figure for. Recomputed from the release each run rather than hard-coded,
    # so a vintage roll cannot leave the comparison anchored to a stale cohort.
    import statistics
    medians = {}
    for col in OFFENCE_COLS:
        vals = [float(r[col]) for r in ons.values() if isinstance(r.get(col), (int, float))]
        if vals:
            medians[col] = statistics.median(vals)

    drift, unresolved = [], []
    for canonical, rec in ons.items():
        key = SITE_ALIAS.get(canonical, canonical)
        if key not in london:
            continue
        total = rec.get(TOTAL_COL)
        if not isinstance(total, (int, float)):
            # ONS suppresses the City of London rate (small resident population),
            # so there is nothing to compare against and nothing to write. Whatever
            # the repo publishes there is our own figure, not theirs — see §11.
            unresolved.append((key, london[key].get('crimeRate'), str(total)))
            continue
        total = round(float(total), 1)
        current = london[key].get('crimeRate')
        if current != total:
            drift.append((key, current, total))
        if args.write:
            london[key]['crimeRate'] = total
            parts = [(c, float(rec[c])) for c in OFFENCE_COLS
                     if isinstance(rec.get(c), (int, float))]
            parts.sort(key=lambda t: -t[1])
            # Two numbers, because either alone misleads. The rate is what a
            # resident actually experiences; the ratio to the London median is
            # what makes the borough unusual. Richmond's violence is 26% of its
            # offences but it has the lowest total in London, so share-of-total
            # would paint its safest borough as violence-ridden. Westminster's
            # theft from the person is only 26% of its total but roughly twenty
            # times the London median — that is the fact worth telling someone.
            london[key]['crimeTop'] = [
                {'offence': c, 'ratePer1000': round(v, 1),
                 'shareOfTotal': round(100 * v / total, 1),
                 'vsLondonMedian': round(v / medians[c], 1) if medians.get(c) else None}
                for c, v in parts[:3]
            ]
            london[key]['crimeVintage'] = 'ONS Table C4, year ending March 2026'

    print(f'\n  city: {args.city}')
    # Compare each ONS row AFTER aliasing, against the repo's keys.
    # Comparing the aliased set against the raw set instead reported
    # `Barking and Dagenham` as unmatched when the alias resolves it.
    unmatched = sorted(n for n in ons if SITE_ALIAS.get(n, n) not in london)
    if unmatched:
        # Loud, because the loop below SKIPS any ONS row it cannot pair
        # up, so a rename on either side would quietly leave the
        # comparison rather than fail it.
        print(f'  ONS rows not matched to a repo borough: {unmatched}')
    print(f'  ONS rows: {len(ons)}   repo boroughs: {len(london)}')
    print(f'  boroughs whose rate differs from ONS: {len(drift)}')
    for k, cur, new in sorted(drift, key=lambda t: -abs((t[1] or 0) - t[2])):
        print(f'    {k:26} repo={str(cur):>7}  ONS={new:>7}  ({new - (cur or 0):+.1f})')
    if unresolved:
        print('\n  ONS publishes no rate for:')
        for k, cur, why in unresolved:
            print(f'    {k}: repo publishes {cur}, ONS says {why!r}')
            print('      -> our own figure. Must not be attributed to ONS. See METHODOLOGY §11.')

    if args.write:
        EXTRA.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
        )
        print(f'\n  wrote {EXTRA}')
        print('  NB: backend/lambdas/score/app.py LONDON_BOROUGHS holds its own copy '
              'and must be updated to match, or site and API will disagree.')
        return 0

    # Exit non-zero on DRIFT only, not on `unresolved`.
    #
    # `unresolved` is the City of London, and it is permanent: ONS states it does
    # not publish a rate there (Table C4 note 8) and never will. Failing on it
    # would leave this check red for ever, and a gate that is always red is a
    # gate nobody reads - the exact anti-pattern scripts/preflight.sh was
    # rewritten to avoid. It is reported loudly above and recorded as an open
    # decision in METHODOLOGY 11; it is not news.
    #
    # Drift IS news: the published rates have moved and the repo has not, which
    # is the condition this script exists to catch.
    if args.check and drift:
        print('\nRESULT: DRIFT — run with --write, and mirror into the Lambda.')
        return 1
    print('\nRESULT: in step with ONS.' if not drift else '')
    return 0


if __name__ == '__main__':
    sys.exit(main())
