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
  - The downstream UsagePlan caps each issued key at 10,000 req/month,
    which is 10,000 SCORES/month: /v1/score/batch is denied per-method
    for this plan (RateLimit 0), so a request cannot carry 100 queries
    and requests and scores are finally the same unit. Before
    2026-08-21 the cap was 100 requests for the same 10,000 scores,
    which an integrator could exhaust in an afternoon.

If this becomes a vector, the next layer is reCAPTCHA / hCaptcha on the
form, then WAF rules. Not worth adding pre-emptively.

Prompt-injection / IDOR risk is nil, the only DB write is keyed by
email and the only data read out is the SignupTable. No user-supplied
identifier is reflected in a response.

VERIFICATION FIRST (audit I17, option A, built 2026-09-15, behind a flag).
With SIGNUP_VERIFY=on nothing above happens on the POST. The address gets a
PENDING row (its own table, 24 h TTL, random token) and ONE email with a
confirm link, and every POST answers the same 201 whatever the register
holds - so a stranger can no longer subscribe your address (privacy.html
says consent is given by the person whose address it is), cannot lock you
out of a later API signup by taking your row first, and cannot learn from
the reply whether an address holds a key. The signup itself - key minting,
the consumer list, the existing-row rules - runs UNCHANGED when the link is
clicked (GET /v1/signup/confirm?token=), which renders a small HTML page
from this Lambda rather than a JSON body, because a person arrives there
from an email client. The flag defaults to OFF: with it on and the SES
identity unverified, every signup would 503, so the flip is a runbook step
(OPERATIONS.md) after the domain is verified and the account is out of the
SES sandbox - not a deploy.
"""

import base64
import hashlib
import html
import json
import logging
import os
import re
import secrets
import time
from datetime import UTC, datetime

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Config -------------------------------------------------------------

AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-2')
# Usage plan resolved at runtime by name to avoid a CloudFormation
# circular dependency (SignupFunction → ScoreFreeUsagePlan → FlightMapApi
# → SignupFunction). Cached after first resolution per warm container.
USAGE_PLAN_NAME = os.environ.get('USAGE_PLAN_NAME', 'SkyScoreFreeTier')
SIGNUPS_TABLE = os.environ.get('SIGNUPS_TABLE', 'london-flight-map-signups')
# I17: verification-first signup. OFF unless the template says otherwise; see
# the module docstring for why the flip is a runbook step, not a deploy.
SIGNUP_VERIFY = os.environ.get('SIGNUP_VERIFY', 'off').strip().lower() == 'on'
PENDING_TABLE = os.environ.get('PENDING_TABLE', 'london-flight-map-signup-pending')
SES_FROM = os.environ.get('SES_FROM', 'Sky Score <noreply@skyscore.co.uk>')
# Replies reach a person (2026-11-22, after Bill's Hotmail put every confirmation in Junk): a no-reply address with
# nowhere to answer reads as bulk mail to Microsoft's filters. The privacy page's published contact; the From and its
# DKIM/DMARC alignment are unchanged.
SES_REPLY_TO = 'Sky Score <support@skyscore.co.uk>'
# NEWS BY EMAIL (Bill, 2026-11-22: the front page's strip, mock-up claude.ai/artifact/XFr75aGp5ziqBEeFFNCCmu v6; it
# grew out of the area updates list built 2026-11-10, which it replaces). Sky Score news, AT MOST ONE EMAIL A MONTH, and
# only after the emailed link is confirmed (his P11 answers). News only since news-v2 (Bill, 2026-11-22): the strip's
# postcode box is gone, the request is source 'updates' with no postcode, and one sent anyway is dropped.
# It lives in ITS OWN table, not the signups table: that table holds one row per address under rules that refuse a
# second purpose (an address on the score-change list is told to contact support for an API key), and a list member
# must not trip them. Items in MAIL_TABLE, all keyed by `pk`:
#   updates#<email>   a member: the consent wording, when consented, its unsubscribe token (a news-v1 member may also
#                     hold the postcode it ticked; nothing writes one since news-v2)
#   unsub#<token>     the token in every email's unsubscribe link -> email (the link never carries the address)
#   suppress#<email>  the do-not-email list: written on unsubscribe and read before ANY send, the confirmation email
#                     included (privacy s2a: "so we never write to it again"; code review 2026-11-22). So a listed
#                     address gets the same 201 and no email; it is cleared only by a link already emailed before
#                     the unsubscribe and pressed after it (fresh consent), or by hand on a request to support.
# OFF unless BOTH this and SIGNUP_VERIFY are on: the list exists only with a confirmation email in front of it.
UPDATES_LIST = os.environ.get('UPDATES_LIST', 'off').strip().lower() == 'on'
MAIL_TABLE = os.environ.get('MAIL_TABLE', 'london-flight-map-mail')
# The strip's wording, versioned: stored with every member so the consent can be shown later exactly as it was given.
# A change to the strip's words or promise (frequency, what is sent) is a new version. NEWS_PROMISE and
# NEWS_PROMISE is js/news-signup.mjs's PROMISE word for word (tests/test_news_flags.py holds them).
# news-v2 (2026-11-22, Bill's pick): the front page offers NEWS ONLY. The postcode box (news-v1's AREA_PROMISE, "Also
# tell me when the figures for {postcode} change.") is gone: the page opens on an example and suggests places, so most
# searches are someone looking around, and two offers in one strip confused. Following a place may come back from the
# full map's result, as its own version. A news-v1 member's stored words stay as they were.
NEWS_CONSENT_VERSION = 'news-v2 (2026-11-22)'
NEWS_PROMISE = 'News by email. New cities and new data. At most one email a month.'


def consent_wording():
    """The words this member agreed to, as stored: the strip's promise, under its version."""
    return f'{NEWS_CONSENT_VERSION}: {NEWS_PROMISE}'
