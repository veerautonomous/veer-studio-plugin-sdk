# Atlas Studio — Port Interfaces
#
# All plugin port abstract base classes live here.  This module has zero
# dependencies beyond the Python standard library — no Qt, no USD, no
# other core/ modules.  Plugins depend on this file; core never depends
# on plugins.
#
# See ../engineering/architecture/PLUGIN_ARCHITECTURE.md §4 and §5 for the full specification.

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Optional, TYPE_CHECKING

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    # Annotation-only references.  ports must not depend on these modules
    # at runtime (contexts imports ports); the imports never evaluate.
    from pxr import Gf
    from core.assembly_schema import AssemblySchema
    from core.contexts import (
        EditorContext, PanelContext, StageManagerInterface,
        StageMutationContext, ToolContext, ToolEvent,
    )


# ---------------------------------------------------------------------------
# Plugin metadata — typed wrapper for plugInfo.json "vstudio" blocks
# ---------------------------------------------------------------------------


@dataclass
class LayerStrategy:
    """Write strategy for a plugin-owned layer.

    Declared in plugInfo.json under ``atlas.layers``.  Controls how the
    draft session handles writes to this layer.
    """

    strategy: str = "draft_overlay"
    """One of ``"draft_overlay"``, ``"create_new"``, or ``"read_only"``.

    - ``draft_overlay`` — writes go to a temp draft overlay; Save merges
      into the original file.
    - ``create_new`` — the layer is created in the temp dir; Save copies
      it to the project directory.
    - ``read_only`` — the layer is opened read-only from the project dir;
      writes raise an error.
    """


def _parse_tool_workspaces(name: str, atlas: dict) -> dict:
    """Parse ``vstudio.toolWorkspaces`` — tool id → predefined workspace id.

    Declares where a registered tool lands in the Tools menu.  Unknown
    workspace ids are tolerated here and fall back at the consumer.
    """
    raw = atlas.get("toolWorkspaces")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _log.warning(
            "Plugin '%s': vstudio.toolWorkspaces must be an object — ignored",
            name)
        return {}
    return {str(tool_id): str(ws_id) for tool_id, ws_id in raw.items()}


def _parse_workspace_buttons(name: str, atlas: dict) -> dict:
    """Parse ``vstudio.workspace`` — workspace id → validated FAB entry dicts.

    A command entry's ``commandId`` must be namespaced under the plugin
    name (``<name>.<command>``) so a contribution can never collide with
    host or other-plugin command ids; spacers are exempt.  Invalid
    entries are dropped with a warning — never fatal to the load.
    """
    raw = atlas.get("workspace")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _log.warning(
            "Plugin '%s': vstudio.workspace must be an object — ignored", name)
        return {}
    prefix = name + "."
    parsed: dict = {}
    for ws_id, block in raw.items():
        buttons = block.get("buttons") if isinstance(block, dict) else None
        if not isinstance(buttons, list):
            _log.warning(
                "Plugin '%s': vstudio.workspace['%s'] needs a 'buttons' "
                "list — ignored", name, ws_id)
            continue
        accepted = []
        for entry in buttons:
            if not isinstance(entry, dict):
                _log.warning(
                    "Plugin '%s': FAB entry is not an object — dropped",
                    name)
                continue
            if "spacerId" in entry:
                accepted.append(dict(entry))
                continue
            cid = str(entry.get("commandId", ""))
            if not cid:
                _log.warning(
                    "Plugin '%s': FAB entry without commandId — dropped",
                    name)
                continue
            if not cid.startswith(prefix):
                _log.warning(
                    "Plugin '%s': FAB commandId '%s' is not namespaced "
                    "under the plugin name — dropped", name, cid)
                continue
            accepted.append(dict(entry))
        if accepted:
            parsed[str(ws_id)] = accepted
    return parsed


_PERMISSION_SECTIONS = ("write", "read")


def parse_permission_block(name: str, raw) -> tuple[dict, dict]:
    """Validate ``vstudio.permissions``; return ``(scopes, reasons)`` (#349).

    ``scopes`` is ``{"write": [...], "read": [...]}`` — the lists the registry
    enforces.  ``reasons`` is ``{"write": {scope: reason}, "read": {...}}`` —
    the declared scopes with the one-line reason the install confirm shows.
    Every declared scope needs a reason; an absent block keeps the read-only
    default.  Raises ``ValueError`` for any other shape (refused at discovery).
    """
    if raw is None:
        return {"write": [], "read": ["*"]}, {"write": {}, "read": {}}
    if not isinstance(raw, dict):
        raise ValueError(_permission_shape_error(name, "permissions"))
    scopes = {"write": [], "read": ["*"]}
    reasons = {"write": {}, "read": {}}
    for section in _PERMISSION_SECTIONS:
        if section not in raw:
            continue
        declared = raw[section]
        if not isinstance(declared, dict):
            raise ValueError(_permission_shape_error(name, f"permissions.{section}"))
        for scope, reason in declared.items():
            _check_permission_reason(name, section, scope, reason)
        scopes[section] = list(declared)
        reasons[section] = {scope: reason.strip() for scope, reason in declared.items()}
    return scopes, reasons


def _permission_shape_error(name: str, where: str) -> str:
    return (f"plugin '{name}': {where} must be an object mapping each scope to "
            f"its one-line reason, e.g. {{\"Assets\": \"Writes the placed prims.\"}}")


def _check_permission_reason(name: str, section: str, scope, reason) -> None:
    """Refuse a scope with no reason, or a reason that is not one line."""
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError(f"plugin '{name}': permissions.{section} has an empty scope name")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(
            f"plugin '{name}': permissions.{section}['{scope}'] has no reason — "
            f"every permission needs a one-line reason")
    if "\n" in reason.strip():
        raise ValueError(
            f"plugin '{name}': permissions.{section}['{scope}'] reason must be one line")


@dataclass
class PluginMeta:
    """Structured metadata parsed from a plugInfo.json ``atlas`` block.

    Built by PluginRegistry during discovery — plugin authors never
    construct this directly.  Provides a typed API instead of passing
    raw dicts through the registry.
    """

    name: str = ""
    """Plugin name from ``PlugPlugin.Name`` (the directory name)."""

    version: str = ""
    """Semantic version string, e.g. '0.1.0'."""

    sdk_version: str = ""
    """Atlas SDK major version this plugin was built against, e.g. '1'."""

    display_name: str = ""
    """Human-readable name shown in the UI."""

    description: str = ""
    """One-paragraph description of what this plugin does."""

    author: str = ""
    """Author or team name."""

    min_core_version: Optional[str] = None
    """Minimum Atlas Studio version required, or None if no constraint."""

    imports: list[str] = field(default_factory=list)
    """File extensions this plugin can import, e.g. ['.pcd', '.las']."""

    tools: list[str] = field(default_factory=list)
    """Fully-qualified tool class paths, e.g. ['my_toolpack.tool_a']."""

    panels: list[str] = field(default_factory=list)
    """Fully-qualified panel class paths."""

    layers: dict[str, LayerStrategy] = field(default_factory=dict)
    """Layer names → write strategy, e.g. ``{"Reality/Meshes/GroundSurface_a1b2c3.usda": LayerStrategy(strategy="draft_overlay")}``.

    Accepts both old list format (converted to draft_overlay defaults) and
    new dict format at parse time via ``from_plug_info()``.
    """

    dependencies: dict = field(default_factory=dict)
    """Python dependencies dict, e.g. {'python': ['numpy>=1.24']}."""

    permissions: dict = field(default_factory=dict)
    """Layer-category permissions declared in ``plugInfo.json``.

    ``write``: list of category tokens this plugin may write to
    (e.g. ``["Reference", "Navigation"]``).  An empty list means the
    plugin is read-only — any write attempt raises ``PermissionError``.

    ``read``: list of category tokens this plugin may read from.
    Defaults to ``["*"]`` (all composed stage data is visible).
    """

    enabled: bool = True
    """Manifest on/off switch (``plugInfo.json`` ``vstudio.enabled``).  When False
    the registry records the plugin in ``PluginRegistry.disabled`` and does NOT
    load it — keeping reference/demo plugins (e.g. hello_toolpack) out of user
    workspaces without removing them from the repo.  Defaults to True."""

    tool_workspaces: dict = field(default_factory=dict)
    """Tool id → predefined workspace id (``vstudio.toolWorkspaces``).

    Declares where a registered tool lands in the Tools menu — e.g.
    ``{"studio_lidar_slam.slam_tool": "reality_capture"}``.  Consulted by
    the Tools-menu builder before the host-side mapping; a declaration
    naming an unknown workspace id falls back to ``"Utility"``.
    """

    workspace_buttons: dict = field(default_factory=dict)
    """Workspace id → list of FAB entry dicts (``vstudio.workspace``).

    Each entry is a button — ``commandId`` (namespaced under the plugin
    name) plus optional ``displayName`` / ``description`` / ``shortcut`` /
    ``icon`` / ``toolId`` / ``mode`` / ``replacesStub`` — or a spacer
    (``spacerId``).  ``app.workspace.apply_plugin_contributions`` merges
    these into the matching workspace's curated ``fab_commands`` at
    startup; ``replacesStub`` retires a roadmap stub the plugin fulfils.
    """

    module_path: Optional[str] = None
    """Resolved Python module import path, set by the registry after discovery."""

    @classmethod
    def from_plug_info(cls, name: str, atlas: dict) -> "PluginMeta":
        """Construct a PluginMeta from a PlugPlugin name and its ``atlas`` info dict.

        Args:
            name: The ``PlugPlugin.Name`` value.
            atlas: The ``plugin.info['vstudio']`` dictionary.

        Returns:
            A fully-populated PluginMeta instance.
        """
        layers_raw = atlas.get("layers", [])
        if isinstance(layers_raw, list):
            # Old format: ["layer_a.usda", "layer_b.usda"]
            # Default all to draft_overlay
            layers = {path: LayerStrategy(strategy="draft_overlay")
                      for path in layers_raw}
        elif isinstance(layers_raw, dict):
            layers = {path: LayerStrategy(**opts) for path, opts in layers_raw.items()}
        else:
            layers = {}

        # Parse permissions block (WS-1 F5).  The reasons are validated here
        # and shown by the install confirm (#349), not kept on PluginMeta.
        permissions, _ = parse_permission_block(name, atlas.get("permissions"))

        return cls(
            name=name,
            version=atlas.get("version", ""),
            sdk_version=atlas.get("sdkVersion", ""),
            display_name=atlas.get("displayName", ""),
            description=atlas.get("description", ""),
            author=atlas.get("author", ""),
            min_core_version=atlas.get("minCoreVersion"),
            imports=atlas.get("imports", []),
            tools=atlas.get("tools", []),
            panels=atlas.get("panels", []),
            layers=layers,
            dependencies=atlas.get("dependencies", {}),
            permissions=permissions,
            enabled=bool(atlas.get("enabled", True)),
            tool_workspaces=_parse_tool_workspaces(name, atlas),
            workspace_buttons=_parse_workspace_buttons(name, atlas),
        )


