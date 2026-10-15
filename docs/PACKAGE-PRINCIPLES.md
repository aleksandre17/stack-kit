# stack-kit — package principles

The kit is a **growth-oriented ops framework**, not a fixed product stack.

## Design goals

| Principle | Meaning for this package |
|-----------|-------------------------|
| **Agnostic** | Drivers do not assume postgres, redis, or any named app |
| **Open/closed** | Extend via manifest + consumer compose files; avoid editing kit for new stores |
| **Single responsibility** | Kit = run/sync/paths/CLI; consumer = which services exist |
| **Manifest contract** | `stack-kit.json` declares intent; no duplicate env toggles |
| **Dynamic** | Add services by adding yaml + manifest entries |

## Infra (example of the split)

| Layer | Owns |
|-------|------|
| **Kit** `toolkit/infra/Invoke-Infra.ps1` | Remote path, rsync, `docker compose` invocation, tunnel |
| **Kit** `compose/infra-catalog.json` | Reference module list (documentation + scaffold source) |
| **Consumer** `ops/compose/infra/` | Base network + `services/*.yml` fragments |
| **Consumer** `stack-kit.json` | `stack.infra.services`: which fragments to merge |

**Not used:** `INFRA_PROFILES` or other env-based service toggles (violates single source of truth).

**Tunnel:** enabled services = `stack.infra.services`; port env keys = kit `compose/infra-catalog.json` (+ optional consumer `ops/compose/infra/infra-catalog.json`). Not a fixed postgres/redis/qdrant triple.

## Stack compose hints

| Layer | Owns |
|-------|------|
| **Kit** `toolkit/stack/compose.ps1` / `compose.sh` | Runs `docker compose`; prints endpoint lines before/up |
| **Kit** `compose/stack-catalog.json` | Per-role port env keys, defaults, health URL path |
| **Consumer** `stack-kit.json` `modules.*` | Which apps exist (`role`: `ui`, `api`, `worker`, …) |
| **Consumer** `ops/config/<secretsModule>/` | Port values (`API_PORT`, `RETRIEVAL_PORT`, …) |

**Not used:** hardcoded `frontend` / `backend` URLs in the kit runner.

Optional filter: `stack.modules` — list of module ids to show (default: all manifest modules with a catalog role).

## Stack compose (compose-gen)

| Layer | Owns |
|-------|------|
| **Kit** `compose/compose-catalog.json` | Templates per `modules.*.type` + `role` (`java-boot` api/worker, `node-vite` ui) |
| **Kit** `compose/manifest_compose.py` | Renders N services from manifest (`stack.composeModules`) |
| **Kit** `compose/stack-catalog.json` | Port env keys + health paths per role |
| **Consumer** `ops/compose/catalog.json` | Per-app targets + `manifestStack` / `manifestModule` target specs |

**Not used:** a single hardcoded api/app/worker triple for every project module.

### Embedded backend worker vs manifest `worker` role

| Mechanism | When to use |
|-----------|-------------|
| **`features.worker`** in consumer `ops/compose/catalog.json` | Legacy: adds `apps/backend/worker` as a second container next to the main API (same repo). |
| **`modules.*` with `role: worker`** | Standalone worker deployables (e.g. `ingestion-service`) — rendered by `manifest_compose.py`. |

**Do not enable both** for the same logical job. Architecture B consumers should set `features.worker: false` and declare ingestion (or other workers) in the manifest only.

**Future kit:** move embedded worker to manifest (`modules.<api>.compose.embeddedWorker`) and deprecate `features.worker`. **Done (P0-kit-13):** manifest flag + `effective_compose_features`; catalog fallback with validate warning.

## Stack remote deploy (`stackDeploy`)

| Source | Owns |
|--------|------|
| **`stack.composeModules`** | Default module list for `stack-kit stack-deploy` (same as compose-gen) |
| **`stackDeploy.modules`** | Optional override of that list |
| **`stackDeploy.steps`** | Explicit steps only when auto-generated plan is insufficient |
| **`lib/stack_deploy.py`** | Role order: api → worker → gateway → data → ui; per-type args (`java-boot` → `deploy all`, `node-vite` → `deploy dist`) |

