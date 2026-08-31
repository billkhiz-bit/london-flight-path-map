"""
Sky Score chat Lambda — RETRIEVAL-ONLY.

Restored 2026-08-06 from the pre-6bad8ce Bedrock Lambdas, deliberately NOT as
the free-form assistant that was removed. The difference is the whole point.

WHY RETRIEVAL-ONLY. A free-form model asked "what's crime like in Barking?"
answers fluently whether or not it knows. On 2026-08-03 Barking's own crime rate
in this repo was corrected from 105 to 84.2 against ONS Table C4, and 29 of 33
boroughs were wrong. A model that invents a plausible figure would undo that
work in a sentence, in a product whose entire value proposition is that its
numbers are defensible.

So the model never supplies data. It is handed the exact JSON that /v1/score
returned and may only phrase it. Three mechanisms enforce that:

  1. The context comes from invoking ScoreFunction directly — the same code
     path /v1/score serves, so an answer cannot drift from the API. Reasoning
     borrowed from the bulk scorer, which reuses resolve_query for the same
     reason.
  2. The system prompt forbids stating any figure not present in the payload,
     and requires "I don't have that" over a guess.
  3. verify_answer() checks it. Every number in the reply must appear in the
     retrieved context; anything else is flagged and the response carries
     `grounded: false`. A prompt is a request, not a guarantee — this is the
     part that can actually fail.

The response always includes the context used, so any claim is checkable
against the same data the site and API serve.
"""

import json
import logging
import os
import re

import boto3
from botocore.config import Config

CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

# Nova models live in us-east-1; the rest of the stack is eu-west-2.
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'us-east-1')
NOVA_LITE_MODEL_ID = os.environ.get('NOVA_LITE_MODEL_ID', 'us.amazon.nova-2-lite-v1:0')

SCORE_FUNCTION_NAME = os.environ.get('SCORE_FUNCTION_NAME', '')

MAX_BODY_BYTES = 4096
MAX_QUESTION_CHARS = 500

# Nova Lite at ~$0.06/1M in, $0.24/1M out. A capped 400-token reply keeps a
# single exchange near $0.0003. The cap is also a safety rail: an unbounded
# max_tokens on a public endpoint is somebody else's budget to spend.
MAX_OUTPUT_TOKENS = 400

logger = logging.getLogger()

# THE INNER BUDGET MUST FIT INSIDE THE OUTER ONE (2026-08-31, audit I16).
#
# Both clients below were built with botocore's DEFAULTS: connect_timeout 60,
# read_timeout 60, and a retry mode that makes up to 5 attempts on a throttle.
# This function's Timeout is 28 (API Gateway will not wait past 29). So when
# Bedrock throttles nova-lite - a shared-capacity model in us-east-1, called
# from eu-west-2 - botocore retried with backoff, elapsed passed 28s, and Lambda
# was killed MID-CALL. `ask_model`'s `except Exception` never ran, so the caller
# got a raw 502 with no CORS headers and no JSON envelope instead of the
# 503 {'error': 'The assistant is unavailable right now.'} that exists for
# exactly this.
#
# Same class as audit I3 (2026-08-22), which lowered NhsFunction from 45s to 28s
# because "at 45s that branch could never run inside the caller's window, so a
# slow upstream produced a raw 504 instead of the degraded answer the code was
# written to give". That sweep fixed function-timeout-exceeds-gateway-cap and
# did not look at client-timeout-exceeds-function-timeout. /nhs already gets
# this right (timeout=26 under 28); chat was the one place an inner budget
# exceeded its outer one.
#
# Hoisted to module scope for the second half of the finding: chat rebuilt a
# client on EVERY invocation, which is 50-200ms of the same budget, while
# favourites and signup already build theirs once.
_BOTO_CONFIG = Config(
    connect_timeout=2,
    read_timeout=8,
    retries={'max_attempts': 2, 'mode': 'standard'},
)
logger.setLevel(logging.INFO)

SYSTEM_PROMPT = """You answer questions about UK and NYC property locations for Sky Score.

You will be given a JSON object containing the ONLY data you may use.

Rules, in order of importance:
1. NEVER state a number, score, price, rate or percentage that does not appear
   in the JSON. Not an estimate, not an approximation, not a typical value.
2. If the JSON does not contain what was asked, say plainly that you do not
   have that data. Do not substitute general knowledge about the area.
3. If the JSON contains a `coverage.notices` array, and your answer touches the
   component it refers to, include that limitation in your reply.
4. Be brief. Two or three sentences unless asked for more.
5. Do not speculate about future prices, and do not give investment advice.

You are a presenter of retrieved data, not a source of it."""


def cors_headers():
    return {
        'Access-Control-Allow-Origin': CORS_ORIGIN,
        'Access-Control-Allow-Methods': 'POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
        'Access-Control-Max-Age': '86400',
    }


def response(status, body):
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', **cors_headers()},
        'body': json.dumps(body),
    }


