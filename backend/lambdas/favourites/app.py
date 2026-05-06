"""
Sky Score favourites Lambda — DynamoDB CRUD for saved properties.

Audit notes addressed in this rewrite (full audit at AUDIT_REPORT.md):
- C7 — replaced bare `except Exception:` with specific types + structured
  `logger.exception` for the final guard.
- M3 — `datetime.utcnow()` → `datetime.now(timezone.utc).isoformat()`.
- I16 (favourites/app.py:30-36) — replaced the broken Decimal-detection
  heuristic (`isinstance(v, boto3.dynamodb.conditions.Key)` was checking
  a query-builder type, not a value type) with a proper
  `decimal.Decimal` JSON encoder.
- C3 (favourites IDOR) is NOT addressed in this commit — separate task.
  This keeps the existing untrusted `userId` query-string contract.
"""

import json
import logging
import os
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


class _DecimalEncoder(json.JSONEncoder):
    """JSON encoder that converts boto3 Decimal values to int / float as
    appropriate. Replaces the previous `hasattr(v, 'is_finite')` heuristic
    which failed for some valid Decimals."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj == int(obj) else float(obj)
        return super().default(obj)


def handler(event, context):
    method = event.get('httpMethod', 'GET')

    try:
        if method == 'OPTIONS':
            return response(200, {})

        if method == 'GET':
            params = event.get('queryStringParameters') or {}
            user_id = params.get('userId', 'anonymous')
            result = table.query(KeyConditionExpression=Key('userId').eq(user_id))
            return response(200, {'favourites': result.get('Items', [])})

        if method == 'POST':
            try:
                body = json.loads(event.get('body') or '{}')
            except json.JSONDecodeError as exc:
                logger.warning('Invalid JSON body on POST: %s', exc)
                return response(400, {'error': 'Invalid JSON body.'})
            user_id = body.get('userId', 'anonymous')
            postcode = body.get('postcode', '')
            if not postcode:
                return response(400, {'error': 'Postcode is required'})

            item = {
                'userId':     user_id,
                'postcode':   postcode,
                'borough':    body.get('borough', ''),
                'noiseLevel': body.get('noiseLevel', ''),
                'buyerScore': str(body.get('buyerScore', 0)),
                'notes':      body.get('notes', ''),
                'timestamp':  datetime.now(timezone.utc).isoformat(),
                'city':       body.get('city', 'london'),
            }
            table.put_item(Item=item)
            return response(200, {'message': 'Saved', 'item': item})

        if method == 'DELETE':
            try:
                body = json.loads(event.get('body') or '{}')
            except json.JSONDecodeError as exc:
                logger.warning('Invalid JSON body on DELETE: %s', exc)
                return response(400, {'error': 'Invalid JSON body.'})
            user_id = body.get('userId', 'anonymous')
            postcode = body.get('postcode', '')
            if not postcode:
                return response(400, {'error': 'Postcode is required'})
            table.delete_item(Key={'userId': user_id, 'postcode': postcode})
            return response(200, {'message': 'Deleted'})

        return response(405, {'error': 'Method not allowed'})

    except (BotoCoreError, ClientError) as exc:
        logger.warning('DynamoDB error in favourites: %s', exc)
        return response(503, {'error': 'Storage backend temporarily unavailable.'})
    except Exception as exc:  # pragma: no cover  — final guard
        logger.exception('Unhandled exception in favourites handler: %s', exc)
        return response(500, {'error': 'Internal server error'})


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
        },
        'body': json.dumps(body, cls=_DecimalEncoder),
    }
