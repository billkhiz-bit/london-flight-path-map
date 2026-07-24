"""Tests for backend/lambdas/favourites/app.py

Rewritten 2026-07-24 for the X-Device-Token contract (audit C3): the
handler no longer accepts a caller-supplied userId — the DynamoDB
partition key is a validated device token sent via the X-Device-Token
header, canonicalised to lowercase hex without hyphens. Requests
without a well-formed token are rejected with 401 before any storage
access.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
# ---------------------------------------------------------------------------
# We must mock boto3 *before* importing the favourites Lambda because it
# creates a DynamoDB resource and Table at module level on import.
# Pre-import boto3.dynamodb.conditions so attribute access like
# ``boto3.dynamodb.conditions.Key(...)`` works inside the handler.
# ---------------------------------------------------------------------------
from boto3.dynamodb.conditions import Key  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from conftest import make_api_event

_mock_table = MagicMock()
_mock_dynamodb = MagicMock()
_mock_dynamodb.Table.return_value = _mock_table

with patch.dict(os.environ, {"FAVOURITES_TABLE": "test-favourites"}):
    with patch("boto3.resource", return_value=_mock_dynamodb):
        from conftest import load_lambda

        app = load_lambda("favourites")

handler = app.handler


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Device-Token",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
}

# A valid UUID v4 device token; the handler canonicalises to lowercase
# hex without hyphens before using it as the partition key.
DEVICE_TOKEN = "550E8400-E29B-41D4-A716-446655440000"  # noqa: S105 — test fixture, not a secret
CANONICAL_TOKEN = "550e8400e29b41d4a716446655440000"  # noqa: S105 — test fixture, not a secret
TOKEN_HEADER = {"X-Device-Token": DEVICE_TOKEN}


@pytest.fixture(autouse=True)
def _reset_mock_table():
    """Reset the mock table (including side effects) before each test."""
    _mock_table.reset_mock(return_value=True, side_effect=True)
    # Ensure the app module's `table` reference points to our mock
    app.table = _mock_table


# ---------------------------------------------------------------------------
# OPTIONS (no token required — CORS preflight must always succeed)
# ---------------------------------------------------------------------------
class TestOptions:
    def test_options_returns_200_without_token(self):
        event = make_api_event("OPTIONS")
        result = handler(event, None)
        assert result["statusCode"] == 200

    def test_cors_on_options(self):
        event = make_api_event("OPTIONS")
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val


# ---------------------------------------------------------------------------
# Auth boundary: X-Device-Token required on every non-OPTIONS method
# ---------------------------------------------------------------------------
class TestDeviceTokenAuth:
    @pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
    def test_missing_token_returns_401(self, method):
        event = make_api_event(method)
        result = handler(event, None)
        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert "X-Device-Token" in body["error"]

    def test_malformed_token_returns_401(self):
        event = make_api_event("GET", headers={"X-Device-Token": "not-a-token"})
        result = handler(event, None)
        assert result["statusCode"] == 401

    def test_query_string_user_id_is_not_accepted_as_auth(self):
        """The pre-C3 contract took userId from the query string. That
        must no longer authenticate a request."""
        event = make_api_event("GET", query_params={"userId": "user1"})
        result = handler(event, None)
        assert result["statusCode"] == 401
        assert not _mock_table.query.called

    def test_lowercase_header_name_accepted(self):
        _mock_table.query.return_value = {"Items": []}
        event = make_api_event("GET", headers={"x-device-token": DEVICE_TOKEN})
        result = handler(event, None)
        assert result["statusCode"] == 200

    def test_bare_32_hex_token_accepted(self):
        _mock_table.query.return_value = {"Items": []}
        event = make_api_event("GET", headers={"X-Device-Token": CANONICAL_TOKEN})
        result = handler(event, None)
        assert result["statusCode"] == 200

    def test_cors_on_401(self):
        event = make_api_event("GET")
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------
class TestGetFavourites:
    def test_get_returns_favourites_list(self):
        _mock_table.query.return_value = {
            "Items": [
                {"userId": CANONICAL_TOKEN, "postcode": "SE1 7PB", "borough": "Southwark"},
                {"userId": CANONICAL_TOKEN, "postcode": "E1 6AN", "borough": "Tower Hamlets"},
            ]
        }
        event = make_api_event("GET", headers=TOKEN_HEADER)
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert len(body["favourites"]) == 2

    def test_get_queries_by_canonical_token(self):
        _mock_table.query.return_value = {"Items": []}
        event = make_api_event("GET", headers=TOKEN_HEADER)
        handler(event, None)
        condition = _mock_table.query.call_args.kwargs["KeyConditionExpression"]
        assert condition == Key("userId").eq(CANONICAL_TOKEN)

    def test_get_empty_favourites(self):
        _mock_table.query.return_value = {"Items": []}
        event = make_api_event("GET", headers=TOKEN_HEADER)
        body = json.loads(handler(event, None)["body"])
        assert body["favourites"] == []

    def test_get_dynamodb_error_returns_503(self):
        _mock_table.query.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "boom"}}, "Query"
        )
        event = make_api_event("GET", headers=TOKEN_HEADER)
        result = handler(event, None)
        assert result["statusCode"] == 503

    def test_cors_on_get(self):
        _mock_table.query.return_value = {"Items": []}
        event = make_api_event("GET", headers=TOKEN_HEADER)
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------
class TestPostFavourite:
    def test_post_saves_favourite(self):
        _mock_table.put_item.return_value = {}
        event = make_api_event(
            "POST",
            body={
                "postcode": "SE1 7PB",
                "borough": "Southwark",
                "noiseLevel": "low-moderate",
                "buyerScore": 7.5,
                "notes": "Nice area",
                "city": "london",
            },
            headers=TOKEN_HEADER,
        )
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Saved"
        assert body["item"]["postcode"] == "SE1 7PB"
        _mock_table.put_item.assert_called_once()

    def test_post_partition_key_is_canonical_token(self):
        """Any userId in the body must be ignored — the partition key
        comes from the validated header token only."""
        _mock_table.put_item.return_value = {}
        event = make_api_event(
            "POST",
            body={"userId": "someone-else", "postcode": "SE1 7PB"},
            headers=TOKEN_HEADER,
        )
        handler(event, None)
        saved_item = _mock_table.put_item.call_args.kwargs["Item"]
        assert saved_item["userId"] == CANONICAL_TOKEN

    def test_post_missing_postcode_returns_400(self):
        event = make_api_event("POST", body={}, headers=TOKEN_HEADER)
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "Postcode is required" in body["error"]

    def test_post_empty_postcode_returns_400(self):
        event = make_api_event("POST", body={"postcode": ""}, headers=TOKEN_HEADER)
        result = handler(event, None)
        assert result["statusCode"] == 400

    def test_post_invalid_json_body_returns_400(self):
        event = make_api_event("POST", headers=TOKEN_HEADER)
        event["body"] = "{not json"
        result = handler(event, None)
        assert result["statusCode"] == 400

    def test_cors_on_post(self):
        _mock_table.put_item.return_value = {}
        event = make_api_event("POST", body={"postcode": "SE1 7PB"}, headers=TOKEN_HEADER)
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
class TestDeleteFavourite:
    def test_delete_removes_favourite(self):
        _mock_table.delete_item.return_value = {}
        event = make_api_event("DELETE", body={"postcode": "SE1 7PB"}, headers=TOKEN_HEADER)
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Deleted"
        _mock_table.delete_item.assert_called_once_with(
            Key={"userId": CANONICAL_TOKEN, "postcode": "SE1 7PB"}
        )

    def test_delete_ignores_body_user_id(self):
        _mock_table.delete_item.return_value = {}
        event = make_api_event(
            "DELETE",
            body={"userId": "someone-else", "postcode": "SE1 7PB"},
            headers=TOKEN_HEADER,
        )
        handler(event, None)
        _mock_table.delete_item.assert_called_once_with(
            Key={"userId": CANONICAL_TOKEN, "postcode": "SE1 7PB"}
        )

    def test_delete_missing_postcode_returns_400(self):
        event = make_api_event("DELETE", body={}, headers=TOKEN_HEADER)
        result = handler(event, None)
        assert result["statusCode"] == 400

    def test_cors_on_delete(self):
        _mock_table.delete_item.return_value = {}
        event = make_api_event("DELETE", body={"postcode": "SE1 7PB"}, headers=TOKEN_HEADER)
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val


# ---------------------------------------------------------------------------
# Unsupported method
# ---------------------------------------------------------------------------
class TestUnsupportedMethod:
    def test_put_with_valid_token_returns_405(self):
        event = make_api_event("PUT", body={}, headers=TOKEN_HEADER)
        result = handler(event, None)
        assert result["statusCode"] == 405
        body = json.loads(result["body"])
        assert "not allowed" in body["error"].lower()
