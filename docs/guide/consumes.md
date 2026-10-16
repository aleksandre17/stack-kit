# Consuming a shared platform

A project often runs beside a platform it does not own: another project's edge proxy with TLS, a
telemetry collector, an identity provider. The project does not copy that infra, and it does not edit
the platform's files. It **declares what it consumes**.

## The project's declaration

In the manifest:

```json
"consumes": {
  "networks":  { "platform":  { "services": ["web"], "owner": "the platform project" } },
  "endpoints": { "telemetry": { "env": "TELEMETRY_ENDPOINT", "services": ["api"] } },
  "routes":    [ { "environment": "prod", "host": "app.example", "service": "web", "tls": "required" } ]
}
```

## The target's answer

On the target, each consumed name is mapped to what it is called on that host:

```json
"consumes": {
  "networks":  { "platform":  "platform-net" },
  "endpoints": { "telemetry": { "prod": "http://collector:4318" } }
}
```

## What the kit does with it

- **Compose.** Each consuming service joins the network as `external`, and gets the endpoint as its
  variable. No deploy, regenerate or `nuke` ever creates or removes a consumed network.
- **Preflight.** It reads (read-only) that each consumed network exists on the target. A missing one
  stops the run with `NOT RUN` (exit 4), naming its owner and the command the owner would run. The
  kit never runs that command.
- **Routes.** `render` writes the requested routes to `ops/compose/stack/<env>/edge-routes.json` for
  the platform's owner to apply. `validate` reports when that file is stale.
- **`validate`.** It refuses:
  - unknown services or environments;
  - unreachable routes;
  - a target that lacks a name or an address;
  - a name inside the project's own namespace;
  - an address that carries a credential.
