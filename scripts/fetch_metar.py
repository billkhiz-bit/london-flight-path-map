"""Fetch each counted airport's QNH from its METAR reports, for the counter's field level through the day.

WHY (2026-10-23, Luton's February). adsb_movements.py judges "low" against the field's PRESSURE altitude, which a
storm moves 300-570 ft within a day. Touchdown votes alone could follow it only where arrivals are frequent; Luton's
mornings are departures, so on 13 and 19 February the morning field read 300-420 ft under the field the METARs
imply, and morning departures were dropped. The METARs give the SHAPE of the day (how far the field moved since
any vote), the aircraft still give its LEVEL; see adsb_movements.FieldLevel.

WHAT. The Iowa Environmental Mesonet's archive of airport weather reports (mesonet.agron.iastate.edu, public), one
request per airport for the whole range, the altimeter setting in inches of mercury, cached per airport per month
as data/metar/<station>-<YYYY-MM>.csv (gitignored, like every data/ file). The counter never fetches: a day whose
month is not cached falls back to the aircraft alone, as before this file existed.

A 200 IS NOT THE FILE (the same day's lesson, from DEFRA's maintenance page): an answer is kept only when it is
IEM's CSV, header `station,valid,alti`; a web page or an empty station raises, naming the airport.

THE DAY'S AIR FOR N65 (2026-11-03, `--air`). Doc 29 flies each departure and approach for the air and wind on the day
(scripts/n65_profiles.Atmosphere): temperature, QNH and the headwind along the runway. `--air` fetches the temperature
(F), the wind (the direction it blows FROM, true degrees; its speed, kt) and the altimeter into a SEPARATE file per
month, data/metar/<station>-<YYYY-MM>-air.csv, so the counter's cache above is never rewritten. A missing wind reading
is kept blank (the reader says so); a report with no temperature or no altimeter is dropped.

Usage:
    python scripts/fetch_metar.py 2026-01 2026-09            # every counted airport, January to September
    python scripts/fetch_metar.py 2026-02 2026-02 --airport LTN
    python scripts/fetch_metar.py 2026-01 2026-09 --refresh  # fetch again what is already cached
    python scripts/fetch_metar.py 2026-07 2026-07 --airport LHR --air
"""

import argparse
import calendar
import csv
import datetime as dt
import io
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adsb_movements import METAR_DIR, METAR_STATION  # noqa: E402  the one holder of the airport -> station map

ARCHIVE = 'https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py'


def months(first, last):
    y, m = map(int, first.split('-'))
    ly, lm = map(int, last.split('-'))
    while (y, m) <= (ly, lm):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def finished(y, m, today=None):
    """True once the month has ended (UTC). A month fetched while it runs is partial, so it is fetched again until
    then: skipping it as "cached" would leave the counter its first half for good."""
    today = today or dt.datetime.now(dt.UTC).date()
    return (y, m) < (today.year, today.month)


AIR_FIELDS = ('tmpf', 'drct', 'sknt', 'alti')


def _request(station, first, last, fields):
    """IEM's CSV text for station over the months first..last, refused unless it is that CSV (header first)."""
    (y1, m1), (y2, m2) = map(int, first.split('-')), map(int, last.split('-'))
    q = [('station', station), *(('data', f) for f in fields), ('year1', y1), ('month1', m1), ('day1', 1),
         ('year2', y2), ('month2', m2), ('day2', calendar.monthrange(y2, m2)[1]), ('tz', 'Etc/UTC'),
         ('format', 'onlycomma'), ('latlon', 'no'), ('missing', 'M'), ('trace', 'T'), ('direct', 'no'),
         ('report_type', '3')]
    req = urllib.request.Request(f'{ARCHIVE}?{urllib.parse.urlencode(q)}', headers={'User-Agent': 'Mozilla/5.0'})
    text = urllib.request.urlopen(req, timeout=180).read().decode('utf-8', 'replace')
    if not text.startswith('station,valid,' + ','.join(fields)):
        raise SystemExit(f'{station}: IEM answered with something other than its CSV ({text[:60]!r})')
    return text


def fetch(station, first, last):
    """[(valid 'YYYY-MM-DD HH:MM' UTC, alti inHg string)] for station over the months first..last, from IEM."""
    text = _request(station, first, last, ('alti',))
    rows = [(r['valid'], r['alti']) for r in csv.DictReader(io.StringIO(text)) if r['alti'] not in ('', 'M')]
    if not rows:
        raise SystemExit(f'{station}: IEM holds no altimeter readings for {first}..{last} (wrong station id?)')
    return rows


def fetch_air(station, first, last):
    """[(valid, tmpf, drct, sknt, alti)] as strings (a missing wind reading blank) for N65's day's air, from IEM. A
    report without a temperature or an altimeter is dropped; none at all is refused, naming the station."""
    text = _request(station, first, last, AIR_FIELDS)
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if r['tmpf'] in ('', 'M') or r['alti'] in ('', 'M'):
            continue
        rows.append((r['valid'], r['tmpf'], *('' if r[f] in ('', 'M') else r[f] for f in ('drct', 'sknt')), r['alti']))
    if not rows:
        raise SystemExit(f'{station}: IEM holds no temperature and altimeter readings for {first}..{last}')
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('first', help='YYYY-MM')
    ap.add_argument('last', help='YYYY-MM')
    ap.add_argument('--airport', action='append', help="the counter's airport code (LTN); repeatable")
    ap.add_argument('--refresh', action='store_true', help='fetch months already cached')
    ap.add_argument('--air', action='store_true', help="N65's day's air: temperature, wind, altimeter (-air.csv)")
    a = ap.parse_args()
    suffix, head = ('-air', 'valid,' + ','.join(AIR_FIELDS)) if a.air else ('', 'valid,alti')
    wanted = list(months(a.first, a.last))
    METAR_DIR.mkdir(parents=True, exist_ok=True)
    for code in sorted(a.airport or METAR_STATION):
        station = METAR_STATION[code]
        todo = [(y, m) for y, m in wanted
                if a.refresh or not finished(y, m) or not (METAR_DIR / f'{station}-{y}-{m:02d}{suffix}.csv').exists()]
        if not todo:
            print(f'{code} ({station}): cached')
            continue
        span = (f'{todo[0][0]}-{todo[0][1]:02d}', f'{todo[-1][0]}-{todo[-1][1]:02d}')
        rows = fetch_air(station, *span) if a.air else fetch(station, *span)
        for y, m in todo:
            mine = [r for r in rows if r[0].startswith(f'{y}-{m:02d}-')]
            with open(METAR_DIR / f'{station}-{y}-{m:02d}{suffix}.csv', 'w', encoding='utf-8', newline='') as fh:
                fh.write(head + '\n' + ''.join(','.join(r) + '\n' for r in mine))
        print(f'{code} ({station}): {len(rows):,} readings, {len(todo)} month(s)')
        time.sleep(2)  # one airport at a time: the archive is a public service
    return 0


if __name__ == '__main__':
    sys.exit(main())
