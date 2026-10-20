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

    def test_category_estate_and_flat_are_read_from_land_registry_uris(self, monkeypatch):
        # Three rows as Land Registry answered for TW9 3PZ on 2026-10-20, trimmed to the fields read.
        # The concept is matched by its URI: the labels are cased differently field to field.
        def concept(uri, label):
            return {"_about": uri, "prefLabel": [{"_value": label, "_lang": "en"}]}

        lr = "http://landregistry.data.gov.uk/def/"
        rows = {"result": {"items": [
            {"pricePaid": 20000, "transactionDate": "Thu, 11 Sep 2025",
             "propertyAddress": {"paon": "16", "street": "STATION PARADE"},
             "propertyType": concept(lr + "common/otherPropertyType", "other"),
             "transactionCategory": concept(lr + "ppi/additionalPricePaidTransaction", "Additional price paid transaction"),
             "estateType": concept(lr + "common/leasehold", "Leasehold")},
            {"pricePaid": 79500, "transactionDate": "Wed, 20 Aug 1997",
             "propertyAddress": {"saon": "FLAT 2", "paon": "THE CAFE, 2", "street": "STATION PARADE"},
             "propertyType": concept(lr + "common/flat-maisonette", "flat-maisonette"),
             "transactionCategory": concept(lr + "ppi/standardPricePaidTransaction", "Standard price paid transaction"),
             "estateType": concept(lr + "common/leasehold", "Leasehold")},
            {"pricePaid": 162500, "transactionDate": "Thu, 08 Apr 2004",
             "propertyAddress": {"paon": "16", "street": "STATION PARADE"},
             "propertyType": concept(lr + "common/semi-detached", "semi-detached"),
             "transactionCategory": concept(lr + "ppi/standardPricePaidTransaction", "Standard price paid transaction"),
             "estateType": concept(lr + "common/freehold", "Freehold")},
            # An unknown concept, one with no URI, and a URI ending in '/' all read as nothing, never a guess.
            {"pricePaid": 300000, "transactionDate": "Mon, 01 Jan 2024", "propertyAddress": {"paon": "1"},
             "transactionCategory": concept(lr + "ppi/someNewCategory", "New"), "estateType": {"prefLabel": "Freehold"}},
            {"pricePaid": 310000, "transactionDate": "Mon, 01 Jan 2024", "propertyAddress": {"paon": "2"},
             "transactionCategory": concept(lr + "ppi/", "?"), "estateType": concept("/", "?")},
        ]}}

        def _urlopen(req, timeout=10):
            resp = io.BytesIO(json.dumps(rows).encode())
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            return resp

        monkeypatch.setattr(app, "urlopen", _urlopen)
        txns = json.loads(handler(make_api_event("GET", query_params={"postcode": "TW9 3PZ"}), None)["body"])["transactions"]
        got = [(t["category"], t["estate"], t["saon"], t["address"]) for t in txns]
        assert got == [("B", "leasehold", "", "16"), ("A", "leasehold", "FLAT 2", "THE CAFE, 2"),
                       ("A", "freehold", "", "16"), ("", "", "", "1"), ("", "", "", "2")]

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
