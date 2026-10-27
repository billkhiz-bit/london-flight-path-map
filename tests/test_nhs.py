"""Tests for backend/lambdas/nhs/app.py"""

import io
import json
import os
import sys
from urllib.error import URLError

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
# OSM Overpass response shape (the handler's data source since the NHS
# Service Search API was retired behind a subscription key). Ways and
# relations carry coordinates under "center"; nodes carry lat/lon directly.
#
# COORDINATES ARE EXETER, DELIBERATELY: outside every bundled area. The handler
# serves each area it bundles from a snapshot and never calls Overpass there, so
# a fixture inside one would short-circuit and these tests would assert nothing
# about the code path they exist to cover. They WERE London, moved to Manchester
# when London was bundled (2026-08-06), and to Exeter when every UK area we score
# was (2026-10-27): both times they failed the moment the change landed, the gate
# working as intended. Each move shifted the whole fixture and its query point by
# one constant offset (this time -2.7536 lat, -1.2778 lon), so the relative
# distances the assertions depend on are unchanged.
QUERY = {"lat": "50.7236", "lon": "-3.5275"}


def test_the_query_point_is_outside_every_bundled_area():
    # Says plainly what broke if Exeter is ever bundled: move the fixture again.
    assert not app.in_bundle_area(float(QUERY["lat"]), float(QUERY["lon"]))


OVERPASS_RESPONSE = json.dumps(
    {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 50.7217,
                "lon": -3.4859,
                "tags": {
                    "amenity": "doctors",
                    "name": "City Medical Centre",
                    "addr:housenumber": "10",
                    "addr:street": "High Street",
                    "addr:postcode": "SE1 7PB",
                    "phone": "020 7123 4567",
                },
            },
            {
                "type": "way",
                "id": 2,
                "center": {"lat": 50.7202, "lon": -3.4897},
                "tags": {
                    "amenity": "pharmacy",
                    "name": "Bridge Pharmacy",
                    "addr:postcode": "SE1 9AA",
                },
            },
            {
                "type": "node",
                "id": 3,
                "lat": 50.7262,
                "lon": -3.4947,
                "tags": {"amenity": "hospital", "name": "Riverside Hospital"},
            },
        ]
    }
).encode()


def _mock_urlopen(req, timeout=12):
    resp = io.BytesIO(OVERPASS_RESPONSE)
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None
    return resp


class TestHandlerSuccess:
    def test_success_response_structure(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params=QUERY)
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "location" in body
        assert "gp" in body
        assert "pharmacies" in body
        assert "hospitals" in body

    def test_gp_results_parsed(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params=QUERY)
        body = json.loads(handler(event, None)["body"])
        gps = body["gp"]
        assert len(gps) >= 1
        gp = gps[0]
        assert gp["name"] == "City Medical Centre"
        assert gp["postcode"] == "SE1 7PB"
        assert gp["phone"] == "020 7123 4567"
        assert isinstance(gp["distance"], int)

    def test_way_elements_use_center_coords(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params=QUERY)
        body = json.loads(handler(event, None)["body"])
        pharmacies = body["pharmacies"]
        assert pharmacies[0]["name"] == "Bridge Pharmacy"
        assert isinstance(pharmacies[0]["distance"], int)

    def test_cors_headers_on_success(self, monkeypatch):
        monkeypatch.setattr(app, "urlopen", _mock_urlopen)
        event = make_api_event("GET", query_params=QUERY)
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val

    def test_fallback_on_api_error(self, monkeypatch):
        """When Overpass is unreachable the handler returns nhs.uk search
        links instead of failing. The handler deliberately catches only
        network/parse errors (URLError et al), not bare Exception."""

        def _raise(req, timeout=12):
            raise URLError("API down")

        monkeypatch.setattr(app, "urlopen", _raise)
        event = make_api_event("GET", query_params=QUERY)
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["available"] is False
        # Fallback returns a list with a single item that has fallback=True
        assert body["gp"][0]["fallback"] is True
