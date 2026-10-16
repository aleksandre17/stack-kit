# stack-kit init

ერთი ბრძანება — სრული ops bootstrap ახალი ან ნაწილობრივ მოწყობილი repo-სთვის.

**პროექტის დოკუმენტაცია (სრული):** [docs/INSTALL.md#first-run](../../docs/INSTALL.md#first-run)

## გაშვება

```powershell
# repo root-დან (ან ცარიელი ფოლდერიდან, სადაც გინდა პროექტი)
.\tools\stack-kit.ps1 init

# მხოლოდ API (worker-ის გარეშე) catalog
.\tools\stack-kit.ps1 init -MinimalCatalog

# არსებული env-ების გადაწერა examples-დან
.\tools\stack-kit.ps1 init -ForceExamples
```

```bash
./tools/stack-kit.sh init
```

## რას აკეთებს

1. **apply-scaffold** — `tools/`, `ops/config/*.example`, `apps/*`, `ops/compose/`, `stack-kit.json`
2. **catalog** — `catalog.full.json` → `ops/compose/catalog.json` (სრული FE+BE+stack; `-MinimalCatalog` — მხოლოდ API)
3. **seed** — `.example` → `.env.dev`, `.env.prod`, `nginx.env`
4. **.gitignore** — scaffold წესების დამატება
5. **compose-gen** — `docker-compose*.yml`, `backend/ops.modules`
6. **nginx-gen** — თუ არსებობს `frontend/nginx.conf.template`
7. **checklist** — რა ჯერ კიდევ უნდა შეივსოს

## Flags

| Flag | მოქმედება |
|------|-----------|
| `-MinimalCatalog` | მინიმალური `catalog.minimal.json` |
| `-SkipComposeGen` | არ გაუშვას compose-gen |
| `-SkipSeed` | არ შექმნას env ფაილები examples-დან |
| `-SkipNginxGen` | გამოტოვოს nginx-gen |
| `-SkipGitIgnore` | არ შეცვალოს `.gitignore` |
| `-ForceExamples` | გადაწეროს არსებული scaffold/env ფაილები |

## არ შედის init-ში

აპლიკაციის კოდი (`frontend/src`, `backend/src`, Gradle) — ეს რჩება შენი starter-ით ან არსებული repo-ით.
