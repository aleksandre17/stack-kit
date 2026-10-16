# Module drivers

**Driver type** = a toolchain (`java-boot`, `node-vite`, `node-spa`, `node-api`, `dotnet-aspnet`).
**Module id** = the host's key in `stack-kit.json`. **Role** (`api`, `ui`, `worker`, ...) is the
module's; its server **tier** is the role's (`config/catalogs/roles.json`).

```
drivers/
  registry.json          # every driver's declaration (registry.schema.json)
  <type>/                # its scripts (lifecycle steps, the host run's launch step) and container/ recipes
  _shared/               # runners a driver family shares (package-scripts)
  _template/             # copy when adding a type
```

## What a driver declares

Everything a module of it needs, and nothing the kit spells: `commands` (lifecycle steps and its
own, each a script run by its runtime), `package` (how one commit becomes one archive),
`container` (how a release runs: a recipe template rendered per module, or a static image),
`dev` (its remote dev container, caches, excludes, reactions to a change), `delivery` (rungs,
usually `via` a kit verb), `ci.setup`, `detect`, `vscode` (its launch configuration as data, the `values` it reads from the
module's files, its `label`; lib/vscode_gen.py holds no debugger), `migrations`, `outputs`,
`compose.opsModules` (the local stack's registry rows).

## Rules

1. Never infer a driver from a folder name: only `modules.<id>.type`.
2. Several APIs are several modules, each with its own type.
3. `stack-kit mod <moduleId> <command>` runs a command the driver declares; `deploy`, `dev`, `ops`
   are the kit's verbs over every driver alike -- a driver ships no deploy, dev or manage script.

## Add a driver

1. Copy `drivers/_template/` -> `drivers/<type>/` (or declare it in the host's own registry,
   `drivers.registry`, beside its folder -- the kit untouched).
2. Declare it in the registry: `label`, `roles`, `commands`, `package`, `container` (with its
   recipe under `container/`), `dev`, `delivery` (`release: {via: release}`, `remote-dev: {via: dev}`).
3. Point a module at it (`"type": "<type>"`); `stack-kit validate`, `stack-kit deploy <module> --plan`.

## Resolution

One resolver (`lib/resolution/`) reads the composed registry (`lib/modules.py`); `lib/drivers.ps1`
looks its answers up. See [docs/REFERENCE.md, Drivers](../docs/REFERENCE.md#drivers).
