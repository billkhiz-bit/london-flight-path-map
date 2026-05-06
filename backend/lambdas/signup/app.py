"""
Sky Score self-service signup Lambda.

  POST /v1/signup
  Body: {"email": "user@example.com", "name": "Optional Display Name"}

Creates a fresh API Gateway API key, links it to the ScoreFreeUsagePlan,
records the signup in the signups DynamoDB table for audit, and returns
the key value ONCE in the response. The form is responsible for making
the user save the key (one-time view).

This endpoint is unauthenticated by design, friction-free signup is the
whole point. Abuse is bounded by:
  - Per-IP API Gateway throttle (configured in template.yaml)
  - One key per email (idempotent, duplicate signups return a "key
    already issued" error; we cannot re-show the key after creation)
  - The downstream UsagePlan caps each issued key at 1000 req/month

If this becomes a vector, the next layer is reCAPTCHA / hCaptcha on the
form, then WAF rules. Not worth adding pre-emptively.

Prompt-injection / IDOR risk is nil, the only DB write is keyed by
email and the only data read out is the SignupTable. No user-supplied
identifier is reflected in a response.
"""

import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import unquote

import boto3
from botocore.exceptions import ClientError

# --- Config -------------------------------------------------------------

AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-2')
# Usage plan resolved at runtime by name to avoid a CloudFormation
# circular dependency (SignupFunction → ScoreFreeUsagePlan → FlightMapApi
# → SignupFunction). Cached after first resolution per warm container.
USAGE_PLAN_NAME = os.environ.get('USAGE_PLAN_NAME', 'SkyScoreFreeTier')
SIGNUPS_TABLE = os.environ.get('SIGNUPS_TABLE', 'london-flight-map-signups')
KEY_NAME_PREFIX = 'SkyScoreUserKey-'

_usage_plan_id_cache = None

# Pragmatic email regex, RFC 5322 compliance is overkill for a signup
# form; this catches the common shape and rejects obvious garbage. The
# real validation is "did the user copy-paste an email they actually
# read". We're not sending email so we don't need deliverability.
EMAIL_PATTERN = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
}

apigw = boto3.client('apigateway', region_name=AWS_REGION)
ddb = boto3.client('dynamodb', region_name=AWS_REGION)


# --- Helpers ------------------------------------------------------------

def response(status, body):
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', **CORS_HEADERS},
        'body': json.dumps(body),
    }


def parse_body(event):
    """Return parsed JSON body or None if malformed."""
    raw = event.get('body') or ''
    if event.get('isBase64Encoded'):
        import base64
        try:
            raw = base64.b64decode(raw).decode()
        except (ValueError, UnicodeDecodeError):
            return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def get_existing_signup(email):
    """Return the existing signup row if this email has already signed up.

    Uses ConsistentRead=True so a second signup hitting a different Lambda
    container shortly after the first sees the prior write, eventual
    consistency would otherwise let the same email sign up twice during
    the propagation window.
    """
    try:
        result = ddb.get_item(
            TableName=SIGNUPS_TABLE,
            Key={'email': {'S': email}},
            ConsistentRead=True,
            ProjectionExpression='createdAt, keyId',
        )
    except ClientError:
        return None
    return result.get('Item')


def resolve_usage_plan_id():
    """Look up the SkyScoreFreeTier usage plan ID at runtime. Cached
    per warm container; first invocation per cold start makes one API call.

    Avoids a CloudFormation circular dependency that would arise from
    referencing ScoreFreeUsagePlan via !Ref in this Lambda's environment.
    """
    global _usage_plan_id_cache
    if _usage_plan_id_cache:
        return _usage_plan_id_cache

    paginator = apigw.get_paginator('get_usage_plans')
    for page in paginator.paginate():
        for plan in page.get('items', []):
            if plan.get('name') == USAGE_PLAN_NAME:
                _usage_plan_id_cache = plan['id']
                return _usage_plan_id_cache
    raise RuntimeError(f'Usage plan {USAGE_PLAN_NAME!r} not found.')


def create_api_key(email, name):
    """Create a new APIGW API key and link it to the free-tier UsagePlan.

    Returns (key_id, key_value) on success or raises on failure.
    """
    usage_plan_id = resolve_usage_plan_id()

    safe_email = email.replace('@', '_at_').replace('.', '_')
    key_name = f'{KEY_NAME_PREFIX}{safe_email}'
    description = f'Sky Score self-service signup. Email: {email}'
    if name:
        description += f'. Name: {name[:80]}'

    created = apigw.create_api_key(
        name=key_name,
        description=description,
        enabled=True,
    )
    key_id = created['id']
    key_value = created['value']

    # Link to the usage plan immediately, without this the key works at
    # API Gateway auth but gets no quota / throttle assignment.
    apigw.create_usage_plan_key(
        usagePlanId=usage_plan_id,
        keyId=key_id,
        keyType='API_KEY',
    )

    return key_id, key_value


