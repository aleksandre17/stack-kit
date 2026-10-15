# Infra compose (consumer-owned)

Kit driver is **agnostic** — it merges yaml files you declare in `stack-kit.json`.

## Select modules (manifest only)

```json
"stack": {
  "infraComposeDir": "ops/compose/infra",
  "infra": {
    "services": ["postgres"]
  }
}
```

`stack-kit infra up` runs: `-f docker-compose.base.yml -f services/postgres.yml` (+ prod overlay if `-Prod`).

## Add a store (open/closed)

1. Add `services/my-store.yml` (services block only).
2. Add `"my-store"` to `stack.infra.services`.
3. Declare volumes/networks in `docker-compose.base.yml` if needed.

Reference modules: `kits/stack-kit/compose/infra-catalog.json`.

## Full manual control

```json
"infra": {
  "composeFiles": ["docker-compose.base.yml", "services/postgres.yml", "custom/extra.yml"]
}
```

When `composeFiles` is set, `services` is ignored.

**Do not** use `INFRA_PROFILES` env toggles — single source of truth is the manifest.

**Tunnel:** extend `infra-catalog.json` (consumer overlay) with `tunnel: [{ "env": "PORT_VAR", "default": "..." }]` per module.
