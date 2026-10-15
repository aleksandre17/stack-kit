# Local Run and Debug (VS Code / Cursor)

**რომელი რეჟიმი როდის (ლოკალური / Docker / remote)?** → **[DEV-MODES.md](DEV-MODES.md)** — მთავარი გზამკვლევი.

პაკეტი გენერირებს **`.vscode/launch.json`** და **`tasks.json`** manifest-იდან — paths აღარ არის hardcoded.

## გენერაცია

```powershell
.\tools\stack-kit.ps1 vscode-gen          # მხოლოდ აკლებული ფაილები
.\tools\stack-kit.ps1 vscode-gen --force  # გადაწერა
```

`stack-kit init` — ავტომატურად უშვებს `vscode-gen` (თუ `.vscode` ფაილები არ არსებობს).

## რა იქმნება

| Driver | Launch config | რა იწყება |
|--------|---------------|-----------|
| `node-vite` | `npm run dev` | Vite ლოკალურად (`modules.<id>.path`) |
| `java-boot` | Java: Spring Boot | `mainClass` + `projectName` (ან auto-detect) |
| — | `stack-kit: stack` | compose stack dev |
| — | `stack-kit: <alias> check` | ops smoke |

**Compound:** `Full stack (local)` — API + UI ერთად (Run and Debug → compound).

**Hybrid ④:** `Hybrid: infra tunnel + API + UI` — `preLaunchTask` = SSH tunnel (`stack.infra.services` manifest-ში); საჭიროა `ops/config/deploy.env` + `ops/config/infra/.env.dev`. Remote infra: `stack-kit infra remote up` (task ან ხელით).

## Manifest (ოფციური დეტალები)

```json
"vscode": {
  "folder": ".vscode",
  "cliScript": "tools/stack-kit.ps1"
},
"modules": {
  "api": {
    "type": "java-boot",
    "path": "apps/api",
    "debug": {
      "java": {
        "mainClass": "com.example.Application",
        "projectName": "my-gradle-root"
      }
    }
  },
  "web": {
    "type": "node-vite",
    "debug": { "npmScript": "dev", "label": "UI: Vite" }
  }
}
```

თუ `debug.java` არ არის — პაკეტი ეძებს `*Application.java` და `settings.gradle` `rootProject.name`.

## საჭირო extensions (Cursor / VS Code)

| Stack | Extension |
|-------|-----------|
| Java/Spring | Extension Pack for Java |
| Node/Vite | ჩვეულებრივ built-in terminal (`node-terminal`) |

## Tasks პანელი

`tasks.json` — `stack-kit stack`, `compose-gen`, `validate`, `<alias> compose up`, checks.

გაშვება: **Terminal → Run Task** ან launch-ში preLaunchTask (თუ ხელით დაამატებ).

## რეჟიმები — launch.json და tasks.json

| რეჟიმი | Run and Debug (launch) | Tasks Panel |
|--------|------------------------|-------------|
| ① ლოკალური, Docker-ის გარეშე | `<ui-module>: npm run dev`, `<api-module>: Spring Boot`, **Full stack (local)** | — |
| ② ლოკალური Docker | `stack-kit: stack (compose dev)` | `stack-kit: stack dev`, `stack-kit: <alias> compose up` |
| ③ Remote + Docker | **launch-ში არ არის** | `stack-kit: <alias> dev watch`, `stack-kit: dev up <alias> --mode remote` |
| ④ Hybrid | **Hybrid: infra tunnel + API + UI** | `stack-kit: dev up <alias>`, `stack-kit: infra tunnel`, `stack-kit: infra remote up` |

სრული ცხრილი, commands და `dev watch` vs `deploy watch`: **[DEV-MODES.md](DEV-MODES.md)**.

## დაკავშირებული

- [DEV-MODES.md](DEV-MODES.md) — ლოკალური vs Docker vs remote
- [STARTER.md](STARTER.md)
- [MATURITY.md](MATURITY.md)
- [REMOTE-DEV-DOCKERFILE-FLOW.md](REMOTE-DEV-DOCKERFILE-FLOW.md)
