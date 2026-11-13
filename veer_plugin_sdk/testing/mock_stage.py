"""Mock USD stage creation for plugin testing.

Provides :func:`create_stage` which builds a minimal in-memory USD stage
with the standard site root and assets hierarchy.  Plugins that
need a stage for testing (e.g. tools that create prims under the assets root)
can use this instead of managing stage creation themselves.

Usage::

    from veer_plugin_sdk.testing import create_stage, assets_root

    def test_my_tool():
        stage = create_stage()
        assert stage.GetPrimAtPath(assets_root())
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pxr import Usd

__all__ = ["create_stage", "site_path", "assets_root"]


def _load_host_paths():
    """Return the host's ``core.paths`` module, or ``None`` outside the host.

    In-host the helpers track the live ``SITE_ROOT`` (mutated at stage open);
    standalone there is no ``core`` package at all, so the mock falls back to
    the default skeleton paths — the same ones ``core.paths`` starts with.
    """
    try:
        import core.paths as hp
    except ModuleNotFoundError as exc:
        if exc.name != "core":
            raise
        return None
    return hp


_HOST_PATHS = _load_host_paths()  # module object, not its results (#72)


def site_path():
    """Absolute path of the site root prim — host-live, mock default otherwise."""
    return _HOST_PATHS.site_path() if _HOST_PATHS is not None else "/Site_Untitled"


def assets_root():
    """Absolute path of the assets root prim."""
    return (
        _HOST_PATHS.assets_root()
        if _HOST_PATHS is not None
        else "/Site_Untitled/Assets"
    )


def create_stage() -> "Usd.Stage":
    """Create a minimal in-memory USD stage with the site root and assets.

    Returns:
        A :class:`Usd.Stage` with the standard skeleton hierarchy.
        The stage is in-memory (no file on disk).

    Raises:
        ImportError: If ``pxr`` is not available.
    """
    try:
        from pxr import Usd, UsdGeom
    except ImportError:
        raise ImportError(
            "OpenUSD is required for mock_stage.create_stage().\n"
            "Install it with: pip install 'veer-studio-plugin-sdk[testing]'"
        ) from None

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, site_path())
    UsdGeom.Xform.Define(stage, assets_root())
    return stage