# A confirm link lives a day. Long enough for an email to sit unread over a
# night, short enough that a leaked link is not a standing door; the pending
# table's TTL expires the row on the same clock, so an old token cannot be
# replayed after the fact even if this check were skipped.
PENDING_TTL_SECONDS = 24 * 3600
TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{20,64}$')
# Verification emails per address per UTC day (audit I-5, 25 Sep). The route
# throttle alone allowed ~86k sends a day at one address - the SES sender
# reputation on the line. Over the cap the reply is still the identical 201,
# so the cap cannot be used to learn anything about an address.
SEND_CAP_PER_DAY = 3
# Counter rows share the pending table under a key TOKEN_PATTERN can never
# match ('#' is outside it), so no confirm link can ever reach one.
SEND_COUNTER_PREFIX = 'sendcap#'
# Confirmation emails to ALL addresses per UTC day: the residual of audit M-3
# (5 Oct) that OPERATIONS.md s3.9 put before the flip. The per-address cap
# bounds what one inbox can be sent; this bounds what the sender can be made to
# send, because SES judges the whole account on its bounces and complaints, and
# a script cycling made-up addresses got three each, ~86k a day at the route
# throttle. 200 is far above any day the site has had and far under SES's
# 50,000; the env var raises it without a code change. Over it, the reply says
# so in words (a 503, logged as one), the same for every address.
SEND_CEILING_PER_DAY = int(os.environ.get('SEND_CEILING_PER_DAY', '200'))
# The ceiling's row: 'all' can never be a sha256 hex digest, so it cannot
# collide with an address's row.
SEND_CEILING_ROW = 'all'
SEND_CEILING_MESSAGE = (
    'We have sent as many confirmation emails as we can today. Please try again tomorrow.'
)
# Domains that deliver every dotted spelling of a local part to one inbox,
# each mapped to the domain it is an alias of. Only Google does this; for any
# other domain `a.b@` and `ab@` can be two people, so their dots are kept.
DOT_BLIND_DOMAINS = {'gmail.com': 'gmail.com', 'googlemail.com': 'gmail.com'}
# A UK postcode SHAPE. Only a match goes into the email body: the field is
# free text, and a mail client auto-links anything domain-shaped.
UK_POSTCODE = re.compile(r'^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$')
KEY_NAME_PREFIX = 'SkyScoreUserKey-'
# Tag applied to every key created by this Lambda (audit N-Code-1).
# IAM policy on apigateway:DELETE has a matching tag-condition so a
# compromised signup Lambda cannot delete keys it did not create.
KEY_TAG_KEY = 'CreatedBy'
KEY_TAG_VALUE = 'SignupLambda'

_usage_plan_id_cache = None


class SignupLookupError(Exception):
    """The signups table could not be read, so nothing about the address is known."""

# Pragmatic email regex, RFC 5322 compliance is overkill for a signup
# form; this catches the common shape and rejects obvious garbage. The
# real validation is "did the user copy-paste an email they actually
# read". We're not sending email so we don't need deliverability.
EMAIL_PATTERN = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')

# Origins allowed to call the signup endpoint from a browser. Locked
# down from '*' (audit N-Sec-4): the form lives on skyscore.co.uk and
# the legacy CloudFront URL only. Server-side abuse isn't gated by
# CORS but the per-route APIGW throttle handles that case.
#
# The two `localhost` entries are the NATIVE APP (audit M4, 2026-09-14).
# The same index.html runs inside a Capacitor WebView, which serves it
# from `capacitor://localhost` on iOS and, with `androidScheme: 'https'`
# in mobile/capacitor.config.ts, from `https://localhost` on Android -
# and the consumer notify form (added 2026-08-21) POSTs JSON here, which
# is a preflighted request. With neither origin listed the WebView was
# answered `Access-Control-Allow-Origin: https://skyscore.co.uk` and
# blocked the response, so the form could only ever fail in the app.
# Neither origin is reachable from a web browser - no site is served
# from them - so listing them widens nothing on the web.
# `test_native_webview_origins_match_capacitor_config` derives both
# from the Capacitor config, so a scheme change there reds here.
ALLOWED_ORIGINS = {
    'https://skyscore.co.uk',
    'https://www.skyscore.co.uk',
    'https://d1oe4ftwutjpf.cloudfront.net',
    'capacitor://localhost',
    'https://localhost',
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
        'Strict-Transport-Security': 'max-age=31536000',
        'X-Content-Type-Options': 'nosniff',
        'Access-Control-Allow-Methods': 'POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '86400',
        'Vary': 'Origin',
    }


# A CLIENT BUDGET THAT FITS INSIDE THE FUNCTION (2026-09-13 audit, I14).
# Both clients were built on botocore's defaults - 60s connect, 60s read,
# legacy retries - inside a function whose Timeout was 10s. One hung GetItem
# was killed by Lambda at 10s; the 503 branches below never ran and the
# consumer form saw a CORS failure. The /nhs class (22 Aug) and the chat
# class (I16), in the two Lambdas those sweeps did not look at. The path
# makes up to FOUR sequential calls (GetItem, CreateApiKey, CreateUsagePlanKey,
# PutItem), so the budget is per hop and the function Timeout is 28 to hold
# four of them; InnerClientBudgetTests asserts hops x budget < Timeout.
_BOTO_CONFIG = Config(
    connect_timeout=2,
    read_timeout=2,
    retries={'max_attempts': 1, 'mode': 'standard'},
)
# 5 since I17 (2026-09-15): the confirm path CONSUMES the pending row with one
# DeleteItem(ReturnValues=ALL_OLD) - read and burn in a single call - and then
# runs the four the key path always made.
# 6 since news by email (2026-11-22, code review): its POST reads the
# do-not-email list first, then the two send counters, the pending write, the
# SES send, and on a failed send the pending delete. Its confirm stays at five
# (the member's PutItem returns the old member, so no separate read). Six hops
# at a 4s budget (read_timeout 3 -> 2: DynamoDB and SES answer in tens of ms)
# is 24, under the 28s Timeout; InnerClientBudgetTests holds it there.
_SEQUENTIAL_HOPS = 6
apigw = boto3.client('apigateway', region_name=AWS_REGION, config=_BOTO_CONFIG)
ddb = boto3.client('dynamodb', region_name=AWS_REGION, config=_BOTO_CONFIG)
# SES in the home region. The identity (skyscore.co.uk) is verified there;
# SUBPROCESSORS.md row 1 names it. Built at import like its two siblings.
ses = boto3.client('sesv2', region_name=AWS_REGION, config=_BOTO_CONFIG)


# --- Helpers ------------------------------------------------------------


def response(status, body, event=None):
    if status >= 500:
        # [5XX] (2026-10-27): API Gateway counts a 5xx but cannot say whose, and a handler that RETURNS one logs
        # nothing else; backend/tests/test_5xx_logged.py holds every builder to this line.
        logger.warning('[5XX] %s %s', status, str(body.get('error', '') if isinstance(body, dict) else '')[:200])
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
    except (ClientError, BotoCoreError) as e:
        # NOT `return None` (audit M13). None means "no row", and the caller
        # acts on it: a consumer form would proceed to the conditional put,
        # hit the existing row, and answer 200 "already-subscribed" - to a
        # KEY HOLDER who is on no list - while a denied GetItem went unlogged.
        # A read that failed is a read that failed; the handler answers 503.
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.error('[SIGNUP_LOOKUP_FAILED] code=%s', code)
        raise SignupLookupError(code) from e
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


