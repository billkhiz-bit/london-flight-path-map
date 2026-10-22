"""Sky Score for Claude: a LOCAL MCP server over the live Sky Score API (2026-10-22).

Option 1 of the MCP idea (Bill, 2026-10-22): Claude Desktop or Claude Code starts this over stdio on the
owner's own machine, and every figure Claude gives comes from the API's own response, carried through with its
`sources` array (terms.html obliges any integrator to pass them on). Nothing is hosted and nothing is public; the
public connector (option 2) is gated on the rename, verified signups, the ICO fee and legal batch 2 (ROADMAP).

The key is the server's OWN free-tier key, SKY_SCORE_MCP_KEY, never the CI key (a blocking preflight gate spends
that one's allowance) nor the free-tier key the scope test holds. It is read from the environment, else from the
repo's .env (that one line only), and is sent only as the X-Api-Key header: never printed, logged or returned.

Tools (all read-only, each one API call or a few):
  score_area       /v1/score for a postcode, ZIP or borough, under a persona
  compare_areas    /v1/score for two to five places, side by side (one call each: the free plan refuses batch)
  list_regions     /v1/regions, the cities and boroughs covered (no key)
  score_changes    /v1/changes, London's quarter-on-quarter movement (no key)
  environment_at   /v1/environment, measured air, road noise and flood at a coordinate (no key)

  python mcp-server/sky_score_mcp.py      run over stdio (what Claude does; see mcp-server/README.md)
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

REPO = Path(__file__).resolve().parent.parent
API_BASE = os.environ.get('SKY_SCORE_API_BASE', 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod')
KEY_VAR = 'SKY_SCORE_MCP_KEY'
TIMEOUT_S = 30
UA = 'Sky Score local MCP server (skyscore.co.uk)'
Persona = Literal['balanced', 'family', 'investor', 'firsttime', 'quietlife', 'renter', 'commuter', 'laterlife']
# A UK postcode or a US ZIP (with an optional +4), as typed; the API resolves and refuses what it cannot place.
POSTCODE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 -]{1,9}$')
NAME = re.compile(r"^[A-Za-z][A-Za-z .,'&()-]{0,59}$")
CITY = re.compile(r'^[a-z]{2,20}$')

INSTRUCTIONS = """\
Sky Score measures how liveable a UK (or New York) area is: aircraft noise, affordability, price growth,
liveability and environment. Answer ONLY from what the tools return, and follow these rules:
- Scores rise = better and are named for the good thing ("Quiet Skies 8/10"); measurements rise = worse and are
  named for the bad thing ("Aircraft noise 2/10"). They can be one value under two labels: never "correct" one
  to match the other.
- Quiet Skies is an ESTIMATE from published flight routes, not a noise measurement, and never says how OFTEN
  planes pass. Shares are of POSTCODES (or US residents), never of addresses.
- Where the response says an input is missing, unavailable or withheld, say so; never fill the gap with a
  guess or a typical value.
- End every answer that uses a figure with the response's `sources` (UK routes are credited "UK AIP (NATS)";
  carry the FAA's "as is" line wherever it appears). Do not describe the whole product as "open government data".
- This is information, not advice: not a survey, a valuation or a conveyancing search.
"""

mcp = FastMCP('Sky Score', instructions=INSTRUCTIONS)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


def api_key():
    """The server's own key: the environment first, else the one line of the repo's .env. None if neither."""
    key = os.environ.get(KEY_VAR)
    if key:
        return key.strip()
    try:
        for line in (REPO / '.env').read_text(encoding='utf-8').splitlines():
            if line.startswith(f'{KEY_VAR}='):
                return line.split('=', 1)[1].strip().strip('"') or None
    except OSError:
        return None
    return None


class ApiError(ToolError):
    """The API answered with an error status: its own message, and the status, never the key."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _get(path, params=None, keyed=False):
    """One GET to the API; its JSON, or a ToolError carrying the API's own message (never the key)."""
    url = f'{API_BASE}{path}'
    if params:
        url += '?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    key = None
    if keyed:
        key = api_key()
        if not key:
            raise ToolError(f'{KEY_VAR} is not set: add the server\'s own key to the repo\'s .env (see mcp-server/README.md)')
        # unredirected: urllib copies ordinary headers onto a redirect, to whatever host it names
        req.add_unredirected_header('X-Api-Key', key)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310 - fixed https base
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except ValueError:
            body = None
        message = (body.get('message') or body.get('error') or '') if isinstance(body, dict) else ''
        message = message if isinstance(message, str) else ''
        if e.code == 429:
            message = message or 'rate or monthly limit reached for this key'
        if key:
            # an error page that echoed the key would put it in Claude's context; it never leaves this function
            message = message.replace(key, '[key]')
        raise ApiError(e.code, f'Sky Score API {e.code} on {path}: {message or e.reason}') from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise ToolError(f'Sky Score API unreachable on {path}: {getattr(e, "reason", e)}') from None
    except ValueError:
        raise ToolError(f'Sky Score API answered {path} with something that is not JSON') from None


_regions = None


def cities_listing(name):
    """The city keys whose borough list (/v1/regions: open, no key, read once a session) holds `name`."""
    global _regions
    if _regions is None:
        cities = _get('/v1/regions').get('cities') or []
        _regions = [(c['id'], {b.casefold() for b in c.get('boroughs') or []}) for c in cities]
    return [cid for cid, names in _regions if name.casefold() in names]


