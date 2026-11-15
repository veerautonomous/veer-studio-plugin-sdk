"""WGS84 lat/lon → local ENU coordinate conversion.

Projects via pyproj using the project's :class:`SiteOrigin`
for the anchor point and projection method.  An origin is **required** —
there is no default frame.  A silent fallback is how two layers end up in
different frames while looking aligned, so a missing origin is an error
that names how to get a real one.
"""

from __future__ import annotations

from functools import lru_cache

import pyproj

# -- Grid spacing for UTM grid origin snap --
_GRID_SIZE = 100_000.0  # metres — aligns with Autoware MGRS 100 km convention

# -- Cache size for per-origin transformers --
# Building a pyproj Transformer is expensive: it runs a full PROJ
# coordinate-operation search against proj.db (tens of ms cold).  A
# transformer and a grid origin are pure functions of the origin's CRS
# parameters, so they are memoised — otherwise the per-point entry points
# rebuild one per node, and a metro-scale OSM import spends all its time in
# proj_create_operations instead of projecting.  A handful of entries covers
# any real session (one active site origin, plus scratch ones in tests).
_ORIGIN_CACHE = 8

# The refusal, naming both doors to a real origin (owner ruling, sdk#1).
_ORIGIN_REQUIRED = (
    "no SiteOrigin given — build one "
    "(SiteOrigin.from_bbox(bbox)) or read the stage's "
    "(ctx.stage_manager.read_site_origin(stage)); there is no default "
    "projection frame"
)


def _require_origin(origin) -> None:
    """Refuse a missing origin — the two ways to get a real one, named."""
    if origin is None:
        raise ValueError(_ORIGIN_REQUIRED)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def latlon_to_local_enu(
    lat: float,
    lon: float,
    ele: float = 0.0,
    *,
    origin=None,
) -> tuple[float, float, float]:
    """Convert a single WGS84 lat/lon to local ENU (metres from site origin).

    Args:
        lat: WGS84 latitude in degrees.
        lon: WGS84 longitude in degrees.
        ele: Elevation in metres (default 0).
        origin: :class:`SiteOrigin` defining the local
                coordinate anchor.  **Required** — ``None`` (or omitted)
                raises ``ValueError`` (there is no default frame).

    Returns:
        ``(local_x, local_y, local_z)`` in metres.
    """
    _require_origin(origin)

    if origin.anchor_mode == "tangent_plane":
        return _tangent_plane_enu(origin, lat, lon, ele)

    # utm_grid (default)
    return _utm_grid_enu(origin, lat, lon, ele)


def batch_latlon_to_local_enu(
    nodes_dict: dict,
    *,
    origin=None,
) -> dict:
    """Convert all OSM nodes from lat/lon to local ENU.

    Args:
        nodes_dict: ``{id: {'lat': float, 'lon': float, 'tags': {'ele': str, ...}}}``
        origin: :class:`SiteOrigin` defining the local
                coordinate anchor.  **Required** — ``None`` (or omitted)
                raises ``ValueError`` (there is no default frame).

    Returns:
        ``{id: (local_x, local_y, local_z)}``
    """
    _require_origin(origin)

    if not nodes_dict:
        return {}

    if origin.anchor_mode == "tangent_plane":
        return _tangent_plane_batch(origin, nodes_dict)

    return _utm_grid_batch(origin, nodes_dict)


# ---------------------------------------------------------------------------
# Tangent plane (AEQD centred on anchor)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=_ORIGIN_CACHE)
def _aeqd_transformer_cached(lat: float, lon: float):
    """Cached AEQD transformer centred on ``(lat, lon)``.

    Azimuthal equidistant projection gives true distance and direction from
    the centre point — perfect for a local tangent plane.
    """
    # AEQD centred on the anchor.  x = easting, y = northing in metres.
    aeqd_crs = (
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} "
        f"+datum=WGS84 +units=m +no_defs"
    )
    return pyproj.Transformer.from_crs("EPSG:4326", aeqd_crs, always_xy=True)


def _aeqd_transformer(origin):
    """AEQD transformer for *origin*'s anchor — cached, see above."""
    return _aeqd_transformer_cached(origin.anchor_lat, origin.anchor_lon)


def _tangent_plane_enu(origin, lat: float, lon: float, ele: float):
    trans = _aeqd_transformer(origin)
    x, y = trans.transform(lon, lat)
    return x, y, ele


def _tangent_plane_batch(origin, nodes_dict: dict) -> dict:
    trans = _aeqd_transformer(origin)
    result = {}
    for nid, node in nodes_dict.items():
        x, y = trans.transform(node["lon"], node["lat"])
        ele = float(node.get("tags", {}).get("ele", 0.0))
        result[nid] = (x, y, ele)
    return result


# ---------------------------------------------------------------------------
# UTM grid
# ---------------------------------------------------------------------------

def _require_utm_epsg(origin) -> int:
    """*origin*'s UTM EPSG code, or a clear error if the zone is unset."""
    epsg = origin.utm_epsg
    if epsg is None:
        raise ValueError("UTM zone/hemisphere not set on SiteOrigin")
    return epsg


@lru_cache(maxsize=_ORIGIN_CACHE)
def _crs_transformer(epsg: int):
    """Cached WGS84 → ``EPSG:<epsg>`` transformer (``always_xy``: lon, lat)."""
    return pyproj.Transformer.from_crs(
        "EPSG:4326", f"EPSG:{epsg}", always_xy=True,
    )


def _utm_transformer(origin):
    """UTM transformer for *origin*'s zone and hemisphere — cached."""
    return _crs_transformer(_require_utm_epsg(origin))


@lru_cache(maxsize=_ORIGIN_CACHE)
def _grid_origin_cached(epsg: int, anchor_lon: float, anchor_lat: float):
    """Cached grid origin for an anchor: UTM easting/northing floored."""
    anchor_e, anchor_n = _crs_transformer(epsg).transform(anchor_lon, anchor_lat)
    return (anchor_e // _GRID_SIZE) * _GRID_SIZE, (anchor_n // _GRID_SIZE) * _GRID_SIZE


def _grid_origin(origin):
    """Compute the UTM grid origin (floored to _GRID_SIZE) from the anchor point."""
    return _grid_origin_cached(
        _require_utm_epsg(origin), origin.anchor_lon, origin.anchor_lat
    )


def _utm_grid_enu(origin, lat: float, lon: float, ele: float):
    """Per-point projection — cheap to call in a loop: both helpers below are
    memoised, so this is two cache lookups plus one ``transform()``."""
    trans = _utm_transformer(origin)
    origin_e, origin_n = _grid_origin(origin)
    utm_e, utm_n = trans.transform(lon, lat)
    return utm_e - origin_e, utm_n - origin_n, ele


def _utm_grid_batch(origin, nodes_dict: dict) -> dict:
    trans = _utm_transformer(origin)
    origin_e, origin_n = _grid_origin(origin)
    result = {}
    for nid, node in nodes_dict.items():
        utm_e, utm_n = trans.transform(node["lon"], node["lat"])
        ele = float(node.get("tags", {}).get("ele", 0.0))
        result[nid] = (utm_e - origin_e, utm_n - origin_n, ele)
    return result
