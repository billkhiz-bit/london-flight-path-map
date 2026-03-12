"""Tests for backend/lambdas/epc/app.py"""

import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from conftest import load_lambda, make_api_event

app = load_lambda("epc")
handler = app.handler
rating_to_band = app.rating_to_band


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}


# ---------------------------------------------------------------------------
# rating_to_band() unit tests
# ---------------------------------------------------------------------------
class TestRatingToBand:
    @pytest.mark.parametrize(
        "rating, expected_band",
        [
            (100, "A"),
            (92, "A"),
            (91, "B"),
            (81, "B"),
            (80, "C"),
            (69, "C"),
            (68, "D"),
            (55, "D"),
            (54, "E"),
            (39, "E"),
            (38, "F"),
            (21, "F"),
            (20, "G"),
            (1, "G"),
            (0, "G"),
        ],
    )
    def test_rating_boundaries(self, rating, expected_band):
        assert rating_to_band(rating) == expected_band


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

    def test_missing_api_key_returns_not_configured(self, monkeypatch):
        """When EPC_API_KEY / EPC_API_EMAIL are absent the handler returns
        a 200 with available=False rather than hitting the API."""
        monkeypatch.delenv("EPC_API_KEY", raising=False)
        monkeypatch.delenv("EPC_API_EMAIL", raising=False)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["available"] is False
        assert "not configured" in body["message"].lower()


# ---------------------------------------------------------------------------
# Success path (mocked)
# ---------------------------------------------------------------------------
CSV_RESPONSE = (
    "address1,current-energy-rating,current-energy-efficiency,property-type,"
    "lodgement-date,total-floor-area,heating-cost-current,hot-water-cost-current,"
    "lighting-cost-current\n"
    "Flat 1,B,82,Flat,2023-01-15,55,400,100,80\n"
    "Flat 2,C,70,Flat,2022-06-20,60,500,120,90\n"
    "House 3,D,58,House,2021-11-01,110,900,200,150\n"
)


def _mock_urlopen(req, timeout=10):
    resp = io.BytesIO(CSV_RESPONSE.encode())
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None
    return resp


class TestHandlerSuccess:
    @pytest.fixture(autouse=True)
    def set_env(self, monkeypatch):
        monkeypatch.setenv("EPC_API_KEY", "test-key")
        monkeypatch.setenv("EPC_API_EMAIL", "test@example.com")

    def test_success_response_structure(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["available"] is True
        assert body["count"] == 3
        assert "summary" in body
        assert "certificates" in body

    def test_summary_statistics(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        body = json.loads(handler(event, None)["body"])
        summary = body["summary"]
        # Average of 82, 70, 58 = 70 -> band C
        assert summary["averageRating"] == 70
        assert summary["averageBand"] == "C"
        assert "bandDistribution" in summary

    def test_certificates_limited_to_10(self, monkeypatch):
        # Build CSV with 15 rows
        header = (
            "address1,current-energy-rating,current-energy-efficiency,"
            "property-type,lodgement-date,total-floor-area,"
            "heating-cost-current,hot-water-cost-current,lighting-cost-current\n"
        )
        rows = "".join(
            f"Flat {i},C,70,Flat,2023-01-01,50,400,100,80\n" for i in range(15)
        )

        def _big_urlopen(req, timeout=10):
            resp = io.BytesIO((header + rows).encode())
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            return resp

        monkeypatch.setattr(app, "urlopen", _big_urlopen)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        body = json.loads(handler(event, None)["body"])
        assert len(body["certificates"]) <= 10

    def test_empty_csv_response(self, monkeypatch):
        def _empty(req, timeout=10):
            resp = io.BytesIO(b"")
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            return resp

        monkeypatch.setattr(app, "urlopen", _empty)
        event = make_api_event("GET", query_params={"postcode": "XX1 1XX"})
        body = json.loads(handler(event, None)["body"])
        assert body["count"] == 0
        assert body["certificates"] == []

    def test_cors_headers_on_success(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val
