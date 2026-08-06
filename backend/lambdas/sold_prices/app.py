import json
import logging
import os
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

OGL_ATTRIBUTION = (
    'Sold prices: HM Land Registry. Contains public sector information licensed under the Open Government Licence v3.0.'
)


def _pref_label(node):
    """Pull the human label out of a Land Registry SKOS-ish concept.

    `propertyType` is not a string. It is an object whose `prefLabel` is a LIST
    OF OBJECTS: [{'_value': 'flat-maisonette', '_lang': 'en'}]. The previous
    code took prefLabel[0] and returned that object, which serialised into the
    response and rendered as "[object Object]" in every consumer.

    Returns '' rather than a placeholder when the shape is unfamiliar: an
    unknown property type is better shown as nothing than as a guess.
    """
    labels = (node or {}).get('prefLabel')
    if isinstance(labels, list) and labels:
        first = labels[0]
        if isinstance(first, dict):
            return first.get('_value', '')
        if isinstance(first, str):
            return first
    if isinstance(labels, str):
        return labels
    return ''


def _iso_date(raw):
    """Normalise Land Registry's RFC-style date to ISO, or '' if unparseable.

    They send 'Thu, 17 Oct 1996' — no time, no timezone, day name first. Every
    consumer here treats dates as ISO and slices the first ten characters, which
    turned that into 'Thu, 17 Oc'. Converting once at the boundary is better than
    teaching each consumer a second date format.
    """
    if not raw:
        return ''
    try:
        return datetime.strptime(raw.strip(), '%a, %d %b %Y').strftime('%Y-%m-%d')
    except (TypeError, ValueError):
        # Unrecognised shape: hand back what we were given rather than invent a
        # date. A visibly odd string is debuggable; a fabricated one is not.
        return raw


def handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        postcode = params.get('postcode', '')

        if not postcode:
            return response(400, {'error': 'postcode parameter is required'})

        # DO NOT substitute '+' for the space here.
        #
        # This read `.replace(' ', '+')` and was then passed through quote()
        # below, which percent-encodes the plus as %2B. Land Registry therefore
        # received the literal string "WA2+8SN" and matched nothing, so this
        # endpoint returned an EMPTY LIST WITH HTTP 200 for every postcode ever
        # queried. It has never returned a transaction.
        #
        # It looked healthy the whole time: no error, no exception, no log line,
        # just `transactions: []` — indistinguishable from a postcode with no
        # recorded sales, which is a real and common case. Isolated 2026-08-06
        # against WA2 8SN, which has records: space encoding returns 3 items,
        # %2B returns 0, no-space returns 0.
        #
        # quote() already encodes a space as %20 and Land Registry accepts that.
        clean = postcode.strip().upper()

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
                    'date': _iso_date(item.get('transactionDate', '')),
                    'address': item.get('propertyAddress', {}).get('paon', ''),
                    'street': item.get('propertyAddress', {}).get('street', ''),
                    'type': _pref_label(item.get('propertyType')),
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
