"""Event-bus surface — the host bus when present, a local copy when not."""

from __future__ import annotations

try:
    from core.events import (
        DomainEvent,
        ToolActivated,
        ToolDeactivated,
        ToolModeChanged,
        SublayersRewired,
        subscribe,
        unsubscribe,
    )
    from core.navigation._events import (
        WayDeleted,
        NodesPruned,
        LaneletCommitted,
        LaneletDeleted,
        RegulatoryElementDeleted,
        AreaCreated,
        LiftSessionStarted,
        LiftSessionEnded,
    )
except ModuleNotFoundError as _exc:
    if _exc.name != "core":
        raise
    from veer_plugin_sdk._events_fallback import (
        DomainEvent,
        ToolActivated,
        ToolDeactivated,
        ToolModeChanged,
        SublayersRewired,
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
    'DomainEvent',
    'ToolActivated',
    'ToolDeactivated',
    'ToolModeChanged',
    'SublayersRewired',
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
