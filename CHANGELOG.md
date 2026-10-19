# Changelog — stack-kit

## 2.7.1 — 2026-10-19

The environment's network has one owner (ADR-001 amendment 23).

### Fixed

- `infra remote up` starts on a target whose network already exists. The CLI makes the environment's
  network before compose runs, while the scaffolded `ops/compose/infra/docker-compose.base.yml`
  declared that same network as compose's own -- so compose refused to adopt it (`network
  {project}-{env} was found but has incorrect label com.docker.compose.network set to ""`) and the
  infra stack could not start on any host whose stack had been deployed first. The generated stack
  compose already declared it `external`; the two halves of the kit now agree.

### Behaviour a host may notice

- The scaffolded infra base joins the environment's network as `external` and asks for its name with
  `${STACK_KIT_NETWORK:?...}` rather than defaulting to `app-net`: a name nobody declared is now a
  clear refusal instead of a second, silently different network. `infra remote sync` has always
  written that value; `infra local up` now sets it from the resolver and makes the network when it is
  not there, as the remote path does.
- A host takes it with a three-way merge of that template (`extend`), then `validate`.

### Added

- Resolver verbs `engine-command` (this machine's container engine invocation) and `local-network`
  (the network this machine's stack and infra share), so no second place invents either.

## 2.7.0 — 2026-10-18

Nothing is lost silently (ADR-001 amendment 22). An audit for one class of defect -- information
reduced, dropped or defaulted without saying so (CWE-222, CWE-223, CWE-390, CWE-636; OWASP A09/A10:2025)
-- found it in the secret scan, the step verdicts, CI, delivery's messages and remote dev.

### Behaviour a host may notice

- `scan secrets`, `validate` and `deploy` refuse a tree git cannot list or a history git cannot read
  (`NOT RUN`, exit 2) instead of scanning nothing and calling it clean. A tree under no version control
  is said to be one (`validate` warns; `scan` is NOT RUN).
- `scan secrets` reads every tracked text file whatever its size (a 2 MB limit hid large seed and dump
  files), and names every tracked file it cannot read as text (`NOT SCANNED: N ... -- a, b`).
- A dotnet-aspnet `test` that discovers no test **fails**, as pytest's and Jest's do; a module with
  none declares it (`dotnet.test: ""`). The count comes from the run's TRX report and is said:
  `103 test(s): 102 passed, 1 not executed (skipped)`.
- Generated CI holds every required lifecycle step even when the module's driver lacks it -- CI then
  fails the step as the local verb does, never drops it. Only an optional step is left out.
- `infra local up -Prod` with no `.env.prod` fails as a missing file; it never reads `.env.dev` for
  production. An absent prod overlay is said.
- `package` refuses a checkout whose `git status` fails, instead of recording it clean.
- A validate pipeline whose teardown fails fails (what it started may still be running).

### Added

- A lifecycle step's verdict names what ran and what did not: `test OK (1 module(s) ran; not run:
  api (declared none))`; `NOTHING RAN` when none did. A driver says it ran nothing through
  `Write-StepNotRun` or the file `STACK_KIT_NOT_RUN` names (drivers/README.md rule 4); the run record
  carries `notRun`.
- A failed tool's message carries the END of its output -- where compose, the engine, ssh or rsync say
  why -- with the cut stated, and the whole output kept under the runs directory
  (`lib/delivery/output.py`).
- Every PowerShell script the kit ships is parsed by a test (one had shipped unparseable).

### Fixed

- `infra` parses again: lines orphaned by the 2.0.0 delivery rewrite made the script unrunnable.
- Remote dev over rsync reacts to what changed: the watcher's two snapshots are compared before the
  newer one replaces the older (a `.csproj` edit was judged as a placeholder and hot-reloaded), and the
  summary no longer counts only the inherited files as everything rsync sent.
- The remote index of a workspace `find` cannot fully read fails instead of reading empty (which
  resent everything and deleted nothing).
- The port preflight says NOT CHECKED when the engine cannot list its containers, instead of reading
  no container as publishing nothing.
- A refused image scan lists every refusing finding (it listed ten); `migrations` names a declared
  `migrations.paths` directory that is not there and says when no ledger exists; `render --check` counts
  what it could not render, and names an environment whose delivery context does not open.
- `dev down` names a container the engine would not remove instead of reporting it stopped; the run
  record's `gitDirty` is null when `git status` fails; a release on a runtime that runs no container
  (static, IIS) says no health check and no image scan applied; the integration-stack CI script fails
  when it cannot list the stack's services instead of skipping the worker's health check.

## 2.6.0 — 2026-10-18

### Added

- Remote dev carries what a module's build reads from above its directory (`dev.inherited`, ADR-001
  amendment 21). dotnet-aspnet names `Directory.Build.props`, `Directory.Build.targets`,
  `Directory.Packages.props`, `global.json` and `NuGet.config`: each is found the way the build tool
  finds it -- the nearest directory above the module, up to the project root -- and sent to the
  workspace's root unless the module has its own. A watcher sees it change and restarts on it. A host
  may now keep central package management and shared properties above its projects and still run
  them in remote dev.

## 2.5.2 — 2026-10-17

### Fixed

- The launcher hands back Python as an argv on every platform. PowerShell unrolls a one-element array
  on `return`: where no `py` launcher stands (Linux, a CI runner) a lone `python3` came back as a
  string, `[0]` took its first letter, and every `mod` step failed with "The term 'p' is not
  recognized". Windows hid it: `py -3` is two elements. A test holds both lone interpreters.

## 2.5.1 — 2026-10-17

### Fixed

- `ci-gen` quotes every step name. A name in words may carry `: ` ("package (build once: one archive
  per commit)"), which ends a plain YAML scalar: GitHub refused the whole workflow before any job
  started, so every run failed in 0 s. A test holds every step name a quoted scalar.

The section below was written after the 2.5.0 heading and shipped in the commit tagged v2.5.0; it is
recorded here, where it was found to stand.

## 2.5.0 addendum — found by the fourth audit

Found by the fourth audit: the secret scan could be blinded by a fake `gates` key or by a tracked key
path, a class library's build output went unflagged, and a compose `build:` was read in one order only.

### Fixed

- `scan secrets` (tree and history) exempts only the specimen strings of an edit-gate document -- what
  its gates hold in `proves` and `admits` -- and scans the rest of the file. A settings file with a
  fake top-level `gates` key once hid every secret in it.
- A known exposure is matched by its value's sha256: a `knownExposures` row takes `fingerprint`, and a
  finding is known only when a value it carries hashes to it exactly. A new secret written at a tracked
  key, or one that contains a short tracked value, is a finding. A row without a fingerprint is still
  matched by the value at its key and is warned about (`scan secrets`, `validate`), with the way to add
  it: `scan secrets --fingerprint <file> <key>` prints the hash, never the value.
- Outside every module, a build output beside a project file only one driver names (`*.csproj`,
  `pom.xml`, `build.gradle*`) is flagged again whatever the project builds (a class library's `bin/` and
  `obj/`); a file several drivers name (`package.json`) still needs the driver's whole detection.
- `validate` reads a compose `build:` block in any field order (`args`, `target`, ...), as a flow
  mapping, and in the short form `build: ./dir`.
- `init --plan` drafts `security.secretPatterns` when the tree holds a taken secrets policy (a document of
  the edit-gate contract, by its shape, under a `secrets` directory, whose gates the scan believes; a
  copy under `.agents/taken/` first), and `commands.validate` beside `test` -- absent fields only.
- The secrets root's `.gitignore` keeps every `*.example` (a ui module named `web` lost its examples) and
  is laid in the declared secrets root, not always `ops/config`.
- The root `.gitignore` scaffold no longer carries another host's directories (`secrets/*`,
  `deploy/.env`, `frontend/logs/*`, `backend/logs/*`) nor the junk `/-OutFile`.
- Kit-laid docs (`ops/compose/stack/README.md`, `ops/config/profiles/*.md`) name the secrets root and a
  module's secrets folder, never `ops/config/backend` or `apps/backend/worker`.
- `compose-gen` skips a module whose driver declares no compose template for its role (dotnet-aspnet,
  node-api), with the reason, instead of failing with "no template" when the module has a `Dockerfile.dev`.
- `init` prints ASCII only: its banner and checklist no longer garble in a non-UTF-8 console.

## 2.5.0 — 2026-10-17

A generated secret reaches the app, and a known exposure is a key, not a file (ADR-001 amendment 20).
Both found by an independent audit of the first adopting host.

### Added

- `generatedSecrets` (a service field): how a runtime reads a generated secret -- `directoryEnv` for a
  directory of key-per-file values, else `<NAME>_FILE` -- and `reads` {glob, pattern, how}, what
  reading it looks like in code. dotnet-aspnet declares `KeyPerFile__Directory` and `AddKeyPerFile(`.
- `validate` refuses a module given a generated secret its code never reads (`config: modules.<id>:
  ... the secret would be made and ignored`), and one whose driver declares no `reads`.
- `generatedSecrets.reads.built`: what reading looks like in what a release carries. Every release is
  refused when its own built output does not read a generated secret its service is given, and
  `rollback` refuses a release on the server that does not (one made before, which ran on a committed
  key). dotnet-aspnet names its own assembly and `AddKeyPerFile`; java-boot and node-api now declare
  their `<NAME>_FILE` reading (node-api also built). `reads.glob` may be a list.
- `validate` refuses a credential-shaped value tracked in the tree, and `deploy` refuses to package a
  checkout that carries one -- the scan blocks, not only `scan secrets`. Known exposures are a warning,
  counted.
- Build output tracked in a project outside every module (a test project beside the app) is refused,
  beside that toolchain's project file; an editor's per-user state is refused
  (`config/editor-state.json`, from github/gitignore's JetBrains and Visual Studio templates).
- `generatedSecrets.uid`: the user a runtime's image runs as. Before the service starts, the release
  hands each generated file to that uid (0400) with the service's own image, run once as root with
  only `chown`/`chmod` and no network; the directory stays the deploy user's at 0755 (a runtime that
  loads a directory of secrets lists it; a key's name is no secret), its values the runtime's alone. dotnet-aspnet declares 1654 (`app`). Found by an
  independent review: the files were the deploy user's, and the app, running as `app`, could not
  read its key.

### Added -- a foreign project comes in with nothing hand-written

Found by adopting two foreign projects from zero (Maven + Vite, Gradle + Angular), stack-kit alone and
beside agent-kit; both now reach a green `validate` with no file written by hand.

- `java-boot` is built by Gradle or Maven: `pom.xml` is detected, the build uses the module's wrapper
  (`mvnw`, `gradlew`), else the tool on the PATH, else it is refused by name; the release jar follows
  the tool (`target/*.jar`); `validate` names a missing wrapper (driver field `buildTools`).
- The draft reads what a driver declares it can (`reads` with `value` and `capture`): a Spring app's
  `server.port` and its actuator's `/actuator/health` become the module's `container.port` and
  `healthPath`, and the local compose asks what the app serves.
- `init` declares each module's own test command (`commands.test-<module>`) beside `test`.
- `docs/guide/setup.md`: the pipeline step by step, the blueprint of a host, alone or with agent-kit.
  `docs/OPERATIONS.md` gains the drivers and the extension points, generated from their declarations.

### Fixed
- The kits never refuse each other: the secret scan reads a document of agent-kit's edit-gate contract
  (`gates[]` with `proves`/`admits`) by its shape, wherever it lies, as calibration -- a host that took
  agent-kit's secrets policy no longer fails `validate`.
- `init` lays files only for the tiers a module lives in (no `apps/backend/` for a project with no
  backend), composes each tier's local service from the module's own declaration (paths inside the
  repository for a module at the root), writes no local service whose recipe is not there and says
  so, declares no embedded worker nobody declared, and writes `ops.modules` beside the api module it
  lists or not at all; `validate` refuses a compose file that builds from a missing Dockerfile.
- `extend driver <name>` brings its `build` and `test` scripts as declared points, its entry names
  them, and a project registry at the default place is read without `drivers.registry` ("unknown
  driver" until the pointer was found by hand); the targets file `init` lays is read the same way.
- `init`'s checklist names the host's own modules (no scaffold folder names) and the CI workflow the
  repository already had, now running beside the generated one.
- The deep fixture path that broke a Windows checkout under a long folder is short (a test holds every
  tracked path under 80 characters).
- A build refused for a missing tool says so in one line, not as a script's stack.
- The schema validator reads `patternProperties`.

- The dotnet-aspnet driver handed a generated secret as `<NAME>_FILE`, which ASP.NET Core does not
  read: the app kept whatever value it found elsewhere.
- `scan secrets` no longer drops every finding in a file listed in `knownExposures`: a finding is known
  only on the line of a tracked key, a new secret beside it is a finding, and known findings are
  counted ("known is not clean").
- Docs: the dotnet-aspnet `run` reads `.env.dev` only (amendment 8); `REFERENCE.md` no longer lists the
  retired `static` field.
- Found by a re-audit: `scan secrets --history` failed on the first committed env file; every history
  finding was line 0, so a known one hid a new one in the same commit and file; a known leaf (`Key`)
  matched the end of another (`ApiKey`); the KNOWN count was printed only when nothing else was found.
- A generated value longer than 48 bytes was two lines (`openssl rand -base64` wraps; a Windows build
  writes CRLF), and an empty one could be moved into place.
- `dev down` and a failed rollback's restore bring a release back up only after its generated secrets
  are handed to its runtime's uid.
- A module can no longer override its driver's `generatedSecrets` (it could make the reach check pass
  with a pattern anything matches), except for a service built from its own `dockerfile`.
- The reach check skipped a host checked out under a directory named `bin`, `obj`, `dist` or
  `node_modules` (it read the absolute path); the secrets folders and the keys a folder is given have
  one definition each.
- Found by a third audit:
  - A known exposure is the VALUE at a tracked key path (in a JSON document; elsewhere, the key's own
    line), compared against the value each finding matched. A new secret under another key with the same
    leaf, or inside another value, is a finding. A line with several secrets yields several findings (it
    yielded only the first).
  - `deploy --artifact` -- the path generated CI takes -- scans the checkout too, and the first deploy job
    waits for the secret scan.
  - node-api (uid 1000) and java-boot (uid 10001) are handed their generated secrets.
  - Their `reads` pattern names each key (`@env@_FILE`, or a generic `endsWith("_FILE")` loader), so a
    `LOG_FILE` is not a reader.
  - The `generatedSecrets` override guard holds whatever kind the service is.
  - An automatic rollback never returns to a release that cannot run.
  - Outside every module a toolchain's project is where its driver's whole `detect` holds (a
    `package.json` beside a committed JavaScript action is not a web app).
  - The scan reads UTF-16 files, names git quotes, and files marked `-diff`. The built-in set knows AWS
    keys, GitHub tokens and a password named first.
  - `editor-state.json` gains the rest of the JetBrains template.

## 2.4.1 — 2026-10-16

`release rollback` is a transaction, and never reports a success it is not (ADR-001 amendment 19).
Found on a host rolling a UI service back to a release made before 2.4.0 (mounted static files, no
recipe): `current` moved and the verb succeeded while the container kept the new image; a second try
failed to build but had already moved `current`.

### Fixed

- `release rollback` judges the target release first: one that cannot run as its service is
  declared now (a `build` service whose release carries no `Dockerfile`) is refused, exit 5, with
  nothing changed, naming the release, why, and the remedy (check out that commit and `deploy` it).
- `current` moves only after the stack runs the release: built when the engine lacks its image, up,
  each service healthy and its container on that release's image. On any failure the previous
  release is brought back up (`current` never left it) and the verb exits 6 naming the failure and
  the build log.
- A rollback of several services to different releases builds and scans each one's own release (it
  built every service from the first one's).

### Changed

- `release list` marks a release that cannot be rolled back to with `!` and why.
- Exit 5 also names a release that cannot run as its service is declared now; `release` lists it.

## 2.4.0 — 2026-10-16

Every deployable module, UI modules included, runs an image built from its driver's recipe, so one
recipe serves the local docker stack, a dev release and prod (ADR-001 amendment 18).

### Added

- `commands.validate` in the manifest schema (beside `build`, `test`, `lint`): the line a host's law
  names as its enforcer `stack-kit:validate`, for agent-kit's stack-kit adapter to vouch for.

### Changed

- `node-spa` and `node-vite` release as `build` services: the shared recipe
  `drivers/_shared/static/Dockerfile` (pinned `nginxinc/nginx-unprivileged`, the `serve` directory
  COPYed to the web root, the rendered `server.conf` COPYed to nginx's config, `USER nginx`,
  `HEALTHCHECK` on `/healthz`). The image is built on the target from the release; `rollback` moves
  `current` as for an api.
- The release carries the rendered config as `server.conf` beside its `Dockerfile` (was
  `.stack-kit/static.conf`); `render` projects both `ops/containers/<module>/Dockerfile` and
  `server.conf`, and a release refuses either stale.
- The local stack: a driver declaring `compose.fromRelease` (both UI drivers) uses the
  `module_ui_release` compose-gen template -- built from the release tree `stack up` stages in
  `.stack-kit/local/<module>/<service>/` from what `package` left, a compose link per proxied
  service. `<module> run` and `dev up` are unchanged.
- Driver `container` vocabulary: `serverConfig` and `webRoot` (a web server's config template and
  root).

### Removed

- The `static` service kind and `container.static {image, mount, config, configMount}`: a
  declaration of it is refused naming the recipe. The `module_ui_stack_dev` / `module_ui_stack_prod`
  compose templates and `node-vite`'s `compose.dockerfiles`.

### Migration

- Run `render` and commit `ops/containers/<ui-module>/Dockerfile`. Remove any `container.static` of
  your own. Regenerate the local compose (`compose-gen`) and run `package <ui-module>` before
  `stack up`.

## 2.3.0 — 2026-10-16

What a project uses from a shared platform it does not own is a declaration (ADR-001 amendment 17).
A host with no `consumes` renders and deploys byte for byte as before.

### Added

- `consumes` in the manifest: `networks.<name>` {`services`, `owner`} (platform networks services
  join), `endpoints.<name>` {`env`, `services`, `owner`} (an address given as a variable), `routes[]`
  {`environment`, `host`, `path`, `service`, `port`, `network`, `tls`: `required`} (what the
  platform's edge is asked to serve). A target's `consumes` names each network on that host and each
  endpoint's address per environment.
- The stack compose joins each consumed network as external and sets each endpoint's variable; no
  deploy, regenerate or `nuke` creates or removes a consumed network.
- The deploy preflight reads that each consumed network exists on the target; a missing one is
  `NOT RUN` (exit 4, the plan included) naming the owner and the create command they would run --
  never run by this project.
- `render` writes each environment's routes to `projections.routes` (default
  `ops/compose/stack/<env>/edge-routes.json`), its `generated` field naming the sources, for the
  platform's owner to apply; validate reports drift, a release refuses a stale one.
- validate: a consumption that names an undeployed service or undeclared environment, a route the
  edge could not reach, a target without a consumed name or address, a consumed name in the
  project's own namespace, an address carrying a credential (never printed).

## 2.2.0 — 2026-10-16

The owed list after amendment 15, closed where it can be, and what a real host found (ADR-001
amendment 16). Each change is a declaration; the migration below names what a host does once.

### Added

- `render` (`--plan`, `--check`): generated projections of what a deploy runs -- each module's
  effective container recipe (`ops/containers/<module>/Dockerfile`), each environment's stack compose
  (`ops/compose/stack/<env>/compose.yml`), each secrets folder's `.env.example` from the catalogue;
  validate reports a stale one, a release refuses one (exit 5).
- `extend env <folder> --env <id>`: an ignored env file made from `config.keys` (non-secret values,
  SECRET pending -- `config` reports it, a deploy refuses it -- generated keys fresh and never printed,
  `none` data sources the unroutable sentinel). Catalogue keys gain `dataSource`, `environments`,
  `generate: "random:<bytes>"`.
- Isolation by data source: two environments that name one server and database through a
  `dataSource` key are refused by a deploy and reported by validate, unless `config.sharedDataSources`
  or a target's `sharedDataSources` declares it with a reason.
- `backup verify` restores SQL Server with `RESTORE ... WITH MOVE` into a uniquely named throwaway
  database (no more VERIFYONLY), anchors queried there, dropped in a finally; `backup replay` applies
  the whole migration chain to an empty throwaway database (`stack.migrate.replay`). Both plan first.
- java-boot `audit`: OSV-Scanner over the Gradle lockfiles (the binary, else its image through the
  local engine); `modules.<id>.audit` overrides (pin a digest there).
- `modules.<id>.package.exclude`: files kept out of every archive and image; release.json records them.
- `security.secretPatterns`: the secret scan's rules as agent-kit edit-gate documents, calibrated
  before use; the built-in set only when none is declared.
- Placement tokens in init and extension templates (`<tier:T>`, `<secrets:T>`, `<up:T>`): a tier's
  files go where the host's module lives (else the layout profile's `tiers`, else `apps/<tier>`).
- `config/vendored.json`: agent-kit's `extension-points.schema.json`, byte for byte, its origin and
  sha256 tested; the registry validates against it.
- Build output is never tracked: each driver declares `outputs` (what its toolchain writes,
  gitignore-style, relative to the module), a module adds its own in `modules.<id>.outputs`, and
  validate refuses every tracked file one matches, with its count and the fix.

### Changed

- A driver's VS Code launch is data (`vscode.launch`, `values`, `label`, `optional`); the generic
  generator names no debugger or tool, and the Full-stack compound takes one launch per role in boot
  order. `compose.opsModules` (java-boot) carries the local ops.modules rows.
- `BatchMode=yes` is first in every target's ssh options; a target declaring otherwise is refused.
- The extension-point registry is in the shared shape (`schema_version`, `required_by` one profile --
  `init` the base -- companions by the `<id>-entry` rule).
- sqlcmd reads its password from `SQLCMDPASSWORD`, never an argument.
- A driver's `generated` directories are its `outputs` patterns (`bin/`, `node_modules/`), read by
  validate, draft and the remote-dev sync alike.

### Migration

1. A host driver whose `vscode.launch` is a string (a former launch kind) declares the launch as data.
2. A host whose dev and prod name the same database marks the key `dataSource: true` and gives each
   environment its own store, or declares `environments: {dev: "none"}`, or declares the sharing in
   `config.sharedDataSources` with its reason -- a deploy refuses it otherwise.
3. A host with `config.keys` runs `stack-kit render` once and commits the projections: its
   hand-written `.env.example` files are now projections of the catalogue (validate reports drift).
4. A java-boot module locks its dependencies (Gradle `dependencyLocking`) for its audit to run.
5. A host driver that declares `generated` renames it `outputs`, each entry a pattern (`build/`); a
   host that tracks build output untracks it as validate names (`git rm -r --cached <dir>`).

## 2.1.0 — 2026-10-16

What the earlier platforms proved, carried as mechanisms (ADR-001 amendment 14), and one extension
grammar (amendment 15). No host change is required; each mechanism is a declaration a host opts into.

### Added

- Release images: unprivileged USER and a HEALTHCHECK in every recipe (`healthPath`, else the port);
  a hardened static server (same-origin `container.proxy`, nosniff, Referrer-Policy, gzip, cache
  rules, `/healthz`); built-bundle checks (no plain-http URL, no IP); floating images refused
  (`requireDigests` for digests); `security.imageScan` (digest-pinned scanner, failOn, observeOnly,
  maxDbAgeHours, OpenVEX).
- Configuration: the env-value `policy` of a catalogued key, run before every release and by
  `config check`; `policy.generate` (made on the server once, `<NAME>_FILE`); the injection
  contract `STACK_KIT_ENV_FILE_<FOLDER>_<ENV>` (ci-gen writes secrets outside the checkout).
- Data: `backup <store>`, `backup verify` (a throwaway restore against declared anchors),
  `backup list`; `stack.migrate` before the apps; `migrations lock|check` (a checksum ledger).
- CI: `ci.database` (a healthy, migrated database, DATABASE_URL); a secrets job; the `audit`,
  `e2e`, `visual` step kinds.
- Security: `scan secrets [--history]` (structural, fingerprints of known leaks, no value printed).
- Infra templates: SQL Server, MinIO, Redis with auth, OTel collector, Prometheus, Grafana, Tempo,
  Keycloak, Flyway, the edge; `tls ca|leaf|truststore`.
- Operate: OIDC readiness in `targets --health`; `ops restart-check`; `ops prune [--schedule]`;
  log rotation; environment isolation in validate.
- `extend` (extension points), `config/conformance.json` (machine-checked).

### Removed

- `scaffold/apply-scaffold.*` (init is `extend --init`).

## 2.0.0 — 2026-10-16

One generic pipeline, one operator CLI, one home per value (ADR-001 amendment 13). Breaking.

### Migration (one command, once)

1. `stack-kit validate` names every former home a host still carries.
2. `stack-kit migrate --apply` carries them and removes them: deploy.env's server and ssh become a
   target in `ops/deploy/targets.json`; `DEPLOY_PROJECT` (else `COMPOSE_PROJECT_NAME`) becomes the
   manifest's `project`; a folder's `DEPLOY_HOST_PORT` becomes the target's `ports`, its `DEPLOY_PATH`
   a `legacyLayout` unit; `COMPOSE_*_SERVICE`, `DOCKER_NETWORK`, `INFRA_SLUG`, `DEPLOY_LAYOUT`,
   `stack.networkName`, `stackDeploy`, `roles.serviceOverride` are dropped (derived now); the former
   manifest filename and fields are renamed. Env files keep every other key.
3. On a server laid out before: `stack-kit layout migrate --target <t> --env <e>` (the plan), then
   `--approve`. A new tree: `stack-kit targets --init --env <e>`.
4. A host whose server has only the standalone compose declares `"compose": ["docker-compose"]` on
   its target. The local stack's app host port is `APP_HOST_PORT` (was `DEPLOY_HOST_PORT`).

### Added

- `lib/delivery/`: package -> ship -> up -> health; `releases/<commit>` + `current`, `release
  list|rollback`, prune to `keep`, rollback on failed health where the environment declares it,
  one compose file per environment, env files 600, runtime config and credentials read-only,
  namespaced names, preflights (marker, runtime, ports, disk), `targets --init`, `targets --verify`
  (the declared state against the host, read-only), `ops status|logs|start|stop|restart|rebuild|rm|nuke`,
  remote dev (`dev up|down|sync|watch|logs|status|shell|tunnel`; rsync or the index + tar fallback),
  `infra remote` and `infra tunnel` in the layout, `layout migrate` from a declared `legacyLayout`.
- The tier: `config/catalogs/tiers.json`, each role's `tier`; the unit `{env}/{tier}/{service}`;
  `backups/`, `stack/state.json`.
- Drivers declare `container` (a recipe template under `container/`, or a static image) and `dev`;
  every packaging driver (dotnet-aspnet, java-boot, node-api, node-spa, node-vite) releases through the kit.
- The CLI is `lib/cli/` (discovered verbs, plan before acting, `--plan`, `--yes`, exit codes 0-6,
  the run record); `help --markdown` renders `docs/OPERATIONS.md`; ci-gen deploys through
  `deploy --artifact --yes` with a `workflow_dispatch` environment choice.
- Environments declare `requireClean`, `rollbackOnFailure`, `confirm`; target runtimes declare
  `engine`, `compose`, `stack`, `local`; targets declare `compose`, `engine`, `healthWait`,
  `minFreeMb`, `legacyLayout`; the manifest declares `project`, `stack.services`, module
  `container`/`services`/`dev`/`credentialPatterns`, runtimeConfig `mount`.
- Tests: one home per fact (deny-by-default, with sensors), no import cycle, docs drift, the
  operator CLI end to end, the engine against a recorded server through a driver the kit does not ship.

### Removed

- Every read of deploy.env, `.env.deploy`, DEPLOY_*, COMPOSE_*, DOCKER_NETWORK, INFRA_SLUG and of the
  kit's former names (`legacyRemovedIn` 2.0.0); `cli/geostat.*`.
- Every driver deploy/dev/manage/compose/check script; `toolkit/deploy`, `toolkit/bash`,
  `toolkit/powershell`, `toolkit/layout`, `toolkit/stack`, `toolkit/templates`,
  `toolkit/infra/ensure-prereqs.sh`, `gen_server_compose.py`; `lib/deploy_paths.py`,
  `lib/stack_deploy.py`, `lib/migrate_layout_*`, `lib/ssh.*`, `lib/drivers.sh`, `lib/runs.ps1`,
  `contracts/`; `unpack`, `stack-deploy`, `layout` (simulators, cleanup); the registry's `deployKind`,
  `layoutSimulator`, `promotes`.

## 1.2.0 — 2026-10-16

### Extension is a declaration (ADR-001 amendment 12)

- Script runtimes declared (`config/runtimes.json`, manifest `runtimes`); a command may be
  `{script, runtime}`. **Removed:** the registry's `runtime` field (read with a notice).
- `validate` holds the composed registry to `drivers/registry.schema.json`; a malformed registry is
  refused by name.
- Catalogs (`config/catalogs/`, manifest `catalogs`): roles, environments, lifecycle steps, target
  runtimes; every lifecycle step is a CLI verb; adding `staging` or `typecheck` touches no code.
- Driver capabilities replace every driver id outside `drivers/` (compose templates, Dockerfiles,
  ops modules, nginx, layout simulators); `compose-catalog.json` lost `templateKey`.
- `ci.actions` (project pins, SHA-only); `vscode.launch` as data; `ci.runsOn` / target `runner`.
- The compose naming no longer privileges a module named `frontend`.

### CD generated: build once, promote the same bytes (ADR-001 amendment 11)

- `stack-kit package <module>` / `unpack <module> <archive>`: the driver's declared `package` step, one
  archive per commit (+ sha256); drivers declare `package` (or `pending`) and a release's `promotes`.
- `ci-gen` adds, on the default branch, package + SBOM + build-provenance attestation per module, and
  `deploy-dev` -> `deploy-prod` (GitHub Environment per target, concurrency per target/env) that unpack
  the same archive, deliver, and verify (`targets --health`, `targets --verify`); CI only, with the
  reasons, without reachable targets or a promotable module. Run records uploaded per job.
- `targets --health`: a target's declared `health` URLs per environment.

### The manifest is drafted from the tree (ADR-001 amendment 10)

- Drivers declare `detect` (the evidence a directory is their module, and what they read from it);
  `init --plan` drafts modules, aliases, `commands`, `layout.profile` as additions against the current
  manifest; `init --approve <who>` writes them (`draft.approvedBy`). Declared fields always win; a
  directory two drivers claim is refused.
- `layout.profile`: canonical trees declared in `config/layout-profiles/` (`monorepo`), derived as floor rows.

### Where a deploy goes is declared (ADR-001 amendment 9)

- **Deploy targets:** manifest `deploy.targets` names `ops/deploy/targets.json` (tracked, no secrets;
  schema `config/deploy-targets.schema.json`), merged under a gitignored `targets.local.json`. Per
  target `host`, `user`, `port`, `root`, `runtime`, `ssh` (identity reference, pinned `knownHosts`,
  `hostKeys`), `layout`, `ports`, `keep`, `pending`; `defaults` per environment. `--target <name>` on
  any verb.
- The resolver answers the server, ssh options (`ssh-args`; `StrictHostKeyChecking=yes`) and every
  remote path (`remote-path`) from the selected target; the shells only ask it.
- **Default remote layout** (`config/deploy-layout.default.json`): `{root}/{project}/{environment}/`
  with `modules/{service}/`, `stack/`, `infra/`; any template overridable per target.
- **Isolation:** every path refused outside `{root}/{project}/`; an ownership marker
  (`.stack-kit-project`) written or checked before any write; compose project `{project}-{environment}`;
  declared ports unique per host and checked against other compose projects at deploy; removes and
  prunes confined; node-vite staging moved inside the module's directory.
- `stack-kit targets [--plan|--verify]`: each target; the whole tree; read-only drift over ssh (exit
  1 drift, 2 not verifiable).
- `modules.<id>.runtimeConfig[]` declared and validated (no secret).
- Deploy provenance: `IMAGE_REVISION` into compose; a prod deploy from a dirty checkout is refused.
- **Deprecated:** `deploy.env` `DEPLOY_SERVER`, `DEPLOY_SERVER_BASE`, `DEPLOY_PATH`, `DEPLOY_LAYOUT`,
  `DEPLOY_PATH_MODE`, `DEPLOY_SSH_*` (read until 2.0.0 on a host without targets; `validate` names
  them; `migrate --apply` declares them as a target). `/home/deploy` is no longer a fallback.
- Pending: the release/`current` delivery, `stack/` compose, runtime-config upload, namespaced
  container/network/volume names (need a docker host to prove).

### A new project works with no setup of its own (ADR-001 amendment 8)

- **Breaking: a run on this machine reads one environment.** `run` / `hybrid boot` read the
  module's shared `.env`, then `.env.dev`; `.env.prod` only with `--env prod`. A development run no
  longer fills from `.env.prod`. `validate` / `migrate` name, per secrets folder, the keys it lost.
- Lifecycle steps per driver: `build`, `test`, `lint` (`dotnet-aspnet`: dotnet build/test/format;
  `java-boot`: Gradle build/test; Node family: package.json scripts through
  `toolkit/node/Invoke-PackageScript.ps1`). `stack-kit build|test|lint [module ...]`: every module,
  fail-fast, the step's exit code.
- New driver `node-spa`: any SPA by its own package.json scripts (Angular CLI, Vite, React, Vue).
- Manifest `commands` {`test` (required), `build`, `lint`, `run`}: literal command lines for every
  tool; the scaffold writes them through the launcher; `validate` checks the scripts they name.
  New fields: `dotnet.solution`, `dotnet.test`, `node.scripts`, `node.packageManager`,
  `toolchain.version`, `ci.workflow`.
- `stack-kit ci-gen [--force|--check]`: `.github/workflows/ci.yml` from the modules, actions pinned
  by verified SHA (`lib/ci-actions.json`); `init` writes it.
- `init` works again (it failed at its first Python call) and its result validates; module env
  examples moved to `ops/config/<module>/.env.example`; the scaffold ships an nginx template.
- Run record: one JSON line per `deliver` rung and lifecycle step in `.stack-kit/runs/runs.jsonl`
  (self-ignoring).
- Layout migrations find their module by `deployKind`, not by driver name; deploy markers name the
  module that wrote them.
- Hygiene: no BOM outside PowerShell; every non-ASCII `.ps1` carries one (Windows PowerShell 5.1);
  README quick start; license pending; `vendorDirs` + `platform/kits/stack-kit`.

### The owed list, closed (ADR-001 amendment 7)

- **Breaking for a host on the former keys, carried by `migrate --apply`:** `ci.<name>` script paths
  the schema spelled for one consumer (`ragSmoke`, `ragEval*`, `chat*Smoke`, `corpusQualityAudit`,
  `verifyServicesProd`, …) → `ci.scripts.<name>`; `modules.<id>.catalog` / `.derivation` →
  `modules.<id>.extensions.*`. The module object is closed: an undeclared field is refused.
  `validate` names the door. Each `ci.scripts` path must exist and is a layout-floor row.
- `run` is the kit's host runner for every driver that declares `hybrid.script`
  (`lib/modules.driver_commands`); the four `drivers/*/ps1/run.ps1` delegates are deleted.
- `stack-deploy` names no driver: the environment is the release rung's `--{environment}` and the
  options a rung passes on are its `forwards` (`java-boot`, `node-api`: `--no-build`,
  `--skip-checks`). `node-api` now deploys the environment asked for. The runner calls the kit's
  CLI, not a host's `tools/stack-kit.ps1`.
- `lib/driver_api.py` and `lib/modules_cli.py` folded into `lib/resolve_cli.py` (`driver-types`,
  `driver-command`, `stack-steps`, `stack-health`, `stack-endpoints`, `compose-names`,
  `compose-service`).
- `lib/module-manifest.ps1` deleted; a driver reads its own fields with `Get-ModuleField`. The JAR
  boot moved to `drivers/java-boot/ps1/_jar-boot.ps1`.
- The deploy-base secrets folder defaults to the primary API module's, not `backend`.
- Kit Python scripts speak UTF-8 on Windows pipes (`PYTHONUTF8=1`, child only).
- Driver, toolkit and CI READMEs link the kit's guides; the link test holds them. CLI help names
  `--mode remote` and `deliver`.

### The host run is declared too (ADR-001 amendment 6)

- `toolkit/hybrid/Invoke-HybridRun.ps1` names no driver. The `java-boot`, `node-vite` and
  `node-api` launch steps moved into each driver's declared `hybrid.script` (`ps1/hybrid.ps1`),
  as `dotnet-aspnet`'s already was; a driver without one is refused by name. `node-api` gains
  the `hybrid` delivery rung its launch step always had.
- `stack-kit hybrid boot <id>` runs the shared runner directly, not through the driver's `run`.
- A host run's environment is the resolver's rule (`envfile.HOST_RUN`: `.env.dev` over
  `.env.prod`; `resolve_cli.py run-env <folder>`; `Import-ModuleRunEnv`), not a fourth parser
  in the runner. An empty value in `.env.prod` no longer unsets a variable of the process.
- Layout floor: a declared `config.keys` and `vscode.cliScript` are rows; missing, they fail.
- `docs/INSTALL.md`: the hand-written launcher example used the advanced param block that
  loses `-d`; it now shows the simple one the scaffold ships.

### Delivery ladders by declaration (ADR-001 K6)

- Each driver declares its delivery ladder in `drivers/registry.json` `delivery`: rung →
  `{command, args}` (a driver command; `{environment}` substituted), `{via}` (a kit verb, e.g.
  `hybrid`) or `{pending}` (named, not built, with its reason). Declared today:

  | Driver | local | hybrid | remote-dev | release | container |
  |---|---|---|---|---|---|
  | java-boot | run | via hybrid | dev | deploy all | — |
  | node-vite | run | via hybrid | dev | deploy dist -Environment {environment} | — |
  | node-api | run | via hybrid | dev | deploy | — |
  | dotnet-aspnet | run | via hybrid | — | deploy artifact | pending: needs a docker host to prove it |

  The `release` rung is the one home of what `deployArgs` held (`stack-deploy` reads it; a project
  registry still saying `deployArgs` is read).
- `stack-kit mod <id> deliver <rung> [--env dev|prod] [--plan]` runs a rung, or prints its plan.
  An undeclared rung is refused, naming the declared ones; a pending rung is refused with its reason.
- `cli/stack-kit.ps1` names no driver. Its branches for two drivers' `watch`, `run` and
  `deploy` became declarations (`operands`: a word the driver rewrites, with its hint) and one
  generic dispatch. A `.sh` script runs under bash, a `.ps1` in the session, whatever the driver's
  `runtime` says. A PowerShell script's `-Name value` operands bind to the parameters it declares.
  A project driver (K7b) used to be dispatched by the kit registry's `runtime`; it is now
  dispatched by its own scripts.
- Off Windows, the CLI finds bash on PATH.

### A project may declare its own drivers (ADR-001 K7b)

- `drivers.registry` in the manifest names a project registry in the kit's shape. Its drivers
  live beside it (`<registry dir>/<id>/`) and are composed with the kit's by `lib/modules.py`,
  the one home of the composition. The resolver, driver dispatch, validate and every runtime
  see them.
- An id the kit already has is refused (`drivers: ... are the kit's`), never shadowed. The
  declared registry file is a layout-floor row.

