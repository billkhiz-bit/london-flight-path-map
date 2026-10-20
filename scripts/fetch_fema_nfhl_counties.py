"""Fetch FEMA's flood hazard zones over the Bay Area as FEMA's own county-wide NFHL downloads.

The same output as scripts/fetch_fema_flood.py (nfhl-bayarea.esrijson.gz + manifest.json, read unchanged by
build_bayarea_flood.py), by FEMA's other route. The NFHL query service that fetcher uses stopped answering
GitHub's runners on 2026-10-18 (run 5 reset at the first request; run 6 hung on the features until the
30-minute limit) and reset both MapServer paths within seconds on 2026-10-19 (run 39282176347).

THE ADDRESS is FEMA's, read from its own guide (FEMA_Hazard_Products_Direct_Download.pdf, Sep 2017, p.2,
served to run 39327658467): `https://msc.fema.gov/portal/downloadProduct?productID=` + a product id, and a
COUNTY-WIDE NFHL database is `NFHL_<5-digit county FIPS>C` (the guide's example: NFHL_51013C).

THE COUNTIES are derived, never typed: the county names of the 50 scored places (data/us-bayarea-places.json)
mapped to FIPS by the county rows of data/us-bayarea-trend.json (FHFA's codes). `--check` proves, with the
Census block frame on disk, that every resident block of the 50 cities lies in one of them, so no resident
can fall outside every download.

THE GUARDS:
- FEMA blocks on and off (run 39327658467 was reset on one request and answered the next), so a download is
  retried with a growing pause, and a page in place of the product is asked for again once. A county still
  failing, for any reason, is recorded in failed.json (rewritten after each failure) with FEMA's reply kept,
  the other counties are still tried until DEADLINE_S, and NOTHING is written for the reader: a partial file
  would read as "no flood map" for that county's cities.
- The reply must be a zip (the portal can answer a missing product with a page, not an error status); its
  size and sha256 are recorded and its members listed, and it is extracted only after every member name is
  checked (no absolute path, no "..") and the unpacked size capped: these are untrusted archives.
- S_FLD_HAZ_AR is read with GDAL's ogr2ogr (the workflow installs gdal-bin), which reads a shapefile and a
  file geodatabase alike, since the guide does not say which a county download holds; it is transformed to
  WGS84 with the fields fetch_fema_flood.py asks for. A county with no polygons fails: empty is not "no flood".

Usage: python -I scripts/fetch_fema_nfhl_counties.py --out <dir> [--raw <dir>]   (on the US runner)
       python scripts/fetch_fema_nfhl_counties.py --check   every resident block is in a fetched county
"""

import argparse
import datetime as dt
import gzip
import hashlib
import http.client
import importlib.util
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parent.parent
PLACES = REPO / 'data' / 'us-bayarea-places.json'
TREND = REPO / 'data' / 'us-bayarea-trend.json'
DOWNLOAD = 'https://msc.fema.gov/portal/downloadProduct?productID='
LAYER = 'S_FLD_HAZ_AR'
TRIES = 6
PAUSE_S = 15  # before the first retry, doubled each time up to PAUSE_MAX_S: FEMA's blocks come and go
PAUSE_MAX_S = 120
TIMEOUT_S = 120  # a SILENCE this long is a hang (FEMA hung run 6 on 2026-10-18); a download streams throughout
DEADLINE_S = 40 * 60  # no county is started after this, so the run ends inside the workflow's 55 minutes
BETWEEN_S = 5  # between counties: a shared public service
NOT_ZIP_TRIES = 2
NOT_ZIP_PAUSE_S = 60
KEEP_REPLY_BYTES = 500_000  # of a reply that was not the product, kept for reading (as text, never opened)
NOT_FOUND = 'the product you were looking for could not be found'  # FEMA's own words, run 39430132007
# FEMA's portal fills its search dropdowns from these (getAjaxData() in /portal/advanceSearch, as saved by
# run 39327658467): ?getCounty=<state> and ?getCommunity=<county value>&state=<state>, each [{value, label}].
PORTAL_SEARCH = 'https://msc.fema.gov/portal/advanceSearch'
PRODUCT_VALUE = re.compile(r'^(\d{6}|\d{5}C)$')  # a community CID, or a county FIPS + C (the guide's two forms)
# The page's search posts its whole form (jQuery("form").serialize() + "&method=search"); these are its fields.
SEARCH_FORM = {'selstate': '', 'selcounty': '', 'selcommunity': '', 'searchedCid': '', 'txtjurisdictionname': '',
               'jurisdictionkey': '', 'jurisdictionvalue': '', 'txtproductid': '', 'txtstartdate': '',
               'txtenddate': '', 'searchedDateStart': '', 'searchedDateEnd': '', 'method': 'search'}
