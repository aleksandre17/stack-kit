# dotnet-aspnet driver

ASP.NET Core service (any .NET SDK project with `dotnet run` / `dotnet publish`). Role: `api`.
Runtime: PowerShell (Windows PowerShell 5.1+ or pwsh).

## Commands

| Command | What it does |
|---|---|
| `run` | Shared hybrid runner: imports `<secrets>/<secretsModule>/.env.dev` into the process -- a development run never reads production configuration (ADR-001 amendment 8) -- then `dotnet run --project <project> [--launch-profile <p>]` (declared as `hybrid.script` in `drivers/registry.json`) |
| `check` | Pre-flight: dotnet SDK, module path, resolvable project file, secrets dir / `.env.dev` (warnings) |
| `package` | `dotnet publish` into the kit's staging directory (`-Output {out}`), verifies the declared `publishExpect` paths, writes `release.json`; `stack-kit package <module>` then archives it with its provenance |
| `deploy` (`deliver release`) | the kit's release: `container/Dockerfile` runs the published assembly (`{dotnet.project}` stem) on the ASP.NET runtime of the module's `toolchain.version`, internal port 8080 |
| `dev up` (`deliver remote-dev`) | `dotnet watch run` in the SDK image, the source synced into the workspace, NuGet's cache a named volume; a project file change restarts it |

`build`, `test`, `lint`, `audit` and `check` are the .NET family's shared scripts
(`drivers/_shared/dotnet/`), the same a `dotnet-library` module runs.

ASP.NET Core reads configuration from environment variables with `__` as the section separator,
so `ConnectionStrings__DefaultConnection=...` in `.env.dev` reaches the app without being written
into a tracked `appsettings.*.json`.

A **generated** secret (a catalogue key with `generate`) never enters an env file. On the server it is
a file in a read-only directory, and the container is told the directory as `KeyPerFile__Directory`
(this driver's `generatedSecrets`). ASP.NET Core reads no `<NAME>_FILE`, so the app loads the
directory itself -- once, at startup:

```csharp
var keyPerFile = builder.Configuration["KeyPerFile:Directory"];
if (!string.IsNullOrEmpty(keyPerFile))
    builder.Configuration.AddKeyPerFile(keyPerFile, optional: false);  // Jwt__Key -> Jwt:Key
```

`validate` refuses a module given a generated secret when no `AddKeyPerFile(` appears in its sources;
a release is refused when its own assembly (`<project>.dll`) does not name `AddKeyPerFile`, and a
rollback to a release on the server that does not (one made before it read the key) is refused. The
check proves the code names the reader; a test of the host proves it is called (a host built with
`WebApplicationFactory`, `KeyPerFile__Directory` set and no other key, starts).
The image runs as `app` (uid 1654), so before the service starts each generated file is handed to
that uid (mode 0400) by the service's own image -- the deploy user keeps the directory (0755: key-per-file
lists it) and never reads a value back.

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

- Windows/IIS delivery — the `iis` target runtime is pending;
- VS Code launch (`vscode.launch`) — no `coreclr` builder in `lib/vscode_gen.py` yet, so the
  driver declares none rather than a kind nothing renders;
- compose templates — this driver has no `compose-catalog.json` entry.
