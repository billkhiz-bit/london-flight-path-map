"""Cut one day of adsb.lol flight history down to the low flying near our airports.

WHY THIS EXISTS
---------------
"How often do planes pass over here?" is the question Sky Score cannot answer:
DEFRA's Lden is an energy average, and N65 (flights above 65 dB a day) is
published for Heathrow alone, as pictures. Bill's ruling, 2026-10-15: answer it
as accurately as the best available source allows, however long it takes. The
best openly licensed source of real flights is adsb.lol's daily history
(github.com/adsblol/globe_history_2026, ODbL 1.0): every aircraft the community
receivers heard, a position every few seconds, with its height, speed and type.

A day is ~3.7 GB of tar for the whole world. This script reads it ONCE, as a
stream, and keeps only what the product can use: points within REGION_KM of an
airport whose routes we draw (data/flight-procedures.json for the UK,
data/us-flight-procedures.json for the US), at or below ALT_CEILING_FT, plus
ground positions there. Measured on 2026-10-14: 77,584 aircraft read, 7,281
kept (4.9M points), an 81 MB extract against a 3.7 GB archive, in 63 s on six
workers. So the raw day can be deleted and a whole year processed a day at a
time (~30 GB of extracts).

LICENCE: ODbL. Measuring privately creates no obligation. The moment counts
derived from this are PUBLISHED they are a Derivative Database and must be
offered under ODbL, with "aircraft positions via adsb.lol (ODbL)". That is
Bill's decision (ROADMAP "How often planes fly"); until then nothing derived
from this leaves the machine.

THE ARCHIVE IS UNTRUSTED INPUT. It is read as a stream (tarfile mode 'r|'),
nothing is extracted to disk, and only members named traces/*/trace_full_*.json
are parsed, as data.

Usage (under a current Python: see adsb_fetch.py's PYTHON note):
    python -I scripts/adsb_extract.py data/adsb/raw/2026-10-14
    (writes data/adsb/extract/2026-10-14.jsonl.gz; --out to override)
"""

import argparse
import gzip
import json
import math
import sys
import tarfile
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCEDURE_FILES = (ROOT / 'data' / 'flight-procedures.json',
                   ROOT / 'data' / 'us-flight-procedures.json')

# 40 km reaches central London from Heathrow (Battersea is ~20 km, the City
# ~24 km) and every covered city-region from its airport; 10,000 ft is the
# Bay Area arrivals rule (the FAA's own "10,000 ft or lower" cut) and is well
# above where an aircraft is loud on the ground.
REGION_KM = 40.0
ALT_CEILING_FT = 10000
# A cheap first pass looks at every PREFILTER_STRIDE-th point against boxes
# widened by PREFILTER_MARGIN_KM. At a point every ~5-10 s that is a 1-2 minute
# gap, under 10 km even at cruise speed, so the margin cannot let a crossing
# flight slip between samples.
PREFILTER_STRIDE = 20
PREFILTER_MARGIN_KM = 15.0
KM_PER_DEG_LAT = 111.2


def airport_centres(paths=PROCEDURE_FILES):
    """{code: (lat, lon)} - the mean of each airport's runway thresholds."""
    out = {}
    for path in paths:
        record = json.loads(path.read_text(encoding='utf-8'))
        for code, ap in record['airports'].items():
            thr = [r['thr'] for r in ap.get('runways', {}).values() if r.get('thr')]
            if not thr:
                raise SystemExit(f'{path.name}: {code} has no runway thresholds')
            out[code] = (sum(t[0] for t in thr) / len(thr),
                         sum(t[1] for t in thr) / len(thr))
    if len(out) < 15:
        raise SystemExit(f'only {len(out)} airports read; expected the UK 15 and the US 7')
    return out


