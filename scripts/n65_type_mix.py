"""How one day's movements at an airport resolve to ANP aircraft (N65 step 3): shares by HOW, never per type.

Reads a day's ADS-B extract (`data/adsb/extract/<day>.jsonl.gz`), counts its movements with adsb_movements (the
same counter the planes feature uses), and resolves each movement's type through scripts/n65_types.py. Prints the
share of movements by how they resolved (own data, proxy, louder variant, by registration, none), which is what
decides whether the registry and the newer ANP release matter. Per-type rows are EASA-derived, so they are written
only with --per-type-out, and only to a path OUTSIDE this repo (refused otherwise).

    python -I -B scripts/n65_type_mix.py --extract data/adsb/extract/2026-07-15.jsonl.gz --airport LHR \
        --anp <v2.3 tables dir> [--anp <v9 dir>] --candidates <subs csv> [--candidates <own-data csv>] \
        [--registry <csv: registration,engine>] [--per-type-out <path outside the repo>]

Run with the system Python (adsb_movements needs tzdata, numpy and pyproj); `-I -B` keeps it from importing or
writing anything beside the extract.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / 'scripts'))
import adsb_movements as am  # noqa: E402
import n65_types as nt  # noqa: E402

OP_OF_KIND = {'take-off': 'D', 'landing': 'A'}


def near_traces(extract: Path, ap: dict) -> list[dict]:
    (clat, clon), zone = ap['centre'], ap['zone_km']
    dlat = zone / 111.2
    dlon = zone / (111.2 * math.cos(math.radians(clat)))
    out = []
    with gzip.open(extract, 'rt', encoding='utf-8') as fh:
        for line in fh:
            rec = json.loads(line)
            pts = rec['pts']
            if any(abs(p[1] - clat) <= dlat and abs(p[2] - clon) <= dlon for p in pts) and \
                    any(am.km_between(p[1], p[2], clat, clon) <= zone for p in pts):
                out.append(rec)
    return out


def read_registry(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    with open(path, encoding='utf-8-sig', newline='') as fh:
        return {r['registration'].strip().upper(): r['engine'].strip() for r in csv.DictReader(fh) if r.get('engine')}


CALLSIGN_AIRLINE = re.compile(r'([A-Z]{3})\d')


def airline_of(rec: dict) -> str:
    """The airline's ICAO code from the trace's most frequent callsign ('BAW123A' -> 'BAW'); '' for a callsign that
    is a registration or missing. Points carry the callsign as their last field."""
    calls = Counter(p[-1].strip() for p in rec.get('pts', []) if isinstance(p[-1], str) and p[-1].strip())
    m = CALLSIGN_AIRLINE.match(calls.most_common(1)[0][0]) if calls else None
    return m.group(1) if m else ''


def outside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO.resolve())
        return False
    except ValueError:
        return True


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap_.add_argument('--extract', type=Path, required=True)
    ap_.add_argument('--airport', default='LHR')
    ap_.add_argument('--anp', type=Path, action='append', required=True, help='ANP release dir; later ones win')
    ap_.add_argument('--candidates', type=Path, action='append', required=True)
    ap_.add_argument('--registry', type=Path)
    ap_.add_argument('--operator-engines', type=Path, help='airline-and-type engine table (n65_types)')
    ap_.add_argument('--per-type-out', type=Path)
    a = ap_.parse_args(argv)
    if a.per_type_out and not outside_repo(a.per_type_out):
        print(f'REFUSED: --per-type-out {a.per_type_out} is inside the repo; per-type rows are EASA-derived')
        return 2

    anp = nt.load_anp(*a.anp)
    cands = nt.index_candidates(*(nt.read_candidates(p) for p in a.candidates))
    registry = read_registry(a.registry)
    operator_engines = nt.read_operator_engines(a.operator_engines) if a.operator_engines else {}
    airport = am.load_airports()[a.airport]
    traces = near_traces(a.extract, airport)
    field, how_field = am.field_level(traces, airport)

    by_how, by_type = Counter(), Counter()
    total = 0
    for rec in traces:
        moves, _ = am.movements(rec, airport, field)
        airline = airline_of(rec)
        for kind, _rw, _ts in moves:
            op = OP_OF_KIND.get(kind)
            if not op:
                continue
            r = nt.resolve(rec.get('t') or '', rec.get('r') or '', op, cands, anp, registry, airline, operator_engines)
            total += 1
            by_how[r.how] += 1
            by_type[(r.icao or '?', op, r.how, r.candidate.anp_id if r.candidate else '', airline)] += 1

    print(f'{a.airport} {a.extract.name}: field {field} ({how_field}); {len(traces)} traces near; {total} movements')
    print(f'ANP releases: {", ".join(p.name for p in a.anp)}; registry entries: {len(registry)}; '
          f'airline-and-type rows: {len(operator_engines)}')
    for how in nt.HOW:
        n = by_how.get(how, 0)
        print(f'  {how:<16} {n:>5}  {100 * n / total if total else 0:5.1f}%')
    if a.per_type_out:
        with open(a.per_type_out, 'w', encoding='utf-8', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['icao', 'op', 'how', 'anp_id', 'airline', 'movements'])
            for (icao, op, how, anp_id, airline), n in by_type.most_common():
                w.writerow([icao, op, how, anp_id, airline, n])
        print(f'per-type rows: {a.per_type_out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
