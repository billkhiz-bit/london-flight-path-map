"""Audit M-3, 2026-11-23: a request body of deep nesting or a 4,300+ digit integer reached each anonymous handler's 500
guard, because the parsers caught only json.JSONDecodeError (Python 3.11 raises RecursionError for the one and a plain
ValueError for the other). Each now answers 400, as for any other body it cannot read. Driven through the real handlers;
no AWS call is reached (the body is refused first)."""
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

LAMBDAS = Path(__file__).resolve().parent.parent / 'lambdas'
BODIES = {'deep nesting': '[' * 1100, 'a 5,000-digit integer': '1' * 5000}


def load(name):
    alias = f'json_bodies_{name}'
    if alias in sys.modules:
        return sys.modules[alias]
    os.environ.setdefault('AWS_REGION', 'eu-west-2')
    spec = importlib.util.spec_from_file_location(alias, LAMBDAS / name / 'app.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


class MalformedBodiesTests(unittest.TestCase):
    def test_signup_refuses_with_a_400(self):
        app = load('signup')
        for label, body in BODIES.items():
            with self.subTest(body=label):
                r = app.handler({'httpMethod': 'POST', 'path': '/v1/signup', 'body': body, 'headers': {}}, None)
                self.assertEqual(r['statusCode'], 400, r['body'])

    def test_favourites_refuses_with_a_400_on_post_and_delete(self):
        app = load('favourites')
        for method in ('POST', 'DELETE'):
            for label, body in BODIES.items():
                with self.subTest(method=method, body=label):
                    r = app.handler({'httpMethod': method, 'path': '/favourites', 'body': body,
                                     'headers': {'X-Device-Token': '550e8400-e29b-41d4-a716-446655440000'}}, None)
                    self.assertEqual(r['statusCode'], 400, r['body'])
                    self.assertIn('Invalid JSON body', json.loads(r['body'])['error'])
