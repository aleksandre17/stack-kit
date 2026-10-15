# Compose catalog

Edit `catalog.json`, then:

```powershell
.\tools\stack-kit.ps1 compose-gen
```

Default from scaffold: `catalog.minimal.json` (API only, `worker: false`).  
Extend using your app's `ops/compose/catalog.json` or [ADOPT.md#compose-catalog](../../kits/stack-kit/docs/ADOPT.md#compose-catalog).

Do not hand-edit `# GENERATED` compose files.
