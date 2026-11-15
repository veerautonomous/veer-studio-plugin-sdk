"""Mock context factories for plugin testing.

Creates :class:`ToolContext`, :class:`PanelContext`, and :class:`EditorContext`
instances pre-populated with sensible defaults (mock stage manager, in-memory
stage, etc.) so plugin tests don't need to construct them manually.

Every context field is overridable via ``**overrides`` — only pass what your
test needs to customize.

**What the defaults are.**  Context callbacks fall into three classes:

- **Queries** answer a question about state and change nothing.  The
  defaults give *empty-world* answers — the mock stage has no ground mesh
  and no clouds, so ``has_ground_mesh()`` is ``False``, ``cloud_units()``
  is ``[]``, and so on.  They are honest about the stage they are handed;
  tests that need a live scenario override them.
- **Notify** callbacks tell the host something happened (status, cursor,
  overlay, selection).  Their defaults are silent no-ops: the call never
  raises, and records nothing — a test that wants to assert on them
  overrides with its own spy.
- **Write** doors mutate the stage, layers, or project on disk and are
  gated by permissions.  They are deliberately left ``None`` so a unit
  test that reaches one fails loudly instead of silently writing.

Usage::

    from veer_plugin_sdk.testing import tool_context

    def test_my_tool():
        ctx = tool_context()
        assert ctx.stage is not None
        assert ctx.stage_manager is not None
        assert ctx.show_status is not None      # notify → silent no-op
        assert ctx.push_undo is None            # write → unwired on purpose
"""

from __future__ import annotations

import tempfile
from typing import Optional

from veer_plugin_sdk import (
    ToolContext, PanelContext, EditorContext, StageMutationContext,
)

__all__ = [
    "tool_context", "panel_context", "editor_context", "mutation_context",
]


def _noop(*_args, **_kwargs) -> None:
    """Default for every notify callback: accept anything, do nothing."""


def _translate(msgctxt: str, text: str) -> str:
    """Default ``translate``: the source text, untranslated (locale is ``en``)."""
    return text


