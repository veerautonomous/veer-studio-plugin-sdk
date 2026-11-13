"""Mock StageManager for plugin testing.

Provides :class:`MockStageManager` which implements :class:`StageManagerInterface`
with full call recording.  Plugin tests can assert on what operations their code
performed without needing a real :class:`StageManager` or a running Qt application.

Usage::

    from veer_plugin_sdk.testing import MockStageManager

    def test_my_contributor():
        mgr = MockStageManager(project_dir="/tmp/test_proj")
        contributor = MyContributor()
        contributor.on_stage_opened(mgr)

        assert len(mgr.added_sublayers) == 1
        assert mgr.was_stage_saved
"""

from __future__ import annotations

from veer_plugin_sdk import StageManagerInterface

__all__ = ["MockStageManager"]


class MockStageManager(StageManagerInterface):
    """Full :class:`StageManagerInterface` implementation that records all calls.

    Every mutating method appends to a list; every query method returns the
    value set via the constructor or a corresponding setter.  Use the
    inspection properties (``added_sublayers``, ``saved_layers``, etc.) to
    assert on plugin behaviour in tests.

    Constructor Args:
        project_dir: Value returned by :meth:`get_project_dir`.  Default ``""``.
        stage: Value returned by :meth:`get_stage`.  Default ``None``.
    """

    def __init__(self, project_dir: str = "", stage=None):
        self._project_dir = project_dir
        self._stage = stage

        # -- Preexisting sublayers (not recorded as calls) --
        self._preexisting_sublayers: list[str] = []

        # -- Call recording lists --
        self._sublayers: list[str] = []
        self._saved_layers: list[str] = []
        self._edit_targets: list[str] = []
        self._saved_stage: bool = False
        self._notified_prims_modified: list[str] = []
        self._on_prims_modified_callbacks: list[callable] = []
        self._dirty: bool = False
        self._dirty_layers: list[str] = []
        self._checkpoints: list[str] = []
        self._deleted_prims: list[tuple[str, str]] = []
        self._created_atlas_prims: list[dict] = []
        self._named_layers: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # StageManagerInterface methods
    # ------------------------------------------------------------------

    def add_sublayer(self, layer_path: str, position: int = -1) -> None:
        """Record the sublayer addition."""
        self._sublayers.append(layer_path)

    def set_edit_target(self, layer_path: str) -> None:
        """Record the edit-target change."""
        self._edit_targets.append(layer_path)

    def save_layer(self, layer_path: str) -> None:
        """Record a single-layer save."""
        self._saved_layers.append(layer_path)

    def save_stage(self) -> None:
        """Record a full-stage save."""
        self._saved_stage = True

    def save_draft_overlays(self) -> int:
        """Save all in-memory draft overlays to disk (no-op in mock)."""
        return 0

    def get_stage(self):
        """Return the stage set at construction time."""
        return self._stage

    def get_layer_paths(self) -> list[str]:
        """Return the current sublayer paths (preexisting + recorded)."""
        return self._preexisting_sublayers + list(self._sublayers)

    def get_project_dir(self) -> str:
        """Return the project directory set at construction time."""
        return self._project_dir

    def notify_prims_modified(self, prim_paths: list[str]) -> None:
        """Record a prims-modified notification and forward to callbacks."""
        self._notified_prims_modified.extend(prim_paths)
        for cb in self._on_prims_modified_callbacks:
            try:
                cb(self, prim_paths)
            except Exception:
                pass

    def get_layer_by_identifier(self, identifier: str):
        """Return None — the mock tracks no identifier → layer map."""
        return None

    def find_point_cloud(self):
        """Return None — the mock stage has no point cloud."""
        return None

    def find_all_point_clouds(self) -> list:
        """Return an empty list — the mock stage has no point clouds."""
        return []

    def find_point_cloud_frame(self):
        """Return None — the mock stage has no point cloud frame."""
        return None

    def get_ground_height_at(self, x: float, y: float) -> float:
        """Return 0.0 — the mock ground is the Z=0 plane."""
        return 0.0

    def has_ground_mesh(self) -> bool:
        """Return False — the mock stage has no ground mesh."""
        return False

    def read_site_origin(self):
        """Return None — the mock stage declares no site origin."""
        return None

    def create_atlas_prim(self, atlas_type_name: str, position, **kwargs) -> str:
        """Record the request and return a placeholder prim path."""
        self._created_atlas_prims.append(
            {"type": atlas_type_name, "position": position, **kwargs})
        return f"/Mock/AtlasObject_{len(self._created_atlas_prims)}"

    def mark_dirty(self) -> None:
        """Flag the stage dirty."""
        self._dirty = True

    def is_dirty(self) -> bool:
        """True once :meth:`mark_dirty` or :meth:`mark_dirty_layer` was called."""
        return self._dirty

    def has_unsaved_layers(self) -> bool:
        """Mirror :meth:`is_dirty` — the mock holds no layer state."""
        return self._dirty

    def mark_dirty_layer(self, layer_id: str = None) -> None:
        """Record the layer and flag the stage dirty."""
        self._dirty_layers.append(layer_id)
        self._dirty = True

    def create_checkpoint(self, label: str = "") -> str:
        """Record the checkpoint and return its label as the id."""
        self._checkpoints.append(label)
        return label

    # -- Draft overlays: the mock has none, so every layer is editable --

    def get_draft_layer_path(self, original_path: str) -> str | None:
        """Return None — the mock creates no draft overlays."""
        return None

    def is_draft_path(self, layer_path: str) -> bool:
        """Return False — no path is a draft in the mock."""
        return False

    def ensure_editable_layer(self, layer_path: str) -> str | None:
        """Return the path itself — the mock has no overlays to scaffold."""
        return layer_path

    def ensure_editable_category(self, category: str) -> str | None:
        """Return the category name — see :meth:`ensure_editable_layer`."""
        return category

    def ensure_named_category_layer(self, category: str,
                                    file_name: str) -> str | None:
        """Record the birth request and return the layer path.

        The mock owns no project directory, so it reports the layer the
        request names rather than scaffolding a file or a draft overlay.
        """
        self._named_layers.append((category, file_name))
        return f"{category}/{file_name}"

    def ensure_editable_prim(self, prim_path: str) -> str | None:
        """Return the path itself — see :meth:`ensure_editable_layer`."""
        return prim_path

    def delete_prim(self, prim_path: str, plugin_id: str = "") -> bool:
        """Record the deletion and report success."""
        self._deleted_prims.append((prim_path, plugin_id))
        return True

    # ------------------------------------------------------------------
    # Inspection properties (test ergonomics)
    # ------------------------------------------------------------------

    @property
    def added_sublayers(self) -> list[str]:
        """All layer paths passed to :meth:`add_sublayer`."""
        return list(self._sublayers)

    @property
    def saved_layers(self) -> list[str]:
        """All layer paths passed to :meth:`save_layer`."""
        return list(self._saved_layers)

    @property
    def edit_targets(self) -> list[str]:
        """All layer paths passed to :meth:`set_edit_target`."""
        return list(self._edit_targets)

    @property
    def was_stage_saved(self) -> bool:
        """True if :meth:`save_stage` was called at least once."""
        return self._saved_stage

    @property
    def notified_prims_modified(self) -> list[str]:
        """All prim paths passed to :meth:`notify_prims_modified`."""
        return list(self._notified_prims_modified)

    @property
    def dirty_layers(self) -> list[str]:
        """All layer ids passed to :meth:`mark_dirty_layer`."""
        return list(self._dirty_layers)

    @property
    def checkpoints(self) -> list[str]:
        """All labels passed to :meth:`create_checkpoint`."""
        return list(self._checkpoints)

    @property
    def deleted_prims(self) -> list[tuple[str, str]]:
        """All ``(prim_path, plugin_id)`` pairs passed to :meth:`delete_prim`."""
        return list(self._deleted_prims)

    @property
    def created_atlas_prims(self) -> list[dict]:
        """All requests passed to :meth:`create_atlas_prim`."""
        return list(self._created_atlas_prims)

    @property
    def named_layers(self) -> list[tuple[str, str]]:
        """All ``(category, file_name)`` pairs passed to
        :meth:`ensure_named_category_layer`."""
        return list(self._named_layers)

    # ------------------------------------------------------------------
    # Test helpers — set up return values after construction
    # ------------------------------------------------------------------

    def set_stage(self, stage) -> None:
        """Set the stage that :meth:`get_stage` will return."""
        self._stage = stage

    def set_project_dir(self, path: str) -> None:
        """Set the project directory that :meth:`get_project_dir` will return."""
        self._project_dir = path

    def add_existing_sublayer(self, layer_path: str) -> None:
        """Pre-populate the sublayer list (simulates an already-loaded layer).

        Use this to test idempotent sublayer logic — the path will appear in
        :meth:`get_layer_paths` without recording an :meth:`add_sublayer` call.
        """
        if layer_path not in self._preexisting_sublayers:
            self._preexisting_sublayers.append(layer_path)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all recorded calls and return to initial state."""
        self._preexisting_sublayers.clear()
        self._sublayers.clear()
        self._saved_layers.clear()
        self._edit_targets.clear()
        self._saved_stage = False
        self._notified_prims_modified.clear()
        self._on_prims_modified_callbacks.clear()
        self._dirty = False
        self._dirty_layers.clear()
        self._checkpoints.clear()
        self._deleted_prims.clear()
        self._created_atlas_prims.clear()
        self._named_layers.clear()