### Configuration carries its sensitivity (ADR-001 K5)

- A host names its key catalogue in the manifest (`config.keys`). The kit owns its shape
  (`config/config-keys.schema.json`): per key `sensitivity` (SECRET, INTERNAL, PUBLIC), `owner`,
  `allowedSource`, `rotation` (required for SECRET), an optional non-secret `default`, extra
  `env` spellings; `knownExposures`; `orphans`.
- `validate` refuses a SECRET given a real value in any tracked env file, JSON or YAML: the key's
  path, or its environment spellings (`A:B` → `A__B`, `a.b` → `A_B`). A placeholder
  (`__NAME__`), an empty value or a `${...}` reference is not a value. A SECRET with a `default`
  or without a `rotation` is refused. A finding names file, place and key, never the value.
- An exposure already known is listed under `knownExposures` with the work that removes it. It
  is then printed on every validate instead of failing. Rotate first: the value is already in
  history.
- java-boot env-profile generation adds no integration of its own. The model, speech and cloud
  keys and the AI and `com.<consumer>.chat` loggers it rendered into every env-profiles module
  were one consumer's. A module declares its own block in `modules.<id>.configGen.profileYml`.

### Validation is a proof (ADR-001 K4)

- **The manifest schema is enforced on every machine.** `validate` used to hand
  `manifest.schema.json` to `jsonschema` when it happened to be installed and skip it otherwise,
  so on a host that had installed nothing every `required`, `enum` and
  `additionalProperties: false` was decoration. `lib/schema_check.py` interprets the schema's
  keywords itself and refuses any it cannot honour. A host may now see schema errors that were
  always there. A manifest on a former field name is validated under the current name.
