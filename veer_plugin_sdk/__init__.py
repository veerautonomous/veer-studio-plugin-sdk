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

__all__ = [
    'BaseOverlayRenderer',
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
    'ToolResult',
    'ValidationReport',
    'EditorContext',
    'PanelContext',
    'StageManagerInterface',
    'StageMutationContext',
    'ToolContext',
    'ToolEvent',
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
]
