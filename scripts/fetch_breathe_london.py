"""Breathe London's sensors: each live sensor's NO2 and PM2.5 mean over the last 12 months.

WHY (2026-10-19). Step 1 of ROADMAP's "The plan for Breathe London". The GLA's Breathe
London network has about 150 low-cost sensors across all 33 boroughs, many at schools,
hospitals and kerbs, where DEFRA's 1 km background model (PCM) cannot see a busy street.
The front page and street report will show the nearest sensor's 12-month mean beside
DEFRA's background figure (step 3, not built). DISPLAY ONLY, NEVER SCORED, as for the AURN
monitors (`fetch_aurn.py`): measured air quality in the score would be a methodology
change, decided on its own. Nothing reads this file yet.

WHAT IT HOLDS. `data/breathe-london-sensors.json`, checked in: one row per live sensor with
a usable mean - site code, name, its borough (ONS code, by point-in-polygon on our own
London boundaries, never the API's borough NAME), the network's classification (Urban
Background, Roadside, Kerbside), location type (School, Hospital, Street ...), distance to
the kerb and height in metres, position, the day this place began measuring, and for NO2 and
PM2.5 the mean, the share of the window's hours it rests on, and the share of those hours
already ratified.

THE KEY. The GLA's API needs a key, sent in an `X-API-KEY` header (never in a URL, so no
logged address can carry it). It lives only in the repo's gitignored `.env` as
`BREATHE_LONDON_API_KEY`, read from the environment or that file; this script never prints
it and redacts it from any error body. No page or visitor calls the API: the browser will
read the checked-in file. `--fetch` refuses to write or cache anything holding the key, and
`--check` searches the file for it wherever the key is available.

THE WINDOW is the 12 whole calendar months before the month of the fetch (fetched on
19 Oct 2026: 1 Oct 2025 to 30 Sep 2026), so a figure can be named ("the 12 months to
September 2026") and two fetches in one month cover the same hours. Hours are UTC.

ONE PLACE PER MEAN. `/ListSensors` holds one row per INSTALLATION (327 rows, 153 live), and
`/SensorData` by site code returns the hours of every installation under that code. On
2026-10-19, 27 live sensors had an earlier installation inside the window, all 27 at the same
place (a device swapped on the same post). A sensor MOVED under its code would otherwise
blend two places into one mean filed at the new position, so only the hours since the
unbroken run of same-place installations began count (`measuring_since`), and `--check`
refuses a capture larger than those hours allow.

THE API'S SHAPES, measured 2026-10-19 on BL0086 (a year of each species):
  - `endTime` is INCLUSIVE: 1 Oct 00:00 to 3 Oct 00:00 returns 49 hours. We ask for the
    window's last hour and drop anything outside [start, end) all the same.
  - A missing hour comes back as a ROW whose `ScaledValue` is null (29 of 8,760 NO2 hours),
    and a sensor installed inside the window has no rows before it. So capture is valid
    hours over the WINDOW's hours, never over the rows returned.
  - `RatificationStatus` is "P" (provisional) or "R" (ratified): PM2.5 was 25% "R", NO2 all
    "P". Calibration is revised weekly and recalculated every six months, so past values
    change and a re-fetch can move a mean a little. The file carries its fetch date.

CAPTURE FLOOR 75% of the window's hours (Bill, 2026-10-13, the same floor as AURN). Neither
network publishes a completeness rule for a mean shown to the public, so ours is a choice
and the page that shows it must say so.

NOT A RANKING. A kerbside sensor and a background one measure different things (UK-AIR
gives the same warning for its own monitors): show the nearest sensor with its
classification and kerb distance; never order sensors or boroughs by these numbers.

ATTRIBUTION, exactly as breathelondon.org/developers requires it (read 2026-10-11, their
spelling): "Contains Breathe London data licensed under the Open Government License v3.0",
linked to breathelondon.org.

    python scripts/fetch_breathe_london.py --fetch    # network + key; writes the file
    python scripts/fetch_breathe_london.py --check    # offline, blocking: the file keeps its rules
    python scripts/fetch_breathe_london.py --verify   # re-derives from the cached raw files (advisory)
"""

from __future__ import annotations

import argparse
import collections
import datetime
import gzip
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))
from build_city_stations import _point_in_geometry  # noqa: E402

