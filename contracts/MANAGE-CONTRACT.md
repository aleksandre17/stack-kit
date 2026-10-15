# Manage CLI contract (frontend + backend)

Unified verbs where possible:

| Verb | Frontend (`manage.ps1`) | Backend (`manage.sh`) |
|------|-------------------------|------------------------|
| `status` | local + remote; shows static/compose mode | remote compose services |
| `logs` | `docker` \| `app` \| `errors` \| `auth` \| `db` \| `files` + level | same sources |
| `stop` | `docker stop` | `compose stop` |
| `start` | `docker start` | `compose up -d` |
| `restart` | `docker restart` | `compose restart` |
| `rebuild` | compose build (remote) / hint for static dist | `compose build` + up |
| `reload` | nginx reload (static dist) | n/a |
| `config` | show `dist/config.json` on server | n/a |
| `undeploy` / `rm` | stop + rm container | `compose down` (keep files) |
| `delete` / `nuke` | stop + rm + delete files | per-service: `compose down -v --rmi local` + wipe deploy dir |
| `nuke all` | n/a | each deployed service above + **scoped** image removal for those compose service names only (no global `docker image prune`) |

## Frontend deploy modes on server

| Mode | Detection | Manage |
|------|-----------|--------|
| **static** | `dist/index.html` + nginx container | `reload`, `config`, docker lifecycle |
| **compose** | `docker-compose.yml` present | same as backend per-container |

## Examples

```powershell
.\frontend\scripts\ps1\manage.ps1 status
.\frontend\scripts\ps1\manage.ps1 reload
.\frontend\scripts\ps1\manage.ps1 config
```

```bash
./tools/stack-kit.sh be manage api status --prod
./tools/stack-kit.sh be manage api logs errors --prod
./tools/stack-kit.sh be manage api logs app ERROR --prod
```

```powershell
.\frontend\scripts\ps1\manage.ps1 logs errors
.\frontend\scripts\ps1\manage.ps1 logs app WARN
```

See [README-MANAGE-LOGS.md](README-MANAGE-LOGS.md).
