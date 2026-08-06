"""Screen a candidate brand name for collisions before committing to it.

WHY THIS EXISTS (2026-08-05). The Sky Score rename search kept producing
false comfort. A web search reported "Assay" as the cleanest of four
candidates; the actual IPO register showed a bare ASSAY word mark filed in
May 2026 covering classes 36, 37 and 42, plus a registered THE ASSAY in
class 9. Both of those are Sky Score's classes. Web search is not a
clearance instrument and should not be used as one.

WHAT THIS AUTOMATES, AND WHAT IT DELIBERATELY DOES NOT
-------------------------------------------------------
* **Companies House** has a real public REST API, so this queries it properly.
  The value is not the match count - "Assay" returns 114 and almost all are
  irrelevant. The value is **filtering by SIC code**, so a property or software
  company using the name surfaces above the noise. ASSAY PROPERTY PARTNER
  LIMITED was the one row of 114 that mattered.

* **The UK IPO has no public trade mark API.** Ipsum is being retired in
  favour of "One IPO Search" with bulk-data APIs committed for a 2026 rollout
  but not broadly available. The alternatives are scraping their web form or
  parsing the weekly Trade Marks Journal PDFs, and a scraper that silently
  breaks would be worse than no check at all - it would report "clean" for a
  name nobody looked at. So this prints the search URL and the exact classes
  to check, and you run it yourself. **That manual step is the real
  clearance check. Everything this script prints is a pre-filter.**

* **Domain checks are DNS only**, which proves a domain RESOLVES, not that it
  is unregistered. A parked domain looks identical to a free one here.

Usage:
    python scripts/check_name.py chainage
    python scripts/check_name.py chainage assay datum

Needs a free Companies House API key in the environment or .env as
COMPANIES_HOUSE_API_KEY. Get one at:
    https://developer.company-information.service.gov.uk/
"""

import base64
import json
import os
import pathlib
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
CH_SEARCH = 'https://api.company-information.service.gov.uk/search/companies'

# SIC codes that make a match RELEVANT rather than merely present. A hair
# salon sharing the name is noise; a property data company is the finding.
RELEVANT_SIC = {
    '62011': 'Ready-made interactive leisure and entertainment software',
    '62012': 'Business and domestic software development',
    '62020': 'Information technology consultancy activities',
    '62090': 'Other information technology service activities',
    '63110': 'Data processing, hosting and related activities',
    '63120': 'Web portals',
    '63990': 'Other information service activities',
    '68100': 'Buying and selling of own real estate',
    '68209': 'Letting and operating of own or leased real estate',
    '68310': 'Real estate agencies',
    '68320': 'Management of real estate on a fee or contract basis',
    '71111': 'Architectural activities',
    '71129': 'Other engineering activities (includes surveying)',
    '74901': 'Environmental consulting activities',
    '74909': 'Other professional and technical activities',
}

# The two classes Sky Score would file in. Named here so the manual step
# below cannot drift from what the business actually needs.
IPO_CLASSES = {
    '9': 'downloadable software and mobile apps (the iOS/Android app)',
    '42': 'SaaS, software services, data services (the /v1/score API)',
    '36': 'financial services and real estate affairs (worth checking too)',
}

DOMAIN_SUFFIXES = ['.co.uk', '.com', '.io', 'score.co.uk', 'score.com', 'data.co.uk', 'property.co.uk']


def load_api_key() -> str | None:
    """Environment first, then .env. Never accept a key as a CLI argument -
    that would put it in shell history."""
    key = os.environ.get('COMPANIES_HOUSE_API_KEY')
    if key:
        return key.strip()

    env_file = REPO / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8', errors='replace').splitlines():
            if line.startswith('COMPANIES_HOUSE_API_KEY='):
                return line.split('=', 1)[1].strip().strip('"\'')
    return None


