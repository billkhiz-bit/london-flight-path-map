"""Tests for backend/lambdas/favourites/app.py"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from conftest import make_api_event

# ---------------------------------------------------------------------------
# We must mock boto3 *before* importing the favourites Lambda because it
# creates a DynamoDB resource and Table at module level on import.
# Pre-import boto3.dynamodb.conditions so attribute access like
# ``boto3.dynamodb.conditions.Key(...)`` works inside the handler.
# ---------------------------------------------------------------------------
import boto3.dynamodb.conditions # noqa: E402, force submodule load

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
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
}


@pytest.fixture(autouse=True)
def _reset_mock_table():
    """Reset the mock table before each test."""
    _mock_table.reset_mock()
    # Ensure the app module's `table` reference points to our mock
    app.table = _mock_table


# ---------------------------------------------------------------------------
# OPTIONS
# ---------------------------------------------------------------------------
class TestOptions:
    def test_options_returns_200(self):
        event = make_api_event("OPTIONS")
        result = handler(event, None)
        assert result["statusCode"] == 200

    def test_cors_on_options(self):
        event = make_api_event("OPTIONS")
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
                {"userId": "user1", "postcode": "SE1 7PB", "borough": "Southwark"},
                {"userId": "user1", "postcode": "E1 6AN", "borough": "Tower Hamlets"},
            ]
        }
        event = make_api_event("GET", query_params={"userId": "user1"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert len(body["favourites"]) == 2

    def test_get_uses_anonymous_as_default_user(self):
        _mock_table.query.return_value = {"Items": []}
        event = make_api_event("GET", query_params={})
        handler(event, None)
        assert _mock_table.query.called

    def test_get_empty_favourites(self):
        _mock_table.query.return_value = {"Items": []}
        event = make_api_event("GET", query_params={"userId": "nobody"})
        body = json.loads(handler(event, None)["body"])
        assert body["favourites"] == []

    def test_cors_on_get(self):
        _mock_table.query.return_value = {"Items": []}
        event = make_api_event("GET", query_params={"userId": "user1"})
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------
class TestPostFavourite:
    def test_post_saves_favourite(self):
        _mock_table.put_item.return_value = {}
        event = make_api_event("POST", body={
            "userId": "user1",
            "postcode": "SE1 7PB",
            "borough": "Southwark",
            "noiseLevel": "low-moderate",
            "buyerScore": 7.5,
            "notes": "Nice area",
            "city": "london",
        })
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Saved"
        assert body["item"]["postcode"] == "SE1 7PB"
        _mock_table.put_item.assert_called_once()

    def test_post_missing_postcode_returns_400(self):
        event = make_api_event("POST", body={"userId": "user1"})
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "Postcode is required" in body["error"]

    def test_post_empty_postcode_returns_400(self):
        event = make_api_event("POST", body={"userId": "user1", "postcode": ""})
        result = handler(event, None)
        assert result["statusCode"] == 400

    def test_post_defaults_user_to_anonymous(self):
        _mock_table.put_item.return_value = {}
        event = make_api_event("POST", body={"postcode": "SE1 7PB"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        saved_item = _mock_table.put_item.call_args[1]["Item"]
        assert saved_item["userId"] == "anonymous"

    def test_cors_on_post(self):
        _mock_table.put_item.return_value = {}
        event = make_api_event("POST", body={"postcode": "SE1 7PB"})
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
class TestDeleteFavourite:
    def test_delete_removes_favourite(self):
        _mock_table.delete_item.return_value = {}
        event = make_api_event("DELETE", body={
            "userId": "user1",
            "postcode": "SE1 7PB",
        })
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["message"] == "Deleted"
        _mock_table.delete_item.assert_called_once_with(
            Key={"userId": "user1", "postcode": "SE1 7PB"}
        )

    def test_delete_missing_postcode_returns_400(self):
        event = make_api_event("DELETE", body={"userId": "user1"})
        result = handler(event, None)
        assert result["statusCode"] == 400

    def test_delete_defaults_user_to_anonymous(self):
        _mock_table.delete_item.return_value = {}
        event = make_api_event("DELETE", body={"postcode": "SE1 7PB"})
        result = handler(event, None)
        _mock_table.delete_item.assert_called_once_with(
            Key={"userId": "anonymous", "postcode": "SE1 7PB"}
        )

    def test_cors_on_delete(self):
        _mock_table.delete_item.return_value = {}
        event = make_api_event("DELETE", body={"postcode": "SE1 7PB"})
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val


# ---------------------------------------------------------------------------
# Unsupported method
# ---------------------------------------------------------------------------
class TestUnsupportedMethod:
    def test_put_returns_405(self):
        event = make_api_event("PUT", body={})
        result = handler(event, None)
        assert result["statusCode"] == 405
        body = json.loads(result["body"])
        assert "not allowed" in body["error"].lower()
