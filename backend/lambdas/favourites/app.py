"""
Sky Score favourites Lambda, DynamoDB CRUD for saved properties.

Audit C3 mitigation: opaque device-token auth.

Previously every endpoint accepted a `userId` from the query string or
body, untrusted. Anyone with a userId could read / write / delete that
user's favourites (OWASP A01, IDOR).

The new contract:
- Caller must send `X-Device-Token` header containing a UUID v4.
- The header is the partition key; userId in query/body is rejected.
- This isn't auth, anyone who learns a token can use it. But:
  - Tokens are 122-bit random (UUID v4); guessing one is infeasible.
  - Tokens never appear in URLs (no leakage via referer headers,
    server logs, browser history).
  - Format is validated, garbage / sniffed query strings are rejected.

Backwards compat: the old localStorage `flightmap_device_id` payload
was a non-UUID string, so existing data is orphaned by this change.
Acceptable in pre-launch, users re-save favourites under their new
token. The old rows remain in DDB until manually cleaned.

Other audit items addressed in this rewrite:
- C7, specific exception types + `logger.exception` final guard.
- M3, `datetime.utcnow()` → `datetime.now(timezone.utc).isoformat()`.
- I16, proper `decimal.Decimal` JSON encoder for boto3 Decimal types.
"""

import json
import logging
import os
import re
from datetime import UTC, datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')
TABLE_NAME = os.environ.get('FAVOURITES_TABLE', 'london-flight-map-favourites')

dynamodb = boto3.resource('dynamodb', region_name='eu-west-2')
table = dynamodb.Table(TABLE_NAME)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Accept either canonical UUID (8-4-4-4-12 hex, with hyphens) or a bare
# 32-char hex string. Case-insensitive. UUIDs only, random 32-byte hex
# is also accepted in case the frontend uses crypto.getRandomValues
# directly without UUID formatting.
_TOKEN_PATTERN = re.compile(
    r'^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$',
    re.IGNORECASE,
)

# The `postcode` field is a location KEY, not strictly a postcode. The
# frontend writes six different shapes into it (index.html):
#   full UK postcode    'SW11 1AA'
#   UK outcode          'TW3'          (lookupPostcode outcode fallback, ~5540)
#   NYC ZIP / ZIP+4     '10001', '10001-1234'
#   area + postcode     "Shepherd's Bush (W12 8LJ)"   (~6365)
#   NYC area + ZIP      'Astoria (11102)'             (~6354)
#   a borough NAME      'Kensington and Chelsea'
#     — the borough card's SAVE button passes data-fav-name as BOTH the
#     postcode and the borough (legacy behaviour, index.html ~7851).
# A strict postcode regex would 400 the last three and break the most
# common save path, so this validates the shape of a *location key*:
# ASCII letters / digits / a small punctuation set, plus a hard length
# cap. That keeps junk out of the sort key without rejecting anything
# the product actually sends. Verified against every AREA_MAP,
# NYC_AREA_MAP and BOROUGH_DATA name in index.html (306 values; longest
# real key 'Kensington and Chelsea (SW11 1AA)', 33 chars).
_LOCATION_PATTERN = re.compile(r"^[A-Za-z0-9 ()'.,&-]+$")

# Length caps. DynamoDB only rejects at 400 KB per item / 1024 B per sort
# key, so a caller can currently store ~400 KB of junk per write. Nothing
# caps items per token or tokens per client, the table has no TTL, and
# PointInTimeRecovery keeps 35 days of continuous backup — so junk written
# today outlives deletion of the items themselves. Capping each field
# bounds a favourite to well under 2 KB, cutting the storage and PITR
# amplification of an abusive write by roughly three orders of magnitude.
#
# We REJECT rather than truncate: truncating would silently corrupt a
# user's own notes, and would still admit the write, which is the thing
# being bounded. Rejecting also matches signup/app.py's precedent
# ('Email or name exceeds maximum length.').
MAX_LOCATION_LEN = 64  # postcode (sort key) and borough
MAX_NOISE_LEVEL_LEN = 48
MAX_CITY_LEN = 32
MAX_NOTES_LEN = 1000
MAX_SCORE_LEN = 16


def get_device_token(event):
    """Extract and validate the device token from headers. Returns the
    canonicalised lowercase hex (no hyphens) or None if absent / malformed."""
    headers = event.get('headers') or {}
    # API Gateway can lower-case header names depending on integration.
    token = (headers.get('X-Device-Token') or headers.get('x-device-token') or '').strip()
    if not token or not _TOKEN_PATTERN.match(token):
        return None
    return token.lower().replace('-', '')


