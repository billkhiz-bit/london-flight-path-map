"""Planes overhead per postcode, as static files for the front page's answer: one file per postcode district.

WHY THIS EXISTS (2026-10-26)
----------------------------
The last step before "how often planes pass" can be shown (ROADMAP "IN PROGRESS: how often planes fly"). Bill's
rulings: told by the way each airport flies, westerly, easterly and mixed days apart (option A, 25 Oct: Kew reads
~310 on a west day and ~4 on an east one, and an average of the two is true on no day); served as STATIC files on
the site, not through /v1/score; shown first in the front page's answer; site-only for now, with an ODbL
download beside /open-data/ to follow after a few weeks live (26 Oct).

It reads data/adsb/postcode-averages.npz (scripts/adsb_postcode_averages.py), which holds ONLY the airports whose
tracking passed coverage_verdict() in every month checked, so no other airport can reach a file: the copy rule
"never say how often planes pass except for airports that pass coverage_verdict()" is held by construction, and
by a test that compares airports.json with the averages' own list.

WHAT A POSTCODE IS TOLD, AND WHAT IT IS NOT
- Per airport, three figures a day: on its westerly, easterly and mixed days (CLASSES' order), CAP 1498
  overflights at 48.5 degrees under 7,000 ft, rounded half up; under 0.5 a day reads "<1", and only a measured
  zero reads 0. An airport is listed for a postcode only when what the postcode is SHOWN reaches 1 a day on
  some kind of day (reaches_one(); a range's top counts).
- ON A CONE'S EDGE, A RANGE (Bill, 2026-10-26): near a runway the cone is ~100 m wide and a postcode on its edge
  reads all-or-nothing (Hounslow TW3 3QL: 339 a day in the next cell, 7 in its own). Where the postcode's cell and
  the eight around it differ by the rule in edge(), the figure is [least, most] within +-100 m.
- `none`: postcodes MEASURED under every airport, none reaching 1 a day on any kind of day. A postcode in no list
  was not measured (no grid reference, or outside the covered councils): the page then says nothing at all.
- `approx`: postcodes whose ONS position is imputed or a sector mean (NSPL gridind 5, 6): they can sit hundreds of
  metres out, and the page says so beside the figure.
- `other`: postcodes where flying we cannot count (airfields that are not among the ten, helicopters, transits, the
  airports that failed the check) is a large part of what passes over: a few from the ten is not a quiet sky
  (Biggin Hill, TN16 3GH). Only the flag is published, never that traffic's figure: it is unchecked.

OUTPUT
  data/planes/<DISTRICT>.json   gitignored, built from a gitignored file; uploaded by `planes-deploy`
  data/planes/airports.json     the airports, their share of days of each kind, the months, the definition, credits
  data/planes-manifest.json     TRACKED: each file's size and MD5 (S3's ETag for a one-part upload), so what is
                                deployed can be checked against what was built without downloading it

    python -I scripts/build_planes_overhead.py --write
    python -I scripts/build_planes_overhead.py --check     # the files on disk == what --write would write
    python -I scripts/build_planes_overhead.py --at "TW9 3PZ"
"""

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
AVERAGES = ROOT / 'data' / 'adsb' / 'postcode-averages.npz'
OUT_DIR = ROOT / 'data' / 'planes'
MANIFEST = ROOT / 'data' / 'planes-manifest.json'


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pa = _load('adsb_postcode_averages')
ao = _load('adsb_overflights')

ANGLE = 48.5  # CAP 1498's headline threshold; 60 degrees stays in the averages file, unpublished
# What every answer says "overhead" means, DERIVED from the thresholds the counts used (2026-10-27 review: it typed
# 48.5 and 7,000 beside the constants). How it works states the same figures, held by its test.
DEFINITION = (f'Overhead means more than halfway up the sky ({ANGLE:g} degrees or more) and below '
              f'{ao.CEILING_FT:,} ft, the CAA\'s definition of an overflight (CAP 1498).')
