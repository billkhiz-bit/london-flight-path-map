#!/usr/bin/env python3
"""Fetch active NHS GP practices and branch surgeries, with postcodes.

WHY THIS ROUTE. The obvious one does not work: `epraccur.zip` on
files.digital.nhs.uk returns **403 even with a browser User-Agent**, so the bulk
download is not scriptable from here. The ODS **syndication API** at
directory.spineservices.nhs.uk is, returns JSON, needs no key, and carries the
postcode in the LIST response so no per-practice detail fetch is needed.

WHICH ROLE CODE, AND WHY IT MATTERS. `RO76` is GP PRACTICE and `RO96` is BRANCH
SURGERY. A first attempt used **`RO177`, which is PRESCRIBING COST CENTRE** - a
financial construct that also covers hospices, care homes, courts, prisons,
immigration removal centres and optometry services. Counting those as "a GP you
could walk to" would have inflated healthcare access everywhere, and the error
would have been invisible in the output: still plausible numbers, still a clean
band, entirely wrong. The role list is fetched and asserted rather than trusted.

QUERY BY `Roles=`, NOT `PrimaryRoleId=`. An English GP practice's PRIMARY role is
RO177; RO76 is a role it also holds. `PrimaryRoleId=RO76` therefore returns
**zero organisations** - a query that looks well-formed, answers 200, and is
silently empty. `Roles=RO76` returns them.

PAGING IS BY HEADER. There is no usable Offset parameter (passing one returns
406); the response carries a `Next-Page` URL and an `X-Total-Count`, and the
count is checked against what was collected so a truncated run cannot pass as a
complete one.

Branch surgeries are INCLUDED. The question the score asks is whether a resident
can reach a GP, and a branch surgery is a place you can attend; excluding them
would understate access in rural and outer-borough areas that are served by one.

  python scripts/fetch_nhs_gp_practices.py            # writes data/nhs-gp-practices.json
  python scripts/fetch_nhs_gp_practices.py --verify   # re-check the role codes
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / 'data' / 'nhs-gp-practices.json'

BASE = 'https://directory.spineservices.nhs.uk/ORD/2-0-0'
UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'
)
# Asserted against the live role list by verify_roles(), not taken on trust.
ROLES = {'RO76': 'GP PRACTICE', 'RO96': 'BRANCH SURGERY'}
PAGE = 1000


def get(url, timeout=180):
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': UA}), timeout=timeout
            ) as resp:
                return json.loads(resp.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3:
                raise SystemExit(f'{url}\n  failed after 3 attempts: {exc}') from exc
            time.sleep(2 * attempt)
    return None


def verify_roles():
    """Fail loudly if a role code no longer means what this script assumes."""
    doc = get(f'{BASE}/roles')
    roles = doc.get('Roles', doc)
    if isinstance(roles, dict):
        roles = roles.get('Role', [])
    by_id = {r.get('id'): (r.get('displayName') or '').upper() for r in roles}
    bad = 0
    for code, expected in ROLES.items():
        actual = by_id.get(code)
        ok = actual == expected
        print(f'  {code}: {actual!r} {"ok" if ok else f"EXPECTED {expected!r}"}')
        bad += not ok
    if bad:
        raise SystemExit(
            f'{bad} role code(s) no longer match. Do NOT fetch until this is resolved - '
            'the wrong code silently counts hospices and care homes as GP surgeries.'
        )
    return 0


def get_with_headers(url, timeout=180):
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': UA}), timeout=timeout
            ) as resp:
                return json.loads(resp.read()), {k.lower(): v for k, v in resp.headers.items()}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3:
                raise SystemExit(f'{url}\n  failed after 3 attempts: {exc}') from exc
            time.sleep(2 * attempt)
    return None, None


def fetch_role(code):
    """Every ACTIVE organisation holding this role, followed by Next-Page."""
    url = f'{BASE}/organisations?Roles={code}&Status=Active&Limit={PAGE}'
    out = []
    expected = None
    while url:
        doc, headers = get_with_headers(url)
        page = doc.get('Organisations', [])
        out.extend(page)
        if expected is None:
            expected = int(headers.get('x-total-count') or 0)
        url = headers.get('next-page')
        print(f'    {code}: {len(out):,}/{expected:,}')
        if url:
            time.sleep(0.4)
    # A short run must fail rather than quietly produce a thin register: fewer
    # surgeries means better-looking distance scores, so under-fetching flatters
    # the data in the direction nobody would question.
    if expected and len(out) < expected:
        raise SystemExit(f'{code}: collected {len(out)} of {expected} - refusing a partial register')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify', action='store_true', help='only re-check the role codes')
    args = ap.parse_args()

    print('verifying role codes against the live ODS role list...')
    verify_roles()
    if args.verify:
        return 0

    records = {}
    for code in ROLES:
        for org in fetch_role(code):
            postcode = (org.get('PostCode') or '').strip().upper()
            if not postcode:
                continue
            # Keyed on OrgId so a practice appearing under both roles is counted
            # once rather than twice.
            records[org['OrgId']] = {
                'name': org.get('Name'),
                'postcode': postcode,
                'role': code,
            }

    OUT.write_text(
        json.dumps(
            {
                'source': 'NHS Organisation Data Service (ODS) syndication API',
                'roles': ROLES,
                'licence': 'Open Government Licence v3.0',
                'count': len(records),
                'practices': records,
            },
            indent=1,
        ),
        encoding='utf-8',
    )
    print(f'\nwrote {len(records):,} active GP practices and branch surgeries to {OUT.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