def retrieve_context(query):
    """Fetch real scoring data by invoking ScoreFunction directly.

    Direct invoke rather than an HTTP call to /v1/score: it runs the identical
    code path with no API key to provision, no egress, and no possibility of the
    chat answer and the API disagreeing. Returns (context_dict, error_string).
    """
    if not SCORE_FUNCTION_NAME:
        return None, 'Scoring backend is not configured.'

    params = {k: v for k, v in query.items() if v}
    event = {
        'httpMethod': 'GET',
        'queryStringParameters': params or None,
    }

    try:
        client = boto3.client('lambda', config=_BOTO_CONFIG)
        result = client.invoke(
            FunctionName=SCORE_FUNCTION_NAME,
            InvocationType='RequestResponse',
            Payload=json.dumps(event).encode(),
        )
        payload = json.loads(result['Payload'].read().decode())
    except Exception as exc:  # noqa: BLE001 — upstream shape is not ours to trust
        logger.exception('[CHAT_RETRIEVAL_FAILED] %r', exc)
        return None, 'Could not reach the scoring service.'

    if payload.get('statusCode') != 200:
        try:
            inner = json.loads(payload.get('body') or '{}')
        except (TypeError, ValueError):
            inner = {}
        # Surfacing the score API's own message keeps one wording for
        # "postcode not recognised" rather than inventing a second.
        return None, inner.get('error', 'That location could not be resolved.')

    try:
        return json.loads(payload['body']), None
    except (KeyError, TypeError, ValueError):
        return None, 'Scoring service returned an unreadable response.'


# Numbers that carry no factual claim on their own. Without this, "2 or 3
# sentences" style phrasing and ordinals trip the grounding check constantly and
# it stops meaning anything.
_TRIVIAL_NUMBERS = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10'}


def extract_numbers(text):
    """Every numeric token in a string, normalised for comparison."""
    return {n.replace(',', '').rstrip('.') for n in re.findall(r'\d[\d,]*\.?\d*', text or '')}


def verify_answer(answer, context):
    """Check that every figure in the answer appears in the retrieved data.

    The system prompt ASKS the model not to invent numbers. This checks whether
    it did — the difference between an instruction and a control. Returns
    (grounded, ungrounded_numbers).

    Deliberately conservative: it compares against the raw JSON text, so a
    number appearing anywhere in the payload passes. It will not catch a model
    that pairs a real number with the wrong label. It WILL catch the failure
    that matters most — a fluent, plausible figure that came from nowhere.
    """
    haystack = extract_numbers(json.dumps(context))
    # Rounded forms: the payload holds 7.0 and a natural answer says "7".
    haystack |= {n.rstrip('0').rstrip('.') for n in haystack if '.' in n}

    ungrounded = []
    for number in extract_numbers(answer):
        if number in _TRIVIAL_NUMBERS or number in haystack:
            continue
        if number.rstrip('0').rstrip('.') in haystack:
            continue
        ungrounded.append(number)

    return (not ungrounded), ungrounded


def ask_model(question, context):
    """Single Bedrock call. Returns (answer, error)."""
    bedrock = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION, config=_BOTO_CONFIG)

    user_text = (
        f'DATA (the only permitted source):\n{json.dumps(context, indent=1)}\n\n'
        f'QUESTION: {question}'
    )

    body = {
        'system': [{'text': SYSTEM_PROMPT}],
        'messages': [{'role': 'user', 'content': [{'text': user_text}]}],
        'inferenceConfig': {'maxTokens': MAX_OUTPUT_TOKENS, 'temperature': 0.2},
    }

    try:
        result = bedrock.invoke_model(
            modelId=NOVA_LITE_MODEL_ID,
            body=json.dumps(body).encode(),
        )
        parsed = json.loads(result['body'].read().decode())
        return parsed['output']['message']['content'][0]['text'].strip(), None
    except Exception as exc:  # noqa: BLE001
        logger.exception('[CHAT_MODEL_FAILED] %r', exc)
        return None, 'The assistant is unavailable right now.'


def handler(event, context):
    method = (event.get('httpMethod') or 'POST').upper()
    if method == 'OPTIONS':
        return {'statusCode': 204, 'headers': cors_headers(), 'body': ''}

    raw = event.get('body') or '{}'
    if len(raw) > MAX_BODY_BYTES:
        return response(413, {'error': f'Request body exceeds {MAX_BODY_BYTES} bytes.'})

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return response(400, {'error': 'Invalid or missing JSON body.'})

    question = (payload.get('question') or '').strip()
    if not question:
        return response(400, {'error': 'question is required.'})
    if len(question) > MAX_QUESTION_CHARS:
        return response(400, {'error': f'question exceeds {MAX_QUESTION_CHARS} characters.'})

    query = {
        'postcode': (payload.get('postcode') or '').strip(),
        'borough': (payload.get('borough') or '').strip(),
        'city': (payload.get('city') or '').strip(),
        'persona': (payload.get('persona') or '').strip(),
    }
    if not query['postcode'] and not query['borough']:
        return response(400, {'error': 'Provide either postcode or borough.'})

    retrieved, err = retrieve_context(query)
    if err:
        return response(400, {'error': err})

    answer, err = ask_model(question, retrieved)
    if err:
        return response(503, {'error': err})

    grounded, ungrounded = verify_answer(answer, retrieved)
    if not grounded:
        # Do NOT return the text. A fluent answer containing a number that came
        # from nowhere is the single failure this endpoint exists to prevent,
        # and shipping it with a warning attached would still put it on screen.
        logger.warning('[CHAT_UNGROUNDED] numbers=%r question=%r', ungrounded, question[:120])
        return response(
            200,
            {
                'answer': (
                    "I can't answer that from the data I have for this location. "
                    'Try asking about the score, its components, prices or crime.'
                ),
                'grounded': False,
                'context': retrieved,
            },
        )

    return response(200, {'answer': answer, 'grounded': True, 'context': retrieved})
