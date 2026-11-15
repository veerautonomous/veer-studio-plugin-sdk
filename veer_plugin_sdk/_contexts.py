# Atlas Studio — Bounded Context Objects
#
# Dataclasses and the StageManagerInterface ABC that form the bounded API
# surface between the framework and plugins.  This module has zero
# dependencies beyond the Python standard library — no Qt, no USD imports.
#
# See ../engineering/architecture/PLUGIN_ARCHITECTURE.md §5 for the full specification.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from pxr import Usd
    from core.ports import GizmoManagerInterface, JobServiceInterface


class DraftSessionDirtyError(RuntimeError):
    """Raised when closing a stage with an active, dirty draft session.

    The caller (MainWindow) catches this and prompts the user to save,
    discard, or cancel.
    """


class LayerPermissionError(PermissionError):
    """Raised when a plugin attempts to write to a layer category it has not
    declared in its ``permissions.write`` manifest.

    The enforcement point is :meth:`ToolContext.edit_target_scope` and
    :meth:`StageMutationContext.edit_target_scope`.  A plugin with an empty
    ``write`` list (read-only) receives this on ANY write attempt.
    """


# ---------------------------------------------------------------------------
# Context dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ToolContext:
    """Bounded API surface for tool execution.

    Passed to IToolProvider.execute() / poll() / activate() / process_event().
    Plugins never import from app/ or touch StageManager internals directly.

    Callback fields are typed ``Callable[[positional params], return]``.
    Keyword-only parameters and defaults are not part of those types, so a
    change to only those is not caught by the SDK surface check.
    """

    # Read-only access to the composed USD stage
    stage: "Usd.Stage" = None

    # Controlled write operations (not the raw StageManager)
    stage_manager: "StageManagerInterface" = None

    # The plugin that owns this context (set by the framework).
    # Empty string for host (atlas_studio) operations.
    plugin_id: str = ""

    # Currently selected prims
    selection: list = field(default_factory=list)

    # The full multi-selection (shift-click / marquee) as Sdf.Path strings,
    # primary first.  ``selection`` above carries only the primary path;
    # group tools need the whole set (interaction model ticket #269).
    selection_set: list = field(default_factory=list)

    # Replace the multi-selection:
    # ``(paths: Sequence[str], primary: str | None = None) -> None``.
    # Drives the app's SelectionModel so viewport highlight, scene tree
    # and property inspector stay in sync (#269).
    set_selection_set: Optional[Callable[[Sequence[str], Optional[str]], None]] = None

    # Live read of the multi-selection, primary first: ``() -> list[str]``.
    # The ``selection_set`` snapshot above is built once at context
    # construction — a tool that mutates the set mid-session (Shift+Click
    # accumulation, #266) must re-read through this, not the snapshot.
    get_selection_set: Optional[Callable[[], list]] = None

    # Query the ground height at a world position (x, y) → z
    get_ground_height: Optional[Callable[[float, float], float]] = None

    # Check whether (x, y) world coords overlap the ground mesh:
    # ``(x: float, y: float) -> bool``.
    # Returns True when no mesh exists or position is within footprint.
    has_ground_mesh_at: Optional[Callable[[float, float], bool]] = None

    # Surface-mesh Z at (x, y) only: ``(x: float, y: float) -> float | None``.
    # ``None`` when no ground mesh covers the point — no four-pass fallback.
    get_ground_mesh_height: Optional[Callable[[float, float], Optional[float]]] = None

    # Stage-level ground-mesh poll: ``() -> bool`` — is there any ground mesh
    # at all?  The free function takes a stage; this is bound to this
    # context's, so a tool asks ``ctx.has_ground_mesh()`` instead of
    # threading ``ctx.stage`` through it.
    has_ground_mesh: Optional[Callable[[], bool]] = None

    # Build the combined ground-mesh cache for this stage:
    # ``() -> dict | None``.  The KD-tree index a tool builds once per
    # GroundSurface rather than re-scanning the mesh every query.
    build_ground_mesh_cache: Optional[Callable[[], Optional[dict]]] = None

    # Cloud-unit discovery over this stage:
    # ``(roles=None, current_only=False) -> list[CloudUnit]``.  *roles* takes
    # role-name strings — pass ``GEOMETRIC_ROLES`` (from ``core.ports``) to
    # keep only the clouds a geometric derivation may read.
    cloud_units: Optional[Callable[..., list]] = None

    # WGS84 → local ENU over this stage: ``(lat, lon, ele=0.0, *, origin)
    # -> (x, y, z)``.  ``origin`` is a required :class:`SiteOrigin` — ``None``
    # raises ``ValueError``.  There is no default projection frame.
    latlon_to_local_enu: Optional[Callable[..., tuple]] = None

    # Spatial query callbacks (populated by the framework)
    find_nearest_prim: Optional[Callable[[float, float, float], Optional[str]]] = None
    """Find the nearest prim to a world position: ``(x, y, z) -> prim_path_str | None``."""

    find_prims_in_radius: Optional[Callable[[float, float, float, float], list]] = None
    """Find all prims within radius: ``(x, y, z, radius) -> [(path_str, dist), ...]``."""

    # Raycast callbacks
    screen_to_world: Optional[Callable[[float, float, int, int, Any], Any]] = None
    """Convert screen coords to world ray:
    ``(screen_x, screen_y, viewport_w, viewport_h, frustum) -> (origin, direction) | (None, None)``."""

    # Project directory of the currently open map
    project_dir: str = ""

    # Plugin's own preferences (auto-loaded from persisted JSON)
    preferences: dict = field(default_factory=dict)

    # Plugin's own intermediate-file directory (map #318, ticket #323):
    # ``callable() -> str`` — a path that exists, bound to this context's
    # ``plugin_id`` at call time.  Created on demand; the host owns the
    # path, the plugin owns its contents and retention.  Raises
    # ValueError on a host context (empty plugin_id) — core code calls
    # core.platform_paths directly instead.
    plugin_data_dir: Optional[Callable[[], str]] = None

    # "Import this file" door (#334, map #318): run a source file through
    # the host's import pipeline — importer detection, re-import gate,
    # permission check, draft sandbox, SiteOrigin stamp.
    # ``(source_path, options=None) -> dict`` with keys
    # ``result_path`` / ``error`` / ``warnings`` / ``imported``.  The
    # host binds its plugin_id; with no confirm callback the gate
    # refuses (raises ``ImportGateRefused``) when user-authored content
    # is at risk — the job path's clean refusal, never a prompt.
    import_file: Optional[Callable[[str, Any], dict]] = None

    # Streamed point-cloud tile door (core/point_cloud_tiles.py):
    # ``(tile_name, status, crate_path=None, placement=None, *, layer_name)
    # -> prim_path``.  ``layer_name`` is required: the file name of the
    # run's layer under Reality/PointClouds, the same name the run's full
    # import resolves to (``dest_layer_name``), so both share one file.
    # ``tile_name`` is the canonical compass name (``"1W_2N"``, origin
    # ``"0_0"``); ``status`` is provisional | closed | final; ``crate_path``
    # is an optional tile crate file whose ``/PointCloud`` the tile
    # references — Save copies the crate into the project
    # (``Reality/PointClouds/tiles/<run>/``) and re-points the reference at
    # that copy, so the project does not depend on the producer's cache
    # (#352).  Save emits ``StreamedTileCratesCommitted`` (subscribe via
    # this module) once the copies land; the producer may release its crates
    # then, and not before — a discarded or crashed session emits nothing;
    # ``placement`` is an optional 16-float row-major frame →
    # stage matrix (default: the frame keeps identity).  ``z_range`` is an
    # optional ``(min, max)`` metres band for the crate's point extent (needs
    # a crate_path); ``xy_range`` is an optional ``(xmin, ymin, xmax, ymax)``
    # tight footprint that replaces the 20 m tile square in that extent (needs
    # a z_range); omitted, no extent is authored and bounds readers fall back
    # to reading the points.
    # Writes into Reality/PointClouds, gated by the plugin's
    # ``permissions.write``; lands in the draft overlay (reaches disk at
    # Save).  Raises ValueError on a bad name/status.
    upsert_point_cloud_tile: Optional[Callable[[str, str, Any, Any, Any, Any], Any]] = None

    # The consolidation door (#388 design §8): replaces one run's streamed tile
    # frames with a single precise cloud that references the run's consolidated
    # crate.  ``consolidate_point_cloud_run(layer_name, crate_path, *,
    # placement=None, z_range=None, xy_range=None)``.  Both z_range and xy_range
    # are required (they set the cloud's extent).  Other runs are untouched.
    # Refuses a placed write without a georeferenced SiteOrigin, before any
    # write.  Lands in the run's draft (reaches disk at Save).
    consolidate_point_cloud_run: Optional[Callable[[str, str], Any]] = None

    # The discard door for a failed or cancelled run: removes every tile frame
    # of ``layer_name`` and returns the count.  ``discard_point_cloud_run(
    # layer_name)``.  Other runs are untouched.  Lands in the run's draft.
    discard_point_cloud_run: Optional[Callable[[str], Any]] = None

    # Reference to the HydraViewport QOpenGLWidget (for overlay callbacks).
    # Set by the framework — tools can use this to register overlay rendering.
    viewport: object = None

    # Request a viewport repaint after overlay/state changes the host cannot
    # observe (your renderer's output is stale).  The sanctioned door —
    # never poke `viewport` itself (veer/veer-studio-plugin-sdk#7).
    # callable() -> None
    request_viewport_repaint: Optional[Callable[[], None]] = None

    # Phase 4: Register an OverlayRenderer on the viewport's overlay stack.
    # callable(renderer: OverlayRenderer) -> None
    register_overlay: Optional[Callable[[Any], None]] = None

    # Phase 4: Remove an overlay renderer by ID.
    # callable(renderer_id: str) -> None
    unregister_overlay: Optional[Callable[[Any], None]] = None

    # Phase 5: Request a cursor state change.
    # callable(state_name: str) -> None
    request_cursor: Optional[Callable[[str], None]] = None

    # Phase 5: Release this tool's cursor request.
    # callable() -> None
    release_cursor: Optional[Callable[[], None]] = None

    # Phase 7: Show a temporary status bar message.
    # callable(message: str, timeout: int = 3000) -> None
    show_status: Optional[Callable[[str, int], None]] = None

    # Phase 7: Set persistent tool hints in the far-right status bar zone.
    # callable(text: str) -> None — empty string clears.
    set_tool_hints: Optional[Callable[[str], None]] = None

    # Phase 7: Show progress in status-bar zone 5 (overlay zone).
    # callable(text: str, value: int, max_value: int) -> None
    show_progress: Optional[Callable[[str, Any, Any], None]] = None

    # Phase 7: Hide status-bar zone 5.  Call it on completion *and* on
    # failure (#272 §6) — a bar left at 3/7 reads as a hung operation.
    hide_progress: Optional[Callable[[], None]] = None

    # Mesh regeneration (#272 §8) — replace-only, recipe-driven, per-mesh
    # progress through show_progress/hide_progress above.
    # callable(mesh_prim_paths: Sequence[str] | None = None, *,
    #          recipes: Mapping[str, MeshRecipe] | None = None,
    #          extra_border: Mapping[str, Sequence[np.ndarray]] | None = None)
    #     -> list[MeshRegenOutcome]
    # Raises on nothing: one outcome per requested mesh, with status
    # "regenerated" / "no_recipe" / "error".  A Save that sees any "error"
    # refuses the whole Save (#272 §5i).
    regenerate_meshes: Optional[Callable[[Any], Any]] = None

    # Background ground regeneration (#413) — the Accept path's door: the
    # CSF derivation runs as a host job (progress and cancel on the job bar,
    # stage pinned), and the one write lands when it finishes.
    # callable(prim_path: str, *, on_done: Callable[[MeshRegenOutcome], None],
    #          provided: MeshRecipe | None = None,
    #          extra: Sequence[np.ndarray] = (), absorb: Sequence[str] = ())
    #     -> None
    # on_done runs once, on the GUI thread, with "regenerated" / "error" /
    # "no_recipe" / "cancelled".  Raises RuntimeError when another background
    # job holds the slot — then on_done is not called.
    regenerate_mesh_in_job: Optional[Callable[[str], None]] = None

    # Phase 8: Push an undo command onto the global undo stack.
    # callable(command: UndoCommand) -> None
    push_undo: Optional[Callable[[Any], None]] = None

    # Phase 9: The shared gizmo surface (one per viewport).  A tool shows a
    # GizmoSpec on it, hit-tests it, drives a drag, and hides it — the
    # surface owns the handle geometry and drag math.
    # core.ports.GizmoManagerInterface | None
    gizmo_manager: "GizmoManagerInterface" = None

    # Background job service (wayfinder #322) — start/cancel long-running
    # child-process pipelines.  The host owns spawn, progress UI, the
    # cancellation ladder and the stage pin; drivers never spawn processes.
    # None when no service is wired (unit tests).
    jobs: "JobServiceInterface" = None

    # Phase 10 (ticket #49): Register a viewport RMB prim context-menu entry.
    # callable(entry: PrimMenuEntry) -> None
    register_prim_menu_entry: Optional[Callable[[Any], None]] = None

    # Phase 10 (ticket #49): Register a double-click edit-session dispatcher.
    # callable(entry: EditSessionEntry) -> None
    register_edit_session_entry: Optional[Callable[[Any], None]] = None

    # Callback: ask the host to refresh the scene tree after stage mutations.
    # Tools call this after adding sublayers or creating prims so the tree
    # picks up the new data without waiting for a full stage reload.
    request_tree_refresh: Optional[Callable[[], None]] = None

    # Callback: notify the host when the tool selects a different prim.
    # Tools call this so the property inspector / relationship panel update.
    on_selection_changed: Optional[Callable[[Any], None]] = None

    # Callback: show a tool auxiliary dock widget.
    # callable(widget, title: str) -> None
    set_auxiliary_dock: Optional[Callable[[Any, str], None]] = None

    # Callback: hide the tool auxiliary dock.
    # callable() -> None
    clear_auxiliary_dock: Optional[Callable[[], None]] = None

    # Callback: request the framework to deactivate this tool.
    # callable() -> None
    request_deactivate: Optional[Callable[[], None]] = None

    # Callback: snapshot current camera state for later restoration.
    # callable() -> dict
    snapshot_camera: Optional[Callable[[], Any]] = None

    # Callback: restore camera to a previously snapshotted state.
    # callable(state: dict) -> None
    restore_camera: Optional[Callable[[Any], None]] = None

    # Callback: frame the viewport on a prim (camera flies to its bounds).
    # callable(prim_path_str: str) -> None
    frame_prim: Optional[Callable[[str], None]] = None

    # Callback: create an undo checkpoint command for a layer.
    # callable(layer_path: str, description: str, source_id: str) -> UndoCommand
    create_undo_checkpoint: Optional[Callable[[str, str, str], Any]] = None

    # Callback: create a composite undo checkpoint spanning N layers —
    # N ``(layer, before, after)`` triples, one Ctrl+Z reverts them all
    # atomically (Reality write model §7).  Lazy befores: the tool calls
    # ``capture_before(layer)`` immediately before the session's first
    # write to each layer and ``capture_after(layer)`` for every captured
    # layer at commit.  ``revert_to_before(stage_manager)`` is the Cancel
    # door — restore everything, push nothing.
    # callable(description: str, source_id: str) -> UndoCommand
    create_multi_undo_checkpoint: Optional[Callable[[str], Any]] = None

    # Callback: create an undo-aware edit scope (context manager).
    # callable(layer_path: str, description: str, source_id: str) -> EditScope
    # Usage:  with ctx.create_edit_scope(draft_path, "drag vertex") as scope:
    #             scope.track_prim(prim_path)
    #             pts_attr.Set(...)
    create_edit_scope: Optional[Callable[[str, str], Any]] = None

    # -- Assembly wiring (Phase A) -----------------------------------------
    # Get terminal manifest for an assembly prim:
    # ``(prim_path_str) -> list[AssemblyTerminal] | None``.
    # Returns None if the prim has no assembly provider or no terminals.
    get_assembly_terminals: Optional[Callable[[str], Any]] = None

    # -- i18n ------------------------------------------------------------
    # Translate a user-visible string: ``(context, source_text) -> translated_text``.
    translate: Optional[Callable[[str, str], str]] = None

    # Current locale code (e.g. "en", "zh_CN", "ja_JP").
    current_locale: str = "en"

    # -- Spatial query helpers (Phase 1b) ---------------------------------
    # Get the world-space center of a prim:
    # ``(prim_path_str) -> Gf.Vec3d | None``.
    get_world_center: Optional[Callable[[str], Any]] = None

    # -- Atlas schema helpers (Phase 1c) -----------------------------------
    # Check if a prim path is an Atlas object: ``(prim_path_str) -> bool``.
    is_atlas_object: Optional[Callable[[str], bool]] = None

    # Get the AtlasType name of a prim: ``(prim_path_str) -> str | None``.
    get_atlas_type: Optional[Callable[[str], Any]] = None

    # Get the atlas:objectId of a prim: ``(prim_path_str) -> str | None``.
    get_atlas_object_id: Optional[Callable[[str], Optional[str]]] = None

    # Check if a prim is a navigable target: ``(prim_path_str) -> bool``.
    is_navigable_target: Optional[Callable[[str], bool]] = None

    # -- Edit target helper (WS-1 T2) ---------------------------------------
    def edit_target_scope(self, layer_path: str):
        """Context manager that temporarily redirects the edit target.

        Resolves *layer_path* to a ``Sdf.Layer`` via absolute-path matching
        (never substring basename — see WS-1 F3).  Enforces the plugin's
        declared ``permissions.write`` categories — raises
        ``LayerPermissionError`` if the target layer's category is not in
        the plugin's write list.  Also refuses locked layers
        (``permissionToEdit is False``).

        Usage::

            with ctx.edit_target_scope("/path/to/layer.usda"):
                stage.DefinePrim(...)

        The previous edit target is restored on exit, including on exception.
        Use this from plugins rather than hand-rolling ``GetEditTarget`` /
        ``SetEditTarget`` pairs — a missing ``finally`` leaks the edit target
        for the rest of the session.
        """
        sm = getattr(self, 'stage_manager', None)
        project_dir = sm.get_project_dir() if sm else ""
        return _edit_target_scope(
            self.stage, layer_path,
            plugin_id=getattr(self, 'plugin_id', '') or '',
            project_dir=project_dir,
            resolve_origin=(getattr(sm, '_resolve_overlay_origin', None)
                            if sm else None))

    # -- Layer-birth door (#389) --------------------------------------------
    def create_named_category_layer(self, file_name: str,
                                    category: str) -> str | None:
        """Create a category layer file if missing; return its draft overlay.

        The layer-birth door for a run that produces a new project layer —
        a retouch run's derived-cloud ``.usdc`` (#389).  Creates
        ``<category>/<file_name>`` when missing, wires it into the root
        sublayers, and returns the draft overlay path: the same sandbox
        ``ensure_editable_category`` hands back, so the caller authors
        through the draft and Save merges it into the original.

        Enforces this context's plugin ``permissions.write`` with the
        *plugin_id stamped at call time* — the same late binding
        ``plugin_data_dir`` and ``import_file`` rely on.  *file_name*
        must be a bare file name; a nested path raises ``ValueError``
        inside the stage manager.
        """
        plugin_id = getattr(self, 'plugin_id', '') or 'root'
        _check_write_permission(plugin_id, category)
        sm = getattr(self, 'stage_manager', None)
        if sm is None:
            raise RuntimeError("no stage manager — cannot birth a layer")
        draft = sm.ensure_named_category_layer(category, file_name)
        if draft is None:
            raise RuntimeError(
                "no draft session is active — open a project first")
        return draft

    # -- Stage pin door (sdk#1, owner ruling 2026-11-14) --------------------
    def stage_pin_exempt(self):
        """The pin's one door: this context's authoring while a job holds it.

        Returns a context manager.  With no pin in force it is a no-op
        yield — there is nothing to bypass.  While a background job runs
        (:mod:`core.stage_pin`, wayfinder #322), it yields only when this
        context's ``plugin_id`` is the job's owner (``JobSpec.plugin_id``);
        anyone else gets ``StagePinnedError`` naming the holder.

        The gate is ownership, not a declared permission: the key exists
        only while *your own* job runs, so a plugin can never open the
        lock on someone else's write.  This method replaces the old
        module-level ``core.contexts.stage_pin_exempt`` re-export, which
        handed the raw door to every caller.
        """
        from core import stage_pin
        return stage_pin.exempt_for(getattr(self, 'plugin_id', '') or '')