# ---------------------------------------------------------------------------
# Cloud unit vocabulary — the point-cloud domain's role names, the unit
# type, and the attribute reader they share
# ---------------------------------------------------------------------------

# Static definitions, not a lazy re-export: they have to ship inside the
# SDK's standalone ``_ports.py`` copy, which gets no ``__getattr__``
# dispatcher.  ``core.clouds._schema`` re-imports them, so
# ``from core.clouds import GEOMETRIC_ROLES`` keeps working.

ROLE_PRECISE = "precise"
ROLE_APPEARANCE = "appearance"
ROLE_DERIVED = "derived"
CLOUD_ROLES = (ROLE_PRECISE, ROLE_APPEARANCE, ROLE_DERIVED)
# The roles that may feed a geometric derivation (mesh generation, snapping).
GEOMETRIC_ROLES = (ROLE_PRECISE, ROLE_DERIVED)

ATTR_DISPLAY_NAME = "atlas:displayName"


def attr_value(prim, name):
    """The authored value of *name* on *prim*, or None when absent/invalid."""
    if prim is None or not prim.IsValid():
        return None
    attr = prim.GetAttribute(name)
    if not attr or not attr.IsValid():
        return None
    return attr.Get()


@dataclass(frozen=True)
class CloudUnit:
    """One cloud unit: a frame prim plus its ``Points`` leaf.

    ``role`` is the resolved role (the tile-prefix fallback already applied),
    ``is_tile`` is ``atlas:tileStatus``, and ``is_current`` is the lineage
    flag with "absent means current" applied.

    Lives here rather than ``core.clouds`` for the same reason as the role
    names above: ``ctx.cloud_units()``'s result type has to ship in the
    SDK's standalone ``_ports.py`` copy, which gets no ``__getattr__``
    dispatcher (veer-studio-plugin-sdk#6).  ``core.clouds._units`` re-exports
    it, so ``from core.clouds import CloudUnit`` keeps working.
    """

    frame: object
    points: object
    role: str
    is_tile: bool
    is_current: bool

    @property
    def name(self) -> str:
        """The frame's prim name."""
        return self.frame.GetName()

    @property
    def display_name(self) -> str:
        """The label a person reads: ``atlas:displayName``, else the frame name."""
        return attr_value(self.frame, ATTR_DISPLAY_NAME) or self.name

    @property
    def frame_path(self) -> str:
        """The frame's absolute prim path."""
        return str(self.frame.GetPath())

    @property
    def points_path(self) -> str:
        """The leaf's absolute prim path."""
        return str(self.points.GetPath())

    @property
    def is_geometric(self) -> bool:
        """Whether the unit may feed a geometric derivation."""
        return self.role in GEOMETRIC_ROLES


# ---------------------------------------------------------------------------
# ToolResult enum
# ---------------------------------------------------------------------------


class ToolResult(Enum):
    """Return value from tool execution.

    FINISHED  — tool completed successfully; the framework auto-deactivates
                the tool (accept-and-exit is the default terminal)
    CANCELLED — user cancelled (or pre-condition not met)
    FAILED    — tool encountered an error
    RUNNING   — modal/interactive tool, keep receiving events

    FINISHED / CANCELLED / FAILED are terminal: on any of them the
    framework routes through the active-tool-finished handler, which
    deactivates the tool.  RUNNING keeps the tool active.
    """

    FINISHED = "finished"
    CANCELLED = "cancelled"
    FAILED = "failed"
    RUNNING = "running"


# ---------------------------------------------------------------------------
# Creation session — ratified creation lifecycle (UX_SPEC §1)
# ---------------------------------------------------------------------------


class CreationVerb(Enum):
    """One verb of the ratified creation lifecycle (UX_SPEC §1).

    FINISH  — accept the ghost geometry and exit the tool (Enter).
              One framework undo step per accept.
    DISCARD — discard the ghost geometry AND exit the tool (Esc) —
              the symmetric terminal with FINISH.
    REPEAT  — accept the ghost geometry and continue the creation
              session (Spacebar) — the ONLY sticky repeat.
    """

    FINISH = "finish"
    DISCARD = "discard"
    REPEAT = "repeat"


@dataclass
class CreationSession:
    """Declares the tool's current mode a creation session.

    Returned by ``IToolProvider.get_creation_session()`` (or the mode's
    ``ModeDef.creation_session``).  A non-None value turns on the
    framework's creation-session plumbing:

    - ``[Spacebar]`` binds to REPEAT (auto-repeat suppressed — one
      commit per press)
    - Right-click opens a tool context menu seeded from ``verbs`` and
      ``extra_entries`` (never bare finish)
    - ``[Esc]`` discards the ghost geometry and exits the tool

    Tools that do not declare a session keep their existing behavior —
    the framework branches only activate when a session is present.
    """

    label: str = ""
    """Short creation-session label, e.g. "Draw lanelet" (menu title/hints)."""

    verbs: tuple = (CreationVerb.FINISH, CreationVerb.DISCARD,
                    CreationVerb.REPEAT)
    """Which verbs the framework should wire.  Defaults to all three."""

    extra_entries: list = field(default_factory=list)
    """Extra tool context menu entries: ``[(label, tool_method_name)]``.

    Each entry invokes ``getattr(tool, method_name)(ctx)`` when chosen.
    """


# ---------------------------------------------------------------------------
# Overlay layer system — priority-ordered render stack
# ---------------------------------------------------------------------------


class OverlayLayer(IntEnum):
    """Priority-ordered overlay layers.  Lower = drawn first (behind)."""
    BACKGROUND = 0      # Grid, OSM reference, ground plane
    CONTENT = 100       # Tool-specific (spline CPs, gizmo, preview, bboxes)
    FOREGROUND = 200    # HUD, scale bar, nav cube, flash highlights
    OVERLAY_UI = 300    # Topmost: Qt overlaid widgets (placement label, etc.)


class OverlayRenderer(ABC):
    """A single overlay renderer registered on the overlay stack.

    Subclass this for each independent overlay concern.  Register
    instances with ``OverlayManager.register()`` via
    ``ctx.register_overlay(renderer)``.
    """

    @property
    @abstractmethod
    def renderer_id(self) -> str:
        """Unique ID for this renderer (e.g. 'grid', 'tool.spline_editor', 'hud')."""

    @abstractmethod
    def render(self, frustum, buf_w: int, buf_h: int) -> None:
        """Draw overlay content.

        Called from ``paintGL`` after Hydra rendering.  The OpenGL
        context is in 3D projection mode; the renderer is responsible
        for setting up any orthographic projection it needs.

        Args:
            frustum: ``Gf.Frustum`` for the current camera.
            buf_w: Viewport width in pixels.
            buf_h: Viewport height in pixels.
        """

    @property
    def layer(self) -> OverlayLayer:
        """Which layer this renderer draws on.  Default: CONTENT."""
        return OverlayLayer.CONTENT

    @property
    def enabled(self) -> bool:
        """Can be toggled off without unregistering."""
        return getattr(self, '_enabled', True)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value


def matrix_to_list(m) -> list:
    """Flatten a Gf.Matrix4d to 16 floats for glLoadMatrixd."""
    vals = []
    for row in range(4):
        rr = m.GetRow(row)
        vals.extend([rr[0], rr[1], rr[2], rr[3]])
    return vals


