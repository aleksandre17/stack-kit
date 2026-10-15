# Package vs project — responsibility matrix

| Artifact | Package (`kits/stack-kit`) | Project (repo root) |
|----------|------------------------------|---------------------|
| `stack-kit.json` | schema | **instance** |
| `ops/config/deploy.env` | example in scaffold | **real values (gitignored)** |
| `ops/compose/catalog.json` | minimal scaffold | **full stack definition** |
| `docker-compose*.yml` | engine | **generated** under `apps/*`, `ops/compose/stack/` |
| `ops.modules` | sync script | **generated** at `apps/backend/ops.modules` |
| `nginx.conf.template` | — | **adapter** under `apps/frontend/` + `ops/config` |
| Java domain code | — | **`apps/backend/` only** |
| Deploy/manage scripts | `toolkit/`, `drivers/` | CLI via `tools/stack-kit.ps1` |
| CI integration | `ci/wait-health.sh`, … | **`ops/ci/integration-stack.sh`** |

## Rule

If it names **your** domain, API key, or business module → **project**.  
If it could work for **any** SSH + Docker + Gradle monorepo → **package**.

Install path: [../../../docs/KITS-PACKAGE.md](../../../docs/KITS-PACKAGE.md)