@dataclass
class PanelContext:
    """Bounded API surface for panel creation.

    Passed to IPanelFactory.create_panel().  Provides stage access plus
    change-notification signals so panels can react to user actions.
    """

    stage: "Usd.Stage" = None
    stage_manager: "StageManagerInterface" = None
    project_dir: str = ""
    preferences: dict = field(default_factory=dict)

    # The owning plugin's intermediate-file directory (map #318, ticket
    # #323): ``callable() -> str`` — a path that exists, bound to the
    # panel factory's ``plugin_id`` at build time.  Same contract as
    # ``ToolContext.plugin_data_dir``.
    plugin_data_dir: Optional[Callable] = None

    # Signals to subscribe to (set by the framework at panel creation time).
    # Each is a callable that accepts a callback, e.g.:
    #   context.on_selection_changed(lambda sel: print(sel))
    on_selection_changed: Optional[Callable] = None
    on_stage_changed: Optional[Callable] = None
    on_viewport_changed: Optional[Callable] = None

    # -- i18n ------------------------------------------------------------
    translate: Optional[Callable] = None
    """Translate a user-visible string: ``(context, source_text) -> translated_text``."""

    current_locale: str = "en"
    """Current locale code (e.g. ``"en"``, ``"zh_CN"``, ``"ja_JP"``)."""

    # -- Undo ------------------------------------------------------------
    push_undo: Optional[Callable] = None
    """Push an ``UndoCommand`` onto the global undo stack.

    Call signature: ``(command: UndoCommand) -> None``.

    Panels use this with ``LayerCheckpointCommand`` to make attribute edits
    undoable via Ctrl+Z.
    """