- **`validate.stages`** declares the real-stack proof: `setup`, `migrate`, `build`, `test`,
  `health`, `ingest`, `anchor` and `teardown` stages, each an argv, fail-fast. Teardown always
  runs. An `anchor` compares its command's output (`equals`, `matches`, `atLeast`). A list with
  no anchor, or whose last working stage is not an anchor, is refused by plain `validate` before
  anything runs. Run it with `stack-kit validate --stages`.
- **Migrations are structure-only.** Each driver declares its migrations (`drivers/registry.json`
  `migrations`: globs, excluded generated files, data-statement patterns) for `java-boot`
  (Flyway SQL) and `dotnet-aspnet` (EF Core). `validate` names any migration that carries data.
  A module points elsewhere with `modules.<id>.migrations.paths`, and allows a reference-data
  file with `migrations.allowData: [{path, reason}]`.
- `cli/stack-kit.ps1` passed no arguments to `migrate`, `init` and `stack`: their handlers are
  invoked without arguments, so `@Args` was always empty, and `stack-kit migrate --apply` from
  PowerShell silently ran as a dry run. They pass the CLI's operands now, as does `validate`.

### The handwriting (ADR-001 K3)

- `.gitattributes` pins LF for every text file (CRLF only for `.cmd`/`.bat`). Under
  `core.autocrlf` a Windows checkout handed bash scripts CRLF, which fails on a Linux server.
