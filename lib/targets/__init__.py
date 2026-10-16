"""Deploy targets (ADR-001 amendments 9, 13), in three parts with one job each:

    declaration   what a host declares: load, select, reachable, validate's problems and notices
    layout        the ONE renderer of remote paths, confined to the project's own directory
    remote        how a target is reached (ssh) and what runs there (engine, compose)
"""
from lib.targets.declaration import (  # noqa: F401
    TargetError, declared_file, environments, keep, load, local_file, notices, problems, reachable, select, server,
)
from lib.targets.layout import (  # noqa: F401
    KINDS, MARKER, LayoutError, Places, declared_root, default_layout, render, render_legacy, under, unproven,
)
from lib.targets.remote import (  # noqa: F401
    check_health_urls, check_oidc, health_urls, identity_kind, local_commands, repository_identity, runs_stack, runtime_commands, ssh_args,
)