OUT = REPO / 'data' / 'breathe-london-sensors.json'
RAW = REPO / 'data' / 'breathe-london'  # gitignored, like every raw download under data/
BOROUGHS = REPO / 'data' / 'london-boroughs.json'
ENV_FILE = REPO / '.env'
KEY_NAME = 'BREATHE_LONDON_API_KEY'
BASE = 'https://breathe-london-7x54d7qf.ew.gateway.dev'
UA = 'skyscore-data-fetch/1 (+https://skyscore.co.uk)'

CAPTURE_FLOOR = 0.75
# Our key -> the API's Species value.
SPECIES = {'no2': 'NO2', 'pm25': 'PM25'}
UNITS = 'ug.m-3'
# A sanity ceiling, not a limit value: a 12-month mean above these is a broken read.
PLAUSIBLE_MAX = {'no2': 150.0, 'pm25': 100.0}
CLASSIFICATIONS = frozenset({'Urban Background', 'Roadside', 'Kerbside'})
ATTRIBUTION = 'Contains Breathe London data licensed under the Open Government License v3.0'
ATTRIBUTION_LINK = 'https://www.breathelondon.org/'
OGL_URL = 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/'
# Between requests: no rate limit is published, and the terms forbid exceeding "usage limits".
PAUSE_S = 0.2
HOUR = datetime.timedelta(hours=1)
STAMP = '%Y-%m-%dT%H:%M:%SZ'

# A borough with no usable sensor inside it, and why. The check fails on an undeclared
# borough with none AND on a declared borough that has one, so this cannot go stale in
# either direction.
NO_SENSOR_INSIDE: dict[str, str] = {}


