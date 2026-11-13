"""The testing toolkit works standalone — mock stage, contexts, stage manager.

Skipped when the ``[testing]`` extra (usd-core) is not installed.
"""

from __future__ import annotations

import pytest

pxr = pytest.importorskip("pxr", reason="testing extra not installed")

from veer_plugin_sdk import (  # noqa: E402
    EditorContext,
    PanelContext,
    StageManagerInterface,
    ToolContext,
)
from veer_plugin_sdk.testing import (  # noqa: E402
    MockStageManager,
    assets_root,
    create_stage,
    editor_context,
    panel_context,
    site_path,
    tool_context,
)


def test_create_stage_has_site_and_assets():
    stage = create_stage()
    assert stage.GetPrimAtPath(site_path())
    assert stage.GetPrimAtPath(assets_root())


def test_context_factories_build_real_types():
    assert isinstance(tool_context().stage_manager, MockStageManager)
    assert isinstance(tool_context(), ToolContext)
    assert isinstance(panel_context(), PanelContext)
    assert isinstance(editor_context(), EditorContext)
    assert isinstance(MockStageManager(), StageManagerInterface)


def test_mock_stage_manager_records_lifecycle():
    mgr = MockStageManager(project_dir="/tmp/proj")
    mgr.add_sublayer("./Navigation/navigation.usda")
    mgr.save_layer("./Navigation/navigation.usda")
    mgr.save_stage()
    mgr.delete_prim("/Site/Thing", "my_plugin")

    assert mgr.get_layer_paths() == ["./Navigation/navigation.usda"]
    assert mgr.saved_layers == ["./Navigation/navigation.usda"]
    assert mgr.was_stage_saved
    assert mgr.deleted_prims == [("/Site/Thing", "my_plugin")]

    mgr.reset()
    assert mgr.get_layer_paths() == []
    assert not mgr.was_stage_saved
