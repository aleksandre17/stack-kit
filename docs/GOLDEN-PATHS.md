# Golden paths — stack-kit

**რეჟიმების  გზამკვლევი (ლოკალური / Docker / remote):** [DEV-MODES.md](DEV-MODES.md).

**გუნდის პოლიტიკა:** ერთი მიზანი = ერთი ბრძანების ხაზი. არ აურიო `static/` (prod artifact) და `compose/dev/` (სორსი) იმავე host-ზე migration-ის გარეშე.

პროექტის მაგალითები (paths, სიმულაცია):

- Frontend: `docs/FRONTEND-DEPLOY-LAYOUTS.md`, `docs/FRONTEND-LAYOUT-SIMULATION-FULL.md`, `docs/FE-WATCH.md`, `docs/DEV-REMOTE.md`
- Backend: `docs/BACKEND-DEPLOY-LAYOUTS.md`, `docs/BACKEND-LAYOUT-SIMULATION-FULL.md`, `docs/BACKEND-DEV-REMOTE.md`, `docs/BE-DEPLOY-WATCH.md`

---

## 1. სტრუქტურირებული სერვერის ხე

`ops/config/<ui-module>/.env.deploy`:

```env
DEPLOY_PATH=/home/<user>/<project>/frontend
DEPLOY_LAYOUT=structured
DEPLOY_PATH_MODE=base
```

| რეჟიმი | ბრძანება | სერვერზე სრული path |
|--------|----------|---------------------|
| Static prod/staging | `fe deploy dist` / `sync` / `deploy watch` | `{DEPLOY_PATH}/static/{container}/` |
| Remote dev (სორსი) | `fe dev bootstrap` / `sync` / `watch` | `{DEPLOY_PATH}/compose/dev/{container}/` |
| Remote compose prod | `fe deploy remote -Environment prod` | `{DEPLOY_PATH}/compose/prod/{container}/` |
| Tar staging | `fe deploy remote` | `{SERVER_BASE}/{project}/deploy-staging/*.tar.gz` |

`static/{container}/` შიგნით ტიპულად:

```text
.stack-kit-deploy.json
.env.runtime.json
nginx.conf
dist/
  index.html
  assets/
  config.json
```

`compose/dev/{container}/` შიგნით ტიპულად:

```text
.env.dev
docker-compose.yml
docker-compose.override.yml
package.json
src/...
public/...
```

Driver: `node-vite` (Vite, Angular CLI, Nx — compose dev + volume). დეტალი: [drivers/node-vite/README.md](../drivers/node-vite/README.md).

**Backend (JAR + `runtime/`):** [GOLDEN-PATHS-BACKEND.md](./GOLDEN-PATHS-BACKEND.md) — `be deploy`, not static/dist.

---

## 2. Golden paths — რომელი ბრძანება როდის

გამოიყენე **მხოლოდ ერთი** inner loop თითო მიზნაზე.

| მიზანი | Golden path | არ გამოიყენო ყოველდღე |
|--------|-------------|------------------------|
| **Dev Windows-ზე** (API Linux-ზე OK) | `cd frontend && npm run dev` | `fe deploy watch` |
| **Dev Docker-ზე იმავე მანქანაზე** (ლაპტოპი ან Linux) | `stack-kit fe compose up -d` | `fe deploy remote` |
| **Dev პირდაპირ Linux-ზე** (იხილე §4) | `npm run dev` ან `fe compose up` | `fe dev watch`, `fe deploy watch` |
| **Windows რედაქტი → Linux UI** (Vite კონტეინერში) | `fe dev bootstrap` → **`fe dev watch`** | `fe deploy watch`, `fe deploy remote` ყოველ save-ზე |

კონკრეტული ნაკადი `frontend/src/Dockerfile`-ით: **[REMOTE-DEV-DOCKERFILE-FLOW.md](./REMOTE-DEV-DOCKERFILE-FLOW.md)**.
| **Prod / staging static UI** | `fe deploy dist` → `fe deploy sync` / **`fe deploy watch`** | `fe dev watch`, flat legacy |
| **Full stack prod** | `stack-kit stack-deploy --prod` | ხელით არეული რეჟიმები |
| **ინტეგრაცია ლოკალურად** | `stack-kit stack up -d --build` | per-module SSH ხე stack-ის ნაცვლად |

