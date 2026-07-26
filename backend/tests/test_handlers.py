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
from unittest.mock import patch, MagicMock

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
        import app # noqa: F401, pylint: disable=import-outside-toplevel
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
        good_token = '550e8400-e29b-41d4-a716-446655440000'
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


if __name__ == '__main__':
    unittest.main()