def validate_favourite(body):
    """Validate a POST body before it reaches put_item.

    Returns None when the body is acceptable, otherwise a dict ready to
    hand straight to `response(400, ...)`.

    This is not a crash / injection / IDOR guard — DynamoDB already
    rejects oversized items and non-string keys, GET only ever queries
    the caller's own token, and the frontend escapes every field on
    render. It exists to bound unbounded junk-item accrual (see the
    length-cap rationale above).

    POST only. DELETE deliberately keeps the looser `if not postcode`
    check so rows saved before these rules landed — which may hold
    values this regex now rejects — remain deletable.
    """
    postcode = body.get('postcode', '')
    if not postcode:
        return {'error': 'Postcode is required'}
    if not isinstance(postcode, str):
        return {'error': 'Postcode must be a string.'}
    if len(postcode) > MAX_LOCATION_LEN:
        return {'error': f'Postcode exceeds the maximum length of {MAX_LOCATION_LEN} characters.'}
    if not _LOCATION_PATTERN.match(postcode) or not any(c.isalnum() for c in postcode):
        return {
            'error': 'Postcode is not a recognisable location.',
            'expected': (
                'A UK postcode or outcode, an NYC ZIP, or an area / borough '
                "name, e.g. 'SW11 1AA', 'TW3', '10001', 'Astoria (11102)'."
            ),
        }

    for field, cap in (
        ('borough', MAX_LOCATION_LEN),
        ('noiseLevel', MAX_NOISE_LEVEL_LEN),
        ('city', MAX_CITY_LEN),
        ('notes', MAX_NOTES_LEN),
    ):
        value = body.get(field, '')
        if value is None or value == '':
            continue
        if not isinstance(value, str):
            return {'error': f'{field} must be a string.'}
        if len(value) > cap:
            return {'error': f'{field} exceeds the maximum length of {cap} characters.'}

    # buyerScore is str()-coerced into the item, so a nested object or a
    # 100k-digit integer would otherwise land as a very large attribute.
    # Restrict it to a scalar whose string form is short. `bool` is
    # excluded explicitly because it is a subclass of int.
    score = body.get('buyerScore', 0)
    if isinstance(score, bool) or not isinstance(score, (int, float, str)):
        return {'error': 'buyerScore must be a number.'}
    try:
        score_text = str(score)
    except ValueError:
        # CPython 3.11+ caps int -> str conversion at 4300 digits and
        # raises here. An integer that long is junk by definition, so
        # treat it as an over-length score rather than letting the
        # ValueError escape to the 500 guard.
        return {'error': f'buyerScore exceeds the maximum length of {MAX_SCORE_LEN} characters.'}
    if len(score_text) > MAX_SCORE_LEN:
        return {'error': f'buyerScore exceeds the maximum length of {MAX_SCORE_LEN} characters.'}

    return None


class _DecimalEncoder(json.JSONEncoder):
    """JSON encoder that converts boto3 Decimal values to int / float as
    appropriate. Replaces the previous `hasattr(v, 'is_finite')` heuristic."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj == int(obj) else float(obj)
        return super().default(obj)


def handler(event, context):
    method = event.get('httpMethod', 'GET')

    try:
        if method == 'OPTIONS':
            return response(200, {})

        # All non-OPTIONS methods require a valid device token.
        token = get_device_token(event)
        if not token:
            return response(
                401,
                {
                    'error': 'X-Device-Token header missing or malformed.',
                    'expected': 'UUID v4 (e.g. 550e8400-e29b-41d4-a716-446655440000) or 32-char hex.',
                },
            )

        if method == 'GET':
            result = table.query(KeyConditionExpression=Key('userId').eq(token))
            return response(200, {'favourites': result.get('Items', [])})

        if method == 'POST':
            try:
                body = json.loads(event.get('body') or '{}')
            except json.JSONDecodeError as exc:
                logger.warning('Invalid JSON body on POST: %s', exc)
                return response(400, {'error': 'Invalid JSON body.'})
            if not isinstance(body, dict):
                return response(400, {'error': 'JSON body must be an object.'})

            error = validate_favourite(body)
            if error:
                logger.info('Rejected favourite write: %s', error['error'])
                return response(400, error)

            postcode = body['postcode']

            item = {
                'userId': token,  # partition key is the device token
                'postcode': postcode,
                'borough': body.get('borough', ''),
                'noiseLevel': body.get('noiseLevel', ''),
                'buyerScore': str(body.get('buyerScore', 0)),
                'notes': body.get('notes', ''),
                'timestamp': datetime.now(UTC).isoformat(),
                'city': body.get('city', 'london'),
            }
            table.put_item(Item=item)
            return response(200, {'message': 'Saved', 'item': item})

        if method == 'DELETE':
            try:
                body = json.loads(event.get('body') or '{}')
            except json.JSONDecodeError as exc:
                logger.warning('Invalid JSON body on DELETE: %s', exc)
                return response(400, {'error': 'Invalid JSON body.'})
            postcode = body.get('postcode', '')
            if not postcode:
                return response(400, {'error': 'Postcode is required'})
            table.delete_item(Key={'userId': token, 'postcode': postcode})
            return response(200, {'message': 'Deleted'})

        return response(405, {'error': 'Method not allowed'})

    except (BotoCoreError, ClientError) as exc:
        logger.warning('DynamoDB error in favourites: %s', exc)
        return response(503, {'error': 'Storage backend temporarily unavailable.'})
    except Exception as exc:  # pragma: no cover, final guard
        logger.exception('Unhandled exception in favourites handler: %s', exc)
        return response(500, {'error': 'Internal server error'})


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Device-Token',
            'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
        },
        'body': json.dumps(body, cls=_DecimalEncoder),
    }
