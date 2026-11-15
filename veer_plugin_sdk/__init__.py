"""Veer Studio Plugin SDK — the contract surface for external plugin authors.

Inside the host (Veer Studio's own checkout) every name re-exports the real
``core`` object, so ``isinstance`` dispatch sees identical classes.  Outside
the host — an author's repository, CI, anywhere the SDK is pip-installed —
the same names resolve to the generated copies shipped in this package.
"""

from __future__ import annotations

try:
    from core.ports import *  # noqa: F403
    from core.contexts import *  # noqa: F403
except ModuleNotFoundError as _exc:
    if _exc.name != "core":
        raise
    from veer_plugin_sdk._ports import *  # noqa: F403
    from veer_plugin_sdk._contexts import *  # noqa: F403
    from veer_plugin_sdk._coord_utils import (
        batch_latlon_to_local_enu,
        latlon_to_local_enu,
    )
    from veer_plugin_sdk._platform_paths import (
        plugin_data_dir as _plugin_data_dir_impl,
    )

    def plugin_data_dir(plugin_id: str) -> str:
        """A plugin's data root as ``str`` — the host door's return type."""
        return str(_plugin_data_dir_impl(plugin_id))

from veer_plugin_sdk.events import (
    DomainEvent,
    ToolActivated,
    ToolDeactivated,
    ToolModeChanged,
    SublayersRewired,
    StreamedTileCratesCommitted,
    subscribe,
    unsubscribe,
    WayDeleted,
    NodesPruned,
    LaneletCommitted,
    LaneletDeleted,
    RegulatoryElementDeleted,
    AreaCreated,
    LiftSessionStarted,
    LiftSessionEnded,
)

from veer_plugin_sdk.paths import (
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
    reference_water_root,
)

__all__ = [
    'ATTR_IMPORT_MODE',
    'ATTR_IMPORT_TRANSFORM',
    'ATTR_SOURCE_CRS',
    'BaseOverlayRenderer',
    'CloudUnit',
    'CreationSession',
    'CreationVerb',
    'Diagnostic',
    'ExportReport',
    'GEOMETRIC_ROLES',
    'IExporter',
    'IFileImporter',
    'IFusionPlugin',
    'IIntegrationPlugin',
    'IPanelFactory',
    'IPluginPreferences',
    'IStageContributor',
    'IToolProvider',
    'IValidator',
    'JobSpec',
    'OverlayLayer',
    'PluginMeta',
    'Severity',
    'SiteOrigin',
    'ToolResult',
    'ValidationReport',
    'imported_source_id',
    'source_key_for',
    'DerivedCloudHandle',
    'EditorContext',
    'PanelContext',
    'StageManagerInterface',
    'StageMutationContext',
    'ToolContext',
    'ToolEvent',
    'latlon_to_local_enu',
    'batch_latlon_to_local_enu',
    'plugin_data_dir',
    'DomainEvent',
    'ToolActivated',
    'ToolDeactivated',
    'ToolModeChanged',
    'SublayersRewired',
    'StreamedTileCratesCommitted',
    'subscribe',
    'unsubscribe',
    'WayDeleted',
    'NodesPruned',
    'LaneletCommitted',
    'LaneletDeleted',
    'RegulatoryElementDeleted',
    'AreaCreated',
    'LiftSessionStarted',
    'LiftSessionEnded',
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
