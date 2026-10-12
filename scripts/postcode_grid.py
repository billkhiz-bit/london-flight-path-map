"""Where an NSPL postcode sits on the British National Grid. ONE holder (2026-10-11).

Every raster this repo samples at a postcode is EPSG:27700: DEFRA's road and
aircraft Lden, the Environment Agency flood mosaic, and DEFRA's PCM air grids.
NSPL publishes each postcode's grid reference to the metre (`east1m`,
`north1m`), and its `lat`/`long` are ONS's own conversion of that reference.
Projecting the lat/long BACK with pyproj does not land on it: with no Ordnance
Survey OSTN15 grid installed, PROJ's WGS84 -> British National Grid step is a
Helmert approximation. Measured on 2026-10-11 at 21 postcodes in 11 cities it
was 1.2 to 2.3 m off ONS's grid reference, and on a 10 m raster that is the
neighbouring cell for about one postcode in five: DE74 2SA read 49.5 dB where
DEFRA's own service gives 51.0 at ONS's grid reference, and all four
mismatches of the 21 reproduced exactly at the projected point.

NORTHERN IRELAND IS THE TRAP. NSPL gives a BT postcode's grid reference on the
IRISH Grid, so BT1 1AA's (334316, 374675), read as British, would sample the
raster near Wigan and publish a Merseyside reading for Belfast. Those rows keep
the projection of their lat/long, as does any row with no grid reference (the
Channel Islands and the Isle of Man, which NSPL parks at 99.999999, 0); both
are what every reader did before, so nothing outside Great Britain moves.
"""
from __future__ import annotations

# NSPL's Northern Ireland postcodes, whose east1m/north1m are Irish Grid.
IRISH_GRID_PREFIX = 'BT'

# The columns a reader must find in NSPL to use the grid reference. A reader
# that cannot find them must stop, not fall back to projecting every row:
# that would bring the offset back silently on a schema change.
GRID_COLUMNS = ('east1m', 'north1m')


def require_grid_columns(fieldnames, path='NSPL'):
    """Hard-fail when NSPL's header lacks the grid reference columns."""
    missing = [c for c in GRID_COLUMNS if c not in (fieldnames or [])]
    if missing:
        raise SystemExit(
            f'{path} has no {missing} column(s); header starts {list(fieldnames or [])[:10]}. '
            'Postcodes are sampled at ONS\'s grid reference (scripts/postcode_grid.py); '
            'refusing to fall back to re-projecting every lat/long.'
        )


def grid_ref(row, to_bng):
    """(easting, northing) in EPSG:27700 for one NSPL row, or None.

    `row` is a csv.DictReader row; `to_bng` a pyproj Transformer from EPSG:4326
    to EPSG:27700 built with always_xy=True, used only for the Northern Ireland
    and no-grid-reference rows described above. None when the row carries no
    usable coordinate at all.
    """
    pc = (row.get('pcds') or '').strip().upper()
    if not pc.startswith(IRISH_GRID_PREFIX):
        e = (row.get('east1m') or '').strip()
        n = (row.get('north1m') or '').strip()
        if e and n:
            try:
                return float(e), float(n)
            except ValueError:
                pass
    try:
        lat, lon = float(row['lat']), float(row['long'])
    except (KeyError, TypeError, ValueError):
        return None
    if not -90 <= lat <= 90:
        # NSPL parks an unlocatable postcode at (99.999999, 0).
        return None
    return to_bng.transform(lon, lat)
