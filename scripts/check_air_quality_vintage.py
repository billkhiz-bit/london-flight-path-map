"""Is the air-quality year we serve DEFRA's latest? Asks DEFRA, not a note.

WHY THIS EXISTS (2026-10-01). The NO2 and PM2.5 figures come from DEFRA's PCM
background maps, one file per year, released each October. The loader was
built on 2026-08-06 against 2022, when 2023 and 2024 were both already out, and
nothing noticed for eight weeks: the vintage was a filename, and nothing ever
compared it with what DEFRA publishes. HM Land Registry prices have had this
check since August (build_hpi_prices.py); air quality had none.

HOW. It probes DEFRA's own datastore for the files a roll would load,
`mapno2{year}.csv` and `mappm25{year}g.csv`, for every year after the one we
serve up to the current one. A year counts only when BOTH exist. A one-byte
ranged request is enough to know a file exists without downloading 8 MB.

TWO WAYS TO GO WRONG, BOTH GUARDED:
  - a network failure must not read as "up to date", so it is INCONCLUSIVE;
  - if DEFRA renames its files, every newer year 404s and the served year
    looks current forever. So the SERVED year's own files are probed too, and
    if they no longer resolve the probe is not trusted: INCONCLUSIVE, naming
    the URL that failed.

Advisory and network-bound (preflight runs it beside the other live checks).
Exit 1 when DEFRA publishes a newer year than we serve; 0 when we are current
or when it cannot tell (printed INCONCLUSIVE, which preflight surfaces).

    python scripts/check_air_quality_vintage.py
"""

from __future__ import annotations

import datetime
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import load_defra_air_quality  # noqa: E402  the one holder of the served year

DATASTORE = 'https://uk-air.defra.gov.uk/datastore/pcm/'
UA = {'User-Agent': 'Mozilla/5.0', 'Range': 'bytes=0-0'}


def files_for(year):
    return [f'{DATASTORE}mapno2{year}.csv', f'{DATASTORE}mappm25{year}g.csv']


def exists(url):
    """True on 200/206, False on 404; raises on anything else (network, 5xx)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return r.status in (200, 206)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def latest_published(served, this_year, probe=exists):
    """The newest year whose NO2 and PM2.5 files both exist, or None if the
    served year's own files do not resolve (so the probe cannot be trusted)."""
    if not all(probe(u) for u in files_for(served)):
        return None
    latest = served
    for year in range(served + 1, this_year + 1):
        if all(probe(u) for u in files_for(year)):
            latest = year
    return latest


def main():
    served = load_defra_air_quality.PCM_YEAR
    try:
        latest = latest_published(served, datetime.date.today().year)
    except (OSError, urllib.error.URLError) as exc:
        print(f'INCONCLUSIVE: could not reach DEFRA\'s datastore ({exc})')
        return 0
    if latest is None:
        print(f'INCONCLUSIVE: the files for the year we serve ({served}) no longer resolve at '
              f'{files_for(served)[0]} - DEFRA may have renamed them, so a newer year cannot be seen either')
        return 0
    if latest > served:
        print(f'STALE: we serve PCM {served}; DEFRA publishes up to {latest} '
              f'({latest - served} year(s) newer). Roll it: ROADMAP, "Air quality vintage roll".')
        return 1
    print(f'ok: PCM {served} is the newest year DEFRA publishes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