def record_signup(email, name, key_id, source='api', postcode=''):
    """Audit-log the signup. Email is the partition key (one per email).

    `source` and `postcode` were added 2026-08-21 for the consumer notify list.
    They are recorded rather than inferred because the two intents are genuinely
    different and a single table cannot distinguish them later: an API signup
    wanted a key, a consumer signup wanted to hear when ONE postcode moves. A
    row with no source would have to be guessed at, and guessing is how a
    marketing list ends up holding people who never asked to be on one.

    `keyId` is empty for a consumer, because no key is issued for them.
    """
    item = {
        'email': {'S': email},
        'name': {'S': name or ''},
        'keyId': {'S': key_id or ''},
        'source': {'S': source},
        'createdAt': {'S': datetime.now(UTC).isoformat()},
    }
    if postcode:
        item['postcode'] = {'S': postcode}
    ddb.put_item(
        TableName=SIGNUPS_TABLE,
        Item=item,
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
    # A body that is not an object, or a field that is not text, is the caller's
    # mistake: each raised on `.get` / `.strip` and answered 500, so anyone could
    # write 5xx lines and trip the 5xx alarm (audit M-11, 12 Nov 2026).
    if not isinstance(body, dict):
        return response(400, {'error': 'JSON body must be an object.'}, event)
    for field in ('email', 'name', 'source', 'postcode'):
        if body.get(field) is not None and not isinstance(body.get(field), str):
            return response(400, {'error': f'{field} must be a string.'}, event)

    email = (body.get('email') or '').strip().lower()
    name = (body.get('name') or '').strip()
    # 'consumer' is the postcode-panel notify list; anything else is the
    # existing B2B key signup. Defaulting to the KEY path would mean a
    # malformed source silently issues an API key to someone who asked for an
    # email alert - so the consumer path is opt-in by exact match, and an
    # unrecognised value falls through to the behaviour that already existed.
    # 'updates' (2026-11-10) is news by email (since 2026-11-22), by the same exact match.
    raw_source = (body.get('source') or '').strip()
    source = raw_source if raw_source in ('consumer', 'updates') else 'api'
    postcode = (body.get('postcode') or '').strip().upper()[:12]

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

    if source == 'updates':
        # Closed until the list may open: the same answer for every address, so it says nothing about any of them.
        # A 403, not a 503: closed is a decision, not a fault, and a 5xx would count in the API's error figures.
        if not (UPDATES_LIST and SIGNUP_VERIFY):
            return response(403, {'error': 'News by email is not open yet.'}, event)
        # News only (news-v2, 2026-11-22): the strip sends no postcode and privacy s2a names none, so one sent anyway
        # is dropped here, never checked, stored or emailed. Same answer either way: nothing to probe.
        postcode = ''

    if SIGNUP_VERIFY:
        return start_verification(email, name, source, postcode, event)
    return complete_signup(email, name, source, postcode, event)


def complete_signup(email, name, source, postcode, event):
    """The signup proper: the existing-row rules, the key mint or the list
    entry, the audit row. Called straight from the POST with SIGNUP_VERIFY
    off, and from the confirm link with it on - the ONE holder of the rules,
    so the two modes cannot drift on what a signup means."""
    if source == 'updates':
        # Its own table and its own rules: the signups table is not read or written for news by email.
        return subscribe_updates(email, event)
    # One key per email. If they already signed up, surface that with a
    # clear message, we cannot re-show the key (APIGW only returns the
    # value at creation time, not on subsequent reads).
    # createdAt is deliberately withheld from this body: /v1/signup is
    # unauthenticated, so anyone who guesses an address would otherwise
    # learn when its owner registered. It stays on the row for support.
    try:
        existing = get_existing_signup(email)
    except SignupLookupError:
        return response(
            503, {'error': 'Could not check this address. Please try again later.'}, event
        )
    # Which register does the existing row belong to? Consumer rows write
    # keyId as an explicit '' (record_signup below); key rows carry the real
    # id. Only an EXPLICIT marker changes a reply: a legacy row missing the
    # attribute keeps its branch's original wording, because guessing about
    # an unknown shape is how a reply ends up describing a list the row is
    # not on - the exact defect this distinction exists to fix (2026-08-24).
    existing_key_id = (existing or {}).get('keyId', {}).get('S')
    if existing and source == 'consumer':
        # The COMMON duplicate path for a consumer, and it must not fall
        # into the B2B 409 below - that one says a key cannot be
        # re-issued and to contact support, which is nonsense to someone
        # who asked for an email about a postcode.
        #
        # This ordering bug shipped to production for the length of one
        # deploy on 2026-08-21 and the unit test did not see it, because
        # the test patched get_existing_signup to None and exercised the
        # RACE path (put_item raising ConditionalCheckFailed) instead of
        # the path every real repeat visitor takes. Caught by calling the
        # deployed endpoint twice.
        if existing_key_id:
            # Their row is the API-key register, and one-row-per-email means
            # this subscription was NOT recorded - so "you are already on the
            # list for score updates" was false in both halves. One sentence,
            # the true one: the frontend prints data.message verbatim.
            return response(
                200,
                {
                    'status': 'already-registered',
                    'message': (
                        'This email already holds a Sky Score API key; use a '
                        'different address for score updates, or contact '
                        'support to switch this one.'
                    ),
                },
                event,
            )
        return response(
            200,
            {
                'status': 'already-subscribed',
                'message': 'You are already on the list for score updates.',
            },
            event,
        )
    if existing:
        if existing_key_id == '':
            # An explicit consumer row: no key was ever issued for this
            # address, so the re-issue wording below would assert a key that
            # does not exist. Name the list the row is actually on.
            return response(
                409,
                {
                    'error': 'This email has already signed up.',
                    'note': (
                        'This address is on the score-updates list and holds '
                        'no API key. Contact support to add API access to it.'
                    ),
                },
                event,
            )
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

    # CONSUMER NOTIFY LIST - returns before any key is created.
    #
    # A person who typed a postcode into the consumer map does not want an API
    # key, and issuing one would be both a cost (API Gateway caps keys per
    # account) and a privacy problem: it puts them in a B2B key registry whose
    # metadata carries their email, which audit finding 9 already flags.
    #
    # WHAT WE PROMISE HERE IS LIMITED ON PURPOSE. There is no SES in this stack
    # and no automated sending of any kind; outbound mail today is a human using
    # Gmail's "send mail as", which is not even DKIM-aligned for this domain yet
    # (see EMAIL_AUTH_SETUP.md). So the copy on the page offers a quarterly note
    # when the score moves - which matches both the real vintage cadence and
    # what a person can actually send by hand - and does NOT offer instant
    # alerts. Storing an address against a promise the infrastructure cannot
    # keep is the same defect as painting a borough with a reading nobody took.
    if source == 'consumer':
        try:
            record_signup(email, name, key_id='', source='consumer', postcode=postcode)
        except ClientError as e:
            if e.response.get('Error', {}).get('Code', '') == 'ConditionalCheckFailedException':
                # Already on the list. That is the outcome they wanted, so it
                # is reported as success rather than as an error - a 409 here
                # would read as "something went wrong" to someone who is, in
                # fact, subscribed.
                return response(
                    200,
                    {
                        'status': 'already-subscribed',
                        'message': "You are already on the list for score updates.",
                    },
                    event,
                )
            logger.error('[SIGNUP_CONSUMER_FAILED] err=%r', e)
            return response(503, {'error': 'Could not save. Please try again later.'}, event)
        return response(
            201,
            {
                'status': 'subscribed',
                'postcode': postcode or None,
                'message': (
                    "Thanks. We will email you when this area's score changes, "
                    'which happens when the underlying data is refreshed - '
                    'roughly quarterly.'
                ),
            },
            event,
        )

    try:
        key_id, key_value = create_api_key(email, name)
    except (ClientError, BotoCoreError) as e:
        # Most common failure: limit on number of API keys per account. The
        # code goes to the LOG, not the body (audit M2): /v1/signup is
        # unauthenticated, and an AWS error code names the service behind
        # it to whoever asks. BotoCoreError is here too - a transport fault
        # escaped this clause as a raw 500 until 2026-09-14.
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.error('[SIGNUP_CREATE_KEY_FAILED] code=%s', code)
        return response(
            503, {'error': 'Could not create API key. Please try again later.'}, event
        )

    try:
        record_signup(email, name, key_id, source='api')
    except (ClientError, BotoCoreError) as e:
        # BotoCoreError joined ClientError here on 2026-09-14 (audit M2). A
        # transport fault on the DDB write used to escape as a raw 500 AFTER
        # create_api_key had succeeded: an enabled key with no row, and a
        # caller who never received it and would try again - minting a
        # second. It now takes the "other errors" branch below: the key is
        # returned, and the orphaned audit row is logged by keyId.
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
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
                'monthlyQuota': 10000,
                'burstLimit': 5,
                'sustainedRateLimit': 2,
                # 1, not 100: /v1/score/batch is denied per-method for this
                # plan as of 2026-08-21, so a free request cannot carry more
                # than one query and the ceiling is no longer a product.
                'batchMultiplier': 1,
                'monthlyScoreCeiling': 10000,
                # 'quota' means the ceiling IS monthlyQuota x batchMultiplier.
                # Professional's is 'fair-use' and is deliberately lower than
                # that product; the field exists so the two are not read as the
                # same kind of number.
                'scoreCeilingBasis': 'quota',
            },
            # Added 2026-08-04, completing the 2026-07-29 decision in
            # BATCH_METERING_DECISION.md. Stated in the SAME UNIT as the tier
            # above it, because the defect that decision fixed was quoting
            # requests while selling scores.
            #
            # THE CEILING IS NOT monthlyQuota x batchMultiplier HERE, and that
            # difference is the whole point. 100,000 x 100 is 10,000,000, which
            # is what a £499 key could technically drain: roughly every home in
            # London three times over, undercutting both the £12,000 Enterprise
            # floor and the £2,500 pilot. 1,000,000 is a deliberate contractual
            # cap at a tenth of that. scoreCeilingBasis distinguishes the two
            # kinds of number so a client cannot read one as the other, and a
            # test asserts this block's ceiling is BELOW the product rather
            # than equal to it.
            #
            # Unenforced, and not described as if it were: API Gateway meters
            # requests, so nothing technically stops a key spending the full
            # 10,000,000. This is a published commitment, not a control. It
            # closes when per-score metering (option A) ships, and the first
            # paying Professional customer is exactly that trigger.
            'upgrade': {
                'tier': 'Professional',
                'priceGbpPerMonth': 499,
                'monthlyQuota': 100000,
                'batchMultiplier': 100,
                'monthlyScoreCeiling': 1000000,
                'scoreCeilingBasis': 'fair-use',
                'contact': 'support@skyscore.co.uk',
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


def confirm_url_base(event):
    """Where the confirm link points, DERIVED from the request that asked for
    it rather than configured: the API's own domain and stage, so a custom
    domain (api.skyscore.co.uk, mapped to the stage at its root) and the raw
    execute-api host both produce a link that resolves. CONFIRM_URL_BASE in
    the environment overrides both, for the day the link should go through
    the site's distribution instead."""
    override = os.environ.get('CONFIRM_URL_BASE', '').strip()
    if override:
        return override.rstrip('/')
    ctx = event.get('requestContext') or {}
    domain = ctx.get('domainName') or ''
    stage = ctx.get('stage') or ''
    if not domain:
        return ''
    if 'execute-api' in domain and stage:
        return f'https://{domain}/{stage}'
    return f'https://{domain}'


def start_verification(email, name, source, postcode, event):
    """SIGNUP_VERIFY=on: write a pending row, send the link, answer 201.

    THE 201 IS IDENTICAL FOR EVERY ADDRESS. The register is not consulted
    here at all - not to warn, not to short-circuit - because a reply that
    differs for a known address is the oracle audit I17 describes, and the
    person who clicks the link will see the true state on the confirm page,
    where only someone who controls the address can read it.
    """
    accepted = response(
        201,
        {
            'status': 'pending',
            'message': (
                'Check your email for a link to confirm this address. '
                'The link works for 24 hours.'
            ),
        },
        event,
    )
    if source == 'updates':
        # The do-not-email list comes first, before a counter is touched: an address that unsubscribed is never
        # written to again (privacy s2a), not even to confirm. The SAME 201, so the list cannot be probed. An
        # unreadable list fails CLOSED: sending without knowing could break that promise.
        try:
            listed = 'Item' in ddb.get_item(TableName=MAIL_TABLE, Key=_mail_key('suppress', email), ConsistentRead=True)
        except (ClientError, BotoCoreError) as e:
            code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
            logger.error('[UPDATES_SUPPRESS_LOOKUP_FAILED] code=%s', code)
            return response(503, {'error': 'Could not start the signup. Please try again later.'}, event)
        if listed:
            logger.info('[UPDATES_SUPPRESSED] no confirmation sent to an address on the do-not-email list')
            return accepted
    decision = send_decision(email)
    if decision == 'full':
        # Said in words, because the person asking is most likely real: a
        # silent 201 would leave them waiting for an email that never comes.
        # send_decision() answers 'full' for every address alike, so this
        # reply says nothing about the address it was asked for.
        logger.warning('[SIGNUP_SEND_CEILING] ceiling=%d/day', SEND_CEILING_PER_DAY)
        return response(503, {'error': SEND_CEILING_MESSAGE}, event)
    if decision == 'skip':
        # Same 201 as a real send: the cap must not become an oracle.
        logger.warning('[SIGNUP_SEND_CAPPED] cap=%d/day', SEND_CAP_PER_DAY)
        return accepted

    token = secrets.token_urlsafe(32)
    now = int(time.time())
    try:
        ddb.put_item(
            TableName=PENDING_TABLE,
            Item={
                'token': {'S': token},
                'email': {'S': email},
                'name': {'S': name},
                'source': {'S': source},
                'postcode': {'S': postcode},
                'createdAt': {'N': str(now)},
                'expiresAt': {'N': str(now + PENDING_TTL_SECONDS)},
            },
            ConditionExpression='attribute_not_exists(#t)',
            ExpressionAttributeNames={'#t': 'token'},
        )
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.error('[SIGNUP_PENDING_WRITE_FAILED] code=%s', code)
        return response(503, {'error': 'Could not start the signup. Please try again later.'}, event)

    link = f'{confirm_url_base(event)}/v1/signup/confirm?token={token}'
    try:
        send_confirmation_email(email, source, postcode, link)
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.error('[SIGNUP_EMAIL_FAILED] code=%s', code)
        # Nothing to confirm without the email; do not leave a live token.
        try:
            ddb.delete_item(TableName=PENDING_TABLE, Key={'token': {'S': token}})
        except (ClientError, BotoCoreError):
            logger.warning('[SIGNUP_PENDING_ORPHAN] a pending row outlives a failed send; the TTL takes it')
        return response(
            503, {'error': 'Could not send the confirmation email. Please try again later.'}, event
        )

    return accepted


def mailbox_key(email):
    """The address as the INBOX it reaches, for counting sends and nothing else:
    never for sending, storing, or matching a signup to the register.

    `name+anything@` reaches `name@` at Gmail, Outlook, iCloud, Fastmail and
    Proton, so the tag is dropped for every domain; at worst two people on a
    system that treats `+` literally share one count of three. Dots are dropped
    only where Google ignores them (DOT_BLIND_DOMAINS), and googlemail.com counts
    as gmail.com. Without this, `name+1@`, `name+2@` and `n.ame@` each had their
    own three sends at one inbox (audit M-3, 5 Oct). Expects the lower-cased,
    validated address handle_post() passes on.
    """
    local, _, domain = email.rpartition('@')
    local = local.split('+', 1)[0]
    if domain in DOT_BLIND_DOMAINS:
        local = local.replace('.', '')
        domain = DOT_BLIND_DOMAINS[domain]
    return f'{local}@{domain}'


def _counter_key(row, day):
    return {'token': {'S': f'{SEND_COUNTER_PREFIX}{row}#{day}'}}


def _count_one(row, day):
    """Add one to a counter row and return the new count, or None when
    DynamoDB could not say (the caller then fails open)."""
    try:
        out = ddb.update_item(
            TableName=PENDING_TABLE,
            Key=_counter_key(row, day),
            UpdateExpression='ADD sends :one SET expiresAt = if_not_exists(expiresAt, :exp)',
            ExpressionAttributeValues={
                ':one': {'N': '1'},
                ':exp': {'N': str(int(time.time()) + PENDING_TTL_SECONDS)},
            },
            ReturnValues='UPDATED_NEW',
        )
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.warning('[SIGNUP_SEND_COUNTER_FAILED] code=%s (failing open)', code)
        return None
    return int(out.get('Attributes', {}).get('sends', {}).get('N', '1'))


def _count_now(row, day):
    """Read a counter row without adding to it: 0 when it does not exist yet,
    None when DynamoDB could not say."""
    try:
        out = ddb.get_item(TableName=PENDING_TABLE, Key=_counter_key(row, day), ConsistentRead=True)
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.warning('[SIGNUP_SEND_COUNTER_FAILED] code=%s (failing open)', code)
        return None
    return int(((out.get('Item') or {}).get('sends') or {}).get('N', '0'))


def send_decision(email):
    """'send', 'skip' (this inbox has had SEND_CAP_PER_DAY today: the same 201,
    no email) or 'full' (SEND_CEILING_PER_DAY emails have gone today: a 503
    that says so).

    Two atomic counters per UTC day, both expiring with the pending rows: one
    per inbox, keyed on a HASH of mailbox_key() so the row holds no address,
    and one for the whole day. The day's counter counts only emails that are
    really sent, so a script hammering one capped address cannot use up the
    day for everyone. An inbox over its cap still READS the day's counter, so
    that once the day is full every address gets the 503: a 201 for a capped
    address beside a 503 for a fresh one would say which addresses had been
    asked for three times today.

    Fails OPEN on a DynamoDB error, either counter: the route throttle still
    bounds sends, and failing closed would lock every real signup out
    whenever a counter was unreadable.
    """
    import hashlib

    day = datetime.now(UTC).strftime('%Y-%m-%d')
    digest = hashlib.sha256(mailbox_key(email).encode('utf-8')).hexdigest()
    sends = _count_one(digest, day)
    if sends is not None and sends > SEND_CAP_PER_DAY:
        today = _count_now(SEND_CEILING_ROW, day)
        return 'full' if today is not None and today >= SEND_CEILING_PER_DAY else 'skip'
    today = _count_one(SEND_CEILING_ROW, day)
    return 'full' if today is not None and today > SEND_CEILING_PER_DAY else 'send'


CONFIRM_SMALL_PRINT = 'The link works for 24 hours. If this was not you, ignore this email and nothing is stored.'
CONFIRM_FOOTER = 'Sky Score - https://skyscore.co.uk'
# Each kind of sign-up's band: its tag, and the strip's promise under the brand where there is one.
_BAND = {
    'updates': ('News by email', 'New cities and new data. At most one email a month.'),
    'consumer': ('Score updates', ''),
    'api': ('API key', ''),
}


def confirmation_html(source, what, link):
    """The confirmation email's HTML part (Bill's pick, 2026-11-22: the blue-grey band, Stitch draft S2, rebuilt here):
    tables and inline styles, as every mail app needs; the site's colours; system fonts; NO images, no remote content,
    nothing that could track an open. Same words as the plain-text part, and every one of them escaped."""
    tag, line = _BAND.get(source, _BAND['api'])
    font = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    e = html.escape
    band_line = (f'<div style="margin-top:4px;font:400 14px/1.45 {font};color:#3a4448">{e(line)}</div>' if line else '')
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">'
        f'<title>{e(tag)} - Sky Score</title></head>'
        '<body style="margin:0;padding:0;background:#f4f3ef">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f3ef" '
        'style="background:#f4f3ef"><tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="max-width:560px;background:#ffffff;border:1px solid #dedcd6;border-radius:18px;border-collapse:separate">'
        # The band: the brand on the left, the kind of sign-up on the right, the promise under them.
        '<tr><td bgcolor="#dbe4e8" style="background:#dbe4e8;padding:18px 24px;border-radius:18px 18px 0 0">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="font:700 17px/1.3 {font};color:#141414">Sky Score</td>'
        f'<td align="right" style="font:400 13px/1.3 {font};color:#3a4448">{e(tag)}</td></tr></table>'
        f'{band_line}</td></tr>'
        f'<tr><td style="padding:22px 24px 0;font:700 22px/1.3 {font};color:#141414">Confirm your email</td></tr>'
        f'<tr><td style="padding:10px 24px 0;font:400 16px/1.55 {font};color:#141414">{e(what)}</td></tr>'
        # A full-width button that also works in Outlook: the cell carries the colour, the link fills it.
        '<tr><td style="padding:20px 24px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'border="0"><tr><td align="center" bgcolor="#141414" style="background:#141414;border-radius:10px">'
        f'<a href="{e(link, quote=True)}" style="display:block;padding:15px 18px;font:700 16px/1.2 {font};'
        'color:#ffffff;text-decoration:none;border-radius:10px">Confirm my email</a></td></tr></table></td></tr>'
        '<tr><td style="padding:20px 24px 0"><div style="border-top:1px solid #dedcd6;font-size:0;line-height:0">'
        '&nbsp;</div></td></tr>'
        f'<tr><td style="padding:14px 24px 0;font:400 14px/1.5 {font};color:#55554f">{e(CONFIRM_SMALL_PRINT)}</td></tr>'
        f'<tr><td style="padding:10px 24px 24px;font:400 13px/1.5 {font};color:#55554f;word-break:break-all">'
        f'If the button does not work, open this link: <a href="{e(link, quote=True)}" style="color:#141414">'
        f'{e(link)}</a></td></tr>'
        '</table>'
        f'<div style="padding:16px 12px 0;font:400 13px/1.5 {font};color:#55554f">Sky Score - '
        '<a href="https://skyscore.co.uk" style="color:#55554f">https://skyscore.co.uk</a></div>'
        '</td></tr></table></body></html>'
    )


