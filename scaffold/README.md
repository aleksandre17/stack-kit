# Project scaffold (stack-kit)

ფაილები და ფოლდერები, რომლებიც **არ არის** პაკეტის `lib/`, `toolkit/`, `drivers/` ნაწილი, მაგრამ **აუცილებელია** repo root-ზე, რომ `stack-kit` სრულად იმუშაოს.

## სწრაფი გამოყენება (რეკომენდებული)

```powershell
.\tools\stack-kit.ps1 init
```

```bash
./tools/stack-kit.sh init
```

## ხელით (მხოლოდ ხე)

```
stack-kit extend --init --root <host>
```

## სრული ხე (v2 layout)

```text
your-app/
├── stack-kit.json          # version 2
├── apps/frontend, apps/backend
├── kits/stack-kit/         # vendor/submodule (არა scaffold-ში)
├── ops/
│   ├── config/               # was secrets/
│   ├── compose/catalog.json
│   ├── compose/stack/        # compose-gen output
│   ├── cli/stack-kit.ps1
│   └── ci/
├── tools/stack-kit.ps1         # shim → ops/cli
└── docs/
```

**გენერირდება** `compose-gen`-ით:  
`apps/*/docker-compose*.yml`, `ops/compose/stack/*.yml`, `apps/backend/ops.modules`.

## შემდეგი ნაბიჯები

1. `stack-kit init` — scaffold + seed + compose-gen + checklist
2. შეავსე env ფაილები და `ops/deploy/targets.json`
3. [docs/ADOPT.md](../docs/ADOPT.md)

`ops/compose/catalog.full.json` — სრული stack; `catalog.minimal.json` — მხოლოდ API (`init -MinimalCatalog`).

This directory is the template store of the extension points (`config/extension-points.json`): init lays down the points it requires, everything else is made on demand (`stack-kit extend <point> [<name>]`).