---

## 3. `deploy watch` vs `dev watch` (აუცილებელი განსხვავება)

| ბრძანება | რას აკეთებს | სერვერის path | ყოველ save-ზე |
|----------|-------------|---------------|----------------|
| **`stack-kit fe deploy watch`** | Prod-like **static** | `.../static/{service}/` | `npm build` → `dist/` → nginx reload |
| **`stack-kit fe dev watch`** | Remote **dev** (სორსი) | `.../compose/dev/{service}/` | **rsync** მხოლოდ (build არა) |
| `stack-kit fe watch` | ძველი alias | → `fe deploy watch` (hint CLI-ში) | იგივე რაც deploy watch |

**წესი:** პრეფიქსი `deploy` = artifact/static; პრეფიქსი `dev` = სორსი + compose dev.

პროექტის  გზამკვლევი: repo `docs/FE-WATCH.md`.

---

## 4. პირდაპირ Linux-ზე მუშაობა — არქიტექტურა **არ იშლება**

ეს პაკეტი აგებულია ფენებად (secrets, structured paths, drivers). **Linux-ზე ყოფნა არქიტექტურას არ არღვევს** — იცვლება მხოლოდ ის, რომელი golden path არის აქტიური.

### რა რჩება იგივე

- `stack-kit.json`, `ops/config/`, `kits/stack-kit`
- სერვერის ხე: `static/`, `compose/dev/`, `compose/prod/`
- Prod UI: `fe deploy dist` / `sync` / `deploy watch`
- Backend: `stack-kit be deploy …`
- Stack: `stack-kit stack up`, `stack-deploy`

### რა **არ გჭირდება** Linux-ზე პირდაპირ

| Windows → Linux | Linux-ზე პირდაპირ |
|-----------------|------------------|
| `fe dev bootstrap` + `fe dev watch` (rsync) | **არა** — ფაილები უკვე იმავე მანქანაზე/რეპოში |
| `fe deploy watch` UI dev-ისთვის | **არა** — გამოიყენე `npm run dev` ან `compose up` |

`fe dev *` განკუთვნილია **რედაქტორის ერთ host-ზე, runtime სხვაზე** სცენარისთვის. თუ რედაქტირებაც და Docker-იც იმავე Linux-ზეა, golden path = **A1/A2** (ქვემოთ).

### Golden path Linux-ზე

| სიტუაცია | რა გაუშვა |
|----------|----------|
| UI dev, ყველაფერი ერთ VM-ზე | `cd frontend && npm run dev` **ან** `stack-kit fe compose up -d` |
| UI + API ერთად იმავე მანქანაზე | `stack-kit stack up -d --build` |
| Prod static **ამ** სერვერზე | `stack-kit fe deploy dist` → `sync` / `deploy watch` |
| Linux laptop → **სხვა** remote server | `fe deploy dist`, `be deploy` (SSH იგივე); კოდი სერვერზე — SSH/Remote IDE, არა `dev watch` laptop-დან |
| კოდი კლონირებულია სერვერზე (`compose/dev/...`) | პირდაპირ იქ `docker compose up` / Vite — **სწორი „Linux-only“ მოდელი**, rsync-ის გარეშე |

### CLI Linux-ზე

`node-vite` driver PowerShell-ზეა (`drivers/node-vite/ps1/`).

| ვარიანტი | როგორ |
|----------|------|
| სრული stack-kit | დააყენე **`pwsh`**, შემდეგ `./tools/stack-kit.sh fe …` (delegate → `stack-kit.ps1`) |
| ყოველდღიური dev | `npm` + `docker compose` პირდაპირ — **არქიტექტურა იგივე**, ops CLI გარეშეც |

`stack-kit stack`, `compose-gen`, `stack-deploy` (bash) Linux-ზე უკვე bash-ით მუშაობს.

### შეჯამება (Linux)

