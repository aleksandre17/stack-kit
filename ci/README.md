# CI helpers (generic)

| Script | Role |
|--------|------|
| `wait-health.sh` | curl + grep until HTTP healthy |
| `prepare-integration-env.sh` | manifest-driven seed (`lib/ci_prepare.py`) — modules + optional GCP |

Project-specific integration (which module, compose file, health URLs) stays in **`ops/ci/`** at repo root, declared in the manifest `ci.*` (`ci.scripts` for the host's own) — [docs/REFERENCE.md#manifest](../docs/REFERENCE.md#manifest).