def send_confirmation_email(email, source, postcode, link):
    """The confirmation email: the plain-text part (the words Bill approved, unchanged) and, since 2026-11-22, an HTML
    part in the site's look (confirmation_html). No tracking, no images, no personal data beyond the address it is
    sent to; the link carries the token alone. News by email names no postcode since news-v2."""
    if source == 'consumer':
        subject = 'Confirm your Sky Score updates'
        # Only a real postcode shape reaches the body; anything else could be
        # a domain a mail client turns into a link inside OUR email.
        shown = postcode if UK_POSTCODE.match(postcode or '') else 'an area'
        what = (
            f'Someone - probably you - asked for an email when the Sky Score for '
            f'{shown} changes. Confirm it here:'
        )
    elif source == 'updates':
        subject = 'Confirm your Sky Score news'
        what = (
            'Someone - probably you - asked for Sky Score news by email: new cities and new data, at most one '
            'email a month. Confirm it here:'
        )
    else:
        subject = 'Confirm your Sky Score API key request'
        what = 'Someone - probably you - asked for a free Sky Score API key. Confirm the address here:'
    body = f'{what}\n\n{link}\n\n{CONFIRM_SMALL_PRINT}\n\n{CONFIRM_FOOTER}\n'
    ses.send_email(
        FromEmailAddress=SES_FROM,
        Destination={'ToAddresses': [email]},
        ReplyToAddresses=[SES_REPLY_TO],
        Content={
            'Simple': {
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Text': {'Data': body, 'Charset': 'UTF-8'},
                    'Html': {'Data': confirmation_html(source, what, link), 'Charset': 'UTF-8'},
                },
            }
        },
    )


