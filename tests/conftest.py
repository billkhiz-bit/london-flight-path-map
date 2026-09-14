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


SCRIPTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir, "scripts")
)


def load_script(name, module_alias=None):
    """Import scripts/<name>.py from source, the way load_lambda does for a
    Lambda, so a test can assert what a builder DERIVES rather than what it
    wrote last time. Scripts import their heavy dependencies (rasterio, boto3)
    inside the functions that need them, so importing one is cheap.
    """
    alias = module_alias or f"script_{name}"
    if alias in sys.modules:
        return sys.modules[alias]

    script_path = os.path.join(SCRIPTS_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(alias, script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helper: build an API Gateway-style event dict
# ---------------------------------------------------------------------------
def make_api_event(method="GET", body=None, query_params=None, headers=None):
    """Return a minimal API-Gateway proxy event."""
    event = {
        "httpMethod": method,
        "queryStringParameters": query_params,
        "body": json.dumps(body) if body is not None else None,
        "headers": headers or {},
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
