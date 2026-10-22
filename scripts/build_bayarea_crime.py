"""Crime per 1,000 residents for the Bay Area's 50 cities: California DOJ and the Census (2026-10-18).

Release 2's crime input (ROADMAP "Release 2 plan", decision 4): each city's police agency in the
California DOJ OpenJustice "Crimes and Clearances" file, matched by NAME within its county (the file
carries no place code), over the Census Bureau's 2025 city population estimate, matched on GEOID.
Counted: violent + property crimes, the FBI's Part I groups, which is what reproduced decision 4's
anchor over every agency (California 2025: 22.27 per 1,000; adding arson gives 22.45). The anchor is
recomputed here, so a US scale built on it is derived, never typed in.

THE ANCHOR IS LIKE FOR LIKE (Bill, 2026-10-22, from the code review). A city's rate counts its own police
agency's crimes; the all-agency state rate also counted ~34,000 recorded by agencies with no residents of their
own (railroad police, universities, the Highway Patrol, transit, ports), crimes no city's rate can contain, so
every city read better than its anchor by construction. The anchor now counts only agencies that police
RESIDENTS (classify_agency: city and town police, county sheriffs, RESIDENT_AGENCIES), over the state's
residents: 2025, 21.39 per 1,000 (34,447 crimes of 209 agencies left out). Every city reads about 0.2-0.4 lower on the US scale, the cautious side.

Five cities have no rate of their own: the San Mateo County Sheriff polices them under contract,
and DOJ's context PDF counts their crime in the sheriff's figures. They carry `per_1000: null` and a
reason. Never share the sheriff's county total out among them.

Licence: both public domain (oag.ca.gov/conditions: "Considered in the public domain"; the Census
estimates are a US government work). Keyless downloads.

  python scripts/build_bayarea_crime.py --fetch   download both raw files (~6.4 MB) into data/
  python scripts/build_bayarea_crime.py --write   write data/us-bayarea-crime.json from them
  python scripts/build_bayarea_crime.py --check   the file is sound (offline); and, when the raw
                                                  files are on disk, every value against them
"""

import argparse
import csv
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CRIME_URL = ('https://data-openjustice.doj.ca.gov/sites/default/files/dataset/2026-07/'
             'Crimes_and_Clearances_with_Arson-1985-2025.csv')
POP_URL = 'https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/cities/totals/sub-est2025_6.csv'
CRIME_RAW = REPO / 'data' / 'openjustice' / CRIME_URL.rsplit('/', 1)[1]
POP_RAW = REPO / 'data' / 'census' / POP_URL.rsplit('/', 1)[1]
PLACES = REPO / 'data' / 'us-bayarea-places.json'
OUT = REPO / 'data' / 'us-bayarea-crime.json'
YEAR = 2025
KINDS = ('city', 'town')
# An agency with no residents of its own (classify_agency): railroads, universities and colleges, school
# districts, the Highway Patrol, transit, airports, ports and harbours, park districts and State Parks (DPR), Cal
# Fire, state hospitals and centres, the State Fair, prosecutors' investigators and marshals. Read only for an
# agency whose name is not a Census place, so a CITY whose name holds one of these words (Port Hueneme) is a city.
NO_RESIDENTS = re.compile(
    r'\b(RR|Railroad|Union Pacific|BNSF|UC|CSU|Cal Poly|University|College|School|Unified|Los Rios|'
    r'Highway Patrol|BART|Transit|Trans\. Authority|Airport|Harbor|Port|Park Dist|DPR|Cal Fire|'
    r'State Hospital|Developmental Center|State Fair|Investigations|Marshal)\b', re.I)