def tool_context(**overrides) -> ToolContext:
    """Build a :class:`ToolContext` with sensible defaults for testing.

    Defaults:

        - *stage*: in-memory stage with ``/World/Assets`` (from :func:`mock_stage.create_stage`)
        - *stage_manager*: :class:`MockStageManager` instance
        - *selection* / *selection_set*: empty list
        - *project_dir*: ``""``
        - *preferences*: empty dict
        - *plugin_data_dir*: one fresh temp directory **per context** — the
          same path on every call, matching the host contract
        - *queries*: empty-world answers — ``has_ground_mesh → False``,
          ``has_ground_mesh_at → True`` (the host returns ``True`` when no
          mesh exists), ``get_ground_mesh_height → None``,
          ``build_ground_mesh_cache → None``, ``cloud_units → []``,
          ``get_ground_height → 0.0``, ``find_nearest_prim → None``,
          ``find_prims_in_radius → []``, ``screen_to_world → (None, None)``,
          ``get_selection_set → []``, ``get_world_center → None``,
          ``is_atlas_object / is_navigable_target → False``,
          ``get_atlas_type / get_atlas_object_id / get_assembly_terminals → None``,
          ``snapshot_camera → {}``
        - *i18n*: ``translate`` returns the source text; ``current_locale``
          stays ``"en"``
        - *notify*: silent no-ops — ``register_overlay``,
          ``unregister_overlay``, ``request_cursor``, ``release_cursor``,
          ``show_status``, ``set_tool_hints``, ``show_progress``,
          ``hide_progress``, ``request_tree_refresh``,
          ``on_selection_changed``, ``set_selection_set``,
          ``set_auxiliary_dock``, ``clear_auxiliary_dock``,
          ``request_deactivate``, ``restore_camera``, ``frame_prim``,
          ``register_prim_menu_entry``, ``register_edit_session_entry``
        - *write doors*: left ``None`` on purpose — ``import_file``,
          ``push_undo``, ``create_edit_scope``, ``create_undo_checkpoint``,
          ``create_multi_undo_checkpoint``, ``regenerate_meshes``,
          ``regenerate_mesh_in_job``, ``upsert_point_cloud_tile``,
          ``consolidate_point_cloud_run``, ``discard_point_cloud_run``
        - ``latlon_to_local_enu`` raises :class:`NotImplementedError` — the
          projection door is ruled separately (gitea
          ``veer-studio-plugin-sdk#11``); override it with your projection
        - ``viewport`` / ``gizmo_manager`` / ``jobs`` stay ``None`` (host
          objects; not mocked)

    Every field can be overridden by passing it as a keyword argument.

    Args:
        **overrides: Keyword arguments to override context fields.

    Returns:
        A fully-populated ToolContext ready for tool testing.
    """
    from .mock_stage import create_stage
    from .mock_stage_manager import MockStageManager

    # One data root per context: the host returns the same path on every
    # call (core/contexts.py plugin_data_dir contract), so a fresh mkdtemp
    # per call would scatter one test's writes across directories.
    data_dir = tempfile.mkdtemp(prefix="veer-studio-test-plugin-data-")

    def _mock_get_ground_height(x: float, y: float) -> float:
        return 0.0

    def _mock_find_nearest_prim(x: float, y: float, z: float) -> Optional[str]:
        return None

    def _mock_find_prims_in_radius(x: float, y: float, z: float, radius: float):
        return []

    def _mock_screen_to_world(screen_x, screen_y, viewport_w, viewport_h, frustum):
        return (None, None)

    def _mock_has_ground_mesh() -> bool:
        return False

    def _mock_has_ground_mesh_at(x: float, y: float) -> bool:
        # Host contract (core/raycast.py): no mesh → True, nothing to
        # filter against; False only when a mesh exists and is elsewhere.
        return True

    def _mock_get_ground_mesh_height(x: float, y: float) -> Optional[float]:
        return None

    def _mock_build_ground_mesh_cache() -> Optional[dict]:
        return None

    def _mock_cloud_units(roles=None, current_only=False):
        return []

    def _mock_get_world_center(prim_path):
        return None

    def _mock_get_atlas_type(prim_path):
        return None

    def _mock_get_atlas_object_id(prim_path):
        return None

    def _mock_get_assembly_terminals(prim_path):
        return None

    def _mock_snapshot_camera() -> dict:
        return {}

    def _mock_plugin_data_dir() -> str:
        return data_dir

    def _mock_latlon_to_local_enu(lat, lon, ele=0.0, *, origin):
        raise NotImplementedError(
            "latlon_to_local_enu is not wired in veer_plugin_sdk.testing; "
            "override it with your projection "
            "(http://gitea.local/veer/veer-studio-plugin-sdk/issues/11)"
        )

    defaults = {
        # -- stage / selection --------------------------------------------
        "stage": create_stage(),
        "stage_manager": MockStageManager(),
        "selection": [],
        "selection_set": [],
        "project_dir": "",
        "preferences": {},
        "plugin_data_dir": _mock_plugin_data_dir,
        # -- queries: empty world -----------------------------------------
        "get_ground_height": _mock_get_ground_height,
        "find_nearest_prim": _mock_find_nearest_prim,
        "find_prims_in_radius": _mock_find_prims_in_radius,
        "screen_to_world": _mock_screen_to_world,
        "has_ground_mesh": _mock_has_ground_mesh,
        "has_ground_mesh_at": _mock_has_ground_mesh_at,
        "get_ground_mesh_height": _mock_get_ground_mesh_height,
        "build_ground_mesh_cache": _mock_build_ground_mesh_cache,
        "cloud_units": _mock_cloud_units,
        "get_selection_set": lambda: [],
        "get_world_center": _mock_get_world_center,
        "is_atlas_object": lambda prim_path: False,
        "get_atlas_type": _mock_get_atlas_type,
        "get_atlas_object_id": _mock_get_atlas_object_id,
        "is_navigable_target": lambda prim_path: False,
        "get_assembly_terminals": _mock_get_assembly_terminals,
        "snapshot_camera": _mock_snapshot_camera,
        "latlon_to_local_enu": _mock_latlon_to_local_enu,
        # -- i18n -----------------------------------------------------------
        "translate": _translate,
        # -- notify: silent no-ops -----------------------------------------
        "set_selection_set": _noop,
        "register_overlay": _noop,
        "unregister_overlay": _noop,
        "request_cursor": _noop,
        "release_cursor": _noop,
        "show_status": _noop,
        "set_tool_hints": _noop,
        "show_progress": _noop,
        "hide_progress": _noop,
        "request_tree_refresh": _noop,
        "on_selection_changed": _noop,
        "set_auxiliary_dock": _noop,
        "clear_auxiliary_dock": _noop,
        "request_deactivate": _noop,
        "restore_camera": _noop,
        "frame_prim": _noop,
        "register_prim_menu_entry": _noop,
        "register_edit_session_entry": _noop,
        # -- write doors: left None on purpose (import_file, push_undo,
        #    create_edit_scope, create_*_undo_checkpoint, regenerate_*,
        #    upsert_point_cloud_tile, consolidate/discard_point_cloud_run)
        # -- host objects: left None on purpose (viewport, gizmo_manager, jobs)
    }
    defaults.update(overrides)
    return ToolContext(**defaults)