SHOWN_FROM = 0.5  # a day's average that rounds to 1: below it on every kind of day, an airport is not listed
COARSE_GRIDIND = (5, 6)  # NSPL: imputed by ONS, or the postcode sector's mean
# SET FROM THE RECOUNT ON THE GROUND (2026-10-26), by the postcodes each rule changes (scratch measure_rules.py):
# a range at gap 10 / ratio 2 on 17,103 postcodes, 4.0% of the 431,678 with a figure (London 6.4%), all on approach
# edges; gap 5 adds ~4,000 more, gap 20 drops ~3,400 real edges (B23 5BH: 1 to 121 a day from Birmingham).
EDGE_MIN_GAP = 10.0  # edge(): the most within 100 m at least this many a day above the least...
EDGE_MIN_RATIO = 2.0  # ...and at least this many times it
# The flag on 34,239 postcodes, mostly round the airports that failed the check (Liverpool, Newcastle, Teesside,
# Cardiff, Norwich) and small airfields; Biggin Hill TN16 3GH (19 of 24 a day uncounted) flagged, Kew (1) not.
# At 2 a day it would flag 77,785, quiet places among them (3 planes a day in all is a quiet sky).
OTHER_MIN = 5.0  # other_traffic(): uncounted flying a day at least this...
OTHER_SHARE = 0.5  # ...and at least this share of everything over the cell


def shown(v):
    """A day's average as the page shows it: 0 only when measured zero, '<1' under 0.5, else rounded half up
    (never Python's round(), which rounds a tie to even: JavaScript would show 3 where we wrote 2)."""
    if v == 0:
        return 0
    if v < SHOWN_FROM:
        return '<1'
    return int(math.floor(v + 0.5))


def edge(mean, lo, hi):
    """True when one figure would be a coin toss: the cells within 100 m differ widely, so the page gives
    [least, most]. Both conditions, so a quiet place (1 against 3) and a busy one (300 against 320) keep one figure."""
    return hi - lo >= EDGE_MIN_GAP and hi >= EDGE_MIN_RATIO * lo


def other_traffic(published_total, everything):
    """True when flying we cannot count is a large part of what passes over the cell. `everything` is the
    averages' unpublishable context: it decides a flag, and is never written itself."""
    uncounted = everything - published_total
    return uncounted >= OTHER_MIN and uncounted >= OTHER_SHARE * everything


def figures(mean, lo, hi):
    """One airport's three figures (CLASSES' order) for one postcode: shown() values, a [least, most] pair on an
    edge. NaN (no day of that kind) is null: not measured, never 0."""
    out = []
    for m, a, b in zip(mean, lo, hi, strict=True):
        if not np.isfinite(m):
            out.append(None)
        elif edge(m, a, b):
            out.append([shown(a), shown(b)])
        else:
            out.append(shown(m))
    return out


def reaches_one(figs):
    """Whether the postcode is SHOWN 1 a day or more on some kind of day (a range's top counts): an airport
    whose every figure reads '<1' or 0 is not listed, and a postcode with none listed is in `none`."""
    return any(isinstance(top, int) and top >= 1
               for f in figs if f is not None for top in ([f[1]] if isinstance(f, list) else [f]))


def build(arrays, meta):
    """{file name: object} for every district and airports.json, from the averages file's arrays and meta."""
    airports = [str(a) for a in arrays['airports']]
    if sorted(airports) != sorted(meta['published']):
        raise SystemExit('the averages file lists airports its meta does not publish: refusing to build')
    ai = list(arrays['angles']).index(ANGLE)
    mean = arrays['mean'][:, :, :, ai]
    lo, hi = arrays['mean_lo'][:, :, :, ai], arrays['mean_hi'][:, :, :, ai]
    context = arrays['context_all_traffic_unpublishable'][:, ai]
    days = arrays['days']
    # Everything that passes over a cell on an average day, from the published airports alone: each kind of day
    # weighted by its share of the airport's days, so it compares with the context's every-day average.
    share = days / days.sum(axis=1, keepdims=True)
    published_total = np.nansum(mean * share[None, :, :], axis=(1, 2))

    # Only an airport reaching SHOWN_FROM somewhere within 100 m can be listed: the rest need no figures worked out.
    near = np.nanmax(np.where(np.isfinite(hi), hi, -1.0), axis=2) >= SHOWN_FROM  # [postcode, airport]
    files = {}
    for k, pc in enumerate(arrays['postcode']):
        pc = str(pc)
        district = pc.split()[0]
        f = files.setdefault(f'{district}.json', {'district': district, 'postcodes': {}, 'none': [], 'approx': [],
                                                  'other': []})
        listed = {}
        for a in np.flatnonzero(near[k]):
            figs = figures(mean[k, a], lo[k, a], hi[k, a])
            if reaches_one(figs):
                listed[airports[a]] = figs
        if listed:
            f['postcodes'][pc] = listed
        else:
            f['none'].append(pc)
        if int(arrays['gridind'][k]) in COARSE_GRIDIND:
            f['approx'].append(pc)
        if np.isfinite(context[k]) and other_traffic(published_total[k], float(context[k])):
            f['other'].append(pc)

    # The page fetches a district's file only when it is listed here, so a postcode outside the covered councils
    # costs no request and no 404 in the console; the bars share one scale, the busiest figure any postcode is shown.
    tops = [top for f in files.values() for listed in f['postcodes'].values() for figs in listed.values()
            for v in figs if v is not None for top in ([v[1]] if isinstance(v, list) else [v]) if isinstance(top, int)]
    files['airports.json'] = {
        'classes': list(pa.CLASSES),
        'districts': sorted(f['district'] for f in files.values()),
        'bar_full': max(tops, default=1),
        'angle_deg': ANGLE, 'ceiling_ft': ao.CEILING_FT,
        'definition': DEFINITION,
        'direction_rule': f'A day counts as one way when {ao.DIRECTION_DAY_SHARE:.0%} of its flights used that way.',
        'airports': {code: {'days': dict(zip(pa.CLASSES, days[a].tolist(), strict=True)),
                            'share_pct': {c: shown(100 * s) for c, s in zip(pa.CLASSES, share[a].tolist(), strict=True)},
                            'months': [meta['published'][code]['months'][0], meta['published'][code]['months'][-1]]}
                     for a, code in enumerate(airports)},
        'credits': ['Flight tracks: adsb.lol (ODbL 1.0)', 'Weather at each airport: Iowa Environmental Mesonet',
                    'Ground heights: Contains OS data © Crown copyright and database right',
                    'Postcode positions: ONS National Statistics Postcode Lookup (OGL)'],
        'licence': 'Open Database License (ODbL) 1.0',
    }
    return files


