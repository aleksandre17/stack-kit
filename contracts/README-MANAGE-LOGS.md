# Manage logs — shared contract

Single contract for backend (`manage.sh`) and frontend (`manage.ps1`).

## Sources

Defined in `manage-logs.contract.json`:

| Source | File (under `<deploy>/logs/`) | Notes |
|--------|----------------------------------|-------|
| `docker` | — | `docker logs -f <container>` |
| `app` | `app.log` | tail -f |
| `errors` | `error.log` | tail -f |
| `auth` | `auth.log` | tail -f |
| `db` | `db.log` | tail -f |
| `files` | — | `find … -name '*.log'` |

## Level filter

Optional: `ERROR`, `WARN`, `INFO` (grep on log lines). Not applied to `docker` or `files`.

## Examples

```bash
./tools/stack-kit.sh be manage your-app-api logs errors --prod
./tools/stack-kit.sh be manage all logs app ERROR --prod
```

```powershell
.\frontend\scripts\ps1\manage.ps1 logs errors
.\tools\stack-kit.ps1 fe manage your-app-app logs app WARN
```

## Implementation

| Module | Role |
|--------|------|
| `kits/stack-kit/toolkit/bash/manage-logs.sh` | Bash dispatch |
| `kits/stack-kit/toolkit/bash/manage-remote.sh` | `remote_path`, `remote_logs_path` |
| `kits/stack-kit/toolkit/powershell/Manage-Logs.ps1` | PowerShell dispatch |

Backend remote paths always use `remote_path()` — never raw `$REMOTE/$service` when compose service key ≠ directory name.
