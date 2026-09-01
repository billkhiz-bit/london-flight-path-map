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

    def test_missing_bearer_token_returns_not_configured(self, monkeypatch):
        """When EPC_BEARER_TOKEN is absent the handler returns a 200 with
        available=False rather than hitting the API."""
        monkeypatch.delenv("EPC_BEARER_TOKEN", raising=False)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["available"] is False
        assert "not configured" in body["message"].lower()


# ---------------------------------------------------------------------------
# Success path (mocked)
# ---------------------------------------------------------------------------
# Response shape of the MHCLG service (api.get-energy-performance-data.
# communities.gov.uk). Search rows carry only the band letter — the handler
# synthesises numeric ratings from band midpoints (B=86, C=75, D=62).
JSON_RESPONSE = json.dumps(
    {
        "rows": [
            {
                "addressLine1": "Flat 1",
                "currentEnergyEfficiencyBand": "B",
                "registrationDate": "2023-01-15",
            },
            {
                "addressLine1": "Flat 2",
                "currentEnergyEfficiencyBand": "C",
                "registrationDate": "2022-06-20",
            },
            {
                "addressLine1": "House 3",
                "currentEnergyEfficiencyBand": "D",
                "registrationDate": "2021-11-01",
            },
        ]
    }
).encode()


def _mock_urlopen(req, timeout=10):
    resp = io.BytesIO(JSON_RESPONSE)
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None
    return resp


class TestHandlerSuccess:
    @pytest.fixture(autouse=True)
    def set_env(self, monkeypatch):
        monkeypatch.setenv("EPC_BEARER_TOKEN", "test-token")

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
        # Band midpoints 86 (B), 75 (C), 62 (D) average to 74.3 -> 74 -> band C
        assert summary["averageRating"] == 74
        assert summary["averageBand"] == "C"
        assert summary["bandDistribution"]["B"] == 1
        assert summary["bandDistribution"]["C"] == 1
        assert summary["bandDistribution"]["D"] == 1

    def test_certificates_limited_to_10(self, monkeypatch):
        rows = [
            {
                "addressLine1": f"Flat {i}",
                "currentEnergyEfficiencyBand": "C",
                "registrationDate": "2023-01-01",
            }
            for i in range(15)
        ]

        def _big_urlopen(req, timeout=10):
            resp = io.BytesIO(json.dumps({"rows": rows}).encode())
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            return resp

        monkeypatch.setattr(app, "urlopen", _big_urlopen)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        body = json.loads(handler(event, None)["body"])
        assert body["count"] == 15
        assert len(body["certificates"]) <= 10

    def test_empty_rows_response(self, monkeypatch):
        def _empty(req, timeout=10):
            resp = io.BytesIO(json.dumps({"rows": []}).encode())
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

    def test_upstream_timeout_returns_504(self, monkeypatch):
        """Socket read timeouts must map to 504, not the 500 guard (A-0724-M9)."""

        def _timeout(req, timeout=10):
            raise TimeoutError("read timed out")

        monkeypatch.setattr(app, "urlopen", _timeout)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        result = handler(event, None)
        assert result["statusCode"] == 504

    def test_invalid_json_returns_502(self, monkeypatch):
        def _garbage(req, timeout=10):
            resp = io.BytesIO(b"<html>not json</html>")
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            return resp

        monkeypatch.setattr(app, "urlopen", _garbage)
        event = make_api_event("GET", query_params={"postcode": "SE1 7PB"})
        result = handler(event, None)
        assert result["statusCode"] == 502


class TestUnreadableEnvelopeIsNotAnAbsence:
    """Audit I31. `extract_rows` returned [] for two different things.

    "MHCLG answered and there are no certificates here" and "MHCLG answered in
    a shape we cannot read" produced the SAME 200 with `available: true` and
    "no certificates on record". So one upstream rename of the `rows` key would
    have had this service confidently report every postcode in the country as
    having no EPC, for as long as nobody looked.

    Both tests below pass on the pre-fix handler if the assertion is only
    "something came back"; they are written against the STATUS and the MESSAGE
    because that is the part that was lying.
    """

    @pytest.fixture(autouse=True)
    def set_env(self, monkeypatch):
        monkeypatch.setenv("EPC_BEARER_TOKEN", "test-token")

    @staticmethod
    def _serving(payload):
        def _mock(req, timeout=10):
            resp = io.BytesIO(json.dumps(payload).encode())
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda s, *a: None
            return resp

        return _mock

    def test_renamed_envelope_is_reported_not_published_as_empty(self, monkeypatch):
        # Exactly the live payload, with `rows` renamed to something we do not
        # know. Pre-fix: 200, available true, count 0.
        monkeypatch.setattr(app, "urlopen", self._serving({"records": [{"currentEnergyEfficiencyBand": "C"}]}))
        result = handler(make_api_event("GET", query_params={"postcode": "SE1 7PB"}), None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 502
        assert body["available"] is False
        assert "cannot say" in body["message"]

    def test_declared_total_contradicting_zero_rows_is_refused(self, monkeypatch):
        # The payload counts 42 certificates and hands over none. The count was
        # already being forwarded to callers; now it is also read.
        monkeypatch.setattr(
            app, "urlopen", self._serving({"rows": [], "pagination": {"totalRecords": 42}})
        )
        result = handler(make_api_event("GET", query_params={"postcode": "SE1 7PB"}), None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 502
        assert body["available"] is False
        assert "42" in body["message"]

    def test_a_genuinely_empty_postcode_still_reports_zero(self, monkeypatch):
        # The other half of the contract: a recognised envelope holding an empty
        # list is a MEASUREMENT and must still be published as one, or the fix
        # has simply moved the dishonesty.
        monkeypatch.setattr(app, "urlopen", self._serving({"rows": [], "pagination": {"totalRecords": 0}}))
        result = handler(make_api_event("GET", query_params={"postcode": "SE1 7PB"}), None)
        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["available"] is True
        assert body["count"] == 0
