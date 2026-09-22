#!/usr/bin/env python3
"""Put the site on a CUSTOM response-headers policy: Permissions-Policy + X-Frame-Options DENY.

WHY. `EGSSPJKLFL33M` runs on the AWS MANAGED `SecurityHeadersPolicy`
(`67f7725c-6f97-4210-82d7-5512b31e9d03`), which cannot be edited and carries
no Permissions-Policy - so the header was never removed, it was never there
(measured 2026-09-08). The same policy sets `X-Frame-Options: SAMEORIGIN`
while every page's meta CSP claims `frame-ancestors 'none'`, which a meta tag
cannot deliver; there is not one <iframe> in the repo, so DENY is the honest
value and this header is the only thing actually refusing to be framed.

WHAT IT DOES NOT DO. No Content-Security-Policy header. The distribution has
one default behaviour for every page, a header CSP is enforced ALONGSIDE each
page's meta CSP, and `prototype/index.html` loads Three.js from jsdelivr under
its own policy - a distribution-wide CSP header blanks it. Verified live on
2026-09-08. `report-uri` is therefore out too (header-only directive, no
collector exists either).

WHAT IT DOES. Creates `sky-score-security-headers` with the managed policy's
five headers reproduced (so nothing else changes), FrameOptions raised to
DENY, and Permissions-Policy added as a custom header; then points every
behaviour that is on the managed policy OR ON NONE at the new one - the
/badge behaviour was found carrying no policy at all (see needs_repoint).

PERMISSIONS. `cloudfront:CreateResponseHeadersPolicy`, `Get...`, `List...`
and `Update...` were DENIED to flightmap-dev on 2026-09-08 and again on
2026-09-18 (probed). They are in `backend/iam-policy.json` under
`CloudFrontResponseHeadersPolicy`; until that is pasted into the console this
script's --plan works and --apply fails on the first call, harmlessly.
`scripts/check_aws_permissions.py` probes `ListResponseHeadersPolicies`, so
the paste landing is visible from here.

USAGE
    python scripts/cloudfront_security_headers.py --plan     # print, touch nothing
    python scripts/cloudfront_security_headers.py --apply    # create policy, UpdateDistribution, wait
    python scripts/cloudfront_security_headers.py --verify   # three URLs at the origin

AFTER --verify PASSES: move `permissions-policy` out of PENDING_HEADERS in
scripts/check_deploy_drift.sh and into its guarded list, or that gate goes
red on the header's presence (by design - the exemption cannot rot).
"""

import argparse
import sys
import urllib.error
import urllib.request

import boto3

DISTRIBUTION_ID = 'EGSSPJKLFL33M'
MANAGED_SECURITY_HEADERS_POLICY = '67f7725c-6f97-4210-82d7-5512b31e9d03'
POLICY_NAME = 'sky-score-security-headers'
SITE = 'https://skyscore.co.uk'

# Every feature the site does not use, denied to every origin; geolocation
# kept for OUR origin only. `geolocation=(self)`, NOT `()`: "Score where I
# am" reaches GPS through `cap.Plugins.Geolocation`, and while the native
# build never loads from CloudFront the installed PWA does (OPERATIONS.md
# s3.2, which first prescribed `()` and corrected itself on 2026-09-08 -
# a grep for `navigator.geolocation` alone misses the Capacitor route).
# Alphabetical, so a diff of the live header against this constant is legible.
PERMISSIONS_POLICY = (
    'accelerometer=(), camera=(), geolocation=(self), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()'
)

# The managed SecurityHeadersPolicy, reproduced. Measured from the live
# response on 2026-09-18: X-XSS-Protection "1; mode=block", X-Frame-Options
# SAMEORIGIN, Referrer-Policy strict-origin-when-cross-origin,
# X-Content-Type-Options nosniff, Strict-Transport-Security max-age=31536000.
# Only FrameOptions changes; parity elsewhere is deliberate so this change is
# exactly two headers wide.
POLICY_CONFIG = {
    'Name': POLICY_NAME,
    'Comment': 'Managed SecurityHeadersPolicy + Permissions-Policy, X-Frame-Options DENY (2026-09-18)',
    'SecurityHeadersConfig': {
        'XSSProtection': {'Override': True, 'Protection': True, 'ModeBlock': True},
        'FrameOptions': {'Override': True, 'FrameOption': 'DENY'},
        'ReferrerPolicy': {'Override': True, 'ReferrerPolicy': 'strict-origin-when-cross-origin'},
        'ContentTypeOptions': {'Override': True},
        'StrictTransportSecurity': {
            'Override': True,
            'IncludeSubdomains': False,
            'Preload': False,
            'AccessControlMaxAgeSec': 31536000,
        },
    },
    'CustomHeadersConfig': {
        'Quantity': 1,
        'Items': [{'Header': 'Permissions-Policy', 'Value': PERMISSIONS_POLICY, 'Override': True}],
    },
}

# What --verify asserts at the origin, on every URL below.
EXPECTED = {
    'permissions-policy': PERMISSIONS_POLICY,
    'x-frame-options': 'DENY',
    'strict-transport-security': 'max-age=31536000',
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'strict-origin-when-cross-origin',
}
# index.html (default behaviour), the badge (its own behaviour, API origin),
# and the prototype - the page a CSP header would have broken, checked here
# so the ABSENCE of a CSP header is asserted too.
VERIFY_PATHS = ('/index.html', '/badge?postcode=SW11%201AA', '/prototype/index.html')