def record_signup(email, name, key_id):
    """Audit-log the signup. Email is the partition key (one per email)."""
    ddb.put_item(
        TableName=SIGNUPS_TABLE,
        Item={
            'email': {'S': email},
            'name': {'S': name or ''},
            'keyId': {'S': key_id},
            'createdAt': {'S': datetime.now(timezone.utc).isoformat()},
        },
        # Idempotency: fail if the email already exists. Caller checked
        # above but a race is possible between get_item and put_item.
        ConditionExpression='attribute_not_exists(email)',
    )


# --- Handler ------------------------------------------------------------

def handle_options():
    return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': ''}


def handle_post(event):
    body = parse_body(event)
    if body is None:
        return response(400, {'error': 'Invalid or missing JSON body.'})

    email = (body.get('email') or '').strip().lower()
    name = (body.get('name') or '').strip()

    if not email or not EMAIL_PATTERN.match(email):
        return response(400, {
            'error': 'Provide a valid email address.',
            'example': {'email': 'you@example.com', 'name': 'optional'},
        })

    if len(email) > 254 or len(name) > 200:
        return response(400, {'error': 'Email or name exceeds maximum length.'})

    # One key per email. If they already signed up, surface that with a
    # clear message, we cannot re-show the key (APIGW only returns the
    # value at creation time, not on subsequent reads).
    existing = get_existing_signup(email)
    if existing:
        return response(409, {
            'error': 'This email has already signed up.',
            'note': ('A new key cannot be re-issued via this endpoint. '
                     'Contact support to revoke and re-issue if the original '
                     'key has been lost.'),
            'createdAt': existing.get('createdAt', {}).get('S'),
        })

    try:
        key_id, key_value = create_api_key(email, name)
    except ClientError as e:
        # Most common failure: limit on number of API keys per account.
        # Surface the specific code so we can debug from logs.
        return response(503, {
            'error': 'Could not create API key. Please try again later.',
            'code': e.response.get('Error', {}).get('Code', 'Unknown'),
        })

    try:
        record_signup(email, name, key_id)
    except ClientError as e:
        code = e.response.get('Error', {}).get('Code', '')
        if code == 'ConditionalCheckFailedException':
            # Race detected, another in-flight signup wrote first. Revoke
            # the key we just created (best-effort) and return 409 so the
            # caller learns the email already had a signup.
            print(f'INFO signup race detected for {email}; revoking orphan key {key_id}')
            try:
                apigw.delete_api_key(apiKey=key_id)
            except ClientError as revoke_err:
                print(f'WARN failed to revoke orphan key {key_id}: '
                      f'{revoke_err.response.get("Error",{}).get("Code")}')
            return response(409, {
                'error': 'This email has already signed up.',
                'note': ('Concurrent signup races are detected and rolled '
                         'back. Try again or contact support if you need '
                         'a re-issue.'),
            })
        # Other DDB errors: still return 201 (the key works regardless)
        # but log server-side so we can find the orphaned audit row.
        print(f'WARN signup created in APIGW but DDB write failed: '
              f'email={email} keyId={key_id} code={code}')

    return response(201, {
        'apiKey': key_value,
        'keyId': key_id,
        'usagePlan': 'SkyScoreFreeTier',
        'limits': {
            'monthlyQuota': 1000,
            'burstLimit': 5,
            'sustainedRateLimit': 2,
        },
        'note': ('Save this key now. It is shown ONCE and cannot be '
                 'retrieved after this response. Pass it as the X-Api-Key '
                 'header on /v1/score requests.'),
        'docs': 'https://d1oe4ftwutjpf.cloudfront.net/score-demo/api-docs.html',
    })


def handler(event, context):
    method = (event.get('httpMethod') or 'POST').upper()
    try:
        if method == 'OPTIONS':
            return handle_options()
        if method == 'POST':
            return handle_post(event)
        return response(405, {'error': f'Method {method} not allowed.'})
    except Exception as exc:
        # Top-level guard, never let an unhandled exception escape the
        # CORS-headered envelope. Log to CloudWatch for postmortem.
        print(f'ERROR unhandled exception in signup handler: {type(exc).__name__}: {exc}')
        return response(500, {'error': 'Internal server error.'})