@dataclass
class EditorContext:
    """Bounded API surface for Properties-panel section bodies.

    Passed to a section provider's ``sections()`` and to its
    ``widget_factory`` (``IInspectorSectionProvider``).  Provides stage
    access plus a request_refresh callback so the body can trigger
    viewport repaints.
    """

    stage: "Usd.Stage" = None
    stage_manager: "StageManagerInterface" = None

    # Tell the viewport to repaint (after property changes)
    request_refresh: Optional[Callable] = None

    # -- i18n ------------------------------------------------------------
    translate: Optional[Callable] = None
    """Translate a user-visible string: ``(context, source_text) -> translated_text``."""

    # -- Undo ------------------------------------------------------------
    push_undo: Optional[Callable] = None
    """Push an ``UndoCommand`` onto the global undo stack.

    Call signature: ``(command: UndoCommand) -> None``.

    Editors use this with ``LayerCheckpointCommand`` to make their attribute
    edits undoable via Ctrl+Z — the same contract ``PanelContext`` offers.
    """

    # -- Selection -------------------------------------------------------
    select_prim: Optional[Callable] = None
    """Make a prim the selection, so the Properties panel and the viewport
    follow it: ``(path: Sdf.Path) -> None``.  A regulatory element's member
    rows use it to hand the selection to the member prim (map #433)."""

    hover_prim: Optional[Callable] = None
    """Highlight a prim's bounding box in the viewport while a row naming it is
    hovered: ``(path: Sdf.Path) -> None``, with the empty path to clear.  The
    same hover box the scene tree and the Relationships panel draw."""

    # -- Active tool -------------------------------------------------------
    active_tool_id: Optional[Callable[[], Optional[str]]] = None
    """The id of the currently active interactive tool, or ``None`` when no
    tool is active: ``() -> str | None``.  A callable, read at use time — a
    value frozen when the context was built would go stale on the first
    tool switch, and an action button must always reflect the live state
    (#456)."""

    activate_tool: Optional[Callable[[str], None]] = None
    """Activate a tool by id with **exclusive** semantics (#456, owner
    ruling 2026-11-04): the requested tool is started, and the request is
    *refused while another tool is active* — a panel-launched special
    editor never ends the tool the user is working in; it fails instead,
    with the holder named on the status bar.  No-op when the id names no
    known tool.  Activation can still be refused (poll gate, operation
    lock, background job) — callers confirm through
    :attr:`active_tool_id` afterwards."""


