"""DEFRA's and the Environment Agency's figures are MODELLED, and the surfaces developers and agents read say so
(2026-10-23).

DEFRA's strategic noise maps and PCM air values, and the EA's flood map, are model outputs. The consumer page
`/how-it-works/` said so; the API page, the OpenAPI spec, METHODOLOGY's body, the README and the MCP server's
`environment_at` tool called them "measured", and the codebase keeps "measured air quality" for the AURN and
Breathe London sensors. An auditor following our provenance would read a model as an instrument. The same tool
also promised a flood value `/v1/environment` never returns.

`measured` as a VALUE of `liveResolution` / `environmentResolution`, and the field `measuredAtLocation`, stay:
renaming them breaks integrators. Their descriptions define them (present for this place; read at this location).
METHODOLOGY's dated changelog (section 20) is history, quoted as it was, so it is not scanned.
"""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SURFACES = ('api/index.html', 'score-demo/openapi.yaml', 'mcp-server/sky_score_mcp.py', 'mcp-server/README.md',
            'METHODOLOGY.md', 'README.md', 'how-it-works/index.html')
CLAIM = re.compile(r'DEFRA measure(?:d|ment)|measured air(?:\s+quality)?,?\s+road'
                   r'|(?:against|closer to|toward) the measurement', re.I)


def body(rel, text):
    return text.split('## 20. Changelog')[0] if rel == 'METHODOLOGY.md' else text


def claims(text):
    """Every phrase in `text` that calls DEFRA's modelled values measured."""
    return [m.group(0) for m in CLAIM.finditer(text)]


def environment_tool_doc(source):
    """The `environment_at` tool's docstring from the MCP server's source."""
    fn = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == 'environment_at')
    return ast.get_docstring(fn) or ''


def promised_flood(doc):
    """True when the tool's description offers a flood value (it may say it has none)."""
    return bool(re.search(r'flood', doc, re.I)) and not re.search(r'no flood', doc, re.I)


def test_no_surface_calls_defra_s_modelled_values_measured():
    found = {rel: claims(body(rel, (REPO / rel).read_text(encoding='utf-8'))) for rel in SURFACES}
    assert {rel: c for rel, c in found.items() if c} == {}


def test_the_environment_tool_promises_no_flood_value_the_endpoint_never_returns():
    app = (REPO / 'backend' / 'lambdas' / 'score' / 'app.py').read_text(encoding='utf-8')
    start = app.index('def build_environment(')
    builder = app[start:app.index('\ndef ', start + 1)]
    doc = environment_tool_doc((REPO / 'mcp-server' / 'sky_score_mcp.py').read_text(encoding='utf-8'))
    assert re.search(r'modelled', doc, re.I), 'the tool must tell an agent the values are modelled'
    if 'flood' not in builder.lower():
        assert not promised_flood(doc), '/v1/environment returns no flood value, so the tool may not offer one'
