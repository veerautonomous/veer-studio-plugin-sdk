"""Stage-pin protocol for plugin tests — the host's pin when present.

In-host the names are the real ``core.stage_pin`` objects, so a pin set
through this module is the pin ``StageManager`` and the edit-scope gate
enforce (shared module state is the point).  Standalone — an author's CI
with only the pip package — the generated ``_stage_pin_fallback`` copy
carries the same pure protocol (threading + contextlib, no host).

Usage::

    from veer_plugin_sdk.testing import stage_pin

    stage_pin.pin("my long job", owner_plugin_id="my.plugin")
    try:
        stage_pin.check_unpinned("save")   # raises StagePinnedError
    finally:
        stage_pin.unpin()

    with stage_pin.exempt_for("my.plugin"):   # the owner's only door
        ...
"""

from __future__ import annotations

__all__ = [
    "StagePinnedError",
    "pin",
    "unpin",
    "is_pinned",
    "pin_reason",
    "check_unpinned",
    "exempt",
    "exempt_for",
    "pin_owner",
]

try:
    from core.stage_pin import (
        StagePinnedError,
        pin,
        unpin,
        is_pinned,
        pin_reason,
        check_unpinned,
        exempt,
        exempt_for,
        pin_owner,
    )
except ModuleNotFoundError as _exc:
    if _exc.name != "core":
        raise
    from veer_plugin_sdk._stage_pin_fallback import (
        StagePinnedError,
        pin,
        unpin,
        is_pinned,
        pin_reason,
        check_unpinned,
        exempt,
        exempt_for,
        pin_owner,
    )
