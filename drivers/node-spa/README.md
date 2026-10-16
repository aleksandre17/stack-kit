# node-spa

A single-page app run by **its own `package.json` scripts**, whatever framework writes them:
Angular CLI (`ng build`, `ng test`, `ng serve`), Vite, React, Vue, Svelte. The driver assumes no
bundler, no output directory and no dev-server port: the package says, the driver runs it.

| Command | Runs | Where it comes from |
|---|---|---|
| `build`, `test`, `lint` | `<pm> run <script>` in the module directory | registry `packageScripts`; a module renames one in `node.scripts.<step>` (`""` = none) |
| `run` (= `hybrid boot`) | the `start` script, with the module's `.env` + `.env.dev` in the process | the kit's host runner, then `ps1/hybrid.ps1` |
| `deploy` (`deliver release`) | the kit's release: `build` packages `dist/**` once per commit; its image is built on the target from the release by the shared recipe (`drivers/_shared/static/Dockerfile`): the pinned unprivileged nginx serving `container.serve` (default `dist`; Angular: `dist/<app>/browser`), every app route answered by `index.html`, its rendered `server.conf` COPYed in; per-environment values are runtime config, mounted read-only | registry `package`, `container` |
| `stack up` (the local docker stack) | the same recipe, built from the release tree `package` left (staged in `.stack-kit/local/<module>/`) -- the UI runs locally in docker as it runs on a target | registry `compose` (`fromRelease`) |
| `dev up` (`deliver remote-dev`) | the `start` script with `--host 0.0.0.0` in a Node container on port 4200, the source synced into the workspace | registry `dev` |

`<pm>` is `node.packageManager`, else the one whose lockfile is nearest above the module
(`pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`), else npm. When `node_modules` is absent the
dependencies are installed from the lockfile first (`npm ci`, `pnpm install --frozen-lockfile`,
`yarn install --frozen-lockfile`), so a fresh clone builds as it is. A `lint` the package lacks is
skipped and said; a missing `build` or `test` fails and names the remedy.

```json
"web": {
  "type": "node-spa", "role": "ui", "path": "apps/web", "secretsModule": "web",
  "node": { "scripts": { "test": "test:ci" } },
  "toolchain": { "version": "22" }
}
```

For Angular in CI, give `test` a non-watching script (`"test:ci": "ng test --watch=false --browsers=ChromeHeadless"`).
The runner is `drivers/_shared/package-scripts/Invoke-PackageScript.ps1`, shared by every Node-family driver; proof:
`tests/acceptance/test_lifecycle.py`.
