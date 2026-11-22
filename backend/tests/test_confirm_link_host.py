"""The links in our emails go through the site's own domain (2026-11-22).

The first news-by-email confirmation went from noreply@skyscore.co.uk with a token link to the raw API Gateway host
(https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/signup/confirm?token=...). SES delivered it to Hotmail
(CloudWatch: Send 1, Delivery 1, Bounce 0) and it reached neither the inbox nor Junk: a token link to an AWS address
in mail from another domain is the shape phishing takes. Since 22 Nov CloudFront routes /v1/signup/* on skyscore.co.uk
to this API (the `/badge` origin, caching off), and the template's ConfirmUrlBase points the links there.

What this holds: the template's default and the function's environment (a parameter that never reaches the Lambda
changes nothing), the link's base as the code builds it, and that every route an email links to sits under the path
the distribution routes. The distribution itself is not in the repo: check it with
`aws cloudfront get-distribution-config --id EGSSPJKLFL33M` (a `/v1/signup/*` behaviour on the APIGW origin).
"""
import importlib.util
import os
import re
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(__file__)
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
# The CloudFront behaviour's path pattern, published 2026-11-22: every link in an email must sit under it.
CLOUDFRONT_ROUTE = '/v1/signup/'
SITE = 'https://skyscore.co.uk'
EVENT = {'requestContext': {'domainName': 'x.execute-api.eu-west-2.amazonaws.com', 'stage': 'prod'}}


def load_signup():
    alias = 'signup_app_link_host'
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, os.path.join(HERE, '..', 'lambdas', 'signup', 'app.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


class ConfirmLinkHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_signup()
        with open(os.path.join(REPO, 'backend', 'template.yaml'), encoding='utf-8') as f:
            cls.template = f.read()

    def test_the_template_points_the_links_at_the_site(self):
        m = re.search(r"^  ConfirmUrlBase:\n(?:    .*\n)*?    Default: '([^']*)'\n(?:    .*\n)*?    AllowedPattern: '([^']*)'",
                      self.template, re.M)
        self.assertIsNotNone(m, 'ConfirmUrlBase parameter (Default, then AllowedPattern) not found in template.yaml')
        self.assertEqual(m.group(1), SITE)
        self.assertRegex(m.group(1), m.group(2), 'the default must pass the parameter\'s own pattern')
        self.assertRegex(self.template, r'(?m)^ {10}CONFIRM_URL_BASE: !Ref ConfirmUrlBase$',
                         'the parameter must reach the sign-up function\'s environment')

    def test_the_link_is_built_on_the_base(self):
        with patch.dict(os.environ, {'CONFIRM_URL_BASE': SITE + '/'}):
            self.assertEqual(self.app.confirm_url_base(EVENT), SITE)

    def test_with_no_base_it_falls_back_to_the_request_host(self):
        with patch.dict(os.environ, {'CONFIRM_URL_BASE': ''}):
            self.assertEqual(self.app.confirm_url_base(EVENT), 'https://x.execute-api.eu-west-2.amazonaws.com/prod')

    def test_every_route_an_email_links_to_is_under_the_cloudfront_route(self):
        # The confirm link (start_verification) and the unsubscribe link (the sender, when built) are the two pages a
        # person reaches from an email; both must be served through the site's domain.
        built = re.findall(r"f'\{confirm_url_base\(event\)\}(/[^?']+)", open(
            os.path.join(HERE, '..', 'lambdas', 'signup', 'app.py'), encoding='utf-8').read())
        self.assertEqual(built, ['/v1/signup/confirm'], 'the confirm link is built in one place')
        paths = set(re.findall(r'(?m)^ +Path: (/v1/signup/\S+)$', self.template))
        self.assertTrue({'/v1/signup/confirm', '/v1/signup/unsubscribe'} <= paths, paths)
        for path in {'/v1/signup/confirm', '/v1/signup/unsubscribe', *built}:
            self.assertTrue(path.startswith(CLOUDFRONT_ROUTE), path)


if __name__ == '__main__':
    unittest.main()
