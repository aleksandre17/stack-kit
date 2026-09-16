# Package architecture — manifest-driven boundary

`geostat-kit` is a **reusable ops package**. It must not embed:

- Project brand names (any single consumer's product/repo name)
- Fixed repo trees (`secrets/`, `packages/`, `frontend/`, `deploy/compose/`)
- Optional artifacts assumed universal (`google-credentials.json`)

Everything resolves through **`geostat.ops.json`** at the **consumer project root**.

## Convention defaults (single source)

**`scaffold/geostat.ops.json`** is the only inline convention catalog. Runtime code reads defaults via:

- Python: `lib/manifest_defaults.py` → `default_field()`, `flatten_defaults()`
- PowerShell: `Get-ScaffoldManifestField` / `Get-ManifestField` (implicit scaffold default)
- Bash: `geostat_read_manifest_field` with empty default → Python `default_field`

No duplicate `DEFAULTS = {...}` dicts in package code.

## Layers

```text
┌─────────────────────────────────────────┐
│  geostat-kit (this package)             │
│  lib/project_context.py  ← single API   │
│  lib/project.sh / env.sh / project.ps1    │
│  drivers · toolkit · compose engine       │
└──────────────────┬──────────────────────┘
                   │ reads
┌──────────────────▼──────────────────────┐
│  Project root (consumer repo)          │
│  geostat.ops.json                       │
│  ops/config/  apps/*  ops/compose/     │
└─────────────────────────────────────────┘
```

## Manifest contract (required)

| Field | Purpose |
|-------|---------|
| `package` | Path to this kit (`kits/geostat-kit`) |
| `secrets` | Config root (`ops/config`) |
| `compose.catalog` | Compose generator input |
| `stack.composeDir` | Generated full-stack YAML |
| `modules.<id>.path` | App code directory |
| `modules.<id>.secretsModule` | Subdir under `secrets` for env files |
| `modules.<id>.type` | Driver id (`java-boot`, `node-vite`, …) |
| `cli.aliases` | Shortcut → `modules.<id>` (e.g. `fe` → `frontend`) |

## Optional (features / adapters)

| Field | Purpose |
|-------|---------|
| `features.gcpCredentials` | If `true`, global GCP profile applies to modules without `credentials[]` |
| `adapters.gcp.*` | `credentialsFile`, `containerMount`, `envVar` — default GCP profile |
| `modules.<id>.credentials[]` | Per-module files: `{ file, mount, envVar }` — **multi-credential** (overrides global for that module) |

Resolution: `lib/credentials.py` → `module_credentials(manifest, moduleId)`.

## Resolution API

**Python:**

```python
from lib.project_context import ProjectContext
ctx = ProjectContext.discover()
ctx.secrets_module_dir("<moduleId>")  # module id, not folder name
ctx.module_id_for_type("node-vite")
ctx.resolve_alias("fe")
```

**Bash:**

```bash
geostat_secrets_dir_for_module backend
geostat_module_id_for_type node-vite
geostat_default_remote_deploy_base "$(geostat_secrets_module_name backend)"
```

**PowerShell:**

```powershell
Get-ManifestModulePath (Get-ModuleIdByDriverType node-vite)
Get-DefaultRemoteDeployPathBase -SecretsFolder (Get-ModuleSecretsFolder frontend)
Resolve-CliAlias fe
```

## Project root discovery

1. **`GEOSTAT_PROJECT_ROOT`** env
2. Walk up for **`geostat.ops.json`** (required in normal use)
3. Legacy (opt-in): **`GEOSTAT_LEGACY_ROOT_DISCOVERY=1`** — `ops/config` or `secrets/` + `kits|packages/geostat-kit`

## CI & init seed

| Layer | Path | Role |
|-------|------|------|
| Package | `ci/prepare-integration-env.sh`, `ci/wait-health.sh` | generic seed + HTTP wait |
| Project | `ci.integration` in manifest (e.g. `ops/ci/integration-stack.sh`) | **api** module via `lib/project.sh` — no hardcoded `apps/backend` |

`geostat init` and `prepare-integration-env` → **`lib/ci_prepare.py`** — loops `manifest.modules`.

## Remote deploy path fallback

`DEPLOY_PATH` unset → `{DEPLOY_SERVER_BASE}/{DEPLOY_PROJECT}/{secretsModule}/` using manifest folder names.

## N-module model (multi-tenant package)

Any number of modules in `geostat.ops.json`:

| Field | Purpose |
|-------|---------|
| `modules.<id>.role` | `ui`, `api`, `worker`, `gateway`, `data`, `other` — stack order, layout, shortcuts |
| `modules.<id>.type` | Driver: `node-vite`, `java-boot`, … (`drivers/registry.json` + `roles`) |
| `modules.<id>.path` | App source tree |
| `modules.<id>.secretsModule` | Subdir under `secrets` |

**CLI**

- `geostat mod <moduleId> deploy …` — canonical
- `cli.aliases` — e.g. `fe` → `frontend` (consumer-defined)
- Auto shortcuts when one module per role: `ui`, `api`, `worker` → that module id

**Layout**

```bash
geostat layout --all              # every module + server overview
geostat layout --role api         # all api-role modules
geostat layout --module web       # one module
```

Deprecated: `--frontend` / `--backend` → use `--role ui` / `--role api`.

**Stack deploy** (`stackDeploy.steps` or default): `api` / `worker` modules first, then `ui`.

**Code:** `lib/modules.py`, `lib/modules.ps1`, `lib/modules_cli.py`

## Tests

Package tests use abstract names — never consumer project brands. `test_manifest_defaults.py` locks scaffold as default source.
