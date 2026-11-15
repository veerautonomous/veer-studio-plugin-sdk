"""Project prim-root getters — the host's ``core.paths`` when present, a standalone copy when not."""

from __future__ import annotations

try:
    from core.paths import (
        assets_root,
        cameras_root,
        color_field_prim_path,
        colorfields_root,
        navigation_root,
        pointcloud_frame_path,
        pointclouds_root,
        reality_root,
        reference_barriers_root,
        reference_buildings_root,
        reference_landuse_root,
        reference_other_root,
        reference_root,
        reference_roads_root,
        reference_satellite_root,
        reference_water_root
    )
except ModuleNotFoundError as _exc:
    if _exc.name != "core":
        raise
    from veer_plugin_sdk._paths_fallback import (
        assets_root,
        cameras_root,
        color_field_prim_path,
        colorfields_root,
        navigation_root,
        pointcloud_frame_path,
        pointclouds_root,
        reality_root,
        reference_barriers_root,
        reference_buildings_root,
        reference_landuse_root,
        reference_other_root,
        reference_root,
        reference_roads_root,
        reference_satellite_root,
        reference_water_root
    )

__all__ = [
    'assets_root',
    'cameras_root',
    'color_field_prim_path',
    'colorfields_root',
    'navigation_root',
    'pointcloud_frame_path',
    'pointclouds_root',
    'reality_root',
    'reference_barriers_root',
    'reference_buildings_root',
    'reference_landuse_root',
    'reference_other_root',
    'reference_root',
    'reference_roads_root',
    'reference_satellite_root',
    'reference_water_root',
]
