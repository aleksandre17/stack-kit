# ops/config/ -- project configuration (consumer repo, not in stack-kit package)

All runtime values live here. Application folders (`frontend/`, `backend/`) hold code only. Where a
deploy goes is not configuration of this folder: it is the targets file (`ops/deploy/targets.json`).

## First-time setup

```powershell
copy frontend\.env.example frontend\.env.dev
copy frontend\.env.example frontend\.env.prod
copy backend\.env.example backend\.env.dev
copy backend\.env.example backend\.env.prod
# SSH: ssh/README.md
# GCP (if needed): backend/google-credentials.json
```

Then: `.\tools\stack-kit.ps1 compose-gen`

## Layout

See [kits/stack-kit/scaffold/README.md](../../kits/stack-kit/scaffold/README.md) and [kits/stack-kit/docs/ADOPT.md#configuration](../../kits/stack-kit/docs/ADOPT.md#configuration).
