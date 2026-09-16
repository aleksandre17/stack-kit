# დეველოპმენტის რეჟიმები — რომელი ვარიანტი როდის

ეს არის **მთავარი გზამკვლევი**: ლოკალური (Docker-ის გარეშე), ლოკალური Docker, remote სერვერი + Docker.  
Run and Debug (`launch.json`) — იხ. [LOCAL-DEBUG.md](LOCAL-DEBUG.md). Golden paths — [GOLDEN-PATHS.md](GOLDEN-PATHS.md).

---

##  ცხრილი

| რეჟიმი | სად მუშაობს | Docker | VS Code Run and Debug |
|--------|-------------|--------|------------------------|
| **① ლოკალური, host** | შენი Windows/Mac — Node/Java პირდაპირ | **არა** | **კი** — `npm run dev`, `Spring Boot`, `Full stack (local)` |
| **② ლოკალური Docker** | იგივე მანქანა, `localhost` | **კი** | Task / launch: `geostat stack`, `<alias> compose up` |
| **③ Remote + Docker** | Linux სერვერი (SSH) | **კი** (სერვერზე) | Tasks: `geostat: <alias> dev watch` — ან `geostat dev up <alias> --mode remote` |
| **④ Hybrid** | Apps host-ზე, infra remote + tunnel | **კი** (remote) | **კი** — `Hybrid: infra tunnel + API + UI`, `geostat hybrid boot` |

---

## ① ლოკალური — Docker-ის გარეშე (ყველაფერი host-ზე)

ჩვეულებრივი დეველოპმენტი **შენს კომპიუტერზე**, პირდაპირ Node და Java-თი.

### Run and Debug (Cursor / VS Code)

| კონფიგურაცია | რა ხდება |
|---------------|----------|
| **`<ui-module>: npm run dev`** | Vite — `modules.<ui>.path` (მაგ. `apps/web`), პორტი ~5173 |
| **`<api-module>: Spring Boot`** | Gradle/Java ლოკალურად, breakpoints |
| **Full stack (local)** | UI + API ერთად (compound) |

### ტერმინალი (იგივე რეჟიმი)

```powershell
cd <ui-module-path>; npm run dev
cd <api-module-path>; .\gradlew bootRun
```

**Docker არ გჭირდება.** API შეიძლება იყოს ლოკალური ან remote URL — `ops/config/<ui>/env.dev` (`VITE_API_URL`).

---

## ② ლოკალური — Docker-ით (compose შენს მანქანაზე)

კონტეინერები **`localhost`**-ზე; remote SSH არაა.

### Run and Debug / Tasks

| სახელი | რა ხდება |
|--------|----------|
| **geostat: stack (compose dev)** | მთელი stack — `geostat stack up -d --build` |
| Task: **geostat: <ui-alias> compose up** | მხოლოდ UI კონტეინერი |
| Task: **geostat: <api-alias> compose up** | მხოლოდ API კონტეინერი |

### ტერმინალი

```powershell
.\tools\geostat.ps1 <ui-alias> compose up -d --build
.\tools\geostat.ps1 <api-alias> compose up -d --build
.\tools\geostat.ps1 stack up -d --build
```

**Docker კი, remote არა.**

---

## ③ Remote სერვერი + Docker (Linux / SSH)

კოდი იწერება **ლოკალურად** (Windows), გაშვება **სერვერზე** Docker compose-ით.  
Run and Debug launch-ში ეს mode **არ ჩანს** — VS Code Tasks (`geostat: <alias> dev watch`) ან CLI.

### სწრაფი გაშვება — ერთი ბრძანება

```powershell
geostat dev up <alias> --mode remote   # rsync → server, watch კონტეინერში
geostat dev up all --mode remote       # ყველა მოდული: თითო ახალ terminal window-ში
```

`dev up --mode remote` კითხულობს driver-ის `tasks.devWatch` argv-ს `drivers/registry.json`-იდან —
ახალი driver-ის დამატება **დეკლარაციაა**, არა კოდის ცვლილება.