# The pages a person reaches from our emails (confirm, unsubscribe, and their answers) wear the email's look (Bill's
# pick, 2026-11-22: the blue-grey band, Stitch draft S2): the site's page colour, a white card with the band and the
# brand, a dark full-width button. The site's own colours (home/index.html: --bg #f4f3ef, --line #dedcd6, --water
# #dbe4e8, --dark #141414, secondary #55554f, --focus #d35a12). Plain CSS in the page, system fonts, no images.
_PAGE = (
    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<meta name="robots" content="noindex">'
    '<title>{title} - Sky Score</title>'
    '<style>'
    'body{{margin:0;background:#f4f3ef;color:#141414;'
    'font:16px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}'
    'main{{max-width:34rem;margin:0 auto;padding:24px 16px 40px}}'
    '.card{{background:#fff;border:1px solid #dedcd6;border-radius:18px;overflow:hidden}}'
    '.band{{background:#dbe4e8;padding:16px 24px;font-weight:600}}'
    '.in{{padding:22px 24px 24px}}'
    'h1{{font-size:22px;line-height:1.3;margin:0 0 12px}}'
    'p{{margin:0 0 12px}}a{{color:#141414}}'
    'button{{display:block;width:100%;font-family:inherit;font-size:16px;font-weight:600;line-height:1.2;padding:14px 18px;'
    'border:0;border-radius:10px;background:#141414;color:#fff;cursor:pointer}}'
    'button:focus-visible,a:focus-visible{{outline:3px solid #d35a12;outline-offset:2px}}'
    'code{{display:block;padding:12px;background:#f4f3ef;border-radius:8px;word-break:break-all;font-size:15px}}'
    '.foot{{text-align:center;font-size:13px;color:#55554f;margin-top:16px}}.foot a{{color:#55554f}}'
    '</style></head>'
    '<body><main><div class="card"><div class="band">Sky Score</div><div class="in"><h1>{title}</h1>{body}</div></div>'
    '<p class="foot"><a href="https://skyscore.co.uk/">skyscore.co.uk</a></p></main>{script}</body></html>'
)

