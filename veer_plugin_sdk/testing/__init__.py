"""Test utilities for Veer Studio plugin development.

Provides mock stage creation, mock contexts, and a MockStageManager so plugin
developers can write tests with only the SDK — no running Veer Studio required.
"""

from .mock_stage import create_stage, site_path, assets_root
from .mock_contexts import (
    tool_context,
    panel_context,
    editor_context,
)
from .mock_stage_manager import MockStageManager
from . import stage_pin

__all__ = [
    "create_stage",
    "site_path",
    "assets_root",
    "tool_context",
    "panel_context",
    "editor_context",
    "MockStageManager",
    "stage_pin",
]