# Agencies that police RESIDENTS under a name that is not a Census place name, so they count in the anchor:
# a city named differently (Ventura is San Buenaventura, Paso Robles is El Paso de Robles, Suisun is Suisun
# City, Carmel is Carmel-by-the-Sea, Buelton is DOJ's spelling of Buellton, Angels Camp is the city of Angels),
# a joint municipal force (Central Marin: Corte Madera, Larkspur, San Anselmo), a sheriff-contract city reported
# on its own row (La Canada-Flintridge, Big Bear), and community police districts (Broadmoor, Kensington, Bear
# Valley, Lake Shastina, Stallion Springs). Held both ways: a name here that the year's file lacks, or that now
# matches a place, stops the build, and so does an agency in no class.
RESIDENT_AGENCIES = frozenset({
    'Angels Camp', 'Bear Valley', 'Big Bear', 'Broadmoor', 'Buelton', 'Carmel', 'Central Marin', 'Kensington',
    'La Canada-Flintridge', 'Lake Shastina', 'Paso Robles', 'Stallion Springs', 'Suisun', 'Ventura',
})
COUNTED = ('Violent_sum', 'Property_sum')
# Policed by the San Mateo County Sheriff under contract (DOJ's context PDF). A SET the check holds
# both ways: a city here that gains a DOJ row, or one not here that loses its row, fails the build.
SHERIFF_CONTRACT = frozenset({'Half Moon Bay', 'Millbrae', 'Portola Valley', 'San Carlos', 'Woodside'})
# The "few residents" note (decision 4): a small city whose rate is several times the state's.
FEW_RESIDENTS_POP = 20000
FEW_RESIDENTS_RATIO = 3
NO_RATE_REASON = ("policed by the San Mateo County Sheriff under contract; DOJ counts its crime in the "
                  "sheriff's county figures, so it has no rate of its own")


def few_residents(population, per_1000, state_per_1000):
    """True when a city's rate is per RESIDENT but its crime is not mostly residents' (decision 4).

    Crime is counted where it happens and divided by the people who sleep there, so a city whose
    shops, offices or cemeteries draw far more people by day than live in it reads alarming: Colma
    (1,385 residents, 469 per 1,000: Serramonte's malls and 17 cemeteries) and Emeryville (13,251,
    109 per 1,000: IKEA and Bay Street) are the two decision 4 names. The flag shows a note beside the
    figure; it never changes the number or the score.

    BOTH tests, because each alone says something false (Claude's recommendation; Bill: "do what is
    recommended", 2026-10-18):
    population alone would note Brisbane and Monte Sereno, where no alarming figure needs explaining;
    the rate alone would note Oakland (3.0 times the state), which does not have few residents.
    """
    return population < FEW_RESIDENTS_POP and per_1000 > FEW_RESIDENTS_RATIO * state_per_1000


def cities():
    """The 50 incorporated cities and towns: the places file also holds 28 census-designated places."""
    with open(PLACES, encoding='utf-8') as fh:
        return [p for p in json.load(fh)['places'] if p['kind'] in KINDS]


def read_population():
    """({7-digit place GEOID: (Census name, 2025 estimate)}, California's 2025 estimate)."""
    places, state = {}, None
    # Latin-1, as the Census Bureau writes it ("La Cañada Flintridge"); decoding as UTF-8 would fail
    with open(POP_RAW, encoding='latin-1', newline='') as fh:
        for r in csv.DictReader(fh):
            if r['SUMLEV'] == '040':
                state = int(r['POPESTIMATE2025'])
            elif r['SUMLEV'] == '162':  # an incorporated place, once (157 rows repeat it per county)
                places['06' + r['PLACE']] = (r['NAME'], int(r['POPESTIMATE2025']))
    if state is None or not places:
        raise SystemExit(f'{POP_RAW.name}: no state row or no place rows; the Census changed the layout')
    return places, state


