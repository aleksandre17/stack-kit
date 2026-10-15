# stack-kit architecture

## Boundaries

```text
┌─────────────────────────────────────────────────────────┐
│  kits/stack-kit  (this package — copy/submodule)      │
│  lib · compose · toolkit · adapters · contracts · ci    │
└───────────────────────────┬─────────────────────────────┘
                            │ stack-kit.json
┌───────────────────────────▼─────────────────────────────┐
│  Consumer project (your-app, …)                         │
│  ops/config/ · ops/compose/catalog.json · apps/*        │
│  generated docker-compose*.yml · ops/compose/stack/     │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  Applications (Spring, Vite, …)                         │
└─────────────────────────────────────────────────────────┘
```

## What must never be added here

- Real `DEPLOY_SERVER`, API keys, CSP production domains
- `docker-compose*.yml` (generated in the consumer project)
- Java/TS business code
- Consumer-specific health check URLs (stay in project `ops/ci/`)

## Entry points

| Consumer calls | Package path |
|----------------|--------------|
| `stack-kit compose-gen` | `compose/build.py` |
| `stack-kit nginx-gen` | `adapters/render_nginx.py` |
| `stack-kit stack` | `toolkit/stack/compose.ps1` |
| `stack-kit infra` | `toolkit/infra/Invoke-Infra.ps1` (+ `ensure-prereqs.sh` when no subcommand) |
| `stack-kit init` | `toolkit/init/` → `lib/ci_prepare.py` |
| `be deploy` / `fe deploy` | `toolkit/deploy/` via drivers |

## Manifest

`stack-kit.json` at project root — see [manifest.schema.json](manifest.schema.json) and [docs/PACKAGE-ARCHITECTURE.md](docs/PACKAGE-ARCHITECTURE.md).

Resolution API: `lib/project_context.py` (Python), `lib/project.sh` + `lib/env.sh` (Bash), `lib/project.ps1` + `lib/env.ps1` (PowerShell).

## Deploy golden paths

**[docs/GOLDEN-PATHS.md](docs/GOLDEN-PATHS.md)** — canonical policy (static dist vs compose/dev, local vs remote).
