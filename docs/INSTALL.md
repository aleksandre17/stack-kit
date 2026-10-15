# Install stack-kit (for other projects)

Use this after you **cloned or submodule-added** this package. Your app code stays in **your** repo; only ops live here.

## 1. Get the package

### A. Git submodule (recommended)

```bash
cd your-project
git submodule add https://github.com/YOUR_USER/stack-kit.git kits/stack-kit
cd kits/stack-kit
git checkout v1.0.0
cd ../..
git add kits/stack-kit .gitmodules
git commit -m "chore: add stack-kit v1.0.0"
```

### B. Copy

```bash
git clone https://github.com/YOUR_USER/stack-kit.git /tmp/stack-kit
cp -r /tmp/stack-kit your-project/kits/stack-kit
```

Pin version: use tag `v1.0.0` or commit SHA.

## 2. Project layout (v2)

```text
your-project/
├── stack-kit.json      ← you own this
├── apps/                 ← your frontend, backend, …
├── ops/config/           ← secrets (gitignored)
├── ops/compose/
├── tools/stack-kit.ps1     ← thin shim (below)
└── kits/stack-kit/     ← this package (do not edit for app logic)
```

## 3. CLI shim (`tools/stack-kit.ps1`)

Create in **your project root**:

```powershell
# tools/stack-kit.ps1
$Kit = Join-Path $PSScriptRoot "..\kits\stack-kit"
& (Join-Path $Kit "cli\stack-kit.ps1") @args
```

Linux / macOS can call `kits/stack-kit/cli/stack-kit.sh` from project root with `STACK_KIT_PROJECT_ROOT` set.

## 4. Manifest

```bash
cp kits/stack-kit/scaffold/stack-kit.json ./stack-kit.json
```

Edit:

- `modules.<id>.path` — e.g. `apps/frontend`, `apps/backend`
- `modules.<id>.role` — `ui`, `api`, `worker`
- `modules.<id>.secretsModule` — folder under `ops/config/`
- `package` — must be `"kits/stack-kit"`

## 5. Bootstrap

```powershell
.\tools\stack-kit.ps1 init
.\tools\stack-kit.ps1 validate
.\tools\stack-kit.ps1 compose-gen
.\tools\stack-kit.ps1 vscode-gen
```

## 6. Daily commands

```powershell
.\tools\stack-kit.ps1 help
.\tools\stack-kit.ps1 mod backend check
.\tools\stack-kit.ps1 mod frontend compose up -d
.\tools\stack-kit.ps1 stack up -d --build
```

Aliases (`fe`, `be`) come from `cli.aliases` in your manifest.

## 7. Requirements

- Windows: PowerShell 5.1+, Git Bash for some backend deploy scripts
- Python 3.10+ for `validate`, `compose-gen`
- Docker (optional) for compose / stack
- Java / Node in **your** `apps/*` (not in the kit repo)

## Next

- [ADOPTION-LINE.md](ADOPTION-LINE.md) — full pipeline
- [DEV-MODES.md](DEV-MODES.md) — local vs Docker vs remote
- [STARTER.md](STARTER.md) — short checklist
