# dotnet-aspnet driver

ASP.NET Core service (any .NET SDK project with `dotnet run` / `dotnet publish`). Role: `api`.
Runtime: PowerShell (Windows PowerShell 5.1+ or pwsh).

## Commands

| Command | What it does |
|---|---|
| `run` | Shared hybrid runner: imports `<secrets>/<secretsModule>/.env.prod` then `.env.dev` into the process, then `dotnet run --project <project> [--launch-profile <p>]` (declared as `hybrid.script` in `drivers/registry.json`) |
| `check` | Pre-flight: dotnet SDK, module path, resolvable project file, secrets dir / `.env.dev` (warnings) |
| `deploy artifact` | `dotnet publish` into `<project>/build/publish/<moduleId>/<short-sha>/`, verifies declared `publishExpect` paths, writes `release.json`. Refuses a dirty tree unless `-AllowDirty` |
| `deploy remote` | **Refused** — delivery to a host is not declared by this driver yet |

ASP.NET Core reads configuration from environment variables with `__` as the section separator,
so `ConnectionStrings__DefaultConnection=...` in `.env.dev` reaches the app without being written
into a tracked `appsettings.*.json`.

## Manifest

```json
"modules": {
  "api": {
    "type": "dotnet-aspnet",
    "role": "api",
    "path": "src/Api",
    "secretsModule": "api",
    "dotnet": {
      "project": "Api.csproj",
      "launchProfile": "http",
      "configuration": "Release",
      "publishExpect": ["Api.dll", "web.config", "wwwroot/index.html"]
    }
  }
}
```

All `dotnet.*` keys are optional. Without `project`, the module path must contain exactly one
`*.csproj`.

## Not declared (yet)

- remote delivery (IIS, VM, container) — `deploy remote` refuses;
- VS Code launch (`vscode.launch`) — no `coreclr` builder in `lib/vscode_gen.py` yet, so the
  driver declares none rather than a kind nothing renders;
- compose templates — this driver has no `compose-catalog.json` entry.
