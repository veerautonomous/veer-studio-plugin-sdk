"""Mock context factories for plugin testing.

Creates :class:`ToolContext`, :class:`PanelContext`, and :class:`EditorContext`
instances pre-populated with sensible defaults (mock stage manager, in-memory
stage, etc.) so plugin tests don't need to construct them manually.

Every context field is overridable via ``**overrides`` — only pass what your
test needs to customize.

Usage::

    from veer_plugin_sdk.testing import tool_context

    def test_my_tool():
        ctx = tool_context()
        assert ctx.stage is not None
        assert ctx.stage_manager is not None
"""

from __future__ import annotations

from typing import Optional

from veer_plugin_sdk import (
    ToolContext, PanelContext, EditorContext, StageMutationContext,
)

__all__ = [
    "tool_context", "panel_context", "editor_context", "mutation_context",
]


def tool_context(**overrides) -> ToolContext:
    """Build a :class:`ToolContext` with sensible defaults for testing.

    Defaults:
        - *stage*: in-memory stage with ``/World/Assets`` (from :func:`mock_stage.create_stage`)
        - *stage_manager*: :class:`MockStageManager` instance
        - *selection*: empty list
        - *project_dir*: ``""``
        - *preferences*: empty dict
        - *plugin_data_dir*: a fresh temp directory per call

    Every field can be overridden by passing it as a keyword argument.

    Args:
        **overrides: Keyword arguments to override context fields.

    Returns:
        A fully-populated ToolContext ready for tool testing.
    """
    from .mock_stage import create_stage
    from .mock_stage_manager import MockStageManager

    def _mock_get_ground_height(x: float, y: float) -> float:
        return 0.0

    def _mock_find_nearest_prim(x: float, y: float, z: float) -> Optional[str]:
        return None

    def _mock_find_prims_in_radius(x: float, y: float, z: float, radius: float):
        return []

    def _mock_screen_to_world(screen_x, screen_y, viewport_w, viewport_h, frustum):
        return (None, None)

    def _mock_plugin_data_dir() -> str:
        import tempfile
        return tempfile.mkdtemp(prefix="veer-studio-test-plugin-data-")

    defaults = {
        "stage": create_stage(),
        "stage_manager": MockStageManager(),
        "selection": [],
        "get_ground_height": _mock_get_ground_height,
        "find_nearest_prim": _mock_find_nearest_prim,
        "find_prims_in_radius": _mock_find_prims_in_radius,
        "screen_to_world": _mock_screen_to_world,
        "project_dir": "",
        "preferences": {},
        "plugin_data_dir": _mock_plugin_data_dir,
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
        - *plugin_data_dir*: a fresh temp directory per call
        - *on_selection_changed*: ``None``
        - *on_stage_changed*: ``None``
        - *on_viewport_changed*: ``None``

    Every field can be overridden by passing it as a keyword argument.

    Args:
        **overrides: Keyword arguments to override context fields.

    Returns:
        A fully-populated PanelContext ready for panel factory testing.
    """
    from .mock_stage import create_stage
    from .mock_stage_manager import MockStageManager

    def _mock_plugin_data_dir() -> str:
        import tempfile
        return tempfile.mkdtemp(prefix="veer-studio-test-plugin-data-")

    defaults = {
        "stage": create_stage(),
        "stage_manager": MockStageManager(),
        "project_dir": "",
        "preferences": {},
        "plugin_data_dir": _mock_plugin_data_dir,
        "on_selection_changed": None,
        "on_stage_changed": None,
        "on_viewport_changed": None,
    }
    defaults.update(overrides)
    return PanelContext(**defaults)


def editor_context(**overrides) -> EditorContext:
    """Build an :class:`EditorContext` with sensible defaults for testing.

    Defaults:
        - *stage*: in-memory stage with ``/World/Assets``
        - *stage_manager*: :class:`MockStageManager` instance
        - *request_refresh*: ``None``

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
        "request_refresh": None,
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
        - *get_ground_height*: returns 0.0
        - *find_nearest_prim*: returns ``None``
        - *find_prims_in_radius*: returns ``[]``

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
    }
    defaults.update(overrides)
    return StageMutationContext(**defaults)