def search_companies(name: str, key: str, limit: int = 100) -> list[dict]:
    query = urllib.parse.urlencode({'q': name, 'items_per_page': limit})
    req = urllib.request.Request(f'{CH_SEARCH}?{query}')
    # Companies House uses HTTP Basic with the key as username and an empty
    # password.
    token = base64.b64encode(f'{key}:'.encode()).decode()
    req.add_header('Authorization', f'Basic {token}')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()).get('items', [])
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            print('  ERROR: Companies House rejected the API key (401).')
        elif exc.code == 429:
            print('  ERROR: rate limited (429). The cap is ~600 requests per 5 minutes.')
        else:
            print(f'  ERROR: Companies House returned HTTP {exc.code}.')
        return []
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f'  ERROR: could not reach Companies House ({exc}).')
        return []


def domain_resolves(domain: str) -> bool | None:
    """True = resolves (in use). False = no A record. None = check failed.

    None matters: a broken resolver that returns False for everything would
    report every domain as available, which is exactly the false-green this
    whole script exists to avoid.
    """
    # Resolve directly rather than shelling out to nslookup and parsing its
    # human-readable output. Two bugs came from doing it the other way, and
    # both were invisible without a control:
    #   1. testing for a line starting "Address:" matched the RESOLVER's own
    #      IP on every query including failures, and missed multi-record
    #      domains entirely because those print "Addresses:" (plural). It
    #      reported bbc.co.uk as having no DNS record.
    #   2. nslookup writes "can't find ...: Non-existent domain" to STDERR,
    #      so reading stdout alone turned every unregistered domain into
    #      "could not determine" rather than "no record".
    # getaddrinfo has neither problem, works on any platform, needs no
    # external binary, and satisfies the subprocess lint rules by not
    # existing. Verified in both directions: a known-live domain returns
    # True, a random string returns False.
    try:
        socket.getaddrinfo(domain, None)
    except socket.gaierror:
        return False
    except OSError:
        return None
    return True


def report(name: str, key: str | None) -> None:
    print(f'\n{"=" * 68}\n  {name.upper()}\n{"=" * 68}')

    print('\n-- Companies House --')
    if not key:
        print('  SKIPPED: no COMPANIES_HOUSE_API_KEY set. This is a SKIP, not a pass.')
        print('  Free key: https://developer.company-information.service.gov.uk/')
    else:
        items = search_companies(name, key)
        active = [i for i in items if i.get('company_status') == 'active']
        relevant = []
        for item in active:
            hits = [s for s in item.get('sic_codes') or [] if s in RELEVANT_SIC]
            if hits:
                relevant.append((item, hits))

        print(f'  {len(items)} matches, {len(active)} active.')
        if relevant:
            print(f'  {len(relevant)} active in a RELEVANT sector:')
            for item, hits in relevant:
                print(f'    * {item.get("title")}  [{item.get("company_number")}]')
                for sic in hits:
                    print(f'        {sic} {RELEVANT_SIC[sic]}')
        else:
            print('  No active company in a property/software/data SIC code.')
            print('  NB: the search API omits SIC codes for some records, so this')
            print('      is a weak negative. Spot-check the closest names by hand.')

    print('\n-- Domains (DNS only: resolving proves USE, not registration) --')
    for suffix in DOMAIN_SUFFIXES:
        domain = f'{name}{suffix}'
        state = domain_resolves(domain)
        label = {True: 'in use', False: 'no A record', None: 'CHECK FAILED'}[state]
        print(f'  {domain:<32} {label}')

    print('\n-- UK IPO: NOT AUTOMATED, DO THIS BY HAND --')
    print('  There is no public IPO trade mark API. This is the clearance check;')
    print('  everything above is a pre-filter.')
    print('  https://trademarks.ipo.gov.uk/ipo-tmtext')
    print(f'  Search: {name.upper()}   then also {name.upper()}SCORE')
    for cls, meaning in IPO_CLASSES.items():
        print(f'    class {cls:<3} {meaning}')
    print('  Treat a PENDING application as a blocker, not a maybe: a published')
    print('  application in your class is someone actively claiming the word.')


def main() -> None:
    names = [a.strip().lower() for a in sys.argv[1:] if a.strip()]
    if not names:
        print(__doc__)
        sys.exit(2)

    key = load_api_key()
    for name in names:
        report(name, key)

    print(f'\n{"=" * 68}')
    print('  Nothing here is clearance. The IPO search decides, and for a name')
    print('  you intend to build a business on, a paid clearance opinion is the')
    print('  step after that.')


if __name__ == '__main__':
    main()
