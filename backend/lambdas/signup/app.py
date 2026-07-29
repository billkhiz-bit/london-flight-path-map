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
  - API Gateway per-route throttle, 1 RPS / 5 burst (template.yaml).
    NOTE this is a stage-wide bucket shared by ALL callers, not per-IP —
    it bounds total signup volume, so it does not stop one determined
    client from consuming the whole allowance. Per-IP limiting would
    need WAF (see below).
  - One key per email (idempotent, duplicate signups return a "key
    already issued" error; we cannot re-show the key after creation)
  - The downstream UsagePlan caps each issued key at 100 req/month,
    which is 10,000 scores/month because a /v1/score/batch request
    carries up to 100 queries and still counts as one request

If this becomes a vector, the next layer is reCAPTCHA / hCaptcha on the
form, then WAF rules. Not worth adding pre-emptively.

Prompt-injection / IDOR risk is nil, the only DB write is keyed by
email and the only data read out is the SignupTable. No user-supplied
identifier is reflected in a response.
"""

import json
import logging
import os
import re
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Config -------------------------------------------------------------

AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-2')
# Usage plan resolved at runtime by name to avoid a CloudFormation
# circular dependency (SignupFunction → ScoreFreeUsagePlan → FlightMapApi
# → SignupFunction). Cached after first resolution per warm container.
USAGE_PLAN_NAME = os.environ.get('USAGE_PLAN_NAME', 'SkyScoreFreeTier')
SIGNUPS_TABLE = os.environ.get('SIGNUPS_TABLE', 'london-flight-map-signups')
KEY_NAME_PREFIX = 'SkyScoreUserKey-'
# Tag applied to every key created by this Lambda (audit N-Code-1).
# IAM policy on apigateway:DELETE has a matching tag-condition so a
# compromised signup Lambda cannot delete keys it did not create.
KEY_TAG_KEY = 'CreatedBy'
KEY_TAG_VALUE = 'SignupLambda'

_usage_plan_id_cache = None

# Pragmatic email regex, RFC 5322 compliance is overkill for a signup
# form; this catches the common shape and rejects obvious garbage. The
# real validation is "did the user copy-paste an email they actually
# read". We're not sending email so we don't need deliverability.
EMAIL_PATTERN = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')

# Origins allowed to call the signup endpoint from a browser. Locked
# down from '*' (audit N-Sec-4): the form lives on skyscore.co.uk and
# the legacy CloudFront URL only. Server-side abuse isn't gated by
# CORS but the per-route APIGW throttle handles that case.
ALLOWED_ORIGINS = {
    'https://skyscore.co.uk',
    'https://www.skyscore.co.uk',
    'https://d1oe4ftwutjpf.cloudfront.net',
}


def _origin_for_request(event):
    """Echo the request Origin if it's in the allow-list, else fall back
    to the canonical site. Returning a single specific origin (not '*')
    is required when CORS responses might also carry credentials in
    future and is best-practice regardless."""
    headers = event.get('headers') or {}
    origin = headers.get('Origin') or headers.get('origin') or ''
    if origin in ALLOWED_ORIGINS:
        return origin
    return 'https://skyscore.co.uk'


def cors_headers(event):
    return {
        'Access-Control-Allow-Origin': _origin_for_request(event),
        'Access-Control-Allow-Methods': 'POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '86400',
        'Vary': 'Origin',
    }


apigw = boto3.client('apigateway', region_name=AWS_REGION)
ddb = boto3.client('dynamodb', region_name=AWS_REGION)


# --- Helpers ------------------------------------------------------------


def response(status, body, event=None):
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', **cors_headers(event or {})},
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
            # createdAt stays projected even though the 409 no longer returns
            # it: get_item omits Item entirely when none of the projected
            # attributes exist, so projecting both keeps the "has this email
            # signed up?" check true for any row shape. Narrowing this to
            # keyId alone would risk a second key for a row missing keyId.
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
        # Tag-based IAM scope-down (audit N-Code-1). The IAM Condition
        # on apigateway:DELETE matches this tag, so this Lambda can
        # only delete keys it created — not arbitrary keys in the account.
        tags={KEY_TAG_KEY: KEY_TAG_VALUE},
    )
    key_id = created['id']
    key_value = created['value']

    # Link to the usage plan immediately, without this the key works at
    # API Gateway auth but gets no quota / throttle assignment.
    try:
        apigw.create_usage_plan_key(
            usagePlanId=usage_plan_id,
            keyId=key_id,
            keyType='API_KEY',
        )
    except Exception:
        # The key above already exists and is ENABLED. Without this rollback
        # the exception unwinds to handle_post, which discards key_id and
        # returns 503, leaving the key in the account forever. Not an auth
        # bypass (an unattached key fails the usage-plan check with
        # InvalidKeyParameter and gets a 403) but every leak erodes the
        # per-account 10,000-key quota. Catch Exception rather than just
        # ClientError: a ParamValidationError or a connection failure leaks
        # the key just as permanently. Re-raise so the caller still sees the
        # original error; _safe_revoke_orphan_key swallows ClientErrors of
        # its own so the rollback does not mask it.
        logger.info('usage-plan link failed; revoking orphan key %s', key_id)
        _safe_revoke_orphan_key(key_id)
        raise

    return key_id, key_value


def record_signup(email, name, key_id):
    """Audit-log the signup. Email is the partition key (one per email)."""
    ddb.put_item(
        TableName=SIGNUPS_TABLE,
        Item={
            'email': {'S': email},
            'name': {'S': name or ''},
            'keyId': {'S': key_id},
            'createdAt': {'S': datetime.now(UTC).isoformat()},
        },
        # Idempotency: fail if the email already exists. Caller checked
        # above but a race is possible between get_item and put_item.
        ConditionExpression='attribute_not_exists(email)',
    )


# --- Handler ------------------------------------------------------------


def handle_options(event):
    return {'statusCode': 200, 'headers': cors_headers(event), 'body': ''}


def _safe_revoke_orphan_key(key_id):
    r"""Best-effort delete of a just-created key during a race rollback.

    Belt-and-braces guard alongside the IAM tag-condition (audit N-Code-1):
    even though IAM only allows DELETE on tagged keys, we additionally
    verify by name-prefix that this is a key we created. Catches any
    future code path that might pass an arbitrary keyId by mistake.

    Audit N-Code-7: failures here are logged with a [SIGNUP_ORPHAN_KEY]
    structured prefix at ERROR level so they're alarm-able via a
    CloudWatch Logs Insights query like:
      fields @timestamp, @message
      | filter @message like /\[SIGNUP_ORPHAN_KEY\]/
    Each failure represents a leaked APIGW key that erodes the per-account
    10,000-key quota over time. Set up a CloudWatch metric filter on the
    above query and alarm on count > 0 over a rolling window.
    """
    # Catch Exception, not just ClientError. Both call sites invoke this
    # helper from inside an `except` block and then re-raise the ORIGINAL
    # error; a non-ClientError escaping from here (a botocore
    # EndpointConnectionError, say) would replace that original error and
    # downgrade handle_post's deliberate 503 to a bare 500.
    try:
        info = apigw.get_api_key(apiKey=key_id, includeValue=False)
    except Exception as get_err:
        logger.error('[SIGNUP_ORPHAN_KEY] lookup-failed keyId=%s err=%r', key_id, get_err)
        return
    key_name = info.get('name', '')
    if not key_name.startswith(KEY_NAME_PREFIX):
        logger.error('[SIGNUP_ORPHAN_KEY] refusing-non-prefix keyId=%s name=%r', key_id, key_name)
        return
    try:
        apigw.delete_api_key(apiKey=key_id)
    except Exception as revoke_err:
        # Same reasoning as the lookup above: never let a rollback failure
        # displace the original error the caller is about to re-raise.
        logger.error('[SIGNUP_ORPHAN_KEY] revoke-failed keyId=%s err=%r', key_id, revoke_err)


def handle_post(event):
    body = parse_body(event)
    if body is None:
        return response(400, {'error': 'Invalid or missing JSON body.'}, event)

    email = (body.get('email') or '').strip().lower()
    name = (body.get('name') or '').strip()

    if not email or not EMAIL_PATTERN.match(email):
        return response(
            400,
            {
                'error': 'Provide a valid email address.',
                'example': {'email': 'you@example.com', 'name': 'optional'},
            },
            event,
        )

    if len(email) > 254 or len(name) > 200:
        return response(400, {'error': 'Email or name exceeds maximum length.'}, event)

    # One key per email. If they already signed up, surface that with a
    # clear message, we cannot re-show the key (APIGW only returns the
    # value at creation time, not on subsequent reads).
    # createdAt is deliberately withheld from this body: /v1/signup is
    # unauthenticated, so anyone who guesses an address would otherwise
    # learn when its owner registered. It stays on the row for support.
    existing = get_existing_signup(email)
    if existing:
        return response(
            409,
            {
                'error': 'This email has already signed up.',
                'note': (
                    'A new key cannot be re-issued via this endpoint. '
                    'Contact support to revoke and re-issue if the original '
                    'key has been lost.'
                ),
            },
            event,
        )

    try:
        key_id, key_value = create_api_key(email, name)
    except ClientError as e:
        # Most common failure: limit on number of API keys per account.
        # Surface the specific code so we can debug from logs.
        return response(
            503,
            {
                'error': 'Could not create API key. Please try again later.',
                'code': e.response.get('Error', {}).get('Code', 'Unknown'),
            },
            event,
        )

    try:
        record_signup(email, name, key_id)
    except ClientError as e:
        code = e.response.get('Error', {}).get('Code', '')
        if code == 'ConditionalCheckFailedException':
            # Race detected, another in-flight signup wrote first. Revoke
            # the key we just created and return 409. Log the keyId only:
            # raw emails must stay out of CloudWatch (the privacy policy
            # promises deletion on request, and log copies would outlive it).
            logger.info('signup race detected; revoking orphan key %s', key_id)
            _safe_revoke_orphan_key(key_id)
            return response(
                409,
                {
                    'error': 'This email has already signed up.',
                    'note': (
                        'Concurrent signup races are detected and rolled '
                        'back. Try again or contact support if you need '
                        'a re-issue.'
                    ),
                },
                event,
            )
        # Other DDB errors: still return 201 (the key works regardless)
        # but log server-side so we can find the orphaned audit row. The
        # keyId is enough to recover the email from APIGW key metadata;
        # never log the raw address itself.
        logger.warning('signup created in APIGW but DDB write failed: keyId=%s code=%s', key_id, code)

    return response(
        201,
        {
            'apiKey': key_value,
            'keyId': key_id,
            'usagePlan': 'SkyScoreFreeTier',
            # Mirrors ScoreFreeUsagePlan in backend/template.yaml, which is the
            # source of truth. Hardcoded rather than read from the plan: fetching
            # it would need apigateway:GetUsagePlan and a second API call on the
            # signup path, to report numbers that change roughly never. Update
            # both together. batchMultiplier is stated explicitly because the
            # quota meters requests while the product sells scores.
            'limits': {
                'monthlyQuota': 100,
                'burstLimit': 5,
                'sustainedRateLimit': 1,
                'batchMultiplier': 100,
                'monthlyScoreCeiling': 10000,
            },
            'note': (
                'Save this key now. It is shown ONCE and cannot be '
                'retrieved after this response. Pass it as the X-Api-Key '
                'header on /v1/score requests.'
            ),
            'docs': 'https://skyscore.co.uk/score-demo/api-docs.html',
        },
        event,
    )


def handler(event, context):
    method = (event.get('httpMethod') or 'POST').upper()
    try:
        if method == 'OPTIONS':
            return handle_options(event)
        if method == 'POST':
            return handle_post(event)
        return response(405, {'error': f'Method {method} not allowed.'}, event)
    except Exception as exc:
        # Top-level guard, never let an unhandled exception escape the
        # CORS-headered envelope. Log to CloudWatch for postmortem.
        logger.exception('unhandled exception in signup handler: %s', exc)
        return response(500, {'error': 'Internal server error.'}, event)