# ...and a listed EFFECTIVE.NFHL_COUNTY_DATA product downloads where the page sends it: with the STATE subtype, as
# the page builds it for county data too (FEMA's own code, run 39327658467's copy; kept as found).
SEARCH_DOWNLOAD = ('https://msc.fema.gov/portal/downloadProduct?productTypeID=NFHL&productSubTypeID=NFHL_STATE_DATA'
                   '&productID=')
MAX_BYTES = 2_000_000_000  # one download; a county's NFHL is tens of MB
MAX_UNPACKED = 8_000_000_000  # one archive's members together


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_query_route = _load('fetch_fema_flood')
FIELDS, UA = _query_route.FIELDS, _query_route.UA  # one field list and one User-Agent for both routes


class NetworkError(Exception):
    """No complete answer after TRIES attempts."""


class NotAZip(Exception):
    """FEMA answered with a page, not the product. Run 39416950759 (2026-10-20): Alameda's NFHL_06001C came
    whole, then San Francisco's NFHL_06075C was the portal's page template, though the city-county's FIRM has
    been effective since 2021: a missing product or a throttle, which the kept reply should tell apart."""

    def __init__(self, message, path=None, missing=False):
        super().__init__(message)
        self.path, self.missing = path, missing


class PortalError(Exception):
    """FEMA's portal search did not answer with the list its own page expects."""


def counties(places_doc, trend_doc):
    """[(county name, FIPS)] for the counties the scored places name, FIPS from the trend file's rows."""
    fips = {r['county']: r['fips'] for r in trend_doc['counties']}
    names = sorted({p['county'] for p in places_doc['places'] if p['kind'] in ('city', 'town')})
    missing = [n for n in names if n not in fips]
    if missing:
        raise SystemExit(f'no FIPS for {missing} in {TREND.name}: add the county to build_bayarea_trend.py')
    out = [(n, fips[n]) for n in names]
    bad = [f for _, f in out if not (len(f) == 5 and f.isdigit() and f.startswith('06'))]
    if bad:
        raise SystemExit(f'{TREND.name}: {bad} are not California county FIPS codes')
    return out


def _disposition_name(header):
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', header or '')
    return m.group(1).strip() if m else None


def download(url, dest, opener=urllib.request.urlopen, sleep=time.sleep):
    """Stream `url` to `dest`, retrying a reset or a server error; (bytes, sha256, the file name FEMA gives).
    A 4xx other than 429 is FEMA's answer, not a block, and fails at once."""
    for attempt in range(TRIES):
        try:
            with opener(urllib.request.Request(url, headers=UA), timeout=TIMEOUT_S) as r:
                name = _disposition_name(r.headers.get('Content-Disposition'))
                digest, size = hashlib.sha256(), 0
                with open(dest, 'wb') as fh:
                    while chunk := r.read(1 << 20):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise SystemExit(f'{url}: over {MAX_BYTES:,} bytes; not a county NFHL')
                        digest.update(chunk)
                        fh.write(chunk)
            return size, digest.hexdigest(), name
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 429:
                raise SystemExit(f'{url}: FEMA answered {exc.code} {exc.reason}') from exc
            err = exc
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:  # resets, TLS, timeouts
            err = exc
        if attempt == TRIES - 1:
            raise NetworkError(f'{url}: {err} after {TRIES} tries')
        wait = min(PAUSE_S * 2 ** attempt, PAUSE_MAX_S)
        print(f'  {err}; try {attempt + 2} of {TRIES} in {wait} s', flush=True)
        sleep(wait)
    raise NetworkError(f'{url}: unreachable')  # pragma: no cover


