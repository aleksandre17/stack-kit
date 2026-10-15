# Remote dev — `src/Dockerfile` (Windows → Linux)

კონკრეტული ქეისი: `frontend/src/Dockerfile` არსებობს Windows-ზე, გუნდი აშვებს **`stack-kit fe dev bootstrap`** + **`stack-kit fe dev watch`**.

ზოგადი golden paths: [GOLDEN-PATHS.md](./GOLDEN-PATHS.md). პროექტი: repo `docs/DEV-REMOTE.md`.

---

## სად არის ფაილი

| ადგილი | სრული გზა (მაგალითი ამ პროექტში) |
|--------|----------------------------------|
| Windows (რედაქტირება) | `frontend/src/Dockerfile` |
| Linux deploy root | `{DEPLOY_PATH}/compose/dev/{container}/` |
| იგივე ფაილი სერვერზე | `.../compose/dev/{COMPOSE_APP_SERVICE}/src/Dockerfile` |
| კონტეინერში (volume) | `/app/src/Dockerfile` |

`docker-compose.yml` (GENERATED):

```yaml
build:
  context: .
  dockerfile: src/Dockerfile
```

`docker-compose.override.yml` (dev):

```yaml
build:
  target: development
volumes:
  - .:/app
  - /app/node_modules
```

---

## `src/Dockerfile` — რომელი stage როდის

```dockerfile
# Stage 1: deps      → npm ci
# Stage 2: development → COPY . . ; CMD npm run dev -- --host 0.0.0.0
# Stage 3: builder   → npm run build (prod build)
# Stage 4: production  → nginx + dist (listens on 80 in-container; host port from DEPLOY_HOST_PORT:80)
```

| ბრძანება | გამოყენებული stage |
|----------|-------------------|
| `fe dev bootstrap` / `fe dev watch` | **მხოლოდ `deps` + `development`** |
| `fe deploy dist` | Windows-ზე `npm build`; სერვერზე nginx + `dist/` (არა ეს compose dev) |
| `fe deploy local` | `production` (ლაპტოპზე) |

---

## ეტაპი 1: `stack-kit fe dev bootstrap -Environment dev`

### 1) rsync (Windows → Linux)

იგზავნება **მთელი** `apps/frontend/` (არა მხოლოდ `src/`):

```text
apps/frontend/
  src/Dockerfile
  src/main.jsx
  package.json
  docker-compose.yml
  docker-compose.override.yml
  ...
```

**არ მიდის:** `node_modules/`, `dist/` (exclude list: `Dev-Remote.ps1`).

სერვერზე: `.../compose/dev/{COMPOSE_APP_SERVICE}/src/Dockerfile` — იგივე შიგთავსი, რაც Windows-ზე.

### 2) `docker compose up -d --build` (Linux)

სერვერზე `cd` → `{DEPLOY_PATH}/compose/dev/{container}/`.

Compose იღებს **`development`** target-ს. Build:

1. **deps** — `npm ci` image-ში
2. **development** — `COPY . .`, `EXPOSE 5177`, `CMD npm run dev -- --host 0.0.0.0`

`builder` და `production` **ამ bootstrap-ში არ იშენება**.

### 3) კონტეინერი + volume

- Volume `.:/app` — სერვერის deploy ფოლდერი = `/app` კონტეინერში
- Volume `/app/node_modules` — image-ის dependencies, host-ის ცარიელი `node_modules` არ ჩაანაცვლებს

**Runtime:** Vite `/app`-დან; UI: `http://<server>:DEPLOY_HOST_PORT` (მაგ. `5177`).

ფაილი დისკზე: `/app/src/Dockerfile` (არსებობს, მაგრამ Vite მას არ „კითხულობს“ ყოველ request-ზე).

---

## ეტაპი 2: `stack-kit fe dev watch`

Windows-ზე ცვლილება, მაგ. `src/components/chatbot/ChatWidget.jsx`.

| ნაბიჯი | `src/Dockerfile` |
|--------|------------------|
| File watcher (Windows) | ჩვეულებრივ **არ** — watch roots: `src/`, `public/`, `vite.config.*`, … |
| rsync | თუ Dockerfile შეცვალე → გადაიწერება სერვერზე `src/Dockerfile` |
| Docker rebuild | **არა** |
| UI | Vite HMR — JSX/CSS |

**ყოველდღიური loop** = კოდი `src/`-ში, არა Dockerfile.

---

## Dockerfile შეცვლა Windows-ზე

| მოქმედება | შედეგი |
|-----------|--------|
| მხოლოდ `fe dev watch` | ფაილი სერვერზე განახლდება; **გაშვებული image იგივეა** — CMD/stages არ იცვლება |
| სწორი განახლება | **`stack-kit fe dev bootstrap`** (საჭიროა `--build`) |

საჭიროა rebuild მაგალითად თუ შეცვალე: `CMD`, `EXPOSE`, base image, dev stage-ის `RUN`/`COPY` ლოგიკა.

`fe dev restart` — env/პროცესის restart; Dockerfile-ის სტრუქტურის ცვლილებისთვის საკმარისი არ არის.

---

## რა არ ხდება ამ flow-ში

- **არ** გაეშვება `production` nginx stage ამ ბრძანებებით
- **არ** გაეშვება `npm run build` ყოველ save-ზე (`fe deploy watch` სხვაა)
- **არ** აიწყობა `dist/` `static/` path-ზე — ეს `fe deploy dist` სამყაროა

---

## დიაგრამა

```text
Windows: frontend/src/Dockerfile
        │
        │  fe dev bootstrap: rsync (მთელი apps/frontend/)
        ▼
Linux:   .../compose/dev/{container}/src/Dockerfile
        │
        │  docker compose build --target development
        │  (კითხულობს src/Dockerfile)
        ▼
Image:   deps + development (Vite CMD)
        │
        │  docker run -v .:/app
        ▼
Runtime: /app = სერვერის ფოლდერი
         Vite ← src/*.jsx (HMR)
         /app/src/Dockerfile ← ფაილი არსებობს, ყოველდღე არ „სრულავს“

fe dev watch: rsync src/... → Vite reload (Dockerfile ცვლილება → bootstrap)
```

---

## ბრძანებები

```powershell
# ერთხელ (ან Dockerfile / package.json სტრუქტურის ცვლილების შემდეგ)
.\tools\stack-kit.ps1 fe dev bootstrap -Environment dev

# ყოველდღე
.\tools\stack-kit.ps1 fe dev watch -Environment dev
```

---

## დაკავშირებული ფაილები

| ფაილი | როლი |
|-------|------|
| `frontend/src/Dockerfile` | multi-stage; dev = `development` |
| `apps/frontend/docker-compose.yml` | `dockerfile: src/Dockerfile` |
| `apps/frontend/docker-compose.override.yml` | `target: development`, volumes |
| `kits/stack-kit/toolkit/powershell/Dev-Remote.ps1` | rsync + compose up |
| `kits/stack-kit/drivers/node-vite/ps1/dev.ps1` | bootstrap / watch |
