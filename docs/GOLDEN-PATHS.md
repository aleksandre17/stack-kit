---
kind: guide
authority: canonical
owns: golden-paths
---

# Golden paths

The paths that work end to end, one command line each. Every verb, its options and exit codes:
[OPERATIONS.md](OPERATIONS.md) (generated from the CLI). Examples use `stack-kit` for the host's
launcher (`pwsh ops/cli/stack-kit.ps1` or `ops/cli/stack-kit.sh`) and the module ids `api` and `web`.

## Policy

- One goal, one command line; the same line in a terminal and in CI.
- A verb that changes a server prints its plan first -- every remote path and command -- and
  `--plan` stops there. Production asks before it acts; `--yes` answers for CI.
- Nothing a driver does is spelled here or in the kit's code: a module's build, its package, its
  container recipe, its dev container and its watch reactions are its driver's declarations
  (`drivers/registry.json`), over which the module may declare its own.

## Dev modes

| Mode | Command | Runs |
|---|---|---|
| local | `stack-kit dev up api --mode local` | the module on this machine, its `.env` + `.env.dev` in the process |
| hybrid | `stack-kit dev up api --mode hybrid` | the same, with the infra stack on the target and an ssh tunnel to it |
| docker | `stack-kit dev up all --mode docker` | the local compose stack (`compose-gen` output) |
| remote | `stack-kit dev up api` | the source synced to the target's workspace, run by the driver's dev container |

`stack-kit hybrid boot api` (alias form: `<alias> run`) is the host run alone.

## Remote dev

```
stack-kit dev up api --plan      # the workspace, the dev container, the ports -- nothing written
stack-kit dev up api             # sync, env file, dev container up, running
stack-kit dev watch api          # each saved change: sync, then the driver's reaction
stack-kit dev logs api --follow
stack-kit dev tunnel api         # ssh -L for the declared dev ports (and dev.debugPort)
stack-kit dev down api           # back to the unit's release, or stopped
```

The workspace is `{root}/{project}/dev/{tier}/{service}/workspace`. A sync is rsync when this
machine and the server both have it, else the kit's own index + tar stream over ssh; env files,
keys and credential files are never sent, and a directory the dev container fills (dependencies)
is never deleted. The reaction to a change is the driver's: `hot-reload` (the dev server reloads),
`restart` (the container), `rebuild` (its `dev.build` in the container).

## Server layout

```
{root}/                                   shared by every project on the host; never acted on
  {project}/                              this project's own, claimed by .stack-kit-project
    {environment}/                        dev, prod (catalogs.environments)
      {tier}/{service}/                   backend/api, frontend/app (each role's tier)
        releases/<commit>/                one per packaged commit
        current -> releases/<commit>      what runs; a deploy and a rollback move it
        runtime/                          runtime config and credentials, mounted read-only
        logs/                             upload.log, build.log, the service's own
        workspace/                        remote dev (a workspace environment only)
      stack/compose.yml                   the environment's one compose file, derived
      stack/env/<service>.env             each service's env file (600)
      infra/  backups/
```

`stack-kit targets --plan` renders it for the declared target; a target's `layout` may override any
template, never outside `{root}/{project}`.

## Deploy

```
stack-kit targets --init --env prod        # once: the tree and the ownership marker
stack-kit deploy api --env prod --plan     # what it will do
stack-kit deploy all --env prod            # package (once per commit) -> ship -> up -> health
stack-kit release list --env prod
stack-kit release rollback api --env prod  # current back to the release before it
stack-kit targets --verify --env prod      # read-only: the declared state against the host
```

Production takes a clean commit only, and rolls a release back when its health fails. One archive
per commit is built once (`.stack-kit/artifacts/<module>-<commit>.tgz`, `release.json` inside it)
and the same bytes are what CI deploys (`deploy --artifact`).

## Operate

```
stack-kit ops status --env prod
stack-kit ops logs api --env prod --follow
stack-kit ops restart backend --env prod   # a service, a module or a tier
stack-kit ops rm app --env dev             # asks; only inside the project's environment
```

## Layout migration

A tree the platform laid out before this layout moves out by declaration, never by a listing:
the target's `legacyLayout` names which old paths are this project's.

```
stack-kit layout migrate --target <t> --env prod             # the plan
stack-kit layout migrate --target <t> --env prod --approve   # the moves, after asking
```

A direct child of the shared root (`backend/`, `frontend/`, `infra/` ...) is never moved; a source
with another project's marker, or a destination that is not empty, refuses the whole migration.

## Smoke

`pytest tests` in the kit proves every path above against a recorded server and a project whose
driver the kit does not ship (`tests/acceptance/test_operator_cli.py`,
`tests/unit/test_delivery_engine.py`, `tests/unit/test_remote_dev.py`). What no test here can prove
is a real docker host: the layout's `unproven` says so.
