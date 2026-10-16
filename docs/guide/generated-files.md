# Generated files

None of these files is edited by hand. Change the source and regenerate; `validate` reports drift,
and a deploy refuses a stale projection.

| File (default path) | Computed from | Verb |
|---|---|---|
| `ops/containers/<module>/Dockerfile` | the driver's container recipe and the module's fields, or the host's driver override | `render` |
| `ops/compose/stack/<env>/compose.yml` | the manifest, the target and the drivers; a deploy ships exactly these bytes | `render` |
| `ops/compose/stack/<env>/edge-routes.json` | `consumes.routes`; the platform's owner applies it | `render` |
| `<secrets>/<module>/.env.example` | the configuration catalogue | `render` |
| `ops/containers/<module>/server.conf` | a static (UI) module's web server config: the driver's template (`drivers/_shared/static/spa.conf`) with `container.serve` / `container.proxy`; the release ships exactly these bytes | `render` |
| `.github/workflows/*` | the manifest and the targets: build and test per module, SHA-pinned actions, dev to prod through GitHub Environments | `ci-gen` |
| local development compose, VS Code launch and tasks, module config, nginx config | the manifest | `compose-gen`, `vscode-gen`, `config-gen`, `nginx-gen` |
| `docs/OPERATIONS.md` (in the kit) | the CLI registry | `help --markdown` |

On the server, `stack/compose.yml` and each release's files are what the rendered projections
describe. `targets --verify` (read-only) reports any difference between the declared state and the
host's actual state.
