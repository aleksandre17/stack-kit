# stack-kit guide

stack-kit answers one question for a repository: *how is each module built, tested, packaged,
deployed, run remotely and operated?* It is a framework. The kit holds the drivers, the CLI, the
schemas, the templates and the layout; a host only declares its modules, targets and configuration.

| Page | What it explains |
|---|---|
| [overview.md](overview.md) | the manifest, modules, drivers, roles and tiers, the CLI |
| [server-layout.md](server-layout.md) | where everything lands on a server, and how projects never touch each other |
| [configuration.md](configuration.md) | the configuration catalogue, env files, secrets, data sources |
| [generated-files.md](generated-files.md) | every file the kit writes into a host, and what it is computed from |
| [extending.md](extending.md) | extension points: how a host adds its own without editing the kit |
| [consumes.md](consumes.md) | using a shared platform (edge, telemetry) the project does not own |
| [developing-the-kit.md](developing-the-kit.md) | changing the kit, versions, and how a host takes the change |

These existing documents stay where they are:

- [INSTALL.md](../INSTALL.md) and [ADOPT.md](../ADOPT.md): putting the kit into a host.
- [OPERATIONS.md](../OPERATIONS.md): every verb with its options and exit codes. It is generated
  from the CLI registry (`stack-kit help --markdown`).
- [REFERENCE.md](../REFERENCE.md): the manifest fields.
- [GOLDEN-PATHS.md](../GOLDEN-PATHS.md): end-to-end walks.
- [decisions/](../decisions/): the decisions and their rejected alternatives (ADR-001 and its
  amendments).
