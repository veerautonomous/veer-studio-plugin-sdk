"""Platform data layout — config, cache, and log roots in one door.

The layout ratified on [Platform data layout and first-run](issue #289,
wayfinder map #279):

======================  ==========================  ==============================  ==================================
store                   Linux                       macOS                           Windows
======================  ==========================  ==============================  ==================================
config                  ``~/.config/veer-studio``   ``~/Library/Application         ``%LOCALAPPDATA%\\veer-studio``
                                                    Support/veer-studio``
data (+ ``plugins/``)   ``$XDG_DATA_HOME`` /        ``~/Library/Application         ``%LOCALAPPDATA%\\veer-studio``
                        ``~/.local/share`` + slug   Support/veer-studio``
cache (+ ``drafts/``)   ``$XDG_CACHE_HOME`` /        ``~/Library/Caches`` /          ``%LOCALAPPDATA%\\veer-studio``
                        ``~/.cache`` + slug         slug + ``drafts/``              ``\\cache`` (+ ``drafts/``)
logs                    ``$XDG_STATE_HOME`` /       ``~/Library/Logs/veer-studio``  ``%LOCALAPPDATA%\\veer-studio``
                        ``~/.local/state`` + slug                                   ``\\logs``
======================  ==========================  ==============================  ==================================

Each root is the platform's *generic* per-user location — the value Qt's
``QStandardPaths`` generic enums resolve to — plus the ``veer-studio``
slug.  Qt's app-injected locations are never used: they key off
``setOrganizationName()``/``setApplicationName()`` (the publisher and
product name — branding, which can move), while the filesystem layout must
stay on the stable slug.  Qt itself is not consulted here: macOS
config is the generic *data* location and macOS logs have no Qt enum at
all, so the canonical layout is spelled out per platform, which also
keeps this module Qt-free like the rest of ``core/``.

Everything resolves at call time — never capture a result at import time
(CLAUDE.md #72's freeze trap).  Tests inject through the ``XDG_*`` /
``LOCALAPPDATA`` / ``HOME`` environment variables, or exercise all three
platform tables through :func:`resolve_roots`.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

#: Filesystem slug — one directory component under each platform root.
SLUG = "veer-studio"


@dataclass(frozen=True)
class Roots:
    """The four per-user stores, each already carrying the :data:`SLUG`."""

    config: Path
    data: Path
    cache: Path
    logs: Path


def current_platform() -> str:
    """The running platform as one of ``"linux"``, ``"darwin"``, ``"win32"``."""
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win") or os.name == "nt":
        return "win32"
    return "linux"


def _xdg_base(env_var: str, default: Path) -> Path:
    """``$env_var`` when set and non-empty, else *default*."""
    value = os.environ.get(env_var)
    return Path(value) if value else default


def resolve_roots(platform_key: str | None = None) -> Roots:
    """Resolve the three roots for *platform_key* (``None`` = running one).

    The platform seam — tests exercise all three tables without needing a
    Mac or a Windows box.
    """
    key = platform_key or current_platform()
    home = Path.home()
    if key == "darwin":
        return Roots(
            config=home / "Library" / "Application Support" / SLUG,
            data=home / "Library" / "Application Support" / SLUG,
            cache=home / "Library" / "Caches" / SLUG,
            logs=home / "Library" / "Logs" / SLUG,
        )
    if key == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        base = Path(local) / SLUG
        return Roots(config=base, data=base, cache=base / "cache",
                     logs=base / "logs")
    return Roots(
        config=_xdg_base("XDG_CONFIG_HOME", home / ".config") / SLUG,
        data=_xdg_base("XDG_DATA_HOME", home / ".local" / "share") / SLUG,
        cache=_xdg_base("XDG_CACHE_HOME", home / ".cache") / SLUG,
        logs=_xdg_base("XDG_STATE_HOME", home / ".local" / "state") / SLUG,
    )


def config_dir() -> Path:
    """``preferences.json``, ``debug.json``, layouts, favorites, presets."""
    return resolve_roots().config


def data_dir() -> Path:
    """Installed per-user payloads — currently just :func:`plugins_dir`."""
    return resolve_roots().data


def plugins_dir() -> Path:
    """The installed-plugins directory — where dropped-in external plugins live.

    The sanctioned home for out-of-repo plugins (wayfinder map #318, ticket
    #320): one folder per plugin with ``resources/plugInfo.json`` inside,
    same layout contract as the shipped tree.  Resolved at call time and
    created **on demand** (Preferences → Plugins → Open Plugins Folder) —
    never at boot, so a user who never installs a plugin sees no directory.
    """
    return data_dir() / "plugins"


def plugin_site_dir() -> Path:
    """The shared folder holding bundled wheels of enabled plugins (#350).

    One folder for every enabled plugin, rebuilt at startup when the winning
    set changes (the host's plugin-wheel rebuild).  Created on demand, never at boot.
    """
    return data_dir() / "plugin_site"


def cache_dir() -> Path:
    """Draft overlays and other regenerable caches."""
    return resolve_roots().cache


def drafts_dir() -> Path:
    """The draft-overlay sandbox — ``cache_dir()/drafts`` (all platforms)."""
    return cache_dir() / "drafts"


def plugin_data_dir(plugin_id: str) -> Path:
    """A plugin's own intermediate-file directory — cache-rooted, per plugin.

    ``cache_dir()/plugin_data/<plugin_id>/`` (wayfinder map #318, ticket
    #323): the sanctioned home for plugin working data that is neither a
    USD layer (draft overlays) nor a preference (``plugin_prefs/``) —
    SLAM keyframes, feature stores, tile caches.  Created on demand, so a
    plugin that never runs litters nothing.

    Retention deliberately diverges from the draft sandbox's orphan GC +
    7-day retention (#289): draft sessions are host-owned, host-readable
    crash recovery, while plugin data is opaque to the host — it cannot
    tell a mid-pipeline checkpoint from a temp file, and silently deleting
    it could destroy work.  The plugin owns its own retention; the host
    only owns the path.

    Plugins reach this through ``ctx.plugin_data_dir()`` or the
    package's module-level ``plugin_data_dir`` door — never by importing
    a private module directly (the bounded-context rule).

    Raises ``ValueError`` when *plugin_id* is not one safe path component.
    """
    d = plugin_data_root(plugin_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def plugin_data_root(plugin_id: str) -> Path:
    """The path :func:`plugin_data_dir` would use, without creating it.

    Uninstall reads this to delete a plugin's working data (#347) — it must
    not create the directory it is about to remove.  Same validation as
    :func:`plugin_data_dir`.
    """
    if (not plugin_id or not plugin_id.strip()
            or plugin_id in (".", "..")
            or "/" in plugin_id or "\\" in plugin_id):
        raise ValueError(
            f"plugin_id must be one safe path component: {plugin_id!r}")
    return cache_dir() / "plugin_data" / plugin_id


def log_dir() -> Path:
    """The rotating file log's directory."""
    return resolve_roots().logs


def ensure_dirs() -> Roots:
    """Create the three boot roots (parents included) and return them.

    The ``data`` root is deliberately absent — it only hosts installed
    plugins, which are created on demand (see :func:`plugins_dir`), so
    booting never litters ``~/.local/share`` for a user who installs
    nothing.

    A root that cannot be created is logged and skipped — the app starts
    degraded rather than refusing to boot.
    """
    roots = resolve_roots()
    logger = logging.getLogger(__name__)
    for path in (roots.config, roots.cache, roots.logs):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("cannot create %s: %s", path, exc)
    return roots
