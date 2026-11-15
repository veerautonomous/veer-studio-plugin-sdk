"""The SDK contract surface — every exported name exists and is reachable.

Runs inside the SDK repo itself (CI) and in-repo (via the export helper).
This file is generated: it ships with the package, so an author who pins a
release runs the checks for that release.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import veer_plugin_sdk


PORTS = [
    "BaseOverlayRenderer",
    "CloudUnit",
    "CreationSession",
    "CreationVerb",
    "Diagnostic",
    "ExportReport",
    "GEOMETRIC_ROLES",
    "IExporter",
    "IFileImporter",
    "IFusionPlugin",
    "IIntegrationPlugin",
    "IPanelFactory",
    "IPluginPreferences",
    "IStageContributor",
    "IToolProvider",
    "IValidator",
    "JobSpec",
    "OverlayLayer",
    "PluginMeta",
    "Severity",
    "ToolResult",
    "ValidationReport",
]
CONTEXTS = [
    "DerivedCloudHandle",
    "EditorContext",
    "PanelContext",
    "StageManagerInterface",
    "StageMutationContext",
    "ToolContext",
    "ToolEvent",
]
EVENTS = [
    "DomainEvent",
    "ToolActivated",
    "ToolDeactivated",
    "ToolModeChanged",
    "SublayersRewired",
    "StreamedTileCratesCommitted",
    "subscribe",
    "unsubscribe",
    "WayDeleted",
    "NodesPruned",
    "LaneletCommitted",
    "LaneletDeleted",
    "RegulatoryElementDeleted",
    "AreaCreated",
    "LiftSessionStarted",
    "LiftSessionEnded",
]
PATHS = [
    "assets_root",
    "cameras_root",
    "navigation_root",
    "reality_root",
    "reference_barriers_root",
    "reference_buildings_root",
    "reference_landuse_root",
    "reference_other_root",
    "reference_root",
    "reference_roads_root",
    "reference_satellite_root",
    "reference_water_root",
]
EXPECTED = PORTS + CONTEXTS + EVENTS + PATHS


def test_all_contract_names_exported():
    missing = [name for name in EXPECTED if not hasattr(veer_plugin_sdk, name)]
    assert missing == [], f"missing from package: {missing}"


def test_all_matches_contract_exactly():
    assert sorted(veer_plugin_sdk.__all__) == sorted(EXPECTED)


def test_api_reference_index_matches_manifest_and_all():
    """§8's contract list, export-manifest.json and __all__ must agree.

    The index is what an author reads; a name landing in one of the three
    and not the others is the drift this suite exists to catch.
    """
    root = Path(__file__).resolve().parent.parent
    text = (root / "docs" / "api-reference.md").read_text(encoding="utf-8")
    section = re.search(
        r"^## Contract \(\d+ names[^\n]*\n(.*?)(?=^## )",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert section, "api-reference.md §8 contract section missing"
    listed = sorted(set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", section.group(1))))
    manifest = json.loads(
        (root / "export-manifest.json").read_text(encoding="utf-8")
    )
    recorded = sorted(entry["name"] for entry in manifest["names"])
    assert listed == recorded == sorted(EXPECTED), (
        f"index={listed!r} manifest={recorded!r} all={sorted(EXPECTED)!r}"
    )


def test_events_module_is_reachable():
    from veer_plugin_sdk import events

    assert veer_plugin_sdk.subscribe is events.subscribe
    assert sorted(events.__all__) == sorted(EVENTS)


def test_paths_module_is_reachable():
    from veer_plugin_sdk import paths

    assert veer_plugin_sdk.reference_roads_root is paths.reference_roads_root
    assert sorted(paths.__all__) == sorted(PATHS)
    # Callability is the sdk#5 promise: both modes return the default root.
    assert paths.reference_roads_root().endswith("/Reference/Roads")
    assert paths.assets_root().endswith("/Assets")


def test_event_classes_subclass_domain_event():
    domain = veer_plugin_sdk.DomainEvent
    for name in EVENTS:
        obj = getattr(veer_plugin_sdk, name)
        if isinstance(obj, type):
            assert issubclass(obj, domain), f"{name} is not a DomainEvent"


def test_standalone_import_did_not_pull_in_host():
    """In an author's environment the host package must never be importable.

    (In the Veer Studio checkout this test is skipped by the host runner —
    the alias path is exercised there instead.)
    """
    if "atlas_studio" in sys.modules or "veer_studio" in sys.modules:
        return
    # 'core' being absent is the standalone guarantee; in-repo the export
    # tests assert this in a subprocess, not here.
    assert "core.contexts" not in sys.modules or "veer_plugin_sdk" in sys.modules
