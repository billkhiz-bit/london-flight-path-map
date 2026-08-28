"""Handler-level smoke tests for the 9 Lambdas without dedicated test files.

Covers the cheap, high-leverage cases each handler should always get right:
- 400 on missing required params
- 401 on missing auth (favourites)
- 405 on unsupported methods
- 200 on the OPTIONS preflight
- 413 on oversized bodies (Bedrock endpoints)
- Validation rules for parsing inputs
- 201 on the signup happy path (added 2026-07-25, see SignupHandlerTests)

Bedrock invocations and external HTTP calls are mocked / skipped, these
tests cover request-handling logic, not upstream integrations. The
upstream integrations are tested via live curl smoke-tests at deploy time.

Run from project root:
    python -m unittest backend.tests.test_handlers
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Make every Lambda's app module importable without spinning up boto3.
LAMBDAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'lambdas')


def _import_lambda(name):
    """Import a Lambda's app module by name. Each Lambda is its own
    package-style folder; we add the folder to sys.path, import as 'app',
    then pop sys.modules so the next import is clean."""
    path = os.path.abspath(os.path.join(LAMBDAS_DIR, name))
    sys.path.insert(0, path)
    if 'app' in sys.modules:
        del sys.modules['app']
    try:
        import app  # noqa: F401, pylint: disable=import-outside-toplevel
        return app
    finally:
        sys.path.pop(0)


# ---------- Score handler tests (in addition to test_score.py) ----------

class ScoreHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('score')

    def test_options_returns_200(self):
        result = self.app.handler({'httpMethod': 'OPTIONS'}, None)
        self.assertEqual(result['statusCode'], 200)

    def test_get_no_params_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'GET', 'queryStringParameters': None}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_batch_invalid_json_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': 'not-json'}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_batch_missing_queries_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': '{}'}, None,
        )
        self.assertEqual(result['statusCode'], 400)


# ---------- Favourites, requires X-Device-Token (audit C3) ----------

class FavouritesHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('favourites')

    def test_options_returns_200(self):
        result = self.app.handler({'httpMethod': 'OPTIONS', 'headers': {}}, None)
        self.assertEqual(result['statusCode'], 200)

    def test_get_without_token_returns_401(self):
        result = self.app.handler(
            {'httpMethod': 'GET', 'headers': {}}, None,
        )
        self.assertEqual(result['statusCode'], 401)

    def test_get_with_invalid_token_returns_401(self):
        result = self.app.handler(
            {'httpMethod': 'GET',
             'headers': {'X-Device-Token': 'not-a-uuid'}},
            None,
        )
        self.assertEqual(result['statusCode'], 401)

    def test_uuid_format_accepted(self):
        # Token validates, but DynamoDB call would happen; mock it.
        # noqa justified: RFC 4122 example UUID, a format fixture rather than a
        # credential. X-Device-Token is an opaque per-install identifier, not a
        # secret — see the auth note in lambdas/favourites/app.py.
        good_token = '550e8400-e29b-41d4-a716-446655440000'  # noqa: S105
        canonical = self.app.get_device_token(
            {'headers': {'X-Device-Token': good_token}},
        )
        self.assertEqual(canonical, '550e8400e29b41d4a716446655440000')

    def test_bare_hex_token_accepted(self):
        canonical = self.app.get_device_token(
            {'headers': {'X-Device-Token': 'a' * 32}},
        )
        self.assertEqual(canonical, 'a' * 32)


# ---------- Signup, POST creates key, idempotent on email ----------

class SignupHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('signup')

    def test_options_returns_200(self):
        result = self.app.handler({'httpMethod': 'OPTIONS'}, None)
        self.assertEqual(result['statusCode'], 200)

    def test_post_no_body_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': ''}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_post_invalid_email_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST', 'body': json.dumps({'email': 'nope'})},
            None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_post_oversized_email_returns_400(self):
        result = self.app.handler(
            {'httpMethod': 'POST',
             'body': json.dumps({'email': 'a' * 300 + '@example.com'})},
            None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_get_returns_405(self):
        result = self.app.handler({'httpMethod': 'GET'}, None)
        self.assertEqual(result['statusCode'], 405)

    def test_cors_origin_echoed_for_allowlisted(self):
        # Allowed origin should be echoed back (not '*'), per N-Sec-4 lockdown.
        result = self.app.handler(
            {'httpMethod': 'OPTIONS',
             'headers': {'Origin': 'https://skyscore.co.uk'}},
            None,
        )
        self.assertEqual(result['headers']['Access-Control-Allow-Origin'],
                         'https://skyscore.co.uk')

    def test_cors_origin_canonical_fallback_for_unknown(self):
        # Hostile / unknown origin should fall back to the canonical site,
        # NOT echo the requester's origin and NOT use '*'.
        result = self.app.handler(
            {'httpMethod': 'OPTIONS',
             'headers': {'Origin': 'https://evil.example.com'}},
            None,
        )
        self.assertEqual(result['headers']['Access-Control-Allow-Origin'],
                         'https://skyscore.co.uk')
        self.assertNotEqual(result['headers']['Access-Control-Allow-Origin'], '*')

    def test_cors_origin_canonical_fallback_when_no_origin(self):
        # No Origin header at all (server-to-server, curl, etc.) → canonical.
        result = self.app.handler({'httpMethod': 'OPTIONS', 'headers': {}}, None)
        self.assertEqual(result['headers']['Access-Control-Allow-Origin'],
                         'https://skyscore.co.uk')

    def test_cors_origin_lowercase_header_also_works(self):
        # API Gateway can deliver headers as either 'Origin' or 'origin'
        # depending on stage / proxy; both must be honoured.
        result = self.app.handler(
            {'httpMethod': 'OPTIONS',
             'headers': {'origin': 'https://www.skyscore.co.uk'}},
            None,
        )
        self.assertEqual(result['headers']['Access-Control-Allow-Origin'],
                         'https://www.skyscore.co.uk')

    def test_safe_revoke_orphan_key_refuses_non_prefix(self):
        # Belt-and-braces guard alongside the IAM tag-condition (N-Code-1):
        # if get_api_key returns a key whose name doesn't start with
        # KEY_NAME_PREFIX, _safe_revoke_orphan_key must NOT call delete_api_key.
        # Mocked since unit tests don't touch live AWS.
        with patch.object(self.app.apigw, 'get_api_key',
                          return_value={'name': 'NotOurPrefix-attacker-controlled'}), \
             patch.object(self.app.apigw, 'delete_api_key') as mock_delete:
            self.app._safe_revoke_orphan_key('some-key-id')
            mock_delete.assert_not_called()  # the prefix guard fired

    def test_safe_revoke_orphan_key_proceeds_for_own_prefix(self):
        # Conversely: a key whose name starts with KEY_NAME_PREFIX is
        # eligible for delete (plus the IAM tag-condition would also apply).
        with patch.object(self.app.apigw, 'get_api_key',
                          return_value={'name': self.app.KEY_NAME_PREFIX + 'user_at_example_com'}), \
             patch.object(self.app.apigw, 'delete_api_key') as mock_delete:
            self.app._safe_revoke_orphan_key('legitimate-key-id')
            mock_delete.assert_called_once_with(apiKey='legitimate-key-id')

    # ----- Consumer notify list (D5, 2026-08-21) -----
    #
    # The consumer path shares a route with the B2B key signup, which is the
    # whole risk: a person who typed a postcode into the consumer map must not
    # come out of it holding an API key. API Gateway caps keys per account, and
    # audit finding 9 records that key METADATA carries the raw email - so an
    # accidental key here is both a cost and a privacy regression.

    def test_consumer_signup_issues_no_api_key(self):
        # The assertion that matters. create_api_key is patched to EXPLODE, so
        # this fails loudly if the consumer path ever reaches it, rather than
        # passing on a mock that quietly returned a key nobody inspected.
        def _must_not_run(*a, **k):
            raise AssertionError('consumer signup created an API key')

        captured = {}
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app, 'create_api_key', side_effect=_must_not_run), \
             patch.object(self.app.ddb, 'put_item',
                          side_effect=lambda **kw: captured.update(kw)):
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({
                    'email': 'reader@example.com',
                    'source': 'consumer',
                    'postcode': 'M1 1AE',
                }),
            }, None)
        self.assertEqual(result['statusCode'], 201)
        payload = json.loads(result['body'])
        self.assertEqual(payload['status'], 'subscribed')
        # No key value may appear in a consumer response, under any key name.
        self.assertNotIn('apiKey', payload)
        self.assertNotIn('key', payload)
        # The row records WHERE it came from. Without this the two intents are
        # indistinguishable later, and a marketing list ends up holding people
        # who only ever asked about one postcode.
        item = captured['Item']
        self.assertEqual(item['source']['S'], 'consumer')
        self.assertEqual(item['postcode']['S'], 'M1 1AE')
        self.assertEqual(item['keyId']['S'], '')

    def test_consumer_repeat_visitor_is_not_told_about_api_keys(self):
        # THE PATH A REAL REPEAT VISITOR TAKES, which is not the one the race
        # test below covers. get_existing_signup finds the row and returns it;
        # before the fix that fell into the B2B 409, so a consumer who typed
        # their address twice was told 'A new key cannot be re-issued via this
        # endpoint. Contact support to revoke and re-issue if the original key
        # has been lost.' - about a key they never asked for and do not have.
        #
        # This shipped and the suite stayed green, because the duplicate test
        # patched get_existing_signup to None and drove the RACE branch. Two
        # branches produce 'already exists'; only one of them is common.
        with patch.object(self.app, 'get_existing_signup',
                          return_value={'email': {'S': 'repeat@example.com'}}):
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'repeat@example.com', 'source': 'consumer'}),
            }, None)
        self.assertEqual(result['statusCode'], 200)
        payload = json.loads(result['body'])
        self.assertEqual(payload['status'], 'already-subscribed')
        # The words that must not reach a consumer.
        blob = json.dumps(payload).lower()
        self.assertNotIn('key', blob)
        self.assertNotIn('support', blob)

    def test_b2b_repeat_still_gets_the_key_409(self):
        # The other direction: the consumer fix must not swallow the B2B 409,
        # which is load-bearing - it tells a developer their key exists and
        # cannot be re-shown.
        with patch.object(self.app, 'get_existing_signup',
                          return_value={'email': {'S': 'dev@example.com'}}):
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'dev@example.com'}),
            }, None)
        self.assertEqual(result['statusCode'], 409)
        self.assertIn('already signed up', json.loads(result['body'])['error'])
    def test_consumer_duplicate_reads_as_success_not_error(self):
        # Already subscribed is the outcome they wanted. A 409 would render as
        # 'something went wrong' to someone who is, in fact, on the list.
        from botocore.exceptions import ClientError
        dupe = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'x'}},
            'PutItem',
        )
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app.ddb, 'put_item', side_effect=dupe):
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'dupe@example.com', 'source': 'consumer'}),
            }, None)
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(json.loads(result['body'])['status'], 'already-subscribed')

    def test_unrecognised_source_falls_through_to_the_key_path(self):
        # Opt-in by EXACT match. If a typo or a hostile body could select the
        # consumer branch by accident that would be harmless, but the reverse -
        # defaulting to the key path only on an exact 'api' - would mean a
        # malformed source silently issues an API key to a consumer.
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app, 'create_api_key',
                          return_value=('key-id', 'sk_value')), \
             patch.object(self.app.ddb, 'put_item'):
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'x@example.com', 'source': 'Consumer '}),
            }, None)
        self.assertEqual(result['statusCode'], 201)
        self.assertIn('apiKey', json.loads(result['body']))

    def test_b2b_signup_still_records_its_own_source(self):
        captured = {}
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app, 'create_api_key',
                          return_value=('key-id', 'sk_value')), \
             patch.object(self.app.ddb, 'put_item',
                          side_effect=lambda **kw: captured.update(kw)):
            self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'dev@example.com'}),
            }, None)
        self.assertEqual(captured['Item']['source']['S'], 'api')

    def test_signup_race_revokes_orphan_and_returns_409(self):
        # I-N6: a real-world signup race — get_existing_signup returns None
        # (no prior row), create_api_key succeeds, but record_signup hits
        # ConditionalCheckFailedException because a concurrent request wrote
        # first. The handler must (a) revoke the just-created key (b) return
        # 409 with a clear note, and not leak the key value back to the caller.
        from botocore.exceptions import ClientError
        race_err = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException',
                       'Message': 'attribute_not_exists(email)'}},
            'PutItem',
        )
        # get_api_key/delete_api_key are exercised inside _safe_revoke_orphan_key;
        # mock both and the apigw.create_api_key path.
        with patch.object(self.app, 'get_existing_signup', return_value=None), \
             patch.object(self.app, 'create_api_key',
                          return_value=('key-id-race', 'sk_secret_value')), \
             patch.object(self.app.ddb, 'put_item', side_effect=race_err), \
             patch.object(self.app.apigw, 'get_api_key',
                          return_value={'name': self.app.KEY_NAME_PREFIX + 'race@example.com'}), \
             patch.object(self.app.apigw, 'delete_api_key') as mock_delete:
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'race@example.com'}),
            }, None)
            # 409 for the loser of the race, with our standard error shape.
            self.assertEqual(result['statusCode'], 409)
            payload = json.loads(result['body'])
            self.assertIn('already signed up', payload['error'])
            self.assertIn('rolled', payload.get('note', ''))
            # Crucial: the leaked key was revoked (not left dangling against
            # the per-account 10,000-key APIGW quota).
            mock_delete.assert_called_once_with(apiKey='key-id-race')
            # Crucial: the secret key value is NOT echoed back in the 409.
            self.assertNotIn('sk_secret_value', result['body'])

    # ----- The create path itself (added 2026-07-25) -----
    #
    # Every signup test above this line exercises an ERROR branch. Nothing
    # asserted that a well-formed signup actually produced a key, so when
    # the SignupFunction IAM policy stopped permitting CreateUsagePlanKey
    # in dab713d (2026-05-07), the whole self-service B2B funnel returned
    # 503 to every visitor for two and a half months and the suite stayed
    # green throughout. The three tests below pin the create path: the
    # 201 shape, the rollback when the usage-plan link fails, and what the
    # duplicate-email 409 is allowed to disclose.
    #
    # Caveat worth keeping in mind: boto3 is mocked here, so these cannot
    # detect an IAM denial by themselves. What they lock in is that
    # create_usage_plan_key is called at all, with the resolved plan and
    # the new key, and that a failure of that call can never be mistaken
    # for success. The IAM half needs a post-deploy smoke test.

    def _usage_plan_paginator(self):
        """A get_paginator stand-in yielding one page holding the free-tier
        plan, so resolve_usage_plan_id() runs for real rather than being
        stubbed out — the resolved id is then asserted on the link call."""
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {'items': [
                {'id': 'plan-other', 'name': 'SomeOtherPlan'},
                {'id': 'plan-free-tier', 'name': self.app.USAGE_PLAN_NAME},
            ]},
        ]
        return paginator

    def test_post_valid_email_returns_201_with_key_and_writes_audit_row(self):
        # THE test whose absence let the outage run: a well-formed signup
        # must create a key, link it to the free-tier usage plan, write the
        # audit row, and return 201 with the key value shown once.
        with patch.object(self.app, '_usage_plan_id_cache', None), \
             patch.object(self.app.apigw, 'get_paginator',
                          return_value=self._usage_plan_paginator()), \
             patch.object(self.app.apigw, 'create_api_key',
                          return_value={'id': 'key-new', 'value': 'sk_live_value'}) as mock_create, \
             patch.object(self.app.apigw, 'create_usage_plan_key') as mock_link, \
             patch.object(self.app.ddb, 'get_item', return_value={}), \
             patch.object(self.app.ddb, 'put_item') as mock_put:
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'New.User@Example.com', 'name': 'New User'}),
            }, None)

        self.assertEqual(result['statusCode'], 201)
        payload = json.loads(result['body'])
        # The key value is returned exactly once, here — APIGW will not
        # re-show it, so a 201 that omits it is unrecoverable for the user.
        self.assertEqual(payload['apiKey'], 'sk_live_value')
        self.assertEqual(payload['keyId'], 'key-new')
        self.assertEqual(payload['usagePlan'], 'SkyScoreFreeTier')

        # Key is enabled and carries the CreatedBy tag the IAM DELETE
        # condition matches on (audit N-Code-1) — drop the tag and this
        # Lambda loses the ability to revoke its own orphans.
        self.assertTrue(mock_create.call_args.kwargs['enabled'])
        self.assertEqual(mock_create.call_args.kwargs['tags'],
                         {self.app.KEY_TAG_KEY: self.app.KEY_TAG_VALUE})

        # The usage-plan link is the step that was failing in production.
        # Without it the key authenticates but has no quota, so /v1/score
        # rejects it with InvalidKeyParameter.
        mock_link.assert_called_once_with(
            usagePlanId='plan-free-tier', keyId='key-new', keyType='API_KEY',
        )

        # Audit row written under the lower-cased email, with the keyId
        # needed to trace a key back to its owner for support revokes.
        mock_put.assert_called_once()
        self.assertEqual(mock_put.call_args.kwargs['TableName'], self.app.SIGNUPS_TABLE)
        item = mock_put.call_args.kwargs['Item']
        self.assertEqual(item['email']['S'], 'new.user@example.com')
        self.assertEqual(item['keyId']['S'], 'key-new')

    def test_usage_plan_link_failure_revokes_orphan_and_returns_503(self):
        # The exact production failure: CreateUsagePlanKey denied by IAM
        # after CreateApiKey has already minted an ENABLED key. The caller
        # must get a 503 (never a 201 for an unusable key) and the orphan
        # must be revoked rather than left against the per-account
        # 10,000-key APIGW quota.
        from botocore.exceptions import ClientError
        denied = ClientError(
            {'Error': {'Code': 'AccessDeniedException',
                       'Message': 'not authorized to perform: apigateway:POST'}},
            'CreateUsagePlanKey',
        )
        with patch.object(self.app, '_usage_plan_id_cache', None), \
             patch.object(self.app.apigw, 'get_paginator',
                          return_value=self._usage_plan_paginator()), \
             patch.object(self.app.apigw, 'create_api_key',
                          return_value={'id': 'key-orphan', 'value': 'sk_never_usable'}), \
             patch.object(self.app.apigw, 'create_usage_plan_key', side_effect=denied), \
             patch.object(self.app.apigw, 'get_api_key',
                          return_value={'name': self.app.KEY_NAME_PREFIX + 'orphan_at_example_com'}), \
             patch.object(self.app.apigw, 'delete_api_key') as mock_delete, \
             patch.object(self.app.ddb, 'get_item', return_value={}), \
             patch.object(self.app.ddb, 'put_item') as mock_put:
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'orphan@example.com'}),
            }, None)

        self.assertEqual(result['statusCode'], 503)
        payload = json.loads(result['body'])
        # The upstream code is surfaced so this is diagnosable from the
        # response alone — that is how the outage was finally identified.
        self.assertEqual(payload['code'], 'AccessDeniedException')
        # Rollback fired: no orphan key survives the failed signup.
        mock_delete.assert_called_once_with(apiKey='key-orphan')
        # No audit row for a signup that never completed, otherwise the
        # user is locked out by their own failed attempt (409 forever).
        mock_put.assert_not_called()
        # The unusable key value must not leak to the caller.
        self.assertNotIn('sk_never_usable', result['body'])

    def test_duplicate_email_409_does_not_disclose_created_at(self):
        # /v1/signup is unauthenticated by design, so the duplicate-email
        # 409 must not become an oracle: anyone who guesses an address
        # would otherwise learn when its owner registered. createdAt stays
        # on the DynamoDB row for support, out of the response body.
        existing = {
            'email': {'S': 'dupe@example.com'},
            'keyId': {'S': 'key-original'},
            'createdAt': {'S': '2026-05-08T09:15:00+00:00'},
        }
        with patch.object(self.app.ddb, 'get_item', return_value={'Item': existing}), \
             patch.object(self.app.apigw, 'create_api_key') as mock_create:
            result = self.app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'dupe@example.com'}),
            }, None)

        self.assertEqual(result['statusCode'], 409)
        payload = json.loads(result['body'])
        self.assertEqual(set(payload), {'error', 'note'})
        # Belt and braces: neither the timestamp nor the original keyId
        # appears anywhere in the raw body, whatever key it were nested under.
        self.assertNotIn('createdAt', result['body'])
        self.assertNotIn('2026-05-08', result['body'])
        self.assertNotIn('key-original', result['body'])
        # No second key minted for an address that already has one — that
        # would burn the per-account quota on every duplicate submit.
        mock_create.assert_not_called()


# ---------- NHS, lat/lon validation, fallback shape ----------

class NhsHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('nhs')

    def test_missing_params_returns_400(self):
        result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 400)

    def test_non_numeric_returns_400(self):
        result = self.app.handler(
            {'queryStringParameters': {'lat': 'abc', 'lon': 'def'}}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_lat_out_of_range_returns_400(self):
        result = self.app.handler(
            {'queryStringParameters': {'lat': '999', 'lon': '0'}}, None,
        )
        self.assertEqual(result['statusCode'], 400)

    def test_partition_results_groups_by_amenity(self):
        elements = [
            {'type': 'node', 'lat': 51.5, 'lon': -0.1,
             'tags': {'amenity': 'hospital', 'name': 'St Bart\'s'}},
            {'type': 'node', 'lat': 51.51, 'lon': -0.11,
             'tags': {'amenity': 'pharmacy', 'name': 'Boots'}},
            {'type': 'node', 'lat': 51.52, 'lon': -0.12,
             'tags': {'amenity': 'doctors', 'name': 'GP Surgery'}},
        ]
        out = self.app.partition_results(elements, 51.5, -0.1)
        self.assertEqual(len(out['hospitals']), 1)
        self.assertEqual(len(out['pharmacies']), 1)
        self.assertEqual(len(out['gp']), 1)


# ---------- Sold Prices, postcode validation ----------

class SoldPricesHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('sold_prices')

    def test_missing_postcode_returns_400(self):
        result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 400)


# ---------- Transport, lat/lon validation ----------

class TransportHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('transport')

    def test_missing_params_returns_400(self):
        result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 400)

    def test_lat_out_of_range_returns_400(self):
        result = self.app.handler(
            {'queryStringParameters': {'lat': '200', 'lon': '0'}}, None,
        )
        self.assertEqual(result['statusCode'], 400)


# ChatHandlerTests / MultiAgentHandlerTests / ReportHandlerTests removed
# 2026-05-07 along with their Lambda directories. All five Bedrock-backed
# Lambdas (chat, multi_agent, analyze_image, analyze_document, report)
# were deleted; restoring is a `git revert` away. See LICENSING.md
# "Removed sources" / CHANGELOG for context.


# ---------- EPC, validation ----------

class EpcHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = _import_lambda('epc')

    def test_missing_postcode_returns_400(self):
        result = self.app.handler({'queryStringParameters': None}, None)
        self.assertEqual(result['statusCode'], 400)

    def _invoke_with_upstream_status(self, status):
        """Drive the handler with a token set and a chosen upstream HTTP error."""
        from urllib.error import HTTPError  # noqa: PLC0415

        err = HTTPError('https://example.invalid', status, 'err', {}, None)
        with patch.dict(os.environ, {'EPC_BEARER_TOKEN': 'test-token'}), \
             patch.object(self.app, 'urlopen', side_effect=err):
            return self.app.handler(
                {'queryStringParameters': {'postcode': 'SW1A 1AA'}}, None
            )

    def test_rejected_token_degrades_gracefully(self):
        """MHCLG answers 403 — not 401 — for a rejected bearer token.

        Verified against the live service 2026-07-26. Both must degrade to a
        200 with available=False so the EPC panel hides quietly; falling
        through to the generic 502 breaks the whole property page, which is
        precisely what this branch exists to prevent. 401 is kept alongside
        403 because the upstream contract is not ours to assume.
        """
        for status in (401, 403):
            with self.subTest(status=status):
                result = self._invoke_with_upstream_status(status)
                self.assertEqual(result['statusCode'], 200)
                body = json.loads(result['body'])
                self.assertFalse(body['available'])
                self.assertIn('token', body['message'].lower())

    def test_other_upstream_errors_still_surface_as_502(self):
        """The graceful branch must not swallow unrelated upstream failures."""
        result = self._invoke_with_upstream_status(500)
        self.assertEqual(result['statusCode'], 502)

    def test_upstream_404_means_no_certificates_not_an_error(self):
        """404 is 'no certificates match' per the MHCLG docs, not a failure."""
        result = self._invoke_with_upstream_status(404)
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertTrue(body['available'])
        self.assertEqual(body['count'], 0)


class NhsEmptyBundleTests(unittest.TestCase):
    """Audit finding I10, fixed 2026-08-22.

    `in_bundle_area()` tests a bounding box that reaches far outside the
    snapshot's real coverage. Measured over a 24x24 grid of that rectangle,
    35.4% of points had nothing within 1500 m and were published as
    `available: true` with three empty lists - an assertion of absence built
    from missing data. The Overpass branch, facing the same gap, returns
    fallback links and `available: false`.
    """

    def setUp(self):
        self.app = _import_lambda('nhs')

    def _call(self, lat, lon):
        result = self.app.handler(
            {'queryStringParameters': {'lat': str(lat), 'lon': str(lon)}}, None
        )
        self.assertEqual(result['statusCode'], 200)
        return json.loads(result['body'])

    def _first_uncovered_point(self):
        """A point inside the bbox that the snapshot cannot serve.

        DERIVED by scanning, not hardcoded. The bbox corner is NOT reliably
        empty - the first version of this test assumed it was and failed - and
        any fixed pair would rot the next time the snapshot is regenerated by
        scripts/fetch_london_healthcare.py.
        """
        bundle = self.app._load_bundle()
        if not bundle:
            self.skipTest('bundle not present')
        min_lat, min_lon, max_lat, max_lon = bundle['bbox']
        steps = 12
        for i in range(steps):
            for j in range(steps):
                lat = min_lat + (max_lat - min_lat) * i / (steps - 1)
                lon = min_lon + (max_lon - min_lon) * j / (steps - 1)
                if not any(self.app.from_bundle(lat, lon).values()):
                    return lat, lon
        self.skipTest('every sampled point inside the bbox is covered')
        return None

    def test_an_uncovered_point_does_not_claim_to_have_looked(self):
        """Inside the rectangle, outside the coverage: must not assert absence."""
        min_lat, min_lon = self._first_uncovered_point()
        # Overpass is stubbed out so the test cannot depend on the network; the
        # handler must land on the honest fallback rather than the confident
        # empty snapshot.
        with patch.object(self.app, 'query_overpass', side_effect=TimeoutError('no net')):
            body = self._call(min_lat, min_lon)
        self.assertFalse(body['available'])
        self.assertNotEqual(body.get('dataSource'), 'bundled-snapshot')
        self.assertTrue(body['gp'], 'fallback links must be offered')

    def test_central_london_still_answers_from_the_snapshot(self):
        """The other direction: real coverage must not start hitting the network."""
        with patch.object(self.app, 'query_overpass', side_effect=AssertionError(
            'central London must be served from the bundle, not Overpass'
        )):
            body = self._call(51.5152, -0.1418)
        self.assertTrue(body['available'])
        self.assertEqual(body['dataSource'], 'bundled-snapshot')
        self.assertTrue(body['gp'] or body['pharmacies'] or body['hospitals'])


class ChangesCachingTests(unittest.TestCase):
    """Audit finding I2, fixed 2026-08-22.

    `/v1/changes` is UNAUTHENTICATED and rebuilt a 114 KB body on every call -
    66 calc_score() runs, two benchmark passes, two growth-rank passes and 33
    attribution builds - to return bytes that are identical within a
    deployment. Anyone could pull that repeatedly.

    The cache must not freeze `generatedAt`, which is the one field that is
    genuinely per-response; a payload claiming it was generated at container
    start would mislead exactly the caller who checks freshness.
    """

    def setUp(self):
        self.app = _import_lambda('score')
        self.app._CHANGES_BODY = None  # cold container

    def _body(self):
        result = self.app.handle_changes({})
        self.assertEqual(result['statusCode'], 200)
        return result, json.loads(result['body'])

    def test_the_payload_is_stable_apart_from_the_timestamp(self):
        first_raw, first = self._body()
        second_raw, second = self._body()
        self.assertTrue(first['changes'], 'no changes computed - nothing is being cached')
        self.assertEqual(len(first['changes']), 33)
        del first['generatedAt'], second['generatedAt']
        self.assertEqual(first, second)
        self.assertEqual(first_raw['statusCode'], second_raw['statusCode'])

    def test_generated_at_is_stamped_per_response_not_cached(self):
        self._body()
        cached = self.app._CHANGES_BODY
        self.assertIsNotNone(cached, 'the body was never memoised')
        self.assertNotIn(
            'generatedAt', cached,
            'generatedAt was cached with the body, so every later response '
            'reports the container start time as its generation time',
        )
        _, body = self._body()
        self.assertIn('generatedAt', body)

    def test_the_response_tells_caches_they_may_keep_it(self):
        result, _ = self._body()
        self.assertIn('Cache-Control', result['headers'])
        self.assertIn('max-age=', result['headers']['Cache-Control'])

    def test_cors_headers_survive_the_extra_header_argument(self):
        """response() gained a headers parameter; the defaults must still apply."""
        result, _ = self._body()
        self.assertIn('Content-Type', result['headers'])
        self.assertTrue(
            any(h.lower().startswith('access-control-') for h in result['headers']),
            'CORS headers were lost when the Cache-Control header was added',
        )


class ApiGatewayTimeoutCapTests(unittest.TestCase):
    """Audit finding I3, fixed 2026-08-22.

    Every function in this template is a SYNCHRONOUS API Gateway integration,
    and APIGW terminates those at 29 seconds. A Lambda timeout above that is
    budget no caller can receive: we keep paying, they already got a 504.

    It is not only cost. `/nhs` catches a slow Overpass and returns NHS search
    links with `available: false`; at Timeout: 45 that branch could not run
    inside the caller window at all, so a slow upstream produced a raw gateway
    error instead of the degraded answer the code exists to give. Raising a
    timeout past the cap silently disables the fallback beneath it.
    """

    TEMPLATE = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'template.yaml'))

    # API Gateway REST integration hard limit. Not ours to raise.
    APIGW_INTEGRATION_CAP = 29

    @classmethod
    def setUpClass(cls):
        import re  # noqa: PLC0415

        with open(cls.TEMPLATE, encoding='utf-8') as handle:
            cls.text = handle.read()
        # Textual, for the reason FreeTierQuotaDriftTests records: the template
        # is full of CFN intrinsics that safe_load rejects.
        cls.timeouts = [int(m) for m in re.findall(r'^\s*Timeout:\s*(\d+)',
                                                   cls.text, re.MULTILINE)]

    def test_the_scan_found_something(self):
        """A regex that matches nothing would make every assertion below vacuous."""
        self.assertGreaterEqual(
            len(self.timeouts), 4,
            'no Timeout: lines parsed - this gate would pass on any template',
        )

    def test_no_timeout_exceeds_what_api_gateway_will_wait_for(self):
        over = [t for t in self.timeouts if t > self.APIGW_INTEGRATION_CAP]
        self.assertEqual(
            over, [],
            f'Timeout values {over} exceed the API Gateway '
            f'{self.APIGW_INTEGRATION_CAP}s integration cap. The excess is '
            'unreachable by any caller and disables any in-handler fallback '
            'that would have run inside the window.',
        )

    def test_the_global_default_is_also_under_the_cap(self):
        """The default applies to every function that does not override it."""
        head = self.text[: self.text.index('Resources:')]
        self.assertIn('Timeout: 28', head, 'Globals default drifted above the cap')


class EpcUnknownBandTests(unittest.TestCase):
    """Audit finding I9, fixed 2026-08-22.

    An EPC band we cannot parse must publish NOTHING, never the worst reading
    on the scale. Two lookups of the same value disagreed: `BAND_MIDPOINT[band]`
    inside `if band in bands` was guarded, and `BAND_MIDPOINT.get(band, 0)` ten
    lines below was not - the mirrored-code shape this repo has recorded three
    times. 0 is below every real certificate on a 1-100 scale, and
    `rating_to_band(0)` is 'G', so an unparsed postcode reported itself as
    worse than any genuine G-rated home.
    """

    def setUp(self):
        self.app = _import_lambda('epc')

    def _run(self, rows):
        payload = json.dumps({'rows': rows}).encode()
        resp = MagicMock()
        resp.read.return_value = payload
        resp.__enter__ = lambda self_: self_
        resp.__exit__ = lambda *a: False
        with (
            patch.dict(os.environ, {'EPC_BEARER_TOKEN': 't'}),
            patch.object(self.app, 'urlopen', return_value=resp),
        ):
            result = self.app.handler(
                {'queryStringParameters': {'postcode': 'SW1A 1AA'}}, None
            )
        self.assertEqual(result['statusCode'], 200)
        return json.loads(result['body'])

    def test_unknown_band_publishes_no_rating_rather_than_zero(self):
        body = self._run([{'currentEnergyRating': 'Z', 'addressLine1': '1 Test St'}])
        self.assertIsNone(body['certificates'][0]['rating'])

    def test_a_known_band_still_carries_its_midpoint(self):
        """The other direction: the guard must not blank real data."""
        body = self._run([{'currentEnergyRating': 'C', 'addressLine1': '1 Test St'}])
        self.assertEqual(body['certificates'][0]['rating'], 75)

    def test_no_recognisable_band_gives_no_average_not_a_G(self):
        body = self._run([
            {'currentEnergyRating': 'Z', 'addressLine1': '1 Test St'},
            {'currentEnergyRating': '', 'addressLine1': '2 Test St'},
        ])
        self.assertIsNone(body['summary']['averageRating'])
        self.assertEqual(body['summary']['averageBand'], 'N/A')
        # mostCommonBand already used this convention; the two now agree.
        self.assertEqual(body['summary']['mostCommonBand'], 'N/A')

    def test_a_real_G_is_still_reported_as_G(self):
        """'G' must stay reachable, or the fix has hidden a true worst case."""
        body = self._run([{'currentEnergyRating': 'G', 'addressLine1': '1 Test St'}])
        self.assertEqual(body['summary']['averageBand'], 'G')
        self.assertEqual(body['summary']['averageRating'], 10)


class FreeTierQuotaDriftTests(unittest.TestCase):
    """The free-tier numbers exist in five places and only one is enforced.

    API Gateway enforces `ScoreFreeUsagePlan` in template.yaml. The signup
    Lambda's 201 response, pricing.html, api/index.html and openapi.yaml only
    *describe* it, and none can read the plan at runtime. Before 2026-07-29 the
    Lambda had drifted to advertising 1000 req/month against a plan being cut
    to 100 — a customer-facing lie that every existing test passed straight
    through, because nothing asserted the numbers at all.

    These tests fail loudly rather than skipping when the template cannot be
    read. A drift gate that quietly skips is the failure mode from the 27 Jul
    audit: green because it ran nothing.
    """

    TEMPLATE = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'template.yaml'))

    @classmethod
    def setUpClass(cls):
        import re  # noqa: PLC0415
        # Read the plan block textually rather than with a YAML parser: the
        # template is full of CFN intrinsics (!Ref, !GetAtt) that safe_load
        # rejects, and adding a custom loader is more machinery than a
        # three-integer assertion needs.
        with open(cls.TEMPLATE, encoding='utf-8') as handle:
            text = handle.read()
        start = text.index('  ScoreFreeUsagePlan:')
        end = text.index('  ScoreFreeUsagePlanKey:', start)
        cls.plan = text[start:end]

        # The DEMO plan is a THIRD published figure and the pages quote it.
        # Without it here, a page stating the demo key's real 2,000/month
        # reds this gate, and the tempting fix is to hardcode 2000 into
        # `allowed` - which is how a drift gate stops tracking the template
        # it exists to track. Read it from the same file as the other two.
        dstart = text.index('  ScoreDemoUsagePlan:')
        # Bounded by the NEXT top-level resource, not a named one: the demo
        # plan has no ...Key sibling, and hardcoding whatever happens to follow
        # it makes this gate break the next time a resource is inserted.
        dnext = re.search(r'^  [A-Za-z][A-Za-z0-9]*:$', text[dstart + 1:], re.MULTILINE)
        assert dnext, 'ScoreDemoUsagePlan is the last resource - bound it explicitly'
        cls.demo_plan = text[dstart:dstart + 1 + dnext.start()]

    def _plan_int(self, field, block=None):
        """Read a PLAN-LEVEL throttle/quota integer.

        Deliberately the LAST match, not the first. From 2026-08-21 the plan
        carries a per-method deny (`/v1/score/batch/POST: RateLimit: 0`) inside
        ApiStages, ABOVE the plan-level Throttle - so a first-match read returned
        0 and this gate failed claiming the response advertised a rate the plan
        did not enforce. The plan-level block is last in the resource, and it is
        the one a caller actually experiences on the routes they can reach.
        """
        import re  # pylint: disable=import-outside-toplevel
        matches = re.findall(rf'^\s*{field}:\s*(\d+)\s*$', block if block is not None else self.plan, re.MULTILINE)
        match = matches[-1] if matches else None
        self.assertIsNotNone(
            match, f'{field} not found in ScoreFreeUsagePlan — the block was '
                   'renamed or restructured, so this gate is no longer '
                   'checking anything. Fix the test, do not delete it.')
        return int(match)

    def _signup_body(self):
        app = _import_lambda('signup')
        with patch.object(app, '_usage_plan_id_cache', None), \
             patch.object(app.apigw, 'get_paginator') as mock_pag, \
             patch.object(app.apigw, 'create_api_key',
                          return_value={'id': 'k', 'value': 'v'}), \
             patch.object(app.apigw, 'create_usage_plan_key'), \
             patch.object(app.ddb, 'get_item', return_value={}), \
             patch.object(app.ddb, 'put_item'):
            paginator = MagicMock()
            paginator.paginate.return_value = [
                {'items': [{'id': 'plan-free-tier', 'name': 'SkyScoreFreeTier'}]}]
            mock_pag.return_value = paginator
            result = app.handler({
                'httpMethod': 'POST',
                'body': json.dumps({'email': 'drift@example.com'}),
            }, None)
        self.assertEqual(result['statusCode'], 201)
        return json.loads(result['body'])

    def _signup_limits(self):
        return self._signup_body()['limits']

    def test_signup_response_matches_the_enforced_usage_plan(self):
        limits = self._signup_limits()
        self.assertEqual(limits['monthlyQuota'], self._plan_int('Limit'))
        self.assertEqual(limits['sustainedRateLimit'], self._plan_int('RateLimit'))
        self.assertEqual(limits['burstLimit'], self._plan_int('BurstLimit'))

    def test_batch_multiplier_follows_whether_the_plan_can_batch(self):
        # The multiplier is what turns a request quota into a score ceiling, so
        # if it is wrong the advertised ceiling is wrong in someone's favour.
        #
        # It used to assert `== MAX_BATCH_SIZE` unconditionally, which was right
        # while every plan could batch. From 2026-08-21 the free plan denies
        # /v1/score/batch per-method, so its real multiplier is 1 and asserting
        # 100 would be asserting an entitlement the gateway refuses.
        #
        # DERIVED FROM THE TEMPLATE, not restated: the expected value is read
        # from whether the deny is present, so this cannot be satisfied by
        # editing a number to match. Removing the deny without restoring the
        # multiplier fails, and vice versa.
        denies_batch = '/v1/score/batch/POST:' in self.plan
        expected = 1 if denies_batch else _import_lambda('score').MAX_BATCH_SIZE
        self.assertEqual(
            self._signup_limits()['batchMultiplier'], expected,
            'the advertised multiplier disagrees with what the plan enforces')

    # ---- The published PAGES, which nothing here had ever read ----------
    #
    # This class opens by saying the free-tier numbers live in five places and
    # only one is enforced - and then asserted exactly one of the other four,
    # the signup Lambda. On 2026-08-22 score-demo/index.html was found still
    # advertising "100 requests / month, 5 burst, 1 sustained" and a working
    # batch multiplier: the pre-2026-08-21 figures, 100x under the real quota,
    # on the page a prospect uses to TRY the API. Every gate was green.
    #
    # These read the pages the same way the signup test reads the Lambda.

    REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    # Published as a fair-use ceiling for Professional. Not in template.yaml
    # because API Gateway does not enforce it - see the open decision in
    # ROADMAP.md. Listed here so a page quoting it is not read as drift.
    PROFESSIONAL_REQUESTS = 100000

    QUOTA_PAGES = (
        'pricing.html',
        'api/index.html',
        'score-demo/index.html',
        'score-demo/openapi.yaml',
    )

    def _page(self, rel):
        with open(os.path.join(self.REPO, rel), encoding='utf-8') as handle:
            return handle.read()

    def test_every_published_request_figure_matches_a_real_limit(self):
        """No page may quote a request quota that is not one we actually offer."""
        import re  # noqa: PLC0415

        allowed = {self._plan_int('Limit'), self.PROFESSIONAL_REQUESTS, self._plan_int('Limit', self.demo_plan)}

        def as_int(digits, suffix):
            """"100k" is a published figure and must be CHECKED, not skipped."""
            return int(digits.replace(',', '')) * (1000 if suffix else 1)

        found_any = False
        for rel in self.QUOTA_PAGES:
            # ABBREVIATIONS COUNT. This matched "N requests" only, so
            # api/index.html could carry "Free - 100 req/mo" in its price line
            # while its own body two lines below said "10,000 requests a
            # month" - a card contradicting itself by 100x, on the B2B funnel
            # page, with this gate green throughout (found 2026-08-27; the
            # enforced plan reads 10,000 from the live API). A drift gate that
            # only reads the long form is checking the WORDING, not the number.
            pattern = r'([\d,]+)\s*(k?)\s*(?:requests|req/mo|req/month)'
            for digits, suffix in re.findall(pattern, self._page(rel)):
                found_any = True
                value = as_int(digits, suffix)
                self.assertIn(
                    value, allowed,
                    f'{rel} advertises "{digits}{suffix} requests" ({value:,}), which '
                    f'is neither the enforced free quota ({self._plan_int("Limit"):,}) '
                    f'nor the published Professional ceiling ({self.PROFESSIONAL_REQUESTS:,})',
                )
        self.assertTrue(
            found_any,
            'no "N requests" phrase found on any page - the wording changed and '
            'this gate is now checking nothing. Fix the pattern, do not delete it.',
        )

    def test_no_page_promises_batch_on_the_free_tier(self):
        """The plan denies /v1/score/batch per-method; the pages must agree.

        score-demo/index.html told free-tier users a batch request "carries up
        to 100 addresses and counts as one request" for a day after the deny
        shipped - an entitlement the gateway answers with 429.
        """
        if '/v1/score/batch/POST:' not in self.plan:
            self.skipTest('free plan no longer denies batch; this claim would be true')
        for rel in ('score-demo/index.html', 'pricing.html', 'api/index.html'):
            text = self._page(rel).lower()
            self.assertNotIn(
                'batch request carries up to 100 addresses and counts as one request',
                text,
                f'{rel} still sells free-tier batch, which the usage plan denies',
            )

    def test_score_ceiling_is_the_product_of_the_two(self):
        limits = self._signup_limits()
        self.assertEqual(limits['monthlyScoreCeiling'],
                         limits['monthlyQuota'] * limits['batchMultiplier'])

    def test_gate_can_actually_fail(self):
        # Proves the template read works and is not silently returning a
        # default. Per the 27 Jul lesson: assert the gate can go red.
        #
        # Restored 2026-08-04. The assertRaises block below was orphaned into
        # test_both_tiers_are_quoted_in_the_same_unit when the Professional
        # tests were inserted mid-method, leaving this test asserting only
        # `Limit > 0` while its comment still promised the gate could go red.
        # It would have passed even if _plan_int started returning a default on
        # a miss, which is the precise failure it exists to catch.
        self.assertGreater(self._plan_int('Limit'), 0)
        with self.assertRaises(AssertionError):
            self._plan_int('NoSuchField')

    # --- Professional upgrade block, added 2026-08-04 -------------------
    # Completing BATCH_METERING_DECISION.md's 2026-07-29 decision. The same
    # three assertions the free tier already carries, because the defect the
    # decision fixed was arithmetic nobody had done: quoting a request quota
    # while selling scores let the real entitlement sit at 100x the number on
    # the page. An unmultiplied figure is exactly how that recurs.

    def test_upgrade_block_states_the_professional_ceiling(self):
        upgrade = self._signup_body()['upgrade']
        self.assertEqual(upgrade['tier'], 'Professional')
        self.assertEqual(upgrade['monthlyQuota'], 100000)
        self.assertEqual(upgrade['monthlyScoreCeiling'], 1000000)

    def test_upgrade_multiplier_matches_the_score_lambda(self):
        # Same coupling as the free tier: if MAX_BATCH_SIZE moves and this
        # does not, the published ceiling silently becomes wrong.
        upgrade = self._signup_body()['upgrade']
        self.assertEqual(upgrade['batchMultiplier'],
                         _import_lambda('score').MAX_BATCH_SIZE)

    def test_openapi_signup_schema_matches_what_the_lambda_returns(self):
        """The published spec must describe the actual 201 body.

        Added 2026-08-04 after a review found the spec had not been updated
        when `scoreCeilingBasis` and the whole `upgrade` block were added to the
        Lambda in the same change that edited this very file for other reasons.
        Nothing caught it: OpenAPI 3.0 does not enforce `additionalProperties`,
        so clients keep deserialising fine while generated SDKs silently omit
        the fields and Swagger UI shows a stale example.

        This asserts COVERAGE, not behaviour — the same gap that let `impact` go
        unguarded in the score Lambda. A spec is a list of things it describes,
        and lists are where these decay.
        """
        try:
            import yaml  # pylint: disable=import-outside-toplevel
        except ImportError:
            self.skipTest('PyYAML not installed')

        spec_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'score-demo', 'openapi.yaml')
        with open(os.path.abspath(spec_path), encoding='utf-8') as handle:
            spec = yaml.safe_load(handle)

        schema = (spec['paths']['/v1/signup']['post']['responses']['201']
                  ['content']['application/json']['schema'])
        body = self._signup_body()

        for key in body:
            with self.subTest(field=key):
                self.assertIn(
                    key, schema['properties'],
                    f'/v1/signup returns {key!r} but the OpenAPI 201 schema '
                    f'does not describe it. Generated SDKs will drop it.')

        for block in ('limits', 'upgrade'):
            declared = set(schema['properties'][block]['properties'])
            returned = set(body[block])
            with self.subTest(block=block):
                self.assertEqual(
                    returned - declared, set(),
                    f'{block} returns fields absent from the spec: '
                    f'{sorted(returned - declared)}')

    def test_upgrade_ceiling_is_a_cap_BELOW_the_product_not_equal_to_it(self):
        # This assertion was written backwards first time and the test caught
        # it. Professional's ceiling is NOT quota x multiplier: that product is
        # 10,000,000, which is what a £499 key could technically drain and what
        # undercut the £12,000 Enterprise floor. 1,000,000 is a deliberate
        # contractual cap at a tenth of it. Asserting equality here would
        # silently re-authorise the 10x giveaway the 2026-07-29 decision closed.
        upgrade = self._signup_body()['upgrade']
        product = upgrade['monthlyQuota'] * upgrade['batchMultiplier']
        self.assertLess(
            upgrade['monthlyScoreCeiling'], product,
            'Professional ceiling is meant to sit BELOW quota x multiplier. '
            f'Got {upgrade["monthlyScoreCeiling"]:,} against a product of '
            f'{product:,}.')
        self.assertEqual(upgrade['scoreCeilingBasis'], 'fair-use')

    def test_the_two_tiers_ceilings_are_different_KINDS_of_number(self):
        # Free is an arithmetic identity; Professional is a contractual cap.
        # A client that reads both as the same kind will compute the wrong
        # entitlement, which is the exact failure the decision documented.
        body = self._signup_body()
        self.assertEqual(body['limits']['scoreCeilingBasis'], 'quota')
        self.assertEqual(body['upgrade']['scoreCeilingBasis'], 'fair-use')

    def test_both_tiers_are_quoted_in_the_same_unit(self):
        # The decision's core point: a developer comparing tiers must not have
        # to multiply anything themselves. Both blocks carry all three fields.
        body = self._signup_body()
        for block in (body['limits'], body['upgrade']):
            for field in ('monthlyQuota', 'batchMultiplier',
                          'monthlyScoreCeiling'):
                self.assertIn(field, block)


if __name__ == '__main__':
    unittest.main()


class ChatGroundingTests(unittest.TestCase):
    """verify_answer is the control that makes the chat endpoint safe.

    The system prompt ASKS the model not to invent figures. This checks whether
    it did. Without it the endpoint is a free-form assistant with a polite
    request attached, which is the thing 6bad8ce removed.

    The canonical failure: on 2026-08-03 Barking's crime rate in this repo was
    corrected from 105 to 84.2 against ONS Table C4. A model that answers "about
    105 per 1,000" undoes that in one sentence, fluently.
    """

    @staticmethod
    def _chat():
        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[1] / 'lambdas' / 'chat' / 'app.py'
        spec = importlib.util.spec_from_file_location('chat_app', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    CONTEXT = {
        'total': 7.2,
        'components': {'quiet': 8.1, 'afford': 4.0},
        'context': {'avgPriceGbp': 465000},
    }

    def test_figures_present_in_context_are_grounded(self):
        chat = self._chat()
        ok, bad = chat.verify_answer('It scores 7.2, quiet 8.1, average £465,000.', self.CONTEXT)
        self.assertTrue(ok)
        self.assertEqual(bad, [])

    def test_invented_crime_rate_is_caught(self):
        chat = self._chat()
        ok, bad = chat.verify_answer('Crime is around 105 per 1,000 residents.', self.CONTEXT)
        self.assertFalse(ok)
        self.assertIn('105', bad)

    def test_invented_price_is_caught(self):
        chat = self._chat()
        ok, bad = chat.verify_answer('Homes here average about £512,000.', self.CONTEXT)
        self.assertFalse(ok)
        self.assertIn('512000', bad)

    def test_prose_without_numbers_is_grounded(self):
        chat = self._chat()
        ok, _ = chat.verify_answer('Quiet is the strongest component here.', self.CONTEXT)
        self.assertTrue(ok)

    def test_small_ordinals_do_not_trip_the_check(self):
        # "2 or 3 sentences" style phrasing would otherwise flag constantly, and
        # a check that fires on everything stops being read.
        chat = self._chat()
        ok, _ = chat.verify_answer('There are 3 things worth noting.', self.CONTEXT)
        self.assertTrue(ok)


class NhsBundleTests(unittest.TestCase):
    """London healthcare is served from a bundled snapshot, not a live call.

    /nhs proxied Overpass per request and kept returning nhs.uk fallback links.
    The query was fine - it returns 200 in ~2s from a laptop. Lambda egress uses
    AWS-managed shared IPs, so we compete for Overpass's per-IP budget with all
    of AWS. Shipping the data removes the dependency rather than tuning it.
    """

    @staticmethod
    def _nhs():
        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[1] / 'lambdas' / 'nhs' / 'app.py'
        spec = importlib.util.spec_from_file_location('nhs_app', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_london_is_inside_the_bundle(self):
        nhs = self._nhs()
        self.assertTrue(nhs.in_bundle_area(51.49423, -0.18825))  # SW5
        self.assertTrue(nhs.in_bundle_area(51.4713, -0.1580))    # SW11

    def test_outside_london_falls_through_to_live(self):
        # The extension's Manchester case. Must NOT be answered from a London
        # snapshot, which would report London facilities as nearby.
        nhs = self._nhs()
        self.assertFalse(nhs.in_bundle_area(53.4772, -2.2497))

    def test_bundle_returns_real_named_results(self):
        nhs = self._nhs()
        buckets = nhs.from_bundle(51.49423, -0.18825)
        self.assertTrue(buckets['gp'], 'expected GP results in central London')
        self.assertTrue(all(item['name'] for item in buckets['gp']))
        self.assertFalse(any(item.get('fallback') for item in buckets['gp']))

    def test_results_are_sorted_nearest_first(self):
        nhs = self._nhs()
        buckets = nhs.from_bundle(51.49423, -0.18825)
        for key in ('gp', 'pharmacies', 'hospitals'):
            distances = [i['distance'] for i in buckets[key]]
            self.assertEqual(distances, sorted(distances), f'{key} not sorted')

    def test_nothing_beyond_the_search_radius_is_returned(self):
        nhs = self._nhs()
        buckets = nhs.from_bundle(51.49423, -0.18825)
        for key in ('gp', 'pharmacies', 'hospitals'):
            for item in buckets[key]:
                self.assertLessEqual(item['distance'], nhs.SEARCH_RADIUS_M)


class SoldPricesParsingTests(unittest.TestCase):
    """/sold-prices returned an empty list with HTTP 200 for EVERY postcode.

    `.replace(' ', '+')` followed by quote() sent Land Registry the literal
    string "WA2+8SN". It never matched, so the endpoint had never returned a
    transaction - and it looked healthy the whole time, because an empty list is
    indistinguishable from a postcode with no recorded sales.
    """

    @staticmethod
    def _sp():
        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[1] / 'lambdas' / 'sold_prices' / 'app.py'
        spec = importlib.util.spec_from_file_location('sold_prices_app', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_rfc_date_becomes_iso(self):
        # Land Registry sends 'Thu, 17 Oct 1996'. Consumers slice [0:10] for a
        # date, which turned that into 'Thu, 17 Oc'.
        self.assertEqual(self._sp()._iso_date('Thu, 17 Oct 1996'), '1996-10-17')

    def test_unparseable_date_is_passed_through_not_invented(self):
        sp = self._sp()
        self.assertEqual(sp._iso_date('not a date'), 'not a date')
        self.assertEqual(sp._iso_date(''), '')

    def test_property_type_extracts_the_label_not_the_object(self):
        # prefLabel is a LIST OF OBJECTS. Taking [0] returned the dict, which
        # serialised into the response and rendered as "[object Object]".
        sp = self._sp()
        node = {'prefLabel': [{'_value': 'flat-maisonette', '_lang': 'en'}]}
        self.assertEqual(sp._pref_label(node), 'flat-maisonette')

    def test_unknown_property_type_shape_yields_empty_not_a_guess(self):
        sp = self._sp()
        self.assertEqual(sp._pref_label(None), '')
        self.assertEqual(sp._pref_label({}), '')
        self.assertEqual(sp._pref_label({'prefLabel': []}), '')

    def test_request_url_encodes_the_space_not_a_plus(self):
        # THE regression. A '+' here becomes %2B once quoted, which Land Registry
        # reads as a literal plus and matches nothing.
        #
        # First written as an inspect.getsource() scan for "replace(' ', '+')",
        # which failed immediately — the comment explaining the bug quotes the
        # bug. Reading source text cannot tell code from prose. Asserting the URL
        # actually built tests the behaviour instead, and would still catch the
        # regression if someone reintroduced it a different way.
        import io as _io
        from unittest.mock import patch

        sp = self._sp()
        captured = {}

        def fake_urlopen(req, timeout=10):
            captured['url'] = req.full_url
            body = _io.BytesIO(b'{"result": {"items": []}}')
            body.__enter__ = lambda s: s
            body.__exit__ = lambda s, *a: None
            return body

        with patch.object(sp, 'urlopen', fake_urlopen):
            sp.handler({'queryStringParameters': {'postcode': 'WA2 8SN'}}, None)

        self.assertIn('WA2%208SN', captured['url'])
        self.assertNotIn('%2B', captured['url'])


# ---------- Usage-plan route scoping (template half) ----------

class ChatRouteDenyTests(unittest.TestCase):
    """Every plan whose keys are handed out must deny POST /v1/chat per-method.

    An API Gateway key authorises at the STAGE, not per route: a key on any
    usage plan reaches every method carrying ApiKeyRequired: true. The demo
    plan gained a per-method RateLimit-0 deny for /v1/chat on 2026-08-21; the
    free plan - whose keys /v1/signup mints for any email address - did not,
    so every self-service key could POST /v1/chat and spend Bedrock budget
    outside the "requests = scores" entitlement the plan block documents.

    This is the TEMPLATE half, deliberately: whether API Gateway treats
    RateLimit 0 as deny rather than "unlimited" is a question only the running
    API can answer, and tests/demo-key-scope.mjs asks it after every deploy.
    This half exists so the deny cannot silently fall out of the template
    between deploys. Same textual read as FreeTierQuotaDriftTests above, for
    the same reason (CFN intrinsics defeat yaml.safe_load).
    """

    TEMPLATE = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'template.yaml'))

    @classmethod
    def setUpClass(cls):
        with open(cls.TEMPLATE, encoding='utf-8') as handle:
            cls.text = handle.read()

    def _api_stages(self, resource, next_resource):
        """The ApiStages segment of one usage plan, where a per-method deny
        must live. A route key under the PLAN-LEVEL Throttle would be invalid
        CloudFormation, so finding it there must not satisfy this test."""
        start = self.text.index(f'  {resource}:')
        end = self.text.index(f'  {next_resource}:', start)
        block = self.text[start:end]
        stages_start = block.index('ApiStages:')
        stages_end = block.index('Quota:', stages_start)
        return block[stages_start:stages_end]

    def _assert_denied(self, stages, route, plan):
        lines = [ln.strip() for ln in stages.splitlines()
                 if ln.strip() and not ln.strip().startswith('#')]
        try:
            at = lines.index(f'{route}:')
        except ValueError:
            self.fail(f'{route} is not listed inside {plan}.ApiStages - '
                      'a key on this plan reaches it')
        self.assertEqual(
            sorted(lines[at + 1:at + 3]),
            ['BurstLimit: 0', 'RateLimit: 0'],
            f'{route} is listed in {plan}.ApiStages but not denied with '
            'BurstLimit 0 / RateLimit 0')

    def test_free_plan_denies_chat_and_batch(self):
        stages = self._api_stages('ScoreFreeUsagePlan', 'ScoreFreeUsagePlanKey')
        self._assert_denied(stages, '/v1/chat/POST', 'ScoreFreeUsagePlan')
        self._assert_denied(stages, '/v1/score/batch/POST', 'ScoreFreeUsagePlan')

    def test_demo_plan_denies_chat_and_batch(self):
        stages = self._api_stages('ScoreDemoUsagePlan', 'SignupFunction')
        self._assert_denied(stages, '/v1/chat/POST', 'ScoreDemoUsagePlan')
        self._assert_denied(stages, '/v1/score/batch/POST', 'ScoreDemoUsagePlan')


class TransportLineStatusOutageTests(unittest.TestCase):
    """A TfL outage on Line/Status must never read as "no disruptions".

    The stations half of this handler has distinguished outage from empty
    since A-0724-I5: fetch_nearby_stations returns None when TfL is
    unreachable and the response says available: false. The lineStatus half,
    in the same file, returned [] for BOTH - so a 403 or timeout rendered as
    an empty disruption list, indistinguishable from "every line is running
    normally". Same absence-as-measurement shape, one function apart.

    Compat constraint: existing consumers read lineStatus as an array, so the
    outage case keeps lineStatus: [] and adds lineStatusAvailable: false
    alongside it rather than changing the field's type.
    """

    def setUp(self):
        self.app = _import_lambda('transport')

    def _stations(self, lines=('victoria',)):
        return [{'name': 'Oxford Circus', 'distance': 120, 'modes': ['tube'],
                 'lines': list(lines), 'lat': 51.515, 'lon': -0.141}]

    def _call(self):
        result = self.app.handler(
            {'queryStringParameters': {'lat': '51.515', 'lon': '-0.141'}}, None)
        self.assertEqual(result['statusCode'], 200)
        return json.loads(result['body'])

    def test_upstream_403_sets_the_flag_false_and_keeps_the_array(self):
        # The 403 TfL answers to a bad User-Agent - the exact failure that hid
        # this endpoint's brokenness for months (see fetch_line_status).
        from urllib.error import HTTPError
        err = HTTPError('https://api.tfl.gov.uk', 403, 'Forbidden', None, None)
        with patch.object(self.app, 'fetch_nearby_stations',
                          return_value=self._stations()),              patch.object(self.app, 'urlopen', side_effect=err):
            body = self._call()
        self.assertEqual(body['lineStatus'], [])
        self.assertIs(body['lineStatusAvailable'], False)

    def test_no_lines_to_ask_about_is_a_real_empty(self):
        # A station list whose stations carry no line ids means there is
        # genuinely nothing to report - not an outage.
        with patch.object(self.app, 'fetch_nearby_stations',
                          return_value=self._stations(lines=())):
            body = self._call()
        self.assertEqual(body['lineStatus'], [])
        self.assertIs(body['lineStatusAvailable'], True)

    def test_successful_status_fetch_reports_available(self):
        import io as _io
        payload = _io.BytesIO(json.dumps([{
            'name': 'Victoria', 'id': 'victoria', 'modeName': 'tube',
            'lineStatuses': [{'statusSeverityDescription': 'Good Service'}],
        }]).encode())
        payload.__enter__ = lambda s=payload: s
        payload.__exit__ = lambda s=payload, *a: None
        with patch.object(self.app, 'fetch_nearby_stations',
                          return_value=self._stations()),              patch.object(self.app, 'urlopen', return_value=payload):
            body = self._call()
        self.assertEqual(body['lineStatus'][0]['status'], 'Good Service')
        self.assertIs(body['lineStatusAvailable'], True)

    def test_stations_outage_branch_reports_status_unavailable_too(self):
        # When TfL is unreachable for stations, statuses were never fetched
        # either - that response must not imply they were checked and empty.
        with patch.object(self.app, 'fetch_nearby_stations', return_value=None):
            body = self._call()
        self.assertIs(body['available'], False)
        self.assertEqual(body['lineStatus'], [])
        self.assertIs(body['lineStatusAvailable'], False)

    def test_fetch_line_status_returns_none_on_failure(self):
        # None, not [] - the same contract fetch_nearby_stations already has,
        # so a caller cannot mistake an outage for an empty result.
        from urllib.error import URLError
        with patch.object(self.app, 'urlopen', side_effect=URLError('down')):
            self.assertIsNone(self.app.fetch_line_status(['victoria']))
        # And no ids to query is a real empty, unchanged.
        self.assertEqual(self.app.fetch_line_status([]), [])


class SignupDuplicateNamesTheListTests(unittest.TestCase):
    """A duplicate reply must name the list the EXISTING row belongs to.

    get_existing_signup keys on email alone, and the signups table holds two
    kinds of row: API-key registrations (keyId set) and consumer score-update
    subscriptions (keyId written as an explicit ''). The duplicate branches
    only ever looked at the SOURCE of the new request, so an API-key holder
    typing their address into the consumer form was told "You are already on
    the list for score updates" - a list their row does not belong to, about a
    subscription that was not recorded. The frontend prints data.message
    verbatim, so the one sentence has to be the true one.
    """

    def setUp(self):
        self.app = _import_lambda('signup')

    def _post(self, body):
        return self.app.handler(
            {'httpMethod': 'POST', 'body': json.dumps(body)}, None)

    def test_key_holder_on_the_consumer_form_is_told_about_the_key(self):
        row = {'email': {'S': 'dev@example.com'}, 'keyId': {'S': 'k-123'}}
        with patch.object(self.app, 'get_existing_signup', return_value=row):
            result = self._post({'email': 'dev@example.com', 'source': 'consumer'})
        self.assertEqual(result['statusCode'], 200)
        payload = json.loads(result['body'])
        self.assertIn('API key', payload['message'])
        # The sentence that was false: this row is NOT on that list, and no
        # subscription was recorded for it.
        self.assertNotIn('list for score updates', payload['message'])
        self.assertNotEqual(payload['status'], 'already-subscribed')

    def test_consumer_row_on_the_consumer_form_keeps_the_plain_reply(self):
        # The common repeat visitor is unchanged: their row IS the score-update
        # list, and the existing guard test's no-key/no-support rule holds.
        row = {'email': {'S': 'x@example.com'}, 'keyId': {'S': ''}}
        with patch.object(self.app, 'get_existing_signup', return_value=row):
            result = self._post({'email': 'x@example.com', 'source': 'consumer'})
        self.assertEqual(result['statusCode'], 200)
        payload = json.loads(result['body'])
        self.assertEqual(payload['status'], 'already-subscribed')
        blob = json.dumps(payload).lower()
        self.assertNotIn('key', blob)
        self.assertNotIn('support', blob)

    def test_consumer_row_asking_for_a_key_is_not_told_one_exists(self):
        # The mirrored direction: a score-updates subscriber posting the B2B
        # form was told a key "cannot be re-issued" - implying a key that was
        # never issued. The 409 stands (one row per email); the note must name
        # the list the row is actually on.
        row = {'email': {'S': 'sub@example.com'}, 'keyId': {'S': ''}}
        with patch.object(self.app, 'get_existing_signup', return_value=row):
            result = self._post({'email': 'sub@example.com'})
        self.assertEqual(result['statusCode'], 409)
        payload = json.loads(result['body'])
        self.assertIn('already signed up', payload['error'])
        self.assertIn('score-updates list', payload['note'])
        self.assertNotIn('re-issue', payload['note'])

    def test_key_holder_asking_for_a_key_keeps_the_re_issue_note(self):
        # And the note that IS true stays: a real key row cannot be re-shown.
        row = {'email': {'S': 'dev@example.com'}, 'keyId': {'S': 'k-123'}}
        with patch.object(self.app, 'get_existing_signup', return_value=row):
            result = self._post({'email': 'dev@example.com'})
        self.assertEqual(result['statusCode'], 409)
        self.assertIn('re-issue', json.loads(result['body'])['note'])
