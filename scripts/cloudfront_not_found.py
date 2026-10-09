#!/usr/bin/env python3
"""Serve the branded not-found page for any address the site has no file for.

WHY (website audit 2026-10-06, I15). A mistyped address, and the old names /privacy.html,
/terms.html and /pricing.html, answered a raw S3 `403 AccessDenied` XML page. The bucket is not
listable, so S3 answers a missing key with 403 rather than 404, and the distribution had no
custom error responses at all (measured 2026-10-07: CustomErrorResponses.Quantity 0).

WHAT IT DOES. Maps origin 403 and 404 to `/404.html` with status 404, cached 60 s, on
EGSSPJKLFL33M. The old .html names are a separate fix, a 301 in the viewer-request function
(`scripts/install_cloudfront_index_rewrite.py`), so they reach the page rather than this one.

THREE THINGS THAT ARE NOT OBVIOUS:

  1. ORDER. `/404.html` must be AT THE ORIGIN before --apply (`make meta-deploy` uploads it).
     CloudFront fetches the error page from the origin; if it is missing too, the visitor gets
     CloudFront's own error, which is worse than the XML it replaces.
  2. ERROR RESPONSES ARE DISTRIBUTION-WIDE, so they cover the /badge behaviour (API origin) too.
     This said that was safe because "/badge answers every GET with an SVG and status 200,
     including a postcode it does not cover". IT DOES NOT (audit 2026-10-09 I-2, measured live):
     an uncovered postcode's badge is an SVG with status 404, by design in handle_badge, and this
     mapping replaces that body with /404.html, so the badge is a broken image on a partner's
     page (skyscore.co.uk/badge?postcode=EX11HS -> 404 text/html; the API origin -> 404
     image/svg+xml). Open, a decision: the badge answering 200 for "not covered" is the smallest
     fix, since an error response cannot be scoped to a path. --verify fetches a COVERED badge
     only, which is why it passed. 429s are not mapped, so a throttled badge stays a 429.
  3. 404, NOT 200. A not-found page answering 200 tells search engines the mistyped address is
     a real page (a "soft 404"). The page also carries `noindex`.

USAGE
    python scripts/cloudfront_not_found.py --plan     # print the change, touch nothing
    python scripts/cloudfront_not_found.py --apply    # UpdateDistribution, wait for Deployed
    python scripts/cloudfront_not_found.py --verify   # the live behaviour, end to end

Needs AWS_PROFILE=flightmap. Re-running --apply when the responses already match is a no-op.
"""

import argparse
import importlib.util
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import boto3

DISTRIBUTION_ID = 'EGSSPJKLFL33M'
SITE = 'https://skyscore.co.uk'
PAGE = '/404.html'
TTL = 60
WANT = {
    'Quantity': 2,
    'Items': [
        {'ErrorCode': code, 'ResponsePagePath': PAGE, 'ResponseCode': '404', 'ErrorCachingMinTTL': TTL}
        for code in (403, 404)
    ],
}
# What the page says, so --verify knows it got OUR page and not CloudFront's or S3's.
MARKER = b"We can't find that page"

_CF = None


def cf():
    global _CF
    if _CF is None:
        _CF = boto3.client('cloudfront', region_name='us-east-1')
    return _CF


def current():
    d = cf().get_distribution_config(Id=DISTRIBUTION_ID)
    return d['DistributionConfig'], d['ETag']


def matches(cfg):
    have = cfg.get('CustomErrorResponses', {'Quantity': 0})
    norm = sorted(
        (i['ErrorCode'], i.get('ResponsePagePath'), str(i.get('ResponseCode')), i.get('ErrorCachingMinTTL'))
        for i in have.get('Items', [])
    )
    want = sorted(
        (i['ErrorCode'], i['ResponsePagePath'], i['ResponseCode'], i['ErrorCachingMinTTL']) for i in WANT['Items']
    )
    return norm == want


