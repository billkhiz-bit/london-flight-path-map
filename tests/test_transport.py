"""Tests for backend/lambdas/transport/app.py"""

import io
import json
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Import the transport Lambda via our loader (avoids module name collisions)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from conftest import load_lambda, make_api_event

app = load_lambda("transport")
handler = app.handler
haversine = app.haversine


# ---------------------------------------------------------------------------
# haversine() unit tests
# ---------------------------------------------------------------------------
class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine(51.5, -0.1, 51.5, -0.1) == 0.0

    def test_london_bridge_to_greenwich(self):
        """London Bridge (51.5079, -0.0877) -> Greenwich (51.4826, 0.0077) ~5-7 km."""
        dist = haversine(51.5079, -0.0877, 51.4826, 0.0077)
        assert 5000 <= dist <= 7500, f"Expected 5-7.5 km, got {dist:.0f} m"

    def test_symmetry(self):
        d1 = haversine(51.5, -0.1, 52.0, 0.0)
        d2 = haversine(52.0, 0.0, 51.5, -0.1)
        assert abs(d1 - d2) < 0.01


# ---------------------------------------------------------------------------
# handler() tests
# ---------------------------------------------------------------------------
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}


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


class TestHandlerSuccess:
    """Mock urlopen so we never hit real TfL API."""

    TFL_STOP_RESPONSE = json.dumps({
        "stopPoints": [
            {
                "commonName": "London Bridge Underground Station",
                "lat": 51.5055,
                "lon": -0.0862,
                "lineModeGroups": [
                    {
                        "modeName": "tube",
                        "lineIdentifier": ["jubilee", "northern"],
                    }
                ],
            }
        ]
    }).encode()

    TFL_STATUS_RESPONSE = json.dumps([
        {
            "name": "Jubilee",
            "id": "jubilee",
            "modeName": "tube",
            "lineStatuses": [
                {"statusSeverityDescription": "Good Service"}
            ],
        },
        {
            "name": "Northern",
            "id": "northern",
            "modeName": "tube",
            "lineStatuses": [
                {"statusSeverityDescription": "Good Service"}
            ],
        },
    ]).encode()

    def _mock_urlopen(self, req, timeout=10):
        """Return different payloads depending on the URL."""
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "StopPoint" in url:
            data = self.TFL_STOP_RESPONSE
        else:
            data = self.TFL_STATUS_RESPONSE

        resp = io.BytesIO(data)
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: None
        return resp

    def test_success_response(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", self._mock_urlopen)
        event = make_api_event("GET", query_params={"lat": "51.5074", "lon": "-0.1278"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "stations" in body
        assert "lineStatus" in body
        assert "location" in body

    def test_stations_list_populated(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", self._mock_urlopen)
        event = make_api_event("GET", query_params={"lat": "51.5074", "lon": "-0.1278"})
        body = json.loads(handler(event, None)["body"])
        assert len(body["stations"]) >= 1
        station = body["stations"][0]
        assert "name" in station
        assert "distance" in station
        assert "modes" in station
        assert "lines" in station

    def test_cors_headers_on_success(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", self._mock_urlopen)
        event = make_api_event("GET", query_params={"lat": "51.5074", "lon": "-0.1278"})
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val