_CF = None


def cf():
    global _CF
    if _CF is None:
        _CF = boto3.client('cloudfront', region_name='us-east-1')
    return _CF


def existing_policy_id():
    """The custom policy's id if it already exists, else None. Re-runnable."""
    marker = None
    while True:
        kwargs = {'Type': 'custom'}
        if marker:
            kwargs['Marker'] = marker
        page = cf().list_response_headers_policies(**kwargs)['ResponseHeadersPolicyList']
        for item in page.get('Items', []):
            if item['ResponseHeadersPolicy']['ResponseHeadersPolicyConfig']['Name'] == POLICY_NAME:
                return item['ResponseHeadersPolicy']['Id']
        marker = page.get('NextMarker')
        if not marker:
            return None


def behaviours(cfg):
    yield 'default', cfg['DefaultCacheBehavior']
    for b in cfg.get('CacheBehaviors', {}).get('Items', []):
        yield b['PathPattern'], b


def needs_repoint(behaviour, new_id):
    """On the managed policy, or on NO policy - both get the custom one.

    The /badge behaviour (2026-09-17) was created with no response-headers
    policy at all, measured by --verify on 2026-09-18: the badge SVG answered
    on skyscore.co.uk with no HSTS and no X-Frame-Options. An SVG opened as a
    document runs script, and this one is served from our hostname, so it
    gets the same headers as a page. A behaviour already on the custom
    policy, or on some third policy set deliberately, is left alone.
    """
    cur = behaviour.get('ResponseHeadersPolicyId')
    # `new_id` is None under --plan before the IAM grant lands (the list call
    # is denied), and an ABSENT id is None too; the two must not compare equal
    # or the badge behaviour prints "leave" for exactly the wrong reason.
    if new_id is not None and cur == new_id:
        return False
    return cur in (None, '', MANAGED_SECURITY_HEADERS_POLICY)


def plan():
    d = cf().get_distribution_config(Id=DISTRIBUTION_ID)['DistributionConfig']
    pid = None
    try:
        pid = existing_policy_id()
        print(f'policy {POLICY_NAME}: {"exists, " + pid if pid else "will be created"}')
    except Exception as exc:  # noqa: BLE001 - the whole point is to report the denial
        print(f'policy {POLICY_NAME}: cannot list ({type(exc).__name__}) - IAM not yet pasted?')
    for name, b in behaviours(d):
        cur = b.get('ResponseHeadersPolicyId', '(none)')
        change = 'REPOINT' if needs_repoint(b, pid) else 'leave'
        print(f'  behaviour {name:<10} response headers policy {cur}  -> {change}')
    print(f'Permissions-Policy: {PERMISSIONS_POLICY}')
    return 0


def apply():
    pid = existing_policy_id()
    if pid is None:
        pid = cf().create_response_headers_policy(ResponseHeadersPolicyConfig=POLICY_CONFIG)['ResponseHeadersPolicy'][
            'Id'
        ]
        print(f'created {POLICY_NAME}: {pid}')
    else:
        print(f'{POLICY_NAME} already exists: {pid}')
    d = cf().get_distribution_config(Id=DISTRIBUTION_ID)
    cfg, etag = d['DistributionConfig'], d['ETag']
    changed = []
    for name, b in behaviours(cfg):
        if needs_repoint(b, pid):
            b['ResponseHeadersPolicyId'] = pid
            changed.append(name)
    if not changed:
        print('every behaviour already carries a custom policy; nothing to repoint (already applied?)')
        return 0
    cf().update_distribution(Id=DISTRIBUTION_ID, IfMatch=etag, DistributionConfig=cfg)
    print(f'repointed {", ".join(changed)}; waiting for Deployed (typically 3-6 minutes) ...')
    cf().get_waiter('distribution_deployed').wait(Id=DISTRIBUTION_ID)
    print('Deployed. Now run --verify.')
    return 0


def head(url):
    # GET, not HEAD: API Gateway has no HEAD on /badge (answers 403).
    req = urllib.request.Request(url, headers={'User-Agent': 'sky-score-header-check'})
    with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310 - fixed https URLs above
        return res.status, {k.lower(): v for k, v in res.headers.items()}


def verify():
    failures = 0
    for path in VERIFY_PATHS:
        url = SITE + path
        try:
            status, headers = head(url)
        except urllib.error.URLError as exc:
            print(f'FAIL {path}: {exc}')
            failures += 1
            continue
        problems = []
        if status != 200:
            problems.append(f'status {status}')
        for name, want in EXPECTED.items():
            got = headers.get(name)
            if got != want:
                problems.append(f'{name}={got!r} (want {want!r})')
        if 'content-security-policy' in headers:
            problems.append('a CSP HEADER is present - that blanks the prototype, remove it')
        if problems:
            failures += 1
            print(f'FAIL {path}: ' + '; '.join(problems))
        else:
            print(f'ok   {path}')
    if failures:
        return 1
    print('PASS: all three URLs carry the custom policy. Next: move permissions-policy out of')
    print('      PENDING_HEADERS in scripts/check_deploy_drift.sh into the guarded list.')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--plan', action='store_true')
    g.add_argument('--apply', action='store_true')
    g.add_argument('--verify', action='store_true')
    args = ap.parse_args()
    if args.plan:
        return plan()
    if args.apply:
        return apply()
    return verify()


if __name__ == '__main__':
    sys.exit(main())
