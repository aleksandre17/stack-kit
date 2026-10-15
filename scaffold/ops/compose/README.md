# Compose catalog

Edit `catalog.json`, then:

```powershell
.\tools\stack-kit.ps1 compose-gen
```

Default from scaffold: `catalog.minimal.json` (API only, `worker: false`).  
Extend using your app's `infra/compose/catalog.json` or [ADOPTION-LINE.md](../../docs/ADOPTION-LINE.md).

Do not hand-edit `# GENERATED` compose files.