def read_crime():
    """({(county, agency): (violent, property)} for YEAR, California's YEAR total over every agency)."""
    agencies, total, blank = {}, 0, []
    with open(CRIME_RAW, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh):
            if r['Year'] != str(YEAR):
                continue
            cells = [r[k] for k in COUNTED]
            if not all(c.isdigit() for c in cells):
                blank.append(f"{r['NCICCode']} ({r['County']})")  # a blank is absence, never a zero
                continue
            key = (r['County'], r['NCICCode'])
            if key in agencies:
                raise SystemExit(f'{CRIME_RAW.name}: {key} appears twice in {YEAR}')
            agencies[key] = tuple(map(int, cells))
            total += sum(agencies[key])
    if not agencies:
        raise SystemExit(f'{CRIME_RAW.name}: no {YEAR} rows')
    if blank:
        raise SystemExit(f'{CRIME_RAW.name}: {len(blank)} agencies have a blank count in {YEAR}, so the state '
                         f'total would undercount: {blank[:5]}')
    return agencies, total


def place_names(population):
    """Every California city and town as DOJ names its police agency: the Census name less ' city'/' town'."""
    return {re.sub(r' (city|town)$', '', name) for name, _ in population.values()}


def classify_agency(agency, places):
    """'place', 'sheriff', 'resident' or 'no-residents' for one DOJ agency name; anything else raises."""
    if agency in places:
        return 'place'
    if 'sheriff' in agency.lower():
        return 'sheriff'
    if agency in RESIDENT_AGENCIES:
        return 'resident'
    if NO_RESIDENTS.search(agency):
        return 'no-residents'
    raise SystemExit(f'DOJ agency {agency!r} is in no class: decide whether it polices residents (add it to '
                     'RESIDENT_AGENCIES) or has none of its own (NO_RESIDENTS) before writing')


def state_anchor(agencies, population, state_pop):
    """California's like-for-like rate: crimes of every agency policing residents, over the state's residents."""
    places = place_names(population)
    kinds = {name: classify_agency(name, places) for _, name in agencies}
    stale = sorted(n for n in RESIDENT_AGENCIES if kinds.get(n) != 'resident')
    if stale:
        raise SystemExit(f'RESIDENT_AGENCIES names {stale}, which the {YEAR} file lacks or now holds as a place')
    counted = sum(sum(v) for (_, name), v in agencies.items() if kinds[name] != 'no-residents')
    left_out = [(name, sum(v)) for (_, name), v in agencies.items() if kinds[name] == 'no-residents']
    return {'crimes': counted, 'population': state_pop, 'per_1000': round(1000 * counted / state_pop, 2),
            'crimes_all_agencies': counted + sum(n for _, n in left_out),
            'left_out': {'agencies': len(left_out), 'crimes': sum(n for _, n in left_out),
                         'why': 'agencies with no residents of their own (railroads, universities and colleges, '
                                'school districts, the Highway Patrol, transit, airports, ports, State Parks, Cal '
                                "Fire, state hospitals): no city's rate can contain their crimes"}}


def build():
    agencies, _ = read_crime()
    population, state_pop = read_population()
    california = state_anchor(agencies, population, state_pop)
    state_per_1000 = california['per_1000']
    rows = []
    for p in cities():
        name, pop = population.get(p['geoid'], (None, None))
        if pop is None or not name.startswith(p['name'] + ' '):
            raise SystemExit(f"{p['name']} ({p['geoid']}): the Census row is {name!r}, not this city")
        county = p['county'].removesuffix(' County') + ' County'
        counts = agencies.get((county, p['name']))
        if (counts is None) != (p['name'] in SHERIFF_CONTRACT):
            raise SystemExit(f"{p['name']}: {'no' if counts is None else 'a'} DOJ row in {county}, yet it is "
                             f"{'not ' if counts is None else ''}in SHERIFF_CONTRACT; find out why before writing")
        row = {'geoid': p['geoid'], 'name': p['name'], 'kind': p['kind'], 'county': p['county'],
               'population': pop}
        if counts is None:
            row.update(agency=None, violent=None, property=None, per_1000=None, few_residents=False,
                       no_rate=NO_RATE_REASON)
        else:
            per_1000 = round(1000 * sum(counts) / pop, 1)
            row.update(agency=p['name'], violent=counts[0], property=counts[1], per_1000=per_1000,
                       few_residents=bool(few_residents(pop, per_1000, state_per_1000)))
        rows.append(row)
    return {
        'source': 'California DOJ OpenJustice, Crimes and Clearances (violent + property crimes by agency), over '
                  'the US Census Bureau Vintage 2025 city population estimates',
        'year': YEAR,
        'urls': [CRIME_URL, POP_URL],
        'licence': 'public domain (oag.ca.gov/conditions; Census estimates a US government work)',
        'generator': 'scripts/build_bayarea_crime.py --write',
        'counted': ' + '.join(COUNTED),
        'california': california,
        'scope': 'crimes where they were recorded, per RESIDENT; not comparable with the UK rate (ONS Table C4 '
                 'counts all recorded crime except fraud)',
        'cities': rows,
    }


