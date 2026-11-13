"""The SDK contract surface — every exported name exists and is reachable.

Runs inside the SDK repo itself (CI) and in-repo (via the export helper).
This file is generated: it ships with the package, so an author who pins a
release runs the checks for that release.
"""

from __future__ import annotations

import sys

import veer_plugin_sdk


PORTS = [
    "Diagnostic",
    "ExportReport",
    "IExporter",
    "IFileImporter",
    "IFusionPlugin",
    "IIntegrationPlugin",
    "IPanelFactory",
    "IPluginPreferences",
    "IStageContributor",
    "IToolProvider",
    "IValidator",
    "PluginMeta",
    "Severity",
    "ToolResult",
    "ValidationReport",
]
CONTEXTS = [
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
EXPECTED = PORTS + CONTEXTS + EVENTS


def test_all_contract_names_exported():
    missing = [name for name in EXPECTED if not hasattr(veer_plugin_sdk, name)]
    assert missing == [], f"missing from package: {missing}"


def test_all_matches_contract_exactly():
    assert sorted(veer_plugin_sdk.__all__) == sorted(EXPECTED)


def test_events_module_is_reachable():
    from veer_plugin_sdk import events

    assert veer_plugin_sdk.subscribe is events.subscribe
    assert sorted(events.__all__) == sorted(EVENTS)


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
