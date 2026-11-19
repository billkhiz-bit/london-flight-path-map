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

Usage:
    python scripts/fetch_metar.py 2026-01 2026-09            # every counted airport, January to September
    python scripts/fetch_metar.py 2026-02 2026-02 --airport LTN
    python scripts/fetch_metar.py 2026-01 2026-09 --refresh  # fetch again what is already cached
"""

import argparse
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
HEADER = 'station,valid,alti'


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


def reaches_month_end(path, y, m):
    """True when the cached file holds a reading on the month's last day (UTC). finished() alone kept a short month for
    good once it ended: one fetched while it ran, or by a request that ended a day early (until 2026-11-18). Audit
    2026-11-19 I-6: the 7 US stations kept three short months each after the UK stations were refetched. A station
    that truly reported nothing on its last day is asked again each run: one request, never a wrong month."""
    last = (dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)) - dt.timedelta(days=1)
    try:
        with open(path, encoding='utf-8') as fh:
            tail = fh.read().rstrip().rsplit('\n', 1)[-1]
    except OSError:
        return False
    return tail.startswith(last.isoformat())


def due(station, wanted, refresh=False, today=None):
    """The months of `wanted` to fetch for `station`: all with --refresh; else any not yet ended, and any ended month
    whose cached file is missing or does not reach the month's last day."""
    return [(y, m) for y, m in wanted
            if refresh or not finished(y, m, today)
            or not reaches_month_end(METAR_DIR / f'{station}-{y}-{m:02d}.csv', y, m)]


def request_end(last):
    """(year2, month2, day2) for a request through the month `last`: the FIRST day of the month after it, because
    IEM's end date is exclusive. Asking for the month's last day dropped that day from the last month of every request
    (18 Nov 2026: 46 cached months were a day short; September 2025's -air file ended 29 Sep, so N65 flew none of 30
    Sep's 1,284 flights). Rows are filed by their own month, so the end never adds a day to any file."""
    y, m = map(int, last.split('-'))
    return (y + 1, 1, 1) if m == 12 else (y, m + 1, 1)


def fetch(station, first, last):
    """[(valid 'YYYY-MM-DD HH:MM' UTC, alti inHg string)] for station over the months first..last, from IEM."""
    y1, m1 = map(int, first.split('-'))
    y2, m2, d2 = request_end(last)
    q = {'station': station, 'data': 'alti', 'year1': y1, 'month1': m1, 'day1': 1, 'year2': y2, 'month2': m2,
         'day2': d2, 'tz': 'Etc/UTC', 'format': 'onlycomma', 'latlon': 'no',
         'missing': 'M', 'trace': 'T', 'direct': 'no', 'report_type': '3'}
    req = urllib.request.Request(f'{ARCHIVE}?{urllib.parse.urlencode(q)}', headers={'User-Agent': 'Mozilla/5.0'})
    text = urllib.request.urlopen(req, timeout=180).read().decode('utf-8', 'replace')
    if not text.startswith(HEADER):
        raise SystemExit(f'{station}: IEM answered with something other than its CSV ({text[:60]!r})')
    rows = [(r['valid'], r['alti']) for r in csv.DictReader(io.StringIO(text)) if r['alti'] not in ('', 'M')]
    if not rows:
        raise SystemExit(f'{station}: IEM holds no altimeter readings for {first}..{last} (wrong station id?)')
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('first', help='YYYY-MM')
    ap.add_argument('last', help='YYYY-MM')
    ap.add_argument('--airport', action='append', help="the counter's airport code (LTN); repeatable")
    ap.add_argument('--refresh', action='store_true', help='fetch months already cached')
    a = ap.parse_args()
    wanted = list(months(a.first, a.last))
    METAR_DIR.mkdir(parents=True, exist_ok=True)
    for code in sorted(a.airport or METAR_STATION):
        station = METAR_STATION[code]
        todo = due(station, wanted, a.refresh)
        if not todo:
            print(f'{code} ({station}): cached')
            continue
        rows = fetch(station, f'{todo[0][0]}-{todo[0][1]:02d}', f'{todo[-1][0]}-{todo[-1][1]:02d}')
        for y, m in todo:
            mine = [r for r in rows if r[0].startswith(f'{y}-{m:02d}-')]
            with open(METAR_DIR / f'{station}-{y}-{m:02d}.csv', 'w', encoding='utf-8', newline='') as fh:
                fh.write('valid,alti\n' + ''.join(f'{v},{x}\n' for v, x in mine))
        print(f'{code} ({station}): {len(rows):,} readings, {len(todo)} month(s)')
        time.sleep(2)  # one airport at a time: the archive is a public service
    return 0


if __name__ == '__main__':
    sys.exit(main())
