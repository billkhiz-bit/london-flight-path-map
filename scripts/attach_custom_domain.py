"""
One-shot script to attach a custom domain (skyscore.co.uk + www) to the
existing CloudFront distribution EGSSPJKLFL33M.

Pre-requisite: an ACM certificate in us-east-1 covering both names,
status `Issued`. The user requests this via the AWS Console — see
the runbook in the README of this commit. Once the cert ARN is known,
run this script to wire it up.

What it does:
  1. Reads the current CloudFront distribution config + ETag
  2. Adds the two alternate domain names if not already present
  3. Attaches the ACM certificate
  4. Sets the SSL support method to SNI-only (cheapest, modern)
  5. Submits the update
  6. Polls until deployment completes (~3-5 min)

Idempotent: re-running with the same cert is a no-op.

Usage:
  AWS_PROFILE=flightmap python scripts/attach_custom_domain.py \
      --cert-arn arn:aws:acm:us-east-1:072674217857:certificate/abc-...

Pre-requisite IAM perms (already in flightmap-dev):
  - cloudfront:GetDistributionConfig
  - cloudfront:UpdateDistribution
  - cloudfront:GetDistribution
"""

import argparse
import sys
import time

DISTRIBUTION_ID = 'EGSSPJKLFL33M'
ALT_DOMAIN_NAMES = ['skyscore.co.uk', 'www.skyscore.co.uk']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--cert-arn', required=True,
        help='ARN of the ACM certificate (must be in us-east-1, status=Issued).',
    )
    args = parser.parse_args()

    if not args.cert_arn.startswith('arn:aws:acm:us-east-1:'):
        print('ERROR: cert ARN must be from us-east-1 — CloudFront only accepts')
        print('certs from that region. The ARN you passed is from elsewhere.')
        sys.exit(1)

    try:
        import boto3

        # Imported for the availability check only: a botocore too old to
        # expose ClientError should fail here, with the pip hint, rather than
        # part-way through a live CloudFront update.
        from botocore.exceptions import ClientError  # noqa: F401
    except ImportError:
        print('Missing boto3. pip install boto3')
        sys.exit(1)

    cf = boto3.client('cloudfront')

    print(f'Step 1/4: reading distribution {DISTRIBUTION_ID} config...')
    cfg_response = cf.get_distribution_config(Id=DISTRIBUTION_ID)
    config = cfg_response['DistributionConfig']
    etag = cfg_response['ETag']

    print('Step 2/4: applying alt-domain + cert changes...')
    needs_update = patch_aliases(config, ALT_DOMAIN_NAMES)
    needs_update |= patch_viewer_cert(config, args.cert_arn)

    if not needs_update:
        print('  Configuration already has the alt names + cert; nothing to do.')
        print_final_steps()
        return

    print('Step 3/4: submitting CloudFront update (this is the slow step)...')
    cf.update_distribution(
        Id=DISTRIBUTION_ID,
        IfMatch=etag,
        DistributionConfig=config,
    )

    print('Step 4/4: waiting for deployment (~3-5 min, polls every 30s)...')
    while True:
        time.sleep(30)
        r = cf.get_distribution(Id=DISTRIBUTION_ID)
        status = r['Distribution']['Status']
        print(f'    distribution status: {status}')
        if status == 'Deployed':
            break

    print('\nDone. CloudFront now accepts requests for:')
    for d in ALT_DOMAIN_NAMES:
        print(f'  https://{d}')
    print_final_steps()


def patch_aliases(config, names):
    """Mutate config to ensure all `names` are in the alternate domain list.
    Returns True if a change was made."""
    aliases = config.setdefault('Aliases', {'Quantity': 0, 'Items': []})
    items = aliases.get('Items') or []
    existing = set(items)
    added = False
    for name in names:
        if name not in existing:
            items.append(name)
            added = True
    aliases['Items'] = items
    aliases['Quantity'] = len(items)
    return added


def patch_viewer_cert(config, cert_arn):
    """Mutate ViewerCertificate to use the supplied ACM cert with SNI-only
    SSL support. Returns True if a change was made."""
    vc = config.setdefault('ViewerCertificate', {})
    if (vc.get('ACMCertificateArn') == cert_arn
            and vc.get('SSLSupportMethod') == 'sni-only'
            and vc.get('MinimumProtocolVersion') == 'TLSv1.2_2021'):
        return False
    vc.clear()
    vc['ACMCertificateArn'] = cert_arn
    vc['SSLSupportMethod'] = 'sni-only'
    vc['MinimumProtocolVersion'] = 'TLSv1.2_2021'
    vc['Certificate'] = cert_arn       # legacy field — older API expects it
    vc['CertificateSource'] = 'acm'    # legacy field
    return True


def print_final_steps():
    print('')
    print('User action remaining (Cloudflare DNS dashboard):')
    print('  1. Add CNAME: skyscore.co.uk     -> d1oe4ftwutjpf.cloudfront.net  (proxy OFF)')
    print('  2. Add CNAME: www.skyscore.co.uk -> d1oe4ftwutjpf.cloudfront.net  (proxy OFF)')
    print('')
    print('Cloudflare DNS supports CNAME flattening at the apex, so the @')
    print('CNAME works fine — no need for ALIAS or ANAME.')
    print('Verify in ~5 minutes:')
    print('  curl -sS -I https://skyscore.co.uk')
    print('  curl -sS -I https://www.skyscore.co.uk')


if __name__ == '__main__':
    main()
