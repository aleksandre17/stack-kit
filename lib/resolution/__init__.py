"""The one resolver (ADR-001 decision 2), in three parts with one job each (amendment 13):

    context    what the manifest says: one flat map, identical in every runtime
    resolver   the environment's answers: env files and values, the selected deploy target
    infra      the local infra stack's compose files and tunnels
"""
from lib.resolution.context import KIT_ROOT, context, monorepo_root, slugify  # noqa: F401
from lib.resolution.resolver import Resolver  # noqa: F401