@dataclass
class StageMutationContext:
    """Transaction guard for safe prim mutations during reactive callbacks.

    Passed to ``IFusionPlugin.on_mutation()`` so the plugin can author new
    attributes and relationships onto the same edit target that received the
    triggering mutation.

    All writes through this context are grouped into a single USD change
    block so they appear as one undoable operation.  The spatial query
    callbacks prevent plugins from needing to traverse the stage themselves.
    """

    stage: "Usd.Stage" = None
    """The composed stage (read-only for context)."""

    stage_manager: "StageManagerInterface" = None
    """Controlled write interface."""

    plugin_id: str = ""
    """The plugin that owns this context.  Set by the framework.
    Empty string for host (atlas_studio) operations."""

    edit_target_layer_path: str = ""
    """The layer path that received the triggering mutation.
    All new writes through this context go to this layer."""

    triggering_prim_path: str = ""
    """The Sdf.Path string of the prim that triggered the mutation."""

    originator_id: str = ""
    """Plugin ``fusion_id`` of the code that triggered this mutation.

    Fusion plugins check this against their own ``fusion_id`` and return
    early if they match — this prevents infinite event loops when a fusion
    plugin's writes cascade back into the mutation notification system.

    Set to ``""`` (empty string) for user-initiated mutations.  Only set
    to a non-empty value when a fusion plugin triggers another mutation.
    """

    # Spatial query callbacks
    get_ground_height: Optional[Callable] = None
    """Query the ground height at a world position: ``(x, y) -> z``."""

    find_nearest_prim: Optional[Callable] = None
    """Find the nearest prim to a world position: ``(x, y, z) -> prim_path_str``."""

    find_prims_in_radius: Optional[Callable] = None
    """Find all prims within radius: ``(x, y, z, radius) -> [(path_str, dist), ...]``."""

    # -- i18n ------------------------------------------------------------
    translate: Optional[Callable] = None
    """Translate a user-visible string: ``(context, source_text) -> translated_text``."""

    # -- Atlas schema helpers -----------------------------------------------
    is_atlas_object: Optional[Callable] = None
    """Check if a prim path is an Atlas object: ``(prim_path_str) -> bool``."""

    is_navigable_target: Optional[Callable] = None
    """Check if a prim is a navigable target: ``(prim_path_str) -> bool``."""

    # -- Edit target helper (WS-1 T2) ---------------------------------------
    def edit_target_scope(self, layer_path: str):
        """Context manager that temporarily redirects the edit target.

        Resolves *layer_path* to a ``Sdf.Layer`` via absolute-path matching
        (never substring basename — see WS-1 F3).  Enforces the plugin's
        declared ``permissions.write`` categories — raises
        ``LayerPermissionError`` if the target layer's category is not in
        the plugin's write list.  Also refuses locked layers
        (``permissionToEdit is False``).

        Usage::

            with ctx.edit_target_scope("/path/to/layer.usda"):
                stage.DefinePrim(...)

        The previous edit target is restored on exit, including on exception.
        Use this from plugins rather than hand-rolling ``GetEditTarget`` /
        ``SetEditTarget`` pairs — a missing ``finally`` leaks the edit target
        for the rest of the session.
        """
        sm = getattr(self, 'stage_manager', None)
        project_dir = sm.get_project_dir() if sm else ""
        return _edit_target_scope(
            self.stage, layer_path,
            plugin_id=getattr(self, 'plugin_id', '') or '',
            project_dir=project_dir,
            resolve_origin=(getattr(sm, '_resolve_overlay_origin', None)
                            if sm else None))


