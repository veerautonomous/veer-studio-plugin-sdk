"""Standalone event-bus surface — generated copy of core/events.py.

Loaded only when the real host package is absent (author CI).  Inside
the host, ``veer_plugin_sdk.events`` forwards to the real bus, so
handlers registered through this package see live events.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Base class for all domain and application events.

    Subclass for typed events::

        @dataclass(frozen=True, kw_only=True)
        class WayDeleted(DomainEvent):
            way_path: str
            way_uuid: str
    """
    timestamp: float = field(default_factory=time.time)
    source: str = "domain"     # "domain" | "application"

@dataclass(frozen=True, kw_only=True)
class ToolActivated(DomainEvent):
    """An interactive tool was activated."""
    tool_id: str
    plugin_id: str = ""
    source: str = "application"

@dataclass(frozen=True, kw_only=True)
class ToolDeactivated(DomainEvent):
    """A previously active interactive tool was deactivated."""
    tool_id: str
    source: str = "application"

@dataclass(frozen=True, kw_only=True)
class ToolModeChanged(DomainEvent):
    """An active tool switched to a different sub-mode."""
    tool_id: str
    mode: str
    source: str = "application"

@dataclass(frozen=True, kw_only=True)
class SublayersRewired(DomainEvent):
    """The root layer's ``subLayerPaths`` changed identity.

    Fired when a draft overlay is wired into the composition —
    replacing its original on first sandboxing (e.g. prim selection
    redirecting the edit target) or re-wiring an orphaned draft — and
    when draft cache paths are reverted to project-relative paths
    (save/discard/close).  Any UI that caches layer ids (layer-bar
    chips) is stale until it rebuilds."""
    detail: str

@dataclass(frozen=True, kw_only=True)
class StreamedTileCratesCommitted(DomainEvent):
    """A Save copied streamed tile crates into the project (#352).

    *source_paths* are the producer-side crates the Save read.  The project
    holds its own copies from here on, so a producer may release its cache
    copies.  Fired after the merge commits; a discarded or crashed session
    fires nothing, so the producer keeps its crates for a retry."""
    source_paths: tuple[str, ...]

_subscribers: list[Callable[[DomainEvent], None]] = []

def subscribe(callback: Callable[[DomainEvent], None]) -> None:
    """Register *callback* to receive all domain events.

    Filter by type inside the callback::

        def on_event(event: DomainEvent):
            if isinstance(event, WayDeleted):
                tree.refresh()
    """
    if callback not in _subscribers:
        _subscribers.append(callback)

def unsubscribe(callback: Callable[[DomainEvent], None]) -> None:
    """Remove a previously registered callback."""
    try:
        _subscribers.remove(callback)
    except ValueError:
        pass

@dataclass(frozen=True, kw_only=True)
class WayDeleted(DomainEvent):
    """A standalone way prim was deleted from the navigation layer."""
    way_path: str              # Sdf.Path string
    way_uuid: int | None       # hdmap:uuid — the integer Site counter

@dataclass(frozen=True, kw_only=True)
class NodesPruned(DomainEvent):
    """Orphaned nodes were pruned from the /Navigation/Points aggregate."""
    pruned_uuids: tuple[str, ...]
    remaining_count: int

@dataclass(frozen=True, kw_only=True)
class LaneletCommitted(DomainEvent):
    """A proposed lanelet was committed to the Roads container."""
    lanelet_path: str
    lanelet_uuid: int | None

@dataclass(frozen=True, kw_only=True)
class LaneletDeleted(DomainEvent):
    """A lanelet container was deleted (committed or proposed)."""
    lanelet_path: str
    lanelet_uuid: int | None

@dataclass(frozen=True, kw_only=True)
class RegulatoryElementDeleted(DomainEvent):
    """A regulatory element (stop line, traffic light, etc.) was deleted."""
    element_path: str
    element_type: str          # "stop_line", "traffic_light", "crosswalk", …

@dataclass(frozen=True, kw_only=True)
class AreaCreated(DomainEvent):
    """An interactive area region was authored (ring way + container).

    Emitted by :func:`create_area_region` on success so the UI can arm
    the navigation overlay's region draw immediately — without it the
    region stays invisible until something else (a save, a stage load)
    rescans for navigation content.
    """
    area_path: str              # Sdf.Path string of the Area_<id> container
    way_uuid: int               # hdmap:uuid of the ring way

@dataclass(frozen=True, kw_only=True)
class LiftSessionStarted(DomainEvent):
    """A lift-in-place editing session began on the given lanelet paths.

    While the session is active, the navigation overlay renders those
    lanelets as **not fixed** regardless of the NodeDB read (map #83,
    ticket #84 — the transient "committed, being adjusted" state is a
    session signal, never data).  Plugins cannot emit domain events (R8),
    so the nav library owns begin/end on behalf of the spline editor.
    """
    paths: tuple[str, ...]

@dataclass(frozen=True, kw_only=True)
class LiftSessionEnded(DomainEvent):
    """The active lift session ended (accept or cancel).

    Accept may have fixed moved nodes in the NodeDB, so consumers that
    cache fixed state should invalidate on this event.
    """
    paths: tuple[str, ...]