def panel_context(**overrides) -> PanelContext:
    """Build a :class:`PanelContext` with sensible defaults for testing.

    Defaults:
        - *stage*: in-memory stage with ``/World/Assets``
        - *stage_manager*: :class:`MockStageManager` instance
        - *project_dir*: ``""``
        - *preferences*: empty dict
        - *plugin_data_dir*: one fresh temp directory **per context** (same
          path on every call, as the host contract requires)
        - *translate*: returns the source text (``current_locale`` stays ``"en"``)
        - *notify*: silent no-ops — ``on_selection_changed``,
          ``on_stage_changed``, ``on_viewport_changed``
        - *write door*: ``push_undo`` stays ``None`` on purpose

    Every field can be overridden by passing it as a keyword argument.

    Args:
        **overrides: Keyword arguments to override context fields.

    Returns:
        A fully-populated PanelContext ready for panel factory testing.
    """
    from .mock_stage import create_stage
    from .mock_stage_manager import MockStageManager

    data_dir = tempfile.mkdtemp(prefix="veer-studio-test-plugin-data-")

    def _mock_plugin_data_dir() -> str:
        return data_dir

    defaults = {
        "stage": create_stage(),
        "stage_manager": MockStageManager(),
        "project_dir": "",
        "preferences": {},
        "plugin_data_dir": _mock_plugin_data_dir,
        "translate": _translate,
        "on_selection_changed": _noop,
        "on_stage_changed": _noop,
        "on_viewport_changed": _noop,
    }
    defaults.update(overrides)
    return PanelContext(**defaults)


def editor_context(**overrides) -> EditorContext:
    """Build an :class:`EditorContext` with sensible defaults for testing.

    Defaults:
        - *stage*: in-memory stage with ``/World/Assets``
        - *stage_manager*: :class:`MockStageManager` instance
        - *translate*: returns the source text (``current_locale`` stays ``"en"``)
        - *queries*: ``active_tool_id → None``
        - *notify*: silent no-ops — ``request_refresh``, ``select_prim``,
          ``hover_prim``, ``activate_tool``
        - *write door*: ``push_undo`` stays ``None`` on purpose

    Every field can be overridden by passing it as a keyword argument.

    Args:
        **overrides: Keyword arguments to override context fields.

    Returns:
        A fully-populated EditorContext ready for property editor testing.
    """
    from .mock_stage import create_stage
    from .mock_stage_manager import MockStageManager

    defaults = {
        "stage": create_stage(),
        "stage_manager": MockStageManager(),
        "translate": _translate,
        "active_tool_id": lambda: None,
        "request_refresh": _noop,
        "select_prim": _noop,
        "hover_prim": _noop,
        "activate_tool": _noop,
    }
    defaults.update(overrides)
    return EditorContext(**defaults)


def mutation_context(**overrides) -> StageMutationContext:
    """Build a :class:`StageMutationContext` with sensible defaults for testing.

    Defaults:
        - *stage*: ``None``
        - *stage_manager*: :class:`MockStageManager` instance
        - *edit_target_layer_path*: ``""``
        - *triggering_prim_path*: ``""``
        - *queries*: ``get_ground_height → 0.0``, ``find_nearest_prim → None``,
          ``find_prims_in_radius → []``, ``is_atlas_object → False``,
          ``is_navigable_target → False``
        - *i18n*: ``translate`` returns the source text

    Every field can be overridden by passing it as a keyword argument.

    Args:
        **overrides: Keyword arguments to override context fields.

    Returns:
        A fully-populated StageMutationContext ready for fusion plugin testing.
    """
    from .mock_stage_manager import MockStageManager

    def _mock_get_ground_height(x: float, y: float) -> float:
        return 0.0

    def _mock_find_nearest_prim(x: float, y: float, z: float) -> Optional[str]:
        return None

    def _mock_find_prims_in_radius(x: float, y: float, z: float, radius: float):
        return []

    defaults = {
        "stage": None,
        "stage_manager": MockStageManager(),
        "edit_target_layer_path": "",
        "triggering_prim_path": "",
        "get_ground_height": _mock_get_ground_height,
        "find_nearest_prim": _mock_find_nearest_prim,
        "find_prims_in_radius": _mock_find_prims_in_radius,
        "translate": _translate,
        "is_atlas_object": lambda prim_path: False,
        "is_navigable_target": lambda prim_path: False,
    }
    defaults.update(overrides)
    return StageMutationContext(**defaults)
