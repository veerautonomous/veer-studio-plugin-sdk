"""Standalone project-root getters — generated copy of core/paths.py.

Loaded only when the real host package is absent (author CI).  Inside
the host, ``veer_plugin_sdk.paths`` forwards to the real getters, so
the roots follow the open stage.  The default site root matches
``testing.create_stage()``.
"""
SITE_ROOT: str = "/Site_Untitled"

def assets_root() -> str:
    """``/Site_X/Assets`` — authoritative site objects (Atlas objects)."""
    return f"{SITE_ROOT}/Assets"

def cameras_root() -> str:
    """``/Site_X/Cameras`` — reference viewpoints."""
    return f"{SITE_ROOT}/Cameras"

def color_field_prim_path(index: int) -> str:
    """``/Site_X/Reality/ColorFields/ColorField_<N>`` — one colour chunk."""
    return f"{colorfields_root()}/ColorField_{index}"

def colorfields_root() -> str:
    """``/Site_X/Reality/ColorFields`` — survey-wide photo-colour container.

    The streamed photo-appearance field (``ColorField_<N>`` flat ``Points``
    chunks, one layer in ``tiles/``) lives here, outside ``PointClouds``:
    it is display appearance, not cloud geometry, so it gets its own
    read-only category and its own chip (#429).
    """
    return f"{SITE_ROOT}/Reality/ColorFields"

def navigation_root() -> str:
    """``/Site_X/Navigation`` — authoritative navigation substrate."""
    return f"{SITE_ROOT}/Navigation"

def pointcloud_frame_path(frame_index: int | str) -> str:
    """``/Site_X/Reality/PointClouds/PointCloudFrame_NNN``.

    The group-frame Xform holding one patch's ``PointCloud``.  Its
    ``xformOp:transform`` is the local→world (ENU) mapping of the measured
    points; derived meshes do **not** live here — see :func:`meshes_root`.
    """
    if isinstance(frame_index, int):
        frame_index = f"{frame_index:03d}"
    return f"{pointclouds_root()}/PointCloudFrame_{frame_index}"

def pointclouds_root() -> str:
    """``/Site_X/Reality/PointClouds`` — category container for PCD patches.

    Individual ``PointCloudFrame_NNN`` prims are children of this container.
    Use ``stage.Traverse()`` or ``prim.GetChildren()`` to enumerate them at
    runtime — there is no hardcoded path for a specific patch.
    """
    return f"{SITE_ROOT}/Reality/PointClouds"

def reality_root() -> str:
    """``/Site_X/Reality`` — measured physical data (point cloud, ground mesh)."""
    return f"{SITE_ROOT}/Reality"

def reference_barriers_root() -> str:
    """``/Site_X/Reference/Barriers`` — OSM barrier curves."""
    return f"{SITE_ROOT}/Reference/Barriers"

def reference_buildings_root() -> str:
    """``/Site_X/Reference/Buildings`` — OSM building footprints."""
    return f"{SITE_ROOT}/Reference/Buildings"

def reference_landuse_root() -> str:
    """``/Site_X/Reference/Landuse`` — OSM land-use area footprints."""
    return f"{SITE_ROOT}/Reference/Landuse"

def reference_other_root() -> str:
    """``/Site_X/Reference/Other`` — uncategorized user-created reference features."""
    return f"{SITE_ROOT}/Reference/Other"

def reference_root() -> str:
    """``/Site_X/Reference`` — unvetted source data (OSM roads, buildings, …)."""
    return f"{SITE_ROOT}/Reference"

def reference_roads_root() -> str:
    """``/Site_X/Reference/Roads`` — OSM road centerlines."""
    return f"{SITE_ROOT}/Reference/Roads"

def reference_satellite_root() -> str:
    """``/Site_X/Reference/Satellite`` — satellite/aerial imagery container."""
    return f"{SITE_ROOT}/Reference/Satellite"

def reference_water_root() -> str:
    """``/Site_X/Reference/Water`` — OSM water body footprints."""
    return f"{SITE_ROOT}/Reference/Water"
