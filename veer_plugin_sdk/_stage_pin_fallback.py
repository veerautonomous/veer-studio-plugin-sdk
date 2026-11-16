"""Stage pin — refuse stage mutations while a background job runs.

Wayfinder #322 (map #318): while a long-running pipeline owns the stage,
Save, prim deletion, and every sanctioned edit-scope acquisition are
refused; only the job authors (through :func:`exempt`).  The pin is a
module-level flag — ``core`` stays Qt-free, and the app-layer
``JobService`` owns pin/unpin across a job's lifetime (pin at start,
unpin at every terminal path).

Enforcement points:

* ``StageManager.save_all`` / ``save_layer`` — no persist mid-run.
* ``StageManager.delete_prim`` and the ``ensure_editable_*`` doors —
  no new writable overlays, no deletions.
* the context's edit-target scope door — the single write gate (#91/#92)
  refuses to retarget the edit target.

The pin is checked, not raised around: an already-running tool's
``attr.Set`` on an open edit target is *not* intercepted (there is no
hook for it) — the save refusal is what keeps such writes off disk.
"""

from __future__ import annotations

import contextlib
import threading

__all__ = [
    "StagePinnedError", "pin", "unpin", "is_pinned", "pin_reason",
    "check_unpinned", "exempt", "exempt_for", "pin_owner",
]


class StagePinnedError(RuntimeError):
    """Raised when a stage mutation is attempted while the stage is pinned."""


_lock = threading.Lock()
_pinned = False
_reason = ""
_owner = ""   # JobSpec.plugin_id of the pin's holder; "" = host/unowned
_exempt_depth = 0


def pin(reason: str, owner_plugin_id: str = "") -> None:
    """Pin the stage.  Raises if already pinned (a double-start bug).

    *owner_plugin_id* names the plugin whose job holds the pin — the only
    plugin :func:`exempt_for` will let through.  Empty means a host job:
    only a context whose own ``plugin_id`` is also empty matches.
    """
    global _pinned, _reason, _owner
    with _lock:
        if _pinned:
            raise RuntimeError(
                f"stage already pinned: {_reason!r} (pin({reason!r}))")
        _pinned = True
        _reason = reason
        _owner = owner_plugin_id or ""


def unpin() -> None:
    """Release the pin.  Tolerated when not pinned (idempotent teardown)."""
    global _pinned, _reason, _owner
    with _lock:
        _pinned = False
        _reason = ""
        _owner = ""


def pin_owner() -> str:
    """The ``plugin_id`` that holds the pin (empty when unpinned or host)."""
    with _lock:
        return _owner


def is_pinned() -> bool:
    """True while a background job holds the stage."""
    with _lock:
        return _pinned


def pin_reason() -> str:
    """The reason the stage was pinned with (empty when unpinned)."""
    with _lock:
        return _reason


def check_unpinned(op: str) -> None:
    """Raise :class:`StagePinnedError` if pinned and not inside :func:`exempt`.

    *op* names the refused operation and appears in the message so the
    caller's stack trace says what was blocked.
    """
    with _lock:
        pinned = _pinned
        exempt = _exempt_depth > 0
        reason = _reason
    if pinned and not exempt:
        raise StagePinnedError(
            f"{op} refused — background job running ({reason})")


@contextlib.contextmanager
def exempt():
    """Allow stage mutations inside the block while pinned.

    The door for a job's *own* authoring (host-side driver code running
    under the pin).  Nested; reverts on exit.
    """
    global _exempt_depth
    with _lock:
        _exempt_depth += 1
    try:
        yield
    finally:
        with _lock:
            _exempt_depth -= 1


def exempt_for(plugin_id: str):
    """The pin's one door, gated by job ownership (sdk#1, ruling 2026-11-14).

    Returns a context manager.  No pin in force -> a no-op yield: there is
    nothing to bypass.  Pinned -> yields only when *plugin_id* equals the
    pin's owner (``JobSpec.plugin_id`` at pin time; both empty means the
    host's own job and the host's own context).  Anyone else gets
    :class:`StagePinnedError` naming the holder.

    This is the supported replacement for the old context-level
    re-export of :func:`exempt`: the raw door never leaves the host, and
    a plugin can only ever open it for a job it owns itself — a declared
    permission would hand out a permanent key to a temporary lock.
    """
    with _lock:
        pinned = _pinned
        owner = _owner
        reason = _reason
    if not pinned:
        return contextlib.nullcontext()
    if (plugin_id or "") == owner:
        return exempt()
    raise StagePinnedError(
        f"stage_pin_exempt refused — background job running ({reason}), "
        f"owned by {owner or 'host'}; only its own authoring may bypass")