class BaseOverlayRenderer(OverlayRenderer):
    """Overlay base with automatic GL matrix setup and draw helpers.

    Subclasses override ``_draw(frustum, buf_w, buf_h)`` instead of
    ``render()``.  The base class sets ``GL_PROJECTION`` and
    ``GL_MODELVIEW`` from the frustum before calling ``_draw()`` and
    restores them afterward.  Hydra/Storm leaves GL matrices in an
    arbitrary state — this base class isolates that concern.

    Built-in helpers (available in ``_draw()``):
      - ``_px_to_world_m(near_point, px)`` — screen pixels → world metres
      - ``_draw_circle_world(center, radius_m, color, segments, filled)``
      - ``_draw_line_world(a, b, color, width)``
      - ``_draw_polyline_world(points, color, width, closed)``
      - ``_draw_triangle_fan_world(points, color, alpha)``

    Existing overlays that override ``render()`` directly are unaffected —
    this class is purely additive.
    """

    # Z offset for preview geometry above terrain (metres).
    Z_OFFSET: float = 3.0

    # ── Subclass overrides this ──

    def _draw(self, frustum, buf_w: int, buf_h: int) -> None:
        """Draw overlay content.  GL_PROJECTION and GL_MODELVIEW are already
        set from *frustum* when this is called.  Base implementation is a
        no-op — subclasses override to add drawing logic."""

    # ── Framework calls this ──

    def render(self, frustum, buf_w: int, buf_h: int) -> None:
        """Set up GL matrices, dispatch to _draw(), restore matrices.

        Caches the frustum and buffer size on ``self._frustum`` /
        ``self._buf_w`` / ``self._buf_h`` so helpers can access them.
        """
        try:
            import OpenGL.GL as GL
        except ImportError:
            return

        self._frustum = frustum
        self._buf_w = buf_w
        self._buf_h = buf_h

        view = frustum.ComputeViewMatrix()
        proj = frustum.ComputeProjectionMatrix()

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadMatrixd(matrix_to_list(proj))

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPushMatrix()
        GL.glLoadMatrixd(matrix_to_list(view))

        try:
            self._draw(frustum, buf_w, buf_h)
        finally:
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glPopMatrix()
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glPopMatrix()

    # ── Pixel ↔ world helpers ──

    def _px_per_m(self, near_point) -> float:
        """Screen pixels per world metre at *near_point*, from the cached frustum.

        Isotropic: the perspective scale at the point's depth, not the screen
        length of one world axis.  Measuring a single axis collapses whenever
        the camera looks down that axis, and sizes pixel-based geometry by
        the reciprocal of nearly zero.
        """
        from pxr import Gf

        f = getattr(self, '_frustum', None)
        bw = getattr(self, '_buf_w', 800)
        if f is None:
            return 100.0  # fallback: matches the px * 0.01 world-size fallback
        proj = f.ComputeProjectionMatrix()
        clip = Gf.Vec4d(near_point[0], near_point[1], near_point[2], 1.0) * (
            f.ComputeViewMatrix() * proj)
        if abs(clip[3]) < 1e-10:
            return 100.0
        return abs(proj[0][0]) * 0.5 * bw / abs(clip[3])

    def _px_to_world_m(self, near_point, px: float) -> float:
        """Convert *px* screen pixels to world-space metres near *near_point*.

        Uses the frustum cached during ``render()``.  Returns metres — callers
        multiply by the desired pixel radius to get a zoom-independent world
        size.
        """
        px_per_m = self._px_per_m(near_point)
        if px_per_m < 1e-6:
            return px * 0.01
        return px / px_per_m

    # ── Drawing helpers ──

    @staticmethod
    def _draw_circle_world(center, radius_m: float,
                           color: tuple, segments: int = 12,
                           filled: bool = True) -> None:
        """Draw a circle at a world-space position.

        *radius_m* is in world metres (use ``_px_to_world_m()`` for
        pixel-based sizing).  Uses ``GL_TRIANGLE_FAN`` when filled,
        ``GL_LINE_LOOP`` otherwise.
        """
        import math
        import OpenGL.GL as GL

        GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_CURRENT_BIT)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glColor3f(*color)

        mode = GL.GL_TRIANGLE_FAN if filled else GL.GL_LINE_LOOP
        GL.glBegin(mode)
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            GL.glVertex3f(
                center[0] + radius_m * math.cos(angle),
                center[1] + radius_m * math.sin(angle),
                center[2])
        GL.glEnd()
        GL.glPopAttrib()

    @staticmethod
    def _draw_line_world(a, b, color: tuple, width: float = 1.0) -> None:
        """Draw a single line segment between two world positions."""
        import OpenGL.GL as GL

        GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_LINE_BIT | GL.GL_CURRENT_BIT)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glLineWidth(width)
        GL.glColor3f(*color)
        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(a[0], a[1], a[2])
        GL.glVertex3f(b[0], b[1], b[2])
        GL.glEnd()
        GL.glPopAttrib()

    @staticmethod
    def _draw_polyline_world(points, color: tuple, width: float = 1.0,
                             closed: bool = False) -> None:
        """Draw a connected line strip through world positions."""
        import OpenGL.GL as GL

        GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_LINE_BIT | GL.GL_CURRENT_BIT)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glLineWidth(width)
        GL.glColor3f(*color)
        mode = GL.GL_LINE_LOOP if closed else GL.GL_LINE_STRIP
        GL.glBegin(mode)
        for p in points:
            GL.glVertex3f(p[0], p[1], p[2])
        GL.glEnd()
        GL.glPopAttrib()

    @staticmethod
    def _draw_triangle_fan_world(points, color: tuple,
                                 alpha: float = 0.3) -> None:
        """Draw a filled polygon from world positions (used for area preview)."""
        import OpenGL.GL as GL

        GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_CURRENT_BIT)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glColor4f(color[0], color[1], color[2], alpha)
        GL.glBegin(GL.GL_TRIANGLE_FAN)
        for p in points:
            GL.glVertex3f(p[0], p[1], p[2])
        GL.glEnd()
        GL.glPopAttrib()


# ---------------------------------------------------------------------------
# Gizmo port — the transform suite's manipulation-handle surface
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GizmoSpec:
    """Declarative description of the handles the gizmo surface draws.

    Axes spell ``"x"``, ``"y"``, ``"z"`` — the *spec frame's* axes.  By
    default that frame is the stage (global); a tool that owns a transform
    delta passes an ``orientation`` so the handles point along the
    selection's rotated axes instead.  There is deliberately no
    per-prim Local/Global toggle — "local" stays ill-defined for a
    multi-prim selection, so the tool's single rotation is the one frame
    (#269).  A family with no axes is **omitted, never dimmed**: a dimmed
    handle is a dead button that still invites the click.

    Args:
        center: Pivot in stage-native world space (``Gf.Vec3d``).
        translate_axes: Axes to draw translate arrows for, e.g. ``("x", "y")``.
        rotate_axes: Axes to rotate **around** — ``("z",)`` draws the
            XY-plane arc.  Empty omits the family.
        scale_axes: Axes to draw per-axis scale handles for.  Non-empty also
            draws the centre handle, which writes one factor into every
            listed axis (so a 2D profile's pinned Z never moves).
        bbox: Optional world-space ``(lo, hi)`` extent drawn as a dashed
            wireframe behind the handles — the selection group's bounds.
        orientation: Optional rotation-only ``Gf.Matrix4d`` mapping the
            spec frame to world — its rows are the world directions of
            ``"x"`` / ``"y"`` / ``"z"``.  ``None`` (default) = stage-aligned.
        bbox_matrix: Optional world transform applied to ``bbox``'s corners
            when drawing, so a moving/rotating selection's wireframe moves
            with it.  ``None`` draws the extent axis-aligned.
    """

    center: "Gf.Vec3d"
    translate_axes: tuple = ()
    rotate_axes: tuple = ()
    scale_axes: tuple = ()
    bbox: Optional[tuple] = None
    orientation: Optional["Gf.Matrix4d"] = None
    bbox_matrix: Optional["Gf.Matrix4d"] = None


@dataclass(frozen=True)
class GizmoHit:
    """A handle hit, returned by :meth:`GizmoManagerInterface.hit_test`.

    Args:
        handle_id: ``"{family}_{axis}"`` — ``"translate_x"``, ``"rotate_z"``
            (rotate *around* Z), ``"scale_y"`` — or ``"scale_uniform"`` for
            the centre handle.
        position: Press position in logical widget pixels: the origin
            :meth:`GizmoManagerInterface.update_drag` measures from.
    """

    handle_id: str
    position: tuple


@dataclass(frozen=True)
class GizmoDelta:
    """What one drag did, in stage-native space.

    ``kind`` names which field carries the value:

    ==========  ==================================================
    kind        value
    ==========  ==================================================
    translate   ``translation`` — world metres, along the handle's axis
    rotate      ``rotation_axis`` (unit) + ``angle_deg``
    scale       ``scale_factor``; ``handle_id`` says which axis
    ==========  ==================================================

    The delta is raw — snapping, preview composition and every USD write
    belong to the tool that asked for it.
    """

    kind: str
    handle_id: str
    translation: Optional[Any] = None
    rotation_axis: Optional[Any] = None
    angle_deg: float = 0.0
    scale_factor: float = 1.0


class GizmoManagerInterface(ABC):
    """The gizmo surface a transform tool drives — one instance per viewport.

    The surface owns handle geometry, screen projection and drag math; a
    tool declares what to show and applies the deltas it gets back, so no
    tool re-implements any of it.  Tools reach the shared instance through
    ``ToolContext.gizmo_manager``.
    """

    @abstractmethod
    def show(self, spec: GizmoSpec) -> None:
        """Draw *spec*'s handles.  Re-callable mid-drag to move the pivot.

        Also the visibility door: if the handles would fall outside the
        viewport, the surface pans the camera so they stay on screen.
        """

    @abstractmethod
    def hide(self) -> None:
        """Remove the handles and abandon any in-flight drag."""

    @abstractmethod
    def hit_test(self, screen_x: float, screen_y: float) -> Optional[GizmoHit]:
        """Return the nearest handle within its family's hit radius, else None.

        The returned hit is retained as the hovered handle — the render
        brightens it — until the next ``hit_test`` or a ``hide``.  Positions
        are logical widget pixels; the device-pixel conversion happens here.
        """

    @abstractmethod
    def begin_drag(self, hit: GizmoHit) -> None:
        """Start dragging *hit*: the origin its deltas are measured from."""

    @abstractmethod
    def update_drag(self, screen_x: float,
                    screen_y: float) -> Optional[GizmoDelta]:
        """Delta from the drag origin to this position.

        Returns None when not dragging, or before the first frame has
        rendered (there are no projection matrices to work from yet).
        """

    @abstractmethod
    def end_drag(self) -> None:
        """End the drag.  The handles stay shown, hit-testable, hoverable."""


# ---------------------------------------------------------------------------
# Background jobs (wayfinder #322)
# ---------------------------------------------------------------------------


@dataclass
class JobSpec:
    """One run of a long-running child-process pipeline.

    The driver plugin (or host caller) fills in the callbacks it cares
    about; every callback is invoked on the GUI thread from the service's
    Qt-signal handlers — never from the child process.

    Child stdout is a JSON-lines protocol (one object per line, flushed):
    ``{"type":"progress","text":…,"value":…,"max":…}``,
    ``{"type":"chunk", …payload}``,
    ``{"type":"log","message":…}``,
    ``{"type":"error","message":…}``.  stderr is free-form log text
    (tail preserved for failure reports).  ``on_chunks`` receives batches
    coalesced at ~1 Hz — the consumer-side throttle (map #318 Q11), so a
    fast producer cannot flood the GUI.
    """

    argv: list[str]
    """Program + arguments; ``argv[0]`` must be an executable path/name."""

    cwd: str = ""
    """Working directory for the child; empty inherits the app's."""

    name: str = ""
    """Display name shown in the status-bar job progress."""

    plugin_id: str = ""
    """The driving plugin's id — the pin this job takes names it as the only
    ``plugin_id`` ``ToolContext.stage_pin_exempt()`` lets through while the
    job runs (stage_pin, sdk#1).  Empty for host-owned jobs."""

    env: Optional[dict] = None
    """Extra environment variables layered over the inherited env."""

    on_progress: Optional[Callable[[str, int, int], None]] = None
    """``(text, value, max)`` — latest progress, delivered at the ~1 Hz tick."""

    on_chunks: Optional[Callable[[list], None]] = None
    """``(batch)`` — coalesced ``chunk`` messages, ~1 Hz (empty batch never sent)."""

    on_log: Optional[Callable[[str], None]] = None
    """``(line)`` — one stderr line (or a stdout ``log`` message)."""

    on_finished: Optional[Callable[[int, str, bool], None]] = None
    """``(exit_code, stderr_tail, cancelled)`` — exactly once per run."""

    on_error: Optional[Callable[[str], None]] = None
    """Terminal failure (spawn error, stall, nonzero exit) — message for the user."""

    undo_revert: Optional[Callable[[], None]] = None
    """Mid-flight Undo door: cancel, then restore the stage to the
    pre-job state (map #318 Q10).  Called after the child is dead."""

    undo_commit: Optional[Callable[[], None]] = None
    """On clean completion: fold the whole run into ONE undo step."""

    chunk_interval_ms: int = 1000
    """Coalescing tick; default 1 Hz (owner ruling, map #318 Q11)."""

    stall_ms: Optional[int] = None
    """Silence limit for this run; None uses the service default (60 s).
    A stage whose first output comes after a long silent setup raises it."""


