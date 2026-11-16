"""The testing toolkit works standalone — mock stage, contexts, stage manager.

Skipped when the ``[testing]`` extra (usd-core) is not installed.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

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
    stage_pin,
    tool_context,
)
from veer_plugin_sdk.testing.mock_contexts import mutation_context  # noqa: E402

# The #8 ruling, recorded as data: write doors stay unwired on purpose, so a
# unit test that reaches one fails loudly instead of silently writing.
WRITE_DOORS = frozenset({
    "import_file",
    "push_undo",
    "create_edit_scope",
    "create_undo_checkpoint",
    "create_multi_undo_checkpoint",
    "regenerate_meshes",
    "regenerate_mesh_in_job",
    "upsert_point_cloud_tile",
    "consolidate_point_cloud_run",
    "discard_point_cloud_run",
    "derive_cloud",
    "revert_derived_clouds",
})


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


# --- #8: default stubs ----------------------------------------------------


def test_empty_world_query_defaults():
    """The mock stage has no ground and no clouds — the answers say so."""
    ctx = tool_context()
    assert ctx.has_ground_mesh is not None
    assert ctx.has_ground_mesh() is False
    assert ctx.has_ground_mesh_at(0.0, 0.0) is True  # host: no mesh → True
    assert ctx.get_ground_mesh_height(0.0, 0.0) is None
    assert ctx.build_ground_mesh_cache() is None
    assert ctx.cloud_units() == []
    assert ctx.cloud_units(roles=("geometry",), current_only=True) == []
    assert ctx.get_ground_height(1.0, 2.0) == 0.0
    assert ctx.find_nearest_prim(0.0, 0.0, 0.0) is None
    assert ctx.find_prims_in_radius(0.0, 0.0, 0.0, 1.0) == []
    assert ctx.screen_to_world(0, 0, 100, 100, None) == (None, None)
    assert ctx.get_selection_set() == []
    assert ctx.get_world_center("/Site/Thing") is None
    assert ctx.is_atlas_object("/Site/Thing") is False
    assert ctx.get_atlas_type("/Site/Thing") is None
    assert ctx.get_atlas_object_id("/Site/Thing") is None
    assert ctx.is_navigable_target("/Site/Thing") is False
    assert ctx.get_assembly_terminals("/Site/Thing") is None
    assert ctx.snapshot_camera() == {}


def test_translate_returns_the_source_text():
    ctx = tool_context()
    assert ctx.translate("CloudCut", "Kept the cuts.") == "Kept the cuts."
    assert ctx.current_locale == "en"


def test_notify_defaults_are_callable_noops():
    """Notify doors never raise and record nothing; override to spy."""
    ctx = tool_context()
    for name in (
        "register_overlay", "unregister_overlay", "request_cursor",
        "release_cursor", "show_status", "set_tool_hints", "show_progress",
        "hide_progress", "request_tree_refresh", "on_selection_changed",
        "set_selection_set", "set_auxiliary_dock", "clear_auxiliary_dock",
        "request_deactivate", "restore_camera", "frame_prim",
        "register_prim_menu_entry", "register_edit_session_entry",
    ):
        getattr(ctx, name)(object())  # must not raise


def test_write_doors_stay_unwired():
    ctx = tool_context()
    for name in sorted(WRITE_DOORS):
        assert getattr(ctx, name) is None, f"{name} is a write door"


def test_latlon_projection_projects_for_real():
    """The stub ships the real projection (sdk#11): origin required, honest
    math — an anchor placed at its own origin projects to the zero point."""
    ctx = tool_context()
    with pytest.raises(ValueError, match="SiteOrigin"):
        ctx.latlon_to_local_enu(47.6, -122.3)

    anchor = SimpleNamespace(
        anchor_mode="tangent_plane", anchor_lat=47.6, anchor_lon=-122.3,
    )
    x, y, z = ctx.latlon_to_local_enu(47.6, -122.3, origin=anchor)
    assert (x, y, z) == (0.0, 0.0, 0.0)

    # A metre north of the anchor: AEQD keeps direction true at short range.
    x, y, z = ctx.latlon_to_local_enu(47.6 + 9.0e-6, -122.3, origin=anchor)
    assert y == pytest.approx(1.0, abs=0.05)
    assert x == pytest.approx(0.0, abs=0.05)
    assert z == 0.0


def test_plugin_data_dir_is_stable_per_context():
    """One context, one data root — the host returns the same path per call."""
    ctx = tool_context()
    first = ctx.plugin_data_dir()
    assert ctx.plugin_data_dir() == first
    other = tool_context()
    assert other.plugin_data_dir() != first


def test_a_lifecycle_path_runs_without_hand_injection():
    """The sample's activate() sequence — no TypeError on a default context."""
    ctx = tool_context()
    assert ctx.has_ground_mesh() is False
    ctx.register_overlay(object())
    ctx.request_cursor("crosshair")
    ctx.show_status(ctx.translate("CloudCut", "Move over the road."), 3000)
    ctx.unregister_overlay("renderer-1")
    ctx.release_cursor()


def test_every_tool_context_callable_is_ruled():
    """Each Optional[Callable] is wired or a documented write door — a new
    field must pick a side (add it to WRITE_DOORS or give it a default)."""
    callables = {
        f.name for f in dataclasses.fields(ToolContext)
        if "Callable" in str(f.type)
    }
    ctx = tool_context()
    for name in sorted(callables):
        value = getattr(ctx, name)
        if name in WRITE_DOORS:
            assert value is None, f"{name} is a write door — leave it unwired"
        else:
            assert value is not None, (
                f"{name} has no testing default — wire it in "
                f"tool_context() or add it to WRITE_DOORS"
            )


def test_overrides_replace_every_default():
    ctx = tool_context(
        has_ground_mesh=lambda: True,
        cloud_units=lambda **kw: ["unit"],
        show_status=lambda *a: None,
        push_undo=lambda *a: None,
        plugin_data_dir=lambda: "/fixed",
    )
    assert ctx.has_ground_mesh() is True
    assert ctx.cloud_units() == ["unit"]
    assert ctx.push_undo is not None
    assert ctx.plugin_data_dir() == "/fixed"


def test_panel_and_editor_defaults():
    panel = panel_context()
    assert panel.translate("Ctx", "Hello") == "Hello"
    panel.on_selection_changed(object())
    panel.on_stage_changed(object())
    panel.on_viewport_changed(object())
    assert panel.push_undo is None  # write door
    assert panel.plugin_data_dir() == panel.plugin_data_dir()

    editor = editor_context()
    assert editor.translate("Ctx", "Hello") == "Hello"
    assert editor.active_tool_id() is None
    editor.request_refresh()
    editor.select_prim("/Site/Thing")
    editor.hover_prim("/Site/Thing")
    editor.activate_tool("some_tool")
    assert editor.push_undo is None  # write door


def test_mutation_context_defaults():
    mut = mutation_context()
    assert mut.get_ground_height(0.0, 0.0) == 0.0
    assert mut.find_nearest_prim(0.0, 0.0, 0.0) is None
    assert mut.find_prims_in_radius(0.0, 0.0, 0.0, 1.0) == []
    assert mut.translate("Ctx", "Hi") == "Hi"
    assert mut.is_atlas_object("/Site/Thing") is False
    assert mut.is_navigable_target("/Site/Thing") is False


def test_stage_pin_protocol_runs_standalone():
    """pin → check refuses → owner exempts → unpin (sdk#12)."""
    stage_pin.unpin()  # idempotent — a prior test's pin must not leak
    assert stage_pin.is_pinned() is False

    stage_pin.pin("unit job", owner_plugin_id="my.plugin")
    assert stage_pin.is_pinned() is True
    assert stage_pin.pin_owner() == "my.plugin"
    assert stage_pin.pin_reason() == "unit job"

    with stage_pin.exempt_for("my.plugin"):
        stage_pin.check_unpinned("write")  # owner passes while pinned

    with pytest.raises(stage_pin.StagePinnedError):
        stage_pin.check_unpinned("write")

    with pytest.raises(stage_pin.StagePinnedError):
        with stage_pin.exempt_for("someone.else"):
            pass

    stage_pin.unpin()
    stage_pin.check_unpinned("write")  # unpinned: everyone passes
    with stage_pin.exempt_for("anyone"):  # no pin → no-op yield
        pass
