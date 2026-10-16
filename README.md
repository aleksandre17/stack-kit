# stack-kit

**Version: see [VERSION](VERSION)** — Manifest-driven **operations package** for SaaS monorepos.

Compose generation, SSH deploy, env contract, multi-module CLI — **no** application code, **no** production secrets in this repo.

| | |
|---|---|
| **Install** | [docs/INSTALL.md](docs/INSTALL.md) |
| **Adopt** | [docs/ADOPT.md](docs/ADOPT.md) |
| **Reference** | [docs/REFERENCE.md](docs/REFERENCE.md) |
| **Golden paths** | [docs/GOLDEN-PATHS.md](docs/GOLDEN-PATHS.md) |

## Quick start — a new project to a working run

```bash
git init my-app && cd my-app
git submodule add https://github.com/aleksandre17/stack-kit.git kits/stack-kit
pwsh kits/stack-kit/cli/stack-kit.ps1 init
```

`init` writes `stack-kit.json` (with its `commands` block), `ops/` (configuration with every secret
ignored and every example tracked), the launchers, `.vscode/` and `.github/workflows/ci.yml`. Point
each module in `stack-kit.json` at your app (`type`, `path`; `pwsh ops/cli/stack-kit.ps1 help` lists
the drivers), then:

```bash
pwsh ops/cli/stack-kit.ps1 validate          # the manifest, its tree, its secrets
pwsh ops/cli/stack-kit.ps1 build             # every module, fail-fast (also: test, lint)
pwsh ops/cli/stack-kit.ps1 <alias> run       # one module on this machine, development configuration
pwsh ops/cli/stack-kit.ps1 ci-gen --force    # after a module is added: CI follows the manifest
```

Vendoring at another path, launchers for cmd.exe and bash, and prerequisites:
**[docs/INSTALL.md](docs/INSTALL.md)**. Taking an existing repository onto the kit:
**[docs/ADOPT.md](docs/ADOPT.md)**.

## Features

- `stack-kit.json` — modules, roles (`ui`, `api`, `worker`), paths, CI, adapters
- Drivers: `java-boot` (Spring/Gradle), `node-vite` (Vite), `node-spa` (any SPA by its package.json scripts: Angular CLI, Vite, React, Vue), `node-api` (Node service), `dotnet-aspnet` (ASP.NET Core); the registry is `drivers/registry.json`
- Lifecycle per module: `build`, `test`, `lint` through its driver; `stack-kit build|test|lint` across them; a run record per step (`.stack-kit/runs/`)
- `stack-kit validate` · `migrate` · `vscode-gen` · `stack` · remote deploy / `dev watch`
- N-module CLI: `stack-kit mod <moduleId> …`
- See [CHANGELOG.md](CHANGELOG.md)

## Layout

```text
stack-kit/          ← this repository (standalone package)
├── lib/              # manifest resolution API
├── drivers/          # stack-type plugins
├── toolkit/          # deploy, stack, init
├── compose/          # catalog → docker-compose generator
├── cli/              # stack-kit entry
├── scaffold/         # templates for new projects
├── ci/               # generic CI helpers
├── scripts/          # verify / smoke
├── tests/
└── docs/
```

## Tests (package maintainers)

```powershell
cd stack-kit
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests -q
```

```powershell
.\scripts\dev-modes-verify.ps1 -SkipDocker
```

## Version

[VERSION](VERSION) holds the current version; [CHANGELOG.md](CHANGELOG.md) what each release changed.

## License

**Pending: not chosen yet.** Choosing a license is the owner's decision; until one is added, no
license is granted. A host vendors the kit under the terms its owner agrees.