- The host's tree is a declared layout held by `validate` as a floor (`lib/layout_floor.py`).
  Every place the manifest declares must exist (vendored kit, secrets root, module directories,
  declared compose catalog, CI scripts, infra compose directory once infra services are
  declared, nginx template). `layout.entries` adds rows in the agent kit's row shape;
  `layout.closed` names directories where an undeclared child is a failure. A `pending` row is
  printed, not failed.
- Tests are split into `tests/unit/` (in-process) and `tests/acceptance/` (shells and CLIs), and
  read the kit root and the fixture from `conftest.py` instead of computing their own.

### One resolver (ADR-001 K2)

Project discovery, manifest fields and their defaults, modules, roles, types, aliases, driver
lookup, env files and values, slugs, server and deploy paths, and the infra compose and tunnel
rules are answered by `lib/resolution.py` alone, through `lib/resolve_cli.py`. `lib/project.sh`,
`lib/env.sh`, `lib/drivers.sh`, `lib/project.ps1`, `lib/env.ps1`, `lib/drivers.ps1` and
`lib/modules.ps1` keep every public function and now only look answers up (1,485 lines of shell
resolution became 844, comments included). A shell resolves what the manifest says once and
keeps it; what the environment says is asked each time. Env files are read by one parser
(`lib/envfile.py`) instead of three.

