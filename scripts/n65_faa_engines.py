"""N65 step 3: the engine of each US-registered aircraft, from the FAA's aircraft register.

The FAA publishes its whole register as a free daily download ("Releasable Aircraft Database", ~70 MB zip, page:
faa.gov > Aircraft Registry > Releasable Aircraft Download; no reuse restrictions stated there, read 2026-10-31).
Its MASTER file holds each N-number with an engine code; its ENGINE file names the code's maker and model. This
writes ONLY `registration,engine` (e.g. `N12345,GE GENX-1B74/75`): MASTER also holds owners' names and addresses,
which are never read out or written. The CSV is the `--registry` of scripts/n65_type_mix.py and the `registry` of
n65_types.resolve(). Keep both the zip and the CSV outside the repo or in gitignored data/n65/.

    python -I scripts/n65_faa_engines.py <ReleasableAircraft.zip> <out.csv>
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

KEPT_COLUMNS = ('registration', 'engine')


def _rows(z: zipfile.ZipFile, member: str):
    with z.open(member) as fh:
        reader = csv.reader(io.TextIOWrapper(fh, encoding='utf-8-sig', errors='replace', newline=''))
        head = [h.strip().upper() for h in next(reader)]
        for r in reader:
            yield dict(zip(head, (c.strip() for c in r), strict=False))


def build(zip_path: Path, out: Path) -> tuple[int, int]:
    """Write the registration-to-engine CSV; return (register rows read, rows written)."""
    z = zipfile.ZipFile(zip_path)
    engines = {r['CODE']: f"{r.get('MFR', '')} {r.get('MODEL', '')}".strip() for r in _rows(z, 'ENGINE.txt')}
    read = written = 0
    with open(out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(KEPT_COLUMNS)
        for r in _rows(z, 'MASTER.txt'):
            read += 1
            engine = engines.get(r.get('ENG MFR MDL', ''), '')
            if r.get('N-NUMBER') and engine:
                w.writerow(['N' + r['N-NUMBER'].upper(), engine])
                written += 1
    return read, written


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    n_read, n_written = build(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f'register rows {n_read}; written {n_written} -> {sys.argv[2]}')
