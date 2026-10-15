---
kind: guide
authority: canonical
owns: golden-paths
---

# Golden paths

The end-to-end paths that work: dev modes, local debug, remote dev, backend and frontend, deploy.
Examples use the scaffold aliases `fe` (ui, `node-vite`) and `be` (api, `java-boot`); substitute any
`<alias>` or `mod <moduleId>`. Verbs and flags: [REFERENCE.md#commands](REFERENCE.md#commands).

## Policy

- One goal = one command line. Use exactly one inner loop per goal.
- Prefix `deploy` = artifact (static `dist/`, JAR); prefix `dev` = live source + compose dev.
- Never mix, on one host, without a migration: `static/` (UI artifact) with `compose/dev/` (UI source), or `runtime/` (JAR) with `workspace/` (API source).
- Which watch a module has is declared by its driver (`drivers/registry.json` `tasks`), not by this page.

## Dev modes

| Mode | Runs where | Docker | VS Code |
|---|---|---|---|
| ① Host | your machine, Node/Java directly | no | launch: `<ui-module>: npm run dev`, `<api-module>: Spring Boot`, compound **Full stack (local)** |
| ② Local Docker | your machine, `localhost` | yes | launch `stack-kit: stack (compose dev)`; tasks `stack-kit: stack dev`, `stack-kit: <alias> compose up` |
| ③ Remote + Docker | Linux server over SSH; code edited locally | on the server | not in launch; tasks `stack-kit: <alias> dev watch` / `deploy watch` |
| ④ Hybrid | apps on your machine, infra on the server through an SSH tunnel | on the server | compound **Hybrid: infra tunnel + API + UI**; tasks `stack-kit: infra tunnel`, `stack-kit: infra remote up` |

`stack-kit dev up <alias|moduleId|all> [--mode hybrid|local|docker|remote] [--no-infra] [--no-tunnel]`:

| `--mode` | Does | Default when |
|---|---|---|
| `hybrid` | `infra remote up` (skip: `--no-infra`), tunnel in a new window (skip: `--no-tunnel`), then the module's driver `run` | `DEPLOY_SERVER` set in `deploy.env` |
| `local` | the module's driver `run` only | `DEPLOY_SERVER` unset |
| `docker` | `stack up -d --build`, ignores the target | — |
| `remote` | the driver's declared `tasks.devWatch` (rsync → server, container reloads); needs `DEPLOY_SERVER` | — |

`all` opens one window per module in `dev.bootOrder` role order (default api, worker, ui); in
`remote` mode, one watch window per module that declares `devWatch`. Adding a driver to `dev up` is a
registry declaration, not a code change.

### ① Host

```powershell
cd <ui-module-path>; npm run dev          # Vite, ~5173
cd <api-module-path>; .\gradlew bootRun
```

No Docker. The UI's API may be local or remote: `ops/config/<ui>/.env.dev` `VITE_API_URL`.

### ② Local Docker

```powershell
.\tools\stack-kit.ps1 fe compose up -d --build   # UI container only
.\tools\stack-kit.ps1 be compose up -d --build   # API container only
.\tools\stack-kit.ps1 stack up -d --build        # whole stack (stack.composeDir)
```

### ③ Remote + Docker

Requires `ops/config/deploy.env` `DEPLOY_SERVER`, `DEPLOY_LAYOUT=structured`, SSH in `ops/config/ssh/`.

```powershell
stack-kit dev up fe --mode remote     # rsync → server, watch in the container
stack-kit dev up all --mode remote    # every module, one terminal window each
```

By hand (bootstrap once first):

| Module | Goal | Commands | On the server |
|---|---|---|---|
| UI | remote dev | `fe dev bootstrap` → `fe dev watch` | `{DEPLOY_PATH}/compose/dev/{container}/` + Docker |
| UI | prod-like static | `fe deploy dist` → `fe deploy watch` | `{DEPLOY_PATH}/static/{container}/` + nginx |
| API | remote dev (bootRun in container) | `be dev bootstrap` → `be dev watch` | `{DEPLOY_PATH}/workspace/{container}/` |
| API | prod JAR | `be deploy all` | `{DEPLOY_PATH}/runtime/{container}/` |

### ④ Hybrid

| Step | Command |
|---|---|
| 1. infra on the server | `stack-kit infra remote up` |
| 2. tunnel | `stack-kit infra tunnel` (or the compound's preLaunch task) |
| 3. apps | `stack-kit hybrid boot <alias>` or `stack-kit <alias> run` |
| 4. F5 | Run and Debug → **Hybrid: infra tunnel + API + UI** |

- Services: `stack.infra.services`; env: `ops/config/<module>/.env.dev` with `INFRA_HOST=127.0.0.1` and peer URLs; `ops/config/infra/.env.dev`.
- Spring profiles: `modules.<id>.hybrid.springProfiles`. Java boot: JAR when `hybrid.preferJar` (default on Windows, avoids Gradle file locks; JAR path `hybrid.bootJar` or newest `build/libs/*SNAPSHOT*.jar`), else Gradle; force with `STACK_KIT_HYBRID_JAR=1` / `STACK_KIT_HYBRID_GRADLE=1`.
- A `role: worker` module gets its compose service from its own `modules.<id>` entry.

### Choose quickly

| I want | Use |
|---|---|
| F5, breakpoints, UI + API locally | **Full stack (local)** |
| UI only, locally | `<ui-module>: npm run dev` |
| everything in Docker on my machine | task `stack-kit: stack dev` / `stack-kit stack up -d --build` |
| apps local, infra remote, with breakpoints | `stack-kit dev up <alias>` (hybrid) |
| every module at once (hybrid) | `stack-kit dev up all` |
| edit on Windows, run on Linux + Docker | `stack-kit <alias> dev watch` / `stack-kit dev up <alias> --mode remote` |
| every module as remote watch | `stack-kit dev up all --mode remote` |
| prod UI on the server | `stack-kit fe deploy watch` |
| prod API on the server | `stack-kit be deploy all` |

## Local debug

`vscode-gen` writes `.vscode/launch.json` and `tasks.json` from the manifest (paths from `modules.*.path`, nothing hardcoded):

```powershell
.\tools\stack-kit.ps1 vscode-gen          # missing files only (init runs this)
.\tools\stack-kit.ps1 vscode-gen --force  # overwrite
```

| Generated | From |
|---|---|
| `<moduleId>: npm run <script>` (node-terminal) | driver launch `node-terminal`; `debug.npmScript` (default `dev`), `debug.label` |
| `<moduleId>: Spring Boot` (java) | driver launch `java`; `debug.java.mainClass` + `projectName`, else `*Application.java` and `settings.gradle` `rootProject.name` |
| `<moduleId>: dotnet run` (C# Dev Kit) | driver launch `dotnet`; `dotnet.project` or the module's single `*.csproj` (ambiguous → none) |
| `stack-kit: stack (compose dev)`, `stack-kit: <alias> check` | always |
| compound `Full stack (local)` | one API + one UI launch |
| compound `Hybrid: infra tunnel + API + UI` | only with `stack.infra.services`; `preLaunchTask` = `stack-kit: infra tunnel`; override with `vscode.hybrid.*` |
| tasks `stack-kit: stack dev` / `stack prod` / `stack down` / `compose-gen` / `validate` | always |
| tasks `stack-kit: infra tunnel` / `infra remote up` / `infra remote status` | with `stack.infra.services` |
| tasks `stack-kit: <alias> check`, `<alias> compose up`, `<alias> dev watch`, `<alias> deploy watch` | per module; watch tasks only if the driver declares them |

```json
"vscode": { "folder": ".vscode", "cliScript": "tools/stack-kit.ps1" },
"modules": {
  "api": { "type": "java-boot", "path": "apps/api",
           "debug": { "java": { "mainClass": "com.example.Application", "projectName": "my-gradle-root" } } },
  "web": { "type": "node-vite", "debug": { "npmScript": "dev", "label": "UI: Vite" } }
}
```

Extensions: Java/Spring — Extension Pack for Java; Node/Vite — the built-in terminal. Tasks run from
**Terminal → Run Task** (or as a `preLaunchTask` you add).

## Server layout

Structured layout (`DEPLOY_LAYOUT=structured`) in each module's `ops/config/<module>/.env.deploy`:

```env
DEPLOY_PATH=/home/<user>/<project>/<module>
DEPLOY_LAYOUT=structured
DEPLOY_PATH_MODE=base
```

- `DEPLOY_LAYOUT`: `structured` | `flat` (legacy, `{DEPLOY_PATH}/{container}/`) | `legacy`. No `.env.deploy` value → `flat`.
- `DEPLOY_PATH_MODE`: `base` (default; layout segments appended) | `full` (`DEPLOY_PATH` used as is).
- No `DEPLOY_PATH` → `stack.deployBaseSecretsModule`'s, else `{server base}/{project}/{folder}` ([REFERENCE.md#resolver](REFERENCE.md#resolver)).

| Module | Mode | Commands | Server path |
|---|---|---|---|
| UI | static prod/staging | `fe deploy dist` / `sync` / `watch` | `{DEPLOY_PATH}/static/{container}/` |
| UI | remote dev (source) | `fe dev bootstrap` / `sync` / `watch` / `restart` | `{DEPLOY_PATH}/compose/dev/{container}/` |
| UI | remote compose prod | `fe deploy remote -Environment prod` | `{DEPLOY_PATH}/compose/prod/{container}/` |
| UI | tar staging | `fe deploy remote` | `{SERVER_BASE}/{project}/deploy-staging/*.tar.gz` |
| API | JAR prod/staging | `be deploy <svc> --prod\|--dev` | `{DEPLOY_PATH}/runtime/{container}/` |
| API | JAR loop | `be deploy watch` | same `runtime/` |
| API | remote source dev | `be dev bootstrap` / `sync` / `watch` | `{DEPLOY_PATH}/workspace/{container}/` (structured only) |

Typical contents:

```text
static/{container}/          compose/dev/{container}/       runtime/{container}/
  .stack-kit-deploy.json       .env.dev                       Dockerfile   (src/Dockerfile: COPY app.jar)
  .env.runtime.json            docker-compose.yml             app.jar
  nginx.conf                   docker-compose.override.yml    .env.dev | .env.prod
  dist/index.html, assets/,    package.json                   docker-compose.{dev|prod}.yml
       config.json             src/…, public/…                logs/, versions/ (prod), .stack-kit-deploy.json
```

## Frontend

`node-vite` covers Vite, Angular CLI and Nx (compose dev + volume). Driver: [drivers/node-vite/README.md](../drivers/node-vite/README.md).

| Goal | Golden path | Not every day |
|---|---|---|
| dev on Windows (API on Linux is fine) | `cd <ui-path> && npm run dev` | `fe deploy watch` |
| dev in Docker on the same machine | `stack-kit fe compose up -d` | `fe deploy remote` |
| dev directly on Linux | `npm run dev` or `fe compose up` | `fe dev watch`, `fe deploy watch` |
| edit on Windows → UI on Linux (Vite in a container) | `fe dev bootstrap` → **`fe dev watch`** | `fe deploy watch`, `fe deploy remote` on each save |
| prod / staging static UI | `fe deploy dist` → `fe deploy sync` / **`fe deploy watch`** | `fe dev watch`, flat legacy |
| full stack prod | `stack-kit stack-deploy --prod` | mixed modes by hand |
| integration locally | `stack-kit stack up -d --build` | per-module SSH trees instead of the stack |

`deploy watch` vs `dev watch`:

| Command | Does | Server path | On each save |
|---|---|---|---|
| `fe deploy watch` | prod-like static | `.../static/{service}/` | `npm run build` → `dist/` → nginx reload |
| `fe dev watch` | remote dev (source) | `.../compose/dev/{service}/` | rsync only (no build); debounced |
| `fe dev sync` | one rsync | `.../compose/dev/{service}/` | — (no build, no restart) |
| `fe dev restart` | `docker compose restart` on the server | `.../compose/dev/{service}/` | — |
| `fe watch` | former alias → `fe deploy watch` (hint printed) | | |

Directly on Linux the architecture is unchanged (`stack-kit.json`, `ops/config/`, `kits/stack-kit`,
the `static/` / `compose/dev/` / `compose/prod/` tree, `be deploy`, `stack up`, `stack-deploy`); only
the active path changes. `fe dev *` is for editor on one host, runtime on another.

| Situation on Linux | Run |
|---|---|
| UI dev, all on one VM | `npm run dev` or `stack-kit fe compose up -d` |
| UI + API on the same machine | `stack-kit stack up -d --build` |
| prod static on this server | `stack-kit fe deploy dist` → `sync` / `deploy watch` |
| Linux laptop → another server | `fe deploy dist`, `be deploy` (same SSH); code on the server via SSH/remote IDE, not `dev watch` |
| code cloned on the server (`compose/dev/...`) | `docker compose up` / Vite there, no rsync |

The `node-vite` driver is PowerShell (`drivers/node-vite/ps1/`): `fe …` from bash goes through
`cli/stack-kit.sh` to `powershell` ([INSTALL.md#launchers](INSTALL.md#launchers)); `stack`, `compose-gen`,
`stack-deploy` run in bash. Or use `npm` + `docker compose` directly — same architecture, no CLI.

Scenario ids (`stack-kit layout --role ui`, `-Markdown -OutFile <file>`):

| Id | Command | Host |
|---|---|---|
| A1 | `npm run dev` | localhost |
| A2 | `fe compose up` (dev) | localhost |
| A3 | `fe compose -Prod up` | localhost smoke |
| A4 | `stack up` | localhost |
| A5 | `fe deploy local` | localhost Docker (`production` stage) |
| B1 / B2 / B3 | `fe deploy dist` / `sync` / `watch` | server `static/` |
| C1 / C2 | `fe deploy remote` dev / prod | server `compose/dev/` / `compose/prod/` |
| D1 / D2 / D3 / D4 | `fe dev bootstrap` / `watch` (rsync) / `sync` / `restart` | server `compose/dev/` |
| E1 | `stack-deploy` | server backend + frontend static |
| L0 | flat legacy | deprecated |

```powershell
# Windows / cross-host: Linux UI dev
.\tools\stack-kit.ps1 fe dev bootstrap -Environment dev
.\tools\stack-kit.ps1 fe dev watch -Environment dev
# prod static on the server
.\tools\stack-kit.ps1 fe deploy dist -Environment prod
.\tools\stack-kit.ps1 fe deploy sync -Environment prod
.\tools\stack-kit.ps1 fe deploy watch -Environment prod
```

```bash
# Linux, same machine
cd <ui-path> && npm run dev
./ops/cli/stack-kit.sh fe compose up -d     # needs PowerShell (node-vite)
./ops/cli/stack-kit.sh stack up -d --build
./ops/cli/stack-kit.sh stack-deploy --prod
```

## Remote dev: Dockerfile flow

UI case: `<ui-path>/src/Dockerfile` edited on Windows, run with `fe dev bootstrap` + `fe dev watch`.

| Where | Path |
|---|---|
| Windows (edit) | `<ui-path>/src/Dockerfile` |
| Linux deploy root | `{DEPLOY_PATH}/compose/dev/{container}/` |
| same file on the server | `.../compose/dev/{container}/src/Dockerfile` |
| in the container (volume) | `/app/src/Dockerfile` |

```yaml
# docker-compose.yml (GENERATED)            # docker-compose.override.yml (dev)
build:                                       build:
  context: .                                   target: development
  dockerfile: src/Dockerfile                 volumes:
                                               - .:/app
                                               - /app/node_modules
```

`src/Dockerfile` stages: `deps` (`npm ci`) → `development` (`COPY . .`, `EXPOSE 5177`, `CMD npm run dev -- --host 0.0.0.0`) → `builder` (`npm run build`) → `production` (nginx + `dist`, port 80 in the container, host port `DEPLOY_HOST_PORT:80`).

| Command | Stages used |
|---|---|
| `fe dev bootstrap` / `fe dev watch` | `deps` + `development` only |
| `fe deploy dist` | build on Windows; server serves `dist/` with nginx (not this compose) |
| `fe deploy local` | `production`, on the laptop |

`fe dev bootstrap -Environment dev`:

1. rsync the whole UI module (not only `src/`); excluded: `node_modules/`, `dist/`, `build/`, `.git/`, `.idea/`, `.vscode/` + `$OpsDevSyncExcludes` (`toolkit/powershell/Dev-Remote.ps1`).
2. On the server, in `.../compose/dev/{container}/`: `docker compose up -d --build` with target `development`; `builder` and `production` are not built.
3. Volumes: `.:/app` (server folder = `/app`), `/app/node_modules` (image deps; the host's empty folder does not shadow them). UI at `http://<server>:DEPLOY_HOST_PORT`.

`fe dev watch`: watch roots `src/`, `public/`, `vite.config.*`, … (`$OpsDevWatchPaths`); changes are
rsynced, no image rebuild, Vite HMR reloads JSX/CSS. A changed Dockerfile is copied but the running
image stays — rerun `fe dev bootstrap` after changing `CMD`, `EXPOSE`, the base image, or dev-stage
`RUN`/`COPY` (also for `package.json` structure). `fe dev restart` restarts env/process only.
Not in this flow: the nginx `production` stage, `npm run build` per save (`fe deploy watch`), `dist/` under `static/` (`fe deploy dist`).

Files: `<ui-path>/src/Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`,
`kits/stack-kit/toolkit/powershell/Dev-Remote.ps1` (rsync + compose up), `kits/stack-kit/drivers/node-vite/ps1/dev.ps1`.

## Backend

`java-boot` (Gradle / Spring Boot). Driver: [drivers/java-boot/README.md](../drivers/java-boot/README.md).

| Goal | Golden path | Not on each save |
|---|---|---|
| dev locally | `./gradlew bootRun` or `be compose up` | `be deploy` |
| Windows → Linux, bootRun in a container | `be dev bootstrap` → `be dev watch` | `be deploy` |
| Windows → Linux, JAR as staging | `be deploy` → `be deploy watch` | `be dev watch` |
| staging/prod on the server (once) | `be deploy <svc> --dev\|--prod` | full repo tar |
| quick JAR (already built) | `be deploy <svc> --no-build` | a full Gradle build |
| status / restart | `be manage <svc> …` | SSH by hand |

```powershell
.\tools\stack-kit.ps1 be compose up --build
.\tools\stack-kit.ps1 be deploy <service> --prod
.\tools\stack-kit.ps1 be deploy all --prod
.\tools\stack-kit.ps1 be manage api status --prod
.\tools\stack-kit.ps1 be modules
.\tools\stack-kit.ps1 be check
```

| Frontend | Backend |
|---|---|
| `static/` + `dist/` | `runtime/` + `app.jar` |
| `compose/dev/` + rsync | `workspace/` + `be dev` |
| `fe deploy watch` → npm build → `static/` | `be deploy watch` → bootJar → `runtime/` |
| `fe dev watch` → rsync → `compose/dev/` | `be dev watch` → rsync → `workspace/` (DevTools reload; `--restart` when needed) |

## Remote dev: JAR flow

| `DEPLOY_LAYOUT` | JAR deploy path | Source dev path |
|---|---|---|
| structured | `{DEPLOY_PATH}/runtime/{container}/` | `{DEPLOY_PATH}/workspace/{container}/` |
| flat (legacy) | `{DEPLOY_PATH}/{container}/` | none — `be dev` needs structured |

| Dockerfile | Used by | Runs |
|---|---|---|
| `<api-path>/src/Dockerfile` | `be deploy` | server `runtime/{container}/`, copies the pre-built `app.jar` (e.g. `FROM eclipse-temurin:21-jre-jammy`, `COPY app.jar app.jar`) |
| `<api-path>/src/Dockerfile.dev` | `be compose up` (local) | laptop, multi-stage build in the image |
| `<api-path>/src/Dockerfile.dev.remote` | `be dev bootstrap` | server `workspace/{container}/`, Gradle image + volume `.:/app` + `bootRun` |

Worker: `worker/Dockerfile`, `worker/Dockerfile.dev`, `worker/Dockerfile.dev.remote` — same pattern.

`be deploy` (JAR):

1. `./gradlew bootJar` — Windows or CI.
2. copy the jar → `<api-path>/app.jar` (`deploy_step_prepare_jars`).
3. scp `app.jar` + `Dockerfile` + `.env.*` → `{DEPLOY_PATH}/runtime/{container}/`.
4. server: `docker compose up --build -d` — the rebuilt image picks up the new `app.jar`.

`be deploy watch` repeats 1–4 on debounced saves (no full `check.sh`, no compose regeneration).

`be dev bootstrap` / `watch` (source):

1. rsync the API module (no `.gradle/`, `build/`) → `workspace/{container}/`.
2. `docker-compose.workspace.yml` generated on the server, `command: ./gradlew bootRun`.
3. volume `.:/app` — the container compiles on Linux.

`be dev watch`: rsync only; Spring DevTools reloads bootRun; `--restart` forces a compose restart (Dockerfile/Gradle changes). Flags: `--no-build`, `--no-initial-sync`.

```text
{DEPLOY_PATH}/
  runtime/{api-service}/     # be deploy, be deploy watch
  workspace/{api-service}/   # be dev bootstrap, be dev watch
```

## Deploy

1. Server prerequisites, once: `stack-kit infra` (SSH checks + Docker network); infra stack: `stack-kit infra remote up` (syncs `stack.infraComposeDir` first, then `up -d --remove-orphans`; `infra remote sync` alone uploads only).
2. Full stack: `stack-kit stack-deploy --prod` (or `--dev`; `--no-build`, `--skip-checks`). Steps: `stackDeploy.steps`, else the auto plan from `stack.composeModules` ([REFERENCE.md#manifest](REFERENCE.md#manifest)).
3. One module: `stack-kit be deploy …`, `stack-kit fe deploy dist -Environment prod`.

Explicit steps, when the auto plan does not fit:

```json
"stackDeploy": { "steps": [
  { "module": "backend",  "command": "deploy", "args": ["all"] },
  { "module": "frontend", "command": "deploy", "args": ["dist", "-Environment", "{environment}"] } ] }
```

`{environment}` → `dev` | `prod`; `--dev` / `--prod` is appended to each deploy step.

## Layout migration

Flat → structured:

1. `ops/config/<module>/.env.deploy`: `DEPLOY_LAYOUT=structured`.
2. `stack-kit layout migrate --dry-run [--backend|--frontend|--all] [--dev|--prod]`, then without `--dry-run` (per side: `toolkit/deploy/migrate-backend-layout.sh` / `migrate-frontend-layout.sh [--dry-run] [--dev|--prod]`).
3. `be deploy <svc>` / `fe deploy dist` → new files land in `runtime/` / `static/`.
4. Optional: remove the old `{DEPLOY_PATH}/{container}/` — `stack-kit layout cleanup [--dry-run]` (this host's dirs only; containers are not stopped).

Simulate first: `stack-kit layout --role api` / `--role ui` / `--all` (`-Markdown -OutFile <file>` writes a report).

## Deprecated

| Old | Use |
|---|---|
| `DEPLOY_LAYOUT=flat` (`.../<module>/{container}/` only) | `structured` + `static/` / `compose/dev/` / `runtime/` / `workspace/` |
| `fe deploy remote` on every change | `fe dev bootstrap` + `fe dev watch` (cross-host only) |
| `fe deploy watch` for Linux UI dev | `npm run dev` / `fe compose up`; `fe dev watch` only cross-host |
| `stack-kit fe watch` | `stack-kit fe deploy watch` |
| two trees on one host (flat + structured) | one structured tree; delete the old one after migration |
| `layout --frontend` / `--backend` | `layout --role ui` / `--role api` |
| catalog `features.worker` | `modules.<api>.compose.embeddedWorker` |

## Smoke

Every dev mode, without starting long-running services in mode ①:

```powershell
.\kits\stack-kit\scripts\dev-modes-verify.ps1                 # [-SkipDocker] [-SkipGradle] [-SkipNpm]
```

```bash
bash kits/stack-kit/scripts/dev-modes-verify.sh                # full, Docker integration if the daemon runs
bash kits/stack-kit/scripts/dev-modes-verify.sh --skip-docker --skip-integration   # kit + config only
```

| Mode | Automatic | Manual (E2E) |
|---|---|---|
| ① host | paths, gradlew, npm, launch.json | `npm run dev`, Java F5 |
| ② Docker | `<alias> check`, docker daemon | `stack up`, compose |
| ③ remote | `DEPLOY_LAYOUT`, `scripts/module-ops-smoke.sh` | SSH + `<alias> dev watch` |

Package gates without SSH: `tests/unit/test_dev_modes_smoke.py`, `tests/unit/test_golden_path_matrix.py` (B/D/C
separation), `tests/unit/test_frontend_contracts.py` (Dockerfile `EXPOSE 80`, compose `HOST:80`); all:
`bash kits/stack-kit/tests/run-kit-tests.sh` ([INSTALL.md#verify-the-kit](INSTALL.md#verify-the-kit)).
