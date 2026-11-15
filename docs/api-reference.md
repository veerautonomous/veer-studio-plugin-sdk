# Veer Studio Plugin SDK — API Reference

The complete reference for every class, method, and data structure the SDK
ships.  Written for someone who already knows Python and USD basics and
wants to know exactly what to override, what to call, and what comes back.

Start with the [author-guide](author-guide.md) if you have not built a
plugin yet — this file is the lookup, that file is the walkthrough.

```python
from veer_plugin_sdk import IToolProvider, ToolContext, ToolResult
```

## How to read this reference

**Two tiers of names.**  `export-manifest.json` pins the 70 names of the
stability contract — the names in `veer_plugin_sdk.__all__`, asserted by
`tests/test_surface.py`.  The package additionally exports *supporting
types* that the contract's own signatures refer to (`GizmoSpec`,
`FieldSpec`, `JobServiceInterface`, `LayerPermissionError`, …).  Both tiers
are importable from `veer_plugin_sdk`, both ship together, and both are
documented here; the tier matters only for contract-drift discussions in
the SDK issue tracker.

**Signatures.**  Methods marked **(abstract)** must be implemented — the
class cannot be instantiated without them.  Everything else has a working
default; override only what you need.  `self`/`cls` is omitted from
signatures below where it adds nothing.

