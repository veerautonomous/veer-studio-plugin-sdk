"""The context-less doors: one stays excised, three ship for real (sdk#11).

sdk#2 excised four module-level forwarders whose implementations lived in
the host — importable anywhere, ``ModuleNotFoundError`` at call time.
sdk#11 brings three of them back with implementations that ship in the
package: the projection pair (the pyproj-backed ``_coord_utils`` copy) and
the data-root door (the stdlib ``_platform_paths`` copy, wrapped to the
host door's ``str`` return).  ``read_osm_nodes`` keeps its excision — its
parser (``osm_importer``) is host-only.

A failure here means the generator's strip list or the door bindings
drifted, or a helper was re-added without its implementation shipping.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import veer_plugin_sdk
from veer_plugin_sdk import PanelContext, ToolContext

EXCISED = (
    "read_osm_nodes",
)

STANDALONE = (
    "latlon_to_local_enu",
    "batch_latlon_to_local_enu",
    "plugin_data_dir",
)

MACHINERY = (
    "_DIRECT_EXPORTS",
    "_LAZY_EXPORT_GROUPS",
    "_LAZY_EXPORT_INDEX",
)


def test_read_osm_nodes_stays_excised():
    if "core.contexts" in sys.modules:
        # In-host, veer_plugin_sdk aliases the live core module, which keeps
        # its own bridges for context-less host customers — sdk#2 scopes the
        # standalone copy only.
        return
    for name in EXCISED:
        assert not hasattr(veer_plugin_sdk, name), name


def test_context_less_doors_ship_with_real_implementations():
    """Exported, callable, and free of host references in their copies."""
    for name in STANDALONE:
        assert callable(getattr(veer_plugin_sdk, name)), name
    import veer_plugin_sdk._coord_utils as coord_utils
    import veer_plugin_sdk._platform_paths as platform_paths

    for module in (coord_utils, platform_paths):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "core." not in source, (
            f"{module.__name__} still references the host: "
            f"{source[source.find('core.'):source.find('core.') + 60]!r}"
        )


def test_projection_refuses_a_missing_origin():
    """sdk#1 decision 3 holds at module level: no origin, no projection."""
    if "core.contexts" in sys.modules:
        return  # the in-host bridge enforces the same refusal via coord_utils
    with pytest.raises(ValueError, match="SiteOrigin"):
        veer_plugin_sdk.latlon_to_local_enu(47.6, -122.3)


def test_dead_lazy_machinery_is_not_shipped():
    import veer_plugin_sdk._contexts as contexts

    for name in MACHINERY:
        assert name not in vars(contexts), name
    assert "__getattr__" not in vars(contexts)


def test_context_callbacks_still_provide_the_capabilities():
    """The above-abstraction doors survive alongside the module-level ones."""
    assert "latlon_to_local_enu" in ToolContext.__dataclass_fields__
    assert "plugin_data_dir" in ToolContext.__dataclass_fields__
    assert "plugin_data_dir" in PanelContext.__dataclass_fields__
