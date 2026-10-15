# Starter — new consumer in 15 minutes

## 1. Add the kit

```bash
git submodule add <stack-kit-repo-url> kits/stack-kit
# or copy kits/stack-kit/
```

Pin version: `cd kits/stack-kit && git checkout v1.0.0` (see `VERSION`).

## 2. Manifest

```bash
cp kits/stack-kit/scaffold/stack-kit.json ./stack-kit.json
```

Edit:

- `modules.*.path` — your app trees
- `modules.*.role` — `ui`, `api`, `worker`, …
- `modules.*.secretsModule` — folder under `ops/config/`
- `cli.aliases` — shortcuts (`fe`, `be`, …)

## 3. Credentials (optional)

**Single GCP (global):**

```json
"features": { "gcpCredentials": true },
"adapters": {
  "gcp": {
    "credentialsFile": "google-credentials.json",
    "containerMount": "/app/google-credentials.json",
    "envVar": "GOOGLE_APPLICATION_CREDENTIALS"
  }
}
```

**Multiple files on one module:**

```json
"modules": {
  "api": {
    "role": "api",
    "type": "java-boot",
    "credentials": [
      { "file": "gcp-primary.json", "mount": "/app/gcp-primary.json", "envVar": "GOOGLE_APPLICATION_CREDENTIALS" },
      { "file": "gcp-audit.json", "mount": "/app/gcp-audit.json", "envVar": "GCP_AUDIT_CREDENTIALS" }
    ]
  }
}
```

## 4. Run and Debug (Cursor / VS Code)

```powershell
.\tools\stack-kit.ps1 vscode-gen --force
```

Run and Debug პანელში: **Full stack (local)** ან ცალკე UI/API.  
რომელი რეჟიმი როდის (ლოკალური / Docker / remote): **[DEV-MODES.md](DEV-MODES.md)**. VS Code დეტალები: [LOCAL-DEBUG.md](LOCAL-DEBUG.md).

## 5. Bootstrap

```powershell
.\tools\stack-kit.ps1 init
.\tools\stack-kit.ps1 validate
.\tools\stack-kit.ps1 compose-gen
```

## 6. CI

Copy `kits/stack-kit/scaffold/ops/ci/integration-stack.sh` → `ops/ci/integration-stack.sh`.

See consumer [docs/CI.md](../../../docs/CI.md).

## 7. Migrate legacy repo

```powershell
.\tools\stack-kit.ps1 migrate          # dry-run
.\tools\stack-kit.ps1 migrate --apply
.\tools\stack-kit.ps1 validate
```

## Next

- [ADOPTION-LINE.md](ADOPTION-LINE.md) — full pipeline
- [MATURITY.md](MATURITY.md) — release checklist
- [PACKAGE-ARCHITECTURE.md](PACKAGE-ARCHITECTURE.md) — design boundaries