@dataclass
class ToolEvent:
    """Framework-level input event for modal / interactive tools.

    Wraps Qt events so plugins don't depend on Qt directly.
    The framework translates QMouseEvent / QKeyEvent → ToolEvent before
    passing to IToolProvider.process_event().
    """

    type: str = ""
    """Event type: 'mouse_press', 'mouse_release', 'mouse_move',
    'mouse_double_click', 'key_press', 'key_release', or 'timer'."""

    position: tuple = (0, 0)
    """(x, y) in viewport pixel coordinates."""

    world_position: Optional[tuple] = None
    """(x, y, z) in world coordinates if ground intersection is available,
    otherwise None."""

    key: str = ""
    """Key name if this is a key event, e.g. 'Escape', 'Return', 'A'."""

    modifiers: set = field(default_factory=set)
    """Modifier keys held during the event: {'shift', 'ctrl', 'alt'}."""

    button: str = ""
    """Mouse button if this is a mouse event: 'left', 'right', 'middle'."""

    is_accepted: bool = False
    """Set to True to stop event propagation to other handlers."""

    is_auto_repeat: bool = False
    """True for an OS key-repeat event (the key is still held).  Qt sends a
    release+press pair per repeat on X11/Wayland, so a hold-to-move tool must
    ignore these or its motion stops and restarts on every repeat."""


