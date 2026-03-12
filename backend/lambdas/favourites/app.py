import json
import os
from datetime import datetime

import boto3

dynamodb = boto3.resource('dynamodb', region_name='eu-west-2')
table_name = os.environ.get('FAVOURITES_TABLE', 'london-flight-map-favourites')
table = dynamodb.Table(table_name)


def handler(event, context):
    method = event.get('httpMethod', 'GET')

    try:
        if method == 'OPTIONS':
            return response(200, {})

        if method == 'GET':
            params = event.get('queryStringParameters') or {}
            user_id = params.get('userId', 'anonymous')
            result = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('userId').eq(user_id)
            )
            items = result.get('Items', [])
            # Convert Decimal types to float/int for JSON serialization
            for item in items:
                for k, v in item.items():
                    if isinstance(v, (boto3.dynamodb.conditions.Key,)):
                        continue
                    try:
                        if hasattr(v, 'is_finite'):
                            item[k] = float(v)
                    except Exception:
                        pass
            return response(200, {'favourites': items})

        elif method == 'POST':
            body = json.loads(event.get('body', '{}'))
            user_id = body.get('userId', 'anonymous')
            postcode = body.get('postcode', '')

            if not postcode:
                return response(400, {'error': 'Postcode is required'})

            item = {
                'userId': user_id,
                'postcode': postcode,
                'borough': body.get('borough', ''),
                'noiseLevel': body.get('noiseLevel', ''),
                'buyerScore': str(body.get('buyerScore', 0)),
                'notes': body.get('notes', ''),
                'timestamp': datetime.utcnow().isoformat(),
                'city': body.get('city', 'london')
            }
            table.put_item(Item=item)
            return response(200, {'message': 'Saved', 'item': item})

        elif method == 'DELETE':
            body = json.loads(event.get('body', '{}'))
            user_id = body.get('userId', 'anonymous')
            postcode = body.get('postcode', '')

            if not postcode:
                return response(400, {'error': 'Postcode is required'})

            table.delete_item(Key={'userId': user_id, 'postcode': postcode})
            return response(200, {'message': 'Deleted'})

        return response(405, {'error': 'Method not allowed'})

    except Exception:
        return response(500, {'error': 'Internal server error'})


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS'
        },
        'body': json.dumps(body, default=str)
    }
