# Module drivers

**Driver type** = stack toolchain (`java-boot`, `node-vite`, `node-api`, …).  
**Module id** = project key in `stack-kit.json` (`backend`, `frontend`, `bff`, …).  
**Role** (`api`, `ui`, `worker`) is documented in the registry only — the manifest always sets `type` explicitly.

```
drivers/
  registry.json          # type → runtime + commands (see registry.schema.json)
  java-boot/             # JVM / Spring — typical API
  node-vite/             # Vite UI — typical frontend
  node-api/              # placeholder for future Node HTTP API (see README there)
  _template/             # copy when adding a new type
```

## Rules (architecture does not break when you add stacks)

1. **Never** infer driver type from folder name `backend` / `frontend`. Only `modules.<id>.type` in `stack-kit.json`.
2. **Multiple APIs** are fine: e.g. `backend` → `java-boot`, `gateway` → `node-api` — different module ids, different types.
3. **CLI**: `stack-kit mod <moduleId> <command> …` always works; `fe` / `be` are optional aliases via `cli.aliases`.
4. **Commands** allowed per module = keys in `registry.json` → `commands` for that type (no hardcoded `modules` only on backend).
5. **Full-stack remote deploy** = `stackDeploy.steps` in manifest (not hardcoded be/fe in scripts).

## Add a new driver (e.g. Node backend)

1. Copy `drivers/_template/` → `drivers/node-api/` (or start from `node-vite` / `java-boot`).
2. Implement `_init` + `deploy` / `manage` / `compose` / `check` (only what you need).
3. Register in `registry.json`:

```json
"node-api": {
  "label": "Node — HTTP API (npm/pnpm, dist or container)",
  "roles": ["api"],
  "runtime": "powershell",
  "commands": {
    "deploy": "ps1/deploy.ps1",
    "manage": "ps1/manage.ps1",
    "compose": "ps1/compose.ps1",
    "check": "ps1/check.ps1"
  }
}
```

4. Point the module at the new type:

```json
"modules": {
  "backend": { "type": "node-api", "path": "backend", "secretsModule": "backend" }
}
```

5. Adjust `stackDeploy.steps` if this module replaces Java in remote deploy.
6. `.\tools\stack-kit.ps1 help` — lists types and per-module capabilities.

## Switch backend Java → Node (example)

Only manifest + driver folder change; `stack-kit be` still targets `modules.backend` via `cli.aliases.be`.

| Before | After |
|--------|--------|
| `"type": "java-boot"` | `"type": "node-api"` |
| `drivers/java-boot/` | `drivers/node-api/` (implemented) |

Frontend stays `node-vite`; catalog / compose may need catalog entries for the new service — that is the project's `ops/compose/`, not the driver registry.

## Resolution

- One resolver: `lib/resolution.py` reads `drivers/registry.json`; `lib/drivers.ps1` and `lib/drivers.sh` look its answers up
- List types: `python3 kits/stack-kit/lib/driver_api.py list-types`

See [docs/REFERENCE.md, Drivers](../docs/REFERENCE.md#drivers).