# ONE CLICK for news by email (Bill's pick 1, 2026-11-22): the confirm page posts its own form as it opens, so a person
# who opens the link is confirmed (privacy s2a: "Opening the link in that email confirms it."). A scanner that only
# FETCHES links (Safe Links, Mimecast, Proofpoint: the 25 Sep incident) runs no script and changes nothing; with script
# off, the button is there. The page's CSP allows this one script by its hash and nothing else.
_AUTO_CONFIRM_JS = "document.getElementById('confirm').submit();"
_AUTO_CONFIRM_HASH = 'sha256-' + base64.b64encode(hashlib.sha256(_AUTO_CONFIRM_JS.encode('utf-8')).digest()).decode('ascii')


def html_page(status, title, body, script=''):
    """A page, not a JSON envelope: the caller is a person who clicked a link
    in an email. Everything interpolated is escaped, including our own
    strings - the key is the one thing on the page that came from an API.
    `script` is only ever _AUTO_CONFIRM_JS: the CSP names its hash, so no other script could run."""
    if script and script != _AUTO_CONFIRM_JS:
        raise ValueError('html_page runs no script but the one-click confirm')
    csp = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"
    if script:
        csp += f"; script-src '{_AUTO_CONFIRM_HASH}'"
    if status >= 500:
        # [5XX] (2026-10-27): API Gateway counts a 5xx but cannot say whose, and a handler that RETURNS one logs
        # nothing else; backend/tests/test_5xx_logged.py holds every builder to this line.
        logger.warning('[5XX] %s %s', status, title)
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
            'Strict-Transport-Security': 'max-age=31536000',
            'Referrer-Policy': 'no-referrer',
            # form-action is NOT covered by default-src, so it is named: the
            # confirm button may post back to this origin and nowhere else.
            'Content-Security-Policy': csp,
        },
        'body': _PAGE.format(title=html.escape(title), body=body,
                             script=f'<script>{script}</script>' if script else ''),
    }