The copies had drifted. Every runtime now gives the answer below; where a runtime used to
differ, it is named:

- **Project root:** a declared `STACK_KIT_PROJECT_ROOT` is authoritative; otherwise the working
  directory and its parents. PowerShell searched upward from the kit's own folder instead of the
  working directory; Python checked the working directory before the declared root.
- **Field defaults:** a missing field takes the declared convention default
  (`manifest_defaults.CONVENTION_DEFAULTS`), never an arbitrary template field. PowerShell applied
  no defaults at all (its `[string]$Default = $null` is `""`, so its template fallback never ran):
  a manifest without `secrets` gave PowerShell the project root as the secrets root.
- **A module's role:** declared, else the first role its driver declares. Bash spelled two
  drivers' roles inline.
- **An env value of a secrets folder:** the last non-empty value across `.env.dev`, `.env.prod`,
  `deploy.env`, `.env.deploy`, which is how compose applies them. Bash returned the first.
- **A shared deploy value:** the process environment first, then `deploy.env`. Bash read the file
  first.
- **The server base:** `DEPLOY_SERVER_BASE`, else `/home/<user>` from `DEPLOY_SERVER`, each looked
  up in `deploy.env` and then in every module folder. Bash looked only in `deploy.env`.
- **A remote deploy base with no `DEPLOY_PATH` and no server to derive one from:** refused.
  Bash produced `/<slug>/<folder>`; Python defaulted to `/home/deploy`.
