import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

OGL_ATTRIBUTION = (
    'Sold prices: HM Land Registry. Contains public sector information licensed under the Open Government Licence v3.0.'
)


def handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        postcode = params.get('postcode', '')

        if not postcode:
            return response(400, {'error': 'postcode parameter is required'})

        clean = postcode.strip().upper().replace(' ', '+')

        # HM Land Registry Price Paid Data - official free API
        url = (
            f'https://landregistry.data.gov.uk/data/ppi/transaction-record.json'
            f'?propertyAddress.postcode={quote(clean)}'
            f'&_pageSize=10'
            f'&_sort=-transactionDate'
        )

        req = Request(url, headers={'Accept': 'application/json'})
        try:
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.warning('Land Registry lookup failed for %s: %s', postcode, exc)
            return response(
                503,
                {
                    'error': 'Sold-prices upstream temporarily unavailable.',
                    'postcode': postcode,
                },
            )
        except json.JSONDecodeError as exc:
            logger.warning('Land Registry returned non-JSON for %s: %s', postcode, exc)
            return response(
                502,
                {
                    'error': 'Sold-prices upstream returned malformed data.',
                    'postcode': postcode,
                },
            )

        items = data.get('result', {}).get('items', [])

        results = []
        for item in items:
            results.append(
                {
                    'price': item.get('pricePaid', 0),
                    'date': item.get('transactionDate', ''),
                    'address': item.get('propertyAddress', {}).get('paon', ''),
                    'street': item.get('propertyAddress', {}).get('street', ''),
                    'type': item.get('propertyType', {}).get('prefLabel', [''])[0]
                    if isinstance(item.get('propertyType', {}).get('prefLabel'), list)
                    else item.get('propertyType', {}).get('prefLabel', ''),
                    'newBuild': item.get('newBuild', False),
                }
            )

        return response(
            200,
            {
                'postcode': postcode,
                'transactions': results,
                'sources': [OGL_ATTRIBUTION],
            },
        )

    except Exception as exc:  # pragma: no cover, final guard
        logger.exception('Unhandled exception in sold_prices handler: %s', exc)
        return response(500, {'error': 'Internal server error'})


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
        },
        'body': json.dumps(body),
    }
