# stack-kit infra

The infra stack a host declares (`stack.infra.services`: postgres, redis, an object store ...) --
on this machine, or on a target in the layout's `infra` place of an environment.

## Commands

| Command | Description |
|---------|-------------|
| `stack-kit infra local up\|down\|status [--prod]` | Docker on this machine (`Invoke-Infra.ps1`), by the local runtime's compose invocation |
| `stack-kit infra remote sync\|up\|down\|status\|purge --env <id>` | on the target: the compose files and `.env.runtime` (600) in `{root}/{project}/{env}/infra`, the compose project `{project}-{env}-infra` joined to the environment's network; `purge` asks first (`lib/delivery/infra.py`) |
| `stack-kit infra tunnel --env <id>` | ssh `-L` for `stack.infra.services` (ports from `infra-catalog.json` tunnel keys) |

## Consumer wiring

- `stack-kit.json` → `stack.infraComposeDir`, **`stack.infra.services`** (e.g. `["postgres"]`)
- Optional **`stack.infra.composeFiles`** — full `-f` list override
- Consumer: `docker-compose.base.yml` + `services/<id>.yml`
- Reference catalog: `compose/infra-catalog.json` (not required at runtime)

## Isolation

Each project's infra lives in its own `{root}/{project}/{env}/infra` under its own compose project;
`down` / `purge` never touch another project's.
