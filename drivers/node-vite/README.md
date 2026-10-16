# node-vite driver (SPA)

Vite single-page apps, `"type": "node-vite"`. Everything below is declared in `drivers/registry.json`.

| | Declared |
|---|---|
| lifecycle | `build`, `test`, `lint`: the module's package scripts |
| host run | `run` / `hybrid boot`: `npm run <debug.npmScript | dev>` (`ps1/hybrid.ps1`) |
| package | `build`, then `dist/**` -- once per commit: what differs per environment is runtime config (`modules.<id>.runtimeConfig`, mounted read-only into the served root), never a rebuild |
| release | a static image serving `serve` (default `dist`), every route that is not a file answered by `index.html` (`container/static.conf`) |
| remote dev | a Node image running `dev --host 0.0.0.0` on port 5173; `node_modules` a named volume; a manifest or lockfile change `restart`s, a source change hot-reloads |

Golden paths: [docs/GOLDEN-PATHS.md](../../docs/GOLDEN-PATHS.md).