def problems(doc, want):
    """Every way the file can be wrong without the raw files: coverage, the sheriff set, arithmetic."""
    out = []
    have = {r['geoid'] for r in doc['cities']}
    if have != {p['geoid'] for p in want}:
        out.append(f"coverage: missing {sorted({p['name'] for p in want if p['geoid'] not in have})}, "
                   f"extra {sorted(have - {p['geoid'] for p in want})}")
    no_rate = {r['name'] for r in doc['cities'] if r['per_1000'] is None}
    if no_rate != SHERIFF_CONTRACT:
        out.append(f'cities without a rate {sorted(no_rate)} are not the sheriff-contract set '
                   f'{sorted(SHERIFF_CONTRACT)}')
    for r in doc['cities']:
        if r['per_1000'] is None:
            if r['violent'] is not None or r['property'] is not None or r['few_residents'] or not r.get('no_rate'):
                out.append(f"{r['name']}: no rate, yet carries counts or a flag, or no reason")
            continue
        if r['per_1000'] != round(1000 * (r['violent'] + r['property']) / r['population'], 1):
            out.append(f"{r['name']}: per_1000 {r['per_1000']} is not its counts over its population")
    ca = doc['california']
    if not 10 < ca['per_1000'] < 40 or ca['per_1000'] != round(1000 * ca['crimes'] / ca['population'], 2):
        out.append(f'implausible California anchor {ca}')
    if ca.get('crimes_all_agencies') != ca['crimes'] + ca.get('left_out', {}).get('crimes', -1):
        out.append('the anchor does not say what it left out: crimes + left_out must be the all-agency total')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.fetch:
        for url, raw in ((CRIME_URL, CRIME_RAW), (POP_URL, POP_RAW)):
            raw.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers={'User-Agent': 'SkyScore/1.0 (support@skyscore.co.uk)'})
            with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310 - fixed https URLs
                raw.write_bytes(resp.read())
            print(f'fetched {raw.relative_to(REPO)} ({raw.stat().st_size:,} bytes)')
        return 0
    if a.write:
        doc = build()
        OUT.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
        flagged = [r['name'] for r in doc['cities'] if r['few_residents']]
        print(f"wrote {OUT.relative_to(REPO)}: {sum(r['per_1000'] is not None for r in doc['cities'])} rated, "
              f"California {doc['california']['per_1000']} per 1,000, few-residents note on {flagged}")
        return 0
    doc = json.loads(OUT.read_text(encoding='utf-8'))
    failures = problems(doc, cities())
    if CRIME_RAW.exists() and POP_RAW.exists():
        if build() != doc:
            failures.append(f'{OUT.name} is not what the raw files give (re-run --write)')
        else:
            print(f'  raw files      {OUT.name} == {CRIME_RAW.name} + {POP_RAW.name}')
    else:
        print('INCONCLUSIVE for values: the raw files are not on disk (run --fetch); shape and arithmetic checked')
    if failures:
        print('RESULT: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    rated = [r for r in doc['cities'] if r['per_1000'] is not None]
    print(f"RESULT: PASS ({len(rated)} of {len(doc['cities'])} cities rated, {YEAR}, "
          f"California {doc['california']['per_1000']} per 1,000)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