- **The infra deploy path with neither:** refused. It used to be one consumer's server path.
- **CLI aliases, the UI compose service name, a driver's layout simulator:** the resolver's.
  PowerShell re-derived the aliases, took the UI service from a module literally named
  `frontend`, and mapped two driver names to simulators inline.

### Identity — the kit names no consumer (ADR-001 K1)

The package, command, manifest and environment are renamed; every former name is still READ for
the whole 1.x line, each read printing one line naming its replacement, once per process tree
(`STACK_KIT_NO_DEPRECATION_NOTICE=1` silences it). 2.0.0 stops reading them. All of it is declared
once, in `lib/identity.json`.

| Former | Current |
|---|---|
| package `geostat-kit`, vendored at `kits/geostat-kit` | `stack-kit`, `kits/stack-kit` |
| command `cli/geostat.ps1`, `cli/geostat.sh` | `cli/stack-kit.ps1`, `cli/stack-kit.sh` (the former paths remain as shims) |
| manifest `geostat.ops.json` | `stack-kit.json` |
| variables `GEOSTAT_*` | `STACK_KIT_*` — the same suffix, so `GEOSTAT_KIT_ROOT` is `STACK_KIT_KIT_ROOT` |
| manifest field `vscode.geostatScript` | `vscode.cliScript` |
| server marker `.geostat-deploy.json` | `.stack-kit-deploy.json` (a former marker is still found) |
| scaffolded launchers `tools/geostat.*`, `ops/cli/geostat.*` | `tools/stack-kit.*`, `ops/cli/stack-kit.*` |

