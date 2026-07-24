"""Tests for backend/lambdas/sold_prices/app.py"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from conftest import load_lambda, make_api_event

app = load_lambda("sold_prices")
handler = app.handler


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------
class TestHandlerValidation:
    def test_missing_postcode_returns_400(self):
        event = make_api_event("GET", query_params={})
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"] == "postcode parameter is required"

    def test_empty_postcode_returns_400(self):
        event = make_api_event("GET", query_params={"postcode": ""})
        result = handler(event, None)
        assert result["statusCode"] == 400

    def test_none_query_params_returns_400(self):
        event = make_api_event("GET", query_params=None)
        result = handler(event, None)
        assert result["statusCode"] == 400

    def test_cors_headers_on_error(self):
        event = make_api_event("GET", query_params={})
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val


# ---------------------------------------------------------------------------
# Success path (mocked)
# ---------------------------------------------------------------------------
LAND_REGISTRY_RESPONSE = json.dumps({
    "result": {
        "items": [
            {
                "pricePaid": 475000,
                "transactionDate": "2024-06-15",
                "propertyAddress": {
                    "paon": "12",
                    "street": "HIGH STREET",
                },
                "propertyType": {"prefLabel": ["Terraced"]},
                "newBuild": False,
            },
            {
                "pricePaid": 320000,
                "transactionDate": "2024-03-10",
                "propertyAddress": {
                    "paon": "5",
                    "street": "CHURCH ROAD",
                },
                "propertyType": {"prefLabel": "Flat"},
                "newBuild": True,
            },
        ]
    }
}).encode()


def _mock_urlopen(req, timeout=10):
    resp = io.BytesIO(LAND_REGISTRY_RESPONSE)
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None
    return resp


class TestHandlerSuccess:
    def test_success_response_structure(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "postcode" in body
        assert "transactions" in body
        assert body["postcode"] == "SE1 7PB"

    def test_transactions_parsed(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        body = json.loads(handler(event, None)["body"])
        txns = body["transactions"]
        assert len(txns) == 2
        assert txns[0]["price"] == 475000
        assert txns[0]["date"] == "2024-06-15"
        assert txns[0]["street"] == "HIGH STREET"
        assert txns[0]["newBuild"] is False

    def test_cors_headers_on_success(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val

    def test_empty_results(self, monkeypatch):
        empty = json.dumps({"result": {"items": []}}).encode()

        def _empty_urlopen(req, timeout=10):
            resp = io.BytesIO(empty)
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            return resp

        monkeypatch.setattr(app, "urlopen", _empty_urlopen)
        event = make_api_event("GET", query_params={"postcode": "XX1 1XX"})
        body = json.loads(handler(event, None)["body"])
        assert body["transactions"] == []
