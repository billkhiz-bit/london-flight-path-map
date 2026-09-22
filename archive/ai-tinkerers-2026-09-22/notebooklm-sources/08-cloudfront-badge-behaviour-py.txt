#!/usr/bin/env python3
"""Give /badge an edge cache on the site's own CloudFront distribution.

WHY (audit M1, ROADMAP open decision 2, option A). `GET /badge?postcode=`
answers with `Cache-Control: public, max-age=86400` (5 min for an uncovered
postcode), and nothing between the viewer and the Lambda honours it: API
Gateway's edge does not cache, so every distinct viewer's first render is an
invocation and the 5 RPS route throttle is the only server-side bound. A
listing page with many first-time viewers renders a broken image.

WHAT IT DOES. Adds the API (`2gjfdzg20c.execute-api.eu-west-2.amazonaws.com`,
origin path `/prod`) as a second origin on `EGSSPJKLFL33M` and a `/badge`
behaviour in front of it, keyed on the `postcode` query string.

THREE THINGS THAT ARE NOT OBVIOUS, all measured 2026-09-15:

  1. NOT a managed cache policy. Both `UseOriginCacheControlHeaders*` managed
     policies put the viewer `Host` header in the cache key and forward it,
     and API Gateway answers 403 to a Host it does not own. A custom policy
     needs `cloudfront:CreateCachePolicy`, which flightmap-dev lacks. So the
     behaviour carries its own forwarding settings: query string `postcode`
     only, no headers, no cookies, TTL 0 / 86400 / 31536000 - which is what
     lets the origin's own Cache-Control set the lifetime.
  2. NO function on this behaviour. The default behaviour runs
     `sky-score-rewrite-index`, which turns an extensionless `/badge` into
     `/badge/index.html`. Behaviour selection happens before the function
     runs, so a behaviour with no association is exempt.
  3. ORDER. Apply this FIRST, `--verify` it, and only then repoint the two
     badge URLs in index.html (`embedSnippet()` and the `badge-preview`
     img) from API_BASE to `/badge`. Repointing first breaks every badge.
     The verification uses TWO postcodes: one postcode hitting twice also
     passes a cache that keys on nothing and serves the first badge to
     everyone for a day.

USAGE
    python scripts/cloudfront_badge_behaviour.py --plan     # print the change, touch nothing
    python scripts/cloudfront_badge_behaviour.py --apply    # UpdateDistribution, wait for Deployed
    python scripts/cloudfront_badge_behaviour.py --verify   # two postcodes, both must HIT

Needs AWS_PROFILE=flightmap (or the env equivalent); boto3, like the loaders,
not the CLI. Refuses to apply if the origin or a /badge behaviour is already
present, so it is safe to re-run.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

import boto3

DISTRIBUTION_ID = 'EGSSPJKLFL33M'
API_HOST = '2gjfdzg20c.execute-api.eu-west-2.amazonaws.com'
ORIGIN_ID = 'APIGW-2gjfdzg20c-prod'
PATH_PATTERN = '/badge'
SITE = 'https://skyscore.co.uk'
# Two postcodes that score, in different cities, so the SVGs differ.
VERIFY_POSTCODES = ('SW11 1AA', 'M1 1AE')


_CF = None


def cf():
    global _CF
    if _CF is None:
        # CloudFront is a global service; the region is what boto3 needs to
        # sign with and is otherwise irrelevant.
        _CF = boto3.client('cloudfront', region_name='us-east-1')
    return _CF


def current():
    d = cf().get_distribution_config(Id=DISTRIBUTION_ID)
    return d['DistributionConfig'], d['ETag']


def build(cfg):
    """The config with the origin and behaviour added, or a reason not to."""
    if any(o['Id'] == ORIGIN_ID for o in cfg['Origins']['Items']):
        return None, f'origin {ORIGIN_ID} already present'
    if any(b['PathPattern'] == PATH_PATTERN for b in cfg['CacheBehaviors'].get('Items', [])):
        return None, f'a {PATH_PATTERN} behaviour already exists'

    cfg = json.loads(json.dumps(cfg))
    cfg['Origins']['Items'].append({
        'Id': ORIGIN_ID,
        'DomainName': API_HOST,
        'OriginPath': '/prod',
        'CustomHeaders': {'Quantity': 0},
        'CustomOriginConfig': {
            'HTTPPort': 80,
            'HTTPSPort': 443,
            'OriginProtocolPolicy': 'https-only',
            'OriginSslProtocols': {'Quantity': 1, 'Items': ['TLSv1.2']},
            'OriginReadTimeout': 30,
            'OriginKeepaliveTimeout': 5,
        },
        'ConnectionAttempts': 3,
        'ConnectionTimeout': 10,
        'OriginShield': {'Enabled': False},
    })
    cfg['Origins']['Quantity'] = len(cfg['Origins']['Items'])

    items = cfg['CacheBehaviors'].get('Items', [])
    items.append({
        'PathPattern': PATH_PATTERN,
        'TargetOriginId': ORIGIN_ID,
        'ViewerProtocolPolicy': 'redirect-to-https',
        'AllowedMethods': {
            'Quantity': 2, 'Items': ['GET', 'HEAD'],
            'CachedMethods': {'Quantity': 2, 'Items': ['GET', 'HEAD']},
        },
        'Compress': True,
        'SmoothStreaming': False,
        'FieldLevelEncryptionId': '',
        'ForwardedValues': {
            'QueryString': True,
            'QueryStringCacheKeys': {'Quantity': 1, 'Items': ['postcode']},
            'Cookies': {'Forward': 'none'},
            'Headers': {'Quantity': 0},
        },
        'MinTTL': 0,
        'DefaultTTL': 86400,
        'MaxTTL': 31536000,
        'TrustedSigners': {'Enabled': False, 'Quantity': 0},
        'TrustedKeyGroups': {'Enabled': False, 'Quantity': 0},
        'LambdaFunctionAssociations': {'Quantity': 0},
        'FunctionAssociations': {'Quantity': 0},
    })
    cfg['CacheBehaviors'] = {'Quantity': len(items), 'Items': items}
    return cfg, None


def plan():
    cfg, etag = current()
    print(f'{DISTRIBUTION_ID} ETag {etag}: {cfg["Origins"]["Quantity"]} origin(s), '
          f'{cfg["CacheBehaviors"]["Quantity"]} behaviour(s)')
    new, why = build(cfg)
    if new is None:
        print(f'nothing to do: {why}')
        return 0
    print(f'would add origin {ORIGIN_ID} -> {API_HOST}/prod')
    print(f'would add behaviour {PATH_PATTERN}: query-string key [postcode], no headers, '
          f'no cookies, TTL 0/86400/31536000, no function')
    return 0


def apply():
    cfg, etag = current()
    new, why = build(cfg)
    if new is None:
        print(f'refusing to apply: {why}')
        return 1
    result = cf().update_distribution(Id=DISTRIBUTION_ID, IfMatch=etag, DistributionConfig=new)
    dist = result['Distribution']
    print(f'update accepted: status {dist["Status"]}, '
          f'{dist["DistributionConfig"]["Origins"]["Quantity"]} origins, '
          f'{dist["DistributionConfig"]["CacheBehaviors"]["Quantity"]} behaviour(s)')
    print('waiting for Deployed (typically 3-6 minutes) ...')
    cf().get_waiter('distribution_deployed').wait(Id=DISTRIBUTION_ID)
    print('Deployed. Now run --verify.')
    return 0


def fetch(url):
    """(status, X-Cache, body). A 4xx is a result here, not an exception:
    before the behaviour exists /badge falls through to the S3 origin and
    answers 403 (measured), and that must read as FAIL, not as a traceback."""
    req = urllib.request.Request(url, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.headers.get('X-Cache', ''), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get('X-Cache', ''), b''


def verify():
    """Two postcodes, each fetched twice: second call must HIT, and the two
    badges must differ from each other (a cache keyed on nothing passes the
    first test and fails the second)."""
    bodies = {}
    ok = True
    for pc in VERIFY_POSTCODES:
        url = f'{SITE}{PATH_PATTERN}?postcode={pc.replace(" ", "+")}'
        first = fetch(url)
        time.sleep(1)
        second = fetch(url)
        hit = 'Hit' in second[1]
        print(f'{pc}: {first[0]} {first[1]!r} then {second[0]} {second[1]!r} -> {"HIT" if hit else "NO HIT"}')
        ok = ok and hit and first[0] == 200
        bodies[pc] = second[2]
    distinct = len(set(bodies.values())) == len(bodies)
    print(f'badges differ across postcodes: {distinct}')
    ok = ok and distinct
    print('PASS: /badge is edge-cached per postcode - repoint index.html now' if ok
          else 'FAIL: do NOT repoint index.html')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--plan', action='store_true')
    g.add_argument('--apply', action='store_true')
    g.add_argument('--verify', action='store_true')
    a = ap.parse_args()
    return plan() if a.plan else apply() if a.apply else verify()


if __name__ == '__main__':
    sys.exit(main())