class JobServiceInterface(ABC):
    """Host-owned background-job execution slot (wayfinder #322).

    Plugins never spawn pipelines themselves — they ask the host
    (``ToolContext.jobs``), which owns progress UI, cancellation, the
    stage pin, and process-tree lifecycle.  Same shape as Blender's
    WM_jobs: add-ons cannot create one; only the host runs jobs.
    """

    @abstractmethod
    def start(self, spec: JobSpec) -> None:
        """Start *spec*.  Pins the stage for the run's duration.

        Raises ``RuntimeError`` if a job is already running or *spec*
        cannot start; the stage is unpinned again on every failure path.
        """

    @abstractmethod
    def cancel(self) -> None:
        """Cancel the running job: stdin ``cancel`` → grace → tree kill.

        No-op when idle or already cancelling.
        """

    @abstractmethod
    def cancel_and_revert(self) -> None:
        """Cancel, then run the spec's ``undo_revert`` once the child dies.

        The mid-flight Ctrl+Z contract (map #318 Q10).
        """

    @abstractmethod
    def is_running(self) -> bool:
        """True from ``start`` until the child reaches a terminal state
        (including while cancelling)."""

    @abstractmethod
    def is_canceling(self) -> bool:
        """True while a cancellation ladder is in flight."""

    @abstractmethod
    def active_spec(self) -> Optional[JobSpec]:
        """The running spec, or None when idle."""


# ---------------------------------------------------------------------------
# Compiler pipeline supporting types
# ---------------------------------------------------------------------------