_INVALID_LINK = ('That link is not valid',
                 '<p>The confirmation link is incomplete. Open it exactly as it appears in the email.</p>')
_EXPIRED_LINK = ('That link has expired or was already used',
                 '<p>Confirmation links work once, for 24 hours. Sign up again where you started: '
                 '<a href="https://skyscore.co.uk/">the front page</a> for news by email, '
                 '<a href="https://skyscore.co.uk/map/">the full map</a> for score alerts, or '
                 '<a href="https://skyscore.co.uk/score-demo/">the API page</a> for a key.</p>')

# Where each kind of sign-up starts again (2026-11-10 review: an area-updates sign-up was sent to the API-key page).
_AGAIN = {
    'updates': ('https://skyscore.co.uk/', 'Sign up again on the front page'),
    'consumer': ('https://skyscore.co.uk/map/', 'Sign up again from the map'),
}
_AGAIN_DEFAULT = ('https://skyscore.co.uk/score-demo/', 'Request a new link')


def _form_token(event):
    """The token from a form POST body (urlencoded, possibly base64), or ''."""
    from urllib.parse import parse_qs

    raw = event.get('body') or ''
    if event.get('isBase64Encoded'):
        import base64

        try:
            raw = base64.b64decode(raw).decode()
        except (ValueError, UnicodeDecodeError):
            return ''
    return (parse_qs(raw).get('token') or [''])[0].strip()


def handle_confirm_get(event):
    """GET /v1/signup/confirm?token= : SHOW the confirm button, change nothing.

    A GET used to consume the token and mint the key (audit I-5, 25 Sep).
    Corporate mail gateways (Safe Links, Mimecast, Proofpoint) fetch every
    link in an inbound email before a person opens it, so the SCANNER got the
    only copy of the key and the person got a 410. Now this only reads the
    row (strongly consistent, never deleting it) and renders a button whose
    POST does the work; scanners fetch links, they do not submit forms.
    """
    token = ((event.get('queryStringParameters') or {}).get('token') or '').strip()
    if not TOKEN_PATTERN.match(token):
        return html_page(400, *_INVALID_LINK)
    try:
        row = ddb.get_item(
            TableName=PENDING_TABLE, Key={'token': {'S': token}}, ConsistentRead=True
        ).get('Item')
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.error('[SIGNUP_CONFIRM_LOOKUP_FAILED] code=%s', code)
        return html_page(503, 'Please try again', '<p>We could not check that link just now. Try it again in a minute.</p>')
    if not row or int(row.get('expiresAt', {}).get('N', '0')) < int(time.time()):
        return html_page(410, *_EXPIRED_LINK)
    source = row.get('source', {}).get('S')
    form = (f'<form method="post" id="confirm"><input type="hidden" name="token" value="{html.escape(token)}">'
            '<button type="submit">Confirm</button></form>')
    if source == 'updates':
        # One click (see _AUTO_CONFIRM_JS): the form posts itself as the page opens; the button is the fallback.
        return html_page(
            200, 'Confirming your email',
            '<p>One moment: confirming this address for Sky Score news by email, at most one email a month.</p>'
            '<p>If nothing happens, press Confirm.</p>' + form,
            script=_AUTO_CONFIRM_JS,
        )
    # API keys and the map's list keep the button: a key is shown ONCE (a scanner running script would take it), and
    # that list's privacy paragraph says "Opening the link alone confirms nothing".
    what = 'email updates' if source == 'consumer' else 'a free Sky Score API key'
    return html_page(
        200, 'Confirm your email address',
        f'<p>Press the button to confirm this address for {html.escape(what)}.</p>' + form,
    )


def handle_confirm(event):
    """POST /v1/signup/confirm : consume the pending row and finish.

    Only the button on the GET page reaches this. The token comes from the
    form body; the query string is accepted too because the form posts back
    to the URL it was served from.
    """
    token = _form_token(event) or ((event.get('queryStringParameters') or {}).get('token') or '').strip()
    if not TOKEN_PATTERN.match(token):
        return html_page(400, *_INVALID_LINK)
    try:
        # Read AND burn in one call: a second click, or a second tab, finds
        # nothing, so one email can never mint two keys.
        old = ddb.delete_item(
            TableName=PENDING_TABLE, Key={'token': {'S': token}}, ReturnValues='ALL_OLD'
        ).get('Attributes')
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.error('[SIGNUP_CONFIRM_LOOKUP_FAILED] code=%s', code)
        return html_page(503, 'Please try again', '<p>We could not check that link just now. Try it again in a minute.</p>')
    if not old or int(old.get('expiresAt', {}).get('N', '0')) < int(time.time()):
        return html_page(410, *_EXPIRED_LINK)
    email = old['email']['S']
    name = old.get('name', {}).get('S', '')
    source = old.get('source', {}).get('S', 'api')
    postcode = old.get('postcode', {}).get('S', '')

    result = complete_signup(email, name, source, postcode, event)
    try:
        data = json.loads(result.get('body') or '{}')
    except ValueError:
        data = {}
    status = result.get('statusCode', 500)
    if status == 201 and data.get('apiKey'):
        return html_page(
            200, 'Your Sky Score API key',
            f'<p>Address confirmed. This key is shown <strong>once</strong> - copy it now.</p>'
            f'<code>{html.escape(data["apiKey"])}</code>'
            f'<p>Send it as the <code>X-Api-Key</code> header on <code>/v1/score</code>. '
            f'{html.escape(str(data.get("limits", {}).get("monthlyQuota", "")))} requests a month on the free tier. '
            f'<a href="https://skyscore.co.uk/score-demo/api-docs.html">Docs</a>.</p>',
        )
    if status in (200, 201):
        title = "You're signed up" if source == 'updates' else 'Confirmed'
        return html_page(200, title, f'<p>{html.escape(data.get("message", "Done."))}</p>')
    if status == 409:
        return html_page(
            200, 'Already signed up',
            f'<p>{html.escape(data.get("error", ""))} {html.escape(data.get("note", ""))}</p>',
        )
    if source == 'updates' and status == 403:
        # The list closed again between the email and the click: nothing was saved, and the page says so.
        return html_page(200, 'News by email is closed', '<p>News by email is not taking sign-ups just now, so nothing '
                         'was saved and we will not email you about it.</p>')
    href, label = _AGAIN.get(source, _AGAIN_DEFAULT)
    return html_page(
        503, 'Please try again',
        '<p>Your address is confirmed but the signup could not be completed just now. '
        f'<a href="{href}">{label}</a> and try again.</p>',
    )


def _mail_key(kind, value):
    return {'pk': {'S': f'{kind}#{value}'}}