def _place_params(place, city):
    """Postcode/ZIP or borough name -> (the /v1/score query, the cities listing a borough name).

    The API defaults `city` to London, so a borough asked for with no city is asked in London, and a city sent
    with a postcode overrides the city the postcode places itself in (the code review, 2026-10-22: Salford read
    NOT COVERED YET). So a postcode never carries `city`, and a borough name with none takes the one city that
    lists it, or is refused when several do. Refuses what is neither before anything leaves the machine.
    """
    place = (place or '').strip()
    if city is not None and not CITY.match(city):
        raise ToolError(f'city {city!r} is not a city key (use list_regions for the keys)')
    if any(ch.isdigit() for ch in place):
        if not POSTCODE.match(place):
            raise ToolError(f'{place!r} does not look like a UK postcode or a US ZIP')
        return {'postcode': place.upper()}, None
    if not NAME.match(place):
        raise ToolError(f'{place!r} does not look like a postcode, a ZIP or a borough name')
    listing = cities_listing(place)
    if city is None and len(listing) > 1:
        raise ToolError(f'{place} is a borough name in {", ".join(listing)}: say which with `city`')
    return {'borough': place, 'city': city or (listing[0] if listing else None)}, listing


def _score(place, params, listing):
    """/v1/score, with a 404 said as the product says it.

    NOT COVERED YET only where it is true: a postcode (the API placed it itself) or a name no city lists. A
    name some city DOES list, asked in another, was asked in the wrong city, and says so. The API's own 404
    for an uncovered postcode names the default city (EX1 1HS: "Borough not currently supported in london",
    measured 2026-10-22), so its words are kept after the plain statement, never instead of it.
    """
    try:
        return _get('/v1/score', params, keyed=True)
    except ApiError as e:
        if e.status != 404:
            raise
        if listing:
            raise ToolError(f"{place} is not a borough of {params.get('city')}; Sky Score lists it under "
                            f"{', '.join(listing)}: ask again with that city. ({e})") from None
        raise ToolError(f'{place} is NOT COVERED YET by Sky Score, or is not a place it can find; there is no '
                        f'score for it. list_regions lists what is covered. ({e})') from None


def _compare_params(place, city):
    """compare_areas' one `city` settles only the names that need it: one two cities share, or one no city lists.
    Applied to every place, it would ask Hounslow in Manchester the moment Salford was compared with it.
    """
    try:
        params, listing = _place_params(place, None)
    except ToolError:
        if city is None:
            raise
        return _place_params(place, city)
    if city is not None and 'borough' in params and not listing:
        return _place_params(place, city)
    return params, listing


@mcp.tool(title='Score an area', annotations=READ_ONLY)
def score_area(place: str, city: str | None = None, persona: Persona = 'balanced',
               compare_previous: bool = False) -> dict[str, Any]:
    """Sky Score for one place: a UK postcode (SW11 1AA), a New York ZIP (10001), or a borough name (Hounslow).

    A borough name finds its own city; `city` (a list_regions key) is needed only where two cities share the
    name, and a postcode or ZIP always places itself. `persona` sets the weights. `compare_previous` adds the
    change since the previous quarterly vintage. Returns the API's response whole, including `sources`, which
    must be cited.
    """
    params, listing = _place_params(place, city)
    params['persona'] = persona
    if compare_previous:
        params['compare'] = 'previous'
    return _score(place, params, listing)


@mcp.tool(title='Compare areas', annotations=READ_ONLY)
def compare_areas(places: list[str], city: str | None = None, persona: Persona = 'balanced') -> dict[str, Any]:
    """Two to five places side by side under one persona: each place's score and components, plus every source
    named by any of them. Places are postcodes, ZIPs or borough names, as score_area takes them, and may be in
    different cities; `city` only settles a borough name two cities share.
    """
    if not 2 <= len(places) <= 5:
        raise ToolError('compare two to five places')
    rows, sources = [], []
    for place in places:
        params, listing = _compare_params(place, city)
        params['persona'] = persona
        doc = _score(place, params, listing)
        rows.append({'place': place, 'score': doc.get('score'), 'components': doc.get('components'),
                     'location': doc.get('location'), 'context': doc.get('context')})
        sources += [s for s in doc.get('sources') or [] if s not in sources]
    return {'persona': persona, 'places': rows, 'sources': sources}


@mcp.tool(title='List covered regions', annotations=READ_ONLY)
def list_regions() -> dict[str, Any]:
    """The cities and boroughs Sky Score covers, with each city's key and postcode format."""
    return _get('/v1/regions')


@mcp.tool(title="London's score changes", annotations=READ_ONLY)
def score_changes() -> dict[str, Any]:
    """Every London borough's score now against the previous quarterly vintage, with why each moved."""
    return _get('/v1/changes')


@mcp.tool(title='Environment at a point', annotations=READ_ONLY)
def environment_at(lat: float, lon: float) -> dict[str, Any]:
    """Measured air quality, road noise and flood readings at a coordinate (UK coverage), with their sources.
    Measurements only: no score and no weights.
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ToolError('lat must be -90..90 and lon -180..180')
    return _get('/v1/environment', {'lat': f'{lat:.6f}', 'lon': f'{lon:.6f}'})


if __name__ == '__main__':
    mcp.run()