def boxes(centres, km):
    """One lat/lon box per airport, half-width km."""
    out = []
    for lat, lon in centres.values():
        dlat = km / KM_PER_DEG_LAT
        dlon = km / (KM_PER_DEG_LAT * math.cos(math.radians(lat)))
        out.append((lat - dlat, lat + dlat, lon - dlon, lon + dlon))
    return out


def km_between(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 12742.0 * math.asin(math.sqrt(a))


def in_any(lat, lon, bxs):
    for la0, la1, lo0, lo1 in bxs:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return True
    return False


# Worker state, set once per process (the airport tables are small).
_CENTRES = _NEAR_BOXES = _WIDE_BOXES = None


def _init(centres):
    global _CENTRES, _NEAR_BOXES, _WIDE_BOXES
    _CENTRES = list(centres.items())
    _NEAR_BOXES = boxes(centres, REGION_KM)
    _WIDE_BOXES = boxes(centres, REGION_KM + PREFILTER_MARGIN_KM)


def keep_point(p, near_boxes, centres):
    """True when a trace point is low and within REGION_KM of an airport."""
    lat, lon, alt = p[1], p[2], p[3]
    if lat is None or lon is None:
        return False
    if alt != 'ground' and (not isinstance(alt, (int, float)) or alt > ALT_CEILING_FT):
        return False
    if not in_any(lat, lon, near_boxes):
        return False
    return any(km_between(lat, lon, c[0], c[1]) <= REGION_KM for _, c in centres)


def filter_trace(doc, near_boxes, wide_boxes, centres):
    """The kept points of one trace document, or None if it never comes near.

    Each kept point is [epoch_s, lat, lon, alt_baro_ft | 'ground', alt_geom_ft,
    ground_speed_kt, track_deg, baro_rate_fpm, flags, callsign]. The callsign
    is carried forward from the last point that reported one, because readsb
    attaches the full message to a point only now and then.
    """
    trace = doc.get('trace') or []
    if not any(p[1] is not None and p[2] is not None and in_any(p[1], p[2], wide_boxes)
               for p in trace[::PREFILTER_STRIDE]):
        # The stride can skip the last point of a short trace; test it too.
        if not trace or not in_any(trace[-1][1] or 0, trace[-1][2] or 0, wide_boxes):
            return None
    base = float(doc.get('timestamp') or 0)
    kept, callsign = [], None
    for p in trace:
        ext = p[8] if len(p) > 8 else None
        if isinstance(ext, dict) and ext.get('flight'):
            callsign = ext['flight'].strip() or callsign
        if keep_point(p, near_boxes, centres):
            kept.append([round(base + p[0], 1), p[1], p[2], p[3],
                         p[10] if len(p) > 10 else None, p[4], p[5],
                         p[7] if len(p) > 7 else None, p[6], callsign])
    if not kept:
        return None
    return {'icao': doc.get('icao'), 'r': doc.get('r'), 't': doc.get('t'),
            'desc': doc.get('desc'), 'pts': kept}


MAX_TRACE_BYTES = 64 * 1024 * 1024  # one aircraft's day; real traces are kilobytes


def _work(raw):
    # The archive is untrusted: a corrupt gzip member (BadGzipFile is an OSError,
    # a truncated one EOFError) counts as one bad trace rather than ending the day,
    # and decompression is capped so a gzip bomb cannot exhaust the machine.
    if raw is None:  # a member members() refused to read: larger than any real trace
        return 'bad', None
    try:
        if raw[:2] == b'\x1f\x8b':
            z = zlib.decompressobj(16 + zlib.MAX_WBITS)
            data = z.decompress(raw, MAX_TRACE_BYTES)
            if z.unconsumed_tail:
                return 'bad', None
        else:
            data = raw
        doc = json.loads(data)
    except (ValueError, OSError, EOFError, zlib.error):
        return 'bad', None
    return 'ok', filter_trace(doc, _NEAR_BOXES, _WIDE_BOXES, _CENTRES)


def _work_batch(raws):
    return [_work(r) for r in raws]


def batched_results(pool, blobs, batch=256, in_flight=24):
    """Yield (status, record) for every blob, holding at most `in_flight`
    batches in memory. Executor.map would read the WHOLE archive first: it
    submits every item before returning, and a day is ~3.7 GB of blobs."""
    pending, chunk = [], []
    for blob in blobs:
        chunk.append(blob)
        if len(chunk) == batch:
            pending.append(pool.submit(_work_batch, chunk))
            chunk = []
            if len(pending) >= in_flight:
                yield from pending.pop(0).result()
    if chunk:
        pending.append(pool.submit(_work_batch, chunk))
    for fut in pending:
        yield from fut.result()


class ChainedParts:
    """A read-only file object over split archive parts (.tar.aa, .tar.ab ...)."""

    def __init__(self, paths):
        self._paths = list(paths)
        self._fh = None
        self._next()

    def _next(self):
        if self._fh:
            self._fh.close()
        self._fh = open(self._paths.pop(0), 'rb') if self._paths else None

    def read(self, n=-1):
        chunks = []
        while self._fh and (n < 0 or n > 0):
            chunk = self._fh.read(n if n > 0 else -1)
            if not chunk:
                self._next()
                continue
            chunks.append(chunk)
            if n > 0:
                n -= len(chunk)
        return b''.join(chunks)

    def close(self):
        if self._fh:
            self._fh.close()


def members(parts):
    """Yield the raw bytes of every trace member, streaming."""
    stream = ChainedParts(parts)
    try:
        with tarfile.open(fileobj=stream, mode='r|') as tar:
            for m in tar:
                name = m.name.replace('\\', '/')
                if m.isfile() and '/traces/' in f'/{name}' and '/trace_full_' in name:
                    if m.size > MAX_TRACE_BYTES:
                        # Never read, so never held or pickled to a worker: the cap in _work covers what a gzip
                        # member EXPANDS to, and a plain member declaring gigabytes had none (audit 2026-10-22).
                        yield None
                        continue
                    yield tar.extractfile(m).read()
    finally:
        stream.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('day_dir', type=Path, help='directory holding one day\'s *.tar.?? parts')
    ap.add_argument('--out', type=Path, help='default data/adsb/extract/<day>.jsonl.gz')
    ap.add_argument('--workers', type=int, default=6)
    args = ap.parse_args()

    parts = sorted(args.day_dir.glob('*.tar.a?')) or sorted(args.day_dir.glob('*.tar'))
    if not parts:
        raise SystemExit(f'no archive parts in {args.day_dir}')
    out = args.out or ROOT / 'data' / 'adsb' / 'extract' / f'{args.day_dir.name}.jsonl.gz'
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + '.partial')

    centres = airport_centres()
    t0 = time.time()
    seen = kept = bad = points = 0
    with gzip.open(tmp, 'wt', encoding='utf-8') as fh, \
            ProcessPoolExecutor(args.workers, initializer=_init, initargs=(centres,)) as pool:
        for status, rec in batched_results(pool, members(parts)):
            seen += 1
            if status == 'bad':
                bad += 1
            elif rec:
                kept += 1
                points += len(rec['pts'])
                fh.write(json.dumps(rec, separators=(',', ':')) + '\n')
            if seen % 50000 == 0:
                print(f'  {seen:,} traces read, {kept:,} kept ({time.time() - t0:.0f} s)', flush=True)
    # A day of the whole world is ~100k aircraft; a short read means a broken
    # or truncated archive, and a file that looks complete must not be left.
    if seen < 20000:
        tmp.unlink()
        raise SystemExit(f'only {seen:,} traces in {args.day_dir}: archive incomplete?')
    tmp.replace(out)
    print(f'{args.day_dir.name}: {seen:,} traces read, {bad} unreadable, {kept:,} kept '
          f'({points:,} points) -> {out.relative_to(ROOT)} in {time.time() - t0:.0f} s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
