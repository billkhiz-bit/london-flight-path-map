import json
from urllib.parse import quote
from urllib.request import Request, urlopen


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
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        items = data.get('result', {}).get('items', [])

        results = []
        for item in items:
            results.append({
                'price': item.get('pricePaid', 0),
                'date': item.get('transactionDate', ''),
                'address': item.get('propertyAddress', {}).get('paon', ''),
                'street': item.get('propertyAddress', {}).get('street', ''),
                'type': item.get('propertyType', {}).get('prefLabel', [''])[0] if isinstance(item.get('propertyType', {}).get('prefLabel'), list) else item.get('propertyType', {}).get('prefLabel', ''),
                'newBuild': item.get('newBuild', False),
            })

        return response(200, {'postcode': postcode, 'transactions': results})

    except Exception as e:
        return response(500, {'error': str(e)})


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,OPTIONS'
        },
        'body': json.dumps(body)
    }
