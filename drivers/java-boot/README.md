# java-boot driver

Gradle / Spring Boot multi-module deploy and remote dev for `stack-kit.json` modules with `"type": "java-boot"`.

## Commands

| Command | Purpose |
|---------|---------|
| `be deploy [svc] --dev\|--prod` | JAR + Dockerfile → `runtime/{container}/` |
| `be deploy watch [svc]` | Debounced bootJar → upload → `compose up --build` |
| `be dev bootstrap\|sync\|watch\|restart` | rsync source → `workspace/{container}/` + bootRun |
| `run` | Local `bootRun` + secrets `.env.dev` (manifest `modules.*.hybrid`) |
| `be manage` | stop/start/logs on server runtime paths |
| `be compose` | Local `docker-compose.dev.yml` / prod |
| `be check` | Pre-flight before deploy |
| `be modules` | List `ops.modules` registry |

Scripts: `sh/*.sh` (run via Git Bash on Windows: `tools/stack-kit.ps1`).

## Layout — `structured` vs `flat`

სრული ახსნა: [docs/GOLDEN-PATHS.md#server-layout](../../docs/GOLDEN-PATHS.md#server-layout)

| ტერმინი | მნიშვნელობა |
|--------|-------------|
| **`structured`** | `runtime/` (JAR) + `workspace/` (dev rsync) |
| **`flat`** | legacy `{DEPLOY_PATH}/{container}/` |
| **flat → runtime** | `migrate-backend-layout.sh` სერვერზე |

`ops/config/backend/.env.deploy`:

```env
DEPLOY_PATH=/home/user/project/backend
DEPLOY_LAYOUT=structured
```

| Kind | Path | Command |
|------|------|---------|
| runtime | `{DEPLOY_PATH}/runtime/{container}/` | `be deploy`, `be deploy watch`, `be manage` |
| workspace | `{DEPLOY_PATH}/workspace/{container}/` | `be dev` (requires structured) |

Without `.env.deploy`, deploy uses legacy **flat** paths.
## Golden paths

- **Local dev:** `./gradlew bootRun` or `be compose up`
- **Windows → Linux JAR staging:** `be deploy watch` (after one `be deploy`)
- **Windows → Linux source:** `be dev watch` (after `be dev bootstrap`)

Docs:

- [docs/GOLDEN-PATHS.md#backend](../../docs/GOLDEN-PATHS.md#backend)
- [docs/GOLDEN-PATHS.md#remote-dev-jar-flow](../../docs/GOLDEN-PATHS.md#remote-dev-jar-flow)
- Repo: `docs/BACKEND-DEPLOY-LAYOUTS.md`, `docs/BACKEND-DEV-REMOTE.md`, `docs/BE-DEPLOY-WATCH.md`

## Toolkit

| Script | Role |
|--------|------|
| `toolkit/deploy/deploy-path.sh` | `runtime/` / `workspace/` resolution |
| `toolkit/deploy/deploy-watch.sh` | `be deploy watch` loop |
| `toolkit/deploy/dev-remote.sh` | `be dev` rsync + workspace compose |
| `toolkit/deploy/*.sh` | Full deploy pipeline (gradle → upload → compose) |

Tests: `kits/stack-kit/tests/test_backend_*.py`

Smoke (local): `bash kits/stack-kit/scripts/backend-ops-smoke.sh`

Layout report: `stack-kit layout --backend -Markdown -OutFile docs/BACKEND-LAYOUT-SIMULATION-FULL.md`

Migrate flat → runtime on server: `bash kits/stack-kit/toolkit/deploy/migrate-backend-layout.sh --dry-run`
