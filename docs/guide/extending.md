# Extending: extension points

A host never edits the kit. It adds its own through a declared **extension point**: a template the
kit scaffolds on demand into a host path, with pending answers that `validate` reports.

```text
stack-kit extend --list                     every point, where its file goes, its status
stack-kit extend <point> [<name>] --plan    what would be created
stack-kit extend <point> [<name>]           create it (refuses to overwrite)
stack-kit extend env <module> --env <env>   the ignored env file, from the catalogue
```

**Points:**

- modules;
- catalogue overlays: roles, tiers, environments, lifecycle, target runtimes, runtimes;
- targets and `targets.local`;
- the host key pin;
- runtime config;
- configuration keys;
- infra services and their entries;
- backup anchors;
- env examples;
- a driver override and its registry entry;
- the CI pins;
- the init files: launchers, `.gitignore`, the compose READMEs.

Init files are placed by the host's layout profile, tiers and module paths.

**Shared registry shape.** The registry of points has the same shape as agent-kit's. Its schema is
vendored here with its origin and digest recorded.

**Template changes.** When a kit template changes, it is merged into the host's file by a three-way
merge. A conflict is reported, never overwritten.

**Undeclared files.** A tracked file in a place a point owns, but declared by no point, is reported.
Ignored files are machine state and are not reported.
