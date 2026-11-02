"""How much smaller is DEFRA's 2021 Heathrow map than a normal year? Measured.

WHY THIS EXISTS
---------------
Every aircraft figure this product publishes rests on DEFRA's Round 4 strategic
noise map, which models 2021 traffic - a COVID year DEFRA itself calls
atypical. The caveat used to say the contours were "likely smaller than in a
normal year", a hand-wave. The CAA's own annual report for Heathrow publishes
Lden contour AREAS for a normal year, so the gap can be measured instead of
described. The current edition is ERCD Report 2601 (August 2026): 2025, when
movements were 1.1% above 2024's (2024 was 0.5% below 2019). Rolled from ERCD
2501's 2024 figures on 2026-11-01; the 55 dB area fell 148.4 -> 142.4 km2 (the
CAA puts it down to quieter types and 10 points more easterly operation).

    DEFRA 2021  - measured here from DEFRA's Heathrow Round 4 GeoTIFF
    CAA 2025    - ERCD Report 2601, Table 12 ("Heathrow 2025 Lden contours")

ROLLING TO A NEW EDITION (each August): set CAA_YEAR, CAA_KM2, CAA_SOURCE and
ERCD_URL together, run --verify-caa (it parses the new PDF), then --write, then
fix every page --check names. The JSON's keys carry no year (`caa_km2` and
`caa_year`), so readers never need renaming.

WHAT THE RATIO IS NOT. The two come from different models (the CAA's ANCON and
DEFRA's strategic-mapping method), with different inputs and population data.
The ratio is a published order of magnitude for a caveat, NEVER a correction
factor: scaling per-postcode readings by an area ratio would be a number nobody
measured (see memory project-lcy-airport-weighting). It is also Heathrow only;
ERCD reports cover Heathrow, Gatwick and Stansted, and this measures one.

Only the Heathrow GeoTIFF is gitignored (2.6 MB+), so the DEFRA half is
advisory: without it `--check` verifies the checked-in JSON and every page that
quotes it, and says it could not re-measure. It never reports that as a pass.

    python scripts/measure_covid_understatement.py --write        # GeoTIFF -> data/covid-understatement.json
    python scripts/measure_covid_understatement.py --check        # JSON consistent + pages quote it
    python scripts/measure_covid_understatement.py --verify-caa   # network: re-parse the ERCD report's Table 12
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'covid-understatement.json'
TIF = ROOT / 'data' / 'defra_aircraft_lden_heathrow.tif'
ERCD_URL = ('https://www.heathrow.com/content/dam/heathrow/web/common/documents/company/local-community/'
            'noise/reports-and-statistics/reports/noise-action-plan-contours/LHR_2025_Summer_and_NAP_Contours.pdf')
# ERCD Report 2601, Table 12, 2025 column (km2). Checked against the PDF by
# --verify-caa, which re-parses the table rather than trusting this literal.
CAA_YEAR = 2025
CAA_KM2 = {55: 142.4, 60: 59.0, 65: 21.4, 70: 7.0, 75: 2.7}
CAA_SOURCE = 'CAA ERCD Report 2601 (August 2026), Table 12: Heathrow 2025 Lden contours'
# The pages that quote the 55 dB comparison. Each must carry both areas as
# printed in the JSON, so a re-measurement that moves them reds here.
QUOTED_IN = ['index.html', 'METHODOLOGY.md', 'api/index.html']
# The served files that NAME the comparison's year or the CAA report (not METHODOLOGY: its changelog keeps the
# history). Every "CAA ... model(led) <year>" and "ERCD (Report) <number>" in them must be the current edition. The
# numbers alone were not enough: on 2026-11-01 the 2025 roll passed --check with seven airports' legends still
# saying "where the CAA also modelled 2024" and the street report's footer crediting "ERCD Report 2501".
EDITION_NAMED_IN = ['index.html', 'api/index.html', 'js/street_report.mjs']
YEAR_PHRASE = re.compile(r"\bCAA(?:'s)?(?: own)?(?: also)? model(?:led)?(?: of)? (20\d\d)\b")
EDITION_PHRASE = re.compile(r'\bERCD(?: Report)? (\d{4})\b')


def measure_defra():
    import rasterio

    with rasterio.open(TIF) as r:
        a = r.read(1)
        px_km2 = abs(r.transform.a * r.transform.e) / 1e6
    out = {}
    for t in CAA_KM2:
        m = (a >= t) & (a < 200)  # the Heathrow coverage's nodata is -3.4e38, below every threshold
        if m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any():
            raise SystemExit(f'the >= {t} dB contour touches the raster edge - its area would be an undercount')
        out[t] = round(float(m.sum()) * px_km2, 1)
    return out


def build(defra):
    rows = []
    for t, caa in CAA_KM2.items():
        rows.append({'lden_db': t, 'defra_2021_km2': defra[t], 'caa_km2': caa,
                     'ratio': round(caa / defra[t], 1)})
    return {
        'airport': 'LHR',
        'defra': "DEFRA strategic noise mapping Round 4 (2021 traffic), Heathrow Lden coverage, measured by this script",
        'caa': CAA_SOURCE,
        'caa_year': CAA_YEAR,
        'caveat': 'Different models and inputs; an order of magnitude for a caveat, never a correction factor.',
        'rows': rows,
    }


def headline(data):
    r = next(x for x in data['rows'] if x['lden_db'] == 55)
    return r


def check_pages(data):
    r = headline(data)
    if 'caa_km2' not in r:
        return [f'{OUT.name} has no caa_km2 at 55 dB (written before the year-free keys?): run --write']
    fails = []
    for rel in QUOTED_IN:
        text = (ROOT / rel).read_text(encoding='utf-8')
        for needle in (f"{r['defra_2021_km2']}", f"{r['caa_km2']}"):
            if needle not in text:
                fails.append(f'{rel} does not quote {needle} km2 (55 dB, from {OUT.name})')
    return fails + check_editions()


def check_editions(root: Path = ROOT) -> list[str]:
    """Every year and report number the served files give the CAA comparison is the current edition's."""
    edition = EDITION_PHRASE.search(CAA_SOURCE).group(1)
    fails = []
    for rel in EDITION_NAMED_IN:
        text = (root / rel).read_text(encoding='utf-8')
        for pattern, want, what in ((YEAR_PHRASE, str(CAA_YEAR), 'year'), (EDITION_PHRASE, edition, 'report')):
            for m in pattern.finditer(text):
                if m.group(1) != want:
                    line = text.count('\n', 0, m.start()) + 1
                    fails.append(f'{rel}:{line} names the CAA {what} {m.group(1)!r} ("{m.group(0)}"); '
                                 f'the current edition is {want}')
    return fails


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    g.add_argument('--verify-caa', action='store_true')
    a = ap.parse_args()

    if a.write:
        data = build(measure_defra())
        OUT.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8', newline='\n')
        for x in data['rows']:
            print(f"  >= {x['lden_db']} dB  DEFRA 2021 {x['defra_2021_km2']:>6} km2   CAA {data['caa_year']} {x['caa_km2']:>6} km2   x{x['ratio']}")
        print(f'wrote {OUT.relative_to(ROOT)}')
        return 0

    if a.verify_caa:
        import pdfplumber

        req = urllib.request.Request(ERCD_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as resp:
            pdf_bytes = resp.read()
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = '\n'.join((p.extract_text() or '') for p in pdf.pages[:40])
        i = text.index('Table 12')
        block = text[i:i + 1200]
        found = {int(t): float(v) for t, _prev, v in re.findall(r'> (\d\d) ([\d.]+) ([\d.]+) [+-]?\d+%', block)}
        bad = {t: (found.get(t), v) for t, v in CAA_KM2.items() if found.get(t) != v}
        if bad:
            print(f'FAIL: Table 12 disagrees with CAA_KM2 (parsed, held): {bad}')
            return 1
        # The title's "den" is a subscript, which pdfplumber puts on the next line ("Heathrow 2025 L contours").
        if f'Table 12 Heathrow {CAA_YEAR} L' not in block:
            print(f'FAIL: Table 12 is not titled for {CAA_YEAR} (CAA_YEAR); is ERCD_URL the right edition?')
            return 1
        print(f'ok: {CAA_SOURCE.split(",")[0]} Table 12 matches CAA_KM2 ({CAA_YEAR}) at {len(found)} thresholds')
        return 0

    if not OUT.exists():
        print(f'FAIL: {OUT.relative_to(ROOT)} missing - run --write with the Heathrow GeoTIFF present')
        return 1
    data = json.loads(OUT.read_text(encoding='utf-8'))
    fails = []
    if data.get('caa_year') != CAA_YEAR or data.get('caa') != CAA_SOURCE:
        fails.append(f"JSON names CAA {data.get('caa_year')} / {data.get('caa')!r}, the script holds {CAA_YEAR} / {CAA_SOURCE!r}: run --write")
    for x in data['rows']:
        if CAA_KM2.get(x['lden_db']) != x.get('caa_km2'):
            fails.append(f"{x['lden_db']} dB: JSON holds CAA {x.get('caa_km2')}, CAA_KM2 holds {CAA_KM2.get(x['lden_db'])}")
            continue
        if x['ratio'] != round(x['caa_km2'] / x['defra_2021_km2'], 1):
            fails.append(f"{x['lden_db']} dB: ratio {x['ratio']} is not CAA / DEFRA")
    fails += check_pages(data)
    remeasured = 'INCONCLUSIVE (Heathrow GeoTIFF absent; gitignored)'
    if TIF.exists():
        defra = measure_defra()
        drift = {t: (next(x for x in data['rows'] if x['lden_db'] == t)['defra_2021_km2'], v)
                 for t, v in defra.items()
                 if next(x for x in data['rows'] if x['lden_db'] == t)['defra_2021_km2'] != v}
        if drift:
            fails.append(f'DEFRA areas re-measured differently (JSON, now): {drift}')
        remeasured = 'DEFRA areas re-measured from the GeoTIFF and agree'
    if fails:
        print('FAIL:\n  ' + '\n  '.join(fails))
        return 1
    r = headline(data)
    print(f"ok: 55 dB Lden DEFRA 2021 {r['defra_2021_km2']} km2 vs CAA {data['caa_year']} {r['caa_km2']} km2 (x{r['ratio']}); "
          f'quoted consistently in {len(QUOTED_IN)} pages; {remeasured}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