### VS Code Tasks (Terminal → Run Task)

`vscode-gen` თითოეული მოდულისთვის აგენერირებს იმ watch task-ებს, რომლებსაც მისი driver
**აცხადებს** `registry.json`-ში:

| Task | საიდან მოდის |
|------|---------------|
| `geostat: <alias> dev watch` | driver-ის `tasks.devWatch` |
| `geostat: <alias> deploy watch` | driver-ის `tasks.deployWatch` (თუ აცხადებს) |

driver, რომელიც watch task-ს არ აცხადებს, ვერც ერთს მიიღებს — და ეს **გაცხადებული
არყოფნაა**, არა ჩუმი ნაკლი.

### ხელით CLI (bootstrap საჭიროა პირველ გაშვებაზე)

### Frontend (Vite კონტეინერში)

| მიზანი | ბრძანება | სერვერზე |
|--------|----------|----------|
| Remote dev | `geostat <ui-alias> dev bootstrap` → **`geostat <ui-alias> dev watch`** | `{DEPLOY_PATH}/compose/dev/{container}/` + Docker |
| Prod-like static | `geostat <ui-alias> deploy dist` → **`geostat <ui-alias> deploy watch`** | `static/` + nginx |

### Backend (Gradle bootRun კონტეინერში)

| მიზანი | ბრძანება | სერვერზე |
|--------|----------|----------|
| Remote dev | `geostat <api-alias> dev bootstrap` → **`geostat <api-alias> dev watch`** | workspace + Docker |
| Prod JAR | `geostat <api-alias> deploy all` | `runtime/` |

### Full stack prod (remote)

```powershell
.\tools\geostat.ps1 stack-deploy --prod
```

### პირობები

- `ops/config/deploy.env` — `DEPLOY_SERVER`, `DEPLOY_LAYOUT=structured`
- SSH: `ops/config/ssh/`

დეტალი: [REMOTE-DEV-DOCKERFILE-FLOW.md](REMOTE-DEV-DOCKERFILE-FLOW.md), [GOLDEN-PATHS.md](GOLDEN-PATHS.md), consumer `docs/DEV-REMOTE.md`, `docs/FE-WATCH.md`.

---

## ④ Hybrid — apps ლოკალურად (Windows), infra remote Linux

**Apps** — `gradlew bootRun` / `npm run dev` შენს მანქანაზე; **Postgres / Redis / Qdrant / RabbitMQ** — მხოლოდ Linux სერვერზე Docker-ით; კავშირი **SSH tunnel** → `localhost`.

| ნაბიჯი | ბრძანება |
|--------|----------|
| 1. Infra remote | `geostat infra remote up` |
| 2. Tunnel | `geostat infra tunnel` (ან VS Code compound preLaunch) |
| 3. Apps | `geostat hybrid boot <alias>` ან `geostat <alias> run` |
| 4. F5 compound | Run and Debug → **Hybrid: infra tunnel + API + UI** |

**Env:** `ops/config/<module>/.env.dev` — `INFRA_HOST=127.0.0.1`, peer URLs (`RETRIEVAL_BASE_URL`, …). Spring profile — manifest `modules.*.hybrid.springProfiles`.

**არ აურიო:** `worker` role-ის მოდული compose service-ს თავისი `modules.<id>` დეკლარაციით იღებს.

სრული არქიტექტურა: consumer [HYBRID-DEV-ARCHITECTURE.md](../../../docs/plan/HYBRID-DEV-ARCHITECTURE.md).

---

## სქემა

```text
                    ┌─────────────────────────────────────┐
                    │  შენი ლეპტოპი (Windows / Mac)        │
                    └─────────────────────────────────────┘
         │                              │
         │ ① ლოკალური, NO Docker         │ ② ლოკალური Docker
         │    Run and Debug:            │    stack / <alias> compose
         │    npm + Java                │    localhost
         │    Full stack (local)        │
         │                              │
         └──────────────┬───────────────┘
                        │ SSH + rsync
                        ▼
                    ┌─────────────────────────────────────┐
                    │  Linux სერვერი                        │
                    │  ③ geostat <alias> dev watch            │
                    │     Docker on server                  │
                    └─────────────────────────────────────┘
```

