# Deploy targets

`targets.json` is where every deploy, remote dev, infra and tunnel command goes: named targets,
each with `host`, `user`, `port`, an absolute `root`, a `runtime`, `ssh` (an identity *reference*:
`agent`, `env:VAR` or `file:<ignored path>`; `knownHosts`; `hostKeys`: `pinned` | `accept-new`) and an
optional `layout` over the kit's default. It is tracked and reviewable, and holds no secret.

- `targets.local.json` beside it (gitignored) is merged over it on one machine only.
- `known_hosts` pins the servers' host keys; ssh runs with `StrictHostKeyChecking=yes`.
- `pwsh ops/cli/stack-kit.ps1 targets --plan` prints every target and each module's remote paths.
- `--target <name>` on any deploy verb picks one; otherwise `defaults.<environment>`.

Schema: `kits/stack-kit/config/deploy-targets.schema.json`; default layout:
`kits/stack-kit/config/deploy-layout.default.json`.
