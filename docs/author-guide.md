# Writing a Veer Studio plugin with this SDK

This SDK is the contract between your plugin and Veer Studio.  With it
you can write and CI-test a plugin in your own repository — no Veer
Studio checkout, no access to its source.

Two documents:

| | |
|---|---|
| **This guide** | how a plugin is structured, discovered, registered, and tested — worked examples end to end |
| **[API reference](api-reference.md)** | every class, method, and data structure, method by method |

## The contract

Everything the host promises you is exported from the top-level package:

```python
from veer_plugin_sdk import IToolProvider, ToolContext, ToolResult, subscribe
```

The stability contract is 43 names — the list in `export-manifest.json`,
asserted by `tests/test_surface.py`, exactly matching
`veer_plugin_sdk.__all__`.  Three groups:

| Group | Names | What they are |
|---|---|---|
| Ports (21) | `IToolProvider`, `IFileImporter`, `IValidator`, … | The ABCs your plugin classes implement |
| Contexts (6) | `ToolContext`, `PanelContext`, `StageManagerInterface`, … | The capabilities the host hands you at runtime |
| Events (16) | `DomainEvent`, `subscribe`, `WayDeleted`, … | The typed event bus you consume (never emit) |

The package additionally ships *supporting types* the contract's own
signatures refer to — `GizmoSpec`, `JobServiceInterface`, `FieldSpec`,
`LayerPermissionError`, and friends.  They are importable from
`veer_plugin_sdk`, documented in the [API reference](api-reference.md#8-exported-name-index),
and versioned together with the rest.  A name in *neither* list is not
part of the contract: ask for it in the SDK issue tracker rather than
importing around it — `import core.…` works inside a host checkout and
fails everywhere else.

---

## Plugin anatomy

### Directory layout

A plugin is a Python package in a folder, with its manifest at
`<folder>/resources/plugInfo.json`:

```
my_plugin/                        # folder name == plugin name == plugin_id
├── resources/
│   └── plugInfo.json             # the manifest (required)
├── my_plugin/                    # the importable Python package
│   ├── __init__.py               # register(registry) / unregister(registry)
│   ├── tool.py                   # your IToolProvider
│   └── ...
└── tests/
    └── test_tool.py              # runs in your CI against the SDK
```

The package must be importable by name (`my_plugin`) — the host adds its
plugin search directories to `sys.path` before importing.

### How the host finds plugins

Discovery reads manifests **without importing your code**.  Three search
tiers, strongest first:

1. **`PXR_PLUGINPATH_NAME`** — `:`-separated directories (the
   developer/CI door: put the directory *containing* your plugin folder
   on it);
2. **the installed-plugins directory** — the user-level home for
   dropped-in plugin folders (same layout contract);
3. **the shipped `plugins/` tree** beside the app.

In each tier the host walks `<dir>/<plugin>/resources/plugInfo.json`,
registers it with USD's `Plug.Registry`, and keeps the entries whose
`Info` block carries a `vstudio` key.  An installed plugin shadows a
same-named shipped one.

### plugInfo.json

The envelope is USD's standard `plugInfo.json` shape with one `vstudio`
block inside `Info` — one plugin per file.  A complete example (based on
a real published plugin):

```json
{
    "Plugins": [
        {
            "Name": "my_plugin",
            "Type": "python",
            "Info": {
                "vstudio": {
                    "version": "0.1.0",
                    "sdkVersion": "1",
                    "displayName": "My Plugin",
                    "description": "One paragraph on what it does.",
                    "author": "Me",

                    "imports": [".yaml"],
                    "tools": ["my_plugin.my_tool"],
                    "toolWorkspaces": {
                        "my_plugin.my_tool": "reality_capture"
                    },
                    "workspace": {
                        "reality_capture": {
                            "buttons": [
                                {
                                    "commandId": "my_plugin.my_tool",
                                    "displayName": "My Tool",
                                    "description": "What the button does.",
                                    "toolId": "my_plugin.my_tool"
                                }
                            ]
                        }
                    },

                    "layers": {
                        "my_data.usda": { "strategy": "draft_overlay" }
                    },
                    "dependencies": {
                        "python": ["numpy>=1.24"]
                    },
                    "permissions": {
                        "write": {
                            "Reality/PointClouds": "Writes the imported cloud tiles."
                        },
                        "read": {
                            "*": "Reads the open project to place them."
                        }
                    }
                }
            }
        }
    ]
}
```

Field reference (all inside `Info.vstudio`):

| Key | Required | Meaning |
|---|---|---|
| `sdkVersion` | **yes** | the SDK major you built against (`"1"`).  A manifest without it is **refused**, and a mismatch with the host's accepted major is refused too — fail-closed |
| `version` | recommended | your plugin's semantic version |
| `displayName` | recommended | human-readable name |
| `description` | recommended | one paragraph |
| `author` | optional | you or your team |
| `minCoreVersion` | optional | minimum host version, dotted numeric (`"0.3.0"`); absent = no floor |
| `imports` | optional | file extensions your importer claims, e.g. `[".pcd"]` |
| `tools` | optional | the tool ids you contribute (informational — the host uses what `register_tool()` receives; keep them equal) |
| `panels` | optional | panel ids you contribute |
| `toolWorkspaces` | optional | tool id → Tools-menu workspace id; unknown ids fall back to `"Utility"` |
| `workspace` | optional | workspace id → FAB button entries.  Every `commandId` **must** be namespaced `<plugin_name>.<command>` (spacers exempt); invalid entries are dropped with a warning, never fatal |
| `layers` | optional | layer file → `{"strategy": "draft_overlay" \| "create_new" \| "read_only"}`; the old list form defaults every layer to `draft_overlay` |
| `dependencies` | optional | `{"python": ["numpy>=1.24"]}` — checked at discovery; missing dep disables the plugin with a reason |
| `permissions` | optional | see [Permissions](#permissions) below — every declared scope needs a **one-line** reason |
| `enabled` | optional | `false` keeps the plugin discovered but not loaded (demo/reference plugins), default `true` |
| `wheels` | optional | bundled-wheel declarations for the host's plugin site folder |

Malformed blocks refuse the plugin at discovery with the reason recorded
in the host's plugin list — check it there when something "doesn't load".

### Registration: `register()` / `unregister()`

After discovery imports your package, the host calls your package's
top-level function with the registry:

```python
# my_plugin/__init__.py
from my_plugin.tool import MyTool

def register(registry) -> None:
    """Called by the host when the plugin loads."""
    registry.register_tool(MyTool())

def unregister(registry) -> None:
    """Called when the plugin is disabled or the app shuts down."""
    registry.unregister_all("my_plugin")
```

Rules the host enforces:

- your package **must** expose a callable `register` — no `register()`
  means the plugin is disabled with that reason;
- `register()` runs with the registry's `current_plugin_id` set to your
  plugin name, which is how every `plugin_id` property gets stamped;
- one broken plugin never blocks others — an exception in `register()`
  disables just your plugin, with the reason recorded;
- `unregister_all(plugin_id)` removes *everything* you registered in one
  call — no per-item cleanup.

The registry methods available inside `register()`:

| Register | What you pass |
|---|---|
| `register_tool` | `IToolProvider` |
| `register_panel` | `IPanelFactory` |
| `register_contributor` | `IStageContributor` |
| `register_importer` | `IFileImporter` (registered per extension; multiple importers per extension allowed) |
| `register_section_provider` | `IInspectorSectionProvider` |
| `register_preferences` | `IPluginPreferences` |
| `register_validator` | `IValidator` |
| `register_exporter` | `IExporter` |
| `register_fusion_plugin` | `IFusionPlugin` (kept sorted by `priority()`) |
| `register_integration_plugin` | `IIntegrationPlugin` |
| `register_assembly_provider` | `IAssemblyProvider` |
| `register_unsaved_state_provider` | `IUnsavedStateProvider` |
| `register_ground_height_provider` | `(stage) -> float \| None` callback |
| `register_stage_hook` | hook name (`"before_save"`, `"stage_saved"`, …) + `(stage_manager)` callback |

---

## The map model

Every project is a small set of layer categories.  The host keys
composition order, draft ownership, and your `permissions.write` off this
taxonomy — hold it in mind while choosing a port:

| Category | Holds | |
|---|---|---|
| `Navigation` | the road network — ways, lanelets, **regulatory elements**, points | major layer |
| `Reality/PointClouds`, `Reality/ColorFields`, `Reality/Meshes` | the captured world — point clouds, photo colour, ground/road meshes | major layer |
| `Reference`, `Reference/Satellite` | OSM reference data and satellite imagery | major layer |
| `Cameras` | saved viewpoints | support |
| `Assets` | placed objects | support |

Domain depth — schemas, authoring workflows, the operator's view — lives
in the [Veer Studio manual](https://www.veerautonomous.com/manual/)
(start with
[Projects and layers](https://www.veerautonomous.com/manual/tasks/projects-and-layers/)).
This guide stays at the SDK's abstraction level: **the doors you call,
not what is under them.**

> **Atlas** is a planned *post-1.0* fourth major map layer — not shipped
> in 1.x.  A few contract names anticipate it (`is_atlas_object`,
> `create_atlas_prim`, the `"atlas"` section band).  They are stable API,
> but do not build current workflows on them, and never model navigation
> content with them.

### Navigation — the road network

Deep dive in the manual:
[lanelet roads](https://www.veerautonomous.com/manual/tasks/lanelet-roads/) ·
[regulatory elements](https://www.veerautonomous.com/manual/tasks/regulatory-elements/).

The layer holds ways (geometry), lanelets (roads), **regulatory
elements** — a traffic light, stop line, or crosswalk is a *regulatory
element* in this layer, never an Atlas object — and the points that
anchor them.

| You want to | Call |
|---|---|
| react to edits | `subscribe()` for `WayDeleted`, `NodesPruned`, `LaneletCommitted`, `LaneletDeleted`, `RegulatoryElementDeleted`, `AreaCreated`, `LiftSessionStarted` / `LiftSessionEnded` |
| author or remove content | `ctx.edit_target_scope(<nav layer>)` + stage writes; `stage_manager.delete_prim(...)` for deletion |
| declare the right to write | `permissions.write: {"Navigation": "..."}` |
| import OSM source data | an `IFileImporter` with `destination_category() -> "Navigation"`; `read_osm_nodes()` pre-parses candidate nodes |
| place geo coordinates | `latlon_to_local_enu(..., origin=ctx.stage_manager.read_site_origin())` — the origin is required; a project without one raises |
| gate quality before export | an `IValidator` returning a `ValidationReport` |

### Reality — the captured world

Deep dive in the manual:
[point clouds](https://www.veerautonomous.com/manual/tasks/point-clouds/) ·
[ground mesh](https://www.veerautonomous.com/manual/tasks/ground-mesh/).

The layer's unit of currency is the **cloud unit**: each carries a
*role* — `precise`, `appearance`, or `derived` (`GEOMETRIC_ROLES` is
what geometric derivations may read) — plus lineage (which unit derived
from which, which is current).  Colour fields and surface meshes sit
beside the clouds.

| You want to | Call |
|---|---|
| discover clouds on the stage | `ctx.cloud_units(roles=GEOMETRIC_ROLES)` |
| stream tiles as you produce them | `ctx.upsert_point_cloud_tile(...)` |
| finish or abandon a run | `ctx.consolidate_point_cloud_run(...)` / `ctx.discard_point_cloud_run(...)` |
| query the ground | `ctx.get_ground_height`, `ctx.has_ground_mesh`, `ctx.build_ground_mesh_cache` |
| rebuild a mesh | `ctx.regenerate_meshes(...)` / `ctx.regenerate_mesh_in_job(...)` |
| find cloud prims | `stage_manager.find_point_cloud()`, `stage_manager.find_all_point_clouds()` |
| geo-reference the data | `stage_manager.read_site_origin()` + `latlon_to_local_enu(...)` |
| declare write rights | `permissions.write: {"Reality/PointClouds": "..."}` |

### Reference and Cameras

Reference is the backdrop (OSM, satellite) — see
[reference base map](https://www.veerautonomous.com/manual/tasks/reference-base-map/).
A reference-writing importer declares
`destination_category() -> "Reference"` and is read-only for everything
else unless its permissions say otherwise.  `Cameras` holds viewpoints —
rarely a plugin's concern.

---

## Choosing a port

| You want to… | Implement | Minimal surface |
|---|---|---|
| add an interactive/one-shot **tool** | `IToolProvider` | `tool_id`, `display_name`, `execute` |
| convert an external file **into** USD | `IFileImporter` | `supported_extensions`, `import_file`, `destination_category` |
| own a **layer** in the stage stack | `IStageContributor` | `layer_name`, `default_layer_path`, `on_stage_opened`, `on_stage_closing` |
| add a **dock panel** | `IPanelFactory` | `panel_id`, `display_name`, `create_panel` |
| show domain fields in the **Properties** panel | `IInspectorSectionProvider` | `provides`, `sections` |
| add a **preferences** page | `IPluginPreferences` | `fields` |
| **validate** the stage before export | `IValidator` | `validator_id`, `display_name`, `validate` |
| export **to** an external format | `IExporter` | `exporter_id`, `display_name`, `export_format`, `export_stage` |
| react to **prim mutations** | `IFusionPlugin` | `fusion_id`, `prim_filter`, `on_mutation` |
| wire layers together on **stage open/close** | `IIntegrationPlugin` | `integration_id`, `on_stage_opened`, `on_stage_closing` |
| declare an **assembly's** schema | `IAssemblyProvider` | `assembly_id`, `subtype_token`, `get_schema` |
| report **unsaved non-USD state** | `IUnsavedStateProvider` | `has_unsaved_state` |

Full signatures and every optional hook: [API reference — ports](api-reference.md#1-extension-ports).

---

## Implementing a tool

### A minimal tool

Three abstract members — anything else is an optional override:

```python
from veer_plugin_sdk import IToolProvider, ToolContext, ToolResult


class MyTool(IToolProvider):
    def tool_id(self) -> str:
        return "my_plugin.my_tool"          # namespaced, stable forever

    def display_name(self) -> str:
        return "My Tool"                    # user-visible → keep localisable

    @classmethod
    def poll(cls, context: ToolContext) -> bool:
        # Availability.  The host calls it on the instance (tool.poll(ctx)),
        # so a classmethod works class- and instance-side.
        return context.stage is not None

    @classmethod
    def poll_reason(cls, context: ToolContext) -> str | None:
        # Optional: one user-facing sentence for the disabled tooltip.
        return None if context.stage else "No project is open."

    def execute(self, context: ToolContext) -> ToolResult:
        # The entry point when the user invokes the tool.
        if context.stage is None:
            return ToolResult.FAILED
        ...                                    # do the work
        return ToolResult.FINISHED             # terminal → host reports & exits
```

The host's call order (get this right and the rest follows):

```
poll / poll_reason ──▶ execute ──┬─ FINISHED/CANCELLED/FAILED ─▶ status message, done
                                 └─ RUNNING ─▶ activate(ctx)
                                                  │
                                          process_event(ctx, event) …
                                                  │
                                          deactivate(ctx)
```

A one-shot tool never runs — return `RUNNING` from `execute` to become
the active interactive tool.  `activate` and `deactivate` both receive
the context; so does `deactivate`'s signature — write
`def deactivate(self, context: ToolContext)`.

### An interactive (modal) tool

```python
class CutTool(IToolProvider):
    def tool_id(self) -> str:
        return "my_plugin.cut"

    def display_name(self) -> str:
        return "Cut"

    def execute(self, context: ToolContext) -> ToolResult:
        self._ctx = context
        context.request_cursor("crosshair")
        context.set_tool_hints("Click to cut · Space repeat · Esc cancel")
        return ToolResult.RUNNING              # → host calls activate(), feeds events

    def activate(self, context: ToolContext) -> None:
        context.register_overlay(self._overlay)   # draw your preview

    def process_event(self, context: ToolContext, event) -> ToolResult:
        if event.type == "mouse_press" and event.button == "left":
            self._do_cut(event.world_position)
            return ToolResult.FINISHED         # terminal → deactivate()
        if event.type == "key_press" and event.key == "Escape":
            return ToolResult.CANCELLED
        return ToolResult.RUNNING              # keep receiving events

    def deactivate(self, context: ToolContext) -> None:
        context.unregister_overlay(self._overlay)
        context.release_cursor()
```

Notes visible in the example:

- draw previews through the **overlay stack**, set the cursor through
  **`request_cursor`/`release_cursor`**, message through
  **`show_status`/`set_tool_hints`** — never poke the widget tree;
- `event.world_position` may be `None` (no ground intersection);
- ignore `event.is_auto_repeat` key events in hold-to-move behaviour.

For a creation flow (Enter accept / Space repeat / Esc discard wired by
the framework), return a `CreationSession` from `get_creation_session()`
and implement `on_creation_finish/repeat/discard` — see the
[reference](api-reference.md#creation-session-optional-overrides).

---

## Writing to the stage

Never write around the host.  The rules, in order of importance:

1. **Route every write through an edit-target scope:**

   ```python
   with ctx.edit_target_scope(draft_or_layer_path):
       attr.Set(value)                       # restores the old target on exit
   ```

   This enforces your declared permissions, refuses locked layers, and
   unlocks authorised ones — a hand-rolled `SetEditTarget` without a
   `finally` leaks the edit target for the rest of the session.

2. **Write into drafts.**  Project layers are backed by draft overlays in
   a session sandbox; Save merges, Discard reverts.  On activation, make
   the layers you may touch writable:

   ```python
   draft = ctx.stage_manager.ensure_editable_category("Navigation")
   # or, for a layer that may not exist yet:
   draft = ctx.stage_manager.ensure_draft_overlay(layer_path)
   # or, for one prim's owning layer:
   draft = ctx.stage_manager.ensure_editable_prim(prim_path)
   ```

   The host pre-creates drafts for your declared write categories on tool
   activation, but your write target is always the one you pick
   explicitly.

3. **Declare `permissions.write`** and let the enforcement work for you
   (below).

4. **Delete through the choke-point:**
   `ctx.stage_manager.delete_prim(path, ctx.plugin_id, checkpoint)` —
   never `stage.RemovePrim()`.  It handles every layer holding a spec and
   can wrap the whole delete in one undo step.

5. **Make edits undoable.**  `ctx.push_undo(command)` for simple cases;
   `create_undo_checkpoint` / `create_multi_undo_checkpoint` for
   multi-layer sessions; `create_edit_scope(...)` as a context manager.

6. **After out-of-band prim writes**, call
   `ctx.stage_manager.notify_prims_modified([path, ...])` so fusion
   plugins hear about it.

7. **While your own background job owns the stage**, wrap job-owned
   writes in `with ctx.stage_pin_exempt():` (SDK 1.2.0) — the pin admits
   only the `JobSpec.plugin_id` that holds it; everyone else gets
   `StagePinnedError`.

### Permissions

`permissions` in the manifest is what the registry enforces; an absent
block keeps you **read-only** (`write: []`, `read: ["*"]`):

```json
"permissions": {
    "write": {
        "Reality/PointClouds": "Writes the imported cloud tiles.",
        "Navigation": "Writes lanelet prims the tool places."
    },
    "read": { "*": "Reads the open project to place them." }
}
```

- every scope needs a **one-line** reason (shown in the install
  confirmation); no reason, a multi-line reason, or a non-object shape
  refuses the plugin at discovery;
- an empty `write` list means any write attempt raises
  `LayerPermissionError` from `edit_target_scope` /
  `create_named_category_layer`;
- a `"*"` in `write` permits every category;
- the category of a draft layer resolves back to the project layer it
  overlays — permissions are checked against the real category, and an
  unresolvable category **fails closed** rather than skipping the check.

---

## Events

```python
from veer_plugin_sdk import subscribe, unsubscribe, LaneletCommitted

def on_event(event):
    if isinstance(event, LaneletCommitted):
        refresh_tree()

subscribe(on_event)      # one subscription sees ALL events; filter by isinstance
unsubscribe(on_event)
```

Plugins **consume** events; emitting is the domain's job and the SDK
does not export the emit door.  Inside the host your handler sees live
events; in your standalone tests there is no app to emit — handlers fire
only when *you* call them directly.

Event catalogue with fields:
[API reference — events](api-reference.md#5-events).

---

## Testing without Veer Studio

The `[testing]` extra ships mock contexts, a mock stage manager, and an
in-memory USD stage:

```bash
pip install "veer-studio-plugin-sdk[testing]"
```

```python
from veer_plugin_sdk.testing import tool_context, create_stage, MockStageManager


def test_tool_activates():
    ctx = tool_context()            # mock stage manager + in-memory stage
    MyTool().activate(ctx)
    assert ctx.stage is not None


def test_poll_false_without_stage():
    ctx = tool_context(stage=None)
    assert MyTool.poll(ctx) is False
    assert MyTool.poll_reason(ctx)


def test_tool_writes_through_stage_manager(tmp_path):
    ctx = tool_context(project_dir=str(tmp_path))
    MyTool().execute(ctx)
    mgr = ctx.stage_manager
    assert mgr.deleted_prims or mgr.saved_layers or mgr.edit_targets  # assert on YOUR effects


def test_stage_has_site_root():
    from veer_plugin_sdk.testing import site_path
    stage = create_stage()
    assert stage.GetPrimAtPath(site_path())
```

Useful properties of the toolkit:

- **`tool_context(**overrides)`** (and `panel_context`,
  `editor_context`, `mutation_context` — the last lives in
  `veer_plugin_sdk.testing.mock_contexts`) — every field is overridable;
  defaults include stub spatial callbacks (`get_ground_height → 0.0`,
  `find_prims_in_radius → []`) and a fresh temp `plugin_data_dir`.
- **`MockStageManager`** records every mutating call for inspection
  (`added_sublayers`, `deleted_prims`, `edit_targets`, `named_layers`, …)
  with setters (`set_stage`, `add_existing_sublayer`) and `reset()`.
  Draft methods return the path itself, so every layer reads as editable.
- The mocks are `isinstance`-compatible with the host's types but do not
  run Veer Studio — **assert on what *your* code did**, not on simulated
  app behaviour.

These tests run identically in your CI — this repo's own
`.github/workflows/ci.yml` does exactly this on 3.12.

---

## Troubleshooting

- **`Can't instantiate abstract class … without an implementation for
  abstract method 'execute'`** — every port has *abstract* members that
  have no default.  For a tool that's `tool_id`, `display_name`,
  `execute`; check the [port list](#choosing-a-port) for yours.
- **`TypeError: … poll() takes 2 positional arguments but 3 were given`
  (or similar)** — override signatures must match the ABC: `poll` and
  `poll_reason` take `(cls, context)` / `(self, context)`;
  `deactivate` takes `(self, context)` — the host always passes the
  context.
- **Plugin never appears / "no register() function"** — the manifest
  must sit at `<your_folder>/resources/plugInfo.json`, the Python
  package must be importable under the folder's name, and the package
  must define `register(registry)`.  Check your folder is on
  `PXR_PLUGINPATH_NAME` or in the user plugins directory.
- **Plugin listed but disabled with an SDK/permission reason** — read
  the reason in the host's plugin list: missing/mismatched `sdkVersion`,
  an unmet `minCoreVersion` or dependency, or a malformed
  `permissions` block (every scope needs a one-line reason).
- **`LayerPermissionError`** — your `permissions.write` doesn't cover the
  target layer's category (or is empty = read-only).  Declare the
  category in the manifest; don't route around the check.
- **`No module named 'core.ports'`** — another installed package named
  `core` is shadowing the standalone path.  Rename or uninstall it; the
  SDK only falls back to its bundled copies when the top-level `core`
  package is genuinely absent.
- **`ImportError: OpenUSD is required`** — install the testing extra:
  `pip install "veer-studio-plugin-sdk[testing]"`.
- **`StagePinnedError` from `stage_pin_exempt()`** — a background job
  you don't own holds the stage.  Only the job's own `plugin_id`
  (the `plugin_id` field on its `JobSpec`) may write through the pin.

---

## Where things live

- **Class/method reference:** [docs/api-reference.md](api-reference.md)
- Contract drift / version: `export-manifest.json`
- Issues: this repo's issue tracker (SDK itself);
  Veer Studio product issues → https://github.com/veerautonomous/veer-studio
