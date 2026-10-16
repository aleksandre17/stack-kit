# node-api driver

Node HTTP services (Fastify / Express / Nest), `"type": "node-api"`. A long-running, health-checked
container -- not `node-vite`'s static UI. Everything below is declared in `drivers/registry.json`.

| | Declared |
|---|---|
| lifecycle | `build`, `test`, `lint`: the module's package scripts (`packageScripts`, the shared runner under `drivers/_shared/package-scripts/`; `node.scripts.<step>`, `node.packageManager`, `node.prebuildScripts`) |
| host run | `run` / `hybrid boot`: the module's `debug.npmScript` (default `dev`) through pnpm, else npm (`ps1/hybrid.ps1`) |
| package | `build`, then `dist/**`, `package.json` and the lockfile |
| release | `container/Dockerfile`: production dependencies from the lockfile, `npm start`, internal port 3000 |
| remote dev | a Node image running the `dev` script; `node_modules` a named volume; a manifest or lockfile change `restart`s |

Golden paths: [docs/GOLDEN-PATHS.md](../../docs/GOLDEN-PATHS.md).