- პირდაპირ Linux = **სრულად ჯდება** პაკეტის სტრუქტურაში.
- **არა** ძირითადი გზა: `fe dev watch` / `fe deploy watch` dev-ისთვის.
- **დიახ** dev-ისთვის: `npm run dev` / `fe compose up`.
- **დიახ** prod-ისთვის: `fe deploy dist` / `sync` / `deploy watch`.

---

## 5. Deprecated / discouraged

| ძველი / ცუდი ჩვევა | ჩანაცვლება |
|-------------------|------------|
| `DEPLOY_LAYOUT=flat` (`.../frontend/{container}/` მხოლოდ) | `structured` + `static/` ან `compose/dev/` |
| `fe deploy remote` ყოველ ცვლილებაზე | `fe dev bootstrap` + `fe dev watch` (მხოლოდ Windows→Linux) |
| `fe deploy watch` Linux UI dev-ისთვის | `npm run dev` / `fe compose up` / `fe dev watch` მხოლოდ cross-host |
| `stack-kit fe watch` | `stack-kit fe deploy watch` |
| ორი path ერთ host-ზე (flat + structured) | ერთი structured; ძველი წაშლა migration-ის შემდეგ |

---

## 6. სცენარების ID (სიმულაცია)

| ID | სახელი | Host |
|----|--------|------|
| A1 | `npm run dev` | localhost |
| A2 | `fe compose up` (dev) | localhost |
| A3 | `fe compose -Prod up` | localhost smoke |
| A4 | `stack up` | localhost |
| A5 | `fe deploy local` | localhost Docker |
| B1 | `fe deploy dist` | server `static/` |
| B2 | `fe deploy sync` | server `static/` |
| B3 | `fe deploy watch` | server `static/` |
| C1 | `fe deploy remote` dev | server `compose/dev/` |
| C2 | `fe deploy remote` prod | server `compose/prod/` |
| D1 | `fe dev bootstrap` | server `compose/dev/` |
| D2 | `fe dev watch` | server `compose/dev/` (rsync) |
| D3 | `fe dev sync` | server `compose/dev/` |
| D4 | `fe dev restart` | server `compose/dev/` |
| E1 | `stack-deploy` | server backend + frontend static |
| L0 | flat legacy | deprecated |

სიმულაცია პროექტში: `stack-kit layout --frontend` (+ `-OutFile docs/FRONTEND-LAYOUT-SIMULATION-FULL.md`).

---

## 7. სწრაფი ბრძანებები (copy-paste)

```powershell
# --- Windows / cross-host: Linux UI dev ---
.\tools\stack-kit.ps1 fe dev bootstrap -Environment dev
.\tools\stack-kit.ps1 fe dev watch

# --- Prod static on server ---
.\tools\stack-kit.ps1 fe deploy dist -Environment prod
.\tools\stack-kit.ps1 fe deploy sync -Environment prod
.\tools\stack-kit.ps1 fe deploy watch -Environment prod

# --- Linux same machine: daily dev ---
cd frontend && npm run dev
# or
./tools/stack-kit.sh fe compose up -d    # needs pwsh for fe alias

# --- Full stack ---
./tools/stack-kit.sh stack up -d --build
./tools/stack-kit.sh stack-deploy --prod
```

---

## 8. დაკავშირებული პაკეტის დოკუმენტები

| ფაილი | თემა |
|-------|------|
| [ADOPTION-LINE.md](./ADOPTION-LINE.md) | სრული გადმოტანის ხაზი |
| [drivers/node-vite/README.md](../drivers/node-vite/README.md) | SPA driver |
| [../ARCHITECTURE.md](../ARCHITECTURE.md) | პაკეტის ფენები |

პროექტის repo `docs/ARCHITECTURE.md` — პროექტ-სპეციფიკური ფენები + golden paths მიმომხილველი.

## ტესტები (პაკეტის gate — SSH-ის გარეშე)

```bash
bash kits/stack-kit/tests/run-kit-tests.sh
```

41 ტესტი: paths, registry, `fe watch` redirect, Dockerfile `EXPOSE 80`, compose `HOST:80`, B/D/C გაყოფა. CI: `ops-package-tests`. დეტალი: [tests/README.md](../tests/README.md).
