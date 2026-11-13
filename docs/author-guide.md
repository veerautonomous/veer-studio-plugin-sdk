# Writing a Veer Studio plugin with this SDK

This SDK is the contract between your plugin and Veer Studio. With it you
can write and CI-test a plugin in your own repository — no Veer Studio
checkout, no access to its source.

## The contract

Everything the host promises you is exported from the top-level package:

```python
from veer_plugin_sdk import IToolProvider, ToolContext, ToolResult, subscribe
```

The full list — 36 names — is `export-manifest.json` in this repo, and
`tests/test_surface.py` asserts it. If a name you need is not there, it is
not part of the contract; ask for it in the SDK issue tracker rather than
importing around it.

Three groups:

| Group | Names | What they are |
|---|---|---|
| Ports (16) | `IToolProvider`, `IFileImporter`, `IValidator`, … | The ABCs your plugin classes implement |
| Contexts (6) | `ToolContext`, `PanelContext`, `StageManagerInterface`, … | The capabilities the host hands you at runtime |
| Events (15) | `DomainEvent`, `subscribe`, `WayDeleted`, … | The typed event bus you consume (never emit) |

## Implementing a plugin

Implement one or more port ABCs. A tool, minimally:

```python
from veer_plugin_sdk import IToolProvider, ToolResult, ToolContext


class MyTool(IToolProvider):
    def tool_id(self) -> str:
        return "my_plugin.my_tool"          # namespaced, stable

    def display_name(self) -> str:
        return "My Tool"                    # user-visible → keep localisable

    def activate(self, ctx: ToolContext) -> None:
        self._ctx = ctx

    def deactivate(self) -> None:
        self._ctx = None

    def poll(self) -> bool:
        return True
```

Your plugin's `plugInfo.json` declares metadata, the write categories it
needs, and the `sdkVersion` major it targets — that last one is required; a
manifest without it is refused by the host.

## Testing without Veer Studio

The `[testing]` extra ships mock contexts, a mock stage manager, and an
in-memory USD stage:

```python
from veer_plugin_sdk.testing import tool_context, create_stage, MockStageManager


def test_tool_activates():
    ctx = tool_context()          # mock stage manager + in-memory stage
    MyTool().activate(ctx)
    assert ctx.stage is not None


def test_stage_has_site_root():
    from veer_plugin_sdk.testing import site_path
    stage = create_stage()
    assert stage.GetPrimAtPath(site_path())
```

The mocks behave like the host's types (`isinstance` holds), but they do not
run Veer Studio: `MockStageManager` records calls instead of touching files,
and `tool_context()` supplies stub callbacks. Assert on what *your* code did.

These tests run identically in your CI — this repo's own
`.github/workflows/ci.yml` does exactly this on 3.12.

## Events

```python
from veer_plugin_sdk import subscribe, LaneletCommitted

subscribe(my_handler)   # handler(event) — dispatch is isinstance-based
```

Plugins **consume** events; emitting is the domain's job and the SDK does
not export the emit door. Inside the host your handler sees live events; in
your standalone tests, handlers registered through this package fire only
when *you* call them directly — there is no app to emit.

## Troubleshooting

- **`No module named 'core.ports'`** — another installed package named
  `core` is shadowing the standalone path. Rename or uninstall it; the SDK
  only falls back to its bundled copies when the top-level `core` package is
  genuinely absent.
- **`ImportError: OpenUSD is required`** — install the testing extra:
  `pip install "veer-studio-plugin-sdk[testing]"`.

## Where things live

- Contract drift / version: `export-manifest.json`
- Issues: this repo's issue tracker (SDK itself);
  Veer Studio product issues → https://github.com/veerautonomous/veer-studio
