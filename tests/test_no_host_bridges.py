"""The host-bridge helpers stay excised from the SDK surface (sdk#2).

`read_osm_nodes`, `latlon_to_local_enu`, `batch_latlon_to_local_enu` and
`plugin_data_dir` were module-level forwarders into host-only modules —
importable anywhere, callable only inside Veer Studio (otherwise
``ModuleNotFoundError`` at call time).  Their machinery was excised with
the dead ``__getattr__`` tables that never worked standalone; the
sanctioned doors are the context callbacks, which tests inject.

A failure here means the export generator's strip list drifted (the
structural names stopped matching) or the helpers were re-added without
the implementation shipping with the package.
"""

from __future__ import annotations

import sys

import veer_plugin_sdk
from veer_plugin_sdk import PanelContext, ToolContext

BRIDGES = (
    "read_osm_nodes",
    "latlon_to_local_enu",
    "batch_latlon_to_local_enu",
    "plugin_data_dir",
)

MACHINERY = (
    "_DIRECT_EXPORTS",
    "_LAZY_EXPORT_GROUPS",
    "_LAZY_EXPORT_INDEX",
)


def test_bridge_helpers_are_not_exported():
    if "core.contexts" in sys.modules:
        # In-host, veer_plugin_sdk aliases the live core module, which keeps
        # its own bridges for context-less host customers — sdk#2 scopes the
        # standalone copy only.
        return
    for name in BRIDGES:
        assert not hasattr(veer_plugin_sdk, name), name


def test_dead_lazy_machinery_is_not_shipped():
    import veer_plugin_sdk._contexts as contexts

    for name in MACHINERY:
        assert name not in vars(contexts), name
    assert "__getattr__" not in vars(contexts)


def test_context_callbacks_still_provide_the_capabilities():
    """The above-abstraction doors survive the excision."""
    assert "latlon_to_local_enu" in ToolContext.__dataclass_fields__
    assert "plugin_data_dir" in ToolContext.__dataclass_fields__
    assert "plugin_data_dir" in PanelContext.__dataclass_fields__
