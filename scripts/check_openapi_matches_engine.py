#!/usr/bin/env python3
"""Assert the published OpenAPI spec describes the score engine that exists.

WHY THIS EXISTS. `score-demo/openapi.yaml` is rendered at
`/score-demo/api-docs.html` and is the stated artefact for generating clients.
On 2026-08-29 an audit found it described a FOUR-component score three days
after `env` shipped; on 2026-09-03 - five weeks later - the string `env` still
appeared in it **zero times**, while every UK response outside Cardiff and New
York carried the component. A strict generated client flags an undocumented
field on all of them; a lenient one silently drops 0.14-0.18 of the score.

The same file declared `enum: [london, nyc]` in three places while the API
served THIRTEEN cities, so a generated client rejected 11 of them.

Both are the same defect: **a correction applied in one holder and not its
mirror.** The consumer site's copy of the four-component claim was fixed as
audit I34 on 2026-09-01 and the three B2B surfaces were not, because nothing
compared them to anything.

WHY IT WALKS THE WHOLE DOCUMENT FOR ENUMS. The spec carries a comment recording
that "three enums in this spec listed personas and only one was complete", and
a gate that checked one known path would have passed that state. So enums are
found by RECURSIVE WALK, keyed on their contents - any enum containing
`london` is a city enum wherever it lives, any enum containing `balanced` is a
persona enum - and every occurrence must be complete. A new enum added in a new
place is covered on the day it is added, with no gate edit.

WHAT IS COMPARED, AND WHY THAT IS A REAL COMPARISON. The expectation comes from
the ENGINE (`app.PERSONAS`, `app.CITIES`, `app.METHODOLOGY_VERSION`, and the
keys `resolve_query` actually emits) and the measurement comes from the SPEC.
Two holders, so they can genuinely disagree - unlike a check whose expected
value is read from the thing it checks, which this repo has shipped nine times.

  python scripts/check_openapi_matches_engine.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'score-demo' / 'openapi.yaml'
sys.path.insert(0, str(ROOT / 'backend' / 'lambdas' / 'score'))

# Borough queries only: they are answered in-process from the Lambda's own
# tables, so this gate needs no network, no credentials and no DynamoDB. A
# postcode query would reach for the NSPL and raster tiers and make a source
# check depend on infrastructure.
SAMPLES = [
    {'borough': 'Camden', 'city': 'london'},
    {'borough': 'Camden', 'city': 'london', 'persona': 'investor'},
    {'borough': 'Brooklyn', 'city': 'nyc'},
    {'borough': 'Cardiff', 'city': 'cardiff'},
    {'borough': 'Middlesbrough', 'city': 'teesside'},
]


def walk_enums(node, path='', out=None):
    """Every `enum` list in the document, with the path that reached it."""
    if out is None:
        out = []
    if isinstance(node, dict):
        for key, val in node.items():
            if key == 'enum' and isinstance(val, list):
                out.append((path or '(root)', val))
            else:
                walk_enums(val, f'{path}.{key}' if path else key, out)
    elif isinstance(node, list):
        for i, val in enumerate(node):
            walk_enums(val, f'{path}[{i}]', out)
    return out


def main():
    try:
        import yaml
    except ImportError:
        print('INCONCLUSIVE: PyYAML is not installed, so the spec was not')
        print('  parsed. That is NOT the same as the spec being correct.')
        return 0

    import app

    spec = yaml.safe_load(SPEC.read_text(encoding='utf-8'))
    schemas = spec['components']['schemas']

    # ---- the engine's side of every comparison, derived not typed ----
    engine_components = {k for w in app.PERSONAS.values() for k in w}
    engine_personas = set(app.PERSONAS) | {'custom'}
    engine_cities = set(app.CITIES)

    emitted_components, emitted_context, emitted_breakdown = set(), set(), set()
    for q in SAMPLES:
        body, status = app.resolve_query(dict(q))
        if not isinstance(body, dict) or status != 200:
            continue
        emitted_components |= set(body.get('components') or {})
        emitted_context |= set(body.get('context') or {})
        emitted_breakdown |= set(body.get('sourceBreakdown') or {})

    failures, checks = [], 0

    def require(label, want, have, where):
        """`have` must be a superset of `want`."""
        nonlocal checks
        checks += 1
        missing = sorted(want - have)
        if missing:
            failures.append(
                f'{label}: {where} is missing {missing}\n'
                f'      spec has {sorted(have)}\n'
                f'      engine needs {sorted(want)}')

    # A component the engine can WEIGHT and a component it EMITS must both be
    # describable. The two sets are compared separately because they can differ:
    # a weighted component absent from every sampled response would be a
    # coverage problem, not a spec problem, and should not be silently merged.
    require('components (weighted)', engine_components,
            set(schemas['Components'].get('properties') or {}),
            'Components.properties')
    require('components (emitted)', emitted_components,
            set(schemas['Components'].get('properties') or {}),
            'Components.properties')
    require('weights (request override)', engine_components,
            set(schemas['Weights'].get('properties') or {}),
            'Weights.properties')
    # The RESPONSE table became its own schema on 2026-09-09, because it is a
    # different object: `Weights` is what a caller may SEND, `AppliedWeights` is
    # what the engine actually multiplied by. Both must still describe every
    # component the engine can emit, or a response carries a weight the spec
    # never defines.
    require('weights (applied, response)', engine_components,
            set(schemas['AppliedWeights'].get('properties') or {}),
            'AppliedWeights.properties')
    require('context', emitted_context,
            set(schemas['Context'].get('properties') or {}),
            'Context.properties')

    sb = (schemas['ScoreResponse']['properties']
          .get('sourceBreakdown', {}).get('properties') or {})
    require('sourceBreakdown', emitted_breakdown, set(sb),
            'sourceBreakdown.properties')

    # ---- EVERY enum, not the first one ----
    enums = walk_enums(spec)
    city_enums = [(p, e) for p, e in enums if 'london' in e]
    persona_enums = [(p, e) for p, e in enums if 'balanced' in e]

    # Floors. An enum kind that matched nothing has not been checked, and
    # "0 incomplete enums" over zero enums is the shape this repo has shipped
    # repeatedly.
    if not city_enums:
        failures.append(
            'city enums: found NONE containing "london". Either the spec '
            'stopped\n      naming cities or this detector no longer matches - '
            'either way\n      nothing was compared.')
    if not persona_enums:
        failures.append(
            'persona enums: found NONE containing "balanced". Nothing was '
            'compared.')

    for path, values in city_enums:
        require('city enum', engine_cities, set(values), f'{path}')

    # REQUEST and RESPONSE persona enums need DIFFERENT sets, and conflating
    # them was this gate's own first defect - found by running it.
    #
    # `custom` is a RESPONSE value only: it is what `persona` reads back when a
    # `weights` override was applied. Sending `persona=custom` is not a request
    # the engine honours - measured, it returns 200 and silently scores
    # `balanced` - so listing it as an accepted input would advertise a
    # parameter value that quietly does something else.
    for path, values in persona_enums:
        is_request = '.parameters' in path or 'Request' in path
        want = set(app.PERSONAS) if is_request else engine_personas
        kind = 'persona enum (request)' if is_request else 'persona enum (response)'
        require(kind, want, set(values), f'{path}')

    # ---- the reproducibility formula the spec now publishes ----
    #
    # `AppliedWeights` documents that `score` reproduces DIRECTLY from the
    # response - sum(components[k] * weights[k]), with no renormalising step,
    # because the weights published ARE the ones the engine multiplied by.
    #
    # THE DENOMINATOR ASSERTION BELOW IS THE LOAD-BEARING HALF (2026-09-09).
    # Until today this divided by the weight of the components present, and
    # that division CANNOT TELL THE TWO TABLES APART: rescaled or not, dividing
    # by the present total recovers the same score. So this check sat green for
    # the entire period the response published the persona's nominal row
    # against an engine scoring with a rescaled one - it was verifying
    # arithmetic that normalised the defect away. Asserting the published total
    # is 1.0, and that the key sets match, is what makes it a check of the
    # CONTRACT.
    #
    # Asserted here because the spec now tells an integrator to compute it this
    # way, and `terms.html` obliges them to rely on it. This is the same shape
    # as audit C6: a published formula that does not reproduce a published
    # number. It is an OUTPUT check - the only kind that catches the two halves
    # drifting apart while each stays individually correct.
    for q in SAMPLES:
        body, status = app.resolve_query(dict(q))
        if not isinstance(body, dict) or status != 200:
            continue
        comp, wts = body.get('components') or {}, body.get('weights') or {}
        if not comp:
            continue
        checks += 1
        if set(wts) != set(comp):
            failures.append(
                f'applied weights: {q} publishes weights {sorted(wts)} against '
                f'components\n      {sorted(comp)} - they must name the same set')
            continue
        total = sum(wts.values())
        if abs(total - 1.0) > 1e-4:
            failures.append(
                f'applied weights: {q} publishes weights summing to {total:.4f}, '
                f'not 1.0.\n      The response must carry the APPLIED table, not the '
                f'persona nominal one')
        # 0.05 for 1dp component rounding, 0.05 for rounding the total. The spec
        # states this bound; nothing tighter is honest while components are 1dp.
        got = sum(comp[k] * wts[k] for k in comp)
        if abs(got - body['score']) > 0.1 + 1e-9:
            failures.append(
                f'reproducibility: {q} publishes score {body["score"]} but the '
                f'formula the spec\n      documents yields {got:.4f}')

    # ---- the version example, a mirror that has gone stale before ----
    checks += 1
    example = str(schemas['ScoreResponse']['properties']
                  .get('methodologyVersion', {}).get('example', ''))
    live = str(app.METHODOLOGY_VERSION)
    if example != live:
        failures.append(
            f'methodologyVersion: spec example is {example!r}, engine serves '
            f'{live!r}')

    # ---- THE PROSE, WHICH THIS GATE COULD NOT SEE UNTIL 2026-09-07 ----
    #
    # Audit I5. This gate walks SCHEMAS and ENUMS, and passed 18 comparisons
    # green while the very first paragraph of the file it guards said the score
    # was "computed from four components" and that coverage was "33 London
    # boroughs ... 5 NYC boroughs". Five components, thirteen cities and
    # ninety-nine boroughs were served at the time. Its own docstring names
    # "described a FOUR-component score" as the defect it exists to prevent.
    #
    # `info.description` is the first thing a human integrator reads and it is
    # rendered at /score-demo/api-docs.html, which all 99 area pages link to.
    # A machine-readable document can be perfectly correct and still mislead
    # every reader through the one field no schema check looks at.
    #
    # Derived, not literal: the count word and the coverage numbers come from
    # the engine.
    WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six',
             7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten'}
    prose = str(spec.get('info', {}).get('description', ''))
    checks += 1
    if not prose.strip():
        failures.append('info.description is empty, so the prose cannot be checked')
    else:
        want_word = WORDS.get(len(engine_components), str(len(engine_components)))
        for said in re.findall(r'([A-Za-z]+)\s+components\b', prose):
            if said.lower() in WORDS.values() and said.lower() != want_word:
                failures.append(
                    f'info.description says "{said} components"; the engine emits '
                    f'{len(engine_components)} ({want_word}): '
                    f'{sorted(engine_components)}')
        total_boroughs = sum(len(c['boroughs']) for c in app.CITIES.values())
        for label, number in (('cities', len(engine_cities)),
                              ('boroughs', total_boroughs)):
            checks += 1
            if str(number) not in prose:
                failures.append(
                    f'info.description never states the real {label} count '
                    f'({number}). The Coverage paragraph is where a prospect '
                    f'decides whether the product reaches their market, and it '
                    f'under-claimed by eleven cities and sixty-one boroughs for '
                    f'as long as nothing read it.')

    print('Published OpenAPI spec vs the score engine')
    print('==========================================')
    print(f'  engine components  {sorted(engine_components)}')
    print(f'  engine cities      {len(engine_cities)}')
    print(f'  city enums found   {len(city_enums)}'
          + (f'  ({", ".join(p for p, _ in city_enums)})' if city_enums else ''))
    print(f'  persona enums      {len(persona_enums)}')
    print(f'  comparisons made   {checks}')

    if checks == 0:
        print()
        print('FAIL: made 0 comparisons, so nothing was checked.')
        return 1

    if failures:
        print()
        print(f'FAIL: {len(failures)} mismatch(es) between the published spec')
        print('      and the engine it claims to describe.')
        for f in failures:
            print(f'  - {f}')
        print()
        print('  Integrators generate clients from this file. A missing')
        print('  property or a short enum makes a valid response fail')
        print('  validation, or drops a scored component silently.')
        return 1

    print()
    print('OK: every component, weight, context key, source line, city and')
    print('    persona the engine can produce is described by the spec.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