# ---------------------------------------------------------------------------
# StageManagerInterface — controlled API surface for plugins
# ---------------------------------------------------------------------------


class StageManagerInterface(ABC):
    """Controlled view of StageManager that plugins receive.

    This is a subset of StageManager's full API — only the operations
    that plugins are allowed to perform.  Plugins never get the raw
    StageManager object, so they cannot accidentally corrupt stage state.

    All methods use only standard-library types in their signatures so
    the module imports without pxr.
    """

    @abstractmethod
    def add_sublayer(self, layer_path: str, position: int = -1) -> None:
        """Add a sublayer to the stage.

        Args:
            layer_path: Absolute or relative path to the .usda/.usdc file.
            position: Insertion index in the sublayer stack.
                      -1 (default) appends at the bottom, 0 prepends at the top.
        """

    @abstractmethod
    def set_edit_target(self, layer_path: str) -> None:
        """Set the edit target to a specific sublayer.

        All subsequent prim mutations (creation, attribute authoring) will
        be written to this layer.
        """

    @abstractmethod
    def save_layer(self, layer_path: str) -> None:
        """Save a specific layer to disk."""

    @abstractmethod
    def save_stage(self) -> None:
        """Save all dirty layers in the stage."""

    @abstractmethod
    def get_stage(self) -> "Usd.Stage":
        """Get the composed stage (read-only access).

        Returns:
            The Usd.Stage, or None if no stage is open.
        """

    @abstractmethod
    def get_layer_paths(self) -> list[str]:
        """Get the ordered list of sublayer paths in the stage's root layer."""

    @abstractmethod
    def get_layer_by_identifier(self, identifier: str):
        """Return the ``Sdf.Layer`` for *identifier*, or ``None``.

        Used by ``LayerCheckpointCommand.undo()`` / ``redo()`` to locate
        the layer to restore.
        """

    @abstractmethod
    def get_project_dir(self) -> str:
        """Get the project directory path (parent of the root .usda file).

        Returns:
            Absolute path to the project directory, or '' if no stage is open.
        """

    @abstractmethod
    def notify_prims_modified(self, prim_paths: list[str]) -> None:
        """Notify the framework that prims have been modified by tools.

        Called by tools (spline editor, regulatory placer, etc.) when they
        write to USD prims outside the normal Atlas CRUD flow.  The
        framework forwards these to fusion plugin notification.

        Args:
            prim_paths: List of ``Sdf.Path`` strings for modified prims.
        """

    # -- Spatial queries (delegated from core utility modules) -----------

    @abstractmethod
    def find_point_cloud(self):
        """Find the primary point cloud Points prim on the stage.

        Returns the leaf ``UsdGeom.Points`` prim, or None if no point
        cloud exists.  Wraps ``core.prim_utils.find_point_cloud``.
        """

    @abstractmethod
    def find_all_point_clouds(self) -> list:
        """Find all point cloud Points prims on the stage.

        Returns a list of ``Usd.Prim`` objects (leaf ``Points`` prims),
        ordered by discovery.  Wraps ``core.prim_utils.find_all_point_clouds``.
        """

    @abstractmethod
    def find_point_cloud_frame(self):
        """Find the Xform container that wraps the point cloud.

        Returns the ``/PointCloudFrame`` Xform prim, or None.  Wraps
        ``core.prim_utils.find_point_cloud_frame``.
        """

    @abstractmethod
    def get_ground_height_at(self, x: float, y: float) -> float:
        """Query ground height at a stage position (x, y).

        Returns the ground Z value in stage-native coordinates.
        Wraps ``core.raycast.get_ground_height_at``.
        """

    @abstractmethod
    def has_ground_mesh(self) -> bool:
        """Return True if the stage has a populated ground mesh.

        Wraps ``core.raycast.has_ground_mesh``.
        """

    @abstractmethod
    def read_site_origin(self):
        """Read the SiteOrigin from the stage's root layer, or None.

        Returns a ``SiteOrigin`` dataclass or None if no origin is stamped.
        Wraps ``core.site_origin.read_site_origin``.
        """

    @abstractmethod
    def create_atlas_prim(self, atlas_type_name: str, position, **kwargs) -> str:
        """Create a new Atlas object prim on the stage.

        Args:
            atlas_type_name: String name of the AtlasType enum member
                (e.g. ``"BUILDING"``).  Navigation regulatory elements
                (traffic lights, stop signs, …) are not Atlas objects —
                create those through the ``nav`` library instead.
            position: ``Gf.Vec3d`` world position for the prim.
            **kwargs: Additional attributes forwarded to
                ``core.atlas_schema.create_atlas_prim``.

        Returns:
            The ``Sdf.Path`` string of the newly created prim.

        Wraps ``core.atlas_schema.create_atlas_prim``.
        """

    @abstractmethod
    def mark_dirty(self) -> None:
        """Mark the stage as having unsaved changes.

        Called by property editors after the user modifies attributes,
        so the framework prompts to save on close.
        """

    @abstractmethod
    def is_dirty(self) -> bool:
        """True if any draft overlay has been modified since last commit."""

    @abstractmethod
    def has_unsaved_layers(self) -> bool:
        """True if Save would write anything (dirty project layers or the
        knowledge store).  The title-bar dot and the close-prompt share this
        single signal so they can never disagree with Save."""

    @abstractmethod
    def create_checkpoint(self, label: str = "") -> str:
        """Snapshot all dirty draft layers. Returns a checkpoint token.

        Called automatically on tool deactivation and before long
        operations.  Tools can also request a checkpoint explicitly.
        """

    @abstractmethod
    def mark_dirty_layer(self, layer_id: str = None) -> None:
        """Mark a specific layer (or the default edit-target layer) as
        having uncommitted draft changes.  The framework handles
        persistence timing.
        """

    @abstractmethod
    def get_draft_layer_path(self, original_path: str) -> str | None:
        """Return the draft (sandbox) layer path for *original_path*.

        If a draft overlay exists for the given original layer, returns
        the absolute path to the draft file in the session temp directory.
        Returns ``None`` if no draft session is active or if *original_path*
        is not under draft management.
        """

    def ensure_draft_overlay(self, original_path: str) -> str | None:
        """Lazily create (or return existing) draft overlay for *original_path*.

        Unlike :meth:`get_draft_layer_path` (which only returns an existing
        overlay or ``None``), this creates the overlay + scaffold if needed
        and wires the subLayerPaths entry so the layer becomes visible to the
        stage.  Returns the overlay path, or ``None`` if no draft session is
        active.

        Tools that write to a layer that may not have an overlay yet (e.g. the
        road mesh tool creating ``Reality/Meshes/RoadSurface_<id>.usda``)
        should call this instead of ``get_draft_layer_path``.
        """

    @abstractmethod
    def save_draft_overlays(self) -> int:
        """Save all in-memory draft overlays to disk for crash protection.

        Call this at tool-finish boundaries so the draft overlay files on disk
        reflect the current in-memory state.  Returns the number saved.
        """

    @abstractmethod
    def is_draft_path(self, layer_path: str) -> bool:
        """Return True if *layer_path* is inside the active draft session.

        Used by tools to detect draft-of-draft patterns: when a layer path
        already lives in the draft cache, callers should set the edit target
        directly rather than creating another overlay on top.
        """

    @abstractmethod
    def ensure_editable_layer(self, layer_path: str) -> str | None:
        """Ensure *layer_path* has a writable draft overlay, overriding read_only.

        Unlike :meth:`ensure_draft_overlay`, this works even for layers
        classified as read_only (e.g. Reference data).  The layer's strategy
        is promoted to ``draft_overlay``, a draft overlay is created lazily,
        and the overlay path is wired into subLayerPaths so writes land in
        the draft.

        Returns the draft overlay path, or None if no draft session is active
        or the layer cannot be made editable.
        """

    @abstractmethod
    def ensure_editable_category(self, category: str) -> str | None:
        """Ensure the layer for *category* has a writable draft overlay.

        *category* is a directory name like ``"Reference"`` or ``"Navigation"``.
        Scans ``subLayerPaths`` for a matching layer
        (including cache-path fallback for crash recovery), creates a draft
        overlay via :meth:`ensure_editable_layer`, sets the edit target, and
        returns the draft path.

        Returns ``None`` if no matching layer is found or no draft session is
        active.  Tools call this once on activation instead of manually
        implementing the discovery + fallback chain.
        """

    @abstractmethod
    def ensure_named_category_layer(self, category: str,
                                    file_name: str) -> str | None:
        """Draft overlay for the layer *file_name* directly under *category*.

        Creates the layer file and wires it into the root sublayers when it
        is missing, the same way the category bootstrap does, then returns
        its draft overlay path.  Refuses a name that would not be one of the
        category's own layers (a bare file name only).  Returns ``None``
        without a draft session.

        This is the layer-birth door behind
        :meth:`ToolContext.create_named_category_layer` — the permission
        check lives there; this method is the stage-manager mechanism.
        """

    @abstractmethod
    def ensure_editable_prim(self, prim_path: str) -> str | None:
        """Make the layer that owns *prim_path* writable and return the draft path.

        Finds the strongest non-anonymous layer in the prim's opinion stack,
        creates a draft overlay for it via :meth:`ensure_editable_layer`, and
        returns the draft path.  Does NOT change the edit target — the caller
        does that.

        This is the one-liner that replaces the GetPrimStack → realPath →
        ensure_editable_layer dance that every tool that mutates prims outside
        ``site_objects.usda`` was duplicating.

        Returns ``None`` if the prim is invalid, no owning layer is found, or
        no draft session is active.
        """

    @abstractmethod
    def delete_prim(self, prim_path: str, plugin_id: str = "",
                    checkpoint=None) -> bool:
        """Delete a prim from the stage, out of every layer holding a spec.

        Routes every spec layer through the session's draft overlay when
        one is live (the delete reverts with Discard and reaches disk
        only at Save), removes the prim from every layer naming it
        (CLAUDE.md #61), and marks the stage dirty.  The *plugin_id* is
        checked against the declared ``permissions.write`` categories of
        every spec layer before the first write.

        This is the single choke-point for prim deletion from plugins and
        framework code alike — no caller should call ``stage.RemovePrim()``
        directly.

        *checkpoint* — optional undo command
        (``LayerCheckpointCommand`` / ``MultiLayerCheckpointCommand``);
        the layer that receives each write is snapshotted before it
        changes, so wrapping a user-visible operation in one bracket
        makes the whole delete one undo step (#55).

        Returns ``True`` if the prim left composition, ``False`` if the
        prim doesn't exist or no layer could be edited.
        """


