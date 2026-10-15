# stack-kit infra (kit driver)

Postgres, Redis, Qdrant — **one stack per consumer repo** on a shared server root.

## Commands

| Command | Description |
|---------|-------------|
| `stack-kit infra prereqs` | SSH checks + Docker network (`ensure-prereqs.sh`) |
| `stack-kit infra local up\|down\|status` | Docker on developer machine |
| `stack-kit infra remote sync` | rsync `stack.infraComposeDir` → `{base}/{DEPLOY_PROJECT}/infra/{INFRA_SLUG}/compose/` |
| `stack-kit infra remote up\|down\|status` | Remote compose (scoped path) |
| `stack-kit infra remote purge -Confirm` | `down -v` for **this** `INFRA_SLUG` only |
| `stack-kit infra tunnel` | SSH `-L` only for `stack.infra.services` (ports via `infra-catalog.json` tunnel env keys) |

Implementation: `Invoke-Infra.ps1`  
Path helpers: `lib/env.ps1`, `lib/deploy_paths.py`

## Consumer wiring

- `stack-kit.json` → `stack.infraComposeDir`, **`stack.infra.services`** (e.g. `["postgres"]`)
- Optional **`stack.infra.composeFiles`** — full `-f` list override
- Consumer: `docker-compose.base.yml` + `services/<id>.yml`
- Reference catalog: `compose/infra-catalog.json` (not required at runtime)
- **No** `INFRA_PROFILES` — manifest is the only service selector

## Isolation

Sibling projects: `.../stack-kit/infra/project-a` vs `.../stack-kit/infra/project-b` — separate containers, volumes, and host ports. `down` / `purge` never touches another slug's path.
