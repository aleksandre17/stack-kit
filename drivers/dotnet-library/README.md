# dotnet-library driver

A .NET class library declared as a module of its own: built and tested on its own, never run,
packaged or released. Role: `other` (a library has no tier of its own; it is never deployed).
Runtime: PowerShell (Windows PowerShell 5.1+ or pwsh).

It is the standalone form of what java-boot's `opsModules.shared` row is inside a Gradle build: the
code a service references, proven by its own tests rather than only through the service's.

## Commands

The same scripts as `dotnet-aspnet` (`drivers/_shared/dotnet/`), over the same `modules.<id>.dotnet`
fields (`project`, `solution`, `test`, `configuration`):

| Command | What it does |
|---|---|
| `build` | `dotnet build` of the module's solution (`dotnet.solution`) or project, in `dotnet.configuration` (default Release) |
| `test` | `dotnet test` of `dotnet.test` (a test project or solution, module-relative), counted from its TRX report: `[<id> test] N test(s): ...`; a run that discovers no test fails; `"test": ""` declares none |
| `lint` | `dotnet format --verify-no-changes` |
| `audit` | `dotnet list package --vulnerable --include-transitive`; a high or critical advisory fails |
| `check` | dotnet SDK, module path, resolvable project file (no secrets or `publishExpect`: nothing runs or is published) |

## What it does not declare

No `hybrid` (so no `run`), no `package`, no `container`, no `dev`, no delivery rung (`delivery: {}`),
no `vscode`, no `compose`: a library has no process, archive, image, health probe, local or remote dev, compose
service or deploy. Each verb that needs one names the module and the missing declaration
(`mod <id> run`: the driver has no command `run`; `package <id>`, `deploy <id>`: the driver declares
no package step). `build`, `test`, `lint` and `audit` across the modules include it. Nor does it
declare `detect`: a class library is declared by its host, never drafted from a tree (every test
project and helper assembly is one).

## Manifest

```json
"modules": {
  "core": {
    "type": "dotnet-library",
    "role": "other",
    "path": "src/Core",
    "secretsModule": "core",
    "dotnet": {
      "project": "Core.csproj",
      "test": "../../tests/Core.Tests/Core.Tests.csproj"
    },
    "toolchain": { "version": "8.0.x" }
  }
}
```

All `dotnet.*` keys are optional. Without `project`, the module path must contain exactly one
`*.csproj`. A service that references the library (`<ProjectReference>`) still builds it as part of
its own build; the library's module adds its own build and its own tests.
