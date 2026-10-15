# stack-kit package tests — last run

| Field | Value |
|-------|--------|
| Date | 2026-09-16 |
| Host | Windows (`win32`) |
| Python | 3.13.3 |
| **Result** | **251 passed, 1 failed, 23 skipped** (0 errors) |
| Project root | **synthetic fixture** `tests/fixtures/golden-consumer` (self-contained) |

## Command

```powershell
cd stack-kit
py -3 -m pytest tests -q
```

No `STACK_KIT_PROJECT_ROOT` is required: the suite runs against a synthetic,
self-contained reference consumer that the kit owns. `conftest.py` materialises
the two volatile bits at session start (a `kits/stack-kit` junction back to the
real kit, and `ops/config/deploy.env` from `deploy.env.fixture`). Set
`STACK_KIT_PROJECT_ROOT` only to smoke-test the kit against a *real* consumer repo.

## The one failure — declared, not hidden

`tests/test_driver_api.py::TestNodeApiDriver::test_node_step_helpers_exist`
asserts `toolkit/deploy/pnpm-build.sh` exists. That file has not landed yet: it
is the subject of a separate, still-open decision (it hardcodes a privileged npm
script name and must be generalised to a manifest-declared prebuild list before
it is taken). The test is correct and the tree is honestly red until that lands.

## Why a synthetic fixture

The suite used to point `repo_root` at whatever `stack-kit.json` sat at the
real project root, asserting one adopting project's module ids. When that
consumer's module set changed, dozens of tests failed — the suite was testing the
consumer, not the kit. The kit is a reusable package, so its tests now run
against a fixture it controls: deterministic, and immune to consumer manifest
churn (standard golden-fixture pattern).

## The reference consumer is GENERIC by construction

`tests/fixtures/golden-consumer/` models a representative multi-module consumer
under **role-named, project-neutral ids** — no consumer brand appears in an id,
a path, a service name or an assertion:

| id | driver | role | exercises |
|----|--------|------|-----------|
| `api` | `java-boot` | api | env-profiles config-gen, two credentials, `spring.portEnv` |
| `search` | `java-boot` | api | simple config-gen, qdrant datastore |
| `worker` | `java-boot` | worker | postgres (+ flyway) and rabbitmq datastores |
| `web` | `node-vite` | ui | vite env wiring, primary-UI compose naming |
| `svc` | `node-api` | api | node-api driver resolution |

## What the suite meaningfully verifies

- Manifest validation + schema + package boundary (`test_validate_manifest`, `test_layout_v2`)
- Driver registry integrity + driver_api resolution incl. node-api & node-vite (`test_driver_api`, `test_registry_integrity`)
- Compose service naming + config-gen golden output (`test_compose_identity`, `test_config_gen`)
- Deploy-path logic, stack-deploy ordering, migrate-layout (`test_deploy_paths`, `test_migrate_layout`)
- Credentials (explicit list + global GCP fallback), vscode-gen, scaffold abstractness

## Not run in this suite

SSH, rsync, Docker, live remote deploy.