def require_zip(path):
    """Raise NotAZip, quoting the reply's page title or its start, unless `path` is a zip. Its `missing` is
    true when the page is FEMA's "could not be found" (run 39430132007: NFHL_06075C, asked twice a minute
    apart while the other three counties downloaded), which is an answer, not a throttle."""
    with open(path, 'rb') as fh:
        head = fh.read(KEEP_REPLY_BYTES)
    if not head.startswith(b'PK\x03\x04'):
        text = head.decode('utf-8', 'replace')
        title = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
        said = ' '.join((title.group(1) if title else text[:200]).split())
        missing = NOT_FOUND in ' '.join(text.split())
        raise NotAZip(f'{path.name}: FEMA sent something that is not a zip ({path.stat().st_size:,} bytes): {said!r}'
                      + (f' ("{NOT_FOUND}")' if missing else ''), path=path, missing=missing)


def safe_extract(zip_path, dest):
    """Extract an untrusted zip after checking every member name and the unpacked size; the member names."""
    with zipfile.ZipFile(zip_path) as z:
        infos = z.infolist()
        for i in infos:
            p = PurePosixPath(i.filename.replace('\\', '/'))
            if p.is_absolute() or '..' in p.parts or (p.parts and ':' in p.parts[0]):
                raise SystemExit(f'{zip_path.name}: refused, a member named {i.filename!r}')
        total = sum(i.file_size for i in infos)
        if total > MAX_UNPACKED:
            raise SystemExit(f'{zip_path.name}: {total:,} bytes unpacked, over {MAX_UNPACKED:,}')
        z.extractall(dest)
    return [i.filename for i in infos]


def find_source(root, depth=1):
    """What GDAL opens for S_FLD_HAZ_AR under `root`: its shapefile, or the file geodatabase holding it.
    A download holding only an inner zip is opened one level down, once."""
    found = [p for p in root.rglob('*') if (p.is_file() and p.name.upper() == f'{LAYER}.SHP')
             or (p.is_dir() and p.suffix.lower() == '.gdb')]
    if len(found) == 1:
        return found[0]
    if found:
        raise SystemExit(f'{root.name}: {len(found)} candidate sources of {LAYER}: {[p.name for p in found]}')
    inner = list(root.rglob('*.zip'))
    if depth and len(inner) == 1:
        sub = inner[0].with_name(inner[0].stem + '-unzipped')
        safe_extract(inner[0], sub)
        return find_source(sub, depth - 1)
    raise SystemExit(f'{root.name}: no {LAYER}.shp and no .gdb (inner zips: {[p.name for p in inner]})')


def read_layer(src, workdir, run=subprocess.run):
    """(S_FLD_HAZ_AR as WGS84 GeoJSON, what ogrinfo says of the source layer), by GDAL's own tools."""
    info = run(['ogrinfo', '-ro', '-so', str(src), LAYER], capture_output=True, text=True, check=True).stdout
    out = workdir / f'{LAYER}.geojson'
    run(['ogr2ogr', '-f', 'GeoJSON', '-t_srs', 'EPSG:4326', '-lco', 'COORDINATE_PRECISION=6',
         '-select', FIELDS, str(out), str(src), LAYER], check=True)
    return json.loads(out.read_text(encoding='utf-8')), info


def esri_features(geojson):
    """GeoJSON polygons as fetch_fema_flood.py's Esri JSON features, and how many had no geometry. Every ring
    of a polygon, or of each part of a multipolygon, goes in one list: the reader tests rings even-odd, which
    needs no ring orientation and reads a multipolygon's parts (which do not overlap) as their union."""
    out, empty = [], 0
    for f in geojson.get('features', []):
        g = f.get('geometry')
        if not g:
            empty += 1
            continue
        if g['type'] == 'Polygon':
            rings = g['coordinates']
        elif g['type'] == 'MultiPolygon':
            rings = [ring for part in g['coordinates'] for ring in part]
        else:
            raise SystemExit(f'{LAYER}: a {g["type"]} among the flood zones; polygons only')
        out.append({'attributes': f.get('properties') or {}, 'geometry': {'rings': rings}})
    return out, empty


