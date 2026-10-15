# Golden paths — backend (java-boot)

**გუნდის პოლიტიკა:** `runtime/` = JAR deploy; `workspace/` = source dev (`be dev`). არ აურიო ერთ host-ზე migration-ის გარეშე.

სრული ახსნა flat vs structured: [../../../docs/BACKEND-DEPLOY-LAYOUTS.md](../../../docs/BACKEND-DEPLOY-LAYOUTS.md)  
Remote dev: [../../../docs/BACKEND-DEV-REMOTE.md](../../../docs/BACKEND-DEV-REMOTE.md)  
Deploy watch: [../../../docs/BE-DEPLOY-WATCH.md](../../../docs/BE-DEPLOY-WATCH.md)

---

## 0. Layout — ერთი წინადადი

| ტერმინი | მნიშვნელობა |
|--------|-------------|
| **`DEPLOY_LAYOUT=structured`** | სერვერი: `runtime/` (JAR) + `workspace/` (dev rsync) |
| **`flat`** | legacy: `{DEPLOY_PATH}/{container}/` პირდაპირ |
| **flat → runtime** | მიგრაცია ძველი flat დირექტორიის `runtime/{container}/`-ში |

```env
# ops/config/backend/.env.deploy
DEPLOY_PATH=/home/<user>/<project>/backend
DEPLOY_LAYOUT=structured
```

`.env.deploy` გარეშე deploy იყენებს **flat** fallback-ს.

---

## 1. Structured server tree

| რეჟიმი | ბრძანება | სერვერზე path |
|--------|----------|----------------|
| JAR prod/staging | `be deploy <svc> --prod\|--dev` | `{DEPLOY_PATH}/runtime/{container}/` |
| JAR auto loop | `be deploy watch` | იგივე `runtime/` |
| Remote source dev | `be dev bootstrap` / `sync` / `watch` | `{DEPLOY_PATH}/workspace/{container}/` |

`runtime/{container}/` შიგნით ტიპულად:

```text
Dockerfile          # src/Dockerfile — COPY app.jar
app.jar
.env.dev | .env.prod
docker-compose.{dev|prod}.yml
logs/
versions/           # prod
.stack-kit-deploy.json
```

Driver: [drivers/java-boot/README.md](../drivers/java-boot/README.md), [REMOTE-DEV-JAR-FLOW.md](./REMOTE-DEV-JAR-FLOW.md).

---

## 2. Golden paths — რომელი ბრძანება როდის

| მიზანი | Golden path | არ გამოიყენო ყოველ save-ზე |
|--------|-------------|---------------------------|
| Dev ლოკალურად | `./gradlew bootRun` ან `be compose up` | `be deploy` |
| Windows → Linux (bootRun კონტეინერში) | `be dev bootstrap` → `be dev watch` | `be deploy` |
| Windows → Linux (JAR როგორც staging) | `be deploy` → `be deploy watch` | `be dev watch` |
| Staging/prod სერვერზე (ერთხელ) | `be deploy <svc> --dev\|--prod` | სრული repo tar |
| სწრაფი jar (უკვე build) | `be deploy <svc> --no-build` | სრული gradle |
| სტატუსი / restart | `be manage <svc> …` | SSH ხელით |

---

## 3. Frontend-თან შედარება

| Frontend | Backend |
|----------|---------|
| `static/` + dist | `runtime/` + `app.jar` |
| `compose/dev/` + rsync | `workspace/` + `be dev` |
| `fe deploy watch` | `be deploy watch` |
| `fe dev watch` | `be dev watch` (DevTools reload; `--restart` საჭიროებისამებრ) |

---

## 4. Migration

1. `ops/config/backend/.env.deploy` — `DEPLOY_LAYOUT=structured`
2. `migrate-backend-layout.sh --dry-run` → apply (თუ flat არსებობს)
3. `be deploy <svc>` → ახალი ფაილები `runtime/`-ში
4. ძველი `{DEPLOY_PATH}/{container}/` წაშლა (optional)

სიმულაცია: `stack-kit layout --backend` → [BACKEND-LAYOUT-SIMULATION-FULL.md](../../../docs/BACKEND-LAYOUT-SIMULATION-FULL.md)