def encode(obj):
    """The bytes a file holds: compact, keys in their written order, one trailing newline."""
    return (json.dumps(obj, separators=(',', ':'), ensure_ascii=False) + '\n').encode('utf-8')


def manifest(encoded):
    """{file name: {bytes, md5}} for the built files."""
    return {name: {'bytes': len(b), 'md5': hashlib.md5(b, usedforsecurity=False).hexdigest()}
            for name, b in sorted(encoded.items())}


def write(encoded, out_dir=OUT_DIR, manifest_path=MANIFEST):
    """Write every file, remove any district that no longer exists, then the manifest last."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob('*.json'):
        if old.name not in encoded:
            old.unlink()
    for name, b in encoded.items():
        (out_dir / name).write_bytes(b)
    manifest_path.write_text(json.dumps(manifest(encoded), indent=1) + '\n', encoding='utf-8', newline='\n')


def check(encoded, out_dir=OUT_DIR, manifest_path=MANIFEST):
    """The differences between what --write would write and what is on disk, as lines (none: in step)."""
    problems = []
    on_disk = {p.name for p in out_dir.glob('*.json')} if out_dir.exists() else set()
    for name in sorted(set(encoded) | on_disk):
        if name not in on_disk:
            problems.append(f'missing: {name}')
        elif name not in encoded:
            problems.append(f'no longer built: {name}')
        elif (out_dir / name).read_bytes() != encoded[name]:
            problems.append(f'stale: {name}')
    try:
        recorded = json.loads(manifest_path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        recorded = None
    if recorded != manifest(encoded):
        problems.append(f'{manifest_path.name} does not match the built files')
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--at', action='append', default=[], help='print what a postcode is told')
    a = ap.parse_args()
    if not AVERAGES.exists():
        print(f'{AVERAGES.relative_to(ROOT)} is missing: scripts/adsb_postcode_averages.py builds it', file=sys.stderr)
        return 1
    arrays, meta = pa.read(AVERAGES)
    files = build(arrays, meta)
    encoded = {name: encode(obj) for name, obj in files.items()}
    if a.write:
        write(encoded)
        total = sum(len(b) for b in encoded.values())
        print(f'{len(encoded) - 1} district files and airports.json, {total / 1e6:.1f} MB')
    if a.check:
        problems = check(encoded)
        print('\n'.join(problems) if problems else 'OK')
        if problems:
            return 1
    for want in a.at:
        pc = ' '.join(want.upper().split())
        f = files.get(f'{pc.split()[0]}.json')
        if f is None:
            print(f'{pc}: no district file')
            continue
        told = f['postcodes'].get(pc, 'none from the ten airports' if pc in f['none'] else 'NOT MEASURED')
        flags = [n for n in ('approx', 'other') if pc in f[n]]
        print(f'{pc}: {told}' + (f'  flags: {flags}' if flags else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