def fetch_county(name, fips, raw, get=None, read=None, portal=None):
    """(Esri JSON features, the manifest's record) for one county: its county-wide NFHL download, or, where
    FEMA has none, each of its communities' (community_products())."""
    get, read = get or download, read or read_layer  # looked up per call, so a test can stub them
    portal = portal or portal_json
    pid = f'NFHL_{fips}C'
    url = DOWNLOAD + pid
    print(f'{name} ({fips}): {url}', flush=True)
    try:
        feats, record = fetch_product(f'{name} ({fips})', pid, raw, get, read)
    except NotAZip as exc:
        if not exc.missing:
            raise
        # No county-wide database: San Francisco, a consolidated city-county (run 39430132007). FEMA's guide
        # names the other form, NFHL_<community CID>; which communities a county has is the portal's answer.
        print(f'  {pid}: "{NOT_FOUND}"; asking the portal for {name} County\'s community products', flush=True)
        products, asked = community_products(fips, name, portal)
        feats, records = [], []
        for label, cpid, curl in products:
            print(f'  {label}: {curl}', flush=True)
            got, rec = fetch_product(f'{name} ({fips}) {label}', cpid, raw, get, read, curl)
            feats.extend(got)
            records.append({**rec, 'community': label})
        return feats, {'county': name, 'fips': fips, 'product_id': pid, 'county_wide': NOT_FOUND,
                       'portal': asked, 'products': records, 'features': len(feats)}
    return feats, {'county': name, 'fips': fips, **record}


def fetch_product(label, pid, raw, get, read, url=None):
    """(Esri JSON features, the record) for one NFHL product, county-wide or a community's, at the guide's
    address or at `url`, the one FEMA's portal page builds for a product its search lists."""
    url = url or DOWNLOAD + pid
    zpath = raw / f'{re.sub(r"[^A-Za-z0-9._-]", "_", pid)}.zip'
    for attempt in range(NOT_ZIP_TRIES):  # a page may be a throttle: asked again once, after a pause
        size, sha, served_as = get(url, zpath)
        try:
            require_zip(zpath)
            break
        except NotAZip as exc:
            if exc.missing or attempt == NOT_ZIP_TRIES - 1:
                raise
            print(f'  {exc}; asking again in {NOT_ZIP_PAUSE_S} s', flush=True)
            time.sleep(NOT_ZIP_PAUSE_S)
    members = safe_extract(zpath, raw / pid)
    src = find_source(raw / pid)
    geojson, info = read(src, raw / pid)
    feats, empty = esri_features(geojson)
    if not feats:
        raise SystemExit(f'{label}: {pid} holds no flood polygons: a failed fetch, not "no flood"')
    dfirms = {}
    for f in feats:
        d = f['attributes'].get('DFIRM_ID')
        dfirms[d] = dfirms.get(d, 0) + 1
    print(f'  {size / 1e6:.1f} MB, {len(members)} members, {len(feats):,} polygons from {src.name}', flush=True)
    return feats, {
        'product_id': pid, 'url': url, 'served_as': served_as, 'bytes': size,
        'sha256': sha, 'members': members[:200], 'members_total': len(members),
        'source': str(src.relative_to(raw / pid)), 'source_layer_info': info[:4000],
        'features': len(feats), 'without_geometry': empty, 'dfirm_ids': dict(sorted(dfirms.items(), key=lambda kv: str(kv[0]))),
    }


