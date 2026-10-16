"""DNL vs Lden for New York's airports, from the hour of day of real movements.

DNL (US): 07-22 unweighted, 22-07 +10 dB. Lden (UK/EU): 07-19 unweighted, 19-23
+5 dB, 23-07 +10 dB. With noise energy taken as proportional to movements (the
same aircraft mix all day), the gap is 10 log10(Lden energy / DNL energy).
Hours in local time (America/New_York).

MEASURED 2026-10-16 over July-August 2026 (all extract days): Lden - DNL = JFK +0.01,
LGA +0.13, EWR +0.06, TEB +0.27 dB. Lden's +5 dB on 19:00-23:00 is almost exactly
offset by DNL's +10 dB on 22:00-23:00, so the Port Authority's monitor DNL can stand
in for Lden once this gap is added. The `near` filter samples every 20th point, so
totals are not adsb_movements.py's counts; only the hour-of-day SHARES are used.
"""
import datetime as dt
import gzip
import json
import math
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))
import adsb_movements as am  # noqa: E402

NY = ZoneInfo('America/New_York')
CODES = ('JFK', 'LGA', 'EWR', 'TEB')


def day_hours(path):
    airports = am.load_airports()
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        traces = [json.loads(line) for line in fh]
    out = {c: Counter() for c in CODES}
    for code in CODES:
        ap = airports[code]
        (clat, clon), zone = ap['centre'], ap['zone_km']
        near = [r for r in traces if any(am.km_between(p[1], p[2], clat, clon) <= zone for p in r['pts'][::20])]
        field, _ = am.field_level(near, ap)
        if field is None:
            continue
        for rec in near:
            moves, _ = am.movements(rec, ap, field)
            for _, _, t in moves:
                out[code][dt.datetime.fromtimestamp(t, NY).hour] += 1
    return out


def gap(hours):
    dnl = lden = 0.0
    for h, n in hours.items():
        dnl += n * (10 if (h >= 22 or h < 7) else 1)
        lden += n * (10 if (h >= 23 or h < 7) else (10 ** 0.5 if h >= 19 else 1))
    return 10 * math.log10(lden / dnl)


if __name__ == '__main__':
    files = sorted((REPO / 'data' / 'adsb' / 'extract').glob('2026-0[78]-*.jsonl.gz'))
    total = {c: Counter() for c in CODES}
    with ProcessPoolExecutor(6) as ex:
        for res in ex.map(day_hours, files):
            for c in CODES:
                total[c].update(res[c])
    for c in CODES:
        h = total[c]
        n = sum(h.values())
        eve = sum(v for k, v in h.items() if 19 <= k < 22)
        late = h[22]
        night = sum(v for k, v in h.items() if k >= 23 or k < 7)
        print(f'{c}: {n} movements; 19-22 {eve / n:.1%}, 22-23 {late / n:.1%}, 23-07 {night / n:.1%}; '
              f'Lden - DNL = {gap(h):+.2f} dB')
