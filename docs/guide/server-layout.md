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
        releases/<commit>/                one release per commit: its files and the recipe its image
                                          is built from on the target (a UI's with its server.conf)
        current -> releases/<commit>      what runs; `release rollback` moves it
        runtime/  logs/  workspace/       runtime config, logs, the remote-dev source
      stack/compose.yml  stack/env/       the environment's one compose file and its env files
      infra/  backups/
```

## Rolling back

`release rollback` moves `current` back to a named release (`--to`) or the one before it, as a
transaction (ADR-001 amendment 19):

1. **Judged first.** A release that cannot run as its service is declared now is refused, with
   nothing changed: a `build` service runs an image built from its release's own `Dockerfile`, so a
   release without one (a UI release made before 2.4.0, when UI files were mounted into a stock
   nginx) has nothing to build. The refusal names the release, why, and the remedy: check out that
   commit and `deploy` it, which packages it with today's recipe. `release list` marks such a
   release `!`, with the reason.
2. **`current` moves last.** The stack is brought up on the release -- its image built when the
   engine lacks it -- while `current` still names the running one; only when each service is healthy
   and its container runs that release's image does `current` move.
3. **A failure puts the previous release back.** A failed build, a failed `up`, an unhealthy service
   or a container left on another image brings the previous release back up (`current` never left
   it), and the verb exits 6 naming the failure and the build log
   (`{tier}/{service}/logs/build.log`) -- never a success.

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
