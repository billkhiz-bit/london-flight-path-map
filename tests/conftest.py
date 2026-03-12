import importlib.util
import json
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Base path for Lambda source files
# ---------------------------------------------------------------------------
LAMBDAS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir, "backend", "lambdas")
)


def load_lambda(name, module_alias=None):
    """Import backend/lambdas/<name>/app.py and register it under *module_alias*
    (defaults to ``<name>_app``) so every test file gets its own module object
    even though all Lambdas share the filename ``app.py``.
    """
    alias = module_alias or f"{name}_app"
    if alias in sys.modules:
        return sys.modules[alias]

    app_path = os.path.join(LAMBDAS_DIR, name, "app.py")
    spec = importlib.util.spec_from_file_location(alias, app_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helper: build an API Gateway-style event dict
# ---------------------------------------------------------------------------
def make_api_event(method="GET", body=None, query_params=None):
    """Return a minimal API-Gateway proxy event."""
    event = {
        "httpMethod": method,
        "queryStringParameters": query_params,
        "body": json.dumps(body) if body is not None else None,
        "headers": {},
        "pathParameters": {},
        "requestContext": {},
    }
    return event


# ---------------------------------------------------------------------------
# Convenience fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def api_get_event():
    """Return a factory for GET events with query params."""
    def _factory(query_params=None):
        return make_api_event(method="GET", query_params=query_params)
    return _factory


@pytest.fixture
def api_post_event():
    """Return a factory for POST events with a JSON body."""
    def _factory(body=None):
        return make_api_event(method="POST", body=body)
    return _factory