def subscribe_updates(email, event):
    """Join news by email, once the emailed link has been confirmed (complete_signup() runs only from the confirm
    page for this source, because the POST refuses 'updates' unless SIGNUP_VERIFY is on). News only since news-v2
    (2026-11-22): no postcode is stored, even from a pending row made before the box was removed (privacy s2a names
    none).

    A confirmed sign-up REPLACES the member: the consent is what was agreed this time, so joining again under news-v2
    drops a news-v1 member's postcode.

    A new token for every confirmed sign-up, written BEFORE the member that names it, so a failure part-way leaves at
    most a token nobody holds, never a member whose emails could carry no working unsubscribe link. A previous token is
    retired. The do-not-email entry goes: a confirmed sign-up is fresh consent from the person who owns the address.

    Once the member is written the person IS subscribed, so the two tidy-ups after it are best effort, logged, and the
    answer stays 201 (2026-11-10 review: a failed retire used to answer 503 to someone already on the list). A stale
    token left behind can only unsubscribe the address it names; a do-not-email entry left behind only stops emails.
    The list's flag is read again here, because a link emailed while it was open can be pressed after it closes.
    """
    if not UPDATES_LIST:
        return response(403, {'error': 'News by email is not open yet.'}, event)
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC).isoformat()
    member = {
        **_mail_key('updates', email),
        'email': {'S': email},
        'consent': {'S': consent_wording()},
        'consentedAt': {'S': now},
        'via': {'S': 'website'},
        'unsubToken': {'S': token},
    }
    try:
        ddb.put_item(TableName=MAIL_TABLE, Item={**_mail_key('unsub', token), 'email': {'S': email}, 'createdAt': {'S': now}})
        # The old member comes back from the write itself (one hop, not a read then a write: the confirm path's budget
        # is five calls, _SEQUENTIAL_HOPS; code review 2026-11-22).
        old = ddb.put_item(TableName=MAIL_TABLE, Item=member, ReturnValues='ALL_OLD').get('Attributes')
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.error('[UPDATES_JOIN_FAILED] code=%s', code)
        return response(503, {'error': 'Could not save. Please try again later.'}, event)
    old_token = (old or {}).get('unsubToken', {}).get('S')
    tidy = [('suppress', email)] + ([('unsub', old_token)] if old_token and old_token != token else [])
    for kind, value in tidy:
        try:
            ddb.delete_item(TableName=MAIL_TABLE, Key=_mail_key(kind, value))
        except (ClientError, BotoCoreError) as e:
            code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
            logger.error('[UPDATES_JOIN_TIDY_FAILED] kind=%s code=%s', kind, code)
    return response(
        201,
        {
            'status': 'subscribed',
            'message': (
                'Thanks. You are on the list for Sky Score news. At most one email a month, and every email has '
                'a link to stop them.'
            ),
        },
        event,
    )


_UNSUB_UNKNOWN = ('You are not on the list',
                  '<p>That link is no longer active, so there is nothing to stop. If you are still getting our emails, '
                  'email support@skyscore.co.uk and we will take you off by hand.</p>')


def handle_unsubscribe_get(event):
    """GET /v1/signup/unsubscribe?token= : SHOW the button, change nothing. Mail scanners fetch every link in an email
    before a person opens it (audit I-5, 25 Sep); a GET that unsubscribed would let a scanner do it. The button's POST
    does the work, and so does a mail client's RFC 8058 one-click POST to the same address."""
    token = ((event.get('queryStringParameters') or {}).get('token') or '').strip()
    if not TOKEN_PATTERN.match(token):
        return html_page(400, 'That link is not valid',
                         '<p>The unsubscribe link is incomplete. Open it exactly as it appears in the email.</p>')
    return html_page(
        200, 'Stop these emails',
        '<p>Press the button and we will stop Sky Score news, and not email this address again.</p>'
        f'<form method="post"><input type="hidden" name="token" value="{html.escape(token)}">'
        '<button type="submit">Unsubscribe</button></form>',
    )


def handle_unsubscribe(event):
    """POST /v1/signup/unsubscribe : the button above, or a mail client's one-click POST (body
    `List-Unsubscribe=One-Click`, the token in the query string). Idempotent: an unknown or used token says so and
    changes nothing. The address joins the do-not-email list, then the member goes, then the token LAST (2026-11-10
    review: deleting the token first meant a failure part-way left the person subscribed, and the retry, finding no
    token, told them there was nothing to stop). Every step repeats safely, so a retry finishes what a failure left.

    ANY live token stops ALL mail to its address, even one from an email sent before the person re-joined (code review
    2026-11-22 raised it). On purpose: whoever presses an unsubscribe link in an email we sent wants our emails to stop,
    and honouring that beats keeping a newer consent the press contradicts (PECR: a refusal must be easy and must work)."""
    token = _form_token(event) or ((event.get('queryStringParameters') or {}).get('token') or '').strip()
    if not TOKEN_PATTERN.match(token):
        return html_page(400, 'That link is not valid',
                         '<p>The unsubscribe link is incomplete. Open it exactly as it appears in the email.</p>')
    try:
        old = ddb.get_item(TableName=MAIL_TABLE, Key=_mail_key('unsub', token), ConsistentRead=True).get('Item')
        if not old:
            return html_page(200, *_UNSUB_UNKNOWN)
        email = old['email']['S']
        ddb.put_item(
            TableName=MAIL_TABLE,
            Item={**_mail_key('suppress', email), 'email': {'S': email}, 'suppressedAt': {'S': datetime.now(UTC).isoformat()}},
        )
        ddb.delete_item(TableName=MAIL_TABLE, Key=_mail_key('updates', email))
        ddb.delete_item(TableName=MAIL_TABLE, Key=_mail_key('unsub', token))
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        logger.error('[UPDATES_UNSUB_FAILED] code=%s', code)
        return html_page(503, 'Please try again',
                         '<p>We could not stop the emails just now. Try the link again in a minute, or email '
                         'support@skyscore.co.uk and we will do it by hand.</p>')
    return html_page(200, 'You are unsubscribed', '<p>We will not email this address again.</p>')


def handler(event, context):
    method = (event.get('httpMethod') or 'POST').upper()
    try:
        path = (event.get('path') or '').rstrip('/')
        is_confirm = path.endswith('/confirm')
        is_unsub = path.endswith('/unsubscribe')
        if method == 'OPTIONS':
            return handle_options(event)
        if method == 'POST' and is_unsub:
            return handle_unsubscribe(event)
        if method == 'GET' and is_unsub:
            return handle_unsubscribe_get(event)
        if method == 'POST' and is_confirm:
            return handle_confirm(event)
        if method == 'POST':
            return handle_post(event)
        if method == 'GET' and is_confirm:
            return handle_confirm_get(event)
        return response(405, {'error': f'Method {method} not allowed.'}, event)
    except Exception as exc:
        # Top-level guard, never let an unhandled exception escape the
        # CORS-headered envelope. Log to CloudWatch for postmortem.
        logger.exception('unhandled exception in signup handler: %s', exc)
        return response(500, {'error': 'Internal server error.'}, event)