**Optional callbacks.**  Context fields typed `Optional[Callable[...]]`
are wired by the host at runtime.  In your own unit tests they may be
`None` — guard before calling (`if ctx.get_ground_height is not None:`)
or inject your own through the `**overrides` factories in
[`veer_plugin_sdk.testing`](#7-testing-toolkit).

**Terms.**  *Port* = an ABC you implement to plug into the host.
*Context* = the dataclass the host hands you at runtime.  *Stage manager*
= the bounded write API (`StageManagerInterface`) — never reach around it.

---

## Contents

1. [Extension ports](#1-extension-ports) — what you implement
2. [Host services](#2-host-services) — interfaces you call
3. [Contexts](#3-contexts) — objects handed to you
4. [Result, report and metadata types](#4-result-report-and-metadata-types)
5. [Events](#5-events)
6. [Module-level helpers](#6-module-level-helpers)
7. [Testing toolkit](#7-testing-toolkit)
8. [Exported-name index](#8-exported-name-index)

---

# 1. Extension ports

All ports are `abc.ABC` subclasses.  You implement one or more of them and
register instances in your plugin's `register(registry)` function (see the
[author-guide](author-guide.md#plugin-anatomy)).

## IToolProvider

A tool that appears in the toolbar/FAB column.  The richest port — read
the lifecycle before the method list.

### Lifecycle

The host drives a tool in this order:

```
poll(ctx) / poll_reason(ctx)     availability (called on every selection change)
        │  True
        ▼
execute(ctx)                     user invoked the tool
        │
        ├─ returns FINISHED / CANCELLED / FAILED ──▶ status message; done
        │        (a tool that started a background job returns FINISHED
        │         while the job keeps running)
        │
        └─ returns RUNNING ──▶ activate(ctx)
                                   │
                                   ▼
                          process_event(ctx, event)   … per input event …
                                   │
                                   ├─ RUNNING      keep receiving events
                                   └─ terminal     deactivate(ctx)
```

`deactivate(ctx)` is also called when the user picks another tool or the
project closes.  Both `activate` and `deactivate` receive the context —
the host always passes it.

While active, the host also calls the mode, camera, dock, Escape and
creation-session hooks listed below.  Activation itself is refused (with
a status-bar message) when another tool holds the operation lock or a
background job owns the stage.

### Identity (abstract)

```python
def tool_id(self) -> str
```
Unique identifier, namespaced under the plugin name — e.g.
`"studio_cloud_cut.cut"`.  Stable across releases: it keys shortcuts,
workspace declarations (`vstudio.toolWorkspaces`), and persisted state.

```python
def display_name(self) -> str
```
Label on the toolbar button / menu item.  User-visible → keep it
localisable (a plain source string).

```python
def execute(self, context: ToolContext) -> ToolResult          # (abstract)
```
The entry point when the user invokes the tool.  Do the work here:
return a terminal `ToolResult` for a one-shot action, or `RUNNING` after
starting interactive work — the host then calls `activate()` and starts
feeding you `process_event()`.  A tool that kicks off a background job
returns `FINISHED` at once; the job is what keeps running.

### Availability

```python
@classmethod
def poll(cls, context: ToolContext) -> bool
```
`False` grays the tool out.  Default `True`.  The host calls this on the
instance (`tool.poll(ctx)`), so override it as a `classmethod` (matching
the declaration, works class- and instance-side) or as
`def poll(self, context)`.  Do the work here instead of handling
"can't run this" inside `execute`.

```python
@classmethod
def poll_reason(cls, context: ToolContext) -> Optional[str]
```
Why `poll` is `False`, as one user-facing sentence — shown on the
disabled button's tooltip and in the status bar if the user tries anyway.
Default `None` (generic message).  Keep it cheap: called on every
selection change alongside `poll`.

### Metadata (optional overrides)

```python
def icon_path(self) -> Optional[str]            # default None (text-only button)
def tool_description(self) -> str               # default display_name()
def tool_shortcut(self) -> str                  # default "" (no suggestion)
def preferred_camera_mode(self) -> str          # default "free_orbit"
```
`preferred_camera_mode()` returns one of:

| Value | Behaviour |
|---|---|
| `"free_orbit"` | no constraint (default) |
| `"top_down_2d"` | forced orthographic top-down; pan/zoom only |
| `"street_view"` | first-person perspective; the tool drives the camera |

Read on activate and after each mode transition.

```python
@property
def plugin_id(self) -> str
```
The owning plugin's name.  Set by the registry at registration — do not
set it yourself; read it when you need identity for permission-sensitive
calls.

### Modal / interactive support (optional overrides)

```python
def activate(self, context: ToolContext) -> None
```
Called when the tool becomes the active tool (only after `execute`
returned `RUNNING`).  Grab context here: stash `context`, register
overlays, set hints.

```python
def process_event(self, context: ToolContext, event: ToolEvent) -> ToolResult
```
One input event while active.  Return `RUNNING` to keep receiving
events; any terminal result ends the tool.  Default: `FINISHED`
(non-interactive).

```python
def deactivate(self, context: ToolContext) -> None
```
The tool is going away.  Unregister overlays, release the cursor, drop
state.  Receives the context — the signature must accept it.

```python
def activate_with_mode(self, context: ToolContext, mode: str) -> None
```
Activate with an initial mode (used when a FAB action declares one).
Default stores `self._initial_mode` and calls `activate()`.

### Sub-modes (optional overrides)

```python
def get_available_modes(self) -> list[tuple[str, str]]   # default []
def get_current_mode(self) -> str                        # default "default"
def on_mode_enter(self, mode_id: str) -> None            # default no-op
def on_mode_exit(self, mode_id: str) -> None             # default no-op
```
`get_available_modes()` returns `[(mode_id, display_name), ...]` — e.g.
the Spline Editor's `("split", "Split")`.  The host emits
`ToolModeChanged` around the enter/exit callbacks.

### Escape cascade (optional override)

```python
def on_cancel(self) -> Optional[str]
```
Called on Escape.  Return the *deepest* level you can handle; the
framework works up the rest of the cascade:

| Return | Meaning |
|---|---|
| `"operation_cancelled"` | an in-progress drag/operation was cancelled |
| `"mode_exited"` | current sub-mode exited, back to default |
| `"tool_deactivated"` | the tool should fully deactivate |
| `None` | nothing at this level — framework tries the next |

### Creation session (optional overrides)

Declaring a creation session hands Spacebar-repeat, the right-click tool
menu, and creation-Esc to the framework:

```python
def get_creation_session(self) -> Optional[CreationSession]  # default None
def on_creation_finish(self, context) -> ToolResult          # default RUNNING
def on_creation_discard(self, context) -> None               # default no-op
def on_creation_repeat(self, context) -> ToolResult          # default RUNNING
```

- **Finish** (`[Enter]` / menu) — accept the ghost geometry; terminal
  results auto-deactivate, `RUNNING` continues.
- **Discard** (`[Esc]` / menu) — throw the ghost away; the framework
  deactivates the tool either way.
- **Repeat** (`[Spacebar]`, one commit per press) — accept and keep
  going.

Return a `CreationSession` from `get_creation_session()` to switch these
on; `None` (default) keeps your own Esc/RMB behaviour.  See
[`CreationSession`](#creationsession).

### Save/Export session gate (optional overrides)

```python
def has_active_session(self) -> bool
def commit_active_session(self, context: ToolContext) -> ToolResult
```
While `has_active_session()` is `True`, Save/Export prompt
**Accept & Save / Abort** instead of running blindly.  Default: a creation
session is active.  Override and OR in your own transient state (active
drags, lift sessions).  `commit_active_session` runs the accept machinery
and ends the session — default routes to `on_creation_finish`.

### Workspace & dock hooks (optional overrides)

```python
def on_workspace_enter(self, workspace_id: str) -> None   # default no-op
def on_workspace_exit(self, workspace_id: str) -> None    # default no-op
def get_options_widget(self, parent)                      # default None
def get_auxiliary_dock_widget(self, parent=None)          # default None
def get_auxiliary_dock_title(self) -> str                 # default display_name()
```
`get_options_widget` returns a `QWidget` for the active-tool options bar
(`None` = nothing configurable).  `get_auxiliary_dock_widget` returns a
widget for the ~300 px auxiliary dock column beside the viewport while
the tool is active — the host shows it on activate, hides it on
deactivate; wire your own signals to drive your state machine.

### State persistence (optional overrides)

```python
def save_state(self) -> dict                    # default {}
def restore_state(self, state: dict) -> None    # default no-op
```
JSON-serializable dict for workspace restore.  Keep it small and
version-tolerant.

---

## IFileImporter

Converts an external file format into a USD layer — the Python-friendly
equivalent of a USD `FileFormat` plugin.  The host's import door runs
detection, permissions, the draft sandbox and SiteOrigin stamping around
your `import_file`.

### Abstract

```python
def supported_extensions(self) -> list[str]
```
e.g. `[".pcd", ".las"]`.  Multiple importers may claim one extension;
the host disambiguates by content.

```python
def import_file(self, source_path: str, dest_layer_path: str,
                options: dict) -> str                    # (abstract)
```
Convert *source_path* into a USD layer at *dest_layer_path* (a
project-relative path such as `"Reality/PointClouds/slam_cloud.usda"`).
*options* carries the values collected from `import_options()`.  Returns
the path actually written.

Raises `FileNotFoundError` (missing source), `ValueError` (malformed or
unsupported input), `RuntimeError` (conversion failed).

### Optional overrides

```python
def destination_category(self) -> str | None             # default None
```
The project category directory the layer lands under — one of
`"Reality/PointClouds"`, `"Reference"`, `"Navigation"` (resolved back
from the directory by the host).  **`None` refuses the import** (the door
has nowhere to write), so override this.

```python
def dest_layer_name(self, source_path: str) -> str | None   # default None
```
Bare file name for this run's layer.  Default `None` = `<basename>.usda`
(same basename ⇒ shared layer).  Return a per-run name (conventionally
`run_<id>`) when successive runs must not clobber each other.

```python
def import_options(self) -> Optional[dict]              # default None
```
Schema for the Import dialog, which auto-builds the widgets and collects
values into the `options` dict:

```python
{
    "downsample": {
        "type": "choice",            # choice | string | int | float | bool
        "label": "Downsample ratio",
        "default": 0.1,
        "choices": [{"value": 0.1, "label": "10 %"},
                    {"value": 1.0, "label": "Keep all"}],
        # "placeholder": "..."                       # string
        # "show_when": {"mode": "advanced"}          # conditional show
    }
}
```

```python
def unavailable_reason(self, stage) -> Optional[str]    # default None
```
Non-`None` disables this importer for the current stage and shows the
reason in the Import dialog.  Product surface only — the domain still
refuses behind the UI gate.

```python
def writes_map_layer(self, source_path: str, options: dict) -> bool   # default True
```
`False` = this call writes only sibling files, not the destination layer;
the door then skips scaffolding/gating entirely.

```python
def wants_unit_name(self) -> bool                       # default False
```
`True` asks the host to mint a fresh `options["unit_name"]`
(`Cloud_<8 hex>`), free on the composed stage.  For cloud importers that
author one unit frame per patch.  You mint your own when the key is absent.

```python
def wants_site_origin(self) -> bool                     # default False
```
`True` makes the door inject `options["existing_site_origin"]` and
`options["site_origin"]` when a map SiteOrigin exists.  Declaring it does
not force a coordinate mode.

```python
def import_tile_batch(self, dest_layer_path: str, tiles: list,
                      unit_name: str, display_name: str) -> str
```
Write several sources as *one* merged cloud unit.  *tiles* is
`[(source_path, options), ...]`.  Default raises `NotImplementedError`
(cannot merge).

```python
@property
def plugin_id(self) -> str                             # set by registry
```

### Import vocabulary (contract)

Everything an `import_file` implementation stamps or derives ships in the
package — these run *inside* the door, where there is no ToolContext, so
they are module-level names, never `ctx.` capabilities:

| Name | What it is |
|---|---|
| `ATTR_IMPORT_MODE` | `atlas:importMode` token — how the source was placed (`auto_center`, `declared_origin`, …) |
| `ATTR_SOURCE_CRS` | `atlas:sourceCoordinateSystem` string (e.g. `"MGRS_local_metres:54SVE"`) |
| `ATTR_IMPORT_TRANSFORM` | `atlas:importTransform` `Matrix4d` — source→stage, baked into the points |
| `SiteOrigin` | the declared-origin record: fields `anchor_mode` / `anchor_lat` / `anchor_lon` / `anchor_ele` / `utm_zone` / `utm_hemisphere` / `z_shift` / `mgrs_grid` / `source`; `SiteOrigin.from_layer(...)` / `.write_to_layer(...)` take any object carrying `customLayerData`; `.grid_reference` and `.utm_epsg` derive |
| `source_key_for(path)` | the slug a source file registers under — no `/`, no `;`, never bare 32-hex |
| `imported_source_id(source_key, kind, id)` | `<sourceKey>/<kind>/<id>` — one provenance assertion (kinds: `node`, `way`, `relation`, `file`, `tile`) |
| `pointcloud_frame_path(index)` | `<site>/Reality/PointClouds/PointCloudFrame_NNN` — the tile frame an import authors |
| `color_field_prim_path(index)` | `<site>/Reality/ColorFields/ColorField_<N>` — one colour chunk |

The two roots those helpers resolve through — `pointclouds_root()`,
`colorfields_root()` — are contract too (§6 Project roots).  In-host,
`from core.contexts import SiteOrigin, ATTR_IMPORT_MODE, …` still works:
the definitions live with the static import vocabulary in `core.ports`
and the original modules re-import them.

---

## IStageContributor

Owns a named sublayer in the stage's layer stack: create it if missing,
keep it positioned, flush on close.

```python
def layer_name(self) -> str                            # (abstract)
```
Logical name, e.g. `"slam_cloud"`.

```python
def default_layer_path(self) -> str                    # (abstract)
```
Path relative to the stage directory, e.g.
`"slam_toolpack/cloud.usda"`.

```python
def on_stage_opened(self, stage_mgr: StageManagerInterface) -> None    # (abstract)
```
Ensure the sublayer exists and sits correctly in the stack.

```python
def on_stage_closing(self, stage_mgr: StageManagerInterface) -> None   # (abstract)
```
Flush / save before the stage goes away.

```python
def layer_strategy(self) -> str                        # default "draft_overlay"
```
`"draft_overlay" | "create_new" | "read_only"` — programmatic fallback;
a `plugInfo.json` `layers` declaration takes precedence.

```python
@property
def plugin_id(self) -> str                             # set by registry
```

---

## IPanelFactory

Creates a Qt dock widget for the main window.  The only port with an
inherent Qt dependency (the module itself imports without Qt).

```python
def panel_id(self) -> str                              # (abstract)
def display_name(self) -> str                          # (abstract)
def create_panel(self, parent, context: PanelContext)  # (abstract)
```
Build and return a `QDockWidget`.  *parent* is the `QMainWindow`;
*context* carries stage access and change signals.

```python
def default_area(self) -> str                          # default "right"
```
`"left" | "right" | "bottom"`.

---

## IInspectorSectionProvider

Contributes domain sections to the Properties panel's spine (the host
keeps the header, meta line, edit gate and section frame; your sections
render inside the domain band).

```python
def provides(self, prim) -> bool                       # (abstract)
```
Whether this provider renders sections for *prim*.

```python
def sections(self, context: EditorContext, prim) -> list[SectionSpec]   # (abstract)
```
The sections for *prim*; empty when it has none.  Re-runs on every
inspect, save commit and locale change — build specs fresh each call
(run labels through `context.translate` while building).

**Custom widget body protocol.**  A `SectionSpec.widget_factory` body the
host drives:

| Member | Role |
|---|---|
| `begin_edit_session()` | open: snapshot values, enable fields |
| `edit_session_dirty() -> bool` | anything unsaved? |
| `end_edit_session(action)` | `"save"` writes buffered changes; `"cancel"` / `"discard"` revert the form |
| `deactivate()` | teardown — clear external state (hover highlights) |
| `read_only = True` (class attr) | body can never dirty a session; keeps it out of the pencil's eligibility |
| `content_changed` (Qt signal, optional) | emit when edits bypass `FieldSpec` signals (e.g. a tag table) so Save arms immediately |

Raise [`SectionSaveRefused`](#sectionsaverefused) inside `end("save")`
to refuse the write — the host rolls the bracket back and shows
`str(exc)`.

### SectionSpec

```python
@dataclass(frozen=True)
class SectionSpec:
    id: str                       # unique across providers; keys persisted open/closed state
    domain: str                   # one of SECTION_DOMAINS
    title: str                    # source string; translate while building
    default_open: bool = True
    order: int = 100              # coarse; multiples of 10; ties → registration order
    fields: tuple[FieldSpec, ...] = ()
    widget_factory: Callable[[EditorContext, Any], Any] | None = None
    actions: tuple[PrimAction, ...] = ()   # header ⋮ launcher entries (outside the edit gate)
```

Invalid `domain` or empty `title` raises `ValueError` at construction.

```python
SECTION_DOMAINS = frozenset({"navigation", "reality", "reference",
                             "atlas", "host"})
```
The band a section renders in.  `host` is reserved; a plugin declaring it
still lands in the domain band and the host logs a warning.  `atlas` is
reserved for the planned post-1.0 Atlas layer (not shipped).

### FieldSpec

```python
@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str                    # source string; translate while building
    kind: str                     # one of SECTION_FIELD_KINDS
    get: Callable[[Any], Any]     # prim -> widget value; None = key absent → displays "—"
    apply: Callable[[Any, Any], None]   # (prim, value); value None removes the attribute
    unit: str = ""                # value suffix (" km/h")
    choices: tuple[str, ...] = ()
    read_only: bool = False
    minimum: float | None = None  # spin-box range (numeric kinds)
    maximum: float | None = None
    step: float | None = None
    live: bool = False            # writes through as edited (viewport follows live);
                                  # every other field buffers until Save
```

```python
SECTION_FIELD_KINDS = frozenset({"text", "int", "float", "choice",
                                 "tags", "tristate"})
```
Unknown `kind` raises `ValueError` at construction.

### PrimAction

```python
@dataclass(frozen=True)
class PrimAction:
    label: str
    callback: Callable[[], None]   # runs at once, outside the edit gate; may start a tool
```
One launchpad too large for a row; the host collects section actions into
the header's ⋮ launcher.

### SectionSaveRefused

```python
class SectionSaveRefused(Exception)
```
Raise inside a factory's `end("save")` to refuse the write — nothing
lands, earlier writes in the same bracket vanish, the session stays open.

---

## IPluginPreferences

Persistent settings for a plugin, auto-persisted to
`~/.config/veer-studio/plugin_prefs/{plugin_id}.json` and loaded into
contexts as the `preferences` dict.

```python
def fields(self) -> dict                              # (abstract)
```
`{field_name: FieldDef}` where a FieldDef is
`{"type": str, "default": Any, "label": str, "choices": list | None}`.
The framework auto-generates the settings UI.

```python
def create_preferences_widget(self, parent, values: dict)   # default None
```
Optional custom widget; `None` keeps the generated one.

```python
@property
def plugin_id(self) -> str    # must match the plugin's folder name; set by registry
```

---

## IValidator

Read-only validation pass over the composed stage (runs before export or
on explicit request).  Never modifies prims.

```python
def validator_id(self) -> str                         # (abstract)
def display_name(self) -> str                         # (abstract)
def validate(self, stage, stage_mgr: StageManagerInterface) -> ValidationReport   # (abstract)
```

---

## IExporter

Output-side counterpart of `IFileImporter`: USD → external format
(Lanelet2 `.osm`, OpenDRIVE `.xodr`, Nav2 `.pgm`+`.yaml`, GeoJSON, …).

```python
def exporter_id(self) -> str                          # (abstract)
def display_name(self) -> str                         # (abstract)
def export_format(self) -> str                        # (abstract)
```
File extension produced, e.g. `".osm"`; `""` when the export is a folder
of files (the dialog then offers a folder picker).

```python
def export_stage(self, stage, stage_mgr: StageManagerInterface,
                 output_path: str, options: dict) -> ExportReport    # (abstract)
```

---

## IFusionPlugin

Reactive pass: listens to prim mutations and resolves cross-layer
relationships (snap-to-ground, approach-lanelet wiring, …).

**This is the highest-cost port** — every prim mutation calls
`prim_filter()`.  Scope hard with `prim_filter` and switch the whole
plugin off with `poll`.

```python
def fusion_id(self) -> str                            # (abstract)
def display_name(self) -> str                         # (abstract)
def prim_filter(self, prim) -> bool                   # (abstract)
```
The primary performance guard — return `False` to skip quickly.

```python
def on_mutation(self, prim, mutation_ctx: StageMutationContext) -> None   # (abstract)
```
Called after a filtered prim was created or modified.  Writes go through
*mutation_ctx* so they land on the right edit target in one change block.
**Always start with the originator guard:**

```python
if mutation_ctx.originator_id == self.fusion_id:
    return   # I caused this — don't react to myself (prevents loops)
```

```python
@classmethod
def poll(cls, stage_mgr: StageManagerInterface) -> bool   # default True
def priority(self) -> int                                 # default 100 (lower = earlier)
```

---

## IIntegrationPlugin

Cross-layer relationship wiring on stage open/close — runs **after** all
contributors finished `on_stage_opened` (every layer in the stack) and
**before** any contributor's `on_stage_closing` (cross-layer data still
intact).

```python
def integration_id(self) -> str                        # (abstract)
def display_name(self) -> str                          # (abstract)
def on_stage_opened(self, stage_mgr: StageManagerInterface) -> None    # (abstract)
def on_stage_closing(self, stage_mgr: StageManagerInterface) -> None   # (abstract)
```

---

## IAssemblyProvider

Declares the behavioural contract (schema-only) for an assembly subtype —
maps an `hdmap:subtype` value to an `AssemblySchema`.

```python
def assembly_id(self) -> str                           # (abstract)
def display_name(self) -> str                          # (abstract)
def subtype_token(self) -> str                         # (abstract)
def get_schema(self) -> AssemblySchema | None          # (abstract)
```
`None` = "applies, but nothing to stamp".

```python
@classmethod
def poll(cls, stage_mgr) -> bool                       # default True
def get_terminals(self) -> list                        # default []
def prim_path_prefix(self) -> str                      # default: core.paths.assets_root()
```
`get_terminals()` returns the terminal/pin manifest (Lanelet2 role → USD
relationship, direction, multiplicity, accepted types).  `prim_path_prefix`
names where instances live; **the default imports `core.paths`, which only
exists inside the host — override it in code you unit-test standalone;
`veer_plugin_sdk.paths.assets_root()` is the portable value.**

---

## IUnsavedStateProvider

Opt-in port for unsaved state held *outside* USD layers (an authority
store, a sidecar queue).  If any registered provider returns `True`, the
title-bar dirty dot lights and the close-prompt fires.

```python
def has_unsaved_state(self) -> bool                    # (abstract)
```

---

# 2. Host services

Interfaces the host hands you inside contexts.  You call these; you never
implement them.

## StageManagerInterface

The bounded write API — `ctx.stage_manager`.  A subset of the host's real
StageManager: only operations plugins are allowed to perform, so nothing
here can corrupt stage state.

### Layer stack & saving

```python
def add_sublayer(self, layer_path: str, position: int = -1) -> None
```
Insert into the root's sublayer stack.  `-1` appends (bottom), `0`
prepends (top).

```python
def set_edit_target(self, layer_path: str) -> None
```
Subsequent prim/attribute writes go to this layer.

```python
def save_layer(self, layer_path: str) -> None
def save_stage(self) -> None                          # all dirty layers
def get_layer_paths(self) -> list[str]                # ordered sublayer paths
def get_layer_by_identifier(self, identifier: str)    # -> Sdf.Layer | None
def get_project_dir(self) -> str                      # parent of root .usda; "" when none
def get_stage(self) -> Usd.Stage                      # composed stage; None when closed
```

### Draft overlays (the sandbox for unsaved work)

Writes go to a draft overlay in the session temp dir; Save merges the
draft into the original project file; Discard reverts.

```python
def get_draft_layer_path(self, original_path: str) -> str | None
```
Existing draft overlay for *original_path*, or `None`.

```python
def ensure_draft_overlay(self, original_path: str) -> str | None
```
Create it lazily (overlay + scaffold + sublayer wiring) if needed.
**Use this instead of `get_draft_layer_path` whenever your tool may write
to a layer that has no overlay yet.**

```python
def ensure_editable_layer(self, layer_path: str) -> str | None
```
Like `ensure_draft_overlay` but also promotes a `read_only`-strategy
layer to `draft_overlay` first.

```python
def ensure_editable_category(self, category: str) -> str | None
```
Find the category's layer in `subLayerPaths` (with cache-path fallback),
give it a writable draft, set the edit target, return the draft path.
Tools call this once on activation.

```python
def ensure_named_category_layer(self, category: str, file_name: str) -> str | None
```
Layer-birth door: create `<category>/<file_name>` if missing, wire it
into the root sublayers, return its draft.  Bare file names only.
(Most plugins reach this through
`ToolContext.create_named_category_layer`, which also checks permissions.)

```python
def ensure_editable_prim(self, prim_path: str) -> str | None
```
Make the strongest layer owning *prim_path* writable and return its draft.
**Does not change the edit target** — pair with `edit_target_scope` /
`set_edit_target`.  Replaces the manual prim-stack dance.

```python
def is_draft_path(self, layer_path: str) -> bool
```
`True` when the path already lives inside the draft session — set the
edit target directly rather than stacking another overlay.

```python
def save_draft_overlays(self) -> int
```
Flush in-memory drafts to disk (crash protection).  Call at tool-finish
boundaries.  Returns the number saved.

### Dirty state & checkpoints

```python
def mark_dirty(self) -> None
def mark_dirty_layer(self, layer_id: str = None) -> None
def is_dirty(self) -> bool
def has_unsaved_layers(self) -> bool                  # what Save would write; shares the title-dot signal
def create_checkpoint(self, label: str = "") -> str   # snapshot dirty drafts; returns a token
```

### Spatial & domain queries

```python
def find_point_cloud(self)                            # leaf UsdGeom.Points | None
def find_all_point_clouds(self) -> list               # [Usd.Prim, ...]
def find_point_cloud_frame(self)                      # /PointCloudFrame Xform | None
def get_ground_height_at(self, x: float, y: float) -> float
def has_ground_mesh(self) -> bool
def read_site_origin(self)                            # SiteOrigin | None
def create_atlas_prim(self, atlas_type_name: str, position, **kwargs) -> str
```
Create a prim in the Atlas object-identity system at *position*
(`Gf.Vec3d`); returns the new `Sdf.Path` string.  **Atlas is a planned
post-1.0 map layer and has not shipped** — new plugins should author
current map content through its own layer's doors instead.  In particular,
do not model navigation content with this: regulatory elements (traffic
lights, stop lines, crosswalks) live in `Navigation` and carry no Atlas
identity.

```python
def notify_prims_modified(self, prim_paths: list[str]) -> None
```
Tell the host you wrote prims outside the normal CRUD flow — it forwards
to fusion-plugin notification.  Call this after out-of-band writes.

### Deletion

```python
def delete_prim(self, prim_path: str, plugin_id: str = "",
                checkpoint=None) -> bool
```
**The single choke-point for prim deletion** — never call
`stage.RemovePrim()` directly.  Removes the prim from every layer
holding a spec (through drafts when live), checks `plugin_id` against
each layer's declared write permissions first, marks the stage dirty.
Pass an undo `checkpoint` to make the whole delete one Ctrl+Z step.
Returns whether the prim left composition.

---

## GizmoManagerInterface

The shared transform-gizmo surface — one instance per viewport at
`ctx.gizmo_manager`.  The surface owns handle geometry, projection and
drag math; you declare handles and apply the deltas you get back.

```python
def show(self, spec: GizmoSpec) -> None
```
Draw *spec*'s handles; re-callable mid-drag to move the pivot.  Also the
visibility door — off-screen handles pan the camera back on screen.

```python
def hide(self) -> None
```
Remove handles, abandon any in-flight drag.

```python
def hit_test(self, screen_x: float, screen_y: float) -> Optional[GizmoHit]
```
Nearest handle within its family's hit radius, else `None`.  The hit is
retained as hovered (render brightens it) until the next `hit_test` or a
`hide`.  Logical widget pixels; device-pixel conversion happens inside.

```python
def begin_drag(self, hit: GizmoHit) -> None
def update_drag(self, screen_x: float, screen_y: float) -> Optional[GizmoDelta]
def end_drag(self) -> None
```
`update_drag` returns the delta from the drag origin to this position —
`None` when not dragging or before the first rendered frame.  Handles
stay shown after `end_drag`.

### GizmoSpec

```python
@dataclass(frozen=True)
class GizmoSpec:
    center: Gf.Vec3d              # pivot, stage-native world space
    translate_axes: tuple = ()    # e.g. ("x", "y")
    rotate_axes: tuple = ()       # axes to rotate AROUND; ("z",) = XY-plane arc
    scale_axes: tuple = ()        # non-empty also draws the uniform centre handle
    bbox: Optional[tuple] = None  # world-space (lo, hi) dashed wireframe behind handles
    orientation: Optional[Gf.Matrix4d] = None   # rotation-only frame; None = stage-aligned
    bbox_matrix: Optional[Gf.Matrix4d] = None   # transform applied when drawing bbox
```
Axes are the *spec frame's* axes; pass `orientation` to point handles
along a rotated selection.  A family with no axes is **omitted, never
dimmed**.  There is deliberately no per-prim Local/Global toggle — the
tool's single rotation is the one frame.

### GizmoHit

```python
@dataclass(frozen=True)
class GizmoHit:
    handle_id: str     # "translate_x" | "rotate_z" | "scale_y" | "scale_uniform"
    position: tuple    # press position in logical widget pixels (drag origin)
```

### GizmoDelta

```python
@dataclass(frozen=True)
class GizmoDelta:
    kind: str                      # "translate" | "rotate" | "scale"
    handle_id: str
    translation: Optional[Any] = None     # world metres along the handle axis (translate)
    rotation_axis: Optional[Any] = None   # unit axis (rotate)
    angle_deg: float = 0.0                # (rotate)
    scale_factor: float = 1.0             # (scale; handle_id says which axis)
```
Raw — snapping, preview composition and every USD write belong to you.

---

## JobServiceInterface

The host's background-job slot at `ctx.jobs`.  **Plugins never spawn
pipelines themselves** — the host owns progress UI, cancellation, the
stage pin, and process-tree lifecycle (same shape as Blender's WM_jobs).
`None` in unit tests.

```python
def start(self, spec: JobSpec) -> None
```
Start *spec*; pins the stage for the run's duration.  Raises
`RuntimeError` if a job is already running or *spec* cannot start.

```python
def cancel(self) -> None
```
stdin `cancel` → grace → tree kill.  No-op when idle.

```python
def cancel_and_revert(self) -> None
```
Cancel, then run the spec's `undo_revert` once the child dies (the
mid-flight Ctrl+Z contract).

```python
def is_running(self) -> bool
def is_canceling(self) -> bool
def active_spec(self) -> Optional[JobSpec]
```

### JobSpec

```python
@dataclass
class JobSpec:
    argv: list[str]                     # program + args; argv[0] executable
    cwd: str = ""                       # "" inherits the app's
    name: str = ""                      # display name on the status-bar job progress
    plugin_id: str = ""                 # owning plugin — the pin admits ONLY this id's
                                        # ToolContext.stage_pin_exempt() while the job
                                        # runs; empty for host-owned jobs  (new in 1.2.0)
    env: Optional[dict] = None          # layered over the inherited env
    on_progress: Optional[Callable[[str, int, int], None]] = None    # (text, value, max), ~1 Hz
    on_chunks: Optional[Callable[[list], None]] = None               # coalesced chunk batch, ~1 Hz
    on_log: Optional[Callable[[str], None]] = None                   # one stderr/stdout log line
    on_finished: Optional[Callable[[int, str, bool], None]] = None   # (exit_code, stderr_tail, cancelled) — once per run
    on_error: Optional[Callable[[str], None]] = None                 # spawn error / stall / nonzero exit
    undo_revert: Optional[Callable[[], None]] = None                 # cancel, then restore pre-job state
    undo_commit: Optional[Callable[[], None]] = None                 # fold the run into ONE undo step
    chunk_interval_ms: int = 1000                                    # coalescing tick
    stall_ms: Optional[int] = None                                   # silence limit; None = service default (60 s)
```

Every callback fires on the GUI thread from Qt-signal handlers — never
from the child process.  The child speaks a JSON-lines protocol on
stdout (one object per line, flushed):

```json
{"type": "progress", "text": "...", "value": 4, "max": 10}
{"type": "chunk",  ...payload...}
{"type": "log",    "message": "..."}
{"type": "error",  "message": "..."}
```

stderr is free-form log text (tail preserved for failure reports).
`on_chunks` batches at ~1 Hz so a fast producer cannot flood the GUI.

---

# 3. Contexts

Dataclasses the host constructs and passes to your port methods.  You read
fields and call callbacks; you never build one yourself outside tests
(`veer_plugin_sdk.testing` does exactly that for tests).

## ToolContext

Passed to `execute` / `poll` / `activate` / `process_event` / the
creation-session hooks.

### Stage access & identity

| Field | Type | Meaning |
|---|---|---|
| `stage` | `Usd.Stage` | the composed stage (read freely; write through doors) |
| `stage_manager` | `StageManagerInterface` | the bounded write API |
| `plugin_id` | `str` | owning plugin (`""` for host operations) |
| `project_dir` | `str` | project directory of the open map |
| `preferences` | `dict` | this plugin's persisted preferences |
| `plugin_data_dir` | `Optional[Callable[[], str]]` | your intermediate-file directory (created on demand; host owns the path, you own contents/retention).  Raises `ValueError` on a host context |

### Selection

| Field | Signature / type | Meaning |
|---|---|---|
| `selection` | `list` | primary selected prim path |
| `selection_set` | `list` | full multi-selection snapshot, primary first |
| `get_selection_set` | `() -> list[str]` | **live** re-read — use this after you mutate the set mid-session |
| `set_selection_set` | `(paths, primary=None) -> None` | replace the multi-selection; keeps viewport, tree and inspector in sync |
| `on_selection_changed` | `(sel) -> None` | subscribe to selection changes |

### Ground & spatial queries

| Field | Signature | Returns |
|---|---|---|
| `get_ground_height` | `(x, y) -> float` | ground Z at world (x, y) |
| `has_ground_mesh` | `() -> bool` | any ground mesh on the stage? |
| `has_ground_mesh_at` | `(x, y) -> bool` | overlap test (True when no mesh exists) |
| `get_ground_mesh_height` | `(x, y) -> float \| None` | surface Z only; `None` where no mesh covers the point |
| `build_ground_mesh_cache` | `() -> dict \| None` | KD-tree cache built once per GroundSurface |
| `find_nearest_prim` | `(x, y, z) -> str \| None` | nearest prim path |
| `find_prims_in_radius` | `(x, y, z, r) -> [(path, dist), ...]` | prims within radius |
| `screen_to_world` | `(sx, sy, w, h, frustum) -> (origin, direction) \| (None, None)` | pick ray |
| `get_world_center` | `(prim_path) -> Gf.Vec3d \| None` | prim's world-space centre |

### Georeferencing & clouds

| Field | Signature | Meaning |
|---|---|---|
| `latlon_to_local_enu` | `(lat, lon, ele=0.0, *, origin) -> (x, y, z)` | WGS84 → local ENU; `origin` (SiteOrigin) **required** — `None` raises `ValueError` |
| `cloud_units` | `(roles=None, current_only=False) -> list[CloudUnit]` | cloud discovery; pass `GEOMETRIC_ROLES` to keep only geometric-derivation-readable clouds.  Returns [`CloudUnit`](#cloudunit-in-the-70-name-contract) records |

### Identity and navigation queries

```python
is_atlas_object   : (prim_path) -> bool
get_atlas_type    : (prim_path) -> str | None
get_atlas_object_id: (prim_path) -> str | None
is_navigable_target: (prim_path) -> bool
get_assembly_terminals: (prim_path) -> list[AssemblyTerminal] | None
```

The `is_atlas_*` / `get_atlas_*` names anticipate the **Atlas** layer — a
planned post-1.0 fourth map layer that has not shipped.  They are
contract-stable API, but not a current workflow: don't build 1.x features
on them.  `is_navigable_target` and `get_assembly_terminals` are the
Navigation-facing queries of this group.

### Import & point-cloud doors

```python
import_file: (source_path, options=None) -> dict
```
Run a source file through the host's full import pipeline (detection,
re-import gate, permission check, draft sandbox, SiteOrigin stamp).
Returns `{"result_path", "error", "warnings", "imported"}`.  With no
confirm callback the gate refuses (`ImportGateRefused`) rather than
prompting when user-authored content is at risk.

```python
upsert_point_cloud_tile: (tile_name, status, crate_path=None,
                          placement=None, *, layer_name) -> prim_path
```
Stream one tile into `Reality/PointClouds`.  *layer_name* (required) is
the run's layer file name — the same one `dest_layer_name` resolves to,
so streaming and full import share one file.  *tile_name* is the
canonical compass name (`"1W_2N"`, origin `"0_0"`); *status* is
`provisional | closed | final`; *crate_path* is an optional tile crate
whose `/PointCloud` the tile references — Save copies it into the project
and re-points the reference; *placement* is an optional 16-float row-major
frame; `z_range` `(min, max)` and `xy_range` `(xmin, ymin, xmax, ymax)`
author the extent (z_range needs a crate_path; xy_range needs a z_range).
Gated by your `permissions.write`; lands in the draft (disk at Save);
raises `ValueError` on a bad name/status.

```python
consolidate_point_cloud_run: (layer_name, crate_path, *, placement=None,
                              z_range=None, xy_range=None)
```
Replace one run's streamed tile frames with a single precise cloud
referencing the consolidated crate.  Both `z_range` and `xy_range` are
required (they set the extent).  Refuses a placed write without a
georeferenced SiteOrigin — before any write.  Other runs untouched.

```python
discard_point_cloud_run: (layer_name) -> count
```
Remove every tile frame of *layer_name* (failed/cancelled run cleanup).
Other runs untouched.

### Derived-cloud replace doors

```python
derive_cloud: (source, points, *, tool_id, name=None, display_name=None,
               parameters=None, colors=None) -> DerivedCloudHandle
revert_derived_clouds: (handles) -> None
```

`derive_cloud` is the one-call replacement for a cloud's points: it
births a derived unit from *points*, retires the source (the derived
unit becomes its lineage's current), and mutes the source for the
session so the viewport drops it at once.  *source* is a frame path or a
`CloudUnit`; *points* are in the source's own frame (invert the frame's
world transform first — `UsdGeom.XformCache`, as every in-host caller
does).  *tool_id* stamps provenance on the derived frame.  *colors*,
when given, are per-point; a source with per-point colours and a write
that brings none raises `ValueError` rather than silently dropping them.

Draft resolution, the `Reality/PointClouds` permission gate
(`LayerPermissionError` without the category) and the draft-aware
promote resolver all run inside — you never open `edit_target_scope`
for this write.  Returns a `DerivedCloudHandle`, a frozen record:
`source_path`, `derived_path`, and `prior_visibility` (the source's
session-visibility capture — treat it as opaque).

`revert_derived_clouds(handles)` takes a batch of handles back in the
order the domain requires: unmute every source first (a mute restores
only while its prim composes), delete every derived unit, then make the
entry clouds current again — a source the batch itself derived is
already gone, so it is not re-promoted.  Handles are single-use.

Both are write doors: `None` in `tool_context()`.

### Overlays, cursor & status UI

```python
register_overlay(renderer)     -> None     # add to the viewport overlay stack
unregister_overlay(renderer)  -> None     # remove by renderer
request_cursor(state_name)     -> None     # e.g. "crosshair"
release_cursor()               -> None     # release your cursor request
request_viewport_repaint()     -> None     # repaint after your overlay/state changes
show_status(message, timeout_ms=3000)      # transient status-bar message
set_tool_hints(text)           -> None     # persistent hints ("" clears)
show_progress(text, value, max)            # status-bar zone 5
hide_progress()                -> None     # call on success AND failure —
                                           # a bar stuck at 3/7 reads as hung
frame_prim(prim_path)          -> None     # fly the camera to a prim
snapshot_camera() -> dict                  # capture for later restore
restore_camera(state)          -> None
set_auxiliary_dock(widget, title)          # show a widget in the auxiliary dock
clear_auxiliary_dock()          -> None
request_deactivate()            -> None     # ask the host to deactivate this tool
request_tree_refresh()          -> None     # scene tree picks up stage changes now
```

`viewport` is the host's widget handle — **never touch it**; ask for a
repaint through `request_viewport_repaint()`.  It is `None` in unit tests.

### Menus

```python
register_prim_menu_entry(entry)        # viewport RMB prim context-menu entry
register_edit_session_entry(entry)     # double-click edit-session dispatcher
```

### Undo

```python
push_undo(command)                       # push an UndoCommand onto the global stack
create_undo_checkpoint(layer_path, description, source_id) -> UndoCommand
create_multi_undo_checkpoint(description, source_id) -> UndoCommand
create_edit_scope(layer_path, description, source_id) -> EditScope
```
`create_multi_undo_checkpoint` spans N layers as one Ctrl+Z: call
`capture_before(layer)` immediately before your first write to each
layer, `capture_after(layer)` for every captured layer at commit, and
`revert_to_before(stage_manager)` as the Cancel door.  `create_edit_scope`
is a context manager:

```python
with ctx.create_edit_scope(draft_path, "drag vertex") as scope:
    scope.track_prim(prim_path)
    pts_attr.Set(...)
```

### Mesh regeneration

```python
regenerate_meshes(mesh_prim_paths=None, *, recipes=None, extra_border=None)
    -> list[MeshRegenOutcome]
```
Replace-only, recipe-driven regeneration; one outcome per requested mesh
with status `"regenerated" | "no_recipe" | "error"`.  A Save seeing any
`"error"` refuses the whole Save.  Progress flows through
`show_progress`/`hide_progress`.

```python
regenerate_mesh_in_job(prim_path, *, on_done, provided=None,
                       extra=(), absorb=()) -> None
```
Background ground regeneration: the derivation runs as a host job (stage
pinned, progress/cancel on the job bar) and the single write lands at the
end.  `on_done` runs once on the GUI thread with
`"regenerated" | "error" | "no_recipe" | "cancelled"`.  Raises
`RuntimeError` when another background job holds the slot — then `on_done`
is not called.

### Services

```python
gizmo_manager: GizmoManagerInterface      # the shared gizmo surface
jobs: JobServiceInterface                  # background jobs (None in unit tests)
```

### i18n

```python
translate: Optional[Callable[[str, str], str]]   # (context, source_text) -> text
current_locale: str = "en"                       # e.g. "en", "zh_CN", "ja_JP"
```

### Methods

```python
def edit_target_scope(self, layer_path: str)
```
Context manager redirecting the edit target to *layer_path* (resolved by
absolute-path match, never substring).  Enforces your declared
`permissions.write` — raises [`LayerPermissionError`](#layerpermissionerror)
when the layer's category is not in your list — refuses locked layers,
and unlocks an authorised one so USD writes succeed.

```python
with ctx.edit_target_scope("/path/to/layer.usda"):
    stage.DefinePrim(...)
```
Restores the previous target on exit, including on exception.  **Use this
instead of hand-rolled `GetEditTarget`/`SetEditTarget` pairs** — a missing
`finally` leaks the edit target for the rest of the session.  A draft
layer's own path has no category; the check resolves back to the project
layer it overlays.

```python
def create_named_category_layer(self, file_name: str, category: str) -> str | None
```
Layer-birth door: create `<category>/<file_name>` when missing, wire it
into the root sublayers, return the draft overlay (author through it;
Save merges).  Enforces `permissions.write` with the plugin_id stamped at
call time.  *file_name* must be bare — a nested path raises `ValueError`.
Raises `RuntimeError` when no stage manager / no draft session.

```python
def stage_pin_exempt(self)
```
The stage-pin door: a context manager for authoring **while your own
background job holds the pin** *(new in 1.2.0)*.

```python
with ctx.stage_pin_exempt():
    ...   # writes that belong to this job's run
```

With no pin in force it is a no-op yield.  While a job runs, it yields
only when this context's `plugin_id` equals the job's
`JobSpec.plugin_id`; anyone else gets `StagePinnedError` naming the
holder.  The gate is *ownership*, not a declared permission — the key
exists only while your own job runs, so a plugin can never open the lock
on someone else's write.  (This replaced the old module-level
`stage_pin_exempt` re-export, which handed the raw door to every caller.)

---

## PanelContext

Passed to `IPanelFactory.create_panel()`.

| Field | Type | Meaning |
|---|---|---|
| `stage` | `Usd.Stage` | composed stage |
| `stage_manager` | `StageManagerInterface` | bounded writes |
| `project_dir` | `str` | project directory |
| `preferences` | `dict` | owning plugin's preferences |
| `plugin_data_dir` | `Optional[Callable]` | same contract as `ToolContext.plugin_data_dir` |
| `on_selection_changed` | `Optional[Callable]` | subscribe: `context.on_selection_changed(cb)` |
| `on_stage_changed` | `Optional[Callable]` | stage changed |
| `on_viewport_changed` | `Optional[Callable]` | viewport changed |
| `translate` | `Optional[Callable]` | `(context, source_text) -> text` |
| `current_locale` | `str = "en"` | e.g. `"en"`, `"zh_CN"`, `"ja_JP"` |
| `push_undo` | `Optional[Callable]` | `(command) -> None`; pair with `LayerCheckpointCommand` so attribute edits are Ctrl+Z-able |

---

## EditorContext

Passed to a section provider's `sections()` and its `widget_factory`.

| Field | Type | Meaning |
|---|---|---|
| `stage` / `stage_manager` | as usual | stage access |
| `request_refresh` | `Optional[Callable]` | repaint the viewport after property changes |
| `translate` / `push_undo` | `Optional[Callable]` | i18n / undo, same contract as PanelContext |
| `select_prim` | `Optional[Callable]` | `(path: Sdf.Path) -> None` — hand selection to a prim (member rows) |
| `hover_prim` | `Optional[Callable]` | `(path) -> None` — hover-highlight a bbox; empty path clears |
| `active_tool_id` | `Optional[Callable[[], Optional[str]]]` | **live** id of the active tool (or None) — a callable, never a frozen value |
| `activate_tool` | `Optional[Callable[[str], None]]` | activate by id with **exclusive** semantics: refused while another tool is active (the request fails, naming the holder, rather than silently ending the user's tool); no-op for unknown ids.  Confirm via `active_tool_id` afterwards — activation can still be refused by the poll gate, operation lock or a running job |

---

## StageMutationContext

Passed to `IFusionPlugin.on_mutation()`.  All writes through it group
into one USD change block on the layer that received the triggering
mutation.

| Field | Type | Meaning |
|---|---|---|
| `stage` | `Usd.Stage` | composed stage (read-only for context) |
| `stage_manager` | `StageManagerInterface` | bounded writes |
| `plugin_id` | `str` | owning plugin (`""` = host) |
| `edit_target_layer_path` | `str` | layer that received the triggering mutation — your writes land here |
| `triggering_prim_path` | `str` | the mutated prim |
| `originator_id` | `str` | `fusion_id` of whatever triggered this ("" = user).  **Check against your own id first** to break write→notify→write loops |
| `get_ground_height` / `find_nearest_prim` / `find_prims_in_radius` | callbacks | same shapes as ToolContext |
| `is_atlas_object` / `is_navigable_target` | callbacks | identity/navigation queries (Atlas naming is forward-looking — see [Identity and navigation queries](#identity-and-navigation-queries)) |
| `translate` | `Optional[Callable]` | i18n |

Plus the same `edit_target_scope(layer_path)` method as `ToolContext`
(shared implementation, same permission semantics).

---

## ToolEvent

Framework-level input event — the host translates Qt mouse/key events so
plugins never import Qt.

| Field | Type | Meaning |
|---|---|---|
| `type` | `str` | `"mouse_press"`, `"mouse_release"`, `"mouse_move"`, `"mouse_double_click"`, `"key_press"`, `"key_release"`, `"timer"` |
| `position` | `tuple` | `(x, y)` viewport pixels |
| `world_position` | `Optional[tuple]` | `(x, y, z)` world coords when ground intersection is available, else `None` |
| `key` | `str` | e.g. `"Escape"`, `"Return"`, `"A"` |
| `modifiers` | `set` | `{"shift", "ctrl", "alt"}` |
| `button` | `str` | `"left" \| "right" \| "middle"` |
| `is_accepted` | `bool` | set `True` to stop propagation |
| `is_auto_repeat` | `bool` | OS key-repeat (hold still pressed).  X11/Wayland sends release+press per repeat — **ignore these in hold-to-move tools** or motion restarts every repeat |

---

# 4. Result, report and metadata types

## ToolResult

```python
class ToolResult(Enum):
    FINISHED = "finished"   # done; framework auto-deactivates (accept-and-exit)
    CANCELLED = "cancelled" # user cancelled / pre-condition unmet
    FAILED = "failed"       # error
    RUNNING = "running"     # interactive — keep receiving events
```
`FINISHED` / `CANCELLED` / `FAILED` are terminal (the host deactivates
the tool on any of them); `RUNNING` keeps it active.  Exception: a tool
that started a background job returns `FINISHED` at once — the job is
what keeps running.

## CreationVerb

```python
class CreationVerb(Enum):
    FINISH  = "finish"    # [Enter]    accept ghost geometry and exit
    DISCARD = "discard"   # [Esc]      discard ghost and exit
    REPEAT  = "repeat"    # [Spacebar] accept and continue (the only sticky one)
```

## CreationSession

```python
@dataclass
class CreationSession:
    label: str = ""
    verbs: tuple = (CreationVerb.FINISH, CreationVerb.DISCARD, CreationVerb.REPEAT)
    extra_entries: list = field(default_factory=list)   # [(label, tool_method_name), ...]
```
Returned by `IToolProvider.get_creation_session()`.  A non-`None` value
turns on the framework's creation plumbing: Spacebar binds to REPEAT
(auto-repeat suppressed — one commit per press); right-click opens a
tool context menu seeded from `verbs` + `extra_entries` (never bare
finish); Esc discards the ghost and exits.  `extra_entries` invoke
`getattr(tool, method_name)(ctx)`.

## Severity, Diagnostic, ValidationReport, ExportReport

```python
class Severity(Enum):
    ERROR = "error"       # must be fixed; blocks export
    WARNING = "warning"   # should be fixed; does not block export
    INFO = "info"
```

```python
@dataclass
class Diagnostic:
    code: str                      # e.g. "E001" — enables ignore-all-by-code filtering
    severity: Severity
    message: str                   # human-readable description
    prim_path: str = ""            # offending prim; "" = stage-scoped
    fix_suggestion: str = ""       # optional; enables one-click fix workflows
```

```python
@dataclass
class ValidationReport:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    is_valid: bool = True          # True iff zero ERROR diagnostics (warnings don't invalidate)
    validator_name: str = ""       # display name; the host fills it from IValidator.display_name()

    @property def errors(self)   -> list[Diagnostic]
    @property def warnings(self) -> list[Diagnostic]
    @property def infos(self)    -> list[Diagnostic]
```

```python
@dataclass
class ExportReport:
    success: bool = False
    output_path: str = ""
    format_name: str = ""          # e.g. "Lanelet2 OSM"
    diagnostics: list[Diagnostic] = field(default_factory=list)
    stats: dict = field(default_factory=dict)   # e.g. {"lanelets": 145}
```

## OverlayLayer, OverlayRenderer, BaseOverlayRenderer

```python
class OverlayLayer(IntEnum):
    BACKGROUND = 0     # grid, OSM reference, ground plane
    CONTENT = 100      # tool-specific: spline CPs, gizmo, previews, bboxes
    FOREGROUND = 200   # HUD, scale bar, nav cube, flash highlights
    OVERLAY_UI = 300   # topmost: Qt overlaid widgets
```
Lower draws first (behind).

```python
class OverlayRenderer(ABC):        # register instances via ctx.register_overlay
    @property renderer_id -> str   # (abstract) unique id, e.g. "tool.spline_editor"
    def render(self, frustum, buf_w, buf_h) -> None   # (abstract) draw; called from
                                                       # paintGL after Hydra rendering
    @property layer -> OverlayLayer                   # default CONTENT
    @property enabled -> bool                         # toggle off without unregistering
```

```python
class BaseOverlayRenderer(OverlayRenderer):
    Z_OFFSET: float = 3.0          # preview-geometry lift above terrain (metres)
    def _draw(self, frustum, buf_w, buf_h) -> None    # override THIS, not render()
```
Sets `GL_PROJECTION` / `GL_MODELVIEW` from the frustum before `_draw`
and restores them after (Hydra/Storm leaves GL matrices arbitrary).
Helpers available inside `_draw()`:

```python
_px_to_world_m(near_point, px) -> float          # screen px -> world metres (zoom-independent)
_draw_circle_world(center, radius_m, color, segments=12, filled=True)
_draw_line_world(a, b, color, width=1.0)
_draw_polyline_world(points, color, width=1.0, closed=False)
_draw_triangle_fan_world(points, color, alpha=0.3)   # filled polygon (area previews)
```
Overrides of `render()` directly are unaffected — the base class is
purely additive.

## PluginMeta, LayerStrategy

`PluginMeta` is the typed parse of the `vstudio` manifest block — built by
the registry during discovery, never by plugin authors.  Useful to *read*:

| Field | Manifest key | Meaning |
|---|---|---|
| `name` | (folder name) | plugin id / directory name |
| `version` | `version` | semantic version, e.g. `"0.1.0"` |
| `sdk_version` | `sdkVersion` | SDK major built against — **required** |
| `display_name` | `displayName` | human-readable name |
| `description` | `description` | one paragraph |
| `author` | `author` | author or team |
| `min_core_version` | `minCoreVersion` | minimum host version or `None` |
| `imports` | `imports` | file extensions, e.g. `[".pcd"]` |
| `tools` | `tools` | tool ids contributed (index/manifest info) |
| `panels` | `panels` | panel ids contributed |
| `layers` | `layers` | layer name → `LayerStrategy` |
| `dependencies` | `dependencies` | e.g. `{"python": ["numpy>=1.24"]}` |
| `permissions` | `permissions` | `{"write": [...], "read": [...]}` |
| `enabled` | `enabled` | manifest on/off switch (default `True`) |
| `tool_workspaces` | `toolWorkspaces` | tool id → Tools-menu workspace id |
| `workspace_buttons` | `workspace` | workspace id → FAB button entries |
| `module_path` | — | import path, set by the registry |

```python
@dataclass
class LayerStrategy:
    strategy: str = "draft_overlay"
```
One of:

| Strategy | Behaviour |
|---|---|
| `"draft_overlay"` | writes go to a temp draft; Save merges into the original |
| `"create_new"` | layer created in the temp dir; Save copies it to the project |
| `"read_only"` | opened read-only; writes raise |

## Errors

### LayerPermissionError

```python
class LayerPermissionError(PermissionError)
```
Raised by `edit_target_scope` / `create_named_category_layer` when you
write to a category outside your declared `permissions.write`.  An empty
write list = read-only — *any* write raises.  A draft overlay resolves to
the category of the project layer it overlays; an unresolvable category
fails closed (the check is never skipped).

### DraftSessionDirtyError

```python
class DraftSessionDirtyError(RuntimeError)
```
Raised when closing a stage with an active, dirty draft session.  The
host catches it and prompts save/discard/cancel — plugin authors rarely
see it directly.

(`SectionSaveRefused` is documented with
[IInspectorSectionProvider](#sectionsaverefused).)

---

# 5. Events

Typed, immutable domain events on a shared bus.  **Plugins consume events;
emitting is the domain's job** — the SDK does not export the emit door.

```python
def subscribe(callback: Callable[[DomainEvent], None]) -> None
def unsubscribe(callback: Callable[[DomainEvent], None]) -> None
```
One subscription receives *all* events; filter by type inside:

```python
def on_event(event: DomainEvent) -> None:
    if isinstance(event, LaneletCommitted):
        tree.refresh()

subscribe(on_event)          # idempotent — double subscribe is ignored
...
unsubscribe(on_event)
```

Inside the host, handlers registered through the SDK see live events.  In
standalone tests there is no app to emit — handlers fire only when *you*
call them directly.

```python
@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    timestamp: float = time.time()
    source: str = "domain"        # "domain" | "application"
```
Base of every event below (and of your own subclasses, if you make any
for internal use).

### Application events

| Event | Fields | Fires when |
|---|---|---|
| `ToolActivated` | `tool_id: str`, `plugin_id: str = ""`, `source = "application"` | an interactive tool became active |
| `ToolDeactivated` | `tool_id: str` | the active tool was deactivated |
| `ToolModeChanged` | `tool_id: str`, `mode: str` | an active tool switched sub-mode |
| `SublayersRewired` | `detail: str` | the root `subLayerPaths` changed identity (draft wired in / reverted).  Any UI caching layer ids is stale until it rebuilds |
| `StreamedTileCratesCommitted` | `source_paths: tuple[str, ...]` | a Save copied streamed tile crates into the project — the producer may release its cache copies **now**; a discarded/crashed session fires nothing, so keep them for a retry |

### Navigation events

| Event | Fields | Fires when |
|---|---|---|
| `WayDeleted` | `way_path: str`, `way_uuid: int \| None` | a standalone way prim was deleted |
| `NodesPruned` | `pruned_uuids: tuple[str, ...]`, `remaining_count: int` | orphaned nodes pruned from `/Navigation/Points` |
| `LaneletCommitted` | `lanelet_path: str`, `lanelet_uuid: int \| None` | a proposed lanelet was committed to Roads |
| `LaneletDeleted` | `lanelet_path: str`, `lanelet_uuid: int \| None` | a lanelet container was deleted |
| `RegulatoryElementDeleted` | `element_path: str`, `element_type: str` | a regulatory element was deleted (`element_type`: `"stop_line"`, `"traffic_light"`, …) |
| `AreaCreated` | `area_path: str`, `way_uuid: int` | an interactive area region was authored — arm region-draw UI immediately |
| `LiftSessionStarted` | `paths: tuple[str, ...]` | lift-in-place editing began; while active, the overlay renders those lanelets as not-fixed regardless of NodeDB |
| `LiftSessionEnded` | `paths: tuple[str, ...]` | the lift session ended (accept or cancel) — invalidate caches of fixed state |

---

# 6. Module-level helpers

Reachable as `from veer_plugin_sdk import ...`.  Most of this section is
the *supporting* tier — shipped and versioned with the package but not
pinned by the 70-name manifest.  The contract-tier members: the two
[projection doors](#projection-doors-contract-tier) and the
[plugin data root](#plugin-data-root-contract-tier) (sdk#11),
`GEOMETRIC_ROLES`, and the twelve [project roots](#project-roots).

> **Back from excision, with implementations.**  `latlon_to_local_enu`,
> `batch_latlon_to_local_enu`, and `plugin_data_dir` were excised from the
> package in [veer-studio-plugin-sdk#2](http://gitea.local/veer/veer-studio-plugin-sdk/issues/2)
> as importable-but-unreachable forwarders (their implementations lived in
> the host); [veer-studio-plugin-sdk#11](http://gitea.local/veer/veer-studio-plugin-sdk/issues/11)
> re-ships them with implementations that run standalone.  They serve the
> **context-less paths** — an `IFileImporter.import_file` body and a
> module-level event subscriber hold no `ToolContext`, so the context
> callbacks (`ctx.latlon_to_local_enu(...)`, `ctx.plugin_data_dir()`) cannot
> reach them.  `read_osm_nodes` stays host-only.

```python
def parse_permission_block(name: str, raw) -> tuple[dict, dict]
```
Validate a `vstudio.permissions` block → `(scopes, reasons)`:
`scopes = {"write": [...], "read": [...]}`, `reasons = {"write": {scope:
reason}, "read": {...}}`.  Every declared scope needs a one-line reason;
an absent block keeps the read-only default (`read: ["*"]`,
`write: []`).  Raises `ValueError` for any other shape — refused at
discovery.

```python
def matrix_to_list(m) -> list        # Gf.Matrix4d -> 16 floats for glLoadMatrixd
```

### Projection doors (contract tier)

```python
def latlon_to_local_enu(lat, lon, ele=0.0, *, origin=None) -> tuple[float, float, float]
def batch_latlon_to_local_enu(nodes, *, origin=None) -> dict
```

WGS84 → local ENU metres, pyproj-backed — the same library the host
projects with, so in-host and standalone results are identical.  `origin`
is **required**: there is no default frame, and omitting it raises
`ValueError` naming the two ways to get a real one — build a `SiteOrigin`
(`SiteOrigin.from_bbox(bbox)`), or read the stage's
(`ctx.stage_manager.read_site_origin(stage)`).  Inside `import_file`,
which receives no context, build the origin from the parsed data's bbox.

`batch_latlon_to_local_enu` converts `{id: {"lat": ..., "lon": ...}}`
records to `{id: (x, y, z)}` in one call.

### Plugin data root (contract tier)

```python
def plugin_data_dir(plugin_id: str) -> str
```

The plugin's intermediate-file directory (`<cache>/veer-studio/plugin_data/<plugin_id>/`),
created on demand, returned as `str` — the standalone body of the host
door and of the `ToolContext` / `PanelContext` capabilities, so one root
serves `execute()` *and* a module-level event subscriber.  Retention is
the plugin's own business; the host only owns the path.

### Cloud role constants

```python
ROLE_PRECISE    = "precise"
ROLE_APPEARANCE = "appearance"
ROLE_DERIVED    = "derived"
CLOUD_ROLES     = (ROLE_PRECISE, ROLE_APPEARANCE, ROLE_DERIVED)
GEOMETRIC_ROLES = (ROLE_PRECISE, ROLE_DERIVED)   # (in the 70-name contract)
```
Pass `GEOMETRIC_ROLES` to `ctx.cloud_units(roles=...)` to keep only the
clouds a geometric derivation (mesh generation, snapping) may read.

### CloudUnit (in the 70-name contract)

`ctx.cloud_units()` returns a list of `CloudUnit` — one frozen record per
cloud, importable as `from veer_plugin_sdk import CloudUnit`:

| Member | What it is |
|---|---|
| `frame` | the unit's frame prim (an `Xform` under `Reality/PointClouds`) |
| `points` | the frame's single `Points` leaf prim |
| `role` | resolved cloud role — the tile-prefix fallback already applied |
| `is_tile` | `atlas:tileStatus` — whether the frame is a streamed tile |
| `is_current` | lineage flag, with "absent means current" applied |
| `name` | the frame's prim name |
| `display_name` | `atlas:displayName`, else the frame name |
| `frame_path` / `points_path` | the frame's / the leaf's absolute prim path (`str`) |
| `is_geometric` | whether `role` is in `GEOMETRIC_ROLES` |

Two attribute-reading helpers ride with it (supporting tier):
`ATTR_DISPLAY_NAME = "atlas:displayName"` and
`attr_value(prim, name)` — the authored value of a prim attribute, or
`None` when the prim, attribute, or value is absent or invalid.  Reading
any other `atlas:*` attribute off a frame uses the same helper.

### Project roots

The standard prim roots — the same strings the host's own tools use,
evaluated at call time so they follow the open stage.  Standalone (no
host on `sys.path`) they resolve against `/Site_Untitled`, the root
`testing.create_stage()` builds.  All sixteen are in the contract (§8);
never hardcode a site path, and never reach for `core.paths` — it only
exists inside a host checkout.

```python
from veer_plugin_sdk import reference_roads_root   # or: veer_plugin_sdk.paths

reference_root()          # <site>/Reference
reality_root()            # <site>/Reality
navigation_root()         # <site>/Navigation
assets_root()             # <site>/Assets
cameras_root()            # <site>/Cameras
reference_roads_root()    # <site>/Reference/Roads
reference_buildings_root()
reference_satellite_root()
reference_water_root()
reference_landuse_root()
reference_barriers_root()
reference_other_root()
pointclouds_root()        # <site>/Reality/PointClouds
colorfields_root()        # <site>/Reality/ColorFields
```

Two frame-path helpers ride the same way: `pointcloud_frame_path(index)`
(`PointCloudFrame_NNN` under the point-clouds root) and
`color_field_prim_path(index)` (`ColorField_<N>` under the colour-fields
root) — documented with the import vocabulary in
[IFileImporter](#ifileimporter).

---

# 7. Testing toolkit

```python
from veer_plugin_sdk.testing import (
    create_stage, site_path, assets_root,
    tool_context, panel_context, editor_context,
    MockStageManager,
)
from veer_plugin_sdk.testing.mock_contexts import mutation_context
```

Requires the `[testing]` extra (`usd-core`):

```bash
pip install "veer-studio-plugin-sdk[testing]"
```

### Context factories

Each factory returns a fully-populated context of the right type with
mock callbacks; **every field is overridable via `**overrides`**.

Context callbacks come in three classes, and the defaults follow the
class:

- **Queries** answer a question about state and change nothing.  Defaults
  give *empty-world* answers — honest about the mock stage, which has no
  ground mesh and no clouds.  Tests that need a live scenario override
  them.
- **Notify** callbacks tell the host something happened (status, cursor,
  overlay, selection).  Defaults are **silent no-ops**: the call never
  raises and records nothing.  A test that wants to assert on them
  overrides with its own spy (the pattern the sample's `make_ctx` uses).
- **Write** doors mutate the stage, layers, or project on disk, gated by
  permissions.  Defaults leave them **`None` on purpose**, so a unit test
  that reaches one fails loudly instead of silently writing.

```python
def tool_context(**overrides) -> ToolContext
```

Base: `stage=create_stage()` (in-memory, site root + assets),
`stage_manager=MockStageManager()`, `selection=[]`, `selection_set=[]`,
`project_dir=""`, `preferences={}`.

| Class | Defaults |
|---|---|
| Queries | `has_ground_mesh → False`, `has_ground_mesh_at → True` (the host returns `True` when no mesh exists), `get_ground_mesh_height → None`, `build_ground_mesh_cache → None`, `cloud_units → []`, `get_ground_height → 0.0`, `find_nearest_prim → None`, `find_prims_in_radius → []`, `screen_to_world → (None, None)`, `get_selection_set → []`, `get_world_center → None`, `is_atlas_object / is_navigable_target → False`, `get_atlas_type / get_atlas_object_id / get_assembly_terminals → None`, `snapshot_camera → {}`, `plugin_data_dir` → one fresh temp directory **per context** (the same path on every call, as the host requires) |
| i18n | `translate(msgctxt, text) → text` (source text; `current_locale` stays `"en"`) |
| Notify (no-ops) | `register_overlay`, `unregister_overlay`, `request_cursor`, `release_cursor`, `request_viewport_repaint`, `show_status`, `set_tool_hints`, `show_progress`, `hide_progress`, `request_tree_refresh`, `on_selection_changed`, `set_selection_set`, `set_auxiliary_dock`, `clear_auxiliary_dock`, `request_deactivate`, `restore_camera`, `frame_prim`, `register_prim_menu_entry`, `register_edit_session_entry` |
| Write (left `None`) | `import_file`, `push_undo`, `create_edit_scope`, `create_undo_checkpoint`, `create_multi_undo_checkpoint`, `regenerate_meshes`, `regenerate_mesh_in_job`, `upsert_point_cloud_tile`, `consolidate_point_cloud_run`, `discard_point_cloud_run`, `derive_cloud`, `revert_derived_clouds` |
| Host objects (left `None`) | `viewport`, `gizmo_manager`, `jobs` |

`latlon_to_local_enu` raises `NotImplementedError` rather than returning a
guess: the projection door is ruled separately, and a test that projects
should override it with a real projection.

```python
def panel_context(**overrides) -> PanelContext
def editor_context(**overrides) -> EditorContext
def mutation_context(**overrides) -> StageMutationContext
```

`panel_context` mirrors the ToolContext base (stage, mock manager, prefs,
data dir, stable `plugin_data_dir`), gives `translate` the same identity
default, no-ops the three `on_*` signals, and leaves `push_undo` (a write
door) `None`.  `editor_context` defaults `translate` to identity and
`active_tool_id → None`, no-ops `request_refresh`, `select_prim`,
`hover_prim`, `activate_tool`, and leaves `push_undo` `None`.
`mutation_context` defaults `stage=None`, `edit_target_layer_path=""`,
`triggering_prim_path=""`, the stub spatial callbacks, `translate` to
identity, and `is_atlas_object / is_navigable_target → False`.
`mutation_context` lives in `veer_plugin_sdk.testing.mock_contexts` (not
re-exported from `veer_plugin_sdk.testing`).

### Mock stage

```python
def create_stage() -> Usd.Stage      # in-memory; site root + /Assets defined
def site_path() -> str               # site root prim path (host-live inside the host,
                                     # "/Site_Untitled" standalone)
def assets_root() -> str             # assets root ("/Site_Untitled/Assets" standalone)
```
Raises `ImportError` with the install hint when `pxr` is absent.

### MockStageManager

A full `StageManagerInterface` that **records calls instead of touching
files** — assert on what your code did:

```python
mgr = MockStageManager(project_dir="/tmp/test_proj")
MyContributor().on_stage_opened(mgr)
assert len(mgr.added_sublayers) == 1
```

Constructor: `MockStageManager(project_dir="", stage=None)`.

Inspection properties (copies of the recorded lists):

```python
added_sublayers          # add_sublayer(...) paths
saved_layers             # save_layer(...) paths
edit_targets             # set_edit_target(...) paths
was_stage_saved          # save_stage() called?
notified_prims_modified  # notify_prims_modified(...) paths
dirty_layers             # mark_dirty_layer(...) ids
checkpoints              # create_checkpoint(...) labels
deleted_prims            # (prim_path, plugin_id) pairs
created_atlas_prims      # {type, position, **kwargs} dicts
named_layers             # (category, file_name) pairs
```

Return-value helpers:

```python
set_stage(stage)                  # what get_stage() returns
set_project_dir(path)             # what get_project_dir() returns
add_existing_sublayer(path)       # pre-populate without recording a call
                                  # (tests idempotent sublayer logic)
reset()                           # clear everything
```

Behavioural notes: draft methods are no-ops that keep every layer
"editable" (`ensure_editable_layer` returns the path itself);
`get_ground_height_at → 0.0`; `has_ground_mesh → False`;
`read_site_origin → None`; `create_atlas_prim` returns
`/Mock/AtlasObject_<n>`; `save_draft_overlays → 0`.

The mocks **behave like the host's types** (`isinstance` holds) but do
not run Veer Studio.  Assert on *your* logic, not on simulated app
behaviour.

---

# 8. Exported-name index

## Contract (70 names, pinned by `export-manifest.json`)

**Ports & metadata (28):**
`ATTR_IMPORT_MODE`, `ATTR_IMPORT_TRANSFORM`, `ATTR_SOURCE_CRS`,
`BaseOverlayRenderer`, `CloudUnit`, `CreationSession`, `CreationVerb`,
`Diagnostic`, `ExportReport`, `GEOMETRIC_ROLES`, `IExporter`,
`IFileImporter`, `IFusionPlugin`, `IIntegrationPlugin`, `IPanelFactory`,
`IPluginPreferences`, `IStageContributor`, `IToolProvider`, `IValidator`,
`JobSpec`, `OverlayLayer`, `PluginMeta`, `Severity`, `SiteOrigin`,
`ToolResult`, `ValidationReport`, `imported_source_id`, `source_key_for`

**Contexts (7):**
`DerivedCloudHandle`, `EditorContext`, `PanelContext`,
`StageManagerInterface`, `StageMutationContext`, `ToolContext`,
`ToolEvent`

**Context-less doors (3):**
`latlon_to_local_enu`, `batch_latlon_to_local_enu`, `plugin_data_dir`

**Events (16):**
`DomainEvent`, `ToolActivated`, `ToolDeactivated`, `ToolModeChanged`,
`SublayersRewired`, `StreamedTileCratesCommitted`, `subscribe`,
`unsubscribe`, `WayDeleted`, `NodesPruned`, `LaneletCommitted`,
`LaneletDeleted`, `RegulatoryElementDeleted`, `AreaCreated`,
`LiftSessionStarted`, `LiftSessionEnded`

**Paths (16):**
`assets_root`, `cameras_root`, `color_field_prim_path`,
`colorfields_root`, `navigation_root`, `pointcloud_frame_path`,
`pointclouds_root`, `reality_root`,
`reference_barriers_root`, `reference_buildings_root`,
`reference_landuse_root`, `reference_other_root`, `reference_root`,
`reference_roads_root`, `reference_satellite_root`, `reference_water_root`

## Supporting types (importable, same package & version)

**Ports:** `IAssemblyProvider`, `IInspectorSectionProvider`,
`IUnsavedStateProvider`, `OverlayRenderer`

**Gizmo & jobs:** `GizmoManagerInterface`, `GizmoSpec`, `GizmoHit`,
`GizmoDelta`, `JobServiceInterface`

**Sections:** `SectionSpec`, `FieldSpec`, `PrimAction`,
`SectionSaveRefused`, `SECTION_DOMAINS`, `SECTION_FIELD_KINDS`

**Manifest & layers:** `LayerStrategy`, `parse_permission_block`

**Errors:** `LayerPermissionError`, `DraftSessionDirtyError`

**Helpers:** `matrix_to_list`, `attr_value`,
`ATTR_DISPLAY_NAME`, `ROLE_PRECISE`, `ROLE_APPEARANCE`, `ROLE_DERIVED`,
`CLOUD_ROLES`

If a name you need is in neither list, it is not part of the contract —
ask for it in the SDK issue tracker rather than importing around it
(e.g. `import core.…` will work inside a host checkout and fail everywhere
else).

---

See the [author-guide](author-guide.md) for the walkthrough: plugin
anatomy, `plugInfo.json`, registration, permissions, and testing recipes.
