---
kind: guide
authority: canonical
owns: adoption
---

# Adopt stack-kit

Taking a host onto the kit, once it is vendored ([INSTALL.md](INSTALL.md)). Field-by-field
manifest and command detail is [REFERENCE.md](REFERENCE.md); the day-to-day paths are
[GOLDEN-PATHS.md](GOLDEN-PATHS.md). Reference host: `tests/fixtures/gc/`.

## Package vs project

| Artifact | Kit (`kits/stack-kit`) | Host (repo root) |
|---|---|---|
| `stack-kit.json` | schema `manifest.schema.json`, template `scaffold/stack-kit.json` | **the instance** |
| `ops/config/` (env files, SSH) | `*.example` in `scaffold/` | **real values, gitignored** |
| `ops/deploy/targets.json` | schema `config/deploy-targets.schema.json` | **where deploys go; tracked, never a secret** |
| `ops/compose/catalog.json` | `scaffold/ops/compose/catalog.{minimal,full}.json` | **the stack definition** |
| `ops/compose/infra/` | `toolkit/infra/Invoke-Infra.ps1`, `compose/infra-catalog.json` | `docker-compose.base.yml`, `services/*.yml`, `ops/config/infra/.env.*` |
| `docker-compose*.yml` | the generator (`compose/build.py`) | **generated** under `apps/*`, `ops/compose/stack/` |
| `ops.modules` (java-boot) | `compose/sync_ops_modules.py` | **generated** at `compose.syncModules` |
| `nginx.conf.template` | `adapters/render_nginx.py` | under the UI module + `ops/config/<ui>/nginx.env` |
| deploy, dev, operate | the CLI (`lib/cli/`, `lib/delivery/`), driver declarations | called through `ops/cli/stack-kit.*` |
| CI | `ci/prepare-integration-env.sh`, `ci/wait-health.sh`, `ci/wait-stack-health.sh` | `ops/ci/integration-stack.sh`, `.github/workflows/` |
| domain code | — | `apps/*` only |

Rule: names your domain, an API key or a business module → host. Works for any SSH + Docker +
Gradle/npm monorepo → kit.

## Target layout

```text
<host>/                         ← STACK_KIT_PROJECT_ROOT
├── stack-kit.json              ← the contract (required)
├── tools/stack-kit.ps1 | .cmd  ← launchers (INSTALL.md#launchers)
├── kits/stack-kit/             ← the kit (submodule or copy)
├── ops/
│   ├── cli/stack-kit.ps1 | .sh ← canonical entry
│   ├── config/                 ← manifest `secrets`; values gitignored
│   │   ├── ssh/
│   │   ├── infra/.env.dev | .env.prod
│   │   └── <secretsModule>/    ← .env, .env.dev, .env.prod, credential files
│   ├── deploy/targets.json     ← deploy targets (tracked)
│   ├── compose/
│   │   ├── catalog.json
│   │   ├── infra/              ← docker-compose.base.yml + services/*.yml
│   │   └── stack/              ← GENERATED full-stack compose
│   └── ci/integration-stack.sh
└── apps/
    ├── frontend/  docker-compose*.yml (GENERATED), nginx.conf.template, src/
    └── backend/   ops.modules (GENERATED), docker-compose.*.yml (GENERATED), src/
```

## Bootstrap with init

`stack-kit init` (`toolkit/init/Invoke-ProjectInit.ps1`; first run from bash: `bash kits/stack-kit/toolkit/init/init.sh [<root>]`, since `cli/stack-kit.sh` stops when no manifest exists yet), in order:

1. The extension points init requires (`config/extension-points.json`): `tools/`, `ops/cli/`, `ops/ci/`, `ops/config/*.example`, `ops/compose/`, `ops/deploy/`, `stack-kit.json`, and each infra service the manifest selects -- never overwriting.
2. Catalog: `catalog.full.json` → `ops/compose/catalog.json` (`-MinimalCatalog`: `catalog.minimal.json`, API only).
3. Seed `ops/config/` per manifest module (`lib/ci_prepare.py`): `.example` → `.env.dev`, `.env.prod`, `nginx.env`.
4. Merge `.gitignore` rules.
5. `compose-gen`.
6. `vscode-gen` (missing `.vscode` files only).
7. `nginx-gen` when `adapters.nginx.template` exists.
8. Checklist of values still to fill.

