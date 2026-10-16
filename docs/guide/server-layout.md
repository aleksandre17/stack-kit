# Server layout

## Targets

A deploy target is declared once by the host: in `targets.json`, plus an ignored `targets.local.json`
for machine overrides. A target declares:

- `runtime`;
- `host`, `user`, `port`;
- `root`: the shared base every project lives under;
- `compose`: the compose invocation that host has, for example the standalone `docker-compose`;
- `ssh`: pinned host keys in a tracked `known_hosts`, an identity reference (never a key);
- `ports`: per environment and service.

A target that cannot be reached yet is `pending`, with its reason, and every deploy to it is
refused. `BatchMode=yes` and strict host-key checking hold on every target.

## The tree

The default layout lives in `config/deploy-layout.default.json`, and a target may override any
template in it:

```text
{root}/                                   shared by every project on the host
  {project}/                              this project's tree, marked .stack-kit-project
    {environment}/                        one disjoint tree per environment
      {tier}/{service}/
        releases/<commit>/                one release per commit
        current -> releases/<commit>      what runs; `release rollback` moves it
        runtime/  logs/  workspace/       runtime config, logs, the remote-dev source
      stack/compose.yml  stack/env/       the environment's one compose file and its env files
      infra/  backups/
```

## Isolation

- Only the resolver renders a remote path, and each path is checked to lie under
  `{root}/{project}/` before a command runs.
- Nothing ever acts on `{root}`, or on a directory without this project's ownership marker.
- Containers, networks and volumes are named `{project}-{environment}-{service}`, and compose
  projects `{project}-{environment}`.
- Ports are preflighted against every port the host already publishes.
- Two environments that share a data source are refused unless the sharing is declared, with its
  reason.

## Moving an older tree

`layout migrate` plans the move of a project's services out of a tree laid out before this layout,
given a declared mapping. It is a plan by default, and only `--approve` applies it.