---

## რას აირჩიო (სწრაფი)

| მინდა… | აირჩიე |
|--------|--------|
| F5, breakpoints, UI+API სწრაფად ლოკალურად | **Full stack (local)** |
| მხოლოდ UI ლოკალურად | **`<ui-module>: npm run dev`** |
| ყველაფერი Docker-ში ლაპტოპზე | task **geostat: stack dev** ან `geostat stack up -d --build` |
| Apps local, infra remote (✓ breakpoints) | task **geostat: dev up <alias>** / `geostat dev up <alias>` |
| ყველა მოდული ერთდროულად (hybrid) | `geostat dev up all` — ახალ windows-ებში |
| ვწერ Windows-ზე, ვიღებ Linux+Docker-ზე | **`geostat <alias> dev watch`** / `geostat dev up <alias> --mode remote` |
| ყველა მოდული remote watch | `geostat dev up all --mode remote` |
| Prod UI სერვერზე | **`geostat <ui-alias> deploy watch`** |
| Prod API სერვერზე | **`geostat <api-alias> deploy all`** |

---

## `deploy watch` vs `dev watch` (remote)

| ბრძანება | რას აკეთებს | path სერვერზე | VS Code Task |
|----------|-------------|----------------|--------------|
| **`<ui-alias> dev watch`** | rsync სორსი, dev server კონტეინერში | `.../compose/dev/{service}/` | `geostat: <alias> dev watch` |
| **`<ui-alias> deploy watch`** | build static → nginx reload loop | `.../static/{service}/` | `geostat: <alias> deploy watch` |
| **`<api-alias> dev watch`** | rsync + in-container restart (bootRun / tsx watch) | workspace | `geostat: <alias> dev watch` |

**წესი:** `dev watch` = სორსი live + compose dev; `deploy watch` = artifact build loop.
რომელი watch არსებობს, ამას **driver აცხადებს** (`registry.json` → `tasks`), და არა ეს დოკუმენტი.

---

## ტესტირება (ყველა რეჟიმი — smoke)

ავტომატური შემოწმება (არ იწყებს ხანგრძლივ სერვისებს mode ①-ში):

```powershell
.\kits\geostat-kit\scripts\dev-modes-verify.ps1
```

```bash
bash kits/geostat-kit/scripts/dev-modes-verify.sh
# სრული Docker integration (თუ daemon ჩართულია):
bash kits/geostat-kit/scripts/dev-modes-verify.sh
# მხოლოდ პაკეტი + config, Docker-ის გარეშე:
bash kits/geostat-kit/scripts/dev-modes-verify.sh --skip-docker --skip-integration
```

რას ამოწმებს:

| რეჟიმი | ავტომატური | ხელით (E2E) |
|--------|------------|-------------|
| ① host | paths, gradlew, npm, launch.json | `npm run dev`, Java F5 |
| ② Docker | `<alias> check`, docker daemon | `stack up`, compose |
| ③ remote | `DEPLOY_LAYOUT`, module-ops-smoke | SSH + `<alias> dev watch` |

პაკეტის pytest: `tests/test_dev_modes_smoke.py`.

---

## დაკავშირებული

- [LOCAL-DEBUG.md](LOCAL-DEBUG.md) — `.vscode` გენერაცია
- [GOLDEN-PATHS.md](GOLDEN-PATHS.md) / [GOLDEN-PATHS-BACKEND.md](GOLDEN-PATHS-BACKEND.md)
- [REMOTE-DEV-DOCKERFILE-FLOW.md](REMOTE-DEV-DOCKERFILE-FLOW.md)
- Consumer: [../../docs/DEV-REMOTE.md](../../docs/DEV-REMOTE.md), [../../docs/FE-WATCH.md](../../docs/FE-WATCH.md)
