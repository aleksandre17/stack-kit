# New driver template

Copy this folder to `drivers/<your-type>/` (e.g. `node-api`, `go-fiber`).

## Layout

```
<your-type>/
  README.md
  _init.sh | _init.ps1     # STACK_KIT_MODULE_ID, ops.config, toolkit _common
  sh/  or  ps1/            # deploy, manage, compose, check, …
```

## Registry entry

Add to `drivers/registry.json`:

```json
"<your-type>": {
  "label": "Human-readable stack name",
  "roles": ["api"],
  "runtime": "bash",
  "commands": {
    "deploy": "sh/deploy.sh",
    "manage": "sh/manage.sh"
  }
}
```

`runtime`: `bash` (Git Bash on Windows) or `powershell`.

## Manifest

```json
"modules": {
  "my-service": {
    "type": "<your-type>",
    "path": "my-service",
    "secretsModule": "my-service"
  }
}
```

Optional CLI shortcut:

```json
"cli": { "aliases": { "api": "my-service" } }
```

## Reuse toolkit

Deploy/manage logic should call `kits/stack-kit/toolkit/` (SSH, env, compose-cli) — do not fork copy into the driver unless stack-specific (Gradle vs npm).

Reference implementations: `java-boot/`, `node-vite/`.
