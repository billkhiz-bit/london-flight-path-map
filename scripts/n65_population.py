#!/usr/bin/env python3
"""The people inside an N65 contour: Census 2021 postcode headcounts at NSPL's grid references (N65 item 3, 2026-11-12).

WHY THIS EXISTS
---------------
scripts/n65_gate.py's Heathrow rule checks the population inside the 50-event contour against ERCD 2601 Table 16
(528,800, within +-20%): a contour of the right size in the wrong place moves it, where the areas cannot see it.
Nothing counted it, so every run said "population >50: not measured" and no run could pass.

HOW (the CAA's own way: ERCD 2601 s2.25 puts each postcode's people at one point, its centroid)
------------------------------------------------------------------------------------------
- THE PEOPLE: ONS, "Postcode resident and household estimates, England and Wales: Census 2021", dataset P001 (usual
  residents by postcode by sex, as at Census Day, 21 March 2021; postcodes as at May 2021 with at least one usual
  resident), the two sexes summed. Nomis, https://www.nomisweb.co.uk/output/census/2021/pcd_p001.csv. Source: Office
  for National Statistics, Crown copyright, Open Government Licence v3.0. The counts carry the Census's disclosure
  control (record swapping, cell key perturbation): small per postcode, unbiased in a sum of thousands.
- THE PLACE: NSPL's grid reference (`east1m`/`north1m`, postcode_grid.grid_ref), never a re-projection.
- INSIDE: the point lies in a cell whose count reaches the level, the same `>=` n65_day.areas_km2 uses for the area;
  never a bounding box.
- RETIRED SINCE 2021: NSPL keeps a retired postcode with its grid reference, and the Census counted its people there,
  so they stay. NEW SINCE MAY 2021: no Census count (those people were counted under the old postcode), so homes built
  since are missed: ours should read a few percent under CACI's 2025 update of the same Census, before any model gap.
- LARGE USERS (`usrtypind` 1) keep their residents: the Census counts only people living there (a communal
  establishment's among them); a PO box with nobody living at it has no Census row at all. Rule A (10 Nov) keeps large
  users out of the planes figures because a delivery office is not where the planes are heard; these are people the
  Census found living at the postcode. Their number inside is reported beside, never hidden.
- UNPLACED: a Census postcode NSPL does not list, or lists with no coordinate, is counted and reported, never dropped.

REFUSED, NEVER GUESSED: no population file; a file made from another Census table or a broken one; a contour that
reaches the grid's edge (people beyond it would be missing).

The file it builds is gitignored (data/n65/population/): 1.4 million postcodes, OGL, but no place for the public repo.

    python -I -B scripts/n65_population.py build --census data/n65/population/pcd_p001.csv \
        --nspl <main clone>/data/nspl.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import postcode_grid  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_FILE = REPO / 'data' / 'n65' / 'population' / 'residents-2021.npz'
CENSUS_HEADER = ['Postcode', 'Sex (2 categories) Code', 'Sex (2 categories) Label', 'Count']
SOURCE = ('Census 2021 postcode resident estimates, England and Wales (ONS, P001, Census Day 21 March 2021): '
          'Office for National Statistics, Crown copyright, Open Government Licence v3.0')
KIND = 'n65-population-v1'


class Refused(ValueError):
    """No count can be made from what was given; nothing is guessed."""


def read_census(path: Path) -> dict[str, int]:
    """{postcode: usual residents} from P001, the two sexes summed. Refused on another table's header, a count that is
    not a whole number of people, or a postcode with the same sex twice."""
    out: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    with open(path, newline='', encoding='utf-8-sig') as fh:
        rows = csv.reader(fh)
        header = next(rows, None)
        if header != CENSUS_HEADER:
            raise Refused(f'{path.name}: header {header} is not P001\'s {CENSUS_HEADER}')
        for n, row in enumerate(rows, start=2):
            if len(row) != 4:
                raise Refused(f'{path.name} line {n}: {len(row)} fields, not 4')
            pc, sex, _, count = row
            pc = pc.strip().upper()
            if (pc, sex) in seen:
                raise Refused(f'{path.name} line {n}: {pc} has sex code {sex} twice')
            seen.add((pc, sex))
            if not count.isdigit():
                raise Refused(f'{path.name} line {n}: count {count!r} for {pc} is not a whole number of people')
            out[pc] = out.get(pc, 0) + int(count)
    if not out:
        raise Refused(f'{path.name}: no postcodes')
    return out


def place(residents: dict[str, int], nspl_path: Path) -> tuple[dict[str, np.ndarray], dict]:
    """(arrays, about): every Census postcode NSPL can place, at its grid reference, with its large-user and retired
    flags; `about` counts the unplaced and the few placed from lat/long (no grid reference in NSPL)."""
    import pyproj  # only for the rows NSPL gives no grid reference (postcode_grid.grid_ref)

    to_bng = pyproj.Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    east, north, people, large, retired = [], [], [], [], []
    found: set[str] = set()
    projected = 0
    newest = ''
    with open(nspl_path, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        postcode_grid.require_grid_columns(reader.fieldnames, str(nspl_path))
        for col in ('pcds', 'doterm', 'usrtypind', 'dointr'):
            if col not in (reader.fieldnames or []):
                raise Refused(f'{nspl_path.name} has no {col} column')
        for row in reader:
            newest = max(newest, (row.get('dointr') or '').strip())
            pc = (row['pcds'] or '').strip().upper()
            n = residents.get(pc)
            if n is None or pc in found:
                continue
            xy = postcode_grid.grid_ref(row, to_bng)
            if xy is None:
                continue
            if not ((row.get('east1m') or '').strip() and (row.get('north1m') or '').strip()):
                projected += 1
            found.add(pc)
            east.append(xy[0])
            north.append(xy[1])
            people.append(n)
            large.append((row['usrtypind'] or '').strip() == '1')
            retired.append(bool((row['doterm'] or '').strip()))
    unplaced = sorted(set(residents) - found)
    arrays = {'east': np.asarray(east, np.float64), 'north': np.asarray(north, np.float64),
              'residents': np.asarray(people, np.int32), 'large_user': np.asarray(large, bool),
              'retired': np.asarray(retired, bool)}
    about = {
        'postcodes_in_census': len(residents), 'people_in_census': int(sum(residents.values())),
        'postcodes_placed': len(found), 'people_placed': int(arrays['residents'].sum()),
        'postcodes_unplaced': len(unplaced), 'people_unplaced': int(sum(residents[p] for p in unplaced)),
        'unplaced_examples': unplaced[:10], 'placed_from_lat_long': projected,
        'retired_postcodes': int(arrays['retired'].sum()), 'people_at_retired': int(arrays['residents'][arrays['retired']].sum()),
        'nspl_newest_postcode_introduced': newest,
    }
    return arrays, about


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def build(census: Path, nspl: Path, out: Path) -> dict:
    arrays, about = place(read_census(census), nspl)
    meta = {'kind': KIND, 'source': SOURCE, 'census_file': census.name, 'census_sha256': _sha256(census),
            'nspl_file': nspl.name, **about}
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, meta=json.dumps(meta), **arrays)
    return meta


def load(path: Path = DEFAULT_FILE) -> dict:
    """{'meta', 'east', 'north', 'residents', 'large_user', 'retired'}, or Refused when the file is missing or not ours."""
    if not path.exists():
        raise Refused(f'no population file at {path}: build it (python -I -B scripts/n65_population.py build '
                      '--census <P001 csv> --nspl <NSPL csv>)')
    with np.load(path, allow_pickle=False) as z:
        meta = json.loads(str(z['meta']))
        if meta.get('kind') != KIND:
            raise Refused(f'{path.name} is not an N65 population file ({meta.get("kind")!r})')
        pop = {k: z[k] for k in ('east', 'north', 'residents', 'large_user', 'retired')}
    sizes = {len(v) for v in pop.values()}
    if len(sizes) != 1:
        raise Refused(f'{path.name}: its arrays differ in length ({sorted(sizes)})')
    pop['meta'] = meta
    return pop


def people_inside(counts: np.ndarray, grid: dict, cell: float, pop: dict, level: int = 50) -> dict:
    """The people whose postcode's point lies in a cell whose count reaches `level` (cells (i, j) are flat index
    j * nx + i from the corner (x0, y0), as n65_day.Grid). Refused when the contour reaches the grid's edge."""
    nx, ny = int(grid['nx']), int(grid['ny'])
    if counts.size != nx * ny:
        raise Refused(f'{counts.size} counts for a {nx} x {ny} grid')
    inside_cells = counts.reshape(ny, nx) >= level
    if inside_cells[0].any() or inside_cells[-1].any() or inside_cells[:, 0].any() or inside_cells[:, -1].any():
        raise Refused(f'the {level}-event contour reaches the grid\'s edge: people beyond it would be missing')
    i = np.floor((pop['east'] - grid['x0']) / cell).astype(np.int64)
    j = np.floor((pop['north'] - grid['y0']) / cell).astype(np.int64)
    on = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    hit = np.zeros(on.shape, bool)
    hit[on] = inside_cells[j[on], i[on]]
    r = pop['residents']
    return {'people': int(r[hit].sum()), 'postcodes': int(hit.sum()),
            'people_at_large_users': int(r[hit & pop['large_user']].sum()),
            'people_at_retired_postcodes': int(r[hit & pop['retired']].sum()), 'level': level}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build', help='place the Census 2021 headcounts at NSPL grid references')
    b.add_argument('--census', required=True, help="P001 CSV (ONS / Nomis pcd_p001.csv)")
    b.add_argument('--nspl', required=True, help='NSPL CSV (the main clone\'s data/nspl.csv)')
    b.add_argument('--out', default=str(DEFAULT_FILE))
    a = p.parse_args(argv)
    out = Path(a.out)
    import n65_day as nd  # the repo's own rule for where derived files may go
    if not nd._safe_out(out):
        print(f'REFUSED: --out {out} is a tracked place in the repo')
        return 2
    try:
        meta = build(Path(a.census), Path(a.nspl), out)
    except (Refused, OSError) as e:
        print(f'REFUSED: {e}')
        return 2
    print(json.dumps({k: v for k, v in meta.items() if k != 'census_sha256'}, indent=1))
    print(f'written to {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
