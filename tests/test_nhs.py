"""Tests for backend/lambdas/nhs/app.py"""

import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from conftest import load_lambda, make_api_event

app = load_lambda("nhs")
handler = app.handler
haversine = app.haversine


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}


# ---------------------------------------------------------------------------
# haversine() unit tests
# ---------------------------------------------------------------------------
class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine(51.5, -0.1, 51.5, -0.1) == 0.0

    def test_known_distance(self):
        """Westminster (51.4975, -0.1357) -> Waterloo (51.5031, -0.1132) ~1.6 km."""
        dist = haversine(51.4975, -0.1357, 51.5031, -0.1132)
        assert 1000 <= dist <= 2500, f"Expected ~1.6 km, got {dist:.0f} m"

    def test_symmetry(self):
        d1 = haversine(51.5, -0.1, 52.0, 0.0)
        d2 = haversine(52.0, 0.0, 51.5, -0.1)
        assert abs(d1 - d2) < 0.01


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------
class TestHandlerValidation:
    def test_missing_lat_lon_returns_400(self):
        event = make_api_event("GET", query_params={})
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "error" in body

    def test_missing_lat_only_returns_400(self):
        event = make_api_event("GET", query_params={"lon": "-0.1"})
        result = handler(event, None)
        assert result["statusCode"] == 400

    def test_missing_lon_only_returns_400(self):
        event = make_api_event("GET", query_params={"lat": "51.5"})
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
NHS_API_RESPONSE = json.dumps({
    "value": [
        {
            "OrganisationName": "City Medical Centre",
            "Address1": "10 High Street",
            "Postcode": "SE1 7PB",
            "Phone": "020 7123 4567",
            "Latitude": 51.5055,
            "Longitude": -0.0862,
            "AcceptingPatients": True,
            "URL": "https://nhs.uk/gp/city-medical",
        },
        {
            "OrganisationName": "Bridge Surgery",
            "Address1": "5 Bridge Road",
            "Postcode": "SE1 9AA",
            "Phone": "020 7765 4321",
            "Latitude": 51.5040,
            "Longitude": -0.0900,
            "AcceptingPatients": False,
            "URL": "https://nhs.uk/gp/bridge-surgery",
        },
    ]
}).encode()


def _mock_urlopen(req, timeout=10):
    resp = io.BytesIO(NHS_API_RESPONSE)
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None
    return resp


class TestHandlerSuccess:
    def test_success_response_structure(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params={"lat": "51.5074", "lon": "-0.1278"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "location" in body
        assert "gp" in body
        assert "pharmacies" in body
        assert "hospitals" in body

    def test_gp_results_parsed(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params={"lat": "51.5074", "lon": "-0.1278"})
        body = json.loads(handler(event, None)["body"])
        gps = body["gp"]
        assert len(gps) >= 1
        gp = gps[0]
        assert "name" in gp
        assert "distance" in gp
        assert "postcode" in gp
        assert "phone" in gp

    def test_cors_headers_on_success(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params={"lat": "51.5074", "lon": "-0.1278"})
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val

    def test_fallback_on_api_error(self, monkeypatch):
        """When urlopen raises, the handler should use the fallback."""

        def _raise(req, timeout=10):
            raise Exception("API down")

        monkeypatch.setattr(app, "urlopen", _raise)
        event = make_api_event("GET", query_params={"lat": "51.5074", "lon": "-0.1278"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        # Fallback returns a list with a single item that has fallback=True
        assert body["gp"][0]["fallback"] is True
