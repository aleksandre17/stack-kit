# geostat-kit — გავრცელება (v1.0.0)

## რა არის

Manifest-driven **ops პაკეტი** — `geostat.ops.json`, drivers (`java-boot`, `node-vite`), compose-gen, deploy, CI, `vscode-gen`. არა app კოდი.

## რა შედის 1.0.0

- 4-plane: `apps/` · `kits/` · `ops/` · `docs/`
- N-module (`role`: ui, api, worker)
- `geostat validate`, `migrate`, multi-credential
- DEV-MODES: local / Docker / remote
- 180+ pytest, `dev-modes-verify`

რეფერენსი: `tests/fixtures/golden-consumer/` (კიტის საკუთარი სინთეზური consumer).

## სწრაფი ჩართვა

Install: **[INSTALL.md](INSTALL.md)** (submodule, shim, `geostat init`).

```bash
git submodule add https://github.com/YOUR_USER/geostat-kit.git kits/geostat-kit
cd kits/geostat-kit && git checkout v1.0.0
```

```powershell
.\tools\geostat.ps1 init
.\tools\geostat.ps1 validate
```

სრული: [ADOPTION-LINE.md](ADOPTION-LINE.md) · [STARTER.md](STARTER.md)

## ვერსია

ჩართვისას დააფიქსირე tag **`v1.0.0`** (იხ. [CHANGELOG.md](../CHANGELOG.md)).
