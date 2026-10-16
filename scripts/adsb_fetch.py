"""Download, cut down and discard adsb.lol flight history, one day at a time.

WHY THIS EXISTS
---------------
Step 1 of "how often planes pass" (ROADMAP) compares a whole MONTH of tracked
take-offs and landings with the CAA's figure for the same month, and step 2
needs a whole year. A day is ~3.7 GB, so the only workable shape is: fetch a
day, run adsb_extract.py on it (81 MB kept), delete the raw archive, move on.
Bill agreed the raw days are deleted automatically once extracted (2026-10-15).

It is RESUMABLE: a day whose extract already exists is skipped, and a partly
downloaded part is resumed, so re-running after a sleep or a dropped
connection carries on. A day that fails keeps its raw files for diagnosis and
the run continues; the exit status is non-zero if any day failed.

Release names come from the GitHub API and are UNTRUSTED: an asset is only
saved under a name matching ASSET_RE, inside data/adsb/raw/<day>/. The API
allows 60 unauthenticated calls an hour, one per day here, which is ample at
~4 minutes a day; set GITHUB_TOKEN to lift it.

PYTHON: run these two scripts under a current Python, not the project's 3.11. They parse an
untrusted tar stream, and the tarfile header-parsing fixes (e.g. CVE-2024-6232) reached 3.11 only
in source-only releases after 3.11.9, the last with a Windows installer. They use the standard
library alone, so any current Python will do; on Bill's machine that is an unregistered embeddable
3.13 (C:/Users/bilal/tools/python-3.13.15/python.exe, checked against python.org's hash,
2026-10-16). The fetcher runs the extractor with the same interpreter.

Usage:
    python -I -u scripts/adsb_fetch.py 2026-08-01 2026-08-31
    python -I -u scripts/adsb_fetch.py 2026-08-01 2026-08-31 --keep-raw
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'adsb' / 'raw'
EXTRACT = ROOT / 'data' / 'adsb' / 'extract'
REPO_API = 'https://api.github.com/repos/adsblol/globe_history_{year}/releases/tags/{tag}'
ASSET_RE = re.compile(r'^v\d{4}\.\d{2}\.\d{2}-planes-readsb-prod-0\.tar(\.a[a-z])?$')
CHUNK = 1 << 20
RETRIES = 5


def log(msg):
    print(f'{dt.datetime.now():%H:%M:%S} {msg}', flush=True)


def tag_for(day):
    return f'v{day:%Y.%m.%d}-planes-readsb-prod-0'


def assets_for(day):
    """[(name, size, url)] for a day's 'prod' release."""
    req = urllib.request.Request(REPO_API.format(year=day.year, tag=tag_for(day)),
                                 headers={'Accept': 'application/vnd.github+json'})
    if os.environ.get('GITHUB_TOKEN'):
        req.add_header('Authorization', f'Bearer {os.environ["GITHUB_TOKEN"]}')
    with urllib.request.urlopen(req, timeout=60) as resp:
        release = json.load(resp)
    out = []
    for a in release.get('assets', []):
        # Only the archive parts are wanted. Anything else (a checksum or a
        # README the publisher may add) is skipped by name, never saved, and
        # never allowed to fail the day.
        if not ASSET_RE.match(a['name']):
            log(f'    skipping asset {a["name"]!r}: not an archive part')
            continue
        url = a['browser_download_url']
        # The release JSON is untrusted: download only over https from GitHub, never
        # file:// or plain http (audit 2026-10-16).
        if not url.startswith(('https://github.com/', 'https://objects.githubusercontent.com/')):
            raise RuntimeError(f'asset {a["name"]!r} has an unexpected download URL: {url!r}')
        out.append((a['name'], int(a['size']), url))
    if not out:
        raise RuntimeError(f'release {tag_for(day)} has no archive parts')
    return sorted(out)


def download(url, path, size):
    """Fetch url to path, resuming a partial file; True once the size matches."""
    for attempt in range(1, RETRIES + 1):
        have = path.stat().st_size if path.exists() else 0
        if have == size:
            return True
        if have > size:
            path.unlink()
            have = 0
        req = urllib.request.Request(url, headers={'Range': f'bytes={have}-'} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                # Append only to a genuine partial reply (206). A server that
                # ignores Range answers 200 with the WHOLE file, which appended
                # to the partial one would overshoot and restart every retry.
                mode = 'ab' if have and resp.status == 206 else 'wb'
                with path.open(mode) as fh:
                    while True:
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
        except OSError as exc:
            log(f'    {path.name}: attempt {attempt} failed ({exc}); retrying')
            time.sleep(10 * attempt)
    return path.exists() and path.stat().st_size == size


def run_day(day, keep_raw):
    out = EXTRACT / f'{day:%Y-%m-%d}.jsonl.gz'
    if out.exists():
        log(f'{day:%Y-%m-%d}: extract exists, skipped')
        return True
    day_dir = RAW / f'{day:%Y-%m-%d}'
    day_dir.mkdir(parents=True, exist_ok=True)
    parts = assets_for(day)
    log(f'{day:%Y-%m-%d}: {len(parts)} parts, {sum(s for _, s, _ in parts) / 2**30:.2f} GiB')
    for name, size, url in parts:
        if not download(url, day_dir / name, size):
            log(f'{day:%Y-%m-%d}: {name} did not download in full; raw kept')
            return False
    res = subprocess.run(  # noqa: S603  (our own script; the path is ours, built from a parsed date)
        [sys.executable, '-I', str(ROOT / 'scripts' / 'adsb_extract.py'), str(day_dir)],
        capture_output=True, text=True)
    summary = (res.stdout.strip().splitlines() or [''])[-1]
    if res.returncode != 0 or not out.exists():
        log(f'{day:%Y-%m-%d}: extract FAILED ({res.returncode}): {res.stderr.strip()[-300:] or summary}')
        return False
    log(f'    {summary}')
    if not keep_raw:
        for name, _, _ in parts:
            (day_dir / name).unlink()
        day_dir.rmdir()
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('first', type=dt.date.fromisoformat)
    ap.add_argument('last', type=dt.date.fromisoformat)
    ap.add_argument('--keep-raw', action='store_true', help='keep each day\'s archive after extracting')
    args = ap.parse_args()
    if args.last < args.first:
        raise SystemExit('last day is before the first')
    failed, day = [], args.first
    while day <= args.last:
        try:
            if not run_day(day, args.keep_raw):
                failed.append(day)
        except (OSError, RuntimeError, ValueError) as exc:
            log(f'{day:%Y-%m-%d}: FAILED ({exc})')
            failed.append(day)
        day += dt.timedelta(days=1)
    log('done' + (f'; {len(failed)} day(s) failed: {", ".join(f"{d:%Y-%m-%d}" for d in failed)}' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