def portal_json(params, opener=urllib.request.urlopen, form=None):
    """FEMA's portal as its own page asks it: a dropdown list, [{'value', 'label'}], by GET `params`; or, with
    `form`, the product search (a POST, like the page's jQuery.ajax), a dict of product groups."""
    url = PORTAL_SEARCH + ('?' + urllib.parse.urlencode(params) if params else '')
    body = urllib.parse.urlencode(form).encode('ascii') if form is not None else None
    headers = {**UA, 'Content-Type': 'application/x-www-form-urlencoded'} if body else UA
    try:
        with opener(urllib.request.Request(url, data=body, headers=headers), timeout=120) as r:
            doc = json.loads(r.read().decode('utf-8'))
    except (urllib.error.URLError, OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        raise PortalError(f'{url}: {exc}') from exc
    if form is not None:
        if not isinstance(doc, dict):
            raise PortalError(f'{url} (search): not the product groups the portal page reads: {str(doc)[:200]}')
        return doc
    if not isinstance(doc, list) or not all(isinstance(d, dict) and 'value' in d and 'label' in d for d in doc):
        raise PortalError(f'{url}: not the [{{value, label}}] list the portal page reads: {str(doc)[:200]}')
    return doc


def community_products(fips, name, portal=None):
    """([(community label, product name, download URL)], what the portal said) for a county whose plain
    NFHL_<FIPS>C FEMA says "could not be found".

    The county is matched by its FIPS in the portal's value, else by its NAME in the label; anything else (none,
    or two) fails rather than taking a neighbour's maps. Each community whose value is a CID or FIPS+C (the
    guide's two forms) is searched the way the portal page searches, and every EFFECTIVE.NFHL_COUNTY_DATA product
    it lists is taken by its listed name (run 39436786877: the portal lists San Francisco as one jurisdiction,
    06075C, whose plain NFHL id FEMA cannot find)."""
    portal = portal or portal_json
    counties = portal({'getCounty': fips[:2]})
    match = [c for c in counties if fips in str(c['value'])] or [
        c for c in counties if re.search(rf'\b{re.escape(name)}\b', str(c['label']), re.I)]
    if len(match) != 1:
        raise PortalError(f'{name} ({fips}): {len(match)} portal counties match, of {counties[:60]}')
    communities = portal({'getCommunity': match[0]['value'], 'state': fips[:2]})
    asked = {'county': match[0], 'communities': communities, 'searches': {}}
    products = []
    for c in communities:
        value = str(c['value'])
        if not PRODUCT_VALUE.match(value):
            continue
        # The page's own search for this jurisdiction (setSearchCriteria(): searchedCid = the community chosen).
        found = portal(None, form={**SEARCH_FORM, 'selstate': fips[:2], 'selcounty': match[0]['value'],
                                   'selcommunity': value, 'searchedCid': value})
        effective = found.get('EFFECTIVE') or {}
        listed = (effective.get('NFHL_COUNTY_DATA') if isinstance(effective, dict) else None) or []
        asked['searches'][value] = {
            'effective_groups': sorted(effective) if isinstance(effective, dict) else str(effective)[:200],
            'nfhl_county_data': listed[:20]}
        for item in listed:
            pname = str((item or {}).get('product_NAME') or '')
            if re.fullmatch(r'[A-Za-z0-9._-]{3,80}', pname):
                products.append((str(c['label']).strip(), pname, SEARCH_DOWNLOAD + urllib.parse.quote(pname)))
    if not products:
        raise PortalError(f"{name} ({fips}): the portal's search lists no NFHL county data: {asked}"[:1500])
    return sorted(set(products)), asked


def keep_failure(name, fips, exc, raw, out):
    """The manifest's record of a county that failed, with FEMA's reply (when there was one) kept under
    out/diagnostics/ as .txt: untrusted data to read, not a page to open."""
    pid = f'NFHL_{fips}C'
    note = {'county': name, 'fips': fips, 'product_id': pid, 'url': DOWNLOAD + pid, 'error': str(exc)[:500]}
    reply = getattr(exc, 'path', None) or raw / f'{pid}.zip'  # a community product's reply, in the fallback
    if isinstance(exc, NotAZip) and reply.exists():
        (out / 'diagnostics').mkdir(exist_ok=True)
        with open(reply, 'rb') as fh:
            (out / 'diagnostics' / f'{reply.stem}.reply.txt').write_bytes(fh.read(KEEP_REPLY_BYTES))
        note['reply_kept'] = f'diagnostics/{reply.stem}.reply.txt'
    return note


def check(want):
    """Every resident block of the 50 cities lies in a county the fetch downloads (needs the Census frame)."""
    blocks = _load('bayarea_blocks')
    fetched = {f for _, f in want}
    if not blocks.PL_RAW.exists():
        print(f'INCONCLUSIVE: {blocks.PL_RAW.name} is not on disk (bayarea_blocks.py --fetch); '
              f'would fetch {sorted(fetched)}')
        return 0
    places = {p['geoid'] for p in blocks.cities()}
    residents = {}
    for block, place, pop, _, _ in blocks.pl_blocks():
        if place in places and pop > 0:
            residents[block[:5]] = residents.get(block[:5], 0) + pop
    outside = {c: n for c, n in residents.items() if c not in fetched}
    for c in sorted(fetched):
        print(f'  {c}: {residents.get(c, 0):,} residents of the 50 cities')
    if outside:
        print(f'RESULT: FAIL: residents in counties no download covers: {outside}')
        return 1
    print(f'RESULT: PASS ({len(fetched)} counties hold all {sum(residents.values()):,} residents)')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=Path, help='where the Esri JSON and manifest go (the artifact)')
    ap.add_argument('--raw', type=Path, default=Path('fema-raw'), help='downloads, unpacked (not uploaded)')
    ap.add_argument('--check', action='store_true', help='every resident block is in a fetched county')
    a = ap.parse_args()
    want = counties(json.loads(PLACES.read_text(encoding='utf-8')), json.loads(TREND.read_text(encoding='utf-8')))
    if a.check:
        return check(want)
    if not a.out:
        ap.error('--out is required unless --check')
    a.raw.mkdir(parents=True, exist_ok=True)
    a.out.mkdir(parents=True, exist_ok=True)
    feats, products, failed = [], [], []
    started = time.monotonic()

    def report():  # rewritten after EVERY failure, so a run killed later still leaves what went wrong
        doc = {'failed': failed, 'fetched': products, 'utc': dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}
        (a.out / 'failed.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')

    for name, fips in want:
        if time.monotonic() - started > DEADLINE_S:
            failed.append({'county': name, 'fips': fips, 'error': f'not tried: {DEADLINE_S // 60} minutes gone'})
            report()
            continue
        try:
            got, record = fetch_county(name, fips, a.raw)
        except (NotAZip, NetworkError, PortalError, SystemExit, zipfile.BadZipFile,
                subprocess.CalledProcessError) as exc:
            # Any county's failure: every county is still tried, so one run says which are missing; then
            # nothing is written that build_bayarea_flood.py could read, since a missing county would read as
            # residents in no zone. (A 4xx, a broken zip or a GDAL error stopped the whole run before.)
            failed.append(keep_failure(name, fips, exc, a.raw, a.out))
            report()
            print(f'  FAILED: {exc}', flush=True)
            continue
        finally:
            time.sleep(BETWEEN_S)
        feats.extend(got)
        products.append(record)
    if failed:
        report()  # once more, with the counties fetched after the last failure
        print(f'{len(failed)} of {len(want)} counties failed ({", ".join(f["county"] for f in failed)}); '
              f'nothing written for the reader: see failed.json and diagnostics/')
        return 1
    doc = {'format': 'esrijson', 'spatialReference': {'wkid': 4326}, 'features': feats}
    blob = gzip.compress(json.dumps(doc, separators=(',', ':')).encode('utf-8'), mtime=0)
    (a.out / 'nfhl-bayarea.esrijson.gz').write_bytes(blob)
    zones = sorted({f['attributes'].get('FLD_ZONE') for f in feats} - {None})
    manifest = {
        'source': 'FEMA National Flood Hazard Layer (public domain, US government work)', 'format': 'esrijson',
        'route': 'MSC county-wide NFHL downloads (scripts/fetch_fema_nfhl_counties.py)', 'layer_name': LAYER,
        'fields': FIELDS, 'counties_from': [str(PLACES.relative_to(REPO)), str(TREND.relative_to(REPO))],
        'products': products, 'features': len(feats), 'zones': zones,
        # the query route's ledgers, empty here: a download is whole, so nothing is simplified or refused
        'generalised_deg': {}, 'refused': {}, 'refused_outside_cities': {},
        'fetched_utc': dt.datetime.now(dt.UTC).isoformat(timespec='seconds'),
        'sha256_gz': hashlib.sha256(blob).hexdigest(),
    }
    (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(f'wrote {len(feats):,} features from {len(products)} counties ({len(blob) / 1e6:.1f} MB gzipped), '
          f'zones {zones}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