# ---------------------------------------------------------------------------
# Internal helpers for edit_target_scope permission checks (WS-1 F5)
# ---------------------------------------------------------------------------

def _resolve_category_for_layer(
    layer_path: str, root_layer, project_dir: str,
) -> str | None:
    """Resolve a layer path to its category token for permission checks.

    Converts absolute or project-relative paths to the form
    ``category_for_path`` expects (e.g. ``"Reference"``,
    ``"Reality/PointClouds"``).
    """
    import os

    from core.layer_discovery import category_for_path

    # If it's already a project-relative path (starts with ./ or is a
    # bare category prefix), use it directly.
    rel = layer_path
    if os.path.isabs(layer_path) and project_dir:
        try:
            rel = os.path.relpath(layer_path, project_dir)
        except ValueError:
            return None
    return category_for_path(rel)


def _check_write_permission(plugin_id: str, category: str) -> None:
    """Raise ``LayerPermissionError`` if *plugin_id* may not write to *category*.

    Looks up the plugin's declared ``permissions.write`` list via the
    global plugin registry.  An empty write list means read-only — any
    write raises.  An absent category in the list raises.

    Does NOT raise when *plugin_id* is ``"root"`` (host operations have
    full access).  Raises ``ValueError`` when *plugin_id* is empty —
    callers must explicitly declare their identity.
    """
    if not plugin_id:
        raise ValueError(
            "plugin_id must not be empty — use 'root' for host operations "
            "or the registered plugin name for plugin operations")

    if plugin_id == "root":
        return  # host operation — full access

    if _plugin_registry is None:
        return  # no registry set yet — allow (startup/bootstrap)

    write_list = _plugin_registry.get_permissions(plugin_id).get("write", [])
    if not write_list:
        raise LayerPermissionError(
            f"Plugin '{plugin_id}' is read-only (permissions.write is empty) "
            f"— cannot write to category '{category}'."
        )
    if "*" in write_list:
        return  # wildcard — all categories permitted
    if category not in write_list:
        raise LayerPermissionError(
            f"Plugin '{plugin_id}' does not have permission to write to "
            f"category '{category}'.  Declared write categories: {write_list}"
        )