def plan():
    cfg, etag = current()
    have = cfg.get('CustomErrorResponses', {}).get('Quantity', 0)
    print(f'{DISTRIBUTION_ID} ETag {etag}: {have} custom error response(s) now')
    if matches(cfg):
        print('nothing to do: the responses already match')
        return 0
    for i in WANT['Items']:
        print(
            f'would map origin {i["ErrorCode"]} -> {i["ResponsePagePath"]} as {i["ResponseCode"]}, '
            f'cached {i["ErrorCachingMinTTL"]} s'
        )
    return 0


def fetch(url, method='GET'):
    """(status, headers, body) without following redirects, so a 301 reads as a 301."""

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, method=method, headers={'User-Agent': 'sky-score-verify'})
    try:
        with opener.open(req, timeout=30) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read()


def apply():
    page_status, _, page_body = fetch(f'{SITE}{PAGE}')
    if page_status != 200 or MARKER not in page_body:
        print(f'refusing to apply: {PAGE} is not at the origin yet ({page_status}). Run meta-deploy first.')
        return 1
    cfg, etag = current()
    if matches(cfg):
        print('nothing to do: the responses already match')
        return 0
    cfg['CustomErrorResponses'] = WANT
    result = cf().update_distribution(Id=DISTRIBUTION_ID, IfMatch=etag, DistributionConfig=cfg)
    print(f'update accepted: status {result["Distribution"]["Status"]}')
    print('waiting for Deployed (typically 3-6 minutes) ...')
    cf().get_waiter('distribution_deployed').wait(Id=DISTRIBUTION_ID)
    print('Deployed. Now run --verify.')
    return 0


def live_function_matches_source():
    """The published function is the installer's FUNCTION_CODE, byte for byte."""
    spec = importlib.util.spec_from_file_location(
        'installer', Path(__file__).resolve().parent / 'install_cloudfront_index_rewrite.py'
    )
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    live = cf().get_function(Name=installer.FUNCTION_NAME, Stage='LIVE')['FunctionCode'].read().decode()
    return live == installer.FUNCTION_CODE


def verify():
    results = []

    def check(name, ok, detail=''):
        results.append(ok)
        print(f'  {"PASS" if ok else "FAIL"}  {name}{"  " + detail if detail else ""}')

    missing = f'/no-such-page-{uuid.uuid4().hex[:8]}'
    status, headers, body = fetch(f'{SITE}{missing}')
    check(
        'a missing address answers 404 with our page',
        status == 404 and MARKER in body,
        f'{status}, ours={MARKER in body}',
    )
    status, _, body = fetch(f'{SITE}/data/no-such-file-{uuid.uuid4().hex[:8]}.json')
    check('a missing data file answers 404 too', status == 404, str(status))
    for old, new in (
        ('/privacy.html', '/privacy'),
        ('/terms.html', '/terms'),
        ('/pricing.html', '/pricing'),
        ('/changes.html', '/changes'),
    ):
        status, headers, _ = fetch(f'{SITE}{old}')
        check(
            f'{old} -> 301 {new}',
            status == 301 and headers.get('Location') == new,
            f'{status} {headers.get("Location")}',
        )
        status, _, _ = fetch(f'{SITE}{new}')
        check(f'{new} answers 200', status == 200, str(status))
    for path in ('/', '/map/', '/score-demo/api-docs.html', '/data/borough-extra.json'):
        status, _, _ = fetch(f'{SITE}{path}')
        check(f'{path} still answers 200', status == 200, str(status))
    status, headers, body = fetch(f'{SITE}/badge?postcode=SW11+1AA')
    check(
        '/badge still answers an SVG',
        status == 200 and body.lstrip().startswith(b'<svg'),
        f'{status} {headers.get("Content-Type")}',
    )
    check('the live function is the installer source', live_function_matches_source())
    ok = all(results)
    print(f'{"PASS" if ok else "FAIL"}: {sum(results)} of {len(results)}')
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
