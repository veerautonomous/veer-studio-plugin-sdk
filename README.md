# Veer Studio Plugin SDK

The contract surface for writing **Veer Studio plugins** without access to
the Veer Studio source tree: the port ABCs, the bounded-context types, the
event bus, and a testing toolkit (mock contexts, mock stage manager, mock USD
stage) — everything needed to write and CI-test a plugin standalone.

- **Version:** `1.0.0` — generated from Veer Studio source
  `49489c81142663e06b8169a92aae6752533a3163`
- **Docs:** [docs/author-guide.md](docs/author-guide.md)
- **Issues:** report SDK problems here
  (https://github.com/veerautonomous/veer-studio-plugin-sdk/issues);
  Veer Studio product issues go to
  https://github.com/veerautonomous/veer-studio

## Install

From a release tag (recommended — the wheel is also attached to the release):

```bash
pip install "veer-studio-plugin-sdk @ git+https://github.com/veerautonomous/veer-studio-plugin-sdk@v1.0.0"
```

For plugin tests that build USD stages, add the testing extra:

```bash
pip install "veer-studio-plugin-sdk[testing] @ git+https://github.com/veerautonomous/veer-studio-plugin-sdk@v1.0.0"
```

## Quickstart

```python
from veer_plugin_sdk import IToolProvider, ToolResult, ToolContext


class MyTool(IToolProvider):
    def tool_id(self) -> str:
        return "my_plugin.my_tool"

    def display_name(self) -> str:
        return "My Tool"

    def activate(self, ctx: ToolContext) -> None:
        ...

    def deactivate(self) -> None:
        ...

    def poll(self) -> bool:
        return True
```

Test it without Veer Studio:

```python
from veer_plugin_sdk.testing import tool_context


def test_activate():
    ctx = tool_context()
    MyTool().activate(ctx)
```

Run your tests the same way CI does: `python -m pytest tests/ -q`.
See [docs/author-guide.md](docs/author-guide.md) for the full walkthrough.

## What this package is not

- It does **not** run Veer Studio, render a viewport, or ship the
  application — plugins are loadable adapters, not apps.
- It does **not** include Veer Studio internals; the 37 exported names are
  the entire contract (see `export-manifest.json`).

## Versioning

Semantic versioning from `1.0.0`. A plugin manifest declares the SDK major it
was built against (`sdkVersion` — required; the host refuses a manifest that
omits it); a major bump means the contract changed in
a way your plugin must answer to. The export manifest in this repo is the
machine-checkable record of the surface each release carries.
