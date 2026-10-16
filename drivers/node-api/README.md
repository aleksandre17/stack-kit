# node-api driver

Node HTTP services (Fastify / Express / Nest) for `stack-kit.json` modules with
`"type": "node-api"`. Same deploy **lifecycle** as `java-boot` (build artifact → docker
image → `up -d` → health-gate → rollback on failure), but the build is **pnpm**
(workspace) and the run is `node dist/index.js` inside a multi-stage image — not gradle/JAR.

Separate from `node-vite` (UI static dist + nginx): node-api is a long-running,
health-checked process/container, so its ops surface mirrors java-boot, not node-vite.

## Commands

| Command | Purpose |
|---------|---------|
| `<alias> deploy [svc] --dev\|--prod` | pnpm build verify → upload workspace context + Dockerfile → server `compose up --build` → health-gate → image rollback |
| `<alias> dev bootstrap\|sync\|watch\|restart` | rsync source → `workspace/{container}/` + `pnpm dev` (tsx watch) in container |
| `run` | Local host run — `pnpm run <debug.npmScript\|dev>` (via `toolkit/hybrid/Invoke-HybridRun.ps1`) |
| `<alias> manage` | stop/start/restart/logs/status/rm/rebuild on server runtime paths |
| `<alias> compose` | Local `docker-compose.dev.yml` / `--prod` with secrets env files |
| `<alias> check` | Pre-flight (package.json, pnpm, Dockerfile, `.env.prod` secrets) |
| `<alias> modules` | List compose services for this module |

Scripts: `sh/*.sh` (Git Bash on Windows, via the consumer's `stack-kit` entry script);
`ps1/hybrid.ps1` is the launch step of the kit's host run (`run`, `hybrid boot`).

## Build ordering

The module package is built with `pnpm --filter <name> build` (filter = the module
`package.json` `name`, auto-detected in `_init.sh` as `$NODE_PKG_FILTER`; workspace root
auto-detected as `$NODE_WORKSPACE_DIR`).

If other workspace packages must be built **first**, that ordering is **declared** — the
driver holds no privileged script name:

```json
"modules": {
  "svc": {
    "node": { "prebuildScripts": ["build:shared", "build:client"] }
  }
}
```

Each entry runs as `pnpm run <script>` from the workspace root, in declaration order,
before the module build. A declared script the workspace does not define is a **failure**,
not a silent skip. Absent or `[]` → nothing extra runs.

The production image's multi-stage Dockerfile re-runs this build server-side; the host
build is a fail-fast compile check (skipped on `--no-build`).

## Toolkit reuse

| Script | Role | Origin |
|--------|------|--------|
| `toolkit/deploy/common.sh`, `deploy-path.sh` | service discovery + `runtime/`/`workspace/` paths | shared (generic) |
| `toolkit/deploy/server-compose.sh` | per-service compose-gen on server | shared (generic) |
| `toolkit/deploy/pnpm-build.sh` | declared `node.prebuildScripts` + `pnpm --filter build` | node-stack step |
| `toolkit/deploy/node-upload.sh` | rsync workspace context + Dockerfile + env (no JAR) | node-stack step |
| `toolkit/deploy/node-docker-up.sh` | `up --build` + health-gate + **image** rollback | node-stack step |
| `toolkit/deploy/node-dev-remote.sh` | node workspace compose + `pnpm dev` + node watch globs | overrides `dev-remote.sh` |

Where java-boot does gradle/jar, node-api does pnpm-build/image. The generic SSH, env,
compose, deploy-path, and server-compose helpers are reused unchanged.

## Manifest

```json
"modules": {
  "svc": {
    "role":          "api",
    "type":          "node-api",
    "path":          "apps/svc",
    "secretsModule": "svc",
    "debug": { "npmScript": "dev" },
    "node":  { "prebuildScripts": [] }
  }
}
```

`cli.aliases`: e.g. `"s": "svc"`. Deploy expects a Dockerfile at the module path
(multi-stage, build context = pnpm workspace root) and `.env.prod` under the
secretsModule.

## Registry declarations

`drivers/registry.json` declares what this driver serves; no generator names it:

- `roles: ["api"]` — the role inferred when a module omits one.
- `tasks.devWatch: ["dev", "watch"]` — the argv used by `stack-kit dev up --mode remote`
  and by the VS Code watch task `vscode-gen` emits.
- `vscode.launch: "node-terminal"` — the launch shape `vscode-gen` emits.

Tests: `tests/unit/test_registry_integrity.py`, `tests/acceptance/test_driver_resolution.py`.
