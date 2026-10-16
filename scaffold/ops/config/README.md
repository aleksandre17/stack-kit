# ops/config/ — project configuration (consumer repo, not in stack-kit package)

All runtime values live here. Application folders (`frontend/`, `backend/`) hold code only.

## First-time setup

```powershell
copy deploy.env.example deploy.env
copy frontend\.env.example frontend\.env.dev
copy frontend\.env.example frontend\.env.prod
copy frontend\.env.deploy.example frontend\.env.deploy
copy backend\.env.example backend\.env.dev
copy backend\.env.example backend\.env.prod
copy backend\.env.deploy.example backend\.env.deploy
# SSH: ssh/README.md
# GCP (if needed): backend/google-credentials.json
```

Then: `.\tools\stack-kit.ps1 compose-gen`

## Layout

See [kits/stack-kit/scaffold/README.md](../../kits/stack-kit/scaffold/README.md) and [kits/stack-kit/docs/ADOPT.md#configuration](../../kits/stack-kit/docs/ADOPT.md#configuration).