**To move a host:** `stack-kit migrate` (dry run), then `stack-kit migrate --apply`. It renames the
manifest file and the renamed fields, refuses a host holding both manifest names, and PRINTS — never
rewrites — every line of the host's own files that still spells a former name.

Behaviour changes a host may notice:

- The variables are adopted inward only: a former variable set by an operator or CI is read; the kit
  no longer exports former names to the processes it starts.
- The java-boot pre-flight check names no integration of its own. A module declares what it checks in
  `modules.<id>.check.requiredEnv` / `optionalEnv` (the search, speech and model keys it used to
  name for one consumer's `chat-api` are gone).
- The primary API module is `stack.primaryApiModule` when declared, else the first module whose role is
  `api`; the module ids `backend` and `chat-api` are no longer privileged.
- Generated Spring defaults use the user `app` and password `app-dev-change-me` (were the consumer's
  name); the default database is `app`. Each remains overridable by its environment variable.
- `compose/build.py` and `compose/sync_ops_modules.py` resolve the project through the one discovery in
  `lib/project_context.py` instead of their own copies; `cli/stack-kit.sh` sources `lib/project.sh`.

### Agnosticism

- Reference test fixture is `tests/fixtures/golden-consumer/` with role-named,
  project-neutral module ids (`api`, `search`, `worker`, `web`, `svc`). No
  consumer brand appears in a fixture id, path or assertion.
- **Driver facts live in `drivers/registry.json`, not in generators.** Each driver
  declares `tasks` (e.g. `devWatch` argv) and `vscode.launch` (its launch shape).
  `lib/vscode_gen.py` no longer contains a `node-vite`/`java-boot` ladder or a
  privileged alias allow-list, so `node-api` — which previously got no VS Code
  tasks at all — now gets them by declaration. A new driver needs no generator edit.
- Role inference when a module omits `role` now reads the driver's declared
  `roles[0]` (`lib/modules.py`, `lib/drivers.ps1`) instead of a type→role ladder.
- `toolkit/deploy/pnpm-build.sh`: build ordering is declared as
  `modules.<id>.node.prebuildScripts` (default `[]`); no consumer script name lives
  in the kit. A declared script the workspace lacks now fails instead of silently
  skipping.
- `toolkit/dev/Invoke-DevUp.ps1`: help text renders from the resolved manifest's
  `cli.aliases` (placeholders when absent); remote watch uses the driver's declared
  `tasks.devWatch`; boot order is `dev.bootOrder` (default `api, worker, ui`).
- Spring actuator exposure is `modules.<id>.spring.managementEndpoints`, default the
  narrow `health,info`. A wider management surface is declared, never a kit default.
- `docs/DEV-MODES.md`, `docs/LOCAL-DEBUG.md`, `drivers/node-api/README.md` and the
  `node-vite` dev help use `<alias>` / `<moduleId>` placeholders only. The `node-api`
  README no longer claims the driver is unregistered.
- `lib/compose_identity.py`: the primary UI service name derives from
  role + primary-module resolution, not from a module literally named
  `frontend`; the privileged `backend` branch is removed.

### Capability

- `dotnet-aspnet` driver (registry entry, `_init.ps1`, `ps1/{run,hybrid,check,deploy}.ps1`):
  `run` through the shared hybrid runner, `check` pre-flight, `deploy artifact` =
  `dotnet publish` + declared `modules.<id>.dotnet.publishExpect` + `release.json`;
  `deploy remote` is an explicit refusal (delivery is not declared yet).
- **Hybrid run is declarative for new drivers.** `toolkit/hybrid/Invoke-HybridRun.ps1`'s
  `default` branch dot-sources the launch script a driver declares as
  `"hybrid": {"script": ...}` (`Get-DriverHybridScript` in `lib/drivers.ps1`) instead of
  refusing; the three existing rungs are unchanged.
- `lib/vscode_gen.py`: launch kind `dotnet` (C# Dev Kit `"type": "dotnet"`, project from
  `modules.<id>.dotnet.project` or the module's single `*.csproj`; ambiguity renders nothing).
- **`cli/geostat.ps1` no longer exits 0 when a PowerShell driver command fails** without
  setting `$LASTEXITCODE` (statement-terminating errors such as parameter binding). The
  PowerShell branch runs inside `try/catch` and exits 1 with the message. Proven by
  `TestCliReportsDriverFailure` (fails on the previous CLI).
- `validate` warns about `compose.catalog` only when the manifest declares `compose`.
- Manifest: `compose` is **optional** (schema `required` and `_validate_required`); a present
  `compose` without `catalog` is still refused. New module block `dotnet` (`project`,
  `launchProfile`, `configuration`, `publishExpect`).

- `node-api` driver (registry entry, `sh/`, `ps1/`, `_init.sh`).
- `geostat dev up` (`toolkit/dev/`), `resource_limits` / `extraServices`
  compose seams, `manifest.migration.legacyDirs`.

## 1.0.0 — 2026-05-21

### Adoption

- [docs/ADOPTION.md](docs/ADOPTION.md) — გავრცელება, რა გავაკეთეთ, GitHub topics, submodule pin

### Documentation & tooling

- [docs/DEV-MODES.md](docs/DEV-MODES.md) + `scripts/dev-modes-verify.*` — dev mode smoke
- [docs/LOCAL-DEBUG.md](docs/LOCAL-DEBUG.md) + `lib/vscode_gen.py` — Run and Debug from manifest

### Package boundary (manifest-driven)

- N-module model: `modules.*.role`, `path`, `secretsModule`, dynamic CLI/layout
- Single default source: `scaffold/geostat.ops.json` via `lib/manifest_defaults.py`
- Runtime hardcode ban: `test_toolkit_hardcodes.py`
- Project CI: consumer `ops/ci/integration-stack.sh` resolves api module from manifest

### Credentials

- Per-module `modules.<id>.credentials[]` (multi-file / multi envVar)
- Global fallback: `features.gcpCredentials` + `adapters.gcp.*`
- `dev-remote`, `ci_prepare`, `upload` use resolved credential profiles

### Tooling

- `geostat validate` — schema + project checks
- `geostat migrate` — v2 role/secretsModule hints (`--apply`)
- Golden consumer fixture: `tests/fixtures/golden-consumer/`

### Docs

- `docs/MATURITY.md`, `docs/STARTER.md`, `docs/PACKAGE-ARCHITECTURE.md` (CI/credentials)
