# stack-kit architecture

## Boundaries

```text
┌──────────────────────────────────────────────────────────────┐
│  the kit (vendored: platform/kits/stack-kit, kits/stack-kit)  │
│  cli · lib (cli, delivery, targets, resolution) · drivers     │
│  config (catalogs, layout, delivery defaults) · toolkit       │
└──────────────────────────────┬───────────────────────────────┘
                               │ stack-kit.json, deploy targets
┌──────────────────────────────▼───────────────────────────────┐
│  a host project: its modules, ops/config (gitignored values), │
│  ops/deploy/targets.json, its own drivers and catalog entries │
└──────────────────────────────┬───────────────────────────────┘
                               │ ssh: {root}/{project}/{env}/{tier}/{service}
┌──────────────────────────────▼───────────────────────────────┐
│  a target: one shared root, each project's own claimed tree   │
└──────────────────────────────────────────────────────────────┘
```

## What must never be added here

- A host's value: a server, a user, a path, a key, a production domain, a project name.
- Generated output (`docker-compose*.yml`, `.stack-kit/`), business code.
- A tool's name in a generic script: a tool lives in its driver's declaration (`tests/unit/test_one_home.py`).

## Entry points

| Consumer calls | Runs |
|---|---|
| `stack-kit <verb>` | `cli/stack-kit.ps1` / `cli/stack-kit.sh` -> `cli/stack_kit.py` -> `lib/cli/main.py` -> a verb of `lib/cli/verbs/` |
| a remote verb (`deploy`, `release`, `ops`, `dev`, `targets`, `layout`, `infra remote`) | `lib/cli/remote.py`: the plan, the confirmation, then `lib/delivery/` |
| a lifecycle step, `mod <module> <command>` | the driver's command by its runtime (`lib/cli/tools.py`) |
| `compose-gen`, `vscode-gen`, `config-gen`, `ci-gen`, `nginx-gen` | `compose/build.py`, `lib/vscode_gen.py`, `lib/config_gen.py`, `lib/ci_gen.py`, `adapters/render_nginx.py` |

## Manifest

`stack-kit.json` at project root — see [manifest.schema.json](manifest.schema.json) and [docs/REFERENCE.md#manifest](docs/REFERENCE.md#manifest).

Resolution: one resolver, `lib/resolution/`; the Bash and PowerShell libraries are shims over `lib/resolve_cli.py` — see [docs/REFERENCE.md#resolver](docs/REFERENCE.md#resolver).

## Golden paths

**[docs/GOLDEN-PATHS.md](docs/GOLDEN-PATHS.md#policy)** — dev modes, remote dev, deploy, operate, layout migration; every verb: [docs/OPERATIONS.md](docs/OPERATIONS.md).