| Flag | Effect |
|---|---|
| `-MinimalCatalog` | `catalog.minimal.json` instead of the full catalog |
| `-SkipComposeGen` | no compose-gen |
| `-SkipSeed` | no env files from examples |
| `-SkipNginxGen` | no nginx-gen |
| `-SkipGitIgnore` | leave `.gitignore` alone |
| `-ForceExamples` | overwrite existing scaffold/env files and the catalog from examples |

Without `-ForceExamples`, existing `.env.*` files and SSH keys are never overwritten.
Tree only, no seed: `stack-kit extend --init --root <dir>` (every extension point init requires). Not part of init: application code. More: [toolkit/init/README.md](../toolkit/init/README.md).

## The manifest

`stack-kit.json` at the host root; start from `scaffold/stack-kit.json` (init copies it). Set
`"$schema": "./kits/stack-kit/manifest.schema.json"`. Edit at least:

| Field | Value |
|---|---|
| `version` | `2` (schema minimum) |
| `package` | `"kits/stack-kit"` |
| `secrets` | `"ops/config"` |
| `modules.<id>.type` | driver id from `drivers/registry.json` — always explicit, never inferred from a folder name |
| `modules.<id>.role` | `ui`, `api`, `worker`, `gateway`, `data`, `other` |
| `modules.<id>.path` | app tree, e.g. `apps/frontend` |
| `modules.<id>.secretsModule` | folder under `ops/config/` (usually the module id) |
| `cli.aliases` | shortcuts, e.g. `{ "fe": "frontend", "be": "backend" }` |

Every section, credentials, stack deploy, CI health, hybrid: [REFERENCE.md#manifest](REFERENCE.md#manifest).
Check with `stack-kit validate`.

## Configuration

`ops/config/` (manifest `secrets`) holds real values; `.gitignore`: `ops/config/**` except `*.example`.
Where a deploy goes is not here: it is the targets file. No env file names a server, a project or a
service -- those are the manifest's `project` and the targets file (stack-kit 2.0.0; a former
`deploy.env`, `.env.deploy` or DEPLOY_*/COMPOSE_* key is a `validate` error naming `migrate`).

