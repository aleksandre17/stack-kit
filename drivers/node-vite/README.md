# node-vite driver (SPA)

Stack-agnostic **single-page app** module driver: **Vite (React)**, **Angular CLI**, **Nx** — same commands if the module uses Docker compose with a **development** target and source volume.

## Commands

| Command | Purpose |
|---------|---------|
| `deploy local\|dist\|remote\|sync\|watch` | Artifact / compose deploy (`watch` = static dist loop) |
| `dev bootstrap\|sync\|watch\|restart` | Windows → Linux **source** sync (rsync), no `dist` build |
| `run` | Local `npm run <script>` + secrets `.env.dev` (manifest `debug.npmScript` / `hybrid`) |

**`deploy watch` vs `dev watch`:** [docs/GOLDEN-PATHS.md#frontend](../../docs/GOLDEN-PATHS.md#frontend)

| `compose`, `manage`, `check` | Module lifecycle |

## Remote dev

```powershell
stack-kit fe dev bootstrap -Environment dev
stack-kit fe dev watch
```

See project `docs/DEV-REMOTE.md`.

## Angular / Nx

1. Set `modules.<id>.type` to `node-vite` in `stack-kit.json`.
2. Provide `docker-compose.override.yml` with dev target + `.:/app` (or `develop.watch`).
3. Optional `ops.config.ps1`: `$OpsDevWatchPaths = @("src", "angular.json", "projects")`.
