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
| Python 3.10+ | every command | The CLI is Python (`cli/stack_kit.py` -> `lib/cli/`); the launchers only find it (`py -3`, `python3`, `python`). |
| PowerShell 7+ (`pwsh`) | PowerShell driver scripts (`dotnet-aspnet`, `dotnet-library`, the package-script runner, the host run), `init`, local `dev up --mode`, `infra local` | Any OS; on Windows, Windows PowerShell 5.1 also runs them (every non-ASCII script carries a BOM). |
| Bash | a driver command written in bash, `init` on a machine without PowerShell | On Windows: Git for Windows (`%ProgramFiles%\Git\bin\bash.exe`). |
| OpenSSH (ssh, tar) | every remote verb: `deploy`, `release`, `ops`, `dev`, `targets --init/--verify`, `layout migrate`, `infra remote`, tunnels | rsync is used for a remote-dev sync when both ends have it, else the kit's own index + tar stream; a key under `ops/config/ssh/` or the agent ([ADOPT.md#configuration](ADOPT.md#configuration)). |
| Docker + compose | the local stack (`stack`, `dev up --mode docker`, `infra local`) and, on a target, every release | The compose invocation is declared (`config/catalogs/targetRuntimes.json`, a target's `compose`): a host with only the standalone binary declares `["docker-compose"]`. |
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

Both kit launchers (`cli/stack-kit.ps1`, `cli/stack-kit.sh`) do one thing: find Python and run
`cli/stack_kit.py` with the command line unchanged, so every verb is the same CLI from PowerShell,
bash and CI. A hand-written PowerShell launcher forwards the kit CLI's two parameters, `Command`
and `CliRest`, from a SIMPLE param block (an advanced one binds an operand such as `-d` as `-Debug`):

```powershell
param([string]$Command = "help", [string[]]$CliRest = @())
$CliRest = @($CliRest) + @($args)
$Root = Split-Path $PSScriptRoot -Parent
& (Join-Path $Root "kits\stack-kit\cli\stack-kit.ps1") -Command $Command -CliRest $CliRest
exit $LASTEXITCODE
```

and a POSIX one:

```bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export STACK_KIT_PROJECT_ROOT="$ROOT"
exec bash "$ROOT/kits/stack-kit/cli/stack-kit.sh" "$@"
```

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
.\tools\stack-kit.ps1 build
.\tools\stack-kit.ps1 dev up api --mode hybrid
.\tools\stack-kit.ps1 deploy api --env dev --plan
```

Every verb, its options and exit codes: [OPERATIONS.md](OPERATIONS.md).

## Verify the kit

Package tests need no SSH, rsync or Docker; they run against `tests/fixtures/gc/`
([tests/README.md](../tests/README.md)).

```powershell
cd kits\stack-kit; $env:PYTHONPATH='.'; python -m pytest tests -q
```

```bash
cd kits/stack-kit && PYTHONPATH=. pytest tests -q
bash kits/stack-kit/tests/run-kit-tests.sh       # installs pytest if missing; -v --tb=short
```

What the suite proves, and what it cannot: [GOLDEN-PATHS.md#smoke](GOLDEN-PATHS.md#smoke).
