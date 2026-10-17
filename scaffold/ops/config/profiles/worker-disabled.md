# Embedded worker disabled

Use when the **worker role** is a separate manifest module (e.g. `ingestion`), not a worker embedded in the API module.

1. `ops/compose/catalog.json`: `"features": { "worker": false }`
2. `stack-kit compose-gen`
3. Declare worker deployables in `stack-kit.json` `modules` + `stack.composeModules`.