def window(today: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """[start, end) in UTC: the 12 whole calendar months before `today`'s month."""
    end = datetime.datetime(today.year, today.month, 1, tzinfo=datetime.UTC)
    return end.replace(year=end.year - 1), end


def window_label(start: datetime.datetime, end: datetime.datetime) -> dict:
    return {'from': start.date().isoformat(), 'to': (end - HOUR).date().isoformat()}


def local_key() -> str | None:
    """The API key from the environment, else the repo's .env. Never printed."""
    key = os.environ.get(KEY_NAME, '').strip()
    if not key and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.partition('=')
            if sep and name.strip() == KEY_NAME:
                key = value.strip().strip('"\'')
    return key or None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # urllib copies every header but the content ones onto a redirect, to any host and over
    # plain http too, so following one would hand the key to wherever the gateway pointed.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f'refused a redirect to {newurl}', headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def api_get(key: str, path: str, params: dict | None = None) -> bytes:
    url = BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
    req = urllib.request.Request(url, headers={'X-API-KEY': key, 'User-Agent': UA})
    for attempt in range(3):
        try:
            with _OPENER.open(req, timeout=300) as resp:  # noqa: S310 - https, our constant
                return resp.read()
        except urllib.error.HTTPError as exc:
            # Redact the WHOLE body, then cut it: cut first, a key straddling the cut prints half.
            body = (exc.read() or b'').decode('utf-8', 'replace').replace(key, '<key>')[:300]
            body = body or str(exc.reason).replace(key, '<key>')
            if (exc.code < 500 and exc.code != 429) or attempt == 2:
                raise SystemExit(f'{path} {params or ""}: HTTP {exc.code} {body}') from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                raise SystemExit(f'{path} {params or ""}: {str(exc).replace(key, "<key>")}') from None
        time.sleep(5 * (attempt + 1))
    raise AssertionError('unreachable')


def cached(key: str | None, dest: Path, path: str, params: dict | None = None) -> list:
    """The API's answer, from the raw cache or fetched into it. Only lists are cached."""
    if not dest.exists():
        if key is None:
            raise SystemExit(f'{dest.relative_to(REPO)} is not cached and there is no key to fetch it')
        body = api_get(key, path, params)
        parsed = json.loads(body)
        # Both forms: the raw bytes, and the decoded content (JSON can spell the key in \u escapes).
        if key.encode() in body or key in json.dumps(parsed, ensure_ascii=False):
            raise SystemExit(f'{path}: the answer contains the API key; nothing cached')
        if not isinstance(parsed, list):
            raise SystemExit(f'{path} {params or ""}: expected a list, got {body[:200]!r}')
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Written whole, then renamed: an interrupted fetch must not leave a truncated file that a
        # same-day resume would take as cached.
        part = dest.with_name(dest.name + '.part')
        part.write_bytes(gzip.compress(body))
        os.replace(part, dest)
        time.sleep(PAUSE_S)
    return json.loads(gzip.decompress(dest.read_bytes()))


def london_boroughs() -> list[tuple[str, str, dict]]:
    """(ONS code, name, geometry) for the 33 boroughs we ship."""
    gj = json.loads(BOROUGHS.read_text(encoding='utf-8'))
    return [(f['properties']['LAD13CD'], f['properties']['LAD13NM'], f['geometry']) for f in gj['features']]


def borough_of(lat: float, lon: float, boroughs) -> tuple[str, str] | None:
    return next(((code, name) for code, name, geom in boroughs if _point_in_geometry(lon, lat, geom)), None)


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _hour(stamp) -> datetime.datetime | None:
    try:
        t = datetime.datetime.strptime(str(stamp), STAMP).replace(tzinfo=datetime.UTC)
    except ValueError:
        return None
    return t if t.minute == 0 and t.second == 0 else None


def same_place(a: dict, b: dict) -> bool:
    """Two installations measure the same place: position to about 10 m, classification, kerb distance.
    Height is left out: a device swapped on the same post can sit 0.4 m higher (BL0056)."""
    pa = (_num(a.get('Latitude')), _num(a.get('Longitude')))
    pb = (_num(b.get('Latitude')), _num(b.get('Longitude')))
    if None in pa + pb:
        return False
    return (abs(pa[0] - pb[0]) < 1e-4 and abs(pa[1] - pb[1]) < 1e-4
            and a.get('SiteClassification') == b.get('SiteClassification')
            and _num(a.get('DistanceToKerb')) == _num(b.get('DistanceToKerb')))


def measuring_since(installations: list[dict], live: dict) -> datetime.datetime | None:
    """When the live installation's PLACE began measuring: the start of the earliest installation in the
    run of same-place installations that ends with the live one. An installation elsewhere ends the run."""
    try:
        since = datetime.datetime.strptime(str(live.get('StartDate')), STAMP).replace(tzinfo=datetime.UTC)
    except ValueError:
        return None
    for r in sorted((r for r in installations if r is not live), key=lambda r: str(r.get('StartDate')), reverse=True):
        try:
            began = datetime.datetime.strptime(str(r.get('StartDate')), STAMP).replace(tzinfo=datetime.UTC)
        except ValueError:
            break
        if began >= since:
            continue
        if not same_place(r, live):
            break
        since = began
    return since.replace(minute=0, second=0)


def summarise(rows: list[dict], code: str, species: str, start: datetime.datetime, end: datetime.datetime,
              since: datetime.datetime | None = None) -> tuple[dict | None, str | None]:
    """One sensor's mean for one species over [start, end), or why there is none. Hours before `since`
    (when this place began measuring) are another place's and are dropped; capture stays over the
    window's hours, so a sensor that moved mid-window rests on its new place's share of the year."""
    hours = round((end - start) / HOUR)
    first = max(start, since) if since else start
    seen: dict[datetime.datetime, dict] = {}
    for r in rows:
        if r.get('SiteCode') != code or r.get('Species') != species:
            return None, f'the API answered with a row for {r.get("SiteCode")} {r.get("Species")}'
        t = _hour(r.get('DateTime'))
        if t is None:
            return None, f'unreadable hour {r.get("DateTime")!r}'
        if not first <= t < end:
            continue  # another place's hour, or the inclusive endTime's neighbour
        if t in seen:
            return None, f'hour {r.get("DateTime")} returned twice'
        seen[t] = r
    valid = [r for r in seen.values() if _num(r.get('ScaledValue')) is not None]
    if not valid:
        return None, 'no readings in the window'
    shapes = {(r.get('Units'), r.get('Duration')) for r in valid}
    if shapes != {(UNITS, 'PT1H')}:
        return None, f'not hourly {UNITS}: {sorted(map(str, shapes))}'
    capture = len(valid) / hours
    if capture < CAPTURE_FLOOR:
        moved = f' (measuring here since {first.date().isoformat()})' if first > start else ''
        return None, f'capture {round(capture * 100)}% of hours{moved}'
    mean = sum(_num(r['ScaledValue']) for r in valid) / len(valid)
    ratified = sum(1 for r in valid if r.get('RatificationStatus') == 'R') / len(valid)
    return {'mean': round(mean, 1), 'capture': round(capture, 3), 'ratified': round(ratified, 3)}, None


def build(sensors: list[dict], series: dict[tuple[str, str], list[dict]], fetched: str, boroughs) -> dict:
    """The file's content from the API's answers. Pure: --fetch and --verify both call it."""
    start, end = window(datetime.date.fromisoformat(fetched))
    live = [s for s in sensors if not s.get('EndDate')]
    installs = collections.Counter(str(s.get('SiteCode')) for s in live)
    every: dict[str, list[dict]] = collections.defaultdict(list)  # each code's installations, ended ones too
    for s in sensors:
        every[str(s.get('SiteCode'))].append(s)
    sites, excluded, done = [], [], set()
    for s in sorted(live, key=lambda s: str(s.get('SiteCode'))):
        code, name = str(s.get('SiteCode')), str(s.get('SiteName') or '').strip()
        if code in done:
            continue
        done.add(code)
        if installs[code] > 1:
            excluded.append({'code': code, 'site': name, 'reason': f'{installs[code]} live installations'})
            continue
        lat, lon = _num(s.get('Latitude')), _num(s.get('Longitude'))
        if lat is None or lon is None:
            excluded.append({'code': code, 'site': name, 'reason': 'no readable position'})
            continue
        lat, lon = round(lat, 5), round(lon, 5)
        where = borough_of(lat, lon, boroughs)
        if where is None:
            excluded.append({'code': code, 'site': name, 'reason': f'({lat}, {lon}) is inside no London borough'})
            continue
        since = measuring_since(every[code], s)
        record = {'code': code, 'name': name, 'borough': where[0], 'boroughName': where[1],
                  'classification': s.get('SiteClassification'), 'locationType': s.get('SiteLocationType'),
                  'kerbDistanceM': _num(s.get('DistanceToKerb')), 'heightM': _num(s.get('SensorHeightAboveGround')),
                  'lat': lat, 'lon': lon, 'measuringSince': since.date().isoformat() if since else None}
        for key, species in SPECIES.items():
            if (code, species) not in series:
                record[key], reason = None, 'not fetched'
            else:
                record[key], reason = summarise(series[(code, species)], code, species, start, end, since)
            if reason:
                excluded.append({'code': code, 'site': name, 'pollutant': key, 'reason': reason})
        if record['no2'] or record['pm25']:
            sites.append(record)
    excluded.sort(key=lambda e: (e['code'], e.get('pollutant', '')))
    return {
        'source': 'Breathe London (Greater London Authority), hourly sensor readings from the Breathe London API',
        'attribution': ATTRIBUTION,
        'attributionLink': ATTRIBUTION_LINK,
        'licence': OGL_URL,
        'window': window_label(start, end),
        'captureFloor': CAPTURE_FLOOR,
        'fetched': fetched,
        'note': ('Display only, never scored. Low-cost sensors, provisional values that are recalibrated '
                 'over time. Kerbside, roadside and background sensors measure different things: show the '
                 'nearest with its classification, never rank them.'),
        'sites': sites,
        'excluded': excluded,
    }


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check(data: dict, key: str | None = None) -> list[str]:
    """Every rule the file must keep. Returns the problems; empty means it passes."""
    problems = []
    if data.get('attribution') != ATTRIBUTION:
        problems.append(f'attribution is not Breathe London\'s required statement: {data.get("attribution")!r}')
    if data.get('attributionLink') != ATTRIBUTION_LINK:
        problems.append(f'attribution link is not {ATTRIBUTION_LINK}')
    if data.get('licence') != OGL_URL:
        problems.append('licence link is not the OGL v3')
    if data.get('captureFloor') != CAPTURE_FLOOR:
        problems.append(f'captureFloor {data.get("captureFloor")} is not {CAPTURE_FLOOR}')
    start = end = None
    try:
        fetched = datetime.date.fromisoformat(str(data.get('fetched')))
    except ValueError:
        problems.append(f'fetched {data.get("fetched")!r} is not a date')
    else:
        start, end = window(fetched)
        expected = window_label(start, end)
        if data.get('window') != expected:
            problems.append(f'window {data.get("window")} is not the 12 months before {fetched:%B %Y}: {expected}')
    if key and key in json.dumps(data, ensure_ascii=False):
        problems.append('the file contains the API key')
    boroughs = {code: (name, geom) for code, name, geom in london_boroughs()}
    sites = data.get('sites') or []
    codes = [s.get('code') for s in sites]
    if len(codes) != len(set(codes)):
        problems.append('duplicate site codes')
    for s in sites:
        where = f'{s.get("code")} {s.get("name")}'
        b = boroughs.get(s.get('borough'))
        if b is None:
            problems.append(f'{where}: {s.get("borough")!r} is not a London borough code')
        elif not (_is_num(s.get('lat')) and _is_num(s.get('lon'))
                  and _point_in_geometry(s['lon'], s['lat'], b[1])):
            problems.append(f'{where}: ({s.get("lat")}, {s.get("lon")}) is not inside {b[0]}')
        elif s.get('boroughName') != b[0]:
            problems.append(f'{where}: boroughName {s.get("boroughName")!r} is not {b[0]!r}')
        if s.get('classification') not in CLASSIFICATIONS:
            problems.append(f'{where}: unknown classification {s.get("classification")!r}')
        if not (s.get('no2') or s.get('pm25')):
            problems.append(f'{where}: carries neither pollutant')
        # One place per mean: a capture beyond the hours since this place began measuring
        # means hours from somewhere else were counted (a sensor moved under its code).
        possible = None
        try:
            began = datetime.datetime.fromisoformat(str(s.get('measuringSince'))).replace(tzinfo=datetime.UTC)
        except ValueError:
            problems.append(f'{where}: measuringSince {s.get("measuringSince")!r} is not a date')
        else:
            if start is not None:
                possible = max(0.0, (end - max(start, began)) / (end - start))
        for k in SPECIES:
            v = s.get(k)
            if v is None:
                continue
            if possible is not None and _is_num(v.get('capture')) and v['capture'] > possible + 0.001:
                problems.append(f'{where}: {k} capture {v["capture"]} is more than the {possible:.3f} possible '
                                f'since it began measuring here on {s.get("measuringSince")}')
            if not (_is_num(v.get('mean')) and 0 < v['mean'] < PLAUSIBLE_MAX[k]):
                problems.append(f'{where}: {k} mean {v.get("mean")} is not a plausible 12-month mean')
            if not (_is_num(v.get('capture')) and CAPTURE_FLOOR <= v['capture'] <= 1):
                problems.append(f'{where}: {k} capture {v.get("capture")} is outside {CAPTURE_FLOOR}-1')
            if not (_is_num(v.get('ratified')) and 0 <= v['ratified'] <= 1):
                problems.append(f'{where}: {k} ratified share {v.get("ratified")} is outside 0-1')
    # The per-borough floor: a count says how many sensors survived, never WHERE. Every
    # borough must hold a usable sensor, or say why not.
    for code, (name, _geom) in sorted(boroughs.items()):
        inside = [s.get('code') for s in sites if s.get('borough') == code]
        if not inside and code not in NO_SENSOR_INSIDE:
            problems.append(f'{code} {name}: no usable sensor, and none declared in NO_SENSOR_INSIDE')
        if inside and code in NO_SENSOR_INSIDE:
            problems.append(f'{code} {name}: declared in NO_SENSOR_INSIDE but {", ".join(inside)} now lies inside: remove it')
    return problems


def report(data: dict) -> None:
    sites = data['sites']
    n_no2 = sum(1 for s in sites if s['no2'])
    n_pm = sum(1 for s in sites if s['pm25'])
    w = data['window']
    print(f'{len(sites)} Breathe London sensors with a usable mean, {w["from"]} to {w["to"]}: '
          f'{n_no2} with NO2, {n_pm} with PM2.5; {len(data["excluded"])} exclusions')
    kinds = collections.Counter(s['classification'] for s in sites)
    print('  by classification: ' + ', '.join(f'{k} {n}' for k, n in sorted(kinds.items())))
    per = collections.Counter(s['borough'] for s in sites)
    names = {code: name for code, name, _g in london_boroughs()}
    fewest = sorted(names, key=lambda c: (per[c], names[c]))[:3]
    print(f'  boroughs holding a sensor: {sum(1 for c in names if per[c])} of {len(names)}; fewest: '
          + ', '.join(f'{names[c]} {per[c]}' for c in fewest))
    reasons = collections.Counter(e['reason'].split(' ')[0] if e['reason'].startswith('capture') else e['reason']
                                  for e in data['excluded'])
    print('  exclusions: ' + ', '.join(f'{r} x{n}' for r, n in reasons.most_common()))


def read_raw(fetched: str, key: str | None) -> tuple[list[dict], dict[tuple[str, str], list[dict]]]:
    """The sensor list and every live sensor's series, from the day's cache (fetching what is missing)."""
    start, end = window(datetime.date.fromisoformat(fetched))
    day = RAW / fetched
    sensors = cached(key, day / 'ListSensors.json.gz', '/ListSensors')
    live = sorted({str(s.get('SiteCode')) for s in sensors if not s.get('EndDate')})
    series = {}
    for i, code in enumerate(live, 1):
        for species in SPECIES.values():
            series[(code, species)] = cached(
                key, day / f'{code}-{species}.json.gz', '/SensorData',
                {'SiteCode': code, 'Species': species,
                 'startTime': start.strftime(STAMP), 'endTime': (end - HOUR).strftime(STAMP)})
        if key and i % 25 == 0:
            print(f'  {i} of {len(live)} sensors', flush=True)
    return sensors, series


class _Redacted:
    """A stream with the key blanked out of everything written to it. Problem lines and the report
    echo field values, so the very check that FINDS the key in a field would otherwise print it."""

    def __init__(self, stream, key: str):
        self.stream, self.key = stream, key

    def write(self, s: str) -> int:
        return self.stream.write(s.replace(self.key, '<key>'))

    def flush(self) -> None:
        self.stream.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fetch', action='store_true', help='download the last 12 months and write the file')
    mode.add_argument('--check', action='store_true', help='offline: the checked-in file keeps its rules')
    mode.add_argument('--verify', action='store_true', help='re-derive from the cached raw files and compare')
    args = ap.parse_args(argv)
    key = local_key()
    if key is None:
        return _run(args, None)
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _Redacted(out, key), _Redacted(err, key)
    try:
        return _run(args, key)
    except SystemExit as exc:  # its message would print after the streams are restored
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        raise
    except Exception:  # noqa: BLE001 - printed here, redacted, rather than by the interpreter, unredacted
        import traceback
        traceback.print_exc()
        return 1
    finally:
        sys.stdout, sys.stderr = out, err


def _run(args, key: str | None) -> int:
    if args.fetch:
        if key is None:
            print(f'FAIL: no {KEY_NAME} in the environment or in .env')
            return 1
        fetched = datetime.date.today().isoformat()
        sensors, series = read_raw(fetched, key)
        data = build(sensors, series, fetched, london_boroughs())
        api_names = {str(s.get('SiteCode')): str(s.get('Borough') or '') for s in sensors if not s.get('EndDate')}
        differ = [f'{s["code"]} (API: {api_names[s["code"]]}, boundary: {s["boroughName"]})'
                  for s in data['sites'] if api_names.get(s['code'], '').lower() != s['boroughName'].lower()]
        problems = check(data, key)
        report(data)
        if differ:
            print(f'  the API names a different borough for {len(differ)}: ' + '; '.join(differ))
        if problems:
            print('NOT WRITTEN, the fetched data breaks its rules:\n  ' + '\n  '.join(problems))
            return 1
        text = json.dumps(data, indent=1, ensure_ascii=False) + '\n'
        if key in text:
            print('NOT WRITTEN: the file would contain the API key')
            return 1
        OUT.write_text(text, encoding='utf-8')
        print(f'wrote {OUT.relative_to(REPO)}')
        return 0

    if not OUT.exists():
        print(f'FAIL: {OUT.relative_to(REPO)} is missing (it is checked in: restore it or run --fetch)')
        return 1
    data = json.loads(OUT.read_text(encoding='utf-8'))

    if args.verify:
        day = RAW / str(data.get('fetched'))
        if not (day / 'ListSensors.json.gz').exists():
            print(f'INCONCLUSIVE: the raw files are not cached under {day.relative_to(REPO)} (run --fetch)')
            return 0
        try:
            rebuilt = build(*read_raw(data['fetched'], None), fetched=data['fetched'], boroughs=london_boroughs())
        except SystemExit as exc:
            print(f'INCONCLUSIVE: {exc}')
            return 0
        except (OSError, EOFError, ValueError) as exc:  # a cached file cut short or corrupted
            print(f'INCONCLUSIVE: a cached file under {day.relative_to(REPO)} cannot be read '
                  f'({type(exc).__name__}): re-run --fetch')
            return 0
        if rebuilt != data:
            diff = [k for k in data if data.get(k) != rebuilt.get(k)]
            print(f'FAIL: {OUT.relative_to(REPO)} differs from a re-derivation in: {", ".join(diff)}')
            return 1
        print(f'ok: {OUT.relative_to(REPO)} re-derives exactly from the cached {data["fetched"]} files')
        return 0

    problems = check(data, key)
    report(data)
    if key is None:
        print(f'  (no {KEY_NAME} here, so the file was not searched for the key)')
    if problems:
        print('FAIL:\n  ' + '\n  '.join(problems))
        return 1
    print('ok: every rule holds')
    return 0


if __name__ == '__main__':
    sys.exit(main())