class Severity(Enum):
    """Validation diagnostic severity.

    ERROR   — must be fixed; blocks export
    WARNING — should be fixed; does not block export
    INFO    — informational only
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    """One validation finding linked to a specific prim.

    The ``code`` field enables filtering — a user can ignore all ``W001``
    diagnostics but not ``E001``.  ``fix_suggestion`` enables one-click-fix
    workflows in a future iteration.
    """

    code: str
    """Error code, e.g. ``'E001'``."""

    severity: Severity
    """ERROR, WARNING, or INFO."""

    message: str
    """Human-readable description of the issue."""

    prim_path: str = ""
    """Sdf.Path string of the offending prim, or empty if stage-scoped."""

    fix_suggestion: str = ""
    """Optional — how to fix the issue."""


@dataclass
class ValidationReport:
    """Result of running a validation pass.

    The ``is_valid`` flag is True when there are zero ERROR-severity
    diagnostics (warnings and info do not invalidate).
    """

    diagnostics: list[Diagnostic] = field(default_factory=list)
    """All diagnostics produced by this validation pass."""

    is_valid: bool = True
    """True if no ERROR-severity diagnostics are present."""

    validator_name: str = ""
    """Display name of the validator that produced this report — set by
    ``run_all_validators`` from ``IValidator.display_name()`` so the
    results table shows a human name instead of the module id."""

    @property
    def errors(self) -> list[Diagnostic]:
        """Diagnostics with ERROR severity."""
        return [d for d in self.diagnostics if d.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        """Diagnostics with WARNING severity."""
        return [d for d in self.diagnostics if d.severity == Severity.WARNING]

    @property
    def infos(self) -> list[Diagnostic]:
        """Diagnostics with INFO severity."""
        return [d for d in self.diagnostics if d.severity == Severity.INFO]


@dataclass
class ExportReport:
    """Result of running an export pass.

    Carries the output path, format name, any diagnostics (e.g. warnings
    about data that couldn't be represented in the target format), and
    optional statistics.
    """

    success: bool = False
    """True if the export completed without errors."""

    output_path: str = ""
    """Path to the exported file."""

    format_name: str = ""
    """Human-readable format name, e.g. ``'Lanelet2 OSM'``."""

    diagnostics: list[Diagnostic] = field(default_factory=list)
    """Diagnostics from the export pass (warnings about data loss, etc.)."""

    stats: dict = field(default_factory=dict)
    """Arbitrary statistics, e.g. ``{'lanelets': 145, 'stop_lines': 38}``."""


# ---------------------------------------------------------------------------
# Port ABCs
# ---------------------------------------------------------------------------


class IToolProvider(ABC):
    """A tool that registers in the toolbar.

    Inspired by Blender's operator system: typed registration, declarative
    poll() for availability, and optional modal event loop.
    """

    @abstractmethod
    def tool_id(self) -> str:
        """Unique identifier, e.g. 'slam_toolpack.ingest'."""

    @abstractmethod
    def display_name(self) -> str:
        """Label shown on toolbar button / menu item."""

    def icon_path(self) -> Optional[str]:
        """Optional icon file path.  Return None for text-only button."""
        return None

    @abstractmethod
    def execute(self, context: "ToolContext") -> ToolResult:
        """Execute the tool.  Return FINISHED, CANCELLED, or FAILED."""

    @classmethod
    def poll(cls, context: "ToolContext") -> bool:
        """Return False to gray out / disable this tool in the current context.

        This is the Blender poll() pattern — declarative availability
        without the tool needing to handle 'can't run here' internally.
        Default: True (always available).
        """
        return True

    @classmethod
    def poll_reason(cls, context: "ToolContext") -> Optional[str]:
        """Why ``poll`` currently returns False — a user-facing sentence.

        The reason-aware half of the poll contract (#389): the host shows
        this on the disabled FAB button's tooltip and in the status bar
        when the user invokes the tool anyway, instead of a generic
        "not available".  Return None (the default) to keep the generic
        message.  Implementations should be cheap — the host calls it on
        every selection change alongside ``poll``.
        """
        return None

    # -- Modal / interactive tool support (optional overrides) --

    def activate(self, context: "ToolContext") -> None:
        """Called when this tool becomes the active interactive tool."""

    def process_event(
        self, context: "ToolContext", event: "ToolEvent"
    ) -> ToolResult:
        """Handle one input event while tool is active (modal mode).

        Return RUNNING to keep receiving events; FINISHED, CANCELLED, or
        FAILED are terminal — the framework auto-deactivates the tool on
        any of them (accept-and-exit is the default).  Default:
        immediately FINISHED (non-interactive tool).
        """
        return ToolResult.FINISHED

    def deactivate(self, context: "ToolContext") -> None:
        """Called when this tool is deactivated."""

    def activate_with_mode(self, context: "ToolContext", mode: str) -> None:
        """Activate in a specific initial mode.

        Called by the FAB column when a FAB action declares a *mode*.
        Default implementation sets ``_initial_mode`` and delegates to
        :meth:`activate`.  Tools with custom activation logic override this.
        """
        self._initial_mode = mode
        self.activate(context)

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this tool.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value

    # -- Tool shelf / UI metadata (optional overrides, Phase 3) --

    def tool_description(self) -> str:
        """Longer description for tooltips.  Default: display_name()."""
        return self.display_name()

    def tool_shortcut(self) -> str:
        """Suggested default keyboard shortcut.  Return '' for none."""
        return ""

    def get_options_widget(self, parent):  # parent: QWidget → returns QWidget|None
        """Return a QWidget to display in the active tool options bar.

        Return None for tools with no configurable options UI.
        The widget is shown in the ActiveToolBar while this tool is active.
        """
        return None

    def get_available_modes(self) -> list[tuple[str, str]]:
        """Return [(mode_id, display_name)] for tools with sub-modes.

        E.g., Spline Editor returns [("select", "Select"),
        ("split", "Split"), ("merge", "Merge"), ...].
        """
        return []

    def get_current_mode(self) -> str:
        """Return the current mode identifier.  Default: 'default'."""
        return "default"

    def on_mode_enter(self, mode_id: str) -> None:
        """Called when entering a sub-mode.  Override in subclass."""

    def on_mode_exit(self, mode_id: str) -> None:
        """Called when leaving a sub-mode.  Override in subclass."""

    # -- Workspace lifecycle hooks (Phase A: UI overhaul) --

    def on_workspace_enter(self, workspace_id: str) -> None:
        """Called when the workspace containing this tool is activated.

        Override to perform setup (e.g. preload data, show panels).
        Default is a no-op — tools that don't need workspace awareness
        are unaffected.
        """

    def on_workspace_exit(self, workspace_id: str) -> None:
        """Called when the workspace containing this tool is deactivated.

        Override to perform teardown (e.g. hide panels, release resources).
        Default is a no-op.
        """

    def preferred_camera_mode(self) -> str:
        """Camera mode this tool prefers while active.

        Returns one of:
        - ``"free_orbit"`` (default) — no constraint, user can orbit freely
        - ``"top_down_2d"`` — force orthographic top-down view, pan/zoom only
        - ``"street_view"`` — first-person perspective; the tool manages
          the camera directly via FreeCamera.  The framework releases any
          prior 2D lock and keeps the view in perspective projection.

        The framework reads this on activate and after each mode transition.
        """
        return "free_orbit"

    def get_auxiliary_dock_widget(self, parent=None):
        """Return a QWidget for the tool's auxiliary panel, or None.

        The widget is hosted in the main window's auxiliary panel — a
        fixed ~300 px column docked flush to the viewport's left edge —
        while the tool is active.  A tool with configurable parameters
        (CSF thresholds, tool options) returns a widget here; stateless
        tools return None.

        The panel follows the tool lifecycle — shown on activate, hidden
        on deactivate.  The tool connects its widget's signals
        (e.g. accepted/cancelled) to drive its own state machine.
        """
        return None

    def get_auxiliary_dock_title(self) -> str:
        """Title for the auxiliary panel when this tool is active.

        Defaults to ``display_name()``.  Override to customize.
        """
        return self.display_name()

    def on_cancel(self) -> Optional[str]:
        """Handle Escape key via the framework's 3-level cascade.

        Return one of:
        - ``"operation_cancelled"`` — an in-progress drag/operation was cancelled
        - ``"mode_exited"`` — the current sub-mode was exited, back to default
        - ``"tool_deactivated"`` — the tool should be fully deactivated
        - ``None`` — nothing to cancel at this level; framework tries next level

        The framework calls this on Escape.  The tool returns the deepest
        cancellation level it can handle; the framework handles the rest.
        See CLAUDE.md #23 for the full escape cascade specification.
        """
        return None

    # -- Creation session (ratified creation lifecycle, UX_SPEC §1) --

    def get_creation_session(self) -> Optional["CreationSession"]:
        """Return the active creation session, or None.

        A non-None value declares the tool's current mode a creation
        session: the framework wires ``[Spacebar]`` repeat, the RMB tool
        context menu, and creation-Esc (discard ghost + exit).  Tools
        that return None (the default) keep their own Esc/RMB behavior.
        """
        return None

    def on_creation_finish(self, context: "ToolContext") -> ToolResult:
        """Accept the ghost geometry and (typically) exit the tool.

        Called by ``[Enter]`` and the RMB menu's Finish entry.  Terminal
        results (FINISHED/CANCELLED/FAILED) auto-deactivate the tool;
        RUNNING keeps it active.  Default: RUNNING.
        """
        return ToolResult.RUNNING

    def on_creation_discard(self, context: "ToolContext") -> None:
        """Discard the ghost geometry; the framework deactivates the tool.

        Called by ``[Esc]`` and the RMB menu's Discard entry.  Discard
        is the symmetric terminal with FINISH — the tool always exits.
        Default: no-op (the tool's ``deactivate()`` clears ghost state).
        """
        pass

    def on_creation_repeat(self, context: "ToolContext") -> ToolResult:
        """Accept the ghost geometry and continue the creation session.

        Called by ``[Spacebar]`` (auto-repeat suppressed — one commit
        per press) and the RMB menu's Repeat entry.  Terminal results
        auto-deactivate; RUNNING keeps the session active.  Default:
        RUNNING.
        """
        return ToolResult.RUNNING

    # -- Editing session (the framework's Save/Export session gate) --

    def has_active_session(self) -> bool:
        """True while the tool holds an open editing session.

        The session gate (Save/Export refuse to run during an active
        editing session — ratified keystone invariant) prompts
        **Accept & Save / Abort** when this returns True.  Default: the
        current mode declares a creation session
        (``get_creation_session()``).  Tools with other transient state
        — lift sessions, active drags — override and OR their own
        conditions in.
        """
        try:
            return self.get_creation_session() is not None
        except Exception:
            return False

    def commit_active_session(self, context: "ToolContext") -> ToolResult:
        """Accept & end the open editing session (the gate's Accept path).

        Runs the session's accept machinery — ground-snap, register,
        fix, wire — and ends the session.  Return a terminal result
        (FINISHED) to also end the tool: the framework deactivates it
        before the save/export proceeds, so the persist stage only ever
        sees stable data.  Default: accept the creation session via
        :meth:`on_creation_finish`.
        """
        return self.on_creation_finish(context)

    def save_state(self) -> dict:
        """Return a JSON-serializable dict of tool state for workspace restore."""
        return {}

    def restore_state(self, state: dict) -> None:
        """Restore tool state from a previously saved dict."""


class IFileImporter(ABC):
    """Converts an external file format into a USD layer.

    This is the Python-friendly equivalent of USD's C++ FileFormat plugin.
    Since Sdf.FileFormat.Read() is not exposed to Python (see CLAUDE.md #9),
    this port bridges the gap: the plugin writes a .usda/.usdc file, then
    core's StageManager adds it as a sublayer.
    """

    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """File extensions this importer handles, e.g. ['.pcd', '.las']."""

    @abstractmethod
    def import_file(
        self, source_path: str, dest_layer_path: str, options: dict
    ) -> str:
        """Convert source_path into a USD layer at dest_layer_path.

        Args:
            source_path: path to the input file (e.g. 'survey.las')
            dest_layer_path: where to write the output
                (e.g. 'Reality/PointClouds/slam_cloud.usda')
            options: plugin-specific dict (e.g. {'downsample': 0.1, 'crs': 'EPSG:32654'})

        Returns:
            The path to the written .usda or .usdc file.

        Raises:
            FileNotFoundError: if source_path doesn't exist
            ValueError: if the file is malformed or unsupported
            RuntimeError: if conversion fails
        """

    def import_options(self) -> Optional[dict]:
        """Declare per-file import options shown in the Import dialog.

        Return ``None`` (the default) when the importer takes no options —
        existing importers are unchanged.  When overridden, return a schema
        dict mapping ``field_name`` → field spec::

            {
                "field_name": {
                    "type": "choice" | "string" | "int" | "float" | "bool",
                    "label": "Human-readable label",
                    "default": <default value>,
                    # type-specific keys:
                    "choices": [{"value": ..., "label": ...}],  # "choice" only
                    "placeholder": "...",                        # "string" only
                    "show_when": {"other_field": "value"},       # conditional show
                }
            }

        The Import dialog auto-builds a widget per field and collects the
        values into the ``options`` dict passed to ``import_file()``.
        """
        return None

    def unavailable_reason(self, stage) -> Optional[str]:
        """Why this importer cannot run against *stage* right now, or None.

        Return ``None`` (the default) when the import may proceed.  Return a
        human-readable reason when the importer is unavailable for the
        stage's current state — the Import dialog disables the file's import
        and shows the reason.  The domain still refuses behind the UI gate
        (scripts bypass dialogs), so this is product surface, not
        enforcement (wayfinder #169).
        """
        return None

    def wants_unit_name(self) -> bool:
        """Declare that the import door should mint ``options["unit_name"]``.

        True for importers that author one cloud unit frame
        (``Cloud_<8 hex>``, #390) per patch — the host mints a name free
        on the composed stage, because a reused name composes as a
        shadowed duplicate (CLAUDE.md #72/#97).  The importer mints its
        own name when the key is absent (headless API use with no
        stage).  (#334, map #318)
        """
        return False

    def import_tile_batch(self, dest_layer_path: str, tiles: list,
                          unit_name: str, display_name: str) -> str:
        """Write several sources as one merged cloud unit (a tile folder, #416).

        *tiles* is ``[(source_path, options), ...]``, each options dict as
        :meth:`import_file` takes it.  The sources become one cloud frame
        named *unit_name* (its identity) in one layer, labelled
        *display_name* (``atlas:displayName``).  Importers that cannot merge
        sources keep this default.
        """
        raise NotImplementedError(
            f"{type(self).__name__} cannot import sources as one layer")

    def wants_site_origin(self) -> bool:
        """Declare that an existing map SiteOrigin should be injected.

        True for importers that can honour the map's WGS84 anchor when
        one already exists — the door then adds
        ``options["existing_site_origin"]`` and ``options["site_origin"]``
        (#334).  Coordinate modes the importer owns still decide whether
        to use it; declaring does not force a mode.
        """
        return False

    def writes_map_layer(self, source_path: str, options: dict) -> bool:
        """Whether this call writes the map layer at the import destination.

        Asked per call, before the door scaffolds anything.  ``False`` means
        the call writes only sibling files (e.g. a colour envelope filled
        under its own layer), so the door skips the destination entirely:
        no draft scaffold, no at-risk re-import gate, no root sublayer
        wiring.  The importer still runs, and may ignore the destination it
        is handed.  Default ``True``: the destination is the import's layer.
        """
        return True

    def dest_layer_name(self, source_path: str) -> str | None:
        """File name of the layer this source imports into, or None for the default.

        The door places the layer directly under its category directory.  The
        default (``None``) names it after the source file (``<basename>.usda``),
        so every source with the same basename shares one layer.  An importer
        whose sources are distinct runs returns a per-run name here so that a
        second run never clears the first.  Must be a bare file name.  A
        per-run name starts with ``run_``: the layer row then reads as
        "Point Clouds · run_<id>" rather than an identical "Point Clouds".
        """
        return None

    def destination_category(self) -> str | None:
        """Category directory this importer's layer is placed under, or None.

        The door places the layer at ``<project>/<category>/<name>``, and
        ``category_for_path`` resolves that directory back to a category, so
        the value must be one of the project's categories: ``"Reality/PointClouds"``,
        ``"Reference"``, or ``"Navigation"``.  ``None`` (the default) refuses the
        import, since the door has no place to write the layer (#422).
        """
        return None

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this importer.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value


class IStageContributor(ABC):
    """Manages a named sublayer in the stage's layer stack.

    Each plugin that contributes persistent data implements this port.
    The plugin owns its sublayer — creates it if missing, ensures it's
    positioned correctly in the stack, and flushes on close.
    """

    @abstractmethod
    def layer_name(self) -> str:
        """Logical name for this plugin's layer, e.g. 'slam_cloud'."""

    @abstractmethod
    def default_layer_path(self) -> str:
        """Default .usda path relative to the stage directory,
        e.g. 'slam_toolpack/cloud.usda'."""

    @abstractmethod
    def on_stage_opened(self, stage_mgr: "StageManagerInterface") -> None:
        """Called when a stage is opened.  Ensure sublayer exists and is
        positioned correctly in the layer stack."""

    @abstractmethod
    def on_stage_closing(self, stage_mgr: "StageManagerInterface") -> None:
        """Called before stage closes.  Flush / save if needed."""

    def layer_strategy(self) -> str:
        """Return the write strategy for this contributor's layer.

        ``"draft_overlay"`` (default), ``"create_new"``, or ``"read_only"``.

        This is a programmatic override for the ``plugInfo.json`` declaration.
        The ``plugInfo.json`` value takes precedence; this method is only
        consulted when no strategy is declared in the manifest.
        """
        return "draft_overlay"

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this contributor.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value


class IPanelFactory(ABC):
    """Creates a Qt dock widget that plugs into the main window.

    This is the ONLY port with an eventual Qt dependency — the factory
    receives a QWidget parent and returns a QDockWidget.  However, the
    module itself imports without Qt (string annotations are used for
    typed context references).
    """

    @abstractmethod
    def panel_id(self) -> str:
        """Unique identifier, e.g. 'slam_toolpack.control_panel'."""

    @abstractmethod
    def display_name(self) -> str:
        """Title bar text for the dock widget."""

    @abstractmethod
    def create_panel(self, parent, context: "PanelContext"):
        """Build and return a QDockWidget.

        Args:
            parent: the QMainWindow (for parenting)
            context: bounded context with stage access and event signals

        Returns:
            A QDockWidget instance.
        """

    def default_area(self) -> str:
        """Where to dock: 'left', 'right', 'bottom'.  Default: 'right'."""
        return "right"

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this panel.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value


@dataclass(frozen=True)
class PrimAction:
    """One special-editor launchpad (map #433 task C, #452, #456).

    A section may carry actions alongside its fields — the launchpads
    too large for a row (the traffic-light bulb canvas, #452).  The host
    collects every section action into the header's ⋮ launcher (one
    click runs the prim's only action, several pop a menu); the
    callback runs at once, outside the edit gate, and may start a tool.
    """

    label: str
    callback: Callable[[], None]


# ---------------------------------------------------------------------------
# Inspector section providers — the Properties panel's domain sections
# (#444 ratified, built in #450).  A plugin offers typed FieldSpec rows
# (or one custom widget) for the prims it owns; the panel renders them
# inside its one spine frame and gates every write through the panel's
# single edit session — one undo step per Save.
# ---------------------------------------------------------------------------

SECTION_DOMAINS = frozenset({
    "navigation", "reality", "reference", "atlas", "host",
})
"""The band a section renders in.  ``host`` is reserved for the panel's
own sections; a plugin declaring it still lands in the domain band and
the host logs a warning."""

SECTION_FIELD_KINDS = frozenset({
    "text", "int", "float", "choice", "tags", "tristate",
})
"""The ratified FieldSpec kinds (PROPERTIES_PANEL_SPEC §4)."""


@dataclass(frozen=True)
class FieldSpec:
    """One gated row in a plugin-provided section (#444).

    ``get(prim)`` returns the widget-ready value — ``None`` means the IR
    does not hold the key and the row displays "—" (never a supplied
    default, #197).  ``apply(prim, value)`` writes it; ``value is None``
    removes the attribute (the tristate middle).  ``label`` is a source
    string the provider runs through ``ctx.translate`` while building
    the spec — the host renders it as-is, and ``sections()`` re-runs on
    every inspect so a locale change rebakes it.

    ``minimum``/``maximum``/``step`` are the spin-box range for the
    numeric kinds (absent = Qt's own span with the unstated sentinel one
    below the floor) — an amendment to the ratified table, which did not
    cover ranges; ``unit`` becomes the value suffix (" km/h").

    ``live`` marks a field that moves the drawn geometry (a height above
    the ground): the panel writes it to the stage as it is edited, so the
    viewport shows the value at once; Save keeps it as one undo step and
    Cancel puts it back.  Every other field buffers until Save.
    """

    key: str
    label: str
    kind: str
    get: Callable[[Any], Any]
    apply: Callable[[Any, Any], None]
    unit: str = ""
    choices: tuple[str, ...] = ()
    read_only: bool = False
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    live: bool = False

    def __post_init__(self) -> None:
        if self.kind not in SECTION_FIELD_KINDS:
            raise ValueError(f"unknown field kind: {self.kind!r}")


@dataclass(frozen=True)
class SectionSpec:
    """One section a provider contributes to the spine's domain band.

    Either ``fields`` rows (rendered by the host's field grammar) or a
    ``widget_factory`` (a custom body — the factory owns its own rows),
    or both.  ``title`` is a source string the provider runs through
    ``ctx.translate`` while building the spec (same as ``FieldSpec.label``).
    ``id`` must be unique across providers; the host keys the
    persisted open/closed state on it.  ``order`` is coarse (multiples
    of 10); equal orders tie on registration order.  ``actions`` are
    collected into the header's ⋮ launcher, one entry each (#452, the
    in-section row that repeated them is gone) — a launchpad outside the
    edit gate, never a field.
    """

    id: str
    domain: str
    title: str
    default_open: bool = True
    order: int = 100
    fields: tuple[FieldSpec, ...] = ()
    widget_factory: Callable[["EditorContext", Any], Any] | None = None
    actions: tuple[PrimAction, ...] = ()

    def __post_init__(self) -> None:
        if self.domain not in SECTION_DOMAINS:
            raise ValueError(f"unknown section domain: {self.domain!r}")
        if not self.title:
            raise ValueError("section title is required")


class SectionSaveRefused(Exception):
    """A factory's ``end("save")`` refuses the write — nothing lands (#444).

    Raised inside the host's save bracket; the host rolls the session
    layer back to its before-snapshot (so field writes made earlier in
    the same bracket vanish too), shows ``str(exc)`` to the user, and
    keeps the session open.  Refuse-don't-repair — the same stance as
    ``nav.PersistGateRefused``.
    """


class IInspectorSectionProvider(ABC):
    """Offers domain sections for prims in the Properties panel (#444).

    A section provider contributes *parts* of the ordinary spine: the
    host keeps its header, meta line, edit gate and section frame, and
    renders the provider's sections inside the domain band.  (This is
    the contract that replaced the ``IPropertyEditor`` whole-panel
    takeover — that ABC died with #451, when the RE panel migrated.)
    ``sections()`` re-runs on every inspect, save commit and locale
    change, and is pinned while an edit session is open.

    A ``widget_factory`` body implements the session protocol the host
    drives:

    - ``begin_edit_session()`` — open: snapshot values, enable fields
    - ``edit_session_dirty() -> bool`` — anything unsaved?
    - ``end_edit_session(action)`` — ``"save"`` writes the buffered
      changes; ``"cancel"`` and ``"discard"`` revert the form (nothing
      was written, so the stage needs no restoring)

    plus ``deactivate()``, called when the section tears down — a body
    with external state (a hover highlight) clears it there.  A body
    that can never dirty a session (a read-only member tree) sets the
    class attribute ``read_only = True`` and keeps the three protocol
    methods as no-ops: the host then keeps it out of the pencil's
    eligibility, so a section offering no editable row never arms a
    dead pencil.

    A body may expose an optional Qt signal named ``content_changed``
    (no arguments).  The host connects it to its dirty-marker refresh
    at build time, so a widget whose edits fire no ``FieldSpec`` signal
    (a tag table, for instance) still enables the Save button the
    moment it goes dirty.  Emitting it outside an edit session is
    harmless — the refresh probes only while a session is open.
    """

    @abstractmethod
    def provides(self, prim) -> bool:
        """Whether this provider renders sections for *prim*."""

    @abstractmethod
    def sections(self, context: "EditorContext", prim) -> list[SectionSpec]:
        """The sections for *prim*; empty when it has none (e.g. no schema)."""

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this provider.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value


class IPluginPreferences(ABC):
    """Declares persistent settings for a plugin.

    Settings are auto-persisted to:
      ~/.config/veer-studio/plugin_prefs/{plugin_id}.json

    The framework loads these on startup and passes them into contexts
    as the `preferences` dict.
    """

    @property
    def plugin_id(self) -> str:
        """Must match the plugin's folder name / PlugPlugin name."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value

    @abstractmethod
    def fields(self) -> dict:
        """Return {field_name: FieldDef} describing all settings.

        FieldDef is a simple dict:
            {'type': str, 'default': Any, 'label': str, 'choices': list|None}

        The framework auto-generates a settings UI from this.
        """

    def create_preferences_widget(self, parent, values: dict):
        """Optional: build a custom preferences widget.

        If not overridden, the framework auto-generates one from fields().
        """
        return None


# ---------------------------------------------------------------------------
# Compiler-stage port ABCs (Phase 2a)
# ---------------------------------------------------------------------------


class IValidator(ABC):
    """Validates a composed stage and produces a diagnostic report.

    Plugins register validators for their domain (e.g. lanelet topology,
    point cloud coverage, asset placement).  Validators are run before export
    or on explicit user request.

    This is the IR-verifier compiler stage — it reads the stage and produces
    a ``ValidationReport`` but never modifies prims.
    """

    @abstractmethod
    def validator_id(self) -> str:
        """Unique identifier, e.g. ``'vectormap_toolpack.lanelet_validator'``."""

    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name, e.g. ``'Lanelet2 Topology Validator'``."""

    @abstractmethod
    def validate(self, stage, stage_mgr: "StageManagerInterface") -> "ValidationReport":
        """Run validation and return a report.

        Args:
            stage: The composed ``Usd.Stage`` to validate.
            stage_mgr: Bounded ``StageManagerInterface`` for querying layer info.

        Returns:
            A ``ValidationReport`` with zero or more diagnostics.
        """

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this validator.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value


class IExporter(ABC):
    """Exports the composed stage (or a subset) to a domain-specific format.

    This is the output-side counterpart to ``IFileImporter``.  While
    ``IFileImporter`` converts external files INTO USD layers, ``IExporter``
    converts FROM USD into external formats (Lanelet2 ``.osm``, OpenDRIVE
    ``.xodr``, ROS Nav2 ``.pgm``+``.yaml``, GeoJSON, etc.).

    This is the backend codegen compiler stage.
    """

    @abstractmethod
    def exporter_id(self) -> str:
        """Unique identifier, e.g. ``'vectormap_toolpack.lanelet2_exporter'``."""

    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name, e.g. ``'Lanelet2 (Autoware .osm)'``."""

    @abstractmethod
    def export_format(self) -> str:
        """File extension this exporter produces, e.g. ``'.osm'``.

        Empty (``''``) when the export is a folder of files rather than one
        file; the export dialog then offers a folder picker.
        """

    @abstractmethod
    def export_stage(
        self, stage, stage_mgr: "StageManagerInterface", output_path: str, options: dict
    ) -> "ExportReport":
        """Export the stage to *output_path* and return a report.

        Args:
            stage: The composed ``Usd.Stage`` to export from.
            stage_mgr: Bounded ``StageManagerInterface``.
            output_path: Where to write the output file.
            options: Plugin-specific dict (e.g. ``{'include_metadata': True}``).

        Returns:
            An ``ExportReport`` indicating success/failure and any diagnostics.
        """

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this exporter.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value


class IFusionPlugin(ABC):
    """Reactive compiler pass — listens to prim mutations and fuses data
    across independent layers.

    A Fusion Plugin monitors changes to one or more prim types and
    algorithmically resolves cross-layer relationships.  Examples:

    * Snap assets to the terrain mesh when their position changes
    * Auto-compute ``hdmap:approachLanelet`` when a navigable target is placed
    * Flag lanelet/point-cloud discrepancies at curbs

    .. note::

        This is the **highest-cost** plugin type.  Every prim mutation
        triggers ``prim_filter()``.  Use ``poll()`` to disable the plugin
        entirely when not needed (e.g. no GroundMesh in the stage), and
        ``prim_filter()`` to scope to specific prim types.
    """

    @abstractmethod
    def fusion_id(self) -> str:
        """Unique identifier, e.g. ``'atlas_studio.snap_to_ground'``."""

    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name."""

    @abstractmethod
    def prim_filter(self, prim) -> bool:
        """Return True only for prims this fusion plugin cares about.

        This is the primary performance guard.  The framework calls
        ``prim_filter()`` on every mutated prim before dispatching to
        ``on_mutation()``.  Return False to skip quickly.
        """

    @abstractmethod
    def on_mutation(
        self,
        prim,
        mutation_ctx: "StageMutationContext",
    ) -> None:
        """Called after a filtered prim has been created or modified.

        The plugin can read the prim's current state, query the spatial
        index, and write new relationships or attributes via *mutation_ctx*.
        The context ensures all writes go to the correct edit target and are
        grouped into a single USD change block.

        **originator_id guard pattern** — every ``on_mutation()``
        implementation should start with::

            if mutation_ctx.originator_id == self.fusion_id:
                return  # I caused this mutation — don't react to myself

        This prevents infinite event loops when a fusion plugin writes back
        to the stage and its own writes re-trigger mutation notification.
        """


    @classmethod
    def poll(cls, stage_mgr: "StageManagerInterface") -> bool:
        """Return False to temporarily disable this fusion plugin.

        Default is True.  Override to disable the plugin when the stage
        doesn't contain relevant data (no GroundMesh, no lanelets, etc.).
        """
        return True

    def priority(self) -> int:
        """Execution order (lower = earlier).  Default 100.

        Fusion plugins with dependencies (e.g. snap-to-ground must run
        before approach-lanelet) use priority to order themselves.
        """
        return 100

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this fusion plugin.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value


class IIntegrationPlugin(ABC):
    """Lifecycle hook for cross-layer integration setup.

    While ``IStageContributor`` manages its OWN sublayer on stage open,
    ``IIntegrationPlugin`` manages cross-layer RELATIONSHIPS.  It runs on
    stage open to wire up references between layers (point cloud → ground
    mesh → lanelets → assets) and on stage close for cleanup.

    Integration plugins fire **after** all contributors have finished
    ``on_stage_opened`` (so all layers are in the stack) and **before**
    any contributor ``on_stage_closing`` (so cross-layer data is intact).
    """

    @abstractmethod
    def integration_id(self) -> str:
        """Unique identifier, e.g. ``'atlas_studio.layer_linker'``."""

    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name."""

    @abstractmethod
    def on_stage_opened(self, stage_mgr: "StageManagerInterface") -> None:
        """Called after ALL contributors have finished ``on_stage_opened``.

        At this point all plugin sublayers are in the stack and ready for
        cross-layer relationship authoring.
        """

    @abstractmethod
    def on_stage_closing(self, stage_mgr: "StageManagerInterface") -> None:
        """Called before ANY contributor ``on_stage_closing``.

        At this point all cross-layer data is still intact.
        """

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this integration plugin.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value


# ---------------------------------------------------------------------------
# Assembly provider port (Phase 1A)
# ---------------------------------------------------------------------------


class IAssemblyProvider(ABC):
    """Declares the behavioral contract for an assembly type.

    An assembly provider maps a nav **subtype** (the ``hdmap:subtype``
    value its prims carry) to an ``AssemblySchema`` — the set of custom
    attributes and applied API schemas that define the assembly's
    behavioral contract (Layer-3).

    Providers are **schema-only**: they declare what to stamp, not how
    to build grounding geometry or relationships.  Grounding stays in
    the domain importer (e.g. ``prim_builder`` for vectormap data).

    Modeled on ``IValidator`` — identifiers are ``@abstractmethod``
    instance methods, never class attributes (CLAUDE.md #33).
    """

    @abstractmethod
    def assembly_id(self) -> str:
        """Unique identifier, e.g. ``'autoware_assemblies.virtual_traffic_light'``."""

    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name, e.g. ``'Virtual Traffic Light Assembly'``."""

    @abstractmethod
    def subtype_token(self) -> str:
        """The ``hdmap:subtype`` value this provider decorates — the key
        it is registered and found under.

        e.g. ``'virtual_traffic_light'``.  A nav prim's kind lives on the
        kernel's own type axis (``hdmap:type`` for the class,
        ``hdmap:subtype`` for the refinement); a regulatory element
        carries no ``atlas:type`` at all (IDENTITY_SPEC §8, wayfinder
        #168), so the subtype is the only key there is.
        """

    @abstractmethod
    def get_schema(self) -> "AssemblySchema | None":
        """Return the assembly schema to stamp, or None if no schema.

        None means "this provider applies but has no behavioral schema
        to stamp" — allowed for future marker-style providers.
        """

    @classmethod
    def poll(cls, stage_mgr) -> bool:
        """Optional guard — return False to suppress this provider."""
        return True

    def get_terminals(self) -> list:
        """Return the assembly's terminal/pin manifest.

        Each terminal maps a Lanelet2 role to a USD relationship with
        direction, multiplicity, and accepted prim types for wiring
        validation.  Returns an empty list if the assembly declares no
        terminals (backward-compatible default).

        .. versionadded:: Phase A — Assembly Terminal Port
        """
        return []

    def prim_path_prefix(self) -> str:
        """Return the parent prim path where instances of this assembly live.

        The default matches the Atlas object convention under the site root.
        Autoware regulatory assemblies override this to return the
        navigation regulatory root.

        .. versionadded:: Phase A — Assembly Terminal Port
        """
        from core import paths
        return paths.assets_root()

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this provider.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value


# ---------------------------------------------------------------------------
# Unsaved-state provider port
# ---------------------------------------------------------------------------


class IUnsavedStateProvider(ABC):
    """Optional port for plugins that hold unsaved state outside USD layers.

    Plugins that maintain in-memory state flushed at save — e.g. an
    authority store, a draft queue, or a sidecar database not yet
    written to a USD layer — implement this so the framework can
    discover unpersisted work.  The core already scans every composed
    USD layer for ``layer.dirty``; this port covers the narrow case
    where a plugin's unsaved state has *not yet been authored* to any
    layer and is only flushed by a ``before_save`` stage hook or
    equivalent.

    Providers are registered via
    ``PluginRegistry.register_unsaved_state_provider()``.  The
    framework aggregates all providers; if **any** returns ``True``
    the title-bar dirty dot lights and the close-prompt fires.
    """

    @abstractmethod
    def has_unsaved_state(self) -> bool:
        """Return ``True`` if this plugin has unpersisted, non-USD changes."""

    # -- Metadata (set by registry at registration time) --

    @property
    def plugin_id(self) -> str:
        """The plugin that owns this provider.  Set by PluginRegistry."""
        return getattr(self, "_plugin_id", "")

    @plugin_id.setter
    def plugin_id(self, value: str) -> None:
        self._plugin_id = value



# ---------------------------------------------------------------------------
# Import vocabulary — the import door's stamps, the declared origin, and
# import identity (veer/veer-studio-plugin-sdk#10)
# ---------------------------------------------------------------------------

# Static definitions, not lazy re-exports, for the same reason as the cloud
# roles above: the SDK's standalone ``_ports.py`` copy gets no
# ``__getattr__`` dispatcher.  ``core.atlas_schema``, ``core.site_origin``
# and ``core.navigation._identity`` re-import these, so every existing
# import line keeps working.  These run *inside* ``import_file`` — a path
# with no ToolContext — which is why they are module-level, not doors.

# -- Import-door stamps: authored once at import, never mutated -----------
ATTR_IMPORT_MODE = "atlas:importMode"             # token: auto_center | auto_center_reproject | mgrs_grid | raw | declared_origin
ATTR_SOURCE_CRS = "atlas:sourceCoordinateSystem"   # string: e.g. "MGRS_local_metres:54SVE"
ATTR_IMPORT_TRANSFORM = "atlas:importTransform"    # Matrix4d: source→stage-local (baked into points)

# -- SiteOrigin: typed view of the coordinate anchor on the root layer ----
# customLayerData keys (stored in root layer, not on prims)
_KEY_ANCHOR_MODE = "atlas:anchorMode"
_KEY_ANCHOR_LAT = "atlas:anchorLat"
_KEY_ANCHOR_LON = "atlas:anchorLon"
_KEY_ANCHOR_ELE = "atlas:anchorEle"
_KEY_UTM_ZONE = "atlas:utmZone"
_KEY_UTM_HEMISPHERE = "atlas:utmHemisphere"
# NOTE: MAP_SPEC §3 names the elevation key ``atlas:anchorHeight``; the
# existing implementation predates that and uses ``atlas:anchorEle``.  The
# two refer to the same concept.  We keep the existing key to avoid
# breaking OSM / vectormap imports that already read it.
_KEY_Z_SHIFT = "atlas:zShift"
_KEY_MGRS_GRID = "atlas:mgrsGrid"
_KEY_SOURCE = "atlas:source"

# Latitude bands C..X, 8° each, 80°S to 84°N.  Index 10 (N) = equator.
_LAT_BANDS = "CDEFGHJKLMNPQRSTUVWXX"
# 100 km column letters cycle every third zone.
_E100K_SETS = ("ABCDEFGH", "JKLMNPQR", "STUVWXYZ")
# 100 km row letters cycle every other zone, repeating every 2,000 km.
_N100K_SETS = ("ABCDEFGHJKLMNPQRSTUV", "FGHJKLMNPQRSTUVABCDE")


def _utm_zone_from_lon(lon: float) -> int:
    """Auto-detect UTM zone from WGS84 longitude.

    Zones are 6° wide starting at 180°W: zone 1 covers [-180°, -174°).
    """
    return int((lon + 180.0) / 6.0) + 1


def _opt_int(value) -> int | None:
    """Parse an optional integer from customLayerData (may be stored as int or str)."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _opt_float(value) -> float | None:
    """Parse an optional float from customLayerData (may be stored as float or str)."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _latlon_to_grid_name(lat: float, lon: float) -> str:
    """MGRS grid zone designator + 100 km square for *lat*, *lon*.

    Uses ``pyproj`` for the UTM projection when available (full accuracy);
    falls back to zone + latitude band only (e.g. ``"54S"``) when pyproj is
    not installed.
    """
    # Zone and hemisphere (pure math, no projection needed).
    zone = int((lon + 180.0) / 6.0) + 1
    if zone > 60:
        zone = 60
    hemisphere = "N" if lat >= 0 else "S"

    # Latitude band.
    band_idx = int((lat + 80.0) / 8.0)
    band_idx = max(0, min(len(_LAT_BANDS) - 1, band_idx))
    band = _LAT_BANDS[band_idx]

    # Try pyproj for the 100 km square letters.  Fall back to zone+band if
    # pyproj is not installed (it's a heavy dependency — optional in core).
    try:
        import pyproj  # noqa: PLC0415

        epsg = (32600 if hemisphere == "N" else 32700) + zone
        ll2utm = pyproj.Transformer.from_crs(
            "EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        easting, northing = ll2utm.transform(lon, lat)

        col = int(easting / 100_000.0)
        col_set = _E100K_SETS[(zone - 1) % 3]
        col_letter = col_set[col - 1] if 1 <= col <= len(col_set) else ""

        row = int(northing / 100_000.0) % 20
        row_set = _N100K_SETS[(zone - 1) % 2]
        row_letter = row_set[row] if 0 <= row < len(row_set) else ""

        square = f"{col_letter}{row_letter}" if col_letter and row_letter else ""
    except ImportError:
        square = ""

    if square:
        return f"{zone}{band} {square}"
    return f"{zone}{band}"


@dataclass
class SiteOrigin:
    """Site origin — typed view of the coordinate anchor on the root layer.

    All fields map to ``customLayerData`` keys on the root layer.
    """

    anchor_mode: str = "utm_grid"
    """``"utm_grid"`` or ``"tangent_plane"``."""

    anchor_lat: float = 0.0
    """WGS84 latitude of the anchor point (degrees)."""

    anchor_lon: float = 0.0
    """WGS84 longitude of the anchor point (degrees)."""

    anchor_ele: float = 0.0
    """Elevation at the anchor point (metres, default 0).

    MAP_SPEC §3 calls this ``anchorHeight``; same concept, different key name.
    For ``auto_center`` PCD imports this is the WGS84 altitude of the ground
    plane if known (otherwise 0).
    """

    utm_zone: int | None = None
    """UTM zone number (1–60).  Only meaningful for ``utm_grid`` mode."""

    utm_hemisphere: str | None = None
    """``"N"`` or ``"S"``.  Only meaningful for ``utm_grid`` mode."""

    z_shift: float | None = None
    """Z offset (metres) subtracted from every point during ``auto_center``
    import (including the reproject-into-existing-frame branch) so the ground
    surface lands at Z=0.  ``None`` when no shift was applied (or the import
    mode is not ``auto_center``).  Recorded so the original Z can be
    recovered: ``z_original = z_local + z_shift`` — the Lanelet2 export
    applies exactly that to ``ele``."""

    mgrs_grid: str | None = None
    """MGRS 100 km grid square (e.g. ``"54SVE"``).  ``mgrs_grid`` mode only."""

    source: str | None = None
    """Provenance — which importer stamped this origin (e.g.
    ``"pcd_importer.auto_center"``, ``"osm_importer"``)."""

    # ------------------------------------------------------------------
    # Derived
    # ------------------------------------------------------------------

    @property
    def grid_reference(self) -> str:
        """Human-readable MGRS grid reference for this site origin.

        Returns the MGRS grid zone designator + 100 km square (e.g.
        ``"54S VE"``) for ``tangent_plane`` and ``utm_grid`` modes.
        Returns ``"Local"`` for ``local`` or ``auto_center`` modes
        (not yet georeferenced).
        """
        if self.anchor_mode in ("local", "auto_center"):
            return "Local"
        if self.anchor_lat == 0.0 and self.anchor_lon == 0.0:
            return "Local"
        if self.mgrs_grid:
            return self.mgrs_grid
        return _latlon_to_grid_name(self.anchor_lat, self.anchor_lon)

    # ------------------------------------------------------------------
    # customLayerData I/O (same pattern as map_version.py)
    # ------------------------------------------------------------------

    @classmethod
    def from_layer(cls, root_layer) -> "SiteOrigin":
        """Read site origin from a root layer's ``customLayerData``.

        Returns a ``SiteOrigin`` with defaults for any missing keys.
        *root_layer* is any object carrying ``customLayerData`` (an
        ``Sdf.Layer`` in-host).
        """
        cld = root_layer.customLayerData
        return cls(
            anchor_mode=cld.get(_KEY_ANCHOR_MODE, "utm_grid"),
            anchor_lat=float(cld.get(_KEY_ANCHOR_LAT, 0.0)),
            anchor_lon=float(cld.get(_KEY_ANCHOR_LON, 0.0)),
            anchor_ele=float(cld.get(_KEY_ANCHOR_ELE, 0.0)),
            utm_zone=_opt_int(cld.get(_KEY_UTM_ZONE)),
            utm_hemisphere=cld.get(_KEY_UTM_HEMISPHERE),
            z_shift=_opt_float(cld.get(_KEY_Z_SHIFT)),
            mgrs_grid=cld.get(_KEY_MGRS_GRID),
            source=cld.get(_KEY_SOURCE),
        )

    def write_to_layer(self, root_layer) -> None:
        """Write (merge) site origin into the root layer's ``customLayerData``.

        Existing keys not in the site origin block are left untouched.
        Optional fields (``utm_zone``, ``utm_hemisphere``, ``z_shift``,
        ``mgrs_grid``, ``source``) are only written when set.
        """
        cld = dict(root_layer.customLayerData)  # copy — preserves other keys
        cld[_KEY_ANCHOR_MODE] = self.anchor_mode
        cld[_KEY_ANCHOR_LAT] = self.anchor_lat
        cld[_KEY_ANCHOR_LON] = self.anchor_lon
        cld[_KEY_ANCHOR_ELE] = self.anchor_ele
        if self.utm_zone is not None:
            cld[_KEY_UTM_ZONE] = self.utm_zone
        else:
            cld.pop(_KEY_UTM_ZONE, None)
        if self.utm_hemisphere is not None:
            cld[_KEY_UTM_HEMISPHERE] = self.utm_hemisphere
        else:
            cld.pop(_KEY_UTM_HEMISPHERE, None)
        if self.z_shift is not None:
            cld[_KEY_Z_SHIFT] = self.z_shift
        else:
            cld.pop(_KEY_Z_SHIFT, None)
        # Auto-compute and persist the MGRS grid name when we have a
        # georeference but no stored grid.  The grid name is a stable
        # function of lat/lon — computing it once at write time makes it
        # visible in the Property Inspector without cluttering the status bar.
        mgrs = self.mgrs_grid
        if not mgrs and self.anchor_mode not in ("local", "auto_center"):
            if self.anchor_lat != 0.0 or self.anchor_lon != 0.0:
                mgrs = self.grid_reference
                self.mgrs_grid = mgrs
        if mgrs:
            cld[_KEY_MGRS_GRID] = mgrs
        else:
            cld.pop(_KEY_MGRS_GRID, None)
        if self.source is not None:
            cld[_KEY_SOURCE] = self.source
        else:
            cld.pop(_KEY_SOURCE, None)
        root_layer.customLayerData = cld

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_bbox(
        cls,
        bbox: tuple[float, float, float, float],
        *,
        mode: str = "utm_grid",
    ) -> "SiteOrigin":
        """Create a SiteOrigin from a WGS84 bounding box.

        Args:
            bbox: ``(min_lat, min_lon, max_lat, max_lon)``.
            mode: ``"utm_grid"`` (default) or ``"tangent_plane"``.

        Returns:
            A new ``SiteOrigin`` with the anchor point and metadata set.
        """
        south, west, north, east = bbox
        center_lat = (south + north) / 2.0
        center_lon = (west + east) / 2.0

        if mode == "tangent_plane":
            return cls(
                anchor_mode="tangent_plane",
                anchor_lat=center_lat,   # centroid → small symmetric coords
                anchor_lon=center_lon,   # centroid
                anchor_ele=0.0,
            )

        # utm_grid mode (default)
        zone = _utm_zone_from_lon(center_lon)
        hemisphere = "N" if center_lat >= 0 else "S"

        # Warn if the bbox spans > 3° from the central meridian of the
        # detected zone (i.e. it crosses into a neighbouring zone).
        central_meridian = zone * 6 - 183  # central meridian of zone
        lon_span = east - west
        if abs(west - central_meridian) > 3.0 + lon_span or abs(east - central_meridian) > 3.0:
            _log.warning(
                "Bbox [%.4f, %.4f, %.4f, %.4f] may straddle UTM zone %d "
                "boundary (central meridian %.0f°).  Consider "
                "anchor_mode='tangent_plane' instead.",
                south, west, north, east, zone, central_meridian,
            )

        return cls(
            anchor_mode="utm_grid",
            anchor_lat=center_lat,
            anchor_lon=center_lon,
            anchor_ele=0.0,
            utm_zone=zone,
            utm_hemisphere=hemisphere,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def utm_epsg(self) -> int | None:
        """EPSG code for the UTM CRS, or ``None`` for tangent_plane mode.

        North: ``326{zone}``, South: ``327{zone}``.
        """
        if self.utm_zone is None:
            return None
        base = 32600 if self.utm_hemisphere == "N" else 32700
        return base + self.utm_zone


# -- Import identity (§4.1 of the navigation schema) ----------------------

#: Element separator — a ``sourceKey`` may contain neither it nor the
#: array separator.
SOURCE_ELEMENT_SEP = "/"
_PREFIX_CHARS = re.compile(r"[^a-z0-9]+")


def imported_source_id(source_key: str, kind: str, source_id: int | str) -> str:
    """``<sourceKey>/<kind>/<id>`` — an imported entity's origin assertion.

    *kind* is the **source's own** kind (``node`` / ``way`` / ``relation`` /
    ``file`` / ``tile``),
    never an IR class — the first segment is the discriminator between the
    two vocabularies, the middle one deliberately differs (§4.1).
    """
    return f"{source_key}{SOURCE_ELEMENT_SEP}{kind}{SOURCE_ELEMENT_SEP}{source_id}"


def source_key_for(source_path: str) -> str:
    """Derive the slug a source file registers under (§4.1).

    Contains neither ``/`` nor ``;``, and is never 32 lowercase hex — that
    shape is the Site's, and the first segment is the discriminator.
    """
    import os

    stem = os.path.splitext(os.path.basename(str(source_path)))[0]
    slug = _PREFIX_CHARS.sub("-", stem.lower()).strip("-") or "source"
    if len(slug) == 32 and all(c in "0123456789abcdef" for c in slug):
        slug = f"{slug}-1"
    return slug
