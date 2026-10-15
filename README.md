# stack-kit

**v1.0.0** — Manifest-driven **operations package** for SaaS monorepos.

Compose generation, SSH deploy, env contract, multi-module CLI — **no** application code, **no** production secrets in this repo.

| | |
|---|---|
| **Install** | [docs/INSTALL.md](docs/INSTALL.md) |
| **What it is** | [docs/ADOPTION.md](docs/ADOPTION.md) |
| **Full setup** | [docs/ADOPTION-LINE.md](docs/ADOPTION-LINE.md) |

## Install (others download your package)

```bash
# Recommended: git submodule
git submodule add https://github.com/YOUR_USER/stack-kit.git kits/stack-kit
cd kits/stack-kit && git checkout v1.0.0
```

Or clone / copy this repo into your project as `kits/stack-kit/`.

In your **project root** (not inside the kit):

```json
// stack-kit.json
{
  "version": 2,
  "package": "kits/stack-kit",
  "secrets": "ops/config",
  ...
}
```

```powershell
# From your project root — add tools/stack-kit.ps1 shim (see docs/INSTALL.md)
.\tools\stack-kit.ps1 init
.\tools\stack-kit.ps1 validate
```

Details: **[docs/INSTALL.md](docs/INSTALL.md)**

## Features (1.0.0)

- `stack-kit.json` — modules, roles (`ui`, `api`, `worker`), paths, CI, adapters
- Drivers: `java-boot` (Spring/Gradle), `node-vite` (Vite)
- `stack-kit validate` · `migrate` · `vscode-gen` · `stack` · remote deploy / `dev watch`
- N-module CLI: `stack-kit mod <moduleId> …`
- See [CHANGELOG.md](CHANGELOG.md)

## Layout

```text
stack-kit/          ← this repository (standalone package)
├── lib/              # manifest resolution API
├── drivers/          # stack-type plugins
├── toolkit/          # deploy, stack, init
├── compose/          # catalog → docker-compose generator
├── cli/              # stack-kit entry
├── scaffold/         # templates for new projects
├── ci/               # generic CI helpers
├── scripts/          # verify / smoke
├── tests/
└── docs/
```

## Tests (package maintainers)

```powershell
cd stack-kit
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests -q
```

```powershell
.\scripts\dev-modes-verify.ps1 -SkipDocker
```

## Version

[VERSION](VERSION) — current: **1.0.0**  
Release tag: **`v1.0.0`**

## License

Add your license file when you distribute the package (MIT, Apache-2.0, or proprietary). This repo may ship without `LICENSE` until you add one.
