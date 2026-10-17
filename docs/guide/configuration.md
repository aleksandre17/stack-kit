# Configuration

## The catalogue

The configuration catalogue (`config.keys`, for example `ops/config/schema/config-keys.json`) is the
one home of every runtime key. Each key declares:

| Field | Meaning |
|---|---|
| `sensitivity` | `PUBLIC`, `INTERNAL` or `SECRET`. A SECRET never has a committed value and always declares its rotation. |
| `policy.modules` | the modules that read it. A SECRET must name them once a project has more than one secrets folder, so it never reaches a module that does not need it. |
| `policy.required` | where it must be set; a secret not required in an environment is left unset there |
| `default`, `environments` | non-secret values, one per environment |
| `dataSource: true` | it names a store; each environment's store is compared, and `none` writes an unroutable sentinel so the app can never reach a real store |
| `generate: random:<bytes>` | made by the kit: locally into an ignored env file, and on the server once (umask 077, never read back), handed to the app in the form its driver declares (`generatedSecrets`): a directory of key-per-file values under one env name (ASP.NET Core: `KeyPerFile__Directory`), or `<NAME>_FILE`. `validate` refuses a module given a generated secret its code never reads, a release one its built output never reads, a rollback one on the server -- a secret made and ignored leaves the app on whatever value it finds elsewhere |

## Env files

| File | Status | What it is |
|---|---|---|
| `<module>/.env.example` | committed | a projection of the catalogue (`render`), never written by hand |
| `<module>/.env.<env>` | ignored | made once by `extend env <module> --env <env>`: defaults filled, secrets pending, generated keys fresh |

`config --env <env>` checks a machine's env files against the policy, by name and never by value. A
deploy is refused while a required secret is pending.

## Secrets

`scan secrets` checks the tracked tree, and `scan secrets --history` checks every commit.

- The patterns come from a declared catalogue (`security.secretPatterns`: documents of the
  edit-gate contract, the same files an agent's commit gate judges by), or from the kit's built-in
  set when none is declared.
- A finding is allowed only with a path, a rule and a reason (`security.allow`), or listed by its
  fingerprint once it has been rotated (`security.knownLeaks`).
- Values are never printed.
