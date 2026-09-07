"""Every unauthenticated route is either throttled per method, or listed here.

WHY THIS EXISTS. A route with no `ApiKeyRequired` and no per-method entry in
`MethodSettings` inherits the stage-wide `'*'/'*'` ceiling of 50 RPS. That has
now been found four times, the first three each as a one-off:

  * /epc     - 2026-07-24, after a soak showed an anonymous flood could exhaust
               the MHCLG bearer quota AND starve GET /v1/score through the
               shared stage bucket
  * /badge   - 2026-08-21, "the same gap /epc had"
  * /favourites - 2026-09-01 (audit I17), where POST writes permanently into a
               PITR-backed, TTL-less, DeletionPolicy: Retain table
  * /nhs, /sold-prices, /transport, /v1/regions, /v1/changes - throttled
               2026-09-07 from measured traffic, and the FOURTH occasion was
               caught by this file rather than by an audit, which is the whole
               reason it was written.

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
#
# EMPTY SINCE 2026-09-07, and the emptying is the point: this list held all
# five remaining routes with the reason "limit unmeasured", which was true and
# was blocked on `flightmap-dev` being denied the CloudWatch verbs. The deploy
# policy was restored on 2026-09-04, the traffic was measured the same week
# with `scripts/measure_route_traffic.py`, and every route got a number derived
# from it. The list did exactly what its docstring promised - it kept a known
# omission visible until the thing it waited on arrived.
#
# Leave the mechanism here. An empty allow-list is not a dead one: the next
# unauthenticated route still fails unless it is throttled or listed.
ON_THE_STAGE_CEILING: dict[tuple[str, str], str] = {}


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


def _unquote(value):
    """The wildcard entry is written `HttpMethod: '*'` / `ResourcePath: '/*'`.

    YAML needs the quotes there; a regex reading the raw text captures them, so
    the catch-all arrives as "'/*'" and compares equal to nothing. Every other
    entry is unquoted, which is why this went unnoticed - the one row it
    mangles is the one row nothing looked up.
    """
    return value.strip('\'"')


def _throttled(text):
    return {
        (_unquote(m.group(2)), _unquote(m.group(1)).upper())
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

    def test_no_throttle_points_at_a_route_that_does_not_exist(self):
        """`ResourcePath` is free text, so a typo declares a limit on nothing.

        This is the gap this whole file guards, wearing a disguise: the entry
        looks present in review, CloudFormation accepts it without complaint,
        and the real route quietly keeps the 50 RPS ceiling. The sibling test
        above cannot see it - it asks whether a path is throttled and a
        misspelled path answers for a route nobody called.
        """
        declared = {(p, m) for p, m, _k in self.routes}
        phantom = [
            f'{method} {path}'
            for path, method in sorted(self.throttled)
            if path != '/*' and (path, method) not in declared
        ]
        self.assertEqual(
            [], phantom,
            'MethodSettings throttles a path with no matching Api event, so the '
            'limit applies to nothing and the route it was meant for still '
            'inherits the stage ceiling:\n  ' + '\n  '.join(phantom))

    def test_no_per_route_limit_is_at_or_above_the_stage_ceiling(self):
        """An entry at the ceiling reads as a control and constrains nothing.

        It is worse than no entry, because the sibling tests then report the
        route as throttled and the allow-list stops naming it - a route can go
        from a visible omission to an invisible one without any value changing
        by more than the difference between 50 and 50.
        """
        text = _read()
        # The comment-skipping group is load-bearing, not defensive. Every
        # entry added since 2026-07-24 carries its rationale ABOVE
        # `ThrottlingRateLimit`, and the `'*' '/*'` ceiling has eleven comment
        # lines there - so a regex demanding four consecutive lines matched
        # every route EXCEPT the ceiling, which is the one value the rest of
        # this test is compared against.
        entries = re.findall(
            r'- HttpMethod: (\S+)\n\s*ResourcePath: (\S+)\n'
            r'(?:\s*#[^\n]*\n)*'
            r'\s*ThrottlingRateLimit: (\d+)\n\s*ThrottlingBurstLimit: (\d+)',
            text)
        self.assertGreaterEqual(
            len(entries), 5,
            f'only {len(entries)} complete rate/burst entries parsed - the '
            'MethodSettings layout changed, so this is checking nothing.')
        entries = [
            (_unquote(m), _unquote(p), r, b) for m, p, r, b in entries
        ]
        ceiling = {
            (p, m.upper()): (int(r), int(b)) for m, p, r, b in entries
        }.get(('/*', '*'))
        self.assertIsNotNone(
            ceiling, "no '*' '/*' entry parsed, so there is no ceiling to "
                     'compare against and this test proves nothing.')
        useless = [
            f'{m} {p} at {r}/{b}'
            for m, p, r, b in entries
            if p != '/*' and (int(r) >= ceiling[0] or int(b) >= ceiling[1])
        ]
        self.assertEqual(
            [], useless,
            f'declared at or above the {ceiling[0]}/{ceiling[1]} stage ceiling, '
            'so they are not per-route limits at all:\n  ' + '\n  '.join(useless))

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
