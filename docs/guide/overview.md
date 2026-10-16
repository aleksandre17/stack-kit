# Overview

## The manifest and its modules

A host declares one manifest, `stack-kit.json`:

- its project slug;
- its modules: path, driver type and role;
- the commands a change is built and proven with;
- where its deploy targets and configuration catalogue live.

Everything else is derived from that declaration.

## Drivers

A driver (`drivers/<id>/`, listed in `drivers/registry.json`) is everything the kit knows about one
toolchain:

- how its presence is detected;
- its lint, build, test, audit and package commands;
- its release container recipe (multi-stage where a stage does work, non-root `USER`, `HEALTHCHECK`):
  every deployable module runs an image built from it, a UI module's included -- the pinned
  unprivileged nginx with the built app and its rendered server config -- so the local stack, a dev
  release and prod run the same recipe;
- its dev container (image, command, caches, sync excludes, reactions to changes);
- the files its build writes (`outputs`; `validate` refuses them when tracked);
- its health probe.

No generic code names a tool. A new toolchain is a new driver, never a code change; an agnosticism
test enforces this. A module may override a driver fact it owns, for example `container.serve`,
`container.proxy`, `node.scripts.dev` or `package.exclude`.

## Roles, tiers, environments, lifecycle steps

These are declared catalogues under `config/catalogs/`, and a host may overlay them:

| Catalogue | What it declares |
|---|---|
| roles | api, worker, gateway, data, ui |
| tiers | backend, frontend; each role names its tier |
| environments | dev, prod, or a host's own such as staging |
| lifecycle steps | lint, build, test, and declared kinds such as e2e or visual regression |
| target runtimes | docker-compose, static, iis |

## The CLI

There is one entry point, the same in a terminal and in CI. A host keeps a thin launcher
(`ops/cli/stack-kit.ps1` or `.sh`) over the Python CLI.

- Every verb has `--help` with its exit codes.
- Every verb that changes a server prints its plan first, and `--plan` writes nothing.
- An environment that confirms asks before acting; `--yes` answers in CI.
- A reading verb never asks.

[OPERATIONS.md](../OPERATIONS.md) is the full list.
