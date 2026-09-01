"""Every unauthenticated route is either throttled per method, or listed here.

WHY THIS EXISTS. A route with no `ApiKeyRequired` and no per-method entry in
`MethodSettings` inherits the stage-wide `'*'/'*'` ceiling of 50 RPS. That has
now been found three times, each as a one-off:

  * /epc     - 2026-07-24, after a soak showed an anonymous flood could exhaust
               the MHCLG bearer quota AND starve GET /v1/score through the
               shared stage bucket
  * /badge   - 2026-08-21, "the same gap /epc had"
  * /favourites - 2026-09-01 (audit I17), where POST writes permanently into a
               PITR-backed, TTL-less, DeletionPolicy: Retain table

Three instances of one shape is a class, and the fix for a class is a check.
Nothing asserted this, so the next unauthenticated route inherits 50 RPS
silently - exactly how the first three did.

WHY AN ALLOW-LIST RATHER THAN A BLANKET REQUIREMENT. Five routes are on the
stage ceiling today and choosing their limits is a product decision, not a
test's: /nhs, /sold-prices and /transport are called by the consumer site on
every postcode lookup, so a limit set too low 429s real visitors, and the right
number depends on traffic nobody has measured yet. Listing them makes the
omission DELIBERATE AND VISIBLE instead of accidental, and - the part that
matters - a route in NEITHER list fails, so a new one cannot join them quietly.

Removing a route from the list without adding a throttle fails. That is the
point: the list is a decision record, not a mute button.
"""

import os
import re
import unittest

TEMPLATE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'template.yaml'))

# Unauthenticated routes deliberately left on the stage-wide ceiling, with the
# reason each is still open. Move a route OUT of here by giving it a
# `MethodSettings` entry - not by deleting the line.
ON_THE_STAGE_CEILING = {
    ('/nhs', 'GET'): 'consumer site calls it per postcode lookup; limit unmeasured',
    ('/sold-prices', 'GET'): 'consumer site calls it per postcode lookup; limit unmeasured',
    ('/transport', 'GET'): 'consumer site calls it per postcode lookup; limit unmeasured',
    ('/v1/regions', 'GET'): 'static metadata, no upstream and no write',
    ('/v1/changes', 'GET'): 'static metadata, no upstream and no write',
}


def _read():
    with open(TEMPLATE, encoding='utf-8') as handle:
        return handle.read().replace('\r\n', '\n')


def _routes(text):
    """(path, method, key_required) for every Api event in the template.

    Read textually, not with a YAML parser: the template is full of CFN
    intrinsics (!Ref, !GetAtt) that safe_load rejects - the same reason
    FreeTierQuotaDriftTests gives for reading its own block by hand.

    The window for a route is its own Properties block, bounded by the first
    line indented no further than `Path:` itself. Reading a fixed number of
    lines ahead is what made an early version of this call /v1/chat
    unauthenticated when its `ApiKeyRequired` sits six lines below `Path`.
    """
    lines = text.split('\n')
    out = []
    for i, line in enumerate(lines):
        match = re.match(r'^(\s*)Path: (\S+)\s*$', line)
        if not match:
            continue
        indent, path = len(match.group(1)), match.group(2)
        window = []
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) < indent:
                break
            window.append(nxt)
        method = None
        for entry in window:
            found = re.match(r'^\s*Method: (\w+)\s*$', entry)
            if found:
                method = found.group(1).upper()
                break
        if method:
            out.append((path, method, any('ApiKeyRequired: true' in w for w in window)))
    return out


def _throttled(text):
    return {
        (m.group(2), m.group(1).upper())
        for m in re.finditer(r'- HttpMethod: (\S+)\n\s*ResourcePath: (\S+)', text)
    }


class RouteThrottleTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        text = _read()
        cls.routes = _routes(text)
        cls.throttled = _throttled(text)

    def test_the_template_was_actually_parsed(self):
        """A parse that finds nothing must fail, not pass every check below."""
        self.assertGreaterEqual(
            len(self.routes), 12,
            f'only {len(self.routes)} routes parsed out of template.yaml - the '
            'Events layout changed, so this gate is checking nothing. Fix the '
            'parser, do not delete it.')
        self.assertGreaterEqual(
            len(self.throttled), 5,
            f'only {len(self.throttled)} per-method throttles parsed - the '
            'MethodSettings layout changed.')
        # The parser must see key gating where it exists, or every gated route
        # would be waved through as "not our problem".
        self.assertTrue(
            any(keyed for _p, _m, keyed in self.routes),
            'no route parsed as API-key gated, but /v1/score is - the '
            'ApiKeyRequired lookup is broken.')

    def test_every_unauthenticated_route_is_throttled_or_listed(self):
        missing = []
        for path, method, keyed in sorted(set(self.routes)):
            if method == 'OPTIONS' or keyed:
                continue
            if (path, method) in self.throttled or (path, '*') in self.throttled:
                continue
            if (path, method) in ON_THE_STAGE_CEILING:
                continue
            missing.append(f'{method} {path}')
        self.assertEqual(
            [], missing,
            'these routes need no API key AND have no per-method throttle, so '
            'they inherit the stage ceiling of 50 RPS:\n  ' + '\n  '.join(missing) +
            '\nGive each a MethodSettings entry, or add it to '
            'ON_THE_STAGE_CEILING with the reason it is being left.')

    def test_the_allow_list_has_no_stale_entries(self):
        """A listed route that has since been throttled must leave the list.

        Otherwise the list slowly becomes a place names go to be forgotten, and
        stops describing anything - the "list of mirrors that omits a mirror"
        failure in its other direction.
        """
        declared = {(p, m) for p, m, _k in self.routes}
        stale = []
        for key in sorted(ON_THE_STAGE_CEILING):
            if key not in declared:
                stale.append(f'{key[1]} {key[0]} - no such route in the template')
            elif key in self.throttled:
                stale.append(f'{key[1]} {key[0]} - now throttled; remove it from the list')
        self.assertEqual([], stale, '\n  '.join(stale))

    def test_no_route_is_throttled_twice(self):
        """CFN renders MethodSettings into ORDERED patches; the later wins.

        The 2026-07-25 scar: /v1/score and /v1/score/batch were each declared
        twice, and the silent winner was an older 5/10 pair, capping both
        revenue routes for all customers combined.
        """
        text = _read()
        pairs = re.findall(r'- HttpMethod: (\S+)\n\s*ResourcePath: (\S+)', text)
        seen, dupes = set(), []
        for method, path in pairs:
            key = (path, method.upper())
            if key in seen:
                dupes.append(f'{method} {path}')
            seen.add(key)
        self.assertEqual(
            [], dupes,
            'declared more than once in MethodSettings, where the LATER entry '
            'wins silently:\n  ' + '\n  '.join(dupes))


if __name__ == '__main__':
    unittest.main()
