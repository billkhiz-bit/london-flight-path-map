"""
One-shot installer for the CloudFront `rewrite-index` function.

What it does
============
1. Creates (or updates) a CloudFront Function whose code rewrites any
   URI that ends in `/` or has no file extension to append `index.html`.
2. Publishes the function to the LIVE stage.
3. Reads the EGSSPJKLFL33M distribution config.
4. Attaches the function to the default cache behaviour's
   viewer-request event if not already attached.
5. Updates the distribution and waits for it to deploy.

Idempotency: each step checks current state first, so re-running this
script is safe, second run is a no-op.

Why this matters
================
Without this rewrite, a request to `https://.../score-demo/` returns
the S3 REST endpoint's "directory listing not allowed" XML 403, the
Access Denied page. CloudFront only auto-resolves `index.html` at the
root, not in subdirectories. The function fixes this for all URLs.

Pre-requisites
==============
- AWS_PROFILE=flightmap configured (same profile used by sam deploy).
- The flightmap-dev IAM user must have the CloudFront Functions
  permissions in backend/iam-policy.json (Sid: CloudFrontFunctions).
  If you haven't applied the policy update yet, this script will
  fail with AccessDenied early, apply the policy and re-run.

Usage
=====
    AWS_PROFILE=flightmap python scripts/install_cloudfront_index_rewrite.py

Run-time
========
~3-7 minutes (the bottleneck is CloudFront propagation, not the API
calls).
"""

import json
import sys
import time

DISTRIBUTION_ID = 'EGSSPJKLFL33M'
FUNCTION_NAME = 'sky-score-rewrite-index'
# CloudFront caps Comment at 64 chars, keep it terse.
FUNCTION_COMMENT = 'Append index.html to subdir URIs (Sky Score)'
FUNCTION_CODE = """function handler(event) {
    var request = event.request;
    var uri = request.uri;
    if (uri.endsWith('/')) {
        request.uri = uri + 'index.html';
    } else if (uri.lastIndexOf('.') === -1) {
        request.uri = uri + '/index.html';
    }
    return request;
}
"""


def main():
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print('Missing boto3. Install with: pip install boto3')
        sys.exit(1)

    cf = boto3.client('cloudfront')

    # ----- Step 1: create or update the function -----
    print('Step 1/5: ensuring CloudFront Function exists ...')
    function_etag = upsert_function(cf, ClientError)

    # ----- Step 2: publish the function (LIVE stage) -----
    print('Step 2/5: publishing function to LIVE stage ...')
    publish_function(cf, function_etag, ClientError)

    # ----- Step 3: read distribution config -----
    print('Step 3/5: reading distribution config ...')
    cfg_response = cf.get_distribution_config(Id=DISTRIBUTION_ID)
    distribution_config = cfg_response['DistributionConfig']
    distribution_etag = cfg_response['ETag']

    # ----- Step 4: attach function if not already attached -----
    print('Step 4/5: attaching function to default cache behaviour ...')
    function_arn = describe_function(cf)['FunctionSummary']['FunctionMetadata']['FunctionARN']
    needs_update, distribution_config = ensure_function_associated(
        distribution_config, function_arn,
    )

    if not needs_update:
        print(' Function is already associated; no distribution update needed.')
        print_summary_and_test()
        return

    # ----- Step 5: push the updated config -----
    print('Step 5/5: updating distribution (this is the slow step) ...')
    cf.update_distribution(
        Id=DISTRIBUTION_ID,
        IfMatch=distribution_etag,
        DistributionConfig=distribution_config,
    )
    print(' Update submitted. Waiting for distribution to redeploy '
          '(~3-5 min, polls every 30s) ...')
    wait_for_deployment(cf)
    print_summary_and_test()


def upsert_function(cf, ClientError):
    """Create the function if missing; otherwise update its code in DEVELOPMENT.
    Returns the ETag for the (now-current) DEVELOPMENT version."""
    try:
        described = cf.describe_function(Name=FUNCTION_NAME)
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'NoSuchFunctionExists':
            created = cf.create_function(
                Name=FUNCTION_NAME,
                FunctionConfig={'Comment': FUNCTION_COMMENT,
                                'Runtime': 'cloudfront-js-2.0'},
                FunctionCode=FUNCTION_CODE.encode(),
            )
            print(f' Created function {FUNCTION_NAME}.')
            return created['ETag']
        raise

    print(f' Function {FUNCTION_NAME} already exists; '
          'updating DEVELOPMENT code in case it has drifted ...')
    updated = cf.update_function(
        Name=FUNCTION_NAME,
        IfMatch=described['ETag'],
        FunctionConfig={'Comment': FUNCTION_COMMENT,
                        'Runtime': 'cloudfront-js-2.0'},
        FunctionCode=FUNCTION_CODE.encode(),
    )
    return updated['ETag']


def publish_function(cf, etag, ClientError):
    try:
        cf.publish_function(Name=FUNCTION_NAME, IfMatch=etag)
        print(' Function published to LIVE.')
    except ClientError as exc:
        # InvalidIfMatchVersion happens when the function is already
        # published at this code revision, safe to ignore.
        code = exc.response.get('Error', {}).get('Code', '')
        if code == 'InvalidIfMatchVersion':
            print(' Function already at LIVE for this code revision.')
        else:
            raise


def describe_function(cf):
    return cf.describe_function(Name=FUNCTION_NAME, Stage='LIVE')


def ensure_function_associated(distribution_config, function_arn):
    """Mutate `distribution_config` in place to add the function association
    on the default cache behaviour. Returns (needs_update, config)."""
    behaviour = distribution_config['DefaultCacheBehavior']
    associations = behaviour.setdefault(
        'FunctionAssociations',
        {'Quantity': 0, 'Items': []},
    )
    items = associations.get('Items') or []

    for item in items:
        if (item.get('EventType') == 'viewer-request'
                and item.get('FunctionARN') == function_arn):
            return False, distribution_config

    # Either no viewer-request association, or it's pointing at a
    # different function. Replace any viewer-request entry with ours.
    items = [it for it in items if it.get('EventType') != 'viewer-request']
    items.append({'FunctionARN': function_arn, 'EventType': 'viewer-request'})
    associations['Items'] = items
    associations['Quantity'] = len(items)
    return True, distribution_config


def wait_for_deployment(cf):
    """Poll get-distribution every 30s until Status is Deployed."""
    while True:
        time.sleep(30)
        resp = cf.get_distribution(Id=DISTRIBUTION_ID)
        status = resp['Distribution']['Status']
        print(f' distribution status: {status}')
        if status == 'Deployed':
            return


def print_summary_and_test():
    print('')
    print('Done. CloudFront Function attached to default cache behaviour.')
    print('Test with these URLs (all should now return HTTP 200):')
    print(' https://d1oe4ftwutjpf.cloudfront.net/score-demo/')
    print(' https://d1oe4ftwutjpf.cloudfront.net/score-demo')
    print(' https://d1oe4ftwutjpf.cloudfront.net/prototype/')
    print(' https://d1oe4ftwutjpf.cloudfront.net/prototype')


if __name__ == '__main__':
    main()
