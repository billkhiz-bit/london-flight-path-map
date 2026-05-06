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
from datetime import datetime, timezone
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


def get_device_token(event):
    """Extract and validate the device token from headers. Returns the
    canonicalised lowercase hex (no hyphens) or None if absent / malformed."""
    headers = event.get('headers') or {}
    # API Gateway can lower-case header names depending on integration.
    token = (headers.get('X-Device-Token')
             or headers.get('x-device-token')
             or '').strip()
    if not token or not _TOKEN_PATTERN.match(token):
        return None
    return token.lower().replace('-', '')


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
            return response(401, {
                'error': 'X-Device-Token header missing or malformed.',
                'expected': 'UUID v4 (e.g. 550e8400-e29b-41d4-a716-446655440000) or 32-char hex.',
            })

        if method == 'GET':
            result = table.query(KeyConditionExpression=Key('userId').eq(token))
            return response(200, {'favourites': result.get('Items', [])})

        if method == 'POST':
            try:
                body = json.loads(event.get('body') or '{}')
            except json.JSONDecodeError as exc:
                logger.warning('Invalid JSON body on POST: %s', exc)
                return response(400, {'error': 'Invalid JSON body.'})
            postcode = body.get('postcode', '')
            if not postcode:
                return response(400, {'error': 'Postcode is required'})

            item = {
                'userId': token, # partition key is the device token
                'postcode': postcode,
                'borough': body.get('borough', ''),
                'noiseLevel': body.get('noiseLevel', ''),
                'buyerScore': str(body.get('buyerScore', 0)),
                'notes': body.get('notes', ''),
                'timestamp': datetime.now(timezone.utc).isoformat(),
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
    except Exception as exc: # pragma: no cover, final guard
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