| File | Typical keys |
|---|---|
| `ops/deploy/targets.json` (tracked) | the deploy targets: `host`, `user`, `root` (the platform's shared directory), `runtime`, `ssh` (identity reference, pinned `known_hosts`), `ports`, `health`; per machine `targets.local.json` (ignored). [REFERENCE.md#targets](REFERENCE.md#targets) |
| `ops/config/<module>/.env` | shared, non-secret values every environment reads |
| `ops/config/<module>/.env.dev`, `.env.prod` | one environment's values (a development run never reads `.env.prod`) |
| `ops/config/<module>/<credential files>` | uploaded to the unit's `runtime/credentials` (600), mounted read-only (`credentialPatterns`) |
| `ops/config/infra/.env.dev`, `.env.prod` | the infra stack's ports and credentials |
| `ops/config/ssh/` | a project-local SSH key ([scaffold/ops/config/ssh/README.md](../scaffold/ops/config/ssh/README.md)) |

Credential profiles: `scaffold/ops/config/profiles/`.

## Compose catalog

`ops/compose/catalog.json` is the host's one source for which services are generated where.

1. Start from `scaffold/ops/compose/catalog.minimal.json` (or the full one init copies).
2. Add `templates` (YAML fragments) and `targets` (which file receives which services); `manifestStack` / `manifestModule` targets render manifest modules.
3. Embedded backend worker: `modules.<api>.compose.embeddedWorker` (catalog `features.worker` is deprecated; `validate` warns). Use `false` when the worker is its own `role: worker` module — never both.
4. Service names come from the manifest's `project` (`lib/naming.py`).

```powershell
.\tools\stack-kit.ps1 compose-gen
```

Generated (never edit a file starting `# GENERATED`): `apps/*/docker-compose*.yml`, `ops/compose/stack/*.yml`, `apps/backend/ops.modules`.

## Module files

A module holds its code and, where it has its own, its container recipe (`container.dockerfile`);
everything else is its driver's declaration ([REFERENCE.md#drivers](REFERENCE.md#drivers)).

| File | Purpose |
|---|---|
| `docker-compose*.yml` | the local stack (GENERATED by `compose-gen`) |
| `package.json`, `*.csproj`, `settings.gradle` | the toolchain's own build, which the driver's steps run |
| `nginx.conf.template` | when `adapters.nginx` is declared |
| `ops.modules` | GENERATED Gradle subproject registry (java-boot, the local stack) |

## CI

Recommended jobs (`.github/workflows/ci.yml`):

| Job | Checks |
|---|---|
| `compose-catalog` | `python3 kits/stack-kit/compose/build.py` + `git diff` on GENERATED yaml |
| `ops-scripts` | Python compile, `shellcheck` drivers/toolkit, catalog JSON valid |
| `frontend-build` | `npm ci && npm run build` (with CI `VITE_API_URL`) |
| `backend-build` | `./gradlew build` |
| `integration-compose` | `prepare-integration-env.sh` + `ops/ci/integration-stack.sh` |

`ops/ci/integration-stack.sh`: copy `scaffold/ops/ci/integration-stack.sh` (init does). It finds the
api module from the manifest (role `api`, else type `java-boot`), seeds env
(`ci/prepare-integration-env.sh` → `lib/ci_prepare.py`), runs compose-gen, starts the dev compose and
waits on health (`ci/wait-health.sh <url> <expect> <seconds>`; all modules: `ci/wait-stack-health.sh`).
Manifest `ci.*` paths must match the files. Health targets: [REFERENCE.md#manifest](REFERENCE.md#manifest) (`ci.healthModules`).

Before a PR, locally:

```powershell
.\tools\stack-kit.ps1 compose-gen
git diff --exit-code **/docker-compose*.yml
.\tools\stack-kit.ps1 be check
.\tools\stack-kit.ps1 fe check
bash ops/ci/integration-stack.sh      # when Docker is available
```

## Adoption checklist

- [ ] `stack-kit.json` at the root with `$schema`; `stack-kit validate` clean
- [ ] `.\tools\stack-kit.ps1 help` lists the modules and types
- [ ] `ops/deploy/targets.json` declares the targets; `stack-kit targets --plan` shows the tree
- [ ] `ops/compose/catalog.json` is valid JSON
- [ ] `compose-gen` run; GENERATED files committed
- [ ] `.\tools\stack-kit.ps1 stack up -d --build` brings UI + API up locally
- [ ] CI workflow added; `ops/ci/integration-stack.sh` green

## Extending the kit

Every host extension goes through a declared point: `stack-kit extend --list` shows each (what it is
for, where the host file goes, `unused` | `drafted` | `answered`); `stack-kit extend <point> [<name>]`
makes it from its template, idempotently, never overwriting; the answers only the host can give are
`<<pending: ...>>` markers `validate` shows; `stack-kit extend --upgrade` merges a changed template
3-way into the host's file and reports a conflict instead of writing. Examples: `extend
infra-service sqlserver`, `extend catalog-environments staging`, `extend target linux`, `extend
backup-anchors postgres`, `extend driver go-api`, `extend module` (the draft from the tree, as
`init --plan`). The kit copy is never edited.

## Moving an existing host

| Situation | Do |
|---|---|
| Host on the former kit names, or on deploy.env | Since 2.0.0 none is read: `validate` names each one; `stack-kit migrate --apply` carries them (the manifest's name, `project`, the targets file, `legacyLayout`) and removes them ([CHANGELOG.md](../CHANGELOG.md) 2.0.0). |
| Manifest before v2, or former names | `stack-kit migrate` (dry run) → `stack-kit migrate --apply` → `stack-kit validate`. Raises `version` to 2, adds missing `role`s (from the driver's declared role), renames the manifest file and renamed fields; refuses a host holding both manifest names; prints, never rewrites, each line of the host's own files that still spells a former name. |
| Pre-v2 tree without a manifest | `STACK_KIT_LEGACY_ROOT_DISCOVERY=1` finds the root by `ops/config` or `secrets/` next to a vendored kit — a bridge until `stack-kit.json` exists. |
| A server tree laid out before the layout | declare `legacyLayout` on the target, then `stack-kit layout migrate` ([GOLDEN-PATHS.md#layout-migration](GOLDEN-PATHS.md#layout-migration)). |
| New stack type (Go, FastAPI, Next.js, …) | A new driver, never a renamed folder: [REFERENCE.md#drivers](REFERENCE.md#drivers). |

## Maturity

Release gate for the kit, and the bar for making it required for new hosts. Every row passes →
ready for multi-module hosts with optional multi-credential profiles.

| Area | Check | How |
|---|---|---|
| Boundary | no consumer names, no tool in a generic script, one home per fact | `pytest tests/unit/test_toolkit_hardcodes.py tests/unit/test_declared_agnosticism.py tests/unit/test_one_home.py tests/acceptance/test_identity.py` |
| Boundary | root = `stack-kit.json` | `ProjectContext.discover()` |
| Manifest | schema valid; every module has `role`, `type`, `path`, `secretsModule`; types in `drivers/registry.json`; declared places exist; migrations carry no data | `stack-kit validate` |
| Real stack | `validate.stages` ends on a value anchor | `stack-kit validate --stages` |
| Manifest | legacy trees migrated | `stack-kit migrate --apply` (one time) |
| Credentials | per-module `modules.<id>.credentials[]`; global `features.gcpCredentials` + `adapters.gcp` | `pytest tests/unit/test_credentials.py` |
| CI | host script manifest-driven; kit helpers `ci/*`; golden fixture | `ops/ci/integration-stack.sh`, `tests/fixtures/gc/` |
| Release | `VERSION` (semver), `CHANGELOG.md`, tag `v$(cat VERSION)` | `pytest tests/unit/test_release.py` |
| Delivery | release, rollback, prune, health, remote dev, migrate-layout, verify against a recorded server | [GOLDEN-PATHS.md#smoke](GOLDEN-PATHS.md#smoke) |
| Local debug | `launch.json` + `tasks.json` from `modules.*.path`; Java Extension Pack for Spring breakpoints | `stack-kit vscode-gen` |

Full verification from the host root:

```bash
(cd kits/stack-kit && PYTHONPATH=. pytest tests -q)
python3 kits/stack-kit/lib/validate_manifest.py
bash kits/stack-kit/ci/prepare-integration-env.sh
bash ops/ci/integration-stack.sh      # optional, needs Docker
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `stack-kit.json not found (run: stack-kit init)` | run from inside the host, or set `STACK_KIT_PROJECT_ROOT` |
| `Unknown driver type` | add the type to `drivers/registry.json` + `drivers/<type>/` |
| `modules.*.type is required` | write `type` on the module |
| `Unknown module: <id>` / `Unknown subcommand` | module ids are `modules.*` keys; valid subcommands are the driver's `commands` (`stack-kit help` lists them) |
| `refused: ... carries no ownership marker` | the directory is not this project's: `targets --init` claims an absent or empty one; an old tree moves with `layout migrate` |
| `compose-gen` fails | install Python; run from the host root |
| GENERATED drift in CI | `stack-kit compose-gen`, commit |
| `Git Bash required` | install Git for Windows (a driver command written in bash) |

## On Windows: a deep checkout

Windows limits a path to 260 characters. The kit keeps its own paths under 80 (a test holds it), so a
host vendored under a long folder still checks out; a host whose own paths are deep sets
`git config --global core.longpaths true` once.
