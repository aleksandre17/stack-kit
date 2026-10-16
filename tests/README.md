# stack-kit package tests

Runs **without SSH, rsync, or Docker**. Validates contracts before you adopt the package.

## Run locally

From repo root:

```bash
pip install pytest
python3 -m pytest kits/stack-kit/tests -v
```

Or:

```bash
bash kits/stack-kit/tests/run-kit-tests.sh
```

## What is covered

| Suite | Covers |
|-------|--------|
| **`test_layout_v2.py`** | **Post-migration layout** — manifest paths, `apps/`/`kits/`/`ops/`, no legacy dirs, Spring/Vite/compose wiring |
| `test_deploy_paths.py` | structured / flat / full paths (B1, D1, C1, …) |
| `test_golden_path_matrix.py` | static vs compose/dev vs compose/prod separation |
| `test_driver_resolution.py` | registry, cli-alias resolution, the host run as `run`, stack-deploy steps, no top-level `watch` |
| `test_frontend_contracts.py` | Dockerfile EXPOSE 80, compose `HOST:80`, deploy/dev scripts |
| `test_registry_integrity.py` | every registry command file exists |

## Not covered (manual / integration)

- Real `rsync` / `ssh` from Windows
- Live `<alias> dev bootstrap` on a server
- PowerShell runtime of full deploy.ps1 (use `layout` simulation on Windows)

CI job: `ops-package-tests` in `.github/workflows/ci.yml`.

## Reference consumer fixture

The suite runs against a **synthetic, self-contained reference consumer** under
`tests/fixtures/golden-consumer/` — not the live project manifest. This keeps the
kit's tests validating the kit's *machinery* independent of any consumer's module
set. `conftest.py` self-provisions the one gitignored bit at session
start (the `kits/stack-kit` junction), so a fresh
checkout runs green with no setup. Point `STACK_KIT_PROJECT_ROOT` at a real repo
only to smoke-test an adoption.

## Last results

