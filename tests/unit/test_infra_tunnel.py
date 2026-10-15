"""Infra SSH tunnel forwards — manifest services + catalog only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.infra_tunnel import load_infra_catalog, resolve_tunnel_forwards

CATALOG = {
    "modules": {
        "postgres": {"tunnel": [{"env": "POSTGRES_PORT", "default": "5432"}]},
        "redis": {"tunnel": [{"env": "REDIS_PORT", "default": "6379"}]},
        "qdrant": {
            "tunnel": [
                {"env": "QDRANT_HTTP_PORT", "default": "6333"},
                {"env": "QDRANT_GRPC_PORT", "default": "6334"},
            ]
        },
    }
}


def _env(values: dict[str, str]):
    def get(key: str, default: str) -> str | None:
        if key in values:
            return values[key]
        return default or None

    return get


def test_postgres_only():
    forwards = resolve_tunnel_forwards(
        service_ids=["postgres"],
        catalog=CATALOG,
        env_getter=_env({}),
    )
    assert forwards == [("5432", "5432")]


def test_all_three_dedupe_ports():
    forwards = resolve_tunnel_forwards(
        service_ids=["postgres", "redis", "qdrant"],
        catalog=CATALOG,
        env_getter=_env({}),
    )
    assert len(forwards) == 4
    assert ("5432", "5432") in forwards
    assert ("6334", "6334") in forwards


def test_env_override():
    forwards = resolve_tunnel_forwards(
        service_ids=["postgres"],
        catalog=CATALOG,
        env_getter=_env({"POSTGRES_PORT": "5433"}),
    )
    assert forwards == [("5433", "5433")]


def test_unknown_service_raises():
    with pytest.raises(ValueError, match="unknown module"):
        resolve_tunnel_forwards(
            service_ids=["elasticsearch"],
            catalog=CATALOG,
            env_getter=_env({}),
        )


def test_merge_consumer_catalog(tmp_path: Path):
    kit = tmp_path / "kit.json"
    kit.write_text(
        json.dumps({"modules": {"postgres": {"tunnel": [{"env": "POSTGRES_PORT", "default": "5432"}]}}}),
        encoding="utf-8",
    )
    consumer = tmp_path / "consumer.json"
    consumer.write_text(
        json.dumps(
            {
                "modules": {
                    "elastic": {
                        "tunnel": [{"env": "ELASTIC_PORT", "default": "9200"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    merged = load_infra_catalog(kit, consumer)
    forwards = resolve_tunnel_forwards(
        service_ids=["postgres", "elastic"],
        catalog=merged,
        env_getter=_env({"ELASTIC_PORT": "9200"}),
    )
    assert ("5432", "5432") in forwards
    assert ("9200", "9200") in forwards
