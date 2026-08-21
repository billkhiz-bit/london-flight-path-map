"""Tests for backend/lambdas/transport/app.py"""

import io
import json
import os
import sys
from urllib.error import HTTPError, URLError

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

    def test_non_numeric_lat_lon_returns_400(self):
        event = make_api_event("GET", query_params={"lat": "abc", "lon": "-0.1"})
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "must be numbers" in body["error"]

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
        """Return different payloads depending on the URL.

        ASSERTS ON THE HEADERS, and that is the point. This branched on the
        URL alone until 2026-08-21 and so could not tell the request that
        works from the one TfL 403s. The Line/Status call was missing a
        User-Agent for its whole existence, the 403 was swallowed to [], and
        test_success_response passed on `"lineStatus" in body` - which an
        empty list satisfies. Green suite, dead endpoint.

        TfL rejects urllib's default Python-urllib/3.x, so a mock that does
        not model the rejection cannot model the upstream.
        """
        url = req.full_url if hasattr(req, "full_url") else str(req)
        ua = req.get_header("User-agent") or ""
        if not ua.startswith("SkyScore"):
            raise HTTPError(url, 403, "Forbidden", {}, None)
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
        assert "location" in body
        assert body["available"] is True
        # DATA, NOT SHAPE. `"lineStatus" in body` was the assertion here until
        # 2026-08-21 and an empty list satisfies it - which is exactly what a
        # swallowed TfL 403 produces, so this test passed for the entire life
        # of an endpoint that had never once returned a line status.
        #
        # Proven red: remove the User-Agent from fetch_line_status and this
        # line fails. The `in body` version does not.
        assert len(body["stations"]) > 0
        assert len(body["lineStatus"]) > 0, (
            "lineStatus is empty - a swallowed upstream error looks exactly "
            "like 'every line running normally'"
        )

    def test_upstream_failure_returns_available_false(self, monkeypatch):
        """TfL being unreachable must be distinguishable from 'no stations
        nearby' — the frontend renders the two differently (A-0724-I5)."""

        def _raise(req, timeout=15):
            raise URLError("TfL down")

        monkeypatch.setattr(app, "urlopen", _raise)
        event = make_api_event("GET", query_params={"lat": "51.5074", "lon": "-0.1278"})
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["available"] is False
        assert body["stations"] == []

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