**Not used:** hardcoded backend+frontend only in consumer manifest when N modules exist.

Inspect: `modules_cli.py stack-deploy-steps [dev|prod]`.

## Compose service names (`COMPOSE_*`)

| Source | Owns |
|--------|------|
| **`stack-kit.json` `modules.*`** | Service keys: `{slug}-api` (backend), `{slug}-retrieval`, `{slug}-ingestion`, `{slug}-app` (ui), … |
| **`lib/compose_identity.py`** | Same rules for `compose-gen`, deploy paths, `ProjectContext.compose_service_names()` |
| **`deploy.env` `COMPOSE_*`** | Optional **legacy overrides** for primary api/ui/worker only (old servers). Not required for new projects. |
| **`deploy.env`** | `COMPOSE_PROJECT_NAME`, `DOCKER_NETWORK`, `DEPLOY_*` — shared identity |

**Not used:** duplicating every module name in `deploy.env` when manifest already declares `target` / `role`.

Inspect names: `stack-kit` → `modules_cli.py compose-names` (JSON) or after `compose-gen` read GENERATED `docker-compose.yml`.

## CI health matrix

| Layer | Owns |
|-------|------|
| **Kit** `lib/ci_health.py` | Health URLs from `stack.composeModules` (or `ci.healthModules`) + `stack-catalog.json` roles |
| **Kit** `ci/wait-stack-health.sh` | Waits all targets via `modules_cli.py stack-health` |
| **Consumer** `stack-kit.json` `ci.healthModules` | Optional subset (e.g. skip `frontend` in Docker CI) |
| **Kit** `compose/stack-catalog.json` | Per-role `urlPath`, `healthExpect`, `ciHealth` |

**Not used:** hardcoded single API URL in `integration-stack.sh` when N modules exist.

Inspect: `modules_cli.py stack-health` (TSV: module, url, expect).

## Hybrid local run (`stack-kit hybrid boot` / `<alias> run`)

| Layer | Owns |
|-------|------|
| **Kit** `toolkit/hybrid/Invoke-HybridRun.ps1` | Load secrets `.env.dev`, Gradle bootRun / npm per driver type |
| **Kit** `drivers/*/ps1/run.ps1` | Thin delegate; `run` in `drivers/registry.json` |
| **Kit** `cli/stack-kit.ps1` | `hybrid boot <alias\|moduleId>` → module driver `run` |
| **Consumer** `stack-kit.json` `modules.*.hybrid` | `springProfiles`, `gradleWrapper`, `gradleProject`, `npmScript` |
| **Consumer** `cli.aliases` | Short names (`fe`, `be`, …) — project-specific, not in kit help text |

**Not used:** consumer repo path (`kits/stack-kit`), product aliases, or dev-mode labels in kit runtime strings.

## App config generation (config-gen)

| Layer | Owns |
|-------|------|
| **Kit** `lib/config_gen.py`, `config/config-catalog.json` | Profile boilerplate templates |
| **Kit** `stack-kit config-gen`, validate drift | Generate / check |
| **Consumer** `modules.*.datastores`, `modules.*.spring` | Postgres schema, profile groups |
| **Consumer** `application-custom.yml` | Domain config — generator never touches |

## Adding a new data store

1. Add `ops/compose/infra/services/my-store.yml` in the consumer repo.
2. Add `"my-store"` to `stack.infra.services` in `stack-kit.json`.
3. Optionally document the module in consumer catalog or upstream kit `infra-catalog.json`.

No kit release required for project-specific stores.

## Anti-patterns (reject in reviews)

- Hardcoding consumer repo or brand names in kit runtime
- Monolithic compose in kit that every project must use as-is
- Env vars that duplicate manifest service selection
- Shrinking extension points to “only three databases”

See also: `ADOPTION-LINE.md`, `ARCHITECTURE.md`, consumer `.cursor/rules/kit-upstream.mdc`.
