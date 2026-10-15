---
kind: guide
authority: canonical
owns: install
---

# Install stack-kit

Getting the kit into a host: prerequisites, vendoring, launchers, first run. Taking the host onto
the kit (manifest, config, CI, migration) is [ADOPT.md](ADOPT.md); every verb and field is
[REFERENCE.md](REFERENCE.md).

The kit holds ops machinery only. Application code, real env values and secrets stay in the host.

## Prerequisites

| Tool | Needed for | Notes |
|---|---|---|
| Python 3.10+ | every command | The one resolver is Python (`lib/resolution.py`); the bash and PowerShell libraries ask it through `lib/resolve_cli.py`. Also `validate`, `migrate`, `compose-gen`, `vscode-gen`, `config-gen`, `nginx-gen`. PowerShell looks for `py -3`, then `python3`, then `python` (`lib/stack-kit-python.ps1`). |
| PowerShell 5.1+ | the Windows CLI, `node-vite` and `dotnet-aspnet` drivers, `init`, `dev`, `hybrid`, `layout`, `config-gen`, `infra <mode>`, `help`, module commands | `cli/stack-kit.sh` hands every verb it does not implement to `powershell` (see [Launchers](#launchers)). |
| Bash | `java-boot` and `node-api` drivers, `stack-deploy`, `infra` (no arguments = prereqs), `layout migrate`, `layout cleanup` | On Windows: Git for Windows. The CLI uses `%ProgramFiles%\Git\bin\bash.exe`, else `%ProgramFiles%\Git\usr\bin\bash.exe`; missing → `Git Bash required`. |
| Docker + compose | `stack`, `<module> compose`, `infra`, CI integration, every remote deploy (on the server) | Optional for manifest-only work. Bash scripts use `docker compose`, else `docker-compose`. |
| SSH + rsync | remote deploy, remote dev, `infra remote`, `infra tunnel` | Keys under `ops/config/ssh/` ([ADOPT.md#configuration](ADOPT.md#configuration)). |
| Node + npm / Java + Gradle / .NET SDK | building the host's own apps | In the host's `apps/*`, never in the kit. |

## Vendor the kit

Git submodule (recommended), from the host root:

```bash
git submodule add <stack-kit-repo-url> kits/stack-kit
cd kits/stack-kit && git checkout <tag-or-sha> && cd ../..
git add kits/stack-kit .gitmodules
git commit -m "chore: add stack-kit"
```

Copy instead of a submodule:

```bash
git clone <stack-kit-repo-url> /tmp/stack-kit
cp -r /tmp/stack-kit <host>/kits/stack-kit
```

- Pin a release tag (`git tag v$(cat VERSION)` is how the kit tags) or a commit SHA. The kit's version is in `VERSION`.
- Vendor path: `kits/stack-kit` (`packages/stack-kit` is also recognised, `lib/identity.json` `vendorDirs`). The manifest's `package` field names it.
- Never put `deploy.env`, keys or any production value inside the kit. Do not edit the kit for app logic.

## Launchers

`stack-kit init` scaffolds the host's launchers (from `scaffold/`):

| Host file | Delegates to | Use |
|---|---|---|
| `tools/stack-kit.ps1` | `ops/cli/stack-kit.ps1` | PowerShell entry (`.\tools\stack-kit.ps1 <verb>`); `vscode.cliScript` default |
| `tools/stack-kit.cmd` | `tools/stack-kit.ps1` via `powershell.exe -File` | cmd.exe (a bare `.ps1` from cmd opens an editor) |
| `ops/cli/stack-kit.ps1` | `kits/stack-kit/cli/stack-kit.ps1` | canonical project entry |
| `ops/cli/stack-kit.sh` | `kits/stack-kit/cli/stack-kit.sh` | bash entry |

A hand-written PowerShell launcher must forward the kit CLI's two parameters, `Command` and `CliRest`:

```powershell
param(
    [Parameter(Position = 0)] [string]$Command = "help",
    [Parameter(ValueFromRemainingArguments = $true)] [string[]]$CliRest = @()
)
$Root = Split-Path $PSScriptRoot -Parent
& (Join-Path $Root "kits\stack-kit\cli\stack-kit.ps1") -Command $Command -CliRest $CliRest
exit $LASTEXITCODE
```

An optional `tools/stack-kit.sh` (not scaffolded):

```bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export STACK_KIT_PROJECT_ROOT="$ROOT"
exec bash "$ROOT/kits/stack-kit/cli/stack-kit.sh" "$@"
```

What `cli/stack-kit.sh` does itself, and what it hands on:

| Verbs | Runs |
|---|---|
| `init` | `toolkit/init/init.sh` → the PowerShell init when `powershell.exe` exists, else a bash fallback (scaffold + seed + compose-gen; no nginx-gen, no `.gitignore` merge) |
| `validate`, `migrate`, `vscode-gen`, `compose-gen`, `nginx-gen` | `python3` directly |
| `stack`, `stack-deploy` | bash (`toolkit/stack/compose.sh`, `toolkit/deploy/stack-remote.sh`) |
| `infra` | no arguments: `toolkit/infra/ensure-prereqs.sh`; with arguments: `pwsh`, else `powershell.exe` |
| anything else (`help`, `mod`, aliases, `dev`, `hybrid`, `layout`, `config-gen`) | `powershell -File <host>/tools/stack-kit.ps1`, else the kit's `cli/stack-kit.ps1` |

Linux/macOS: call `kits/stack-kit/cli/stack-kit.sh` from the host root, or set `STACK_KIT_PROJECT_ROOT`.

## First run

From the host root. Before `init` there is no `tools/` launcher: call the kit's CLI directly
(`.\kits\stack-kit\cli\stack-kit.ps1 init`; bash: `bash kits/stack-kit/toolkit/init/init.sh [<root>]` — `cli/stack-kit.sh`
resolves the root before dispatching and stops without a manifest) or hand-write the launcher above. `init` finds the root
by walking up for `stack-kit.json`, else two levels above the kit, else the working directory.

```powershell
.\tools\stack-kit.ps1 init          # scaffold + seed env + catalog + compose-gen + vscode-gen + checklist
.\tools\stack-kit.ps1 validate      # schema + project checks
.\tools\stack-kit.ps1 compose-gen   # regenerate docker-compose*.yml
.\tools\stack-kit.ps1 vscode-gen    # .vscode launch/tasks (missing files only)
.\tools\stack-kit.ps1 help          # verbs, driver types, project modules, aliases
```

Without a manifest every verb except `init` stops with `stack-kit.json not found (run: stack-kit init)`.
What `init` writes and its flags: [ADOPT.md#bootstrap-with-init](ADOPT.md#bootstrap-with-init).

Daily commands once adopted:

```powershell
.\tools\stack-kit.ps1 mod backend check
.\tools\stack-kit.ps1 mod frontend compose up -d
.\tools\stack-kit.ps1 stack up -d --build
```

Aliases (`fe`, `be`, …) come from the host's `cli.aliases` ([REFERENCE.md#commands](REFERENCE.md#commands)).

## Verify the kit

Package tests need no SSH, rsync or Docker; they run against `tests/fixtures/golden-consumer/`
([tests/README.md](../tests/README.md)).

```powershell
cd kits\stack-kit; $env:PYTHONPATH='.'; python -m pytest tests -q
```

```bash
cd kits/stack-kit && PYTHONPATH=. pytest tests -q
bash kits/stack-kit/tests/run-kit-tests.sh       # installs pytest if missing; -v --tb=short
```

Dev-mode smoke: [GOLDEN-PATHS.md#smoke](GOLDEN-PATHS.md#smoke). Release gate: [ADOPT.md#maturity](ADOPT.md#maturity).
