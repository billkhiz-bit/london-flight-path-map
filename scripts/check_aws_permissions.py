#!/usr/bin/env python3
"""Probe what the deploy user can ACTUALLY do, and compare it to what
`backend/iam-policy.json` says it should be able to do.

WHY THIS EXISTS. On 2026-09-02 `CLAUDE.md` recorded that `logs:FilterLogEvents`,
`logs:GetLogEvents` and `logs:DescribeLogStreams` were allowed, "proven by
reading production output". On 2026-09-03 all three were denied, along with
`logs:DescribeLogGroups`. Nothing detected the change: the claim was written in
the present tense with no re-check attached, and it surfaced only because the
BLOCKING `log retention == privacy.html` stage happens to need the same verb.

**A permission is a timestamp, not a property.** `backend/iam-policy.json` is
the repo's record of the policy the deploy user SHOULD hold, and it is
aspirational - `load_nspl.py:170` and `load_defra_raster.py:295` both already
say in comments that appearing in that file "proves nothing", and until now
nothing compared it to the live account.

WHY IT IS A CAPABILITY PROBE AND NOT A POLICY DIFF. The obvious check is to
read the live policy and diff it. That is impossible from here:
`iam:ListAttachedUserPolicies` is itself denied. So this asks the only question
it can - "does the call work?" - which is also the better question, because it
measures the effective permission after every policy, boundary and SCP has been
applied, rather than one document's opinion of it.

THREE THINGS THAT MAKE THE CLASSIFICATION HONEST.

1. **`ResourceNotFoundException` means GRANTED, not denied.** Authorisation is
   evaluated before resource lookup, so an answer of "no such log group" proves
   the caller was allowed to ask. This is exactly the trap that produced the
   wrong reading from 2026-07-26 to 2026-09-02: the probe of the day used a
   log-group name that no longer existed - a Lambda's suffix changes whenever
   CloudFormation REPLACES the function - and read the resulting error as a
   permissions wall. Probes here deliberately name a group that CANNOT exist,
   so they never depend on resolving a real one.
2. **Denial is matched on the ERROR CODE, never on exit status or on any
   non-zero result.** Same reason.
3. **Bad or absent credentials abort the whole run as INCONCLUSIVE.** Every
   probe would return "denied" and the report would look like a catastrophic
   policy regression. `sts:GetCallerIdentity` is called first as the harness's
   own self-test.

WHAT IT DELIBERATELY DOES NOT COVER. The policy declares 110 actions and most
of them DELETE, CREATE or MUTATE something. Probing `cloudformation:DeleteStack`
to see whether it is allowed is not a check, it is an outage. Only read-only
actions with a harmless call are probed, and the summary reports how many of
the declared actions that IS, so the output cannot be mistaken for full
coverage - the "a list of mirrors that omits a mirror is worse than no list"
lesson this repo keeps relearning.

  python scripts/check_aws_permissions.py           # exit 1 on drift
  python scripts/check_aws_permissions.py --report  # always exit 0
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'backend' / 'iam-policy.json'
REGION = 'eu-west-2'
PROFILE = 'flightmap'

# A log group under the policy's own `london-flight-map-*` resource scope that
# cannot exist. Reaching ResourceNotFoundException on it proves the verb is
# allowed WITHOUT needing to resolve a real group - which is the step that
# produced a false "denied" reading for five weeks.
ABSENT_GROUP = '/aws/lambda/london-flight-map-permission-probe-does-not-exist'
ABSENT_STREAM = 'permission-probe-does-not-exist'
ABSENT_FUNCTION = 'london-flight-map-permission-probe-does-not-exist'

# Error codes that mean "you were allowed to ask; the thing was not there or
# the request was malformed". Authorisation precedes resource resolution and
# parameter validation, so every one of these proves the permission.
REACHED_THE_SERVICE = {
    'ResourceNotFoundException',
    'ResourceNotFound',
    'NoSuchEntity',
    'ValidationException',
    'ValidationError',
    'InvalidParameterException',
    'InvalidParameterValueException',
    'NotFoundException',
    'ResourceNotFoundFault',
}

DENIED = {
    'AccessDenied',
    'AccessDeniedException',
    'UnauthorizedOperation',
    'AuthorizationError',
}

# Credential problems, not policy problems. These abort the run.
NO_CREDENTIALS = {
    'InvalidClientTokenId',
    'ExpiredToken',
    'ExpiredTokenException',
    'SignatureDoesNotMatch',
    'UnrecognizedClientException',
    'AuthFailure',
}


def build_probes(session):
    """action -> a zero-side-effect call that exercises exactly that action.

    Every entry must be READ-ONLY. If you cannot probe an action without
    changing something, leave it out and let the summary report it as
    unprobed; a check that mutates state to test itself is worse than no check.
    """
    logs = session.client('logs', region_name=REGION)
    cw = session.client('cloudwatch', region_name=REGION)
    lam = session.client('lambda', region_name=REGION)
    cfn = session.client('cloudformation', region_name=REGION)
    ddb = session.client('dynamodb', region_name=REGION)
    s3 = session.client('s3', region_name=REGION)
    cfr = session.client('cloudfront')
    apigw = session.client('apigateway', region_name=REGION)

    return {
        # The observability cluster - the set that silently regressed.
        'logs:DescribeLogGroups': lambda: logs.describe_log_groups(limit=1),
        'logs:DescribeLogStreams': lambda: logs.describe_log_streams(
            logGroupName=ABSENT_GROUP, limit=1),
        'logs:FilterLogEvents': lambda: logs.filter_log_events(
            logGroupName=ABSENT_GROUP, limit=1),
        'logs:GetLogEvents': lambda: logs.get_log_events(
            logGroupName=ABSENT_GROUP, logStreamName=ABSENT_STREAM, limit=1),
        'cloudwatch:DescribeAlarms': lambda: cw.describe_alarms(MaxRecords=1),
        'cloudwatch:ListMetrics': lambda: cw.list_metrics(
            Namespace='AWS/Lambda'),
        'cloudwatch:DescribeAlarmsForMetric': (
            lambda: cw.describe_alarms_for_metric(
                MetricName='Errors', Namespace='AWS/Lambda')),
        'lambda:ListFunctions': lambda: lam.list_functions(MaxItems=1),
        'lambda:GetFunction': lambda: lam.get_function(
            FunctionName=ABSENT_FUNCTION),
        'logs:DescribeQueries': lambda: logs.describe_queries(maxResults=1),
        # Deliberately aimed at a group that cannot exist, so it exercises the
        # REACHED_THE_SERVICE branch - the piece of logic this whole file turns
        # on, and the one a run where everything is denied would otherwise
        # leave unproven. It errors before any query is started or billed.
        'logs:StartQuery': lambda: logs.start_query(
            logGroupName=ABSENT_GROUP, startTime=1, endTime=2,
            queryString='fields @message'),
        'cloudwatch:GetMetricStatistics': lambda: cw.get_metric_statistics(
            Namespace='AWS/Lambda', MetricName='Errors',
            StartTime='2026-01-01T00:00:00Z', EndTime='2026-01-02T00:00:00Z',
            Period=3600, Statistics=['Sum']),
        # The DEPLOY path. Added 2026-09-03 after the probe's first run proved
        # the policy had been replaced rather than extended: every one of these
        # was denied, which means no `make web-deploy-all`, no SAM deploy and
        # no CloudFront invalidation. A permissions check that watches only the
        # verbs that broke last time is a check aimed at the last incident.
        #
        # All READ-ONLY. The write verbs that actually ship a deploy
        # (s3:PutObject, cloudformation:UpdateStack, cloudfront:
        # CreateInvalidation) cannot be probed without performing them, so they
        # stay in the UNPROBED count - a read denial on the same service is the
        # available signal, not a proof.
        's3:ListBucket': lambda: s3.list_objects_v2(
            Bucket='london-flight-map-frontend', MaxKeys=1),
        'cloudfront:GetDistribution': lambda: cfr.get_distribution(
            Id='EGSSPJKLFL33M'),
        'apigateway:GET': lambda: apigw.get_rest_apis(limit=1),
        'dynamodb:GetItem': lambda: ddb.get_item(
            TableName='london-flight-map-postcodes', Key={'pc': {'S': 'N17SX'}}),
        # Anchors. These are expected to pass, and prove the harness itself
        # reaches AWS - so "everything denied" cannot be mistaken for a working
        # probe against a stripped policy.
        'cloudformation:DescribeStacks': lambda: cfn.describe_stacks(
            StackName='london-flight-map'),
        'dynamodb:DescribeTable': lambda: ddb.describe_table(
            TableName='london-flight-map-favourites'),
    }


def declared_actions():
    """Every action the policy FILE grants. The expectation side of the check.

    Read from a different holder than the thing being measured - the file is
    the claim, the live account is the fact - which is what makes this a real
    comparison rather than a check reading its own answer.
    """
    doc = json.loads(POLICY.read_text(encoding='utf-8'))
    out = set()
    for stmt in doc.get('Statement', []):
        if stmt.get('Effect') != 'Allow':
            continue
        act = stmt.get('Action')
        for a in ([act] if isinstance(act, str) else act or []):
            out.add(a)
    return out


def classify(call):
    """-> (state, detail). Never reads exit status; always the error CODE."""
    from botocore.exceptions import ClientError, NoCredentialsError
    try:
        call()
        return 'granted', ''
    except NoCredentialsError:
        return 'nocreds', 'no credentials resolved'
    except ClientError as exc:
        code = exc.response.get('Error', {}).get('Code', '')
        if code in DENIED:
            return 'denied', code
        if code in NO_CREDENTIALS:
            return 'nocreds', code
        if code in REACHED_THE_SERVICE:
            # Authorisation passed; the resource simply is not there.
            return 'granted', f'{code} (reached the service)'
        return 'error', code or type(exc).__name__
    except Exception as exc:  # noqa: BLE001 - report, never classify as denied
        return 'error', type(exc).__name__


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true',
                    help='always exit 0; print the state without failing')
    ap.add_argument('--profile', default=PROFILE)
    args = ap.parse_args()

    try:
        import boto3
    except ImportError:
        print('INCONCLUSIVE: boto3 is not installed, so nothing was probed.')
        print('  That is NOT the same as every permission being present.')
        return 0

    try:
        session = boto3.Session(profile_name=args.profile)
    except Exception as exc:  # noqa: BLE001
        print(f'INCONCLUSIVE: profile {args.profile!r} unusable ({exc}).')
        return 0

    # Self-test FIRST. Without it, bad credentials render every probe "denied"
    # and the report reads as a total policy wipe.
    sts = session.client('sts', region_name=REGION)
    state, detail = classify(sts.get_caller_identity)
    if state != 'granted':
        print(f'INCONCLUSIVE: sts:GetCallerIdentity did not succeed ({detail}).')
        print('  Credentials are unusable, so a "denied" from every probe would')
        print('  describe the credentials, not the policy. Nothing was measured.')
        return 0

    who = sts.get_caller_identity()['Arn']
    declared = declared_actions()
    probes = build_probes(session)

    print('AWS effective permissions vs backend/iam-policy.json')
    print('====================================================')
    print(f'  identity  {who}')
    print()

    drift, granted, errors, unprobed_declared = [], [], [], []
    for action in sorted(probes):
        if action not in declared:
            # Probeable but not claimed by the file. Report separately - a
            # live grant the file does not declare is drift in the other
            # direction and is worth seeing, but it is not a failure.
            continue
        state, detail = classify(probes[action])
        if state == 'nocreds':
            print(f'INCONCLUSIVE: credentials failed mid-run ({detail}).')
            return 0
        if state == 'denied':
            drift.append(action)
            print(f'  DENIED   {action}')
        elif state == 'granted':
            granted.append(action)
            print(f'  ok       {action}'
                  + (f'   [{detail}]' if detail else ''))
        else:
            errors.append((action, detail))
            print(f'  ERROR    {action}   {detail} (not classified)')

    probed = len(granted) + len(drift) + len(errors)

    # A FLOOR, for the same reason every other check here has one: a run that
    # measured nothing must not read as agreement.
    if probed == 0:
        print()
        print('FAIL: probed 0 actions, so nothing was compared. Either the')
        print('  probe table and the policy file share no actions, or the')
        print('  policy file could not be parsed.')
        return 1

    unprobed_declared = sorted(declared - set(probes))
    print()
    print(f'  probed    {probed} of {len(declared)} declared actions')
    print(f'  granted   {len(granted)}')
    print(f'  DENIED    {len(drift)}')
    if errors:
        print(f'  errors    {len(errors)} (unclassified, see above)')
    print(f'  UNPROBED  {len(unprobed_declared)} - destructive or stateful, so')
    print('            deliberately not exercised. This report says NOTHING')
    print('            about them; it is not full coverage of the policy.')

    if drift:
        print()
        print('FAIL: the policy file grants these and the live account does not.')
        for a in drift:
            print(f'  - {a}')
        print()
        print('  backend/iam-policy.json is a RECORD OF INTENT, not of fact. Apply')
        print('  the missing statements in the IAM console (the deploy user cannot')
        print('  grant itself IAM, and iam:ListAttachedUserPolicies is denied, so')
        print('  this probe is the only way to see the difference from here).')
        return 0 if args.report else 1

    print()
    print('OK: every safely-probeable declared action is live.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