_plugin_registry = None  # type: ignore
"""Set by the application layer after the plugin registry is created.
Used by ``_check_write_permission`` for layer-boundary enforcement."""


def set_plugin_registry(registry) -> None:
    """Set the global plugin registry for permission checks.

    Called by the application layer (MainWindow) after creating the
    ``PluginRegistry`` instance.
    """
    global _plugin_registry
    _plugin_registry = registry


def _edit_target_scope(stage, layer_path: str, plugin_id: str = "",
                       project_dir: str = "", resolve_origin=None):
    """Shared implementation for both ``ToolContext`` and ``StageMutationContext``.

    Resolves *layer_path* to a ``Sdf.Layer`` via absolute-path matching (F3),
    checks ``permissionToEdit`` (F2) and category-level permissions (F5), then
    returns a ``Usd.EditContext`` that restores the previous edit target on exit.

    *resolve_origin* maps a draft-overlay path back to the project layer it
    overlays (``StageManager._resolve_overlay_origin``).  A draft lives in the
    cache tree, so its own path has no category; its origin does, and that is
    the category the manifest check must run against.
    """
    import contextlib
    import os

    from pxr import Sdf, Usd

    from core import stage_pin

    if not stage:
        @contextlib.contextmanager
        def _noop():
            yield
        return _noop()

    # Stage pin (wayfinder #322): no edit-scope acquisition while a
    # background job owns the stage — the single write gate refuses before
    # any permission/unlock work happens.
    stage_pin.check_unpinned("edit_target_scope")

    root = stage.GetRootLayer()
    target_abs = os.path.normpath(root.ComputeAbsolutePath(layer_path))
    target = None
    for sp in root.subLayerPaths:
        resolved = root.ComputeAbsolutePath(sp)
        if os.path.normpath(resolved) == target_abs:
            target = Sdf.Layer.FindOrOpen(resolved)
            break
    if target is None and os.path.exists(layer_path):
        target = Sdf.Layer.FindOrOpen(layer_path)
    if target is None:
        raise ValueError(f"Layer not found: {layer_path}")

    # Permission check via plugin manifest.  If the plugin is authorised
    # for this layer's category, unlock it via USD's native
    # SetPermissionToEdit so that attr.Set() / stage.DefinePrim() succeed.
    # Without this call the layer stays locked (lock_all_layers runs at
    # stage-open time) and USD itself rejects every write.
    if plugin_id:
        category = _resolve_category_for_layer(layer_path, root, project_dir)
        if category is None and resolve_origin is not None:
            origin = resolve_origin(layer_path)
            if origin:
                category = _resolve_category_for_layer(origin, root,
                                                       project_dir)
        if category is None:
            # Fails closed (#334).  Skipping the check left the layer
            # write-locked anyway, so the write failed at the USD level
            # with a confusing error; refuse with the real reason.
            raise LayerPermissionError(
                f"Cannot resolve a category for layer '{layer_path}' — "
                "refusing the write rather than skipping the permission "
                "check.")
        _check_write_permission(plugin_id, category)
        # Manifest check passed — unlock this layer so writes succeed.
        try:
            target.SetPermissionToEdit(True)
        except Exception:
            pass

    return Usd.EditContext(stage, target)
