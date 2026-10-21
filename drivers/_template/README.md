# New driver template

Copy this folder to `drivers/<your-type>/` (e.g. `go-fiber`), or declare the driver in the host's
own registry (`drivers.registry`) beside its folder -- the kit untouched.

## Layout

```
<your-type>/
  README.md
  ps1/ or sh/              # the lifecycle steps the toolchain needs (build, test, lint, package)
  container/Dockerfile     # the release recipe, rendered per module ({toolchain.version|...}, {artifact}, {port}, {entry})
```

## Registry entry

```json
"<your-type>": {
  "label": "Human-readable stack name",
  "roles": ["api"],
  "commands": { "build": "sh/build.sh", "test": "sh/test.sh" },
  "package": { "command": "build", "artifacts": ["out/**"] },
  "container": { "template": "container/Dockerfile", "port": 8080 },
  "dev": { "image": "<dev image>", "command": ["<dev server>"], "port": 8080, "caches": {}, "excludes": ["out/"] },
  "delivery": { "release": { "via": "release" }, "remote-dev": { "via": "dev" } }
}
```

A command runs by its script's runtime (`config/runtimes.json`). The kit's verbs -- `deploy`,
`dev`, `ops`, `release` -- run every driver alike from these declarations; a driver ships no
deploy, dev or manage script.

## Manifest

```json
"modules": { "my-service": { "type": "<your-type>", "role": "api", "path": "my-service", "secretsModule": "my-service" } }
```

Then `stack-kit validate` and `stack-kit deploy my-service --plan`. Reference implementations: `dotnet-aspnet/`, `java-boot/`; a module that is never run: `dotnet-library/`.
